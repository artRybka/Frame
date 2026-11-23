"""How works look, as numbers: Szukaj by words for how a work looks, by a
photograph of one, and the works that look like a work (Mateusz
2026-11-13, "G1": "wdrażamy G1").

SigLIP 2, on the server itself (:mod:`.seen`, Mateusz 2026-11-20:
"Przesiadamy."), turns every work's thumbnail into numbers once, in the
background, and words or a photograph the same way when they are asked
about: works that look alike, and the words for how they look, lie close.
The numbers are kept (:class:`LookIndex`) and every question is answered on
the server, in a few milliseconds. Google's embedding model gave them
before (from 2026-11-13); it was taken out on 2026-11-23 (Mateusz:
„Odciski SIGLip … wyłączyć poprzednie funkcje”), its numbers deleted
(:meth:`Looks.forget_google`).

The museums' works and the owner's own works are numbered (Mateusz
2026-11-17: "własne dzieła niech normalnie idą do wykonania odcisku.
Zawsze."), never his photos.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import shutil
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from PIL import Image

from .ai.client import AiUnavailable
from .library import palettes as palettes_
from .library.models import Item, ItemKind
from .library.verdict import Place, against
from .library.wording import Wording

if TYPE_CHECKING:
    from .library import Library
    from .library.images import ImageCache
    from .seen import Seen

log = logging.getLogger(__name__)

#: SigLIP's numbers of a picture (``seen.SIZE``).
SIZE = 768
#: Google's numbers of before, under ``data/looks`` (deleted at start).
GOOGLES = ("three", "vectors.i8", "ids.txt", "telling.json")
BATCHES = "batches.json"
#: Words remembered with their numbers: the same words cost nothing again.
REMEMBERED = 500
#: A search's answer: at most this many works.
MOST = 60
#: Szukaj's own list (Mateusz 2026-11-13): the works looked through for
#: words narrowed by the groups, and at most this many shown, nearest first.
AMONG_NEAR = 3000
#: However far the nearest are (his own works, photographed, are all under
#: the floor), this many are shown, and no more (Mateusz 2026-11-19:
#: "Minimum - ustawmy 8, żeby nie pokazywać dzieł niezwiązanych").
ALIKE_LEAST = 8
#: ... and at most this many, however many are near.
ALIKE_MOST = 1000
#: Szukaj's list scrolled to its end asks for the less near (``further``
#: of :meth:`Looks.alike`), at most this many steps (``seen.Floors.step``).
ALIKE_FURTHER = 3
AMONG_MOST = 240
#: Szukaj's "Słowa": how long a search waits for its words' numbers before
#: it answers with the words alone (mostly made while typing,
#: :meth:`Looks.prefetch`).
WORDS_WAIT = 1.5
#: How long a museum search waits for its works' numbers (made on the NAS
#: by SigLIP, their thumbnails fetched first: 10-19 s a page, Mateusz
#: 2026-11-22 "Wcześniej było niemal natychmiastowe"); those not numbered by
#: then go on in the background and are judged at the next search.
JUDGE_WAIT = 2.0
#: A photograph searched in Szukaj (``Looks.photo``) is a ``like`` of its
#: own: this before the key its numbers are kept under (``photos/<key>``).
PHOTO = "photo:"
#: A photograph's museum searches (:meth:`Looks.photo_searches`): the
#: subjects of its nearest works of the catalogue, this many of them looked
#: at, a subject had by at least ``PHOTO_SUBJECT``, ``PHOTO_SEARCHES`` at most.
PHOTO_NEAR = 24
PHOTO_SUBJECT = 4
PHOTO_SEARCHES = 3
#: "Podobne do" a photograph: the works no further than ``PHOTO_BELOW``
#: below its nearest (a step more for each step of the list scrolled on,
#: ``seen.Floors.step``), and never under ``PHOTO_LOWEST``, though
#: :data:`ALIKE_LEAST` however far. A photograph lies further from every
#: painting than paintings from each other (Mateusz 2026-11-22: „spodziewałem
#: się wielu autoportretów i portretów”; his selfie to 25 painted
#: self-portraits nearest 0.68, median 0.61). The museums' works shown with
#: it: as near (``judge_photo``).
PHOTO_BELOW = 0.08
PHOTO_LOWEST = 0.50
#: Rows of the numbers worked through at once (some 12 MB as floats).
CHUNK = 16_384
#: Rows no longer used (a work's picture changed, the work gone) as a share
#: of all, from which the file is written anew.
DEAD_SHARE = 0.2
#: What Szukaj's "Podobne do" asks: both, the subject, the form.
By = Literal["", "subject", "style"]


def _unit(x: np.ndarray) -> np.ndarray:
    """Each row at length 1; one of (next to) no length stays (next to)
    nothing, not a direction of rounding's noise."""
    length = np.linalg.norm(x, axis=-1, keepdims=True)
    return np.where(length > 1e-5, x / np.maximum(length, 1e-5), 0.0).astype(np.float32)


