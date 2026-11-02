"""Every copy of a work's picture the sources have, for the owner to pick
from ("Szukaj lepszej kopii" on the work's card).

The look in the background (:mod:`frame_server.sharper`) takes a copy only
when it is certainly better, and says nothing. Here the owner sees them all
as the sources answer: each copy judged by the same tests (the same picture
whole, in its colours, not a reproduction, how much sharper on the frame),
with the reason when it falls short, and a close-up of one spot in both
pictures at the frame's scale (:meth:`Copies.compare`). The pick is kept as
the work's sharper copy (``Item.sharper``, marked ``chosen``): the work
keeps its id, texts, hearts, playlists and crops.
"""

from __future__ import annotations

import base64
import io
import logging
import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, as_completed, wait
from typing import TYPE_CHECKING, Literal

import httpx
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from .imaging.layout import load_image
from .library import Item, ItemKind
from .library.duplicates import surname
from .library.images import IMAGE_MAX, display_copy, own_copy
from .library.likeness import WHOLE_TURN, Fit, keypoints
from .library.vocabulary import is_copy, is_photograph, is_reproduction
from .sharper import Quality, colour_note, tone

if TYPE_CHECKING:
    from .sharper import Sharper

log = logging.getLogger(__name__)

#: Results asked from each source (the look in the background asks fewer).
HITS = 12
#: Copies whose pictures are downloaded to be measured, at most, per look.
MEASURED = 6
#: Seconds the sources have to answer; one still silent then is told as
#: failed. Its search goes on in the background (Openverse can take a minute,
#: Paris Musées longer) for up to LATE seconds, and what it finds is kept for
#: the next look (KEPT_ANSWERS).
ANSWER = 20.0
LATE = 90.0
#: How long a source's answer to one query is kept, in seconds, and how many.
KEPT_FOR = 6 * 3600.0
KEPT_ANSWERS = 200
#: Sources whose search looks for the whole query in the title alone: asked
#: for the title only, the artist is checked on what they find.
TITLE_ONLY = ("paris",)
#: Copies judged at once (thumbnails downloaded, keypoints compared).
JUDGES = 4
#: The close-up's side, in pixels of the picture at the frame's scale.
SPOT = 320
#: Pictures kept in memory for close-ups (the app asks for several spots).
KEPT = 4

Verdict = Literal["checking", "better", "warn", "worse", "off"]
Role = Literal["copy", "current", "own"]


class CopyView(BaseModel):
    """One copy of the work's picture as the owner sees it in the list.

    ``verdict``: "better" (sharper on the frame, the same picture whole in
    its colours), "warn" (sharper, but its colours differ), "worse" (the
    same picture, not sharper), "off" (a detail, a page around it, a grey
    plate, a reproduction: only to look at), "checking" (being compared).
    ``notes``: why, as codes the app names: "whole", "colours", "fragment",
    "page", "turned", "grey", "coloured", "colour-off", "reproduction".
    ``role``: "current" (the picture shown now), "own" (the work's own
    picture, while a copy stands in for it), "copy"."""

    item_id: str
    source: str
    museum: str = ""
    #: The copy's page at its source.
    url: str = ""
    width: int = 0
    height: int = 0
    bits: float | None = None
    #: Measured from the downloaded picture rather than taken from the
    #: source's description.
    measured: bool = False
    #: How many times sharper than the picture shown now, on the frame.
    gain: float | None = None
    verdict: Verdict = "checking"
    notes: list[str] = Field(default_factory=list)
    role: Role = "copy"
    #: The current picture is a copy the owner picked.
    chosen: bool = False


class CopyLine(BaseModel):
    """One line of the answer, as it comes (JSON lines): "start" (the
    sources asked), "copy" (a copy, new or judged: the app replaces it by
    ``item_id``), "drop" (a copy that is another picture after all),
    "source" (a source has answered: how many copies, or that it failed),
    "end"."""

    kind: Literal["start", "copy", "drop", "source", "end"]
    sources: list[str] = Field(default_factory=list)
    source: str = ""
    found: int = 0
    failed: bool = False
    copy_: CopyView | None = Field(None, alias="copy", serialization_alias="copy")
    item_id: str = ""

    model_config = {"populate_by_name": True}


