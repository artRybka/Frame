"""How works look, as numbers made on the server itself: SigLIP 2 (Google,
ViT-B-16 at 256 px, Apache License 2.0) in place of Google's embedding
model of :mod:`frame_server.looks` (Mateusz 2026-11-20: "Przesiadamy.";
on the trial's boards "Jest super. Wdrażajmy").

A trial on 13 790 works of his catalogue (2026-11-20) against
gemini-embedding-2: of the twelve works it put first for a Szukaj phrase in
English, 9.9 were among Gemini's first 120; the ten works nearest a work
were by the same artist 33 times in 150 (Gemini 44), and with a small layer
taught on the catalogue (step two) its subject and its form apart as well
as Gemini's three (subject: same subject 76% against 79%; form: same
technique 59% against 60%). Apple's MobileCLIP did as well, but its weights
may be used for research only.

Step one, this module: the model fetched once from the repository's release
(:data:`MODEL`, made by ``scripts/look-model/export.py``, some 950 MB, kept
in ``data/seen``), and every work :meth:`Looks.wanted <frame_server.looks.Looks.wanted>`
numbered from its kept thumbnail in the background, a few at a time, while
the app is not in use; a work whose thumbnail changed is numbered again.
Nothing is asked of them yet but the owner's debug questions: Szukaj and
"Podobne do" stay with Gemini until most works have their numbers here.
"""

from __future__ import annotations

import contextlib
import hashlib
import html
import logging
import os
import re
import string
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import numpy as np
from PIL import Image

from .library.models import Item
from .looks import CHUNK, LookIndex, Looks

if TYPE_CHECKING:
    from .library import Library
    from .library.images import ImageCache

log = logging.getLogger(__name__)

#: The release the model is fetched from (``.github/workflows/look-model.yml``'s TAG).
MODEL = "look-model-siglip2-b16-1"
#: Where releases are fetched from.
RELEASES = "https://github.com/artRybka/Frame/releases/download"
#: The model's files; their sums come in ``SHA256SUMS``.
FILES = ("picture.onnx", "words.onnx", "tokenizer.json")
SUMS = "SHA256SUMS"
#: The picture side for the phone (Core ML, made on the Mac from the same
#: weights, ``scripts/look-model/phone.py``; an uncompressed tar): fetched
#: beside the server's own and handed to the app, which numbers a photograph
#: itself and sends the numbers (Mateusz 2026-11-21: "szykujmy takie
#: rozwiązanie"). Its sum is kept here: the release has no ``SHA256SUMS``.
#: Empty: none yet.
PHONE = "look-model-siglip2-b16-phone-1"
PHONE_FILE = "Look.mlpackage.tar"
PHONE_SUM = "88ca2a8b423763a4da6751d524c5e454e3dd06b226f516d3112c6bad3423fb69"

#: Numbers a work.
SIZE = 768
#: The side its picture is seen at, and the words' tokens at most.
SIDE = 256
CONTEXT = 64

#: Works numbered at once, and the pause after each batch (the NAS's
#: processor shared with everything else).
BATCH = 16
BREATHE = 1.0
#: The model's threads (of the processor's cores).
THREADS = 2
#: The pause while the app is in use, after a failure, and with nothing to do.
IN_USE = 60.0
REST = 1800.0
IDLE = 900.0
#: Works whose thumbnail was missing are looked for again after a day.
NO_THUMB_AGAIN = 86_400.0
#: Lower priority of the background's thread (and the model's, made in it).
NICE = 10
#: Works with their numbers as a share of those that would have them, from
#: which SigLIP answers in Google's place (``seen/answers``), and how often
#: that is looked at.
READY_SHARE = 0.95
READY_EVERY = 600.0
ANSWERS = "answers"


