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
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic
from PIL import Image
from pydantic import BaseModel, Field

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
#: Beside a waiting photograph: the work Opus found in it.
FOUND = ".found.json"
#: A scan's file as :meth:`OwnWorks.merge` names it.
_SCAN_FILE = re.compile(r"^(first|side[1-9])\.jpg$")
#: The side the photograph is looked at for the work's corners and hints:
#: a JPEG is opened that much faster at an eighth of 48 MP.
LOOK_SIDE = 3000
#: Photographs from the side a first one may have (``-side1``, ``-side2``).
SIDES = 2
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


class Merged(Incoming):
    """The first photograph with its reflections taken out by the side
    ones: how many could be laid over it, and how much was taken (0–1: of
    the work's light where the work's corners were known, of the
    photograph's pixels where a lamp's glare alone was replaced)."""

    used: int = 0
    replaced: float = 0.0


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
        img.save(self.incoming / f"{token}.jpg", "JPEG", quality=INCOMING_QUALITY)
        return Incoming(token=token, width=img.width, height=img.height)

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

    def side(self, token: str, data: bytes) -> int:
        """Another photograph of the same work taken a little from the side
        (the scan of three, Mateusz 2026-11-16), kept with the first until
        :meth:`merge`. How many side photographs it has now."""
        self.path(token)
        taken = sorted(self.incoming.glob(f"{token}-side*.jpg"))
        if len(taken) >= SIDES:
            raise ValueError("enough side photographs")
        try:
            img = load_image(data).convert("RGB")
        except OSError as err:
            raise ValueError("no picture") from err
        img.thumbnail((INCOMING_SIDE, INCOMING_SIDE), Image.Resampling.LANCZOS)
        img.save(
            self.incoming / f"{token}-side{len(taken) + 1}.jpg", "JPEG", quality=INCOMING_QUALITY
        )
        return len(taken) + 1

    def merge(self, token: str, corners: Quad | None = None, outline: Quad | None = None) -> Merged:
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
        the reflections are taken out."""
        path = self.path(token)
        sides = sorted(self.incoming.glob(f"{token}-side*.jpg"))
        with Image.open(path) as img:
            seen = Merged(token=token, width=img.width, height=img.height)
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
        self._keep_scan(token, path, sides)
        seen.used, seen.replaced = self._merge(path, path, sides, quad)
        self._note_scan(token, seen)
        for side in sides:
            side.unlink(missing_ok=True)
        log.info(
            "own photograph %s: %d side(s) laid over, %.1f%% %s taken out",
            token,
            seen.used,
            seen.replaced * 100,
            "of the light" if quad is not None else "glare",
        )
        return seen

    @staticmethod
    def _merge(first: Path, into: Path, sides: list[Path], quad: Quad | None) -> tuple[int, float]:
        """``first`` merged with ``sides`` and written to ``into`` (when
        anything was taken out): how many were laid over, how much went."""
        import numpy as np

        from .imaging import glare, reflections

        def whole(path: Path, side: int | None = None) -> Any:
            with Image.open(path) as img:
                if side is not None:
                    img.draft("RGB", (side, side))
                return np.asarray(img.convert("RGB"))

        photo = whole(first)
        if quad is not None:
            # The side ones only say what is reflection: small is enough.
            clean = reflections.merge(
                photo, [whole(p, reflections.MATCH_SIDE) for p in sides], quad
            )
            used, taken, image = clean.used, clean.removed, clean.image
        else:
            patched = glare.merge(photo, [whole(p) for p in sides])
            used, taken, image = patched.used, patched.replaced, patched.image
        if taken > 0:
            Image.fromarray(image).save(into, "JPEG", quality=INCOMING_QUALITY)
        return used, round(taken, 4)

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
        used, taken = self._merge(folder / "first.jpg", self.path(token), sides, quad)
        info.update(corners=quad, used=used, replaced=taken, again=now_iso())
        (folder / SCAN_INFO).write_text(json.dumps(info))
        log.info("own photograph %s merged again within his corners", token)

    def _keep_scan(self, token: str, first: Path, sides: list[Path]) -> None:
        """The scan's photographs as they came, in a folder of their own."""
        folder = self.scans / token
        try:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(first, folder / "first.jpg")
            for n, side in enumerate(sides, start=1):
                shutil.copyfile(side, folder / f"side{n}.jpg")
        except OSError as err:
            log.warning("scan %s not kept: %s", token, err)

    def _note_scan(self, token: str, seen: Merged) -> None:
        """What the merge came to, beside the scan's photographs."""
        info = {
            "at": now_iso(),
            "used": seen.used,
            "replaced": seen.replaced,
            "width": seen.width,
            "height": seen.height,
            "corners": seen.corners,
        }
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
        with Image.open(path) as img:
            seen = Incoming(token=token, width=img.width, height=img.height)
            img.draft("RGB", (LOOK_SIDE, LOOK_SIDE))
            img.load()
            found = self.crops.home_corners(img)
        if found is not None:
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
        shape of his size (1.145.168) cut anew to it. How many were."""
        from .imaging.cut import cut_aspect
        from .library.models import PlaylistRules

        done = 0
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
        if done:
            log.info("own works cut to the shape of their size: %d", done)
        return done

    # -- the work ------------------------------------------------------------------

    def add(self, token: str, corners: Quad | None, by: str, shape: str, text: Description) -> Item:
        """The work in the catalogue: the photograph whole in ``full/``
        ("Pełny kadr"), its original cut to ``corners`` (``by`` "auto" when
        they are Opus's, "owner" when he set them), and what he wrote."""
        path = self.path(token)
        self._again(token, corners)
        item = self.importer.add_upload(
            path.read_bytes(),
            kind=ItemKind.OWN,
            title=text.title.strip(),
            artist=text.artist.strip(),
            description=text.description.strip(),
        )
        item = self._describe(item, text)
        item = self._cut(item, corners, by, shape)
        self._done(path)
        log.info("own work %s added", item.id)
        return item

    def describe(self, item: Item, text: Description) -> Item:
        """ "Edytuj opis": what the owner wrote, again; a work cut out of
        his photograph is cut anew to a new size's shape."""
        self._check(item)
        before = (item.own.height_cm, item.own.width_cm) if item.own is not None else (None, None)
        updated = self._describe(item, text)
        if before != (text.height_cm, text.width_cm) and updated.cut_shown() is not None:
            updated = self.crops.apply(updated, updated.cut)
        return updated

    def retake(self, item: Item, token: str, corners: Quad | None, by: str, shape: str) -> Item:
        """ "Zrób zdjęcie ponownie": a new photograph of the same work (one
        without the lamp's reflection), cut anew; what he wrote stays."""
        self._check(item)
        path = self.path(token)
        self._again(token, corners)
        self.images.remove(item)
        width, height = self.images.store(item, path.read_bytes(), master=True)
        stored = self.library.update(item.id, width=width, height=height, cut=None) or item
        stored = self._cut(stored, corners, by, shape)
        self._done(path)
        return stored

    @staticmethod
    def _done(path: Path) -> None:
        """The waiting photograph and what was found in it, gone."""
        path.unlink(missing_ok=True)
        path.with_suffix(FOUND).unlink(missing_ok=True)

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

    def _cut(self, item: Item, corners: Quad | None, by: str, shape: str) -> Item:
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
        )
        return self.crops.apply(item, cut)


__all__ = ["Description", "Hints", "Incoming", "Merged", "OwnWorks"]