class Spot(BaseModel):
    """One spot of the picture in both: where (fractions of the work's
    picture shown now: its centre and its width and height) and the two
    close-ups at the frame's scale (JPEG)."""

    x: float
    y: float
    w: float
    h: float
    #: JPEG, in standard base64 (as the app's JSON decoder reads ``Data``).
    current: str
    copy_: str = Field(alias="copy", serialization_alias="copy")

    model_config = {"populate_by_name": True}


def frame_side(side: int) -> int:
    return min(side, IMAGE_MAX)


def gain(copy: Quality, current: Quality) -> float | None:
    if not copy.side or not current.side:
        return None
    return round(frame_side(copy.side) / frame_side(current.side), 2)


class Copies:
    def __init__(self, sharper: Sharper) -> None:
        self.sharper = sharper
        self.images = sharper.images
        self.likeness = sharper.likeness
        importer = sharper.importer
        #: The sources asked, and one source's results for a query.
        self.sources: Callable[[], list[str]] = importer.sources
        self.search_in: Callable[[str, str, int], list[Item]] = lambda key, query, n: (
            importer.search(key, query, n, wait=LATE)[1]
        )
        self.answer = ANSWER
        #: Sources' answers by (source, query): when, and the works found.
        self._answers: OrderedDict[tuple[str, str], tuple[float, list[Item]]] = OrderedDict()
        self._kept: OrderedDict[str, Image.Image] = OrderedDict()
        self._lock = threading.Lock()

    # -- the list ------------------------------------------------------------------

    def look(self, item: Item, emit: Callable[[CopyLine], None], gone: threading.Event) -> None:
        """Every copy of ``item``'s picture onto ``emit`` as the sources
        answer; stops early once ``gone`` is set (the app stopped
        listening)."""
        stored = self.sharper.library.get(item.id) or item
        keys = self.sources()
        emit(CopyLine(kind="start", sources=keys))
        current = self.current(stored)
        emit(CopyLine(kind="copy", copy=current))
        if stored.sharper is not None:
            emit(CopyLine(kind="copy", copy=self.own(stored)))
        quality = Quality(current.width and max(current.width, current.height), current.bits)
        seen = {stored.id, *([stored.sharper.item_id] if stored.sharper else [])}
        measured = [MEASURED]
        lock = threading.Lock()

        def fresh(found: Iterable[Item]) -> list[Item]:
            out = []
            with lock:
                for copy in found:
                    if copy.id in seen or not self._eligible(stored, copy):
                        continue
                    seen.add(copy.id)
                    out.append(copy)
            return out

        def judge(copy: Item) -> None:
            if gone.is_set():
                return
            try:
                view = self.judge(stored, copy, quality, measured, lock)
            except Exception:
                log.exception("judging copy %s of %s", copy.id, stored.id)
                view = None
            if view is None:
                emit(CopyLine(kind="drop", item_id=copy.id))
            else:
                emit(CopyLine(kind="copy", copy=view))

        def answered(key: str, future: Future[list[Item]]) -> None:
            failed = False
            try:
                hits = future.result()
            except Exception as err:  # one source's failure costs no other's copies
                log.info("copies of %s from %s: %s", stored.id, key or "known", err)
                hits, failed = [], True
            hits = [h for h in hits if not key or self.sharper._by_artist(stored, h)]
            new = fresh(hits)
            for copy in new:
                emit(CopyLine(kind="copy", copy=self.view(copy, quality, "checking")))
                judged.append(judging.submit(judge, copy))
            if key:
                emit(CopyLine(kind="source", source=key, found=len(new), failed=failed))

        title = stored.title[:80].strip()
        query = f"{title} {surname(stored.artist)}".strip()
        judged: list[Future[None]] = []
        # Not a ``with``: leaving it would wait for a source that does not answer.
        asking = ThreadPoolExecutor(max(1, len(keys)) + 1, "copies-ask")
        try:
            with ThreadPoolExecutor(JUDGES, "copies-judge") as judging:
                asked: dict[Future[list[Item]], str] = {asking.submit(self.known, stored): ""}
                for key in keys:
                    if text := title if key in TITLE_ONLY else query:
                        asked[asking.submit(self._ask, key, text)] = key
                waiting = set(asked)
                deadline = time.monotonic() + self.answer
                while waiting and not gone.is_set():
                    left = deadline - time.monotonic()
                    done, waiting = wait(waiting, max(left, 0.0), FIRST_COMPLETED)
                    for future in done:
                        answered(asked[future], future)
                    if not done:  # the time is up: the rest are told as silent
                        for future in waiting:
                            key = asked[future]
                            log.info(
                                "copies of %s from %s: no answer in %.0f s",
                                stored.id,
                                key or "known",
                                self.answer,
                            )
                            if key:
                                emit(CopyLine(kind="source", source=key, failed=True))
                        break
                for verdict in as_completed(judged):
                    verdict.result()
        finally:
            asking.shutdown(wait=False, cancel_futures=True)
        emit(CopyLine(kind="end"))

    def _ask(self, key: str, query: str) -> list[Item]:
        """``key``'s works for ``query``: kept from an earlier look (a source
        too slow then has answered since), else asked."""
        now = time.monotonic()
        with self._lock:
            kept = self._answers.get((key, query))
            if kept is not None and now - kept[0] < KEPT_FOR:
                return list(kept[1])
        found = self.search_in(key, query, HITS)
        with self._lock:
            self._answers[(key, query)] = (time.monotonic(), list(found))
            self._answers.move_to_end((key, query))
            while len(self._answers) > KEPT_ANSWERS:
                self._answers.popitem(last=False)
        return found

    def known(self, item: Item) -> list[Item]:
        """Copies known without a search: the work's Commons file and the
        library's copies of it."""
        found: list[Item] = []
        if self.sharper.commons_file is not None and (name := self.sharper.commons_file(item)):
            try:
                if (copy := self.sharper.importer.commons_file(name)) is not None:
                    found.append(copy)
            except (httpx.HTTPError, ValueError) as err:
                log.info("Commons file of %s: %s", item.id, err)
        works = self.sharper.library.works()
        index = works.group_of(item)
        if index is not None:
            found += [i for i in works.groups[index] if i.id != item.id]
        return found

    @staticmethod
    def _eligible(item: Item, copy: Item) -> bool:
        """A work's picture, with a picture: no photo sent once, no photograph
        of a work that is none (reproductions are shown, as "off")."""
        return (
            copy.kind == ItemKind.ARTWORK
            and copy.look is None
            and copy.sharper is None
            and (is_photograph(item) or not is_photograph(copy))
            and bool(display_copy(copy))
        )

    def current(self, item: Item) -> CopyView:
        """The picture shown now: the work's own or the copy in its place."""
        if item.sharper is not None:
            copy = item.sharper
            size = self.images.source_size(item)
            bits = Quality.of(*size).bits if size else None
            return CopyView(
                item_id=copy.item_id,
                source=copy.source,
                museum=copy.museum,
                url=self._page(copy.item_id),
                width=copy.width,
                height=copy.height,
                bits=bits,
                measured=True,
                verdict="better",
                role="current",
                chosen=copy.chosen,
            )
        own = self.sharper.own(item)
        size = self.images.source_size(item) if own is not None and own.side else None
        view = self.view(item, own or Quality(0), "worse", role="current")
        view.bits = own.bits if own is not None else None
        if size is not None:
            view.width, view.height, view.measured = size[0], size[1], True
        return view

    def own(self, item: Item) -> CopyView:
        """The work's own picture, while a copy stands in for it."""
        size = self.sharper.own_size(item)
        width, height = (size[0], size[1]) if size else (item.width or 0, item.height or 0)
        bits = Quality.of(*size).bits if size else None
        assert item.sharper is not None
        current = Quality(max(item.sharper.width, item.sharper.height))
        return CopyView(
            item_id=item.id,
            source=item.source,
            museum=item.museum,
            url=item.url,
            width=width,
            height=height,
            bits=bits,
            measured=size is not None,
            gain=gain(Quality(max(width, height)), current),
            verdict="worse",
            notes=["whole", "colours"],
            role="own",
        )

    def view(self, copy: Item, current: Quality, verdict: Verdict, role: Role = "copy") -> CopyView:
        width, height = copy.width or 0, copy.height or 0
        return CopyView(
            item_id=copy.id,
            source=copy.source,
            museum=copy.museum,
            url=copy.url,
            width=width,
            height=height,
            gain=None if role == "current" else gain(Quality(max(width, height)), current),
            verdict=verdict,
            role=role,
        )

    def _page(self, item_id: str) -> str:
        found = self.sharper.importer.resolve(item_id)
        return found.url if found is not None else ""

    def judge(
        self,
        item: Item,
        copy: Item,
        current: Quality,
        measured: list[int] | None = None,
        lock: threading.Lock | None = None,
    ) -> CopyView | None:
        """``copy`` judged against ``item``'s picture (``current``: the one
        shown now); None when it is another picture altogether."""
        try:
            own_thumb = self.images.ensure_thumb(item)
            copy_thumb = self.images.ensure_thumb(copy)
        except (httpx.HTTPError, OSError) as err:
            log.info("thumbnails of %s and %s: %s", item.id, copy.id, err)
            return None
        fit = self.likeness.fit(item, copy)
        if fit is None:
            return None
        notes: list[str] = []
        off = False
        if fit.whole:
            notes.append("whole")
        elif fit.turn > WHOLE_TURN and fit.cover >= 0.8:
            notes.append("turned")
            off = True
        else:
            notes.append("fragment" if fit.inside > 1 else "page")
            off = True
        try:
            colours = colour_note(tone(own_thumb), tone(copy_thumb))
        except OSError:
            colours = None
        notes.append(colours or "colours")
        off = off or colours in ("grey", "coloured")
        if is_copy(copy) or is_reproduction(copy):
            notes.append("reproduction")
            off = True
        view = self.view(copy, current, "worse")
        quality = Quality(max(view.width, view.height))
        if not off and self._may_measure(measured, lock):
            try:
                img = self._picture(display_copy(copy))
            except (httpx.HTTPError, OSError) as err:
                log.info("copy %s of %s: %s", copy.id, item.id, err)
            else:
                quality = Quality.of_image(img)
                view.width, view.height = img.size
                view.bits = quality.bits
                view.measured = True
                view.gain = gain(quality, current)
        if off:
            view.verdict = "off"
        elif not quality.better(current):
            view.verdict = "worse"
        else:
            view.verdict = "warn" if colours else "better"
        view.notes = notes
        return view

    @staticmethod
    def _may_measure(measured: list[int] | None, lock: threading.Lock | None) -> bool:
        if measured is None:
            return True
        with lock or threading.Lock():
            if measured[0] <= 0:
                return False
            measured[0] -= 1
            return True

    # -- the pick --------------------------------------------------------------------

    def choose(self, item: Item, copy_id: str) -> Item:
        """The owner's pick for ``item``'s picture: a copy (``copy_id``), or
        the work's own (its own id). Raises LookupError for no such copy,
        ValueError for one that is another picture."""
        stored = self.sharper.library.get(item.id) or item
        if copy_id == stored.id:
            return self.sharper.keep_own(stored)
        copy = self.sharper.importer.resolve(copy_id)
        if copy is None or not display_copy(copy):
            raise LookupError(copy_id)
        self.images.ensure_thumb(stored)
        self.images.ensure_thumb(copy)
        if self.likeness.fit(stored, copy) is None:
            raise ValueError(f"{copy_id} is not a copy of {stored.id}")
        return self.sharper.choose(stored, copy)

    # -- the close-up ------------------------------------------------------------------

    def compare(self, item: Item, copy_id: str, x: float | None, y: float | None) -> Spot:
        """One spot (its centre at ``x``, ``y``; the most detailed one when
        not given) in the picture shown now and in the copy, both at the
        frame's scale. Raises LookupError for no such copy, ValueError for
        one that is another picture."""
        stored = self.sharper.library.get(item.id) or item
        if copy_id == stored.id and stored.sharper is not None:
            copy = stored.model_copy(update={"sharper": None})  # the work's own
            url = own_copy(stored)
        else:
            found = self.sharper.importer.resolve(copy_id)
            if found is None or not display_copy(found):
                raise LookupError(copy_id)
            copy, url = found, display_copy(found)
        path, _ = self.images.picture(stored, True)
        current = load_image(path).convert("RGB")
        self.images.ensure_thumb(stored)
        self.images.ensure_thumb(copy)
        fit = self.likeness.fit(stored, copy) if copy.id != stored.id else None
        if fit is None and copy.id != stored.id:
            raise ValueError(f"{copy_id} is not a copy of {stored.id}")
        picture = self._picture(url)
        # The picture shown now, at the frame's scale (its long side the frame's).
        scale = IMAGE_MAX / max(current.size)  # small pictures are enlarged on the frame
        fw, fh = current.width * scale, current.height * scale
        w, h = min(1.0, SPOT / fw), min(1.0, SPOT / fh)
        if x is None or y is None:
            x, y = self._busiest(stored, w, h)
        x, y = min(max(x, w / 2), 1 - w / 2), min(max(y, h / 2), 1 - h / 2)
        side = (round(min(SPOT, fw)), round(min(SPOT, fh)))
        here = _cut(current, (x, y, w, h), side)
        there = _cut(picture, _laid(fit, (x, y, w, h)) if fit else (x, y, w, h), side)
        return Spot(x=x, y=y, w=w, h=h, current=_jpeg(here), copy_=_jpeg(there))

    def _busiest(self, item: Item, w: float, h: float) -> tuple[float, float]:
        """The centre of the spot with the most keypoints (the most detail),
        as fractions of the picture."""
        found = keypoints(self.images.thumb_path(item))
        if found is None or not len(found.points):
            return 0.5, 0.45
        tw, th = found.size
        pts = found.points / np.array([tw, th], dtype=np.float32)
        best, at = -1, (0.5, 0.45)
        steps = 9
        for i in range(steps):
            for j in range(steps):
                cx = w / 2 + (1 - w) * i / (steps - 1)
                cy = h / 2 + (1 - h) * j / (steps - 1)
                inside = (np.abs(pts[:, 0] - cx) <= w / 2) & (np.abs(pts[:, 1] - cy) <= h / 2)
                count = int(inside.sum())
                if count > best:
                    best, at = count, (cx, cy)
        return at

    def _picture(self, url: str) -> Image.Image:
        """A copy's picture, downloaded once for its measure and close-ups."""
        with self._lock:
            img = self._kept.get(url)
            if img is not None:
                self._kept.move_to_end(url)
                return img
        img = self.images.sample(url, urgent=True)
        with self._lock:
            self._kept[url] = img
            while len(self._kept) > KEPT:
                self._kept.popitem(last=False)
        return img