@dataclass(frozen=True)
class Floors:
    """How near is near enough with SigLIP's numbers, in place of
    :mod:`frame_server.looks`' Gemini floors. Set on his catalogue on the NAS
    (2026-11-21, 35 works, 40% numbered): as many works above each floor as
    Gemini showed, ``scripts/look-model/calibrate.py``."""

    #: Words: at least this near, and not further than ``near_best`` below the best.
    words: float = 0.08
    near_best: float = 0.04
    #: A photograph: at least this near.
    picture: float = 0.78
    #: A work like another: at least this near to be shown at all.
    base: float = 0.70
    #: "Podobne do": both, the subject, the style; ``step`` less for each
    #: step scrolled on.
    alike: dict[str, float] = field(
        default_factory=lambda: {"": 0.84, "subject": 0.80, "style": 0.85}
    )
    step: float = 0.03
    #: The gatekeeper's look-alikes of a cover.
    raw: float = 0.84


FLOORS = Floors()
#: Whether :data:`FLOORS` were set on his catalogue: until then SigLIP never
#: answers, however many works have their numbers.
FLOORS_SET = True


def _unit_rows(rows: np.ndarray) -> np.ndarray:
    """Rows (bytes as kept, or numbers) at length 1."""
    found = rows.astype(np.float32)
    return found / np.maximum(np.linalg.norm(found, axis=1, keepdims=True), 1e-9)


class SeenModel:
    """SigLIP 2's two sides, fetched into ``root`` on first use."""

    def __init__(self, root: Path, threads: int = THREADS) -> None:
        self.root = root
        self.threads = threads
        self._lock = threading.Lock()
        self._picture: Any = None
        self._words: Any = None
        self._tokenizer: Any = None

    @property
    def folder(self) -> Path:
        return self.root / MODEL

    def loaded(self) -> bool:
        """Whether either side is in memory."""
        with self._lock:
            return self._picture is not None or self._words is not None

    def release(self) -> None:
        """Both sides and the tokenizer out of memory, read again on next
        use (a second or two). The picture side took some 0.5 GB of the
        NAS's memory to the next restart, the words' as much once a debug
        question asked them (Mateusz 2026-11-20: "Potem chyba faktycznie nie
        musi być cały czas w pamięci"). A run under way keeps its own hold."""
        with self._lock:
            self._picture = self._words = self._tokenizer = None

    def here(self) -> bool:
        return all((self.folder / name).is_file() for name in FILES)

    def fetch(self, client: httpx.Client | None = None) -> None:
        """The model's files fetched when not here, each checked against its sum."""
        if self.here():
            return
        own = client is None
        http = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0))
        try:
            sums = self._sums(http.get(f"{RELEASES}/{MODEL}/{SUMS}").raise_for_status().text)
            self.folder.mkdir(parents=True, exist_ok=True)
            for name in FILES:
                path = self.folder / name
                if path.is_file():
                    continue
                part = path.with_suffix(path.suffix + ".part")
                digest = hashlib.sha256()
                with http.stream("GET", f"{RELEASES}/{MODEL}/{name}") as answer:
                    answer.raise_for_status()
                    with part.open("wb") as out:
                        for chunk in answer.iter_bytes(1 << 20):
                            digest.update(chunk)
                            out.write(chunk)
                if digest.hexdigest() != sums.get(name):
                    part.unlink(missing_ok=True)
                    raise ValueError(f"seen: {name} came changed on the way")
                os.replace(part, path)
                log.info("seen: %s fetched (%d MB)", name, path.stat().st_size >> 20)
        finally:
            if own:
                http.close()

    def phone(self, client: httpx.Client | None = None) -> Path | None:
        """The phone's picture side (:data:`PHONE`), fetched when not here and
        checked against :data:`PHONE_SUM`; None when there is none yet."""
        if not PHONE_SUM:
            return None
        path = self.root / PHONE / PHONE_FILE
        if path.is_file():
            return path
        own = client is None
        http = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            part = path.with_suffix(path.suffix + ".part")
            digest = hashlib.sha256()
            with http.stream("GET", f"{RELEASES}/{PHONE}/{PHONE_FILE}") as answer:
                answer.raise_for_status()
                with part.open("wb") as out:
                    for chunk in answer.iter_bytes(1 << 20):
                        digest.update(chunk)
                        out.write(chunk)
            if digest.hexdigest() != PHONE_SUM:
                part.unlink(missing_ok=True)
                raise ValueError(f"seen: {PHONE_FILE} came changed on the way")
            os.replace(part, path)
            log.info("seen: the phone's model fetched (%d MB)", path.stat().st_size >> 20)
            return path
        finally:
            if own:
                http.close()

    def phone_here(self) -> Path | None:
        """The phone's picture side when already fetched, else None."""
        path = self.root / PHONE / PHONE_FILE
        return path if PHONE_SUM and path.is_file() else None

    @staticmethod
    def _sums(text: str) -> dict[str, str]:
        found = {}
        for line in text.splitlines():
            digest, _, name = line.strip().partition("  ")
            if name:
                found[name] = digest
        return found

    def _session(self, name: str) -> Any:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        return ort.InferenceSession(
            str(self.folder / name), options, providers=["CPUExecutionProvider"]
        )

    @staticmethod
    def pixels(img: Image.Image) -> np.ndarray:
        """A picture as the model sees it: RGB at :data:`SIDE` square, -1 to 1."""
        seen = img.convert("RGB").resize((SIDE, SIDE), Image.Resampling.BICUBIC)
        return (np.asarray(seen, dtype=np.float32) / 127.5 - 1.0).transpose(2, 0, 1)

    def pictures(self, imgs: Sequence[Image.Image]) -> np.ndarray:
        """Unit vectors of :data:`SIZE` numbers, one a picture."""
        if not imgs:
            return np.zeros((0, SIZE), dtype=np.float32)
        with self._lock:
            if self._picture is None:
                self._picture = self._session("picture.onnx")
            session = self._picture
        batch = np.stack([self.pixels(img) for img in imgs])
        return np.asarray(session.run(None, {"pixels": batch})[0], dtype=np.float32)

    @staticmethod
    def clean(text: str) -> str:
        """As SigLIP's words were read when it was taught: no punctuation,
        lower case, single spaces."""
        text = html.unescape(html.unescape(text)).strip().replace("_", " ")
        text = text.translate(str.maketrans("", "", string.punctuation)).lower()
        return " ".join(text.split())

    def tokens(self, texts: Sequence[str]) -> np.ndarray:
        with self._lock:
            if self._tokenizer is None:
                from tokenizers import Tokenizer

                self._tokenizer = Tokenizer.from_file(str(self.folder / "tokenizer.json"))
            tokenizer = self._tokenizer
        out = np.zeros((len(texts), CONTEXT), dtype=np.int64)
        for row, text in enumerate(texts):
            ids = tokenizer.encode(self.clean(text)).ids[:CONTEXT]
            out[row, : len(ids)] = ids
        return out

    def words(self, texts: Sequence[str]) -> np.ndarray:
        """Unit vectors of :data:`SIZE` numbers, one for each text (best in English)."""
        if not texts:
            return np.zeros((0, SIZE), dtype=np.float32)
        tokens = self.tokens(texts)
        with self._lock:
            if self._words is None:
                self._words = self._session("words.onnx")
            session = self._words
        return np.asarray(session.run(None, {"tokens": tokens})[0], dtype=np.float32)