@dataclass(frozen=True)
class Found:
    """A work near what was asked, and how near (cosine, -1 to 1)."""

    item: Item
    score: float


class LookIndex:
    """The numbers of works, one row each, kept on disk in ``root``:
    ``vectors.i8`` (the rows, each number as a byte: its direction is what
    counts) and ``ids.txt`` (the row's work and the stamp of the picture it
    was made from). A work's later row wins; earlier ones are dead. A row
    may be ``parts`` sets of numbers side by side (the three of a work),
    each with a direction of its own."""

    def __init__(
        self, root: Path, size: int = SIZE, parts: int = 1, load: bool = True
    ) -> None:
        self.root = root
        self.size = size
        self.parts = parts
        self.part = size // parts
        self._lock = threading.Lock()
        self._rows = np.zeros((0, size), dtype=np.int8)
        self._norms = np.zeros((0, parts), dtype=np.float32)
        self._means: tuple[int, np.ndarray] | None = None
        #: Changes whenever the rows are read or written anew (their places move).
        self.generation = 0
        self._ids: list[str] = []
        self._row: dict[str, int] = {}
        self._stamps: dict[str, int] = {}
        if load:
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
        self._norms = self._lengths(self._rows)
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

    def _lengths(self, rows: np.ndarray) -> np.ndarray:
        """Each row's parts' lengths."""
        split = rows.astype(np.float32).reshape(len(rows), self.parts, self.part)
        return np.linalg.norm(split, axis=2).astype(np.float32)

    @staticmethod
    def quantised(vectors: np.ndarray, parts: int = 1) -> np.ndarray:
        """Each row (each of its ``parts``) as bytes in the same direction."""
        vectors = np.asarray(vectors, dtype=np.float32)
        split = vectors.reshape(len(vectors), parts, -1)
        peak = np.abs(split).max(axis=2, keepdims=True)
        peak[peak == 0] = 1.0
        return np.round(split / peak * 127).astype(np.int8).reshape(vectors.shape)

    def add(self, rows: Sequence[tuple[str, int, Sequence[float]]]) -> None:
        """Keeps ``(work, stamp, numbers)`` rows, after those kept."""
        if not rows:
            return
        vectors = np.array([r[2] for r in rows], dtype=np.float32)
        if vectors.shape[1] != self.size:
            raise ValueError(f"{vectors.shape[1]} numbers a row, {self.size} kept")
        packed = self.quantised(vectors, self.parts)
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with self._vectors.open("ab") as out:
                out.write(packed.tobytes())
            with self._names.open("a", encoding="utf-8") as out:
                out.writelines(f"{item_id}\t{stamp}\n" for item_id, stamp, _ in rows)
            start = len(self._ids)
            self._rows = np.concatenate([self._rows, packed])
            self._norms = np.concatenate([self._norms, self._lengths(packed)])
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
        self.generation += 1
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
        self._norms = self._norms[at] if len(at) else np.zeros((0, self.parts), dtype=np.float32)
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
        if length == 0:
            return []
        query = query / length

        def cosine(rows: np.ndarray, norms: np.ndarray) -> np.ndarray:
            with np.errstate(divide="ignore", invalid="ignore"):
                found = rows.astype(np.float32) @ query
                return np.where(norms[:, 0] > 0, found / norms[:, 0], -1.0)

        return self.ranked(cosine, count)

    def means(self) -> np.ndarray:
        """The mean direction of each part over the works (``parts`` rows),
        worked out again once their number has changed by a fiftieth."""
        with self._lock:
            rows, norms, count = self._rows, self._norms, len(self._ids)
        kept = self._means
        if kept is not None and abs(kept[0] - count) <= max(8, count // 50):
            return kept[1]
        total = np.zeros((self.parts, self.part), dtype=np.float64)
        for start in range(0, len(rows), CHUNK):
            part = rows[start : start + CHUNK].astype(np.float32)
            split = part.reshape(len(part), self.parts, self.part)
            total += (split / np.maximum(norms[start : start + len(part), :, None], 1e-9)).sum(0)
        mean = (total / max(count, 1)).astype(np.float32)
        self._means = (count, mean)
        return mean

    def ranked(
        self, score: Callable[[np.ndarray, np.ndarray], np.ndarray], count: int
    ) -> list[tuple[str, float]]:
        """The ``count`` works ``score`` puts highest, highest first, with
        their score; ``score`` is given rows (as they are kept, bytes) and
        their parts' lengths, a chunk at a time."""
        if count <= 0:
            return []
        with self._lock:
            rows, norms, ids, live = self._rows, self._norms, self._ids, self._row
        if not len(rows):
            return []
        scores = np.empty(len(rows), dtype=np.float32)
        for start in range(0, len(rows), CHUNK):
            part = rows[start : start + CHUNK]
            scores[start : start + len(part)] = score(part, norms[start : start + len(part)])
        return self.top(scores, ids, live, count)

    @staticmethod
    def top(
        scores: np.ndarray, ids: Sequence[str], live: dict[str, int], count: int
    ) -> list[tuple[str, float]]:
        """The ``count`` live rows of the highest ``scores`` (a row's work
        and its score), highest first."""
        if count <= 0 or not len(scores):
            return []
        scores = np.nan_to_num(scores, nan=-2.0)
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
    """The questions asked of the works' numbers (SigLIP's, :mod:`.seen`):
    words, a photograph, a work."""

    def __init__(
        self,
        library: Library,
        images: ImageCache,
        seen: Seen,
        root: Path,
    ) -> None:
        self.library = library
        self.images = images
        self.seen = seen
        self.root = root
        self._words: OrderedDict[str, list[float]] = OrderedDict()
        self._words_lock = threading.Lock()
        #: Words' numbers being made (:meth:`prefetch`), by key.
        self._asking: dict[str, Future[list[float]]] = {}
        self._askers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="looks-words")
        self._numberers = ThreadPoolExecutor(max_workers=1, thread_name_prefix="looks-judge")
        self._numbering: set[str] = set()
        #: The English of Szukaj's words, as known (the phone's translation,
        #: Haiku's): SigLIP reads English best.
        self.english: Callable[[str], str] = lambda text: text
        #: The catalogue's palettes, for "Barwy" (:mod:`.library.palettes`).
        self.palettes = palettes_.Palettes(library.all_items, library.stamp)

    def forget_google(self) -> int:
        """Google's numbers of before taken off the disk (Mateusz
        2026-11-23: „Zgadzam się z Twoimi rekomendacjami”, their files
        deleted): the whole thumbnail's, the three, the sentences, the
        batches, and those of the photographs searched. How many files."""
        gone = 0
        for name in (*GOOGLES, BATCHES):
            path = self.root / name
            if path.is_dir():
                gone += sum(1 for p in path.rglob("*") if p.is_file())
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink(missing_ok=True)
                gone += 1
        photos = self.root / "photos"
        if photos.is_dir():
            for path in photos.glob("*.f32"):
                if not path.name.endswith((".seen.f32", ".palette.f32")):
                    path.unlink(missing_ok=True)
                    gone += 1
        if gone:
            log.info("looks: Google's numbers of before deleted (%d files)", gone)
        return gone

    # -- what may be asked -----------------------------------------------------------

    def enabled(self) -> bool:
        """Whether SigLIP's numbers answer (:meth:`Seen.answers`): once most
        works have them. No key, no switch (Google's numbers until
        2026-11-23)."""
        return self.seen.answers()

    def local(self) -> bool:
        """The same, as the app asks it (``LooksSeen.answers``)."""
        return self.enabled()

    def ready(self) -> bool:
        """Whether a question can be answered: some works have numbers."""
        return self.enabled() and len(self.seen.index) > 0

    @staticmethod
    def wanted(item: Item) -> bool:
        """A museum's work with a picture, or a work of the owner's own
        ("Dodaj własne dzieło": found by its look and among the similar,
        Mateusz 2026-11-15); never a photograph of his."""
        if item.kind == ItemKind.OWN:
            return item.source == "upload"
        return item.kind == ItemKind.ARTWORK and bool(item.thumb_url)

    def counts(self) -> tuple[int, int]:
        """Works with their numbers, and works that would have them."""
        return self.seen.counts()

    # -- questions -------------------------------------------------------------------

    def words(self, text: str, limit: int = MOST) -> list[Found]:
        """Works that look like ``text`` says ("mglisty poranek nad wodą"),
        nearest first. Raises :class:`AiUnavailable` when it cannot ask."""
        text = " ".join(text.split())[:300]
        if not text:
            return []
        vector = self._words_vector(text)
        return self._answer(self._words_near(vector, limit * 3), limit, seen_floors().words)

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
        near = self._words_near(vector, max(AMONG_NEAR, limit * 3))
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
                bar = max(seen_floors().words, score - seen_floors().near_best)
            if score < bar:
                break
            seen.add(item.id)
            found.append(Found(item, round(score, 4)))
        return found

    def prefetch(self, texts: Iterable[str]) -> None:
        """the numbers of words asked ahead, while Szukaj's
        suggestions show them (Mateusz 2026-11-19: "wyniki chciałbym od
        razu"): the search that follows finds them here. Some 0.0002 cent
        a time; nothing when they cannot be asked."""
        if not self.ready():
            return
        for text in texts:
            self._ask(text)

    def _ask(self, text: str) -> Future[list[float]] | None:
        """The numbers of ``text``: kept, being asked, or asked now in the
        background; None for no words."""
        text = " ".join(text.split())[:300]
        if not text:
            return None
        key = text.lower()
        with self._words_lock:
            kept = self._words.get(key)
            if kept is not None:
                done: Future[list[float]] = Future()
                done.set_result(kept)
                return done
            asking = self._asking.get(key)
            if asking is not None:
                return asking
            asking = self._askers.submit(self._words_vector, text)
            self._asking[key] = asking

        def gone(_: Future[list[float]]) -> None:
            with self._words_lock:
                if self._asking.get(key) is asking:
                    del self._asking[key]

        asking.add_done_callback(gone)
        return asking

    def asking(self, text: str) -> bool:
        """Whether the numbers of ``text`` are on their way (asked,
        not here yet): a search answered without them can be asked again
        in a moment."""
        key = " ".join(text.split())[:300].lower()
        with self._words_lock:
            return key in self._asking

    def scored(self, text: str, wait: float | None = None) -> list[tuple[str, float]] | None:
        """The works nearest what the words say (:data:`AMONG_NEAR` of
        them), each with how near, nearest first: Szukaj's "Słowa"
        (``PlaylistRules.seen``). None when they cannot be asked, or when
        the numbers of the words are not here within ``wait`` (they
        are kept once they come)."""
        try:
            self._check()
        except AiUnavailable:
            return None
        asking = self._ask(text)
        if asking is None:
            return []
        wait = WORDS_WAIT if wait is None else wait
        try:
            vector = asking.result(timeout=wait)
        except FutureTimeout:
            log.info("Słowa: the numbers of %r not here within %.1f s", text, wait)
            return None
        except AiUnavailable:
            return None
        return self._words_near(vector, AMONG_NEAR)

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
        return [item_id for item_id, _ in self._words_near(vector, AMONG_NEAR)]

    def judge(self, text: str, items: Sequence[Item]) -> list[Item]:
        """Museum works a search for a look brought (``ai.look_words``):
        those that look as ``text`` says, as near as the catalogue's own
        answer asks (:data:`NEAR_BEST` below its best, over :data:`FLOOR`),
        nearest first (Mateusz 2026-11-13, card: "Hasła i ocena wyglądem").
        Their thumbnails get their numbers now, Google asked at once (some
        0.03 cent a work), and keep them: the catalogue's background asks
        nothing again for them, and the next search finds them at home.
        None when it cannot be asked now."""
        try:
            vector = np.asarray(self._words_vector(" ".join(text.split())[:300]))
        except AiUnavailable as err:
            log.info("judging museum works by look: %s", err)
            return []
        if not items:
            return []
        asked = self.seen.index
        self._number_within([i for i in items if i.id not in asked])
        best = self._words_near(vector, 1)
        floor = seen_floors().words
        bar = max(floor, (best[0][1] if best else floor) - seen_floors().near_best)
        scored: list[tuple[float, Item]] = []
        for item in items:
            row = asked.vector(item.id)
            if row is None:
                continue
            score = self._words_score(row[None, :], vector)[0]
            if score >= bar:
                scored.append((float(score), item))
        scored.sort(key=lambda s: -s[0])
        return [item for _, item in scored]

    def _number_within(self, items: Sequence[Item], wait: float | None = None) -> None:
        """:meth:`_number` for museum works, waited for :data:`JUDGE_WAIT`
        at most: the rest go on behind (once, however many searches ask)."""
        with self._words_lock:
            fresh = [i for i in items if i.id not in self._numbering]
            self._numbering.update(i.id for i in fresh)
        if not fresh:
            return

        def number() -> None:
            try:
                self._number(fresh)
            except AiUnavailable as err:
                log.info("numbers for museum works: %s", err)
            except Exception:
                log.exception("numbers for museum works")
            finally:
                with self._words_lock:
                    self._numbering.difference_update(i.id for i in fresh)

        going = self._numberers.submit(number)
        try:
            going.result(timeout=JUDGE_WAIT if wait is None else wait)
        except FutureTimeout:
            log.info("museum works: %d still being numbered, judged at the next search", len(fresh))

    def _number(self, items: Sequence[Item]) -> None:
        """Numbers for museum works' thumbnails (downloaded and kept, as the
        app shows them), made at once by SigLIP; a work whose thumbnail
        cannot be had is left without."""
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
        if not got:
            return
        self.seen.add([(item.id, stamp, img) for item, img, stamp in got])

    def looking(self, text: str, allowed: list[Item]) -> list[Item] | None:
        """:meth:`among` for the library (``Library.looking``): the works
        alone, None when it cannot be asked now."""
        try:
            return [f.item for f in self.among(text, allowed)]
        except AiUnavailable:
            return None

    def picture(self, img: Image.Image, limit: int = MOST) -> list[Found]:
        """Works that look like ``img`` (a photograph of a work, a postcard)."""
        self._check()
        small = img.convert("RGB")
        small.thumbnail((640, 640))
        vector = self.seen.model.pictures([small])[0]
        near = self.seen.alike_near(vector, limit * 3 + 8)
        return self._answer(near, limit, seen_floors().picture, relative=False)

    def photo(self, data: bytes, img: Image.Image) -> str:
        """Szukaj's "Szukaj zdjęciem" (Mateusz 2026-11-15: "mogłoby się
        pokazywać zwykłe szukanie i dawać możliwość zawężania wyników,
        tworzenia playlisty"): the photograph's numbers kept under a key
        (``photo:…``) that Szukaj then asks as ``PlaylistRules.like``, the
        groups narrowing it and a smart playlist keeping it. The photograph
        itself is not kept."""
        key = PHOTO + hashlib.sha256(data).hexdigest()[:20]
        if self.photo_vector(key) is not None:
            return key
        self._check()
        self._keep_photo(self._photo_path(key, "palette"), palettes_.of_picture(img))
        small = img.convert("RGB")
        small.thumbnail((640, 640))
        vector = self.seen.model.pictures([small])[0]
        self._keep_photo(self._photo_path(key, "seen"), vector)
        return key

    def photo_numbers(self, vector: np.ndarray, palette: np.ndarray | None = None) -> str:
        """:meth:`photo` for a photograph the phone numbered itself with
        SigLIP's picture side (``seen.PHONE``): the numbers kept under the
        key the photograph would have had, at length 1. Only while SigLIP
        answers (:class:`AiUnavailable` otherwise: the app sends the
        photograph then). ``palette``: its colours as the phone found them
        (``palettes.colours_of``'s rows), for "Barwy"."""
        if not self.enabled():
            raise AiUnavailable("SigLIP does not answer yet")
        vector = np.asarray(vector, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if len(vector) != self.seen.index.size or not np.isfinite(norm) or norm < 1e-6:
            raise ValueError("not a photograph's numbers")
        vector = vector / norm
        key = PHOTO + hashlib.sha256(vector.astype("<f4").tobytes()).hexdigest()[:20]
        if palette is not None:
            rows = np.asarray(palette, dtype=np.float32).reshape(-1)
            if (
                len(rows) % 4
                or not 0 < len(rows) <= 4 * 2 * palettes_.K
                or not np.isfinite(rows).all()
            ):
                raise ValueError("not a palette")
            rows = palettes_.palette(rows.reshape(-1, 4)[:, :3], rows.reshape(-1, 4)[:, 3])
            self._keep_photo(self._photo_path(key, "palette"), rows)
        if self.photo_vector(key) is None:
            self._keep_photo(self._photo_path(key, "seen"), vector)
        return key

    def photo_palette(self, key: str) -> np.ndarray | None:
        """A photograph's palette (rows L, a, b, weight), or None when it
        came without one (an older app)."""
        if not key.startswith(PHOTO):
            return None
        try:
            rows = np.fromfile(self._photo_path(key, "palette"), dtype=np.float32)
        except (OSError, ValueError):
            return None
        return rows.reshape(-1, 4) if len(rows) and len(rows) % 4 == 0 else None

    def _palette_of(self, item_id: str) -> tuple[np.ndarray, bool] | None:
        """The palette asked about, and whether to compare it with
        paintings: a photograph's (with paintings), a work's or its copy's."""
        if item_id.startswith(PHOTO):
            rows = self.photo_palette(item_id)
            return None if rows is None else (rows, True)
        for copy in self._copies(item_id):
            if (found := self.palettes.of(copy)) is not None:
                return found
        return None

    def _copies(self, item_id: str) -> list[str]:
        works = self.library.works()
        own = works.group_index(item_id)
        return [item_id] + (
            [c.id for c in works.groups[own] if c.id != item_id] if own is not None else []
        )

    def _photo_floor(self, near: list[tuple[str, float]], further: int = 0) -> float:
        """How near a work must be to a photograph (``near``: the nearest
        first) to be shown like it: :data:`PHOTO_BELOW` under the nearest,
        a step less for each step on, never under :data:`PHOTO_LOWEST`."""
        if not near:
            return PHOTO_LOWEST
        steps = min(max(further, 0), ALIKE_FURTHER)
        step = seen_floors().step
        return max(PHOTO_LOWEST, near[0][1] - PHOTO_BELOW - step * steps)

    def alike_colours(self, item_id: str, further: int = 0) -> list[str]:
        """ "Barwy" alone (Mateusz 2026-11-21): the works whose palettes lie
        nearest the work's (or photograph's), of its kind, nearest first,
        as near as :func:`palettes.floor` says. Needs no numbers."""
        asked = self._palette_of(item_id)
        if asked is None:
            return []
        rows, painted = asked
        skip = set(self._copies(item_id)) if not item_id.startswith(PHOTO) else set()
        near = [
            (i, d)
            for i, d in self.palettes.near(rows, painted, palettes_.MOST + len(skip))
            if i not in skip
        ]
        return palettes_.enough(near, palettes_.floor(False, further))

    def _coloured(self, item_id: str, ids: list[str], further: int) -> list[str]:
        """ "Barwy" beside "Treść" or "Forma": of the works found alike
        (``ids``), those whose palettes lie near the one asked, nearest first."""
        asked = self._palette_of(item_id)
        if asked is None:
            return ids
        ranked = self.palettes.ranked(asked[0], ids)
        return palettes_.enough(ranked, palettes_.floor(True, further))

    def photo_searches(self, key: str) -> list[Wording]:
        """The museums' searches for a photograph searched (Mateusz
        2026-11-21: "Tak, zróbmy proszę w ten sposób", no Claude asked): the
        subjects most of the catalogue's :data:`PHOTO_NEAR` nearest works
        have, at least :data:`PHOTO_SUBJECT` of them, :data:`PHOTO_SEARCHES`
        at most, each by its museum word with its Polish name."""
        from .library.vocabulary import term

        vector = self.photo_vector(key)
        if vector is None or not self.enabled():
            return []
        near = self.seen.alike_near(vector, PHOTO_NEAR * 3)
        counted: dict[str, int] = {}
        works = 0
        for item_id, score in near:
            if score < seen_floors().picture or works >= PHOTO_NEAR:
                break
            item = self.library.get(item_id)
            if item is None:
                continue
            works += 1
            for found in dict.fromkeys(t for t in item.terms if t.startswith("subject:")):
                counted[found] = counted.get(found, 0) + 1
        out: list[Wording] = []
        for found, count in sorted(counted.items(), key=lambda c: -c[1]):
            named = term(found)
            if count < PHOTO_SUBJECT or named is None or not named.query:
                continue
            out.append(Wording(named.query, en=named.query, pl=named.name.lower()))
            if len(out) >= PHOTO_SEARCHES:
                break
        return out

    def judge_photo(self, key: str, items: Sequence[Item]) -> list[Item]:
        """:meth:`judge` for a photograph searched: the museum works that
        look like it, as near as the catalogue's shown for it
        (:meth:`_photo_floor`, or :attr:`Floors.picture`), nearest first;
        their thumbnails numbered here now and kept."""
        vector = self.photo_vector(key)
        if vector is None or not items or not self.enabled():
            return []
        asked = self.seen.index
        self._number_within([i for i in items if i.id not in asked])
        query = vector / max(float(np.linalg.norm(vector)), 1e-9)
        # As near as the catalogue's works shown for it.
        floor = min(seen_floors().picture, self._photo_floor(self.seen.alike_near(vector, 1)))
        scored: list[tuple[float, Item]] = []
        for item in items:
            row = asked.vector(item.id)
            if row is None:
                continue
            score = float(row @ query) / max(float(np.linalg.norm(row)), 1e-9)
            if score >= floor:
                scored.append((score, item))
        scored.sort(key=lambda s: -s[0])
        return [item for _, item in scored]

    @staticmethod
    def _keep_photo(path: Path, vector: np.ndarray) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(".new")
        np.asarray(vector, dtype=np.float32).tofile(part)
        os.replace(part, path)

    def photo_vector(self, key: str) -> np.ndarray | None:
        """The numbers of a photograph searched (:meth:`photo`) that the
        questions now ask, or None."""
        if not key.startswith(PHOTO):
            return None
        try:
            vector = np.fromfile(self._photo_path(key, "seen"), dtype=np.float32)
        except (OSError, ValueError):
            return None
        return vector if len(vector) == self.seen.index.size else None

    def _photo_path(self, key: str, kind: str = "") -> Path:
        """Where a photograph's numbers are kept: SigLIP's ("seen"), its
        palette ("palette")."""
        name = "".join(c for c in key.removeprefix(PHOTO) if c in "0123456789abcdef")
        return self.root / "photos" / f"{name or '0'}{'.' + kind if kind else ''}.f32"

    def similar(
        self,
        item: Item,
        limit: int = 24,
        place: Place = Place.FOUND,
        by: By = "",
        near_enough: bool = False,
        further: int = 0,
    ) -> list[Found]:
        """Works that look like ``item`` (``by``: both its subject and its
        style, or one of them): none until it or another copy of its work
        has numbers (the card shows the work's best copy, the index may
        have another: no "Podobne wyglądem" under van Gogh's Sunflowers
        found by a look, 2026-11-13). Its own copies and the work itself
        are left out; ``place``: where they are shown. ``near_enough``:
        only those Szukaj's "Podobne do" shows (:meth:`enough`, ``further``
        steps less near)."""
        works = self.library.works()
        own = works.group_index(item.id)
        copies = [item.id] + (
            [c.id for c in works.groups[own] if c.id != item.id] if own is not None else []
        )
        asked = self.seen.index
        vector = next((v for c in copies if (v := asked.vector(c)) is not None), None)
        if vector is None:
            return []
        near = self._alike_near(vector, limit * 3 + 8, by)
        near = [
            (i, s) for i, s in near if i != item.id and (own is None or works.group_index(i) != own)
        ]
        if near_enough:
            near = self._near_enough(near, by, further)
        found = self._answer(near, limit, self._alike_base(), relative=False, place=place)
        return self.enough(found, by, further) if near_enough else found

    def enough(self, found: list[Found], by: str = "", further: int = 0) -> list[Found]:
        """Of ``found`` (nearest first), those Szukaj's "Podobne do" shows:
        at least :data:`ALIKE_FLOOR` near (``further`` steps less near,
        :data:`ALIKE_STEP` each), though :data:`ALIKE_LEAST` of them
        however far."""
        floor = self._floor(by, further)
        near = sum(1 for f in found if f.score >= floor)
        return found[: max(near, ALIKE_LEAST)]

    def _floor(self, by: str, further: int = 0) -> float:
        """How near a work must be for "Podobne do", ``further`` steps on."""
        steps = min(max(further, 0), ALIKE_FURTHER)
        floors = seen_floors()
        return floors.alike.get(by, floors.alike[""]) - floors.step * steps

    def _alike_base(self) -> float:
        """How near a work must be to be shown as like another at all."""
        return seen_floors().base

    def _near_enough(
        self, near: list[tuple[str, float]], by: str, further: int = 0
    ) -> list[tuple[str, float]]:
        """``near`` (nearest first) without the far ones :meth:`enough`
        never keeps, so that they are not looked up: past the floor, only
        enough for :data:`ALIKE_LEAST` works should some nearer be hidden
        or copies of one."""
        floor = self._floor(by, further)
        under = next((k for k, (_, score) in enumerate(near) if score < floor), len(near))
        return near[: max(under, ALIKE_LEAST * 3 + 8)]

    def alike(
        self, item_id: str, by: str = "", further: int = 0, colours: bool = False
    ) -> list[str] | None:
        """The ids of the works that look like the work ``item_id`` (or the
        photograph kept as ``photo:…``, :meth:`photo`), by ``by`` (both
        their subject and their style, "subject" or "style"), nearest
        first, as near as :meth:`enough` says (``further`` steps less
        near: the list scrolled to its end), for Szukaj
        (``Library.like_near``, ``PlaylistRules.like``); None while SigLIP
        does not answer. ``colours`` ("Barwy" beside
        them): of those, a step less near, the ones of near colours; ``by``
        "colours": "Barwy" alone (:meth:`alike_colours`)."""
        if by == "colours":
            return self.alike_colours(item_id, further)
        if not self.enabled():
            return None
        shape: By = by if by in ("subject", "style") else ""  # type: ignore[assignment]
        most = ALIKE_MOST
        wide = further + 1 if colours else further
        if item_id.startswith(PHOTO):
            vector = self.photo_vector(item_id)
            if vector is None:
                return []
            near = self._alike_near(vector, most * 3 + 8, shape)
            floor = self._photo_floor(near, wide)
            found = self._answer(near, most, None, relative=False)
            kept = sum(1 for f in found if f.score >= floor)
            ids = [f.item.id for f in found[: max(kept, ALIKE_LEAST)]]
        else:
            item = self.library.get(item_id)
            if item is None:
                return []
            found = self.similar(item, most, by=shape, near_enough=True, further=wide)
            ids = [f.item.id for f in found]
        return self._coloured(item_id, ids, further) if colours else ids

    def near_ids(self, item_id: str, limit: int = 40) -> list[str]:
        """The ids of the works whose numbers lie nearest ``item_id``'s
        (subject and style), whatever they are and wherever they are
        hidden: the gatekeeper's look-alikes of a cover. None without
        numbers."""
        vector = self.seen.index.vector(item_id)
        if vector is None:
            return []
        near = self.seen.index.nearest(vector, limit + 1)
        raw = seen_floors().raw
        return [i for i, score in near if i != item_id and score >= raw][:limit]

    def neighbours(self, item_id: str, limit: int = 12) -> list[str]:
        """The ids of works that look most like ``item_id`` (the study's
        candidates of works like it, proposed by the server); none without
        its numbers or with Szukanie wyglądem off."""
        item = self.library.get(item_id)
        if item is None or not self.enabled():
            return []
        return [f.item.id for f in self.similar(item, limit, Place.PROPOSED)]

    def _check(self) -> None:
        if not self.enabled():
            raise AiUnavailable("SigLIP does not answer yet")

    def _words_vector(self, text: str) -> list[float]:
        key = text.lower()
        with self._words_lock:
            if key in self._words:
                self._words.move_to_end(key)
                return self._words[key]
        self._check()
        # In English, as the museums abroad are asked ("koń": an ex libris
        # first in Polish, Mateusz 2026-11-20).
        english = self.english(text) or text
        vector = [float(x) for x in self.seen.model.words([english])[0]]
        with self._words_lock:
            self._words[key] = vector
            while len(self._words) > REMEMBERED:
                self._words.popitem(last=False)
        return vector

    @staticmethod
    def _words_score(rows: np.ndarray, vector: Sequence[float] | np.ndarray) -> np.ndarray:
        """How near words' numbers lie to works' rows."""
        rows = np.asarray(rows, dtype=np.float32)
        return _unit(rows) @ _unit(np.asarray(vector, dtype=np.float32))

    def _words_near(
        self, vector: Sequence[float] | np.ndarray, count: int
    ) -> list[tuple[str, float]]:
        return self.seen.index.nearest(vector, count)

    def _alike_near(self, vector: np.ndarray, count: int, by: By = "") -> list[tuple[str, float]]:
        """The works nearest a work's (or a photograph's) numbers, by ``by``."""
        return self.seen.alike_near(vector, count, by)

    def _answer(
        self,
        near: list[tuple[str, float]],
        limit: int,
        floor: float | None,
        relative: bool = True,
        place: Place = Place.FOUND,
    ) -> list[Found]:
        """The works of ``near`` worth showing: in the library, not hidden,
        shown where Szukaj shows works, one copy of each work (its best),
        not far below the best (``relative``) nor under ``floor`` (None:
        the nearest, however near)."""
        if not near:
            return []
        best = near[0][1]
        low = -2.0 if floor is None else floor
        bar = max(low, best - seen_floors().near_best) if relative else low
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

    def stop(self) -> None:
        self._askers.shutdown(wait=False, cancel_futures=True)
        self._numberers.shutdown(wait=False, cancel_futures=True)


def seen_floors() -> Any:
    """SigLIP's floors (:data:`frame_server.seen.FLOORS`), read late: the
    module needs this one."""
    from .seen import FLOORS

    return FLOORS