def _laid(fit: Fit, spot: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """``spot`` (fractions of the first picture) laid over the second by the
    thumbnails' mapping."""
    x, y, w, h = spot
    aw, ah = fit.a.size
    bw, bh = fit.b.size
    m = np.asarray(fit.mapping, float)
    cx, cy = m @ np.array([x * aw, y * ah, 1.0])
    scale = math.hypot(m[0][0], m[1][0])
    return float(cx / bw), float(cy / bh), float(w * aw * scale / bw), float(h * ah * scale / bh)


def _cut(
    img: Image.Image, spot: tuple[float, float, float, float], side: tuple[int, int]
) -> Image.Image:
    x, y, w, h = spot
    w, h = min(w, 1.0), min(h, 1.0)
    x, y = min(max(x, w / 2), 1 - w / 2), min(max(y, h / 2), 1 - h / 2)  # inside the picture
    box = (
        max(0.0, (x - w / 2) * img.width),
        max(0.0, (y - h / 2) * img.height),
        min(float(img.width), (x + w / 2) * img.width),
        min(float(img.height), (y + h / 2) * img.height),
    )
    return img.convert("RGB").resize(side, Image.Resampling.LANCZOS, box=box)


def _jpeg(img: Image.Image) -> str:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return base64.b64encode(out.getvalue()).decode()
