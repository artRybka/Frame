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
import string
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import numpy as np
from PIL import Image

from .looks import LookIndex, Looks

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
        vectors = self.model.pictures([img for _, _, img in rows])
        self.index.add(
            [(item_id, stamp, v) for (item_id, stamp, _), v in zip(rows, vectors, strict=True)]
        )
        return len(rows)

    def tidy(self) -> int:
        """Numbers of works no longer in the library forgotten; how many."""
        gone = self.index.ids() - {i.id for i in self.library.all_items()}
        self.index.forget(gone)
        return len(gone)

    def nearest(self, vector: np.ndarray, count: int) -> list[tuple[str, float]]:
        return self.index.nearest(vector, count)

    def like(self, item_id: str, count: int) -> list[tuple[str, float]] | None:
        """The works nearest this one, or None when it has no numbers yet."""
        vector = self.index.vector(item_id)
        if vector is None:
            return None
        return [(i, s) for i, s in self.nearest(vector, count + 1) if i != item_id][:count]

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
        tidied = 0.0
        done = 0
        began = self.clock()
        while not self._stop.is_set():
            pause = BREATHE
            try:
                if self.busy():
                    pause = IN_USE
                else:
                    self.model.fetch()
                    if self.clock() - tidied > 86_400:
                        self.tidy()
                        tidied = self.clock()
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
                        pause = IDLE
            except Exception as err:
                self.trouble = str(err)
                log.exception("seen: a round failed")
                pause = REST
            self._stop.wait(pause)
            if pause == IDLE:
                began = self.clock()
