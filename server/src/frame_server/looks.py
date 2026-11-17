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

Its subject and its style apart (Mateusz 2026-11-17: "chciałbym mieć styl
i tematykę osobno"; "Ok, wdrażajmy"): a work now has three sets of
numbers (:data:`PART` each, :attr:`Looks.three`), of its thumbnail asked
for its style alone (:data:`STYLE_ASK`), of its thumbnail asked for what
it depicts (:data:`SUBJECT_ASK`), and of a sentence on what it depicts
that Gemini Flash-Lite writes from the thumbnail (:data:`DESCRIBE`). Its
style is the first with the third's direction taken out, its subject the
second and the third together, both their mean (:func:`shapes`; trial on
1104 works: of the ten nearest by style 38% by the same artist and 71% in
the same technique, by subject an Annunciation finds 81% Annunciations, a
Crucifixion 94% Crucifixions; the one look of before 33%, 58%, 67%, 79%).
Szukaj's "Podobne do" asks one of the three (``PlaylistRules.like_by``),
the card both. The numbers of before (the whole thumbnail,
:attr:`Looks.index`) answer until :data:`READY_SHARE` of the works have
their three, and are then dropped.

The museums' works and the owner's own works are sent (Mateusz
2026-11-17: "własne dzieła niech normalnie idą do wykonania odcisku.
Zawsze."), never his photos. A work gets its numbers in the background
(:meth:`Looks.start`), through Google's Batch at half the price (Mateusz
2026-11-13: "Rozumiem że ta praca G1 pójdzie przez batch?"): first its
sentence (:data:`PER_TOLD` works a batch), then its numbers
(:data:`PER_BATCH` works a batch), some 0.02 cent a work in all; those
cared about first and :data:`OPEN` batches at a time, while the Gemini
page's switch is on and the image model's month's limit allows; a work
whose picture changed (a sharper copy, the creative restorer) gets them
anew. Only words and photographs asked about are sent at once.
"""

from __future__ import annotations

import hashlib
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
from typing import TYPE_CHECKING, Any, Literal

import httpx
import numpy as np
from PIL import Image

from .ai.client import AiUnavailable
from .ai.gemini import EMBED_MAX, EMBED_SIZE, Embedded, NotDrawn, TooHeavy
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
#: (300 thumbnails weighed 30 MB, over Google's 19; 150 at a time, some
#: 15 MB, still timed out on the NAS's upload once: 100.)
PER_BATCH = 40
OPEN = 24
#: Works whose sentence (:data:`DESCRIBE`) is asked in one batch.
PER_TOLD = 100
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
#: Works Szukaj's "Podobne do" shows at most: the card counts to 60 ("60+").
ALIKE_MOST = 120
AMONG_MOST = 240
#: A photograph searched in Szukaj (``Looks.photo``) is a ``like`` of its
#: own: this before the key its numbers are kept under (``photos/<key>``).
PHOTO = "photo:"
#: A work whose thumbnail is not here is looked at again after this long.
NO_THUMB_AGAIN = 86_400.0
#: Rows of the numbers worked through at once (some 12 MB as floats).
CHUNK = 16_384
#: Rows no longer used (a work's picture changed, the work gone) as a share
#: of all, from which the file is written anew.
DEAD_SHARE = 0.2

#: Numbers kept of each of a work's three: the first of Google's
#: :data:`EMBED_SIZE` (they come ordered, the first 512 lose next to
#: nothing: trial of 2026-11-17).
PART = 512
#: What the thumbnail is asked with for its style, and for its subject.
STYLE_ASK = (
    "Represent only the artistic style of this artwork: medium and technique, "
    "brushwork or line, surface and texture, treatment of light, palette, degree "
    "of finish, stylistic tradition. Ignore what is depicted."
)
SUBJECT_ASK = (
    "Represent only what this artwork depicts: figures, objects, place, scene, "
    "story or theme. Ignore medium, technique, style and colours."
)
#: What Gemini Flash-Lite is asked of a thumbnail: what it depicts, no word
#: of how; its answer, before :data:`TOLD`, becomes the third numbers.
DESCRIBE = (
    "In 25-45 words, in English, say only WHAT this artwork depicts: figures and "
    "their actions, objects, place, scene, story or religious/mythological theme, "
    "genre. Do not mention medium, technique, style, colours, brushwork, period or "
    "artist. Plain text, no preamble."
)
TOLD = "task: clustering | query: "
#: The thumbnail's longer side for the sentence (Google reads it at its low
#: resolution anyway).
TOLD_SIDE = 384
#: What Szukaj's "Podobne do" asks of the three: both, the subject, the style.
By = Literal["", "subject", "style"]
#: Works with their three as a share of those that would have them, from
#: which questions are answered by the three and the numbers of before are
#: dropped (until then those answer, with "Temat" and "Styl" as both).
READY_SHARE = 0.95
#: A work's three are centred on the works' mean: one under this is less
#: like the work asked about than an average work, and is not shown.
THREE_FLOOR = 0.0
#: The same as :data:`PICTURE_FLOOR` for the mean of a work's raw style
#: and subject (both at the 27th hundredth of all pairs in the trial).
RAW_FLOOR = 0.75
#: The file saying that the three answer (``three/ready``).
READY = "ready"
#: Words each work's sentence is kept with (``three/told.jsonl``: also for
#: later uses of what Gemini saw), and the three's batches out.
TOLD_FILE = "told.jsonl"
TELLING = "telling.json"


def _unit(x: np.ndarray) -> np.ndarray:
    """Each row at length 1; one of (next to) no length stays (next to)
    nothing, not a direction of rounding's noise."""
    length = np.linalg.norm(x, axis=-1, keepdims=True)
    return np.where(length > 1e-5, x / np.maximum(length, 1e-5), 0.0).astype(np.float32)


def shapes(rows: np.ndarray, means: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The style and the subject of works' three (rows of ``3 * PART``
    numbers, at any scale), each a unit row: each of the three centred on
    the works' mean (``means``, :meth:`LookIndex.means`; what all works
    share says nothing of one), the style the first with the third's
    direction taken out, the subject the second and the third together."""
    g, h, c = (_unit(_unit(rows[:, k * PART : (k + 1) * PART]) - means[k]) for k in range(3))
    style = _unit(g - (g * c).sum(axis=1, keepdims=True) * c)
    subject = _unit(c + h)
    return style, subject


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

    def __init__(self, root: Path, size: int = EMBED_SIZE, parts: int = 1) -> None:
        self.root = root
        self.size = size
        self.parts = parts
        self.part = size // parts
        self._lock = threading.Lock()
        self._rows = np.zeros((0, size), dtype=np.int8)
        self._norms = np.zeros((0, parts), dtype=np.float32)
        self._means: tuple[int, np.ndarray] | None = None
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
                return np.where(norms[:, 0] > 0, (rows @ query) / norms[:, 0], -1.0)

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
        their score; ``score`` is given rows (as floats) and their parts'
        lengths, a chunk at a time."""
        if count <= 0:
            return []
        with self._lock:
            rows, norms, ids, live = self._rows, self._norms, self._ids, self._row
        if not len(rows):
            return []
        scores = np.empty(len(rows), dtype=np.float32)
        for start in range(0, len(rows), CHUNK):
            part = rows[start : start + CHUNK].astype(np.float32)
            scores[start : start + len(part)] = score(part, norms[start : start + len(part)])
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
        #: The numbers of before: the whole thumbnail, one set a work.
        self.index = LookIndex(root)
        #: A work's three: its style, its subject, its sentence (:data:`PART` each).
        self.three = LookIndex(root / "three", size=3 * PART, parts=3)
        self.root = root
        self.clock = clock
        #: Whether questions are still answered by the numbers of before.
        self._old = len(self.index) > 0 and not (self.three.root / READY).exists()
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
        #: The sentences of works waiting for their three (stamp, words).
        self._told: dict[str, tuple[int, str]] = {}
        self._told_lock = threading.Lock()
        self._load_told()

    # -- what may be asked -----------------------------------------------------------

    def enabled(self) -> bool:
        """Google's key, and the Gemini page's switch on."""
        return self.painter.enabled() and self.config.config.looks

    def old(self) -> bool:
        """Whether questions are answered by the numbers of before (until
        :data:`READY_SHARE` of the works have their three)."""
        return self._old

    def _asked(self) -> LookIndex:
        return self.index if self._old else self.three

    def ready(self) -> bool:
        """Whether a question can be answered: some works have numbers."""
        return self.enabled() and len(self._asked()) > 0

    @staticmethod
    def wanted(item: Item) -> bool:
        """A museum's work with a picture, or a work of the owner's own
        ("Dodaj własne dzieło": found by its look and among the similar,
        Mateusz 2026-11-15); never a photograph of his."""
        if item.kind == ItemKind.OWN:
            return item.source == "upload"
        return item.kind == ItemKind.ARTWORK and bool(item.thumb_url)

    def counts(self) -> tuple[int, int]:
        """Works with their three, and works that would have them (worked
        out at most once a minute)."""
        kept = self._counts
        if kept is not None and self.clock() - kept[0] < 60:
            return kept[1], kept[2]
        items = self.library.all_items()
        wanted = {i.id for i in items if self.wanted(i)}
        done = len(wanted & self.three.ids())
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
        return self._answer(self._words_near(vector, limit * 3), limit, FLOOR)

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
        except (AiUnavailable, NotDrawn, httpx.HTTPError) as err:
            log.info("judging museum works by look: %s", err)
            return []
        if not items:
            return []
        asked = self._asked()
        try:
            self._number([i for i in items if i.id not in asked])
        except (AiUnavailable, NotDrawn, httpx.HTTPError) as err:
            log.info("numbers for museum works: %s", err)
        best = self._words_near(vector, 1)
        bar = max(FLOOR, (best[0][1] if best else FLOOR) - NEAR_BEST)
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

    def _number(self, items: Sequence[Item]) -> None:
        """Numbers for museum works' thumbnails (downloaded and kept, as the
        app shows them), asked of Google at once, :data:`EMBED_MAX` at a
        time (their three: their sentences first); a work whose thumbnail
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
        if self._old:
            for start in range(0, len(got), EMBED_MAX):
                part = got[start : start + EMBED_MAX]
                vectors = self.painter.embed(KIND, [img for _, img, _ in part])
                self.index.add(
                    [(item.id, stamp, v) for (item, _, stamp), v in zip(part, vectors, strict=True)]
                )
            return
        with ThreadPoolExecutor(min(len(got), 8)) as pool:
            told = list(pool.map(lambda p: self._tell(p[1]), got))
        for (item, _, stamp), words in zip(got, told, strict=True):
            self._keep_told(item.id, stamp, words)
        each = EMBED_MAX // 3
        for start in range(0, len(got), each):
            part = got[start : start + each]
            asked: list[Embedded] = []
            for (_, img, _), words in zip(part, told[start : start + each], strict=True):
                asked += self._asks(img, words)
            vectors = self.painter.embed(KIND, asked)
            rows, at = [], 0
            for (item, _, stamp), words in zip(part, told[start : start + each], strict=True):
                g, h = vectors[at], vectors[at + 1]
                c = vectors[at + 2] if words else h
                at += 3 if words else 2
                rows.append((item.id, stamp, self._joined(g, h, c)))
            self.three.add(rows)
            with self._told_lock:
                for item_id, stamp, _ in rows:
                    if self._told.get(item_id, (None,))[0] == stamp:
                        del self._told[item_id]

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
        if self._old:
            vector = np.asarray(self.painter.embed(KIND, [small])[0], dtype=np.float32)
            return self._answer(self.index.nearest(vector, limit * 3), limit, PICTURE_FLOOR)
        vector = self._three_of(small)
        near = self._alike_near(vector, limit * 3 + 8)
        return self._answer(near, limit, THREE_FLOOR, relative=False)

    def photo(self, data: bytes, img: Image.Image) -> str:
        """Szukaj's "Szukaj zdjęciem" (Mateusz 2026-11-15: "mogłoby się
        pokazywać zwykłe szukanie i dawać możliwość zawężania wyników,
        tworzenia playlisty"): the photograph's numbers kept under a key
        (``photo:…``) that Szukaj then asks as ``PlaylistRules.like``, the
        groups narrowing it and a smart playlist keeping it. The photograph
        itself is not kept; the same photograph again asks Google nothing."""
        key = PHOTO + hashlib.sha256(data).hexdigest()[:20]
        if self.photo_vector(key) is not None:
            return key
        self._check()
        small = img.convert("RGB")
        small.thumbnail((640, 640))
        if self._old:
            vector = np.asarray(self.painter.embed(KIND, [small])[0], dtype=np.float32)
            self._keep_photo(self._photo_path(key), vector)
        self._keep_photo(self._photo_path(key, three=True), self._three_of(small))
        return key

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
            vector = np.fromfile(self._photo_path(key, three=not self._old), dtype=np.float32)
        except (OSError, ValueError):
            return None
        return vector if len(vector) == self._asked().size else None

    def _photo_path(self, key: str, three: bool = False) -> Path:
        name = "".join(c for c in key.removeprefix(PHOTO) if c in "0123456789abcdef")
        return self.root / "photos" / f"{name or '0'}{'.three' if three else ''}.f32"

    def _three_of(self, img: Image.Image) -> np.ndarray:
        """A picture's three, asked of Google at once: its sentence, then
        its numbers."""
        words = self._tell(img)
        vectors = self.painter.embed(KIND, self._asks(img, words))
        g, h = vectors[0], vectors[1]
        return np.asarray(self._joined(g, h, vectors[2] if words else h), dtype=np.float32)

    def similar(
        self, item: Item, limit: int = 24, place: Place = Place.FOUND, by: By = ""
    ) -> list[Found]:
        """Works that look like ``item`` (``by``: both its subject and its
        style, or one of them): none until it or another copy of its work
        has numbers (the card shows the work's best copy, the index may
        have another: no "Podobne wyglądem" under van Gogh's Sunflowers
        found by a look, 2026-11-13). Its own copies and the work itself
        are left out; ``place``: where they are shown."""
        works = self.library.works()
        own = works.group_index(item.id)
        copies = [item.id] + (
            [c.id for c in works.groups[own] if c.id != item.id] if own is not None else []
        )
        asked = self._asked()
        vector = next((v for c in copies if (v := asked.vector(c)) is not None), None)
        if vector is None:
            return []
        near = self._alike_near(vector, limit * 3 + 8, by)
        near = [
            (i, s) for i, s in near if i != item.id and (own is None or works.group_index(i) != own)
        ]
        floor = PICTURE_FLOOR if self._old else THREE_FLOOR
        return self._answer(near, limit, floor, relative=False, place=place)

    def alike(self, item_id: str, by: str = "") -> list[str] | None:
        """The ids of the works that look like the work ``item_id`` (or the
        photograph kept as ``photo:…``, :meth:`photo`), by ``by`` (both
        their subject and their style, "subject" or "style"), nearest
        first, :data:`ALIKE_MOST` at most, for Szukaj
        (``Library.like_near``, ``PlaylistRules.like``); None with Szukanie
        wyglądem off. Asks Google nothing."""
        if not self.enabled():
            return None
        shape: By = by if by in ("subject", "style") else ""  # type: ignore[assignment]
        if item_id.startswith(PHOTO):
            vector = self.photo_vector(item_id)
            if vector is None:
                return []
            near = self._alike_near(vector, ALIKE_MOST * 3 + 8, shape)
            floor = PICTURE_FLOOR if self._old else THREE_FLOOR
            found = self._answer(near, ALIKE_MOST, floor, relative=False)
            return [f.item.id for f in found]
        item = self.library.get(item_id)
        if item is None:
            return []
        return [f.item.id for f in self.similar(item, ALIKE_MOST, by=shape)]

    def near_ids(self, item_id: str, limit: int = 40) -> list[str]:
        """The ids of the works whose numbers lie nearest ``item_id``'s
        (subject and style), whatever they are and wherever they are
        hidden: the gatekeeper's look-alikes of a cover. Asks Google
        nothing; none without numbers."""
        vector = self._asked().vector(item_id)
        if vector is None:
            return []
        if self._old:
            near = self.index.nearest(vector, limit + 1)
            return [i for i, score in near if i != item_id and score >= PICTURE_FLOOR][:limit]
        # Its style and its subject as they come, not centred: the
        # gatekeeper asks this of 200 covers at once, and this is some five
        # times quicker than :meth:`_alike_near`.
        style = _unit(vector[:PART])
        subject = _unit(vector[PART : 2 * PART])

        def score(rows: np.ndarray, norms: np.ndarray) -> np.ndarray:
            g = rows[:, :PART] @ style / np.maximum(norms[:, 0], 1e-9)
            h = rows[:, PART : 2 * PART] @ subject / np.maximum(norms[:, 1], 1e-9)
            return (g + h) / 2

        near = self.three.ranked(score, limit + 1)
        return [i for i, score in near if i != item_id and score >= RAW_FLOOR][:limit]

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
        if not len(self._asked()):
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

    def _words_score(self, rows: np.ndarray, vector: Sequence[float] | np.ndarray) -> np.ndarray:
        """How near words' numbers lie to works' rows: to the whole
        thumbnail before, to the nearer of its style and its subject now
        (their raw numbers: words name either)."""
        rows = np.asarray(rows, dtype=np.float32)
        if self._old:
            return _unit(rows) @ _unit(np.asarray(vector, dtype=np.float32))
        words = _unit(np.asarray(vector, dtype=np.float32)[:PART])
        style = _unit(rows[:, :PART]) @ words
        subject = _unit(rows[:, PART : 2 * PART]) @ words
        return np.maximum(style, subject)

    def _words_near(
        self, vector: Sequence[float] | np.ndarray, count: int
    ) -> list[tuple[str, float]]:
        if self._old:
            return self.index.nearest(vector, count)
        return self.three.ranked(lambda rows, _: self._words_score(rows, vector), count)

    def _alike_near(self, vector: np.ndarray, count: int, by: By = "") -> list[tuple[str, float]]:
        """The works nearest a work's (or a photograph's) numbers, by
        ``by``; with the numbers of before, simply the nearest."""
        if self._old:
            return self.index.nearest(vector, count)
        means = self.three.means()
        style, subject = shapes(np.asarray(vector, dtype=np.float32)[None, :], means)

        def score(rows: np.ndarray, _: np.ndarray) -> np.ndarray:
            their_style, their_subject = shapes(rows, means)
            if by == "style":
                return their_style @ style[0]
            if by == "subject":
                return their_subject @ subject[0]
            return (their_style @ style[0] + their_subject @ subject[0]) / 2

        return self.three.ranked(score, count)

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
        bar = max(low, best - NEAR_BEST) if relative else low
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

    # -- a work's three ----------------------------------------------------------------

    @staticmethod
    def _asks(img: Image.Image, words: str) -> list[Embedded]:
        """What the embedding model is asked of a picture for its three:
        its style, its subject, its sentence (none when Gemini gave none:
        the subject stands for it, :meth:`_joined`)."""
        asks: list[Embedded] = [(STYLE_ASK, img), (SUBJECT_ASK, img)]
        return [*asks, TOLD + words] if words else asks

    @staticmethod
    def _joined(g: Sequence[float], h: Sequence[float], c: Sequence[float]) -> list[float]:
        """A row of the three: the first :data:`PART` of each."""
        return [*g[:PART], *h[:PART], *c[:PART]]

    def _tell(self, img: Image.Image) -> str:
        """Gemini's sentence on what a picture depicts, asked at once;
        empty when it gives none (a picture it will not take)."""
        small = img.convert("RGB")
        small.thumbnail((TOLD_SIDE, TOLD_SIDE))
        try:
            return self.painter.describe(KIND, DESCRIBE, small)
        except (NotDrawn, httpx.HTTPError) as err:
            log.info("looks: no sentence for a picture (%s)", err)
            return ""

    def _load_told(self) -> None:
        path = self.three.root / TOLD_FILE
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            try:
                one = json.loads(line)
                item_id, stamp, words = str(one["id"]), int(one["stamp"]), str(one["words"])
            except (ValueError, KeyError, TypeError):
                continue  # a line broken off
            if self.three.stamp(item_id) == stamp:
                self._told.pop(item_id, None)
            else:
                self._told[item_id] = (stamp, words)

    def _keep_told(self, item_id: str, stamp: int, words: str) -> None:
        """A work's sentence, kept on disk (for good) and here (until its
        three are made)."""
        line = json.dumps({"id": item_id, "stamp": stamp, "words": words}, ensure_ascii=False)
        with self._told_lock:
            self.three.root.mkdir(parents=True, exist_ok=True)
            with (self.three.root / TOLD_FILE).open("a", encoding="utf-8") as out:
                out.write(line + "\n")
            self._told[item_id] = (stamp, words)

    # -- the background --------------------------------------------------------------

    def waiting(self, limit: int) -> list[tuple[Item, Path, int]]:
        """Up to ``limit`` works whose sentence to ask now, with their
        thumbnails and their stamps: without their three, or with the three
        of a picture since changed, and no sentence of this picture yet;
        those cared about first. Only thumbnails already here are sent."""
        have = self.three.ids()
        out = {
            item_id
            for name in (TELLING, BATCHES)
            for rows in self._out(name).values()
            for item_id, _ in rows
        }
        with self._told_lock:
            told = dict(self._told)
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
            if self.three.stamp(item.id) == stamp or told.get(item.id, (None,))[0] == stamp:
                continue
            found.append((item, thumb, stamp))
        return found

    def _ready_to_number(self, limit: int) -> list[tuple[str, Path, int, str]]:
        """Up to ``limit`` works told and not yet numbered (their thumbnail,
        its stamp, the sentence), those cared about first; a sentence of a
        picture since changed, or of a work gone, is let go."""
        out = {item_id for rows in self._out(BATCHES).values() for item_id, _ in rows}
        ranks = self.cared()
        with self._told_lock:
            told = sorted(self._told.items(), key=lambda kv: ranks.get(kv[0], 99))
        found: list[tuple[str, Path, int, str]] = []
        for item_id, (stamp, words) in told:
            if len(found) >= limit:
                break
            seen = self._no_thumb.get(item_id)
            if item_id in out or (seen is not None and self.clock() - seen < NO_THUMB_AGAIN):
                continue
            thumb = self.images.kept_thumb(item_id)
            try:
                now = int(thumb.stat().st_mtime) if thumb is not None else None
            except OSError:
                now = None
            if now != stamp or self.library.get(item_id) is None:
                with self._told_lock:
                    if self._told.get(item_id, (None,))[0] == stamp:
                        del self._told[item_id]
                continue
            assert thumb is not None
            found.append((item_id, thumb, stamp, words))
        return found

    # -- the Batch --------------------------------------------------------------------

    def _out(self, name: str = BATCHES, old: bool = False) -> dict[str, list[tuple[str, int]]]:
        """The batches out: their works and stamps, by the batch's name
        (``old``: those of the numbers of before)."""
        root = self.root if old else self.three.root
        try:
            raw = json.loads((root / name).read_text())
        except (OSError, ValueError):
            return {}
        return {
            str(batch): [(str(i), int(stamp)) for i, stamp in rows]
            for batch, rows in raw.items()
            if isinstance(rows, list)
        }

    def _keep_out(self, out: dict[str, list[tuple[str, int]]], name: str = BATCHES) -> None:
        root = self.three.root
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({batch: [list(r) for r in rows] for batch, rows in out.items()}))
        os.replace(temp, path)

    def _all_out(self) -> int:
        return sum(len(self._out(name)) for name in (TELLING, BATCHES)) + len(self._out(old=True))

    def collect(self) -> int:
        """The answers of the batches Google has answered kept: sentences,
        then numbers; how many works got their three. A lost batch is
        dropped (its works go again)."""
        self._collect_old()
        self._collect_told()
        out = self._out(BATCHES)
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
            kept = []
            with self._told_lock:
                told = dict(self._told)
            for item_id, stamp in rows:
                g, h = found.get(f"{item_id}#g"), found.get(f"{item_id}#h")
                if not g or not h:
                    self._no_thumb[item_id] = self.clock()  # tried again tomorrow
                    continue
                c = found.get(f"{item_id}#c") or h
                kept.append((item_id, stamp, self._joined(g, h, c)))
            self.three.add(kept)
            with self._told_lock:
                for item_id, stamp, _ in kept:
                    if told.get(item_id, (None,))[0] == stamp and item_id in self._told:
                        del self._told[item_id]
            done += len(kept)
            del out[name]
        self._keep_out(out, BATCHES)
        return done

    def _collect_told(self) -> int:
        """The sentences of the batches Google has answered kept; how
        many. A work Gemini says nothing of gets an empty one (its subject
        stands for it)."""
        out = self._out(TELLING)
        done = 0
        for name, rows in list(out.items()):
            try:
                found = self.painter.described(KIND, name)
            except NotDrawn as err:
                log.warning("looks: %s", err)
                del out[name]
                continue
            if found is None:
                continue
            for item_id, stamp in rows:
                said = found.get(item_id)
                self._keep_told(item_id, stamp, said if isinstance(said, str) else "")
                done += 1
            del out[name]
        self._keep_out(out, TELLING)
        return done

    def _collect_old(self) -> int:
        """The numbers of before still out when the three came: kept while
        they answer, let go after."""
        out = self._out(old=True)
        if not out:
            return 0
        done = 0
        for name, rows in list(out.items()):
            if self._old:
                try:
                    found = self.painter.embed_batched(KIND, name)
                except NotDrawn:
                    found = {}
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
        path = self.root / BATCHES
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({b: [list(r) for r in rows] for b, rows in out.items()}))
        os.replace(temp, path)
        return done

    def send(self) -> int:
        """Batches sent while fewer than :data:`OPEN` are out: the numbers
        of works told, then the sentences of works waiting; how many works
        went."""
        if not self.enabled():
            return 0
        sent = 0
        out = self._out(BATCHES)
        while self._all_out() < OPEN and not self._stop.is_set():
            todo = self._ready_to_number(PER_BATCH)
            groups: list[tuple[tuple[str, int], list[tuple[str, Embedded]]]] = []
            for item_id, thumb, stamp, words in todo:
                try:
                    with Image.open(io.BytesIO(thumb.read_bytes())) as img:
                        img.load()
                        picture = img.convert("RGB")
                except OSError:
                    self._no_thumb[item_id] = self.clock()
                    continue
                asks = self._asks(picture, words)
                names = [f"{item_id}#g", f"{item_id}#h", f"{item_id}#c"]
                groups.append(((item_id, stamp), list(zip(names, asks, strict=False))))
            if not groups:
                break
            sent += self._hand(
                groups, lambda part: self.painter.embed_batch(KIND, part), out, BATCHES
            )
            if len(todo) < PER_BATCH:
                break
        telling = self._out(TELLING)
        while self._all_out() < OPEN and not self._stop.is_set():
            waiting = self.waiting(PER_TOLD)
            told: list[tuple[tuple[str, int], list[tuple[str, Image.Image]]]] = []
            for item, thumb, stamp in waiting:
                try:
                    with Image.open(io.BytesIO(thumb.read_bytes())) as img:
                        img.load()
                        small = img.convert("RGB")
                    small.thumbnail((TOLD_SIDE, TOLD_SIDE))
                except OSError:
                    self._no_thumb[item.id] = self.clock()
                    continue
                told.append(((item.id, stamp), [(item.id, small)]))
            if not told:
                break
            sent += self._hand(
                told,
                lambda part: self.painter.describe_batch(KIND, DESCRIBE, part),
                telling,
                TELLING,
            )
            if len(waiting) < PER_TOLD:
                break
        return sent

    def _hand(
        self,
        groups: Sequence[tuple[tuple[str, int], Sequence[tuple[str, Any]]]],
        send: Callable[[list[tuple[str, Any]]], str],
        out: dict[str, list[tuple[str, int]]],
        name: str,
    ) -> int:
        """Hands each work's questions (``groups``: the work and its
        stamp, its questions) to the Batch with ``send``, in halves while
        they weigh more than Google takes at once (bigger thumbnails: 300
        weighed 30 MB of 19, and no work got its numbers from 2026-11-13
        16:08 on); how many works went. A work too heavy alone waits as one
        without a thumbnail."""
        try:
            batch = send([one for _, asks in groups for one in asks])
        except TooHeavy:
            if len(groups) == 1:
                self._no_thumb[groups[0][0][0]] = self.clock()
                return 0
            half = len(groups) // 2
            return self._hand(groups[:half], send, out, name) + self._hand(
                groups[half:], send, out, name
            )
        out[batch] = [row for row, _ in groups]
        self._keep_out(out, name)
        return len(groups)

    def round(self) -> tuple[int, int]:
        """Collects what came back, then sends more: (works that got their
        three, works sent); then, once enough works have their three, they
        answer."""
        done, sent = self.collect(), self.send()
        self.settle()
        return done, sent

    def settle(self) -> bool:
        """Once :data:`READY_SHARE` of the works have their three, they
        answer and the numbers of before are dropped; whether they answer."""
        if not self._old:
            return True
        self._counts = None
        done, total = self.counts()
        if not total or done < READY_SHARE * total:
            return False
        self.three.root.mkdir(parents=True, exist_ok=True)
        (self.three.root / READY).write_text(f"{done}/{total}\n")
        self._old = False
        self.index.forget(self.index.ids())
        for path in (self.root / "vectors.i8", self.root / "ids.txt", self.root / BATCHES):
            path.unlink(missing_ok=True)
        for path in (self.root / "photos").glob("*.f32"):
            if not path.name.endswith(".three.f32"):
                path.unlink(missing_ok=True)
        log.info("looks: %d of %d works have their three; they answer now", done, total)
        return True

    def tidy(self) -> int:
        """Rows of works no longer in the library forgotten; how many."""
        kept = {i.id for i in self.library.all_items()}
        gone = self.three.ids() - kept
        self.three.forget(gone)
        self.index.forget(self.index.ids() - kept)
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
                    pause = POLL if self._all_out() else IDLE
                    if done or sent:
                        log.info(
                            "looks: %d works got their three, %d sent (%d kept)",
                            done,
                            sent,
                            len(self.three),
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