# -- a work's form and its subject apart ---------------------------------------------------

#: The techniques the form is taught to tell apart, by words of a work's
#: medium (as in the trial of 2026-11-20).
TECHNIQUES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        ("woodcut", r"woodcut|woodblock|drzeworyt|gravure sur bois|xylograph|nishiki|ukiyo"),
        (
            "etching",
            r"etching|engraving|akwafort|miedzioryt|staloryt|intaglio|drypoint|sucha igła"
            r"|mezzotint|aquatint|akwatint|gravure|eau-forte|burin",
        ),
        ("litho", r"lithograph|litografi|lithographie"),
        (
            "photo",
            r"photograph|albumen|gelatin silver|fotografi|daguerre|platinum print|salted paper",
        ),
        ("watercolour", r"watercolou?r|akwarel|aquarelle|gouache|gwasz"),
        ("oil", r"\boil\b|olej|huile|oil on|peinture à l'huile|tempera"),
        (
            "drawing",
            r"graphite|pencil|ołówek|charcoal|węgiel|chalk|kred|pen |pióro|ink|tusz|sanguine"
            r"|pastel|crayon|fusain|plume|encre|drawing|rysun",
        ),
    )
)
#: ... and the half centuries.
HALVES = tuple(range(1300, 2100, 50))
#: A subject is taught when this many works have it.
LEAST_SUBJECT = 30
#: How hard each layer holds back (ridge): the trial's best.
HOLD_FORM = 3.0
HOLD_SUBJECT = 0.3
#: The subject alone is chosen among this many nearest by both halves (the
#: boards Mateusz chose it on, 2026-11-22).
BARE_AMONG = 2000
#: The layers are taught again once the works with numbers grew by this share.
TEACH_AGAIN = 0.05
HEADS = "heads.npz"
_YEAR = re.compile(r"(1[0-9]{3}|20[0-2][0-9])")


