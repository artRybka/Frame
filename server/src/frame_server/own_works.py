"""Works of the owner's own in the catalogue ("Dodaj własne dzieło",
Mateusz 2026-11-15): a photograph taken with the phone (or from its
library), the work found in it and cut out of its frame and mount as a
museum's photograph is (:meth:`..ai.crops.Crops.home_corners`), a few lines
read off the picture to start the description with (:meth:`OwnWorks.hints`),
and what the owner wrote: author, date, technique, size, where it hangs,
where it came from, a note.

The photograph is sent first and waits in ``incoming/`` (a day at most)
while the owner looks at the cut and writes; the work joins the catalogue
only when he adds it. Shown, studied and searched like any other work (its
picture goes to Google for "Szukaj zdjęciem" too, Mateusz 2026-11-15)."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import re
import secrets
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic
from PIL import Image
from pydantic import BaseModel, Field

from . import build_version
from .ai.client import SONNET, AiUnavailable, request
from .ai.crops import _block
from .imaging.cut import Quad, valid, warp
from .imaging.layout import load_image
from .library import Item, ItemKind
from .library.dates import text_year
from .library.images import OWN_MAX
from .library.models import Cut, Note, OwnWork
from .library.repo import now_iso

if TYPE_CHECKING:
    from .ai.client import Claude
    from .ai.crops import Crops
    from .imaging.colorchecker import Chart
    from .library import Library
    from .library.images import ImageCache
    from .library.importer import Importer
    from .sizes import Sizes

log = logging.getLogger(__name__)

#: How long a photograph waits for the owner to add its work.
KEEP_SECONDS = 24 * 3600
#: The longest side a photograph is kept with while it waits: the phone's
#: 48 MP whole (8064 × 6048), which the work is cut out of and kept at
#: (Mateusz 2026-11-16: "zdecydowanie wyższą jakość niż 4000px").
INCOMING_SIDE = OWN_MAX
#: How good its JPEG is: it is opened and saved once more on the way.
INCOMING_QUALITY = 95
#: How long the photographs of a scan (the first as it came and its side
#: ones) are kept after they were made one, for the merging to be tuned on
#: (Mateusz 2026-11-16: "Tak, przez 14 dni").
SCANS_SECONDS = 14 * 24 * 3600
#: What a scan's folder holds besides its photographs.
SCAN_INFO = "scan.json"
#: Goes up by one whenever what the merging (:func:`.imaging.reflections.
#: merge`, :func:`.imaging.glare.merge`) makes of the same photographs
#: changes. His works scanned before are then made once more of their
#: scans' photographs after the update (:meth:`OwnWorks.scanned_again`;
#: Mateusz 2026-11-17 09:30 UTC: "a może być po aktualizacji która
#: zmieniła sposób łączenia zdjęć?"). A scan that noted none was made
#: before 1.145.217 (what 1.145.216 does with a lamp's edge is 1; side
#: views settled on the first place by place, 1.145.220, is 2). The scan
#: made also of a relief for him to choose (1.145.229) changes nothing of
#: scans made before it: they note no ``doubt`` and stay as they were.
#: The side photographs' light told by the steps they share with the
#: first, a work behind glass with the room all over one of them no
#: longer in doubt, a lamp taken out to the frame, what is put in under
#: it as fine as the side photographs have it, and the tone under a veil
#: in the glass what the side views show (1.145.244) is 3.
MERGING = 3
#: A work's photograph is a kept scan's when the fine of the two, small
#: and grey, goes together at least this much (1 is the same picture). Of
#: his first twelve scans the first photograph and what was made of it
#: went together 0.82 (his drawing, a lamp taken out of it) to 0.99, and
#: two scans of one work 0.18 at the most: held by hand, no two have the
#: work's lines in the same pixels. All of the picture's light, not its
#: fine alone, told them apart no better than 0.75 from 0.86.
SCAN_LIKE = 0.6
#: So small (pixels a side), the fine being what a blur so wide (pixels
#: of that) takes away, and of shapes no further apart than this.
SCAN_LOOK = 128
SCAN_FINE = 2
SCAN_SHAPE = 0.02
#: Beside a waiting photograph: the work Opus found in it.
FOUND = ".found.json"
#: Beside a waiting photograph: the colour chart found in it and the way
#: back to true colours it gave (:mod:`.imaging.colorchecker`).
CHART = ".chart.json"
#: Beside a waiting photograph: from how far to the side each of its side
#: ones was taken, where the phone said (their numbers to degrees;
#: negative: from the work's left).
ANGLES = ".sides.json"
#: Beside a waiting photograph: what it says took it (the camera, its
#: lens), where it says so (:mod:`.imaging.lens`): the work added from it
#: is kept without that lens's bend.
LENS = ".lens.json"
#: A scan's file as :meth:`OwnWorks.merge` names it: the first photograph,
#: the side ones the scan was made of, and those taken besides.
_SCAN_FILE = re.compile(r"^(first|side[1-9]|more[1-9])\.jpg$")
#: The side the photograph is looked at for the work's corners and hints:
#: a JPEG is opened that much faster at an eighth of 48 MP.
LOOK_SIDE = 3000
#: Photographs from the side a first one may have (``-side1``…). The scan
#: is made of one from each side; walking round the work in one arc the
#: phone takes a few more on the way (Mateusz 2026-11-18: "może kolejne
#: zdjęcia nie muszą być dokładnie pod 30° i trzeba pozwolić na więcej
#: skanów pod różnymi kątami?"), kept to learn from what angle is enough.
SIDES = 6
#: How far to the side (degrees) the photographs the merging was tuned on
#: were taken: of those from one side, the nearest to it is the one used.
SIDE_ANGLE = 30.0
_SIDE_NUMBER = re.compile(r"-side(\d+)\.jpg$")
#: A token as :meth:`OwnWorks.take` makes it.
_TOKEN = re.compile(r"^[0-9a-f]{24}$")
#: The side the picture is read at for the hints.
HINT_SIDE = 1400
#: The notes' kind of the hints, for the AI's spending.
HINTS = "own_hints"

TECHNIQUES = (
    "oil", "acrylic", "watercolour", "gouache", "tempera", "pastel", "pencil", "charcoal",
    "ink", "lithograph", "etching", "woodcut", "linocut", "screenprint", "photograph",
    "mixed", "unknown",
)  # fmt: skip
SUPPORTS = ("canvas", "paper", "board", "panel", "unknown")

HINT_TEXT = """This is a photograph of an artwork its owner keeps at home (cut out of its frame). \
Read off it what would help describe it in a home catalogue, in Polish where words are \
asked for:
- "signature": the signature, monogram or inscription exactly as written (with its date, \
if any), "" if none can be read;
- "artist": the artist's name as the signature gives it, "" if none;
- "date": the year or period it was most likely made, from a dated signature first, else \
from its look ("ok. 1965", "lata 30. XX w.", "XIX w."), "" if you cannot tell;
- "technique" and "support": what it is made with and on;
- "title": a short plain Polish title for what it shows ("Pejzaż morski z klifem", \
"Portret kobiety w niebieskiej sukni"), never invented names;
- "sure": true only if the signature is clearly legible.
Answer in JSON only."""
HINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["signature", "artist", "date", "technique", "support", "title", "sure"],
    "properties": {
        "signature": {"type": "string"},
        "artist": {"type": "string"},
        "date": {"type": "string"},
        "technique": {"type": "string", "enum": list(TECHNIQUES)},
        "support": {"type": "string", "enum": list(SUPPORTS)},
        "title": {"type": "string"},
        "sure": {"type": "boolean"},
    },
}


class Incoming(BaseModel):
    """A photograph waiting for its work to be added: its ``token``, its
    size, and the work found in it (``corners`` on the photograph, 0–1
    across and down; None when none was found or it was not asked)."""

    token: str
    width: int
    height: int
    corners: Quad | None = None
    #: The work's outline as Opus saw it ("rectangle", "round",
    #: "irregular"; "" when not asked): only a rectangle is cut.
    shape: str = ""
    #: The colour chart photographed beside the work (its corners), by
    #: which the photograph's colours were set; None when there was none.
    chart: Quad | None = None
    #: The outer edge of the work's frame or passe-partout in the
    #: photograph, and which ("frame", "mount"), as Opus saw it with the
    #: corners: the card's "W ramie" (``Cut.surround``).
    surround: Quad | None = None
    surround_kind: str = ""
    #: Whether Opus answered (``surround`` asked).
    looked: bool = False


class Merged(Incoming):
    """The first photograph with its reflections taken out by the side
    ones: how many could be laid over it, and how much was taken (0–1: of
    the work's light where the work's corners were known, of the
    photograph's pixels where a lamp's glare alone was replaced).

    He has the two to choose between whenever a side one was laid over it
    (Mateusz 2026-11-17 22:43 UTC: "wybór pomiędzy obrazem składanym
    (inteligentnym) a z pojedynczego zdjęcia - zawsze go dawaj, a w
    sytuacji gdzie podejrzewasz płaskorzeźbę albo dzieło które wymaga
    pojedynczego zdjęcia ustawiaj je jako domyślne"): where the
    photographs do not show one flat work in one light the scan is made
    of them all the same, and ``doubt`` says the photograph from the front
    is the one proposed (where the phone gives the choice: an app before
    1.145.229 gets such a scan untouched, as it did)."""

    used: int = 0
    replaced: float = 0.0
    doubt: bool = False


class Hints(BaseModel):
    """What was read off the picture, for the description's chips."""

    signature: str = ""
    artist: str = ""
    date: str = ""
    technique: str = ""
    support: str = ""
    title: str = ""
    sure: bool = False


class Description(BaseModel):
    """What the owner wrote about the work ("Własne dzieło"'s fields)."""

    title: str = Field("", max_length=300)
    artist: str = Field("", max_length=200)
    date_text: str = Field("", max_length=80)
    #: Technique and support as one line ("olej na płótnie").
    medium: str = Field("", max_length=200)
    #: His note ("O dziele").
    description: str = Field("", max_length=4000)
    hangs: str = Field("", max_length=120)
    origin: str = Field("", max_length=300)
    height_cm: float | None = Field(None, gt=0, lt=10000)
    width_cm: float | None = Field(None, gt=0, lt=10000)


def _look(path: Path, k1: float | None = None) -> tuple[Any, float]:
    """The fine of a photograph small and grey (:data:`SCAN_LOOK` a side,
    without what :data:`SCAN_FINE` blurs away, its mean taken off, its
    length 1), and its width over its height. ``k1``: looked at without
    its lens's bend (:func:`.imaging.lens.straight`), as the work made of
    it is kept."""
    import numpy as np
    from PIL import ImageFilter, ImageOps

    from .imaging import lens

    with Image.open(path) as img:
        img.draft("L", (SCAN_LOOK * 4, SCAN_LOOK * 4))
        upright = ImageOps.exif_transpose(img.convert("L"))
        if k1:
            upright = Image.fromarray(lens.straight(np.asarray(upright), k1))
        shape = upright.width / upright.height
        small = upright.resize((SCAN_LOOK, SCAN_LOOK), Image.Resampling.BOX)
        coarse = small.filter(ImageFilter.GaussianBlur(SCAN_FINE))
        fine = np.asarray(small, float) - np.asarray(coarse, float)
    fine = fine - fine.mean()
    return fine / max(float(np.linalg.norm(fine)), 1e-6), shape


def _alike(one: tuple[Any, float], other: tuple[Any, float]) -> float:
    """How much two photographs (:func:`_look`) go together, -1 to 1;
    nothing when they are of another shape."""
    if abs(one[1] / other[1] - 1) > SCAN_SHAPE:
        return 0.0
    return float((one[0] * other[0]).sum())


class OwnWorks:
    def __init__(
        self,
        library: Library,
        images: ImageCache,
        importer: Importer,
        crops: Crops,
        sizes: Sizes,
        claude: Claude,
    ) -> None:
        self.library = library
        self.images = images
        self.importer = importer
        self.crops = crops
        self.sizes = sizes
        self.claude = claude
        self.incoming = images.images.parent / "incoming"
        self.incoming.mkdir(parents=True, exist_ok=True)
        #: The photographs of his scans, a folder each, for two weeks.
        self.scans = images.images.parent / "scans"

    # -- the photograph waiting -----------------------------------------------------

    def path(self, token: str) -> Path:
        if not _TOKEN.match(token):
            raise LookupError("no such photograph")
        path = self.incoming / f"{token}.jpg"
        if not path.is_file():
            raise LookupError("the photograph is no longer here")
        return path

    def take(self, data: bytes) -> Incoming:
        """The photograph kept while the owner looks at its cut (turned as
        the camera held it). Raises ValueError for what is no picture."""
        self.prune()
        try:
            img = load_image(data).convert("RGB")
        except OSError as err:
            raise ValueError("no picture") from err
        img.thumbnail((INCOMING_SIDE, INCOMING_SIDE), Image.Resampling.LANCZOS)
        token = secrets.token_hex(12)
        path = self.incoming / f"{token}.jpg"
        self._note_lens(token, path, data)
        chart = self._chart(img)
        if chart is not None:
            img = self._true(img, chart)
            path.with_suffix(CHART).write_text(json.dumps(chart.to_json()))
            log.info(
                "own photograph %s: colours set by its chart (off %.3f, now %.3f)",
                token,
                chart.off,
                chart.left,
            )
        img.save(path, "JPEG", quality=INCOMING_QUALITY)
        return Incoming(
            token=token,
            width=img.width,
            height=img.height,
            chart=list(chart.corners) if chart is not None else None,
        )

    @staticmethod
    def _note_lens(token: str, path: Path, data: bytes) -> None:
        """What the photograph says took it, beside it while it waits
        (Mateusz 2026-11-18 22:28 UTC, a frame's straight sides bowed:
        "Zakrzywienie obiektywu iPhone? Jakieś możliwości prostowania czy
        to bardzo skomplikowane?"). The photograph waits as it was taken,
        for the corners he sets on his phone's own copy of it to be the
        same; the work added from it has the bend taken out."""
        from .imaging import lens

        seen = lens.seen(data)
        if seen is None:
            return
        with contextlib.suppress(OSError):
            path.with_suffix(LENS).write_text(json.dumps(seen.to_json()))
        log.info(
            "own photograph %s: taken by %s (%s, %g mm): %s",
            token,
            seen.model,
            seen.lens or "its lens not said",
            seen.film,
            "its lens's bend not known, the work kept as taken"
            if seen.bend is None
            else f"the work kept without its lens's bend ({seen.bend:+.4f})",
        )

    def _lens(self, token: str) -> dict[str, Any] | None:
        """What the waiting photograph said took it (:meth:`_note_lens`)."""
        try:
            noted = json.loads(self.path(token).with_suffix(LENS).read_text())
        except (OSError, ValueError, LookupError):
            return None
        return noted if isinstance(noted, dict) else None

    @staticmethod
    def _bend(info: dict[str, Any]) -> float | None:
        """The bend of the lens a scan's photographs were taken with, from
        what the scan noted (``info``): what its camera said of itself;
        a scan from before one noted that (to 1.145.248) was taken with
        his phone's main camera by the app, when its first photograph is
        the sensor's whole. None: not known, the work stays as taken."""
        from .imaging import lens

        if "lens" in info:
            noted = info["lens"]
            if not isinstance(noted, dict) or not noted.get("main"):
                return None
            return lens.BENDS.get(str(noted.get("model") or ""))
        try:
            size = int(info.get("width") or 0), int(info.get("height") or 0)
        except (TypeError, ValueError):
            return None
        return lens.BENDS.get(lens.PHONE) if lens.whole(*size) else None

    @staticmethod
    def _unbent(cut: Cut, size: tuple[int, int], k1: float) -> Cut:
        """``cut``, set on the photograph as taken (``size``), on it
        straightened."""
        from .imaging import lens

        def at(quad: Quad | None) -> Quad | None:
            return lens.moved(quad, *size, k1) if quad else quad

        return cut.model_copy(
            update={
                "work": at(cut.work),
                "plate": at(cut.plate),
                "undone": at(cut.undone),
                "surround": at(cut.surround),
            }
        )

    @staticmethod
    def _chart(img: Image.Image) -> Chart | None:
        """A ColorChecker photographed beside the work (Mateusz 2026-11-16
        22:25 UTC: "dodajmy obsługę. Oczywiście nie jako obowiązkową, ale
        opcjonalna"), with the way back to true colours it gives."""
        import numpy as np

        from .imaging import colorchecker

        try:
            return colorchecker.find(np.asarray(img))
        except (ValueError, ArithmeticError) as err:  # numpy's LinAlgError is a ValueError
            log.warning("colour chart not read: %s", err)
            return None

    @staticmethod
    def _true(img: Image.Image, chart: Chart) -> Image.Image:
        """``img`` in the colours its chart gives it."""
        import numpy as np

        from .imaging import colorchecker

        return Image.fromarray(colorchecker.apply(np.asarray(img), chart))

    def _charted(self, token: str) -> Chart | None:
        """The chart found in the waiting photograph, if one was."""
        from .imaging.colorchecker import Chart

        try:
            return Chart.from_json(json.loads(self.path(token).with_suffix(CHART).read_text()))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def shown(self, token: str, side: int | None = None) -> Path | bytes:
        """The photograph as it waits, for the phone to set the corners
        on: the file itself, or a copy no longer than ``side``."""
        path = self.path(token)
        if side is None:
            return path
        with Image.open(path) as img:
            if max(img.size) <= side:
                return path
            img.draft("RGB", (side, side))
            small = img.convert("RGB")
        small.thumbnail((side, side), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        small.save(out, "JPEG", quality=90)
        return out.getvalue()

    def side(self, token: str, data: bytes, angle: float | None = None) -> int:
        """Another photograph of the same work taken a little from the side
        (the scan of three, Mateusz 2026-11-16), kept with the first until
        :meth:`merge`. How many side photographs it has now. ``angle``:
        from how far to the side the phone says it was taken (degrees;
        negative: from the work's left)."""
        path = self.path(token)
        taken = sorted(self.incoming.glob(f"{token}-side*.jpg"))
        if len(taken) >= SIDES:
            raise ValueError("enough side photographs")
        try:
            img = load_image(data).convert("RGB")
        except OSError as err:
            raise ValueError("no picture") from err
        img.thumbnail((INCOMING_SIDE, INCOMING_SIDE), Image.Resampling.LANCZOS)
        # In the first one's colours: its chart is in the same light.
        chart = self._charted(token)
        if chart is not None:
            img = self._true(img, chart)
        img.save(
            self.incoming / f"{token}-side{len(taken) + 1}.jpg", "JPEG", quality=INCOMING_QUALITY
        )
        if angle is not None:
            angles = self._angles(token)
            angles[len(taken) + 1] = round(angle, 1)
            path.with_suffix(ANGLES).write_text(json.dumps(angles))
        return len(taken) + 1

    def _angles(self, token: str) -> dict[int, float]:
        """From how far to the side each side photograph was taken, by its
        number, where the phone said."""
        try:
            noted = json.loads(self.path(token).with_suffix(ANGLES).read_text())
            return {int(n): float(angle) for n, angle in noted.items()}
        except (OSError, ValueError, AttributeError):
            return {}

    @staticmethod
    def chosen(sides: list[Path], angles: dict[int, float]) -> tuple[list[Path], list[Path]]:
        """The side photographs the scan is made of, and the others. The
        merging was tuned on one from each side, some 30° off: with the
        phone saying where each was taken, the one nearest
        :data:`SIDE_ANGLE` of those from the left and of those from the
        right. All of them where the phone did not say (an app before the
        one arc took just the two)."""
        best: dict[bool, tuple[float, Path]] = {}
        for side in sides:
            number = _SIDE_NUMBER.search(side.name)
            angle = angles.get(int(number.group(1))) if number else None
            if angle is None:
                return sides, []
            left, off = angle < 0, abs(abs(angle) - SIDE_ANGLE)
            if left not in best or off < best[left][0]:
                best[left] = (off, side)
        used = {side for _, side in best.values()}
        return [s for s in sides if s in used], [s for s in sides if s not in used]

    def merge(
        self,
        token: str,
        corners: Quad | None = None,
        outline: Quad | None = None,
        choice: bool = False,
        trace: dict[str, float] | None = None,
    ) -> Merged:
        """The first photograph without the reflections its side ones do
        not share, kept in its place. Within the work's ``corners`` (the
        phone's; else Opus is asked, and :meth:`find` answers the same
        after) the veil over the glass and what is mirrored in it go
        (:mod:`.imaging.reflections`); with no corners only a lamp's glare
        is replaced (:mod:`.imaging.glare`). Unchanged when no side one
        could be laid over it. The photographs as they came are kept two
        weeks in ``scans/`` (:data:`SCANS_SECONDS`).

        ``outline`` is the rectangle the phone's camera followed while the
        first photograph was taken (Mateusz 2026-11-16: "kadrowanie -
        rozumiem że teraz robi je model? czy to potrzebne skoro mamy już
        dane z iPhone?"). It is the largest rectangle there, most often
        the frame's outer edge, so Opus is still asked for the work within
        the frame and the mount; where Opus has no answer (no key, or it
        found none: three of his first five scans) the outline is where
        the reflections are taken out.

        ``choice``: the phone shows him the scan and the first photograph
        to choose between. The scan is then made also of photographs that
        show no one flat work, and ``doubt`` proposes the first one.

        ``trace``: what the phone noted of the scan as it was taken (when
        its marks came, how fast it turned at each photograph), kept
        beside the photographs for the camera to be tuned on."""
        path = self.path(token)
        angles = self._angles(token)
        sides, more = self.chosen(sorted(self.incoming.glob(f"{token}-side*.jpg")), angles)
        with Image.open(path) as img:
            seen = Merged(token=token, width=img.width, height=img.height)
        chart = self._charted(token)
        if chart is not None:
            seen.chart = list(chart.corners)
        if not sides:
            return seen
        quad = valid(corners) if corners is not None else None
        if quad is None:
            try:
                found = self.find(token)
            except (AiUnavailable, anthropic.APIError) as err:
                log.info("own photograph %s: the work not looked for: %s", token, err)
                found = None
            if found is not None:
                quad, seen.shape = found.corners, found.shape
            if quad is None and outline is not None:
                quad = valid(outline)
        seen.corners = quad
        kept = self._keep_scan(token, path, sides, more)
        # Made even of a relief when he chooses, the one photograph proposed.
        seen.used, seen.replaced, seen.doubt = self._merge(path, path, sides, quad, choice)

        def at(side: Path) -> float | None:
            number = _SIDE_NUMBER.search(side.name)
            return angles.get(int(number.group(1))) if number else None

        self._note_scan(token, seen, {name: at(side) for name, side in kept.items()}, trace)
        for side in [*sides, *more]:
            side.unlink(missing_ok=True)
        path.with_suffix(ANGLES).unlink(missing_ok=True)
        where = ", ".join("?" if at(s) is None else f"{at(s):+.0f}" for s in kept.values())
        log.info(
            "own photograph %s: %d side(s) laid over%s, %.1f%% %s taken out%s",
            token,
            seen.used,
            f" (of {len(kept)}, from {where}°)" if angles else "",
            seen.replaced * 100,
            "of the light" if quad is not None else "glare",
            ", not one flat work: the one photograph proposed" if seen.doubt else "",
        )
        if trace:
            log.info(
                "own photograph %s: the phone's scan: %s",
                token,
                ", ".join(f"{key} {value:g}" for key, value in sorted(trace.items())),
            )
        return seen

    @staticmethod
    def _merge(
        first: Path, into: Path, sides: list[Path], quad: Quad | None, anyway: bool = False
    ) -> tuple[int, float, bool]:
        """``first`` merged with ``sides`` and written to ``into`` (when
        anything was taken out): how many were laid over, how much went,
        and whether the photographs show no one flat work (in doubt: then
        nothing is taken out unless asked for ``anyway``)."""
        import os

        import numpy as np

        from .imaging import bands, glare, reflections

        def whole(path: Path, side: int | None = None) -> Any:
            with Image.open(path) as img:
                if side is not None:
                    img.draft("RGB", (side, side))
                return np.asarray(img.convert("RGB"))

        began = time.perf_counter()
        # The side ones only say what is reflection: small is enough. All
        # are read at a time: each is a file of its own.
        small = reflections.MATCH_SIDE if quad is not None else None
        photo, *others = bands.pool.map(
            lambda read: whole(*read), [(first, None), *((p, small) for p in sides)]
        )
        read = time.perf_counter()
        if quad is not None:
            clean = reflections.merge(photo, others, quad, anyway)
            used, taken, image, doubt = clean.used, clean.removed, clean.image, clean.doubt
            parts = ", ".join(f"{part} {seconds:.1f}" for part, seconds in clean.took.items())
        else:
            patched = glare.merge(photo, others)
            used, taken, image, doubt = patched.used, patched.replaced, patched.image, False
            parts = "a glare only"
        merged = time.perf_counter()
        if taken > 0:
            Image.fromarray(image).save(into, "JPEG", quality=INCOMING_QUALITY)
        done = time.perf_counter()
        # What a scan's time goes on is told from his own scans (Mateusz
        # 2026-11-18 23:34 UTC: "przyspieszyć składanie obrazów - teraz
        # trwa to zdecydowanie za długo").
        log.info(
            "own photograph %s: merged in %.1f s on %d core(s) with %.1f GB to spare: "
            "read %.1f, %s, written %.1f",
            into.stem,
            done - began,
            os.cpu_count() or 1,
            reflections.spare(),
            read - began,
            parts or "nothing laid",
            done - merged,
        )
        return used, round(taken, 4), doubt

    def single(self, token: str) -> None:
        """The first photograph as it came, back in the scan's place
        (Mateusz 2026-11-16 19:00 UTC, a collage with a mirror and a
        circuit board in relief: "daj możliwość wyboru zdjęcia bez korekty
        usunięcia odbić, tj. „Jedno zdjęcie” - bywa że to lepsze
        rozwiązanie"). The work is then added from that photograph, and
        nothing merges the scan's again."""
        path = self.path(token)
        folder = self.scans / token
        first = folder / "first.jpg"
        if not first.is_file():
            raise LookupError("no scan of this photograph is kept")
        shutil.copyfile(first, path)
        try:
            info = json.loads((folder / SCAN_INFO).read_text())
            info["single"] = now_iso()
            (folder / SCAN_INFO).write_text(json.dumps(info))
        except (OSError, ValueError) as err:
            log.warning("scan %s not noted: %s", token, err)
        log.info("own photograph %s: the one photograph kept, not the scan", token)

    def _again(self, token: str, corners: Quad | None) -> None:
        """Before the work is added: the corners he set reach beyond what
        was cleaned around the ones the merge had, so the scan's
        photographs are merged once more within his."""
        import cv2
        import numpy as np

        from .imaging.reflections import grown

        folder = self.scans / token
        quad = valid(corners) if corners is not None else None
        try:
            info = json.loads((folder / SCAN_INFO).read_text())
        except (OSError, ValueError):
            return
        had = valid(info.get("corners") or [])
        sides = sorted(folder.glob("side*.jpg"))
        # He chose the one photograph over the scan (:meth:`single`).
        if quad is None or had is None or not sides or info.get("single"):
            return
        cleaned = grown(had).astype(np.float32)
        if all(cv2.pointPolygonTest(cleaned, (x, y), False) >= 0 for x, y in quad):
            return
        # A scan in doubt he went on with all the same is made as he saw it.
        used, taken, _ = self._merge(
            folder / "first.jpg", self.path(token), sides, quad, bool(info.get("doubt"))
        )
        info.update(corners=quad, used=used, replaced=taken, again=now_iso(), merging=MERGING)
        (folder / SCAN_INFO).write_text(json.dumps(info))
        log.info("own photograph %s merged again within his corners", token)

    def _keep_scan(
        self, token: str, first: Path, sides: list[Path], more: list[Path] | None = None
    ) -> dict[str, Path]:
        """The scan's photographs as they came, in a folder of their own:
        the side ones the scan is made of (``side1.jpg``…, which is what
        it is made of again) and those taken besides (``more1.jpg``…).
        Which of them became which file there."""
        folder = self.scans / token
        kept: dict[str, Path] = {}
        try:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(first, folder / "first.jpg")
            for name, photos in (("side", sides), ("more", more or [])):
                for n, side in enumerate(photos, start=1):
                    shutil.copyfile(side, folder / f"{name}{n}.jpg")
                    kept[f"{name}{n}.jpg"] = side
        except OSError as err:
            log.warning("scan %s not kept: %s", token, err)
        return kept

    def _note_scan(
        self,
        token: str,
        seen: Merged,
        angles: dict[str, float | None] | None = None,
        trace: dict[str, float] | None = None,
    ) -> None:
        """What the merge came to, beside the scan's photographs."""
        info: dict[str, Any] = {
            "at": now_iso(),
            # Which release made it one, and how photographs were merged
            # then: when that changes the work is made of them once more.
            "release": build_version(),
            "merging": MERGING,
            "used": seen.used,
            "replaced": seen.replaced,
            # Made of photographs that show no one flat work, for him to
            # choose: kept on (he did not take the one photograph, or
            # ``single`` would say so), it is made so again.
            "doubt": seen.doubt and seen.replaced > 0,
            "width": seen.width,
            "height": seen.height,
            "corners": seen.corners,
            # The photographs kept are in the chart's colours already.
            "chart": chart.to_json() if (chart := self._charted(token)) is not None else None,
            # How a chart was looked for: read otherwise by a later
            # release, one may be found that was none (:meth:`_chart_late`).
            "sought": self._reading(),
            # What the first photograph said took it (None: it named no
            # camera): the work is kept without that lens's bend, where
            # it is known (``straight``, noted when the work is added).
            "lens": self._lens(token),
        }
        if angles and any(angle is not None for angle in angles.values()):
            # From how far to the side each was taken, as the phone said.
            info["angles"] = angles
        if trace:
            info["trace"] = trace
        try:
            (self.scans / token / SCAN_INFO).write_text(json.dumps(info))
        except OSError as err:
            log.warning("scan %s not noted: %s", token, err)

    def kept_scans(self) -> list[dict[str, Any]]:
        """The scans kept, newest first: what :meth:`merge` noted of each
        and its files with their sizes."""
        found: list[dict[str, Any]] = []
        if not self.scans.is_dir():
            return found
        for folder in self.scans.iterdir():
            if not _TOKEN.match(folder.name) or not folder.is_dir():
                continue
            try:
                info = json.loads((folder / SCAN_INFO).read_text())
            except (OSError, ValueError):
                info = {}
            files = {
                p.name: p.stat().st_size
                for p in sorted(folder.iterdir())
                if _SCAN_FILE.match(p.name)
            }
            found.append({"token": folder.name, **info, "files": files})
        return sorted(found, key=lambda scan: str(scan.get("at", "")), reverse=True)

    def scan_file(self, token: str, name: str) -> Path:
        if not _TOKEN.match(token) or not _SCAN_FILE.match(name):
            raise LookupError("no such photograph")
        path = self.scans / token / name
        if not path.is_file():
            raise LookupError("the photograph is no longer here")
        return path

    def find(self, token: str) -> Incoming:
        """The work found in the photograph by Opus (``corners`` None when
        nothing was, or no key). Asked once of a photograph: :meth:`merge`
        asks first, and the phone after it."""
        path = self.path(token)
        known = path.with_suffix(FOUND)
        try:
            return Incoming.model_validate_json(known.read_text())
        except (OSError, ValueError):
            pass
        chart = self._charted(token)
        with Image.open(path) as img:
            seen = Incoming(
                token=token,
                width=img.width,
                height=img.height,
                chart=list(chart.corners) if chart is not None else None,
            )
            img.draft("RGB", (LOOK_SIDE, LOOK_SIDE))
            img.load()
            found = self.crops.home_corners(img)
        if found is not None:
            seen.looked = True
            seen.surround = found.get("surround")
            seen.surround_kind = str(found.get("surround_kind") or "") if seen.surround else ""
            seen.shape = str(found.get("shape") or "")
            if seen.shape == "rectangle" or not seen.shape:
                seen.corners = found["work"] or found["plate"]
        with contextlib.suppress(OSError):
            known.write_text(seen.model_dump_json())
        return seen

    def hints(self, token: str, corners: Quad | None = None) -> Hints:
        """Signature, date, technique and a plain title read off the work
        (Sonnet, about a grosz); an empty answer when it refused."""
        with Image.open(self.path(token)) as img:
            img.draft("RGB", (LOOK_SIDE, LOOK_SIDE))
            img.load()
            picture = warp(img.convert("RGB"), corners) if corners else img.convert("RGB")
        picture.thumbnail((HINT_SIDE, HINT_SIDE), Image.Resampling.LANCZOS)
        answer = self.claude.ask(
            HINTS,
            request(
                model=SONNET,
                system="You help describe artworks in a home catalogue.",
                content=[_block(picture), {"type": "text", "text": HINT_TEXT}],
                schema=HINT_SCHEMA,
                max_tokens=3000,
                effort="low",
            ),
        )
        if answer.refused or not answer.data:
            return Hints()
        return Hints.model_validate(
            {k: v for k, v in answer.data.items() if k in Hints.model_fields}
        )

    def prune(self) -> None:
        """Photographs whose work was never added, after a day; a scan's
        photographs after two weeks."""
        old = time.time() - KEEP_SECONDS
        for path in self.incoming.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < old:
                    path.unlink()
            except OSError:
                pass
        old = time.time() - SCANS_SECONDS
        if self.scans.is_dir():
            for folder in self.scans.iterdir():
                try:
                    if _TOKEN.match(folder.name) and folder.stat().st_mtime < old:
                        shutil.rmtree(folder, ignore_errors=True)
                except OSError:
                    pass

    def reshape(self) -> int:
        """Once after a start: works added before their pictures took the
        shape of his size (1.145.168) cut anew to it. How many were.

        And the frames about them ("W ramie") set before those took the
        work's shape (1.145.245) given it: the frame held the work in the
        photograph's shape, the card showed it in his size's, and the
        frame's photograph showed beside the work (Mateusz 2026-11-18
        21:44 UTC, "Out of the box": "Podwójny obraz po wyświetleniu
        ramy")."""
        from .ai.crops import framed
        from .imaging.cut import cut_aspect
        from .library.models import PlaylistRules

        done = frames = 0
        for item in self.library.query(PlaylistRules(kinds=[ItemKind.OWN]), include_excluded=True)[
            1
        ]:
            quad, cut = item.cut_shown(), item.cut
            if item.source != "upload" or item.own is None or quad is None or cut is None:
                continue
            ratio = item.own.ratio(cut_aspect(quad, cut.aspect))
            path = self.images.image_path(item)
            if ratio is None or not path.is_file():
                continue
            try:
                with Image.open(path) as img:
                    off = abs(img.width / img.height - ratio) / ratio
            except OSError:
                continue
            if off > 0.01:
                self.crops.apply(item, cut)
                done += 1
            elif cut.framed_kind:
                fresh = framed(cut, item.own.ratio)
                if (fresh.framed_aspect, fresh.framed_inner) != (
                    cut.framed_aspect,
                    cut.framed_inner,
                ):
                    self.library.update(item.id, cut=fresh)
                    frames += 1
        if done:
            log.info("own works cut to the shape of their size: %d", done)
        if frames:
            log.info("own works' frames given the shape of their size: %d", frames)
        return done

    # -- the work ------------------------------------------------------------------

    def add(
        self,
        token: str,
        corners: Quad | None,
        by: str,
        shape: str,
        text: Description,
        balance: float = 0.0,
    ) -> Item:
        """The work in the catalogue: the photograph whole in ``full/``
        ("Pełny kadr"), its original cut to ``corners`` (``by`` "auto" when
        they are Opus's, "owner" when he set them), and what he wrote.
        ``balance``: the white balance he set where no colour chart was
        beside the work (:mod:`.imaging.balance`; 0, as taken).

        Kept without its lens's bend where the photograph said what took
        it and that lens was measured (:mod:`.imaging.lens`): the corners,
        set on the photograph as taken, go with it."""
        path = self.path(token)
        self._again(token, corners)
        k1, straightened = self._straightening(token)
        item = self.importer.add_upload(
            self._finished(path, balance, k1),
            kind=ItemKind.OWN,
            title=text.title.strip(),
            artist=text.artist.strip(),
            description=text.description.strip(),
        )
        item = self._describe(item, text)
        item = self._cut(
            item, straightened(corners), by, shape, self._surround(token, straightened)
        )
        self._note_work(token, item, balance, k1)
        self._done(path)
        log.info("own work %s added", item.id)
        return item

    def _straightening(
        self, token: str
    ) -> tuple[float | None, Callable[[Quad | None], Quad | None]]:
        """The bend of the lens the waiting photograph was taken with
        (None: not known, or it did not say what took it), and what puts
        corners set on it as taken where they are on it straightened."""
        from .imaging import lens

        noted = self._lens(token)
        k1 = self._bend({"lens": noted}) if noted is not None else None
        if k1 is None:
            return None, lambda quad: quad
        with Image.open(self.path(token)) as img:
            size = img.size
        return k1, lambda quad: lens.moved(quad, *size, k1) if quad else quad

    @staticmethod
    def _finished(path: Path, balance: float, k1: float | None = None) -> bytes:
        """The photograph at ``path`` as the work keeps it: without its
        lens's bend (``k1``), in the white balance he set."""
        import numpy as np

        from .imaging import balance as white
        from .imaging import lens

        if abs(balance) < 1e-3 and not k1:
            return path.read_bytes()
        with Image.open(path) as img:
            photo = img.convert("RGB")
        if k1:
            photo = Image.fromarray(lens.straight(np.asarray(photo), k1))
        if abs(balance) >= 1e-3:
            photo = white.apply(photo, balance)
        out = io.BytesIO()
        photo.save(out, "JPEG", quality=INCOMING_QUALITY)
        return out.getvalue()

    def describe(self, item: Item, text: Description) -> Item:
        """ "Edytuj opis": what the owner wrote, again; a work cut out of
        his photograph is cut anew to a new size's shape."""
        self._check(item)
        before = (item.own.height_cm, item.own.width_cm) if item.own is not None else (None, None)
        updated = self._describe(item, text)
        if before != (text.height_cm, text.width_cm) and updated.cut_shown() is not None:
            updated = self.crops.apply(updated, updated.cut)
        return updated

    def retake(
        self,
        item: Item,
        token: str,
        corners: Quad | None,
        by: str,
        shape: str,
        balance: float = 0.0,
    ) -> Item:
        """ "Zrób zdjęcie ponownie": a new photograph of the same work (one
        without the lamp's reflection), cut anew; what he wrote stays."""
        self._check(item)
        path = self.path(token)
        self._again(token, corners)
        k1, straightened = self._straightening(token)
        self.images.remove(item)
        width, height = self.images.store(item, self._finished(path, balance, k1), master=True)
        stored = self.library.update(item.id, width=width, height=height, cut=None) or item
        stored = self._cut(
            stored, straightened(corners), by, shape, self._surround(token, straightened)
        )
        self._note_work(token, stored, balance, k1)
        self._done(path)
        return stored

    # -- the scan it was made of ----------------------------------------------------

    def _note_work(
        self,
        token: str,
        item: Item,
        balance: float | None = None,
        straight: float | None = None,
    ) -> None:
        """Which work a kept scan became, beside its photographs, the
        white balance he set for it (made again, it has the same), and
        the lens's bend taken out of it (``straight``: its corners are
        on the photograph straightened)."""
        note = self.scans / token / SCAN_INFO
        try:
            info = json.loads(note.read_text())
            info["item"] = item.id
            if balance is not None:
                info["balance"] = round(balance, 3)
            if straight is not None:
                info["straight"] = straight
            note.write_text(json.dumps(info))
        except (OSError, ValueError):
            pass  # no scan: one photograph, or it is gone

    def _noting(self, item: Item) -> tuple[dict[str, Any] | None, list[str]]:
        """The newest kept scan that noted the work, its photographs still
        here (the work was photographed last by it: an older scan of the
        same work is never what it is made of), and the scans that noted
        no work at all."""
        loose: list[str] = []
        for scan in self.kept_scans():
            files = scan.get("files", {})
            if "first.jpg" not in files or "side1.jpg" not in files:
                continue
            if scan.get("item") == item.id:
                return scan, loose
            if "item" not in scan and not scan.get("single"):
                loose.append(str(scan["token"]))
        return None, loose

    def scan_of(self, item: Item, looks: dict[str, tuple[Any, float]] | None = None) -> str | None:
        """The kept scan the work's photograph was made of (its token), if
        its photographs are still here: the newest that noted the work,
        unless he chose its one photograph over it (:meth:`single`).
        A work added before scans noted theirs (1.145.217) is the scan its
        photograph looks like, of those that noted none; and that is noted.
        ``looks``: what such scans look like, kept from one work to the next."""
        if item.kind != ItemKind.OWN or item.source != "upload":
            return None
        noted, loose = self._noting(item)
        if noted is not None:
            return None if noted.get("single") else str(noted["token"])
        if not loose:
            return None
        master = self.images.master_path(item)
        try:
            mine = _look(master if master.is_file() else self.images.museum_photo(item))
        except OSError:
            return None
        best, token = SCAN_LIKE, None
        looks = {} if looks is None else looks
        for candidate in loose:
            try:
                if candidate not in looks:
                    looks[candidate] = _look(self.scans / candidate / "first.jpg")
            except OSError:
                continue
            like = _alike(mine, looks[candidate])
            if like > best:
                best, token = like, candidate
        if token is not None:
            self._note_work(token, item)
            log.info("own work %s: its scan is %s (alike %.3f)", item.id, token, best)
        return token

    def scanned_again(self) -> int:
        """Once after a start: his works whose scans were made one before
        photographs were merged as they are now (:data:`MERGING`), made once
        more of the photographs kept. How many were.

        Asked whether earlier scans should be made again by a button on
        the work or by themselves after every update, he said (2026-11-17
        09:30 UTC): "a może być po aktualizacji która zmieniła sposób
        łączenia zdjęć?".

        So are the works whose photographs still have their lens's bend
        (2026-11-18 22:28 UTC: "Zakrzywienie obiektywu iPhone?"; told
        his scans of the last two weeks would be set straight by
        themselves), the one photograph he chose over a scan among them."""
        from .library.models import PlaylistRules

        if not self.scans.is_dir():
            return 0
        done = 0
        looks: dict[str, tuple[Any, float]] = {}
        for item in self.library.query(PlaylistRules(kinds=[ItemKind.OWN]), include_excluded=True)[
            1
        ]:
            try:
                token = self.scan_of(item, looks) or self._one_of(item)
                if token is None:
                    continue
                folder = self.scans / token
                info = json.loads((folder / SCAN_INFO).read_text())
                # The one photograph is not merged, however that is done.
                merged = bool(info.get("single")) or int(info.get("merging") or 0) >= MERGING
                late = self._chart_late(folder, info)
                bent = "straight" not in info and self._bend(info) is not None
                if merged and not late and not bent:
                    continue
                if not self._still(item, folder, info):
                    continue
                self.rescan(item)
                done += 1
            except (OSError, ValueError, LookupError) as err:
                log.warning("own work %s not scanned again: %s", item.id, err)
        # Scans that are no work's are not looked at again at every start.
        for scan in self.kept_scans():
            if "item" not in scan:
                note = self.scans / str(scan["token"]) / SCAN_INFO
                try:
                    info = json.loads(note.read_text())
                    info["item"] = ""
                    note.write_text(json.dumps(info))
                except (OSError, ValueError):
                    pass
        if done:
            log.info("own works scanned again as photographs are merged now: %d", done)
        return done

    def rescan(self, item: Item) -> Item:
        """The work's photograph made once more of its scan's photographs
        (Mateusz 2026-11-17 09:19 UTC, shown what 1.145.216 does with the
        lamp on his drawing: "Jest idealnie! Czy poprzednie skany przerobią
        się po wydaniu?"). What takes the reflections out gets better with
        a release, and a work scanned before it has what the scan came to
        then. Its cut and what he wrote stay.

        The one photograph he chose over a scan is that photograph again
        (in a chart's colours read since, without its lens's bend). The
        lens's bend goes where it is known (:meth:`_bend`), and the cut,
        set on the photograph as taken, goes to where the work is on it
        straightened, once."""
        self._check(item)
        token = self.scan_of(item) or self._one_of(item)
        if token is None:
            raise LookupError("no scan of this work is kept")
        folder = self.scans / token
        info = json.loads((folder / SCAN_INFO).read_text())
        self._chart_late(folder, info)
        self._relit(folder, info)
        quad = valid(info.get("corners") or [])
        k1 = self._bend(info)
        again = self.incoming / f"{token}-again.jpg"
        shutil.copyfile(folder / "first.jpg", again)
        try:
            used, taken = int(info.get("used") or 0), float(info.get("replaced") or 0.0)
            if not info.get("single"):
                # A scan from before he was given the choice notes no doubt,
                # and a relief among them stays the one photograph it was.
                used, taken, _ = self._merge(
                    folder / "first.jpg",
                    again,
                    sorted(folder.glob("side*.jpg")),
                    quad,
                    bool(info.get("doubt")),
                )
            data = self._finished(again, float(info.get("balance") or 0.0), k1)
            with Image.open(again) as img:
                size = img.size
        finally:
            again.unlink(missing_ok=True)
        cut = item.cut
        self.images.remove(item)
        width, height = self.images.store(item, data, master=True)
        stored = self.library.update(item.id, width=width, height=height) or item
        if k1 is not None and "straight" not in info:
            if cut is not None:
                # Set on the photograph as taken: where the work is now.
                cut = self._unbent(cut, size, k1)
                stored = self.library.update(item.id, cut=cut) or stored
            # Noted with the corners, before the pictures are made of
            # them: never moved twice.
            info["straight"] = k1
            (folder / SCAN_INFO).write_text(json.dumps(info))
            log.info("own work %s: its lens's bend (%+.4f) taken out", item.id, k1)
        if cut is not None and cut.shown() is not None:
            # The same corners: the photograph is the same one. Set anew,
            # for the app's pictures kept from before to be had again.
            stored = self.crops.apply(stored, cut.model_copy(update={"at": now_iso()}))
        else:
            self.images.recut(stored)
        info.update(
            used=used,
            replaced=taken,
            again=now_iso(),
            release=build_version(),
            merging=MERGING,
            item=item.id,
        )
        (folder / SCAN_INFO).write_text(json.dumps(info))
        log.info(
            "own work %s scanned again from %s: %d side(s), %.1f%% taken out",
            item.id,
            token,
            used,
            taken * 100,
        )
        return stored

    def _one_of(self, item: Item) -> str | None:
        """The kept scan whose one photograph from the front he chose for
        the work (:meth:`single`), if it is the last the work was
        photographed by and its photographs are still here."""
        if item.kind != ItemKind.OWN or item.source != "upload":
            return None
        noted, _ = self._noting(item)
        return str(noted["token"]) if noted is not None and noted.get("single") else None

    def _still(self, item: Item, folder: Path, info: dict[str, Any]) -> bool:
        """Whether the work's photograph is still the scan's. Photographed
        again by one photograph (no scan, nothing kept of it), the work
        would be made of the earlier scan again and that photograph lost:
        it is left as it is."""
        master = self.images.master_path(item)
        noted = info.get("straight")
        k1 = float(noted) if isinstance(noted, int | float) else None
        try:
            mine = _look(master if master.is_file() else self.images.museum_photo(item))
            alike = _alike(mine, _look(folder / "first.jpg", k1))
        except OSError as err:
            log.warning("own work %s: its scan not looked at: %s", item.id, err)
            return False
        if alike <= SCAN_LIKE:
            log.info(
                "own work %s: its photograph is no longer scan %s's (alike %.3f): left as it is",
                item.id,
                folder.name,
                alike,
            )
        return alike > SCAN_LIKE

    @staticmethod
    def _reading() -> int:
        from .imaging import colorchecker

        return colorchecker.READING

    def _chart_late(self, folder: Path, info: dict[str, Any]) -> bool:
        """A chart beside the work that was not read when the scan came,
        read now (Mateusz 2026-11-18 21:14 UTC, a chart on the frame in a
        dim room: "Dlaczego karta kolorów nie jest tu wykrywana?"; 21:20,
        one on a table under a lamp: "Podobny problem."; to 1.145.244 a
        chart whose black patch had no light, or whose white was at the
        photograph's top, was no chart). The scan's photographs are put
        in its colours, all of them or none, the chart is noted, and the
        white balance he may have set without it is let go. Looked for
        once for each way of reading a chart; whether one was read."""
        import numpy as np

        from .imaging import colorchecker

        if info.get("chart") or int(info.get("sought") or 0) >= colorchecker.READING:
            return False
        info["sought"] = colorchecker.READING
        chart: Chart | None = None
        try:
            with Image.open(folder / "first.jpg") as img:
                chart = self._chart(img.convert("RGB"))
            if chart is not None:
                put: list[tuple[Path, Path]] = []
                for path in sorted(folder.iterdir()):
                    if not _SCAN_FILE.match(path.name):
                        continue
                    with Image.open(path) as img:
                        seen = colorchecker.apply(np.asarray(img.convert("RGB")), chart)
                    into = path.with_suffix(".lit")
                    Image.fromarray(seen).save(into, "JPEG", quality=INCOMING_QUALITY)
                    put.append((into, path))
                for into, path in put:
                    into.replace(path)
                info["chart"] = chart.to_json()
                info["balance"] = 0.0
                log.info(
                    "scan %s: its chart read now, colours set by it (off %.3f, now %.3f)",
                    folder.name,
                    chart.off,
                    chart.left,
                )
            (folder / SCAN_INFO).write_text(json.dumps(info))
        except OSError as err:
            log.warning("scan %s: no chart looked for: %s", folder.name, err)
            return False
        return chart is not None

    @staticmethod
    def _relit(folder: Path, info: dict[str, Any]) -> None:
        """The scan's photographs, kept by an earlier release as their
        chart's patches truly are, lit as a chart lights them now (his
        first scan with a real chart, 2026-11-18 18:13 UTC: "Wyszło
        trochę blado i mdło"; 19:13: "Wyważone, pół na pół"). Once: the
        note says how they are lit."""
        import numpy as np

        from .imaging import colorchecker

        noted = info.get("chart")
        if not noted or int(noted.get("look") or 0) >= colorchecker.LOOK:
            return
        chart = colorchecker.Chart.from_json(noted)
        lit: list[tuple[Path, Path]] = []
        for path in sorted(folder.iterdir()):
            if not _SCAN_FILE.match(path.name):
                continue
            with Image.open(path) as img:
                seen = colorchecker.relit(np.asarray(img.convert("RGB")), chart)
            into = path.with_suffix(".lit")
            Image.fromarray(seen).save(into, "JPEG", quality=INCOMING_QUALITY)
            lit.append((into, path))
        # All of them or none: a photograph lit twice is no photograph.
        for into, path in lit:
            into.replace(path)
        noted["look"] = colorchecker.LOOK
        (folder / SCAN_INFO).write_text(json.dumps(info))
        log.info("scan %s: its photographs lit as a chart lights them now", folder.name)

    @staticmethod
    def _done(path: Path) -> None:
        """The waiting photograph and what was found in it, gone."""
        path.unlink(missing_ok=True)
        path.with_suffix(FOUND).unlink(missing_ok=True)
        path.with_suffix(CHART).unlink(missing_ok=True)
        path.with_suffix(LENS).unlink(missing_ok=True)

    @staticmethod
    def _check(item: Item) -> None:
        if item.kind != ItemKind.OWN or item.source != "upload":
            raise ValueError("not a work of the owner's own")

    def _describe(self, item: Item, text: Description) -> Item:
        date = text.date_text.strip()
        own = OwnWork(
            hangs=text.hangs.strip(),
            origin=text.origin.strip(),
            height_cm=text.height_cm,
            width_cm=text.width_cm,
        )
        updated = self.library.update(
            item.id,
            title=text.title.strip(),
            artist=text.artist.strip(),
            date_text=date,
            year=text_year(date),
            medium=text.medium.strip(),
            description=text.description.strip(),
            own=own,
        )
        self._size(item, own)
        return updated or item

    def _size(self, item: Item, own: OwnWork) -> None:
        """His size is the work's real size ("Rozmiar obrazu"), none if he
        wrote none: never looked up elsewhere."""
        from .sizes import KIND as SIZE
        from .sizes import VERSION

        data: dict[str, Any] = {}
        if own.height_cm and own.width_cm:
            data = {"height": own.height_cm, "width": own.width_cm}
        self.library.save_note(
            Note(item_id=item.id, kind=SIZE, model="", prompt_version=VERSION, data=data)
        )

    def _surround(
        self, token: str, straightened: Callable[[Quad | None], Quad | None] = lambda quad: quad
    ) -> dict[str, Any]:
        """The frame's edge Opus saw in the photograph (:meth:`find`), as
        :class:`Cut` keeps it (``straightened``: on the photograph without
        its lens's bend); nothing when he was not asked."""
        try:
            seen = Incoming.model_validate_json(self.path(token).with_suffix(FOUND).read_text())
        except (OSError, ValueError, LookupError):
            return {}
        if not seen.looked:
            return {}
        return {
            "surround": straightened(seen.surround),
            "surround_kind": seen.surround_kind if seen.surround else "",
            "surround_asked": True,
        }

    def _cut(
        self,
        item: Item,
        corners: Quad | None,
        by: str,
        shape: str,
        surround: dict[str, Any] | None = None,
    ) -> Item:
        quad = valid(corners) if corners is not None else None
        if quad is None:
            self.images.recut(item)  # whole: its tiles from all its pixels
            return item
        with Image.open(self.images.museum_photo(item, urgent=True)) as img:
            aspect = round(img.width / img.height, 5)
        cut = Cut(
            work=quad,
            aspect=aspect,
            picture=item.picture_key(),
            by="owner" if by == "owner" else "auto",
            shape=shape if shape in ("rectangle", "round", "irregular") else "",
            at=now_iso(),
            **(surround or {}),
        )
        return self.crops.apply(item, cut)


__all__ = ["Description", "Hints", "Incoming", "Merged", "OwnWorks"]
