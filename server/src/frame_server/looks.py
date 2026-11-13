"""How works look, as numbers: Szukaj by words for how a work looks, by a
photograph of one, and the works that look like a work (Mateusz
2026-11-13, "G1": "wdrażamy G1").

Google's embedding model (``ai.gemini``: :meth:`Painter.embed`) turns a
work's thumbnail into :data:`~frame_server.ai.gemini.EMBED_SIZE` numbers
once, and words or a photograph the same way when they are asked about:
works that look alike, and the words for how they look, lie close. The
numbers are kept here (:class:`LookIndex`, some 75 MB for 100 000 works)
and every question after the first is answered on the server, in a few
milliseconds, without asking Google again. A trial on 2000 works of the
Cleveland Museum of Art (2026-11-13): "Zwiastowanie" eight Annunciations,
"melancholijny nastrój, ciemne barwy" Munch and Dürer, a van Gogh from
elsewhere three van Goghs of Cleveland; 0.23 USD.

Only the museums' works are sent: never the owner's photos nor his own
works. A work gets its numbers in the background (:meth:`Looks.start`),
through Google's Batch at half the price (Mateusz 2026-11-13: "Rozumiem że
ta praca G1 pójdzie przez batch?"; some 0.006 cent a work): those cared
about first, :data:`PER_BATCH` works a batch and :data:`OPEN` batches at
a time, while the Gemini page's switch is on and the image model's
month's limit allows; a work whose picture changed (a sharper copy, the
creative restorer) gets them anew. Only words and photographs asked about
are sent at once.
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import numpy as np
from PIL import Image

from .ai.client import AiUnavailable
from .ai.gemini import EMBED_MAX, EMBED_SIZE, NotDrawn, TooHeavy
from .library.models import Item, ItemKind
from .library.verdict import Place, against

if TYPE_CHECKING:
    from .ai.config import AiConfigStore
    from .ai.gemini import Painter
    from .library import Library
    from .library.images import ImageCache

log = logging.getLogger(__name__)

#: What the numbers' cost is counted as, in the image model's month.
KIND = "looks"
#: Works sent in one round of the background, and the pause between rounds
#: while some are left; when none is, it looks again after :data:`IDLE`.
PER_BATCH = 300
OPEN = 8
#: Seconds between looks at the batches out (a small one is back in minutes).
POLL = 120.0
IDLE = 600.0
#: The batches out, kept across restarts (the works in each, and their stamps).
BATCHES = "batches.json"
#: After Google's trouble (busy, a refusal, the limit): a longer rest.
REST = 1800.0
#: Words are asked as a search (Google's own advice for gemini-embedding-2);
#: pictures go as they are.
QUERY = "task: search result | query: "
#: Words remembered with their numbers: the same words cost nothing again.
REMEMBERED = 500
#: A search's answer: at most this many works, and only those near the best:
#: words in the trial lay at 0.60-0.67 from the works they fit and at about
#: 0.56 from those they did not, so a work further than :data:`NEAR_BEST`
#: below the best, or under :data:`FLOOR`, is left out.
MOST = 60
NEAR_BEST = 0.07
FLOOR = 0.52
#: A picture (a photograph, a work) is closer to works than words are.
PICTURE_FLOOR = 0.60
#: Szukaj's own list (Mateusz 2026-11-13: "strumień dzieł „szukaj wyglądem”
#: musiałby trafiać w tę samą listę co zwykłe wyszukiwanie"): the works
#: looked through for words narrowed by the groups, and at most this many
#: shown, nearest first.
AMONG_NEAR = 3000
AMONG_MOST = 240
#: A work whose thumbnail is not here is looked at again after this long.
NO_THUMB_AGAIN = 86_400.0
#: Rows of the numbers worked through at once (some 12 MB as floats).
CHUNK = 16_384
#: Rows no longer used (a work's picture changed, the work gone) as a share
#: of all, from which the file is written anew.
DEAD_SHARE = 0.2


@dataclass(frozen=True)
class Found:
    """A work near what was asked, and how near (cosine, -1 to 1)."""

    item: Item
    score: float


class LookIndex:
    """The numbers of works, one row each, kept on disk in ``root``:
    ``vectors.i8`` (the rows, each number as a byte: its direction is what
    counts) and ``ids.txt`` (the row's work and the stamp of the picture it
    was made from). A work's later row wins; earlier ones are dead."""

    def __init__(self, root: Path, size: int = EMBED_SIZE) -> None:
        self.root = root
        self.size = size
        self._lock = threading.Lock()
        self._rows = np.zeros((0, size), dtype=np.int8)
        self._norms = np.zeros(0, dtype=np.float32)
        self._ids: list[str] = []
        self._row: dict[str, int] = {}
        self._stamps: dict[str, int] = {}
        self._load()

    @property
    def _vectors(self) -> Path:
        return self.root / "vectors.i8"

    @property
    def _names(self) -> Path:
        return self.root / "ids.txt"

    def _load(self) -> None:
        if not self._vectors.is_file() or not self._names.is_file():
            return
        try:
            raw = np.fromfile(self._vectors, dtype=np.int8)
            lines = self._names.read_text(encoding="utf-8").splitlines()
        except OSError:
            log.exception("looks: the kept numbers cannot be read")
            return
        count = min(len(raw) // self.size, len(lines))
        rows = raw[: count * self.size].reshape(count, self.size)
        ids, stamps = [], []
        for line in lines[:count]:
            item_id, _, stamp = line.partition("\t")
            ids.append(item_id)
            stamps.append(int(stamp) if stamp.isdigit() else 0)
        self._rows = rows.copy()
        self._norms = np.linalg.norm(self._rows.astype(np.float32), axis=1).astype(np.float32)
        self._ids = ids
        self._row = {item_id: at for at, item_id in enumerate(ids)}
        self._stamps = {item_id: stamps[at] for item_id, at in self._row.items()}
        if count < len(lines) or count * self.size < len(raw):
            self._rewrite()  # a write broken off: the whole rows kept

    def __len__(self) -> int:
        return len(self._row)

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._row

    def stamp(self, item_id: str) -> int | None:
        return self._stamps.get(item_id)

    def ids(self) -> set[str]:
        with self._lock:
            return set(self._row)

    @staticmethod
    def quantised(vectors: np.ndarray) -> np.ndarray:
        """Each row as bytes in the same direction."""
        vectors = np.asarray(vectors, dtype=np.float32)
        peak = np.abs(vectors).max(axis=1, keepdims=True)
        peak[peak == 0] = 1.0
        return np.round(vectors / peak * 127).astype(np.int8)

    def add(self, rows: Sequence[tuple[str, int, Sequence[float]]]) -> None:
        """Keeps ``(work, stamp, numbers)`` rows, after those kept."""
        if not rows:
            return
        vectors = np.array([r[2] for r in rows], dtype=np.float32)
        if vectors.shape[1] != self.size:
            raise ValueError(f"{vectors.shape[1]} numbers a row, {self.size} kept")
        packed = self.quantised(vectors)
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with self._vectors.open("ab") as out:
                out.write(packed.tobytes())
            with self._names.open("a", encoding="utf-8") as out:
                out.writelines(f"{item_id}\t{stamp}\n" for item_id, stamp, _ in rows)
            start = len(self._ids)
            self._rows = np.concatenate([self._rows, packed])
            self._norms = np.concatenate(
                [self._norms, np.linalg.norm(packed.astype(np.float32), axis=1)]
            )
            for at, (item_id, stamp, _) in enumerate(rows):
                self._ids.append(item_id)
                self._row[item_id] = start + at
                self._stamps[item_id] = stamp
            if self._dead_share() > DEAD_SHARE:
                self._rewrite()

    def forget(self, item_ids: Iterable[str]) -> None:
        """Rows of works gone (left on disk until it is written anew)."""
        with self._lock:
            for item_id in item_ids:
                self._row.pop(item_id, None)
                self._stamps.pop(item_id, None)
            if self._dead_share() > DEAD_SHARE:
                self._rewrite()

    def _dead_share(self) -> float:
        return 1 - len(self._row) / len(self._ids) if self._ids else 0.0

    def _rewrite(self) -> None:
        """Only the live rows, written to new files that then take the old
        ones' place."""
        live = sorted(self._row.items(), key=lambda kv: kv[1])
        at = np.array([row for _, row in live], dtype=np.int64)
        rows = self._rows[at] if len(at) else np.zeros((0, self.size), dtype=np.int8)
        self.root.mkdir(parents=True, exist_ok=True)
        vectors, names = self._vectors.with_suffix(".new"), self._names.with_suffix(".new")
        rows.tofile(vectors)
        names.write_text(
            "".join(f"{item_id}\t{self._stamps.get(item_id, 0)}\n" for item_id, _ in live),
            encoding="utf-8",
        )
        os.replace(vectors, self._vectors)
        os.replace(names, self._names)
        self._rows = rows
        self._norms = self._norms[at] if len(at) else np.zeros(0, dtype=np.float32)
        self._ids = [item_id for item_id, _ in live]
        self._row = {item_id: n for n, item_id in enumerate(self._ids)}

    def vector(self, item_id: str) -> np.ndarray | None:
        """The work's numbers (as kept), or None."""
        with self._lock:
            row = self._row.get(item_id)
            return None if row is None else self._rows[row].astype(np.float32)

    def nearest(self, vector: Sequence[float] | np.ndarray, count: int) -> list[tuple[str, float]]:
        """The ``count`` works nearest ``vector``, nearest first, with their
        cosine."""
        query = np.asarray(vector, dtype=np.float32)
        length = float(np.linalg.norm(query))
        if length == 0 or count <= 0:
            return []
        query = query / length
        with self._lock:
            rows, norms, ids, live = self._rows, self._norms, self._ids, self._row
        if not len(rows):
            return []
        scores = np.empty(len(rows), dtype=np.float32)
        for start in range(0, len(rows), CHUNK):
            part = rows[start : start + CHUNK].astype(np.float32)
            scores[start : start + len(part)] = part @ query
        with np.errstate(divide="ignore", invalid="ignore"):
            scores = np.where(norms > 0, scores / norms, -1.0)
        found: list[tuple[str, float]] = []
        take = min(len(scores), count * 3 + 16)
        while True:
            best = (
                np.argpartition(-scores, take - 1)[:take]
                if take < len(scores)
                else np.arange(len(scores))
            )
            ordered = best[np.argsort(-scores[best])]
            found = [(ids[n], float(scores[n])) for n in ordered if live.get(ids[n]) == n]
            if len(found) >= count or take >= len(scores):
                return found[:count]
            take = min(len(scores), take * 4)


class Looks:
    """The works' numbers made in the background, and the questions asked
    of them: words, a photograph, a work."""

    def __init__(
        self,
        library: Library,
        images: ImageCache,
        painter: Painter,
        config: AiConfigStore,
        root: Path,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.library = library
        self.images = images
        self.painter = painter
        self.config = config
        self.index = LookIndex(root)
        self.root = root
        self.clock = clock
        #: The works cared about, by id (``cared.Cared.ranks``): sent first.
        self.cared: Callable[[], dict[str, int]] = dict
        self._words: OrderedDict[str, list[float]] = OrderedDict()
        self._words_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        #: Why the last round stopped short, for Konfiguracja.
        self.trouble: str | None = None
        #: Works whose thumbnail was not here, and when that was seen.
        self._no_thumb: dict[str, float] = {}
        self._counts: tuple[float, int, int] | None = None

    # -- what may be asked -----------------------------------------------------------

    def enabled(self) -> bool:
        """Google's key, and the Gemini page's switch on."""
        return self.painter.enabled() and self.config.config.looks

    def ready(self) -> bool:
        """Whether a question can be answered: some works have numbers."""
        return self.enabled() and len(self.index) > 0

    @staticmethod
    def wanted(item: Item) -> bool:
        """A museum's work with a picture (never the owner's own)."""
        return item.kind == ItemKind.ARTWORK and bool(item.thumb_url)

    def counts(self) -> tuple[int, int]:
        """Works with numbers, and works that would have them (worked out
        at most once a minute)."""
        kept = self._counts
        if kept is not None and self.clock() - kept[0] < 60:
            return kept[1], kept[2]
        items = self.library.all_items()
        wanted = {i.id for i in items if self.wanted(i)}
        done = len(wanted & self.index.ids())
        self._counts = (self.clock(), done, len(wanted))
        return done, len(wanted)

    # -- questions -------------------------------------------------------------------

    def words(self, text: str, limit: int = MOST) -> list[Found]:
        """Works that look like ``text`` says ("mglisty poranek nad wodą"),
        nearest first. Raises :class:`AiUnavailable` when it cannot ask."""
        text = " ".join(text.split())[:300]
        if not text:
            return []
        vector = self._words_vector(text)
        return self._answer(self.index.nearest(vector, limit * 3), limit, FLOOR)

    def among(self, text: str, allowed: Sequence[Item], limit: int = AMONG_MOST) -> list[Found]:
        """Works of ``allowed`` (what Szukaj's other choices found: a
        technique, a period, colours, a museum) that look like ``text``
        says, nearest first: Szukaj's one list (Mateusz 2026-11-13). A copy
        the index has stands for its work's copy in ``allowed``; only those
        near the best of them, and over :data:`FLOOR`. Raises
        :class:`AiUnavailable` when it cannot ask."""
        text = " ".join(text.split())[:300]
        if not text:
            return []
        self._check()  # also for words asked before (their numbers kept)
        if not allowed:
            return []
        vector = self._words_vector(text)
        by_id = {i.id: i for i in allowed}
        works = self.library.works()
        by_work: dict[int, Item] = {}
        for one in allowed:
            group = works.group_index(one.id)
            if group is not None:
                by_work.setdefault(group, one)
        near = self.index.nearest(vector, max(AMONG_NEAR, limit * 3))
        found: list[Found] = []
        seen: set[str] = set()
        bar: float | None = None
        for item_id, score in near:
            if len(found) >= limit:
                break
            item: Item | None = by_id.get(item_id)
            if item is None:
                group = works.group_index(item_id)
                item = by_work.get(group) if group is not None else None
            if item is None or item.id in seen:
                continue
            if bar is None:
                bar = max(FLOOR, score - NEAR_BEST)
            if score < bar:
                break
            seen.add(item.id)
            found.append(Found(item, round(score, 4)))
        return found

    def near(self, text: str) -> list[str] | None:
        """The ids of the works :meth:`among` chooses from for ``text``
        (the library puts its other rules through those alone), nearest
        first; None when it cannot be asked now."""
        text = " ".join(text.split())[:300]
        if not text:
            return []
        try:
            self._check()
            vector = self._words_vector(text)
        except AiUnavailable:
            return None
        except (NotDrawn, httpx.HTTPError) as err:
            log.warning("Szukanie wyglądem: Google did not answer (%s)", err)
            return None
        return [item_id for item_id, _ in self.index.nearest(vector, AMONG_NEAR)]

    def judge(self, text: str, items: Sequence[Item]) -> list[Item]:
        """Museum works a search for a look brought (``ai.look_words``):
        those that look as ``text`` says, as near as the catalogue's own
        answer asks (:data:`NEAR_BEST` below its best, over :data:`FLOOR`),
        nearest first (Mateusz 2026-11-13, card: "Hasła i ocena wyglądem").
        Their thumbnails get their numbers now, Google asked at once (some
        0.01 cent a work), and keep them: the catalogue's background asks
        nothing again for them, and the next search finds them at home.
        None when it cannot be asked now."""
        try:
            vector = np.asarray(self._words_vector(" ".join(text.split())[:300]))
        except (AiUnavailable, NotDrawn, httpx.HTTPError) as err:
            log.info("judging museum works by look: %s", err)
            return []
        if not items:
            return []
        self._number([i for i in items if i.id not in self.index])
        best = self.index.nearest(vector, 1)
        bar = max(FLOOR, (best[0][1] if best else FLOOR) - NEAR_BEST)
        length = float(np.linalg.norm(vector)) or 1.0
        scored: list[tuple[float, Item]] = []
        for item in items:
            row = self.index.vector(item.id)
            if row is None:
                continue
            norm = float(np.linalg.norm(row)) or 1.0
            score = float(row @ vector) / (norm * length)
            if score >= bar:
                scored.append((score, item))
        scored.sort(key=lambda s: -s[0])
        return [item for _, item in scored]

    def _number(self, items: Sequence[Item]) -> None:
        """Numbers for museum works' thumbnails (downloaded and kept, as the
        app shows them), asked of Google at once, :data:`EMBED_MAX` at a
        time; a work whose thumbnail cannot be had is left without."""
        if not items:
            return

        def picture(item: Item) -> tuple[Item, Image.Image, int] | None:
            try:
                path = self.images.ensure_thumb(item, urgent=True)
                stamp = int(path.stat().st_mtime)
                with Image.open(io.BytesIO(path.read_bytes())) as img:
                    img.load()
                    return item, img.convert("RGB"), stamp
            except Exception as err:  # gone, refused, not a picture
                log.info("no thumbnail of %s to judge by look: %s", item.id, err)
                return None

        with ThreadPoolExecutor(min(len(items), 8)) as pool:
            got = [p for p in pool.map(picture, items) if p is not None]
        for start in range(0, len(got), EMBED_MAX):
            part = got[start : start + EMBED_MAX]
            try:
                vectors = self.painter.embed(KIND, [img for _, img, _ in part])
            except (AiUnavailable, NotDrawn, httpx.HTTPError) as err:
                log.info("numbers for museum works: %s", err)
                return
            self.index.add(
                [(item.id, stamp, v) for (item, _, stamp), v in zip(part, vectors, strict=True)]
            )

    def looking(self, text: str, allowed: list[Item]) -> list[Item] | None:
        """:meth:`among` for the library (``Library.looking``): the works
        alone, None when it cannot be asked now."""
        try:
            return [f.item for f in self.among(text, allowed)]
        except AiUnavailable:
            return None
        except (NotDrawn, httpx.HTTPError) as err:
            log.warning("Szukanie wyglądem: Google did not answer (%s)", err)
            return None

    def picture(self, img: Image.Image, limit: int = MOST) -> list[Found]:
        """Works that look like ``img`` (a photograph of a work, a postcard)."""
        self._check()
        small = img.convert("RGB")
        small.thumbnail((640, 640))
        vector = self.painter.embed(KIND, [small])[0]
        return self._answer(self.index.nearest(vector, limit * 3), limit, PICTURE_FLOOR)

    def similar(self, item: Item, limit: int = 24, place: Place = Place.FOUND) -> list[Found]:
        """Works that look like ``item``: none until it or another copy of
        its work has numbers (the card shows the work's best copy, the
        index may have another: no "Podobne wyglądem" under van Gogh's
        Sunflowers found by a look, 2026-11-13). Its own copies and the work
        itself are left out; ``place``: where they are shown."""
        works = self.library.works()
        own = works.group_index(item.id)
        copies = [item.id] + (
            [c.id for c in works.groups[own] if c.id != item.id] if own is not None else []
        )
        vector = next((v for c in copies if (v := self.index.vector(c)) is not None), None)
        if vector is None:
            return []
        near = self.index.nearest(vector, limit * 3 + 8)
        near = [
            (i, s) for i, s in near if i != item.id and (own is None or works.group_index(i) != own)
        ]
        return self._answer(near, limit, PICTURE_FLOOR, relative=False, place=place)

    def neighbours(self, item_id: str, limit: int = 12) -> list[str]:
        """The ids of works that look most like ``item_id`` (the study's
        candidates of works like it, proposed by the server); none without
        its numbers or with Szukanie wyglądem off."""
        item = self.library.get(item_id)
        if item is None or not self.enabled():
            return []
        return [f.item.id for f in self.similar(item, limit, Place.PROPOSED)]

    def _check(self) -> None:
        if not self.painter.enabled():
            raise AiUnavailable("no Google API key")
        if not self.config.config.looks:
            raise AiUnavailable("Szukanie wyglądem is switched off")
        if not len(self.index):
            raise AiUnavailable("no work has its numbers yet")

    def _words_vector(self, text: str) -> list[float]:
        key = text.lower()
        with self._words_lock:
            if key in self._words:
                self._words.move_to_end(key)
                return self._words[key]
        self._check()
        vector = self.painter.embed(KIND, [QUERY + text])[0]
        with self._words_lock:
            self._words[key] = vector
            while len(self._words) > REMEMBERED:
                self._words.popitem(last=False)
        return vector

    def _answer(
        self,
        near: list[tuple[str, float]],
        limit: int,
        floor: float,
        relative: bool = True,
        place: Place = Place.FOUND,
    ) -> list[Found]:
        """The works of ``near`` worth showing: in the library, not hidden,
        shown where Szukaj shows works, one copy of each work (its best),
        not far below the best (``relative``) nor under ``floor``."""
        if not near:
            return []
        best = near[0][1]
        bar = max(floor, best - NEAR_BEST) if relative else floor
        hidden = self.library.hidden()
        works = self.library.works()
        seen: set[int | str] = set()
        found: list[Found] = []
        for item_id, score in near:
            if score < bar or len(found) >= limit:
                break
            item = self.library.get(item_id)
            if item is None or item.excluded or item in hidden:
                continue
            group = works.group_index(item_id)
            if group is not None:
                item = works.groups[group][0]
            key: int | str = group if group is not None else item_id
            if key in seen or against(item, place):
                continue
            seen.add(key)
            found.append(Found(item, round(score, 4)))
        return found

    # -- the background --------------------------------------------------------------

    def waiting(self, limit: int) -> list[tuple[Item, Path, int]]:
        """Up to ``limit`` works to send now, with their thumbnails and their
        stamps: without numbers, or with numbers of a picture since changed;
        those cared about first. Only thumbnails already here are sent."""
        have = self.index.ids()
        out = {item_id for rows in self._out().values() for item_id, _ in rows}
        ranks = self.cared()
        items = [i for i in self.library.all_items() if self.wanted(i)]
        # Cared about first, then those without numbers, then the rest
        # (whose picture may have changed).
        items.sort(key=lambda i: (ranks.get(i.id, 99), i.id in have))
        found: list[tuple[Item, Path, int]] = []
        for item in items:
            if len(found) >= limit:
                break
            if item.id in out:
                continue
            if item.id in have and ranks.get(item.id) is None:
                break  # works not cared about are looked at again only when gone
            seen = self._no_thumb.get(item.id)
            if seen is not None and self.clock() - seen < NO_THUMB_AGAIN:
                continue
            thumb = self.images.kept_thumb(item.id)
            if thumb is None:
                self._no_thumb[item.id] = self.clock()
                continue
            try:
                stamp = int(thumb.stat().st_mtime)
            except OSError:
                continue
            if self.index.stamp(item.id) == stamp:
                continue
            found.append((item, thumb, stamp))
        return found

    # -- the Batch --------------------------------------------------------------------

    def _out(self) -> dict[str, list[tuple[str, int]]]:
        """The batches out: their works and stamps, by the batch's name."""
        try:
            raw = json.loads((self.root / BATCHES).read_text())
        except (OSError, ValueError):
            return {}
        return {
            str(name): [(str(i), int(stamp)) for i, stamp in rows]
            for name, rows in raw.items()
            if isinstance(rows, list)
        }

    def _keep_out(self, out: dict[str, list[tuple[str, int]]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / BATCHES
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({name: [list(r) for r in rows] for name, rows in out.items()}))
        os.replace(temp, path)

    def collect(self) -> int:
        """The numbers of the batches Google has answered kept; how many
        works got them. A lost batch is dropped (its works go again)."""
        out = self._out()
        done = 0
        for name, rows in list(out.items()):
            try:
                found = self.painter.embed_batched(KIND, name)
            except NotDrawn as err:
                log.warning("looks: %s", err)
                del out[name]
                continue
            if found is None:
                continue
            stamps = dict(rows)
            kept = [
                (item_id, stamps[item_id], vector)
                for item_id, vector in found.items()
                if vector is not None and item_id in stamps
            ]
            self.index.add(kept)
            done += len(kept)
            del out[name]
        self._keep_out(out)
        return done

    def send(self) -> int:
        """Batches sent while fewer than :data:`OPEN` are out; how many
        works went."""
        if not self.enabled():
            return 0
        out = self._out()
        sent = 0
        while len(out) < OPEN and not self._stop.is_set():
            todo = self.waiting(PER_BATCH)
            pictures, rows = [], []
            for item, thumb, stamp in todo:
                try:
                    with Image.open(io.BytesIO(thumb.read_bytes())) as img:
                        img.load()
                        pictures.append((item.id, img.convert("RGB")))
                    rows.append((item.id, stamp))
                except OSError:
                    self._no_thumb[item.id] = self.clock()
            if not pictures:
                break
            sent += self._hand(pictures, rows, out)
            if len(todo) < PER_BATCH:
                break
        return sent

    def _hand(
        self,
        pictures: list[tuple[str, Image.Image]],
        rows: list[tuple[str, int]],
        out: dict[str, list[tuple[str, int]]],
    ) -> int:
        """Hands ``pictures`` to the Batch, in halves while they weigh more
        than Google takes at once (bigger thumbnails: 300 weighed 30 MB of
        19, and no work got its numbers from 2026-11-13 16:08 on); how many
        went. A picture too heavy alone waits as one without a thumbnail."""
        try:
            name = self.painter.embed_batch(KIND, pictures)
        except TooHeavy:
            if len(pictures) == 1:
                self._no_thumb[pictures[0][0]] = self.clock()
                return 0
            half = len(pictures) // 2
            return self._hand(pictures[:half], rows[:half], out) + self._hand(
                pictures[half:], rows[half:], out
            )
        out[name] = rows
        self._keep_out(out)
        return len(rows)

    def round(self) -> tuple[int, int]:
        """Collects what came back, then sends more: (works that got their
        numbers, works sent)."""
        return self.collect(), self.send()

    def tidy(self) -> int:
        """Rows of works no longer in the library forgotten; how many."""
        gone = self.index.ids() - {i.id for i in self.library.all_items()}
        self.index.forget(gone)
        return len(gone)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="looks", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def nudge(self) -> None:
        """The switch or the key changed: look at once."""
        self._wake.set()

    def _run(self) -> None:
        tidied = 0.0
        while not self._stop.is_set():
            pause = IDLE
            if self.enabled():
                try:
                    if self.clock() - tidied > 86_400:
                        self.tidy()
                        tidied = self.clock()
                    done, sent = self.round()
                    self.trouble = None
                    pause = POLL if self._out() else IDLE
                    if done or sent:
                        log.info(
                            "looks: %d works got their numbers, %d sent (%d kept)",
                            done,
                            sent,
                            len(self.index),
                        )
                except (AiUnavailable, NotDrawn) as err:
                    self.trouble = str(err)
                    log.info("looks: %s", err)
                    pause = REST
                except Exception:
                    log.exception("looks: a round failed")
                    pause = REST
            self._wake.wait(pause)
            self._wake.clear()