def technique(item: Item) -> str | None:
    medium = item.medium.lower()
    return next((name for name, pattern in TECHNIQUES if pattern.search(medium)), None)


def year(item: Item) -> int | None:
    if item.year:
        return item.year
    found = _YEAR.search(item.date_text or "")
    return int(found.group(1)) if found else None


def form_marks(item: Item) -> list[int]:
    """The columns of a work's form it is taught by: its technique, its half century."""
    marks = []
    found = technique(item)
    if found is not None:
        marks.append([name for name, _ in TECHNIQUES].index(found))
    when = year(item)
    if when is not None:
        half = min(len(HALVES) - 1, max(0, (when - HALVES[0]) // 50))
        marks.append(len(TECHNIQUES) + half)
    return marks


class Heads:
    """Two small layers taught on the catalogue (Mateusz 2026-11-20:
    "Czy nie ma żadnej możliwości utrzymania podziału na formę i treść?"):
    from a work's numbers to its technique and half century (its form), and
    to the subjects of its terms (its subject). A work's form is then the
    first's answer beside its numbers, its subject the second's
    (:meth:`Seen.alike_near`): the trial's Treść 13/42/76% and Forma
    17/59/65% (artist, technique, subject among the ten nearest)."""

    def __init__(self, form: np.ndarray, subject: np.ndarray, subjects: list[str], count: int):
        #: (weights :data:`SIZE` × columns, then a row of means, a row of spreads)
        self.form = form
        self.subject = subject
        self.subjects = subjects
        self.count = count

    @staticmethod
    def _ridge(x: np.ndarray, xty: np.ndarray, hold: float) -> np.ndarray:
        gram = x.T @ x + hold * np.eye(x.shape[1], dtype=np.float64)
        return np.linalg.solve(gram, xty)

    @classmethod
    def taught(cls, vectors: np.ndarray, items: Sequence[Item]) -> Heads:
        """Both layers from works' unit ``vectors`` and the works."""
        x = vectors.astype(np.float64)
        counts: dict[str, int] = {}
        for item in items:
            for term in item.terms:
                if term.startswith("subject:"):
                    counts[term] = counts.get(term, 0) + 1
        subjects = sorted(t for t, n in counts.items() if n >= LEAST_SUBJECT)
        column = {t: k for k, t in enumerate(subjects)}
        width = len(TECHNIQUES) + len(HALVES)

        def layer(marks: list[list[int]], columns: int, hold: float) -> np.ndarray:
            y = np.zeros((len(items), max(columns, 1)), dtype=np.float64)
            for row, found in enumerate(marks):
                y[row, found] = 1.0
            y -= y.mean(axis=0)
            weights = cls._ridge(x, x.T @ y, hold)
            answers = x @ weights
            return np.vstack([weights, answers.mean(axis=0), answers.std(axis=0) + 1e-6]).astype(
                np.float32
            )

        form = layer([form_marks(i) for i in items], width, HOLD_FORM)
        subject = layer(
            [[column[t] for t in i.terms if t in column] for i in items],
            len(subjects),
            HOLD_SUBJECT,
        )
        return cls(form, subject, subjects, len(items))

    @staticmethod
    def answer(layer: np.ndarray, vectors: np.ndarray) -> np.ndarray:
        """A layer's answer for unit ``vectors``: each column at its spread
        over the catalogue, each row at length 1."""
        found = (vectors @ layer[:-2] - layer[-2]) / layer[-1]
        length = np.linalg.norm(found, axis=1, keepdims=True)
        return (found / np.maximum(length, 1e-9)).astype(np.float32)

    def save(self, path: Path) -> None:
        part = path.with_suffix(".new.npz")
        np.savez(
            part,
            form=self.form,
            subject=self.subject,
            subjects=np.array(self.subjects, dtype=str),
            count=np.array(self.count),
        )
        os.replace(part, path)

    @classmethod
    def load(cls, path: Path) -> Heads | None:
        try:
            with np.load(path) as kept:
                return cls(
                    kept["form"],
                    kept["subject"],
                    [str(s) for s in kept["subjects"]],
                    int(kept["count"]),
                )
        except (OSError, KeyError, ValueError):
            return None


class Seen:
    """Every work's SigLIP numbers, made in the background."""

    def __init__(
        self,
        library: Library,
        images: ImageCache,
        root: Path,
        model: SeenModel | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.library = library
        self.images = images
        self.root = root
        self.model = model or SeenModel(root / "model")
        self.index = LookIndex(root / "index", size=SIZE)
        self.clock = clock
        #: The works cared about, by id (``cared.Cared.ranks``): numbered first.
        self.cared: Callable[[], dict[str, int]] = dict
        #: Whether the app is in use now: the background waits.
        self.busy: Callable[[], bool] = lambda: False
        self._no_thumb: dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: Why the last round stopped short.
        self.trouble: str | None = None
        #: The layers telling a work's form and subject (None until taught).
        self.heads = Heads.load(root / HEADS)
        self._shaped_lock = threading.Lock()
        #: The works' form and subject by the layers, in the index's rows'
        #: order: (the index's generation, the heads, form rows, subject rows).
        self._shaped: tuple[int, Heads, np.ndarray, np.ndarray] | None = None
        self._answers = (root / ANSWERS).exists()

    def answers(self) -> bool:
        """Whether SigLIP's numbers answer Szukaj in Google's place: once
        :data:`READY_SHARE` of the works have them and the layers are taught
        (``seen/answers``; without it Google answers again)."""
        return self._answers and self.heads is not None

    def settle(self) -> bool:
        """Answers from now on when enough works have their numbers; whether it does."""
        if self._answers:
            return True
        if self.heads is None or not FLOORS_SET:
            return False
        done, total = self.counts()
        if not total or done < READY_SHARE * total:
            return False
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ANSWERS).write_text(f"{done}/{total}\n")
        self._answers = True
        log.info("seen: %d of %d works have their numbers; SigLIP answers now", done, total)
        return True

    def add(self, rows: Sequence[tuple[str, int, Image.Image]]) -> None:
        """Pictures numbered at once (a museum search's works judged by
        their look), :data:`BATCH` at a time."""
        for at in range(0, len(rows), BATCH):
            part = rows[at : at + BATCH]
            vectors = self.model.pictures([img for _, _, img in part])
            self.index.add([(i, stamp, v) for (i, stamp, _), v in zip(part, vectors, strict=True)])

    def counts(self) -> tuple[int, int]:
        """Works with their numbers here, and works that would have them."""
        wanted = {i.id for i in self.library.all_items() if Looks.wanted(i)}
        return len(wanted & self.index.ids()), len(wanted)

    def waiting(self, limit: int) -> list[tuple[str, Path, int]]:
        """Up to ``limit`` works to number now (id, thumbnail, its stamp):
        without numbers or with those of a thumbnail since changed; those
        cared about first. Only thumbnails already here."""
        ranks = self.cared()
        have = self.index.ids()
        items = [i for i in self.library.all_items() if Looks.wanted(i)]
        items.sort(key=lambda i: (ranks.get(i.id, 99), i.id in have))
        found: list[tuple[str, Path, int]] = []
        now = self.clock()
        for item in items:
            if len(found) >= limit:
                break
            seen = self._no_thumb.get(item.id)
            if seen is not None and now - seen < NO_THUMB_AGAIN:
                continue
            thumb = self.images.kept_thumb(item.id)
            if thumb is None:
                self._no_thumb[item.id] = now
                continue
            try:
                stamp = int(thumb.stat().st_mtime)
            except OSError:
                continue
            if self.index.stamp(item.id) != stamp:
                found.append((item.id, thumb, stamp))
        return found

    def number(self, limit: int = BATCH) -> int:
        """Numbers up to ``limit`` works; how many."""
        todo = self.waiting(limit)
        rows: list[tuple[str, int, Image.Image]] = []
        for item_id, thumb, stamp in todo:
            try:
                with Image.open(thumb) as img:
                    img.load()
                    rows.append((item_id, stamp, img.copy()))
            except (OSError, ValueError, Image.DecompressionBombError):
                self._no_thumb[item_id] = self.clock()
        if not rows:
            return 0
        self.add(rows)
        return len(rows)

    def tidy(self) -> int:
        """Numbers of works no longer in the library forgotten; how many."""
        gone = self.index.ids() - {i.id for i in self.library.all_items()}
        self.index.forget(gone)
        return len(gone)

    def nearest(self, vector: np.ndarray, count: int) -> list[tuple[str, float]]:
        return self.index.nearest(vector, count)

    # -- form and subject ------------------------------------------------------------

    def teach(self, force: bool = False) -> bool:
        """The layers taught (again) on the works with numbers, when there
        are none yet or the works grew by :data:`TEACH_AGAIN`; whether they were."""
        count = len(self.index)
        heads = self.heads
        if not count or (
            not force and heads is not None and count < heads.count * (1 + TEACH_AGAIN)
        ):
            return False
        with self.index._lock:
            rows, live = self.index._rows, dict(self.index._row)
        items, at = [], []
        for item_id, row in live.items():
            item = self.library.get(item_id)
            if item is not None:
                items.append(item)
                at.append(row)
        if not items:
            return False
        vectors = _unit_rows(rows[np.array(at, dtype=np.int64)])
        took = self.clock()
        self.heads = Heads.taught(vectors, items)
        self.root.mkdir(parents=True, exist_ok=True)
        self.heads.save(self.root / HEADS)
        log.info(
            "seen: form and subject taught on %d works (%d subjects) in %.0f s",
            len(items),
            len(self.heads.subjects),
            self.clock() - took,
        )
        return True

    def shaped(self) -> tuple[Heads, np.ndarray, np.ndarray, list[str], dict[str, int]] | None:
        """The heads, the works' form and subject rows (as the index's rows),
        and the index's ids; rows added since the last time worked out now."""
        heads = self.heads
        if heads is None:
            return None
        with self.index._lock:
            rows, ids, live = self.index._rows, list(self.index._ids), dict(self.index._row)
            generation = self.index.generation
        with self._shaped_lock:
            kept = self._shaped
            if (
                kept is None
                or kept[0] != generation
                or kept[1] is not heads
                or len(kept[2]) > len(rows)
            ):
                kept = (
                    generation,
                    heads,
                    np.zeros((0, heads.form.shape[1]), np.float16),
                    np.zeros((0, heads.subject.shape[1]), np.float16),
                )
            start = len(kept[2])
            if start < len(rows):
                forms, subjects = [kept[2]], [kept[3]]
                for at in range(start, len(rows), CHUNK):
                    unit = _unit_rows(rows[at : at + CHUNK])
                    forms.append(Heads.answer(heads.form, unit).astype(np.float16))
                    subjects.append(Heads.answer(heads.subject, unit).astype(np.float16))
                kept = (generation, heads, np.concatenate(forms), np.concatenate(subjects))
                self._shaped = kept
        return heads, kept[2], kept[3], ids, live

    def alike_near(self, vector: np.ndarray, count: int, by: str = "") -> list[tuple[str, float]]:
        """The works nearest a work's (or a photograph's) numbers: by its
        whole look (``by`` empty), or by its form ("style") or its subject
        ("subject"): the layer's answer and the whole look, half each.

        The subject alone is asked of the look without its form (Mateusz
        2026-11-22, Wyspiański's self-portrait by Treść alone: "w wynikach
        praktycznie tylko rysunek"; of the boards he chose "Bez formy"): the
        whole look less what the form layer says of the two, beside the
        subject layer's answer, among the :data:`BARE_AMONG` nearest.
        (Taking only the form layer's directions out of the numbers changed
        nothing: "Chyba bez istotnych zmian?") Its
        scores are then told at the levels the half-and-half ones have at
        the same places (the n-th nearest gets the n-th nearest's score of
        before), so the floors set on those still show as many works."""
        query = _unit_rows(np.asarray(vector, dtype=np.float32)[None, :])[0]
        shaped = self.shaped() if by in ("style", "subject") else None
        if shaped is None:
            return self.index.nearest(query, count)
        heads, forms, subjects, ids, live = shaped
        layer, answers = (heads.form, forms) if by == "style" else (heads.subject, subjects)
        asked = Heads.answer(layer, query[None, :])[0]
        bare = by == "subject"
        form_asked = Heads.answer(heads.form, query[None, :])[0] if bare else None
        with self.index._lock:
            rows, norms = self.index._rows, self.index._norms
        rows, norms = rows[: len(answers)], norms[: len(answers)]
        scores = np.empty(len(answers), dtype=np.float32)
        levels = np.empty(len(answers), dtype=np.float32) if bare else None
        for at in range(0, len(answers), CHUNK):
            whole = rows[at : at + CHUNK].astype(np.float32) @ query
            whole /= np.maximum(norms[at : at + CHUNK, 0], 1e-9)
            told = answers[at : at + CHUNK].astype(np.float32) @ asked
            scores[at : at + CHUNK] = (whole + told) / 2
            if levels is not None and form_asked is not None:
                levels[at : at + CHUNK] = scores[at : at + CHUNK]
                form = forms[at : at + CHUNK].astype(np.float32) @ form_asked
                scores[at : at + CHUNK] = (whole - form + told) / 2
        if levels is None:
            return LookIndex.top(scores, ids, live, count)
        # Among the nearest of before, as on the boards: over the whole
        # catalogue a work far in everything but its technique would come.
        among = LookIndex.top(levels, ids, live, max(BARE_AMONG, count))
        ranked = sorted(among, key=lambda pair: -float(scores[live[pair[0]]]))[:count]
        before = [s for _, s in among[: len(ranked)]]
        return [(i, level) for (i, _), level in zip(ranked, before, strict=True)]

    def like(self, item_id: str, count: int, by: str = "") -> list[tuple[str, float]] | None:
        """The works nearest this one (``by`` as :meth:`alike_near`), or
        None when it has no numbers yet."""
        vector = self.index.vector(item_id)
        if vector is None:
            return None
        near = self.alike_near(vector, count + 1, by)
        return [(i, s) for i, s in near if i != item_id][:count]

    def words(self, text: str, count: int) -> list[tuple[str, float]]:
        return self.nearest(self.model.words([text])[0], count)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="seen", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        with contextlib.suppress(AttributeError, OSError):
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), NICE)
        tidied = settled = 0.0
        done = 0
        began = self.clock()
        while not self._stop.is_set():
            pause = BREATHE
            try:
                if self.busy():
                    pause = IN_USE
                else:
                    self.model.fetch()
                    self.model.phone()
                    if self.clock() - tidied > 86_400:
                        self.tidy()
                        tidied = self.clock()
                    self.teach()
                    if self.clock() - settled > READY_EVERY:
                        self.settle()
                        settled = self.clock()
                    took = self.clock()
                    count = self.number()
                    self.trouble = None
                    if count:
                        done += count
                        if done % (BATCH * 50) < count:
                            have, total = self.counts()
                            log.info(
                                "seen: %d of %d works have their numbers (%.2f s a work)",
                                have,
                                total,
                                (self.clock() - took) / count,
                            )
                    else:
                        if done:
                            have, total = self.counts()
                            log.info(
                                "seen: %d of %d works have their numbers, %d made in %.0f min",
                                have,
                                total,
                                done,
                                (self.clock() - began) / 60,
                            )
                            done = 0
                        # Nothing left to number: the model out of memory
                        # until a new work or a debug question wants it.
                        # Never while works wait, nor in the app's pauses.
                        if self.model.loaded():
                            self.model.release()
                            log.info("seen: nothing to number; the model let go of")
                        pause = IDLE
            except Exception as err:
                self.trouble = str(err)
                log.exception("seen: a round failed")
                pause = REST
            self._stop.wait(pause)
            if pause == IDLE:
                began = self.clock()
