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

import logging
import re
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image
from pydantic import BaseModel, Field

from .ai.client import SONNET, request
from .ai.crops import _block
from .imaging.cut import Quad, valid, warp
from .imaging.layout import load_image
from .library import Item, ItemKind
from .library.dates import text_year
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
#: The longest side a photograph is kept with while it waits (the phone
#: takes 48 MP, 8064 × 6048, Mateusz 2026-11-16; the work is cut out of it
#: at up to 4000 px, `originals-4k`).
INCOMING_SIDE = 6000
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
    """The first photograph with the glare taken out by the side ones:
    how many could be laid over it, and how much of it they gave (0–1)."""

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
        img.save(self.incoming / f"{token}.jpg", "JPEG", quality=93)
        return Incoming(token=token, width=img.width, height=img.height)

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
        img.save(self.incoming / f"{token}-side{len(taken) + 1}.jpg", "JPEG", quality=93)
        return len(taken) + 1

    def merge(self, token: str) -> Merged:
        """The first photograph without the reflections its side ones do
        not have (:mod:`.imaging.glare`); kept in its place, the side ones
        gone. Unchanged when none could be laid over it."""
        import numpy as np

        from .imaging.glare import merge

        path = self.path(token)
        sides = sorted(self.incoming.glob(f"{token}-side*.jpg"))
        with Image.open(path) as img:
            first = np.asarray(img.convert("RGB"))
        photos = []
        for side in sides:
            with Image.open(side) as img:
                photos.append(np.asarray(img.convert("RGB")))
        done = merge(first, photos)
        if done.replaced > 0:
            Image.fromarray(done.image).save(path, "JPEG", quality=93)
        for side in sides:
            side.unlink(missing_ok=True)
        log.info(
            "own photograph %s: %d side(s) laid over, %.1f%% glare taken out",
            token,
            done.used,
            done.replaced * 100,
        )
        h, w = first.shape[:2]
        return Merged(
            token=token, width=w, height=h, used=done.used, replaced=round(done.replaced, 4)
        )

    def find(self, token: str) -> Incoming:
        """The work found in the photograph by Opus (``corners`` None when
        nothing was, or no key)."""
        with Image.open(self.path(token)) as img:
            img.load()
            seen = Incoming(token=token, width=img.width, height=img.height)
            found = self.crops.home_corners(img)
        if found is not None:
            seen.shape = str(found.get("shape") or "")
            if seen.shape == "rectangle" or not seen.shape:
                seen.corners = found["work"] or found["plate"]
        return seen

    def hints(self, token: str, corners: Quad | None = None) -> Hints:
        """Signature, date, technique and a plain title read off the work
        (Sonnet, about a grosz); an empty answer when it refused."""
        with Image.open(self.path(token)) as img:
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
        """Photographs whose work was never added, after a day."""
        old = time.time() - KEEP_SECONDS
        for path in self.incoming.glob("*.jpg"):
            try:
                if path.stat().st_mtime < old:
                    path.unlink()
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
        item = self.importer.add_upload(
            path.read_bytes(),
            kind=ItemKind.OWN,
            title=text.title.strip(),
            artist=text.artist.strip(),
            description=text.description.strip(),
        )
        item = self._describe(item, text)
        item = self._cut(item, corners, by, shape)
        path.unlink(missing_ok=True)
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
        self.images.remove(item)
        width, height = self.images.store(item, path.read_bytes())
        stored = self.library.update(item.id, width=width, height=height, cut=None) or item
        stored = self._cut(stored, corners, by, shape)
        path.unlink(missing_ok=True)
        return stored

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
