"""Library data model shared by the database, the API and the importers."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from ..imaging.layout import Crop, Fit, mm
from . import memo
from .places import known_places, migrate_sources, source_place
from .viewer import OWNER_ID, VIEWER


class ItemKind(StrEnum):
    ARTWORK = "artwork"  # from a museum collection
    OWN = "own"  # own work / family art, uploaded with a description
    PHOTO = "photo"  # iCloud shared album or camera roll


class ColorSwatch(BaseModel):
    hex: str
    weight: float  # share of the picture
    #: A small, vivid colour (the Milkmaid's blue apron) listed after the
    #: dominant ones; its weight counts only the pixels that look like it.
    accent: bool = False


class Contour(BaseModel):
    """A picture's drawn contour (``library.contour``): the colour its lines
    are painted in, how much of them there is (their free length, in the
    picture's short sides) and how wide they are (% of the short side)."""

    hex: str
    length: float
    width: float


class PhotoInfo(BaseModel):
    taken_at: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    contributor: str | None = None
    caption: str | None = None
    #: iCloud: when the photo was added to the shared album.
    shared_at: str | None = None
    #: iCloud: checksum of the full-size picture, to ask for a fresh link
    #: (Apple's links expire) when the original is needed.
    asset: str | None = None
    #: A few Polish words for what the photo shows ("Montaż drewnianej
    #: ścianki"), written by the language model with its keywords: the
    #: photo's title while it has no caption of its own.
    title: str | None = None
    #: The place its coordinates name ("Kraków", "Rzym, Włochy"), looked up
    #: by the server (``places``); "" when nothing was found.
    place: str | None = None


class Look(BaseModel):
    """How a photo sent once from the camera roll ("Zdjęcie na ramkę") is
    shown, in place of the settings' presentation for photos: over the
    whole frame or in a passe-partout; the style is always automatic."""

    fit: Literal[Fit.FILL, Fit.FIT] = Fit.FILL
    mat: Literal["white", "cream", "grey", "black", "picture", "picture_dark"] = "white"
    margin: float = Field(mm(10), ge=0, le=0.3)


class Framing(BaseModel):
    """Corrections saved by the user for one orientation of the frame."""

    fill: Crop | None = None  # FILL: the part shown
    detail: Crop | None = None  # DESCRIPTION: its close-up
    picture: Crop | None = None  # DESCRIPTION: the part of the picture shown
    fit: Crop | None = None  # FIT: the part shown and the window's shape

    @model_validator(mode="before")
    @classmethod
    def _from_details(cls, data: Any) -> Any:
        """Older framings: of the retired two close-ups (DETAILS), the closer
        one becomes the description's close-up unless it has its own."""
        if not isinstance(data, dict) or "details" not in data:
            return data
        data = dict(data)
        details = data.pop("details")
        if data.get("detail") is None and isinstance(details, list) and len(details) == 2:
            data["detail"] = details[1]
        return data


#: Sources that are a museum's own collection: the work hangs where its
#: source says (``Item.museum``). The others gather pictures from many
#: collections, and their name says only where the picture is from.
COLLECTIONS = frozenset(
    {
        "aic",
        "cma",
        "met",
        "rijks",
        "smk",
        "nga",
        "mnw",
        "mnk",
        "yale",
        "si",
        "paris",
        "vam",
        "wellcome",
        "courtauld",
        "louvre",
        "loc",
        "getty",
    }
)

#: Europeana's providers that are art history photo archives, not
#: collections: they photographed the work where it hangs, so their name is
#: not its museum (``Item.held_by``; Mateusz 2026-11-09: van Gogh's still
#: life "in" the Marburg Picture Index). See ``vocabulary.is_art_archive_photo``.
ART_PHOTO_ARCHIVES = frozenset(
    {
        "German Documentation Center for Art History - Marburg Picture Index",
        "Royal Institute for Cultural Heritage",
        # Rome's Hertziana photographs works for art historians as Marburg
        # does: Vermeer's "Ansicht von Delft", cropped (2026-11-09).
        "Bibliotheca Hertziana, Max Planck Institute for Art History Rome. Photographic Collection",
    }
)

#: Openverse's museums, by the host of a work's page there.
OPENVERSE_HOSTS = {
    "metmuseum.org": "Metropolitan Museum of Art",
    "clevelandart.org": "Cleveland Museum of Art",
    "artic.edu": "Art Institute of Chicago",
    "rijksmuseum.nl": "Rijksmuseum",
    "smk.dk": "Statens Museum for Kunst",
    "brooklynmuseum.org": "Brooklyn Museum",
    "nga.gov": "National Gallery of Art",
}


class SharperCopy(BaseModel):
    """Another source's copy of the same picture, sharper than the work's own
    (``frame_server.sharper``): shown, sent to the frame and cut into details
    in its place; the work keeps its own texts."""

    url: str  # the copy's display-size address
    item_id: str  # the copy's id ("wmc:123"): the version the app asks by
    source: str
    museum: str = ""  # where the copy is from, as the card names it
    width: int
    height: int
    #: Picked by the owner ("Szukaj lepszej kopii"), not found by the server.
    chosen: bool = False
    #: The copy's small picture, for the work's thumbnail when it has to be
    #: had again; "" for copies kept before it was noted (then ``url``).
    thumb_url: str = ""
    #: Found because the work's own source gave no picture (down, or
    #: turning us away), not because it is sharper. It stays: the museum
    #: is not asked again.
    stand_in: bool = False
    #: Drawn again larger by the image model from the picture shown before
    #: ("Kreatywny restaurator", Mateusz 2026-11-12): the same work, its
    #: detail invented, not recovered; kept as the owner's pick.
    restored: bool = False


def quads_close(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]], by: float = 0.012
) -> bool:
    """Whether two sets of corners are one: no corner further apart than
    ``by`` (share of the photograph's side)."""
    return len(a) == len(b) and all(
        abs(x - u) <= by and abs(y - v) <= by for (x, y), (u, v) in zip(a, b, strict=True)
    )


#: The outlines of a work (``Cut.shape``).
SHAPES = ("rectangle", "round", "irregular")
#: Outlines that are not cut to a rectangle.
NOT_RECTANGLE = frozenset({"round", "irregular"})


class Cleaned(BaseModel):
    """The work shown with the colours time took given back by calculation
    (:mod:`frame_server.imaging.recovery`, :mod:`frame_server.cleaning`;
    Mateusz 2026-11-15 18:39 UTC: "Wybranie w menu podmienia na wersje z
    odżółconym papierem / ściągniętym werniksem … Jeżeli wersja podmieniona
    na skorygowaną to wyliczamy kolory i pasek z wersji po korekcie"): the
    original, the thumbnail, the colours and what the frame shows are made
    from the picture so cleaned; the picture as it came is kept beside it,
    and "Przywróć…" goes back to it."""

    #: An aged varnish taken off (oil, tempera) or the sheet de-yellowed.
    kind: Literal["varnish", "paper"]
    #: How the app said the work is made: "oil", "paper" (a medium that
    #: lets the sheet through) or "opaque" (pastel, gouache: only where the
    #: sheet shows is changed). Kept so another copy can be cleaned anew.
    made: str = ""
    #: The varnish's thickness taken off (``recovery.kept_strength``).
    strength: float = 0.0
    #: The sum it was taken off with (``recovery.READING``): a work kept
    #: from an earlier one is made again (``Cleaning.catch_up``).
    reading: int = 1
    #: The picture it was read on: the copy's id (``SharperCopy.item_id``)
    #: when a copy was shown, else "". Never applied to another photograph:
    #: "nie wiemy jaką ona ma kolorystykę i automatyczne naniesienie zmian
    #: barwy mogłoby być błędem" (Mateusz 2026-11-15 18:54).
    picture: str = ""
    #: The restorer's drawing of that picture (its copy id), which is the
    #: same photograph drawn larger and is cleaned the same ("tak dla
    #: wersji restauratora"); "" without one.
    drawn: str = ""
    #: When it was set (ISO): the app's pictures kept from before are had anew.
    at: str = ""


class Cut(BaseModel):
    """The work in its museum photograph, without what is around it (a
    frame, an easel, the board it lies on: ``imaging.cut``, ``ai.crops``;
    Mateusz 2026-11-14). Corners (top-left, top-right, bottom-right,
    bottom-left) as fractions of the photograph's width and height. The
    photograph itself is kept: "Pełny kadr" shows it, and "Przywróć zdjęcie
    muzeum" goes back to it."""

    #: The work as shown: for a print or drawing with its paper. None: the
    #: museum's photograph whole (the owner gave the cut up, or there is
    #: only paper around a print); a work with a cut is never cut again by
    #: itself.
    work: list[tuple[float, float]] | None = None
    #: A print or drawing without its paper (the plate or the image area),
    #: when it is known: shown with ``paper`` off.
    plate: list[tuple[float, float]] | None = None
    #: Prints and drawings keep their paper unless the owner says otherwise
    #: ("Pokaż z marginesem / bez marginesu").
    paper: bool = True
    #: "auto" (the model) or "owner" (corrected or chosen in the app).
    by: Literal["auto", "owner"] = "auto"
    #: The photograph's width / height when the corners were set: a cut of
    #: one photograph never cuts another (a copy shown in its place).
    aspect: float = 0.0
    #: The picture it was set on: the copy's id (``SharperCopy.item_id``)
    #: when a copy was shown, else "".
    picture: str = ""
    #: What was around the work, as the model saw it ("frame", "easel",
    #: "mount", "backdrop", "paper_margin"…).
    around: list[str] = Field(default_factory=list)
    #: When it was set (ISO): the app's pictures kept from before are had anew.
    at: str = ""
    #: The outline of the work itself as the model saw it (:data:`SHAPES`):
    #: "rectangle", "round" (a tondo, a miniature in its round frame, a
    #: plate) or "irregular" (a cut-out, a shard, a shaped panel, an
    #: object); "" when not asked (cuts set before 1.145.153). A work that
    #: is not a rectangle is never cut by itself (Mateusz 2026-11-15: „Przy
    #: obiektach o kształcie innym niż prostokąt … nie kadruj”).
    shape: str = ""
    #: The model's corners this cut took the place of when a work found not
    #: to be a rectangle was given back whole, and when they were set: a
    #: study's boxes drawn on the cut picture still find their place.
    undone: list[tuple[float, float]] | None = None
    undone_at: str = ""
    #: The outer edge of the frame or the passe-partout around the work as
    #: Opus saw it (``ai.crops.surround_in``): the card's "W ramie" shows
    #: the photograph cut to it (Mateusz 2026-11-17: „przełącznik
    #: pokazujący dzieło w ramie albo passe-partout czy z marginesem”).
    #: None when there is neither, or it was not asked.
    surround: list[tuple[float, float]] | None = None
    #: What :attr:`surround` is: "frame" or "mount" ("" without one).
    surround_kind: str = ""
    #: "auto" (the model) or "owner": his frame's edge in "Popraw kadr"
    #: (Mateusz 2026-11-17, „Tak, drugie narożniki dla ramy”), never
    #: changed by the model again, also when the work is cut anew.
    surround_by: Literal["auto", "owner"] = "auto"
    #: Whether Opus was asked for :attr:`surround` (cuts set before
    #: 1.145.224 were not: asked once, ``Crops.surrounded``).
    surround_asked: bool = False
    #: The card's "W ramie" as it is now (``Crops.framed``, set with every
    #: change of the cut): "frame", "mount", "paper" (a print shown without
    #: its sheet: the sheet), "" when there is nothing to show around the
    #: work; the picture's width / height and where the work is in it
    #: (left, top, right, bottom, fractions), for the app's move from the
    #: work to its frame.
    framed_kind: str = ""
    framed_aspect: float = 0.0
    framed_inner: tuple[float, float, float, float] | None = None

    def framed_by(self) -> tuple[list[tuple[float, float]], str] | None:
        """The corners of the card's "W ramie" on the photograph and what
        they are (:attr:`framed_kind`): the frame's or the passe-partout's
        outer edge, else a print's sheet when it is shown without it; None
        for neither, or a work shown whole."""
        if self.shown() is None:
            return None
        if self.surround is not None and self.surround_kind:
            return self.surround, self.surround_kind
        if not self.paper and self.plate is not None and self.work is not None:
            return self.work, "paper"
        return None

    def without_twin(self) -> Cut:
        """Without a "plate" that is the work itself (Wyczółkowski's
        lithograph on China paper laid on a card, MNK, 2026-11-15: the card
        cut away, the China paper is the print; "Z papierem" and "Sama
        odbitka" were the same picture): no paper to choose, so none named
        around it either."""
        if self.plate is None or self.work is None or not quads_close(self.plate, self.work):
            return self
        around = [a for a in self.around if a not in ("paper_margin", "page_text")]
        return self.model_copy(update={"plate": None, "paper": True, "around": around})

    @property
    def not_rectangle(self) -> bool:
        """The work's outline is no rectangle (:attr:`shape`): never cut by
        itself."""
        return self.shape in NOT_RECTANGLE

    def shown(self) -> list[tuple[float, float]] | None:
        """The corners the picture is cut to, None for the whole photograph."""
        return self.plate if not self.paper and self.plate is not None else self.work

    @property
    def has_paper(self) -> bool:
        """A print or drawing on its sheet: the app's "Pokaż z marginesem /
        bez marginesu"."""
        return self.plate is not None or bool({"paper_margin", "page_text"} & set(self.around))


class OwnWork(BaseModel):
    """What the owner wrote about a work of his own (``ItemKind.OWN``,
    "Dodaj własne dzieło", Mateusz 2026-11-15) beyond the fields every work
    has (title, artist, date, technique in ``medium``, his note in
    ``description``)."""

    #: Where it hangs at home ("Salon").
    hangs: str = ""
    #: Where it came from ("Rodzinne, po dziadku", "Kupione w 1998").
    origin: str = ""
    #: Its size without the frame, in centimetres; the study's "Rozmiar
    #: obrazu" draws it (``sizes``).
    height_cm: float | None = None
    width_cm: float | None = None

    def ratio(self, measured: float) -> float | None:
        """The work's width / height from his size, for the picture cut out
        of his photograph (Mateusz 2026-11-15: "Proporcje własnego dzieła
        trzeba wyliczać z podanego wymiaru"); ``measured`` is the shape the
        photograph's corners give. None without both sizes, or for a size
        more than twice off it (a slip of the finger, not the work)."""
        if not self.height_cm or not self.width_cm or measured <= 0:
            return None
        given = self.width_cm / self.height_cm
        return given if 0.5 <= given / measured <= 2.0 else None


class Item(BaseModel):
    """One picture the frame can show."""

    id: str  # "<source>:<source_id>"
    kind: ItemKind = ItemKind.ARTWORK
    source: str
    source_id: str
    title: str = ""
    artist: str = ""
    artist_bio: str = ""
    date_text: str = ""
    year: int | None = None
    medium: str = ""
    classification: str = ""
    styles: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    culture: str = ""
    museum: str = ""
    credit: str = ""
    license: str = ""
    url: str = ""
    description: str = ""
    image_url: str = ""  # large source image, downloaded on first display
    thumb_url: str = ""  # small remote image, downloaded at import
    width: int | None = None
    height: int | None = None
    colors: list[ColorSwatch] = Field(default_factory=list)
    color_tags: list[str] = Field(default_factory=list)
    #: Each colour family's share of the picture (colors.colour_shares), for
    #: colours asked at a level ("blue@much").
    color_shares: dict[str, float] = Field(default_factory=dict)
    #: Its drawn contour, if it has one (Matisse's black lines): the colour
    #: bar draws it round its paint (Mateusz 2026-11-13).
    contour: Contour | None = None
    #: What a language model sees in the picture (ai.keywords): words in
    #: English and Polish searched with the rest of the text, and the
    #: vocabulary's subjects (``"subject:sea"``) it found.
    keywords: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    #: The museum searches that found it (:meth:`PlaylistRules.search_key`):
    #: it fits them, as the museum judged it, whatever its words say (Szukaj
    #: and the smart playlist of one search show the same works).
    found_for: list[str] = Field(default_factory=list)
    #: One of the works its museum counts among its most important.
    highlight: bool = False
    # colors.tint_spread: ~0 when the picture has no colour of its own.
    tint_spread: float | None = None
    #: The share of the picture that may be a blue under yellowed varnish
    #: (``colors.varnished_blue``): 0 when none; Haiku is asked at night
    #: (``ai.varnish``) whether it is.
    varnish_blue: float = 0.0
    favorite: bool = False
    #: Hidden in the app ("Ukryj dzieło"): never shown, listed or found, but
    #: in Playlists' "Ukryte"; ``excluded_at`` when (newest first there).
    excluded: bool = False
    excluded_at: str | None = None
    #: Added by the server for a rotation (Suggestions, a smart playlist), not
    #: kept by the owner; unshown ones are cleaned up after a while.
    pooled: bool = False
    added_at: str = ""
    last_shown_at: str | None = None
    show_count: int = 0
    photo: PhotoInfo | None = None
    framing: dict[str, Framing] = Field(default_factory=dict)  # by orientation
    #: A photo sent once from the camera roll: shown with its own look, on
    #: its own or from the queue, and never part of a list or a rotation.
    look: Look | None = None
    #: A sharper copy of the picture from another source, shown in place of
    #: the work's own.
    sharper: SharperCopy | None = None
    #: The work cut out of its museum photograph (:class:`Cut`): what the
    #: frame, the thumbnails and the studies show; None when nothing was
    #: decided yet.
    cut: Cut | None = None
    #: The work's colours given back by calculation (:class:`Cleaned`): a
    #: varnish taken off or the sheet de-yellowed, at the owner's ask.
    cleaned: Cleaned | None = None
    #: A work of the owner's own: where it hangs, where it came from, its
    #: size (:class:`OwnWork`); None for every other.
    own: OwnWork | None = None
    #: The collection the work is in, as found out for a work from a source
    #: that gathers pictures from many (Wikidata's "collection" of the work
    #: on Commons or WikiArt, the institution on its Commons page, WikiArt's
    #: gallery); "" when not known. See :attr:`held_by`.
    holder: str = ""
    #: The Wikidata item of the place the work is in, when a look found it
    #: (the holder's item, the collection a Commons search by place asked
    #: for, the painting a reproduction is of); "" else. See :attr:`held_at`.
    place: str = ""
    #: What the picture is when it is not of the work itself but a copy kept
    #: elsewhere ("Chromolitografia"): its place is then the original's.
    reproduction: str = ""
    #: A fragment of another work (``library.fragments``): that work's id,
    #: and which of how many parts this is (counted from 1); "" and 0 else.
    part_of: str = ""
    part: int = 0
    parts: int = 0
    #: Another copy of the same work found by its picture under another
    #: title ("Lekcja muzyki" on Commons, "The music lesson" on WikiArt;
    #: ``library.twins``): that item's id, which groups them as one work
    #: (``duplicates``); "" else.
    copy_of: str = ""
    #: The picture is a detail of another copy's (``library.twins``): that
    #: item's id; a detail is no work for the frame (``vocabulary.is_detail``).
    detail_of: str = ""
    #: The picture is a photograph of another copy's work with what is
    #: around it (its frame, the museum's wall, a page): that item's id
    #: (``library.twins``); no work for the frame either.
    scene_of: str = ""
    #: Version of ``library.twins``' look at the picture, 0 for none yet.
    twins_seen: int = 0
    #: Version of its look at the large pictures of the artist's works, for
    #: details too small for a thumbnail; 0 while still to be done.
    twins_large: int = 0
    #: The thumbnail's difference hash (``library.picture_hash``), "" while
    #: not worked out, "-" when there is no telling.
    picture_hash: str = ""
    #: Changes when the work's picture became another photograph with no
    #: copy taking its place (``ImageCache.thumb_follows``): an original
    #: kept from a mirror while its museum was down (Paris Musées' gilt
    #: frame and Commons' canvas of Géricault's "Paysage italien au
    #: tombeau", Mateusz 2026-11-17), and its thumbnail made again from
    #: it. "" while the thumbnail is the one first made. The app asks for
    #: the thumbnail again when it changes, as for ``ItemSummary.picture``.
    picture_stamp: str = ""
    #: What the catalogue's gatekeeper (``ai.gatekeeper``) found the picture
    #: to be when it is no artwork for the frame ("postal", "text", "room",
    #: "grey_copy", "not_art"), confirmed by its critic; "" else.
    seen_as: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def held_by(self) -> str:
        """The museum the work is in ("Muzeum Narodowe w Warszawie"), named on
        the card above its title; "" when not known. Not where the picture is
        from: a work on Wikimedia Commons hangs in a museum, not on Commons.
        One museum has one name, however its source writes it."""
        key = self.held_at
        return (known_places().name(key) if key else "") or self._held_by()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def held_at(self) -> str:
        """The key of the place the work is in (:mod:`.places`): a Wikidata
        item ("Q190804"), else the folded name ("name:…"); "" when not
        known. Szukaj's "Muzeum" chooses by it."""
        if self.kind != ItemKind.ARTWORK or self.look is not None:
            return ""
        places = known_places()
        if self.place:
            return places.canon(self.place)
        raw = self._held_by()
        if self.source in COLLECTIONS and not self.reproduction:
            return places.key_of(raw, self.source) if raw else source_place(self.source)
        if not raw:
            return ""
        if self.sharper is not None and raw == self.sharper.museum:
            return places.key_of(raw, self.sharper.source)
        return places.key_of(raw)

    def cut_shown(self) -> list[tuple[float, float]] | None:
        """The corners the picture is cut to now (:class:`Cut`): None
        without a cut, when the owner keeps the photograph whole, or when
        another picture than the one the cut was set on is shown."""
        cut = self.cut
        if cut is None or cut.picture != self.picture_key():
            return None
        return cut.shown()

    def cut_framed(self) -> list[tuple[float, float]] | None:
        """Where the work is on the photograph the card's "W ramie" is cut
        from: the cut shown, or, for the restorer's drawing of the museum's
        own photograph (``SharperCopy.restored``), the cut set on that
        photograph: the drawing is of the work alone, laid in its frame
        (Mateusz 2026-11-18)."""
        shown = self.cut_shown()
        if shown is not None:
            return shown
        cut, sharper = self.cut, self.sharper
        if cut is None or sharper is None or not sharper.restored or cut.picture != "":
            return None
        return cut.shown()

    def picture_key(self) -> str:
        """Which picture is shown: the copy's id when a copy is, else ""."""
        return self.sharper.item_id if self.sharper is not None else ""

    def cut_version(self) -> str:
        """Changes whenever the cut of the picture shown changes (set,
        corrected, the paper switched, given up): the app's pictures kept
        from before are had anew. "" without one."""
        cut = self.cut
        if cut is None or cut.picture != self.picture_key() or cut.shown() is None:
            return ""
        return cut.at or "cut"

    def cleaned_shown(self) -> Cleaned | None:
        """How the picture shown now is cleaned (:class:`Cleaned`): None
        without, or when another picture than the one it was read on (or
        the restorer's drawing of that one) is shown."""
        cleaned = self.cleaned
        if cleaned is None:
            return None
        key = self.picture_key()
        if key == cleaned.picture or (cleaned.drawn and key == cleaned.drawn):
            return cleaned
        return None

    def cleaned_version(self) -> str:
        """Changes whenever the cleaning of the picture shown does (set,
        given up): the app's pictures kept from before are had anew. ""
        without one."""
        cleaned = self.cleaned_shown()
        return "" if cleaned is None else cleaned.at or cleaned.kind

    def _held_by(self) -> str:
        """The museum's name as the work's data give it."""
        if self.kind != ItemKind.ARTWORK or self.look is not None:
            return ""
        if self.source in COLLECTIONS and not (self.place and self.reproduction):
            return self.museum
        if self.holder:
            return self.holder
        if self.sharper is not None and self.sharper.source in COLLECTIONS and self.sharper.museum:
            return self.sharper.museum  # the same picture whole, from the museum itself
        if self.source == "europeana":
            # Its data provider: the collection, unless a photo archive.
            return "" if self.credit in ART_PHOTO_ARCHIVES else self.credit
        if self.source == "openverse":
            host = (urlsplit(self.url).hostname or "").removeprefix("www.")
            return next((n for h, n in OPENVERSE_HOSTS.items() if host.endswith(h)), "")
        return ""

    def __setattr__(self, name: str, value: Any) -> None:
        """A record changed where it stands: what was worked out of it
        before is asked anew (:mod:`.memo`). The library itself never does
        so, it puts a copy in the record's place."""
        super().__setattr__(name, value)
        memo.changed(self)

    @property
    def file_stem(self) -> str:
        return Item.stem_of(self.id)

    @staticmethod
    def stem_of(item_id: str) -> str:
        """The name of a work's files (thumbnail, original) without suffix."""
        return item_id.replace(":", "_").replace("/", "_")

    @field_serializer("favorite")
    def _favorite_for_viewer(self, value: bool, info: SerializationInfo) -> bool:
        """Stored: someone's favourite. To the app: the viewer's own heart
        (see library.viewer)."""
        if info.context and info.context.get("store"):
            return value
        viewer = VIEWER.get()
        return value if viewer is None else viewer.likes(self.id)


def cut_size(
    quad: list[tuple[float, float]], aspect: float, width: int | None, height: int | None
) -> tuple[int, int] | None:
    """The size of the picture cut to ``quad`` out of a photograph of
    ``aspect`` (width / height), ``width`` × ``height`` px when known."""
    if aspect <= 0:
        return None
    w = float(width) if width and height else 1000.0 * aspect
    h = w / aspect
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    top = math.hypot((x1 - x0) * w, (y1 - y0) * h)
    bottom = math.hypot((x2 - x3) * w, (y2 - y3) * h)
    left = math.hypot((x3 - x0) * w, (y3 - y0) * h)
    right = math.hypot((x2 - x1) * w, (y2 - y1) * h)
    cw, ch = round(max(top, bottom)), round(max(left, right))
    return (cw, ch) if cw > 0 and ch > 0 else None


class ItemSummary(BaseModel):
    """Compact form for grids and lists."""

    id: str
    kind: ItemKind
    source: str
    title: str
    artist: str
    date_text: str
    year: int | None
    colors: list[ColorSwatch]
    width: int | None
    height: int | None
    favorite: bool
    pooled: bool = False
    #: The Polish title, where a list shows it ("Teraz"); None elsewhere.
    title_pl: str | None = None
    #: ``Item.held_by``: the museum the work is in, "" when not known.
    held_by: str = ""
    #: ``Item.held_at``: its key, for Szukaj with that museum.
    held_at: str = ""
    #: Which picture the work shows: the id of the copy in its place
    #: (``Item.sharper``), "" for its own. The app asks for the thumbnail
    #: again when it changes, instead of the one kept from before.
    picture: str = ""
    #: ``Item.picture_stamp``: changes when the work's picture became
    #: another photograph of its own; the thumbnail is asked for again.
    picture_stamp: str = ""
    #: A photo's line under its title: when and where ("29 października
    #: 2026 · Kraków"); "" for works.
    subtitle: str = ""
    #: Its picture can be looked at far closer, in tiles ("Pod lupą":
    #: ``zoom.zooms``).
    zoom: bool = False
    #: Its picture's long side when it is known and small for the frame
    #: (``low_res.low_side``), else 0: a mark after the title.
    low_side: int = 0
    #: Its picture was drawn again by the image model ("Kreatywny
    #: restaurator": ``SharperCopy.restored``): its mark in place of the
    #: low resolution's.
    restored: bool = False
    #: Its picture is cut out of the museum's photograph (``Item.cut``): a
    #: mark after the title. ``cut``: changes with every change of the cut.
    cropped: bool = False
    cut: str = ""
    #: Its picture is shown cleaned by calculation (``Item.cleaned``):
    #: "varnish" or "paper", "" when not; a mark after the title.
    #: ``cleaned_at``: changes with every change of it.
    cleaned: str = ""
    cleaned_at: str = ""
    #: ``Item.own``: a work of the owner's own (the card names where it
    #: hangs above its title, its technique and size below the artist).
    own: OwnWork | None = None

    @classmethod
    def of(cls, item: Item) -> ItemSummary:
        from .low_res import low_side
        from .photo_text import photo_line, photo_title
        from .zoom import zooms

        summary = cls(
            **item.model_dump(
                include=set(cls.model_fields)
                - {"subtitle", "zoom", "low_side", "restored", "cropped", "cut"}
                - {"cleaned", "cleaned_at"}
            )
        )
        if (cleaned := item.cleaned_shown()) is not None:
            summary.cleaned = cleaned.kind
            summary.cleaned_at = item.cleaned_version()
        summary.zoom = zooms(item)
        summary.low_side = low_side(item)
        summary.cut = item.cut_version()
        shown = item.cut_shown()
        if shown is not None and item.cut is not None:
            summary.cropped = True
            if (size := cut_size(shown, item.cut.aspect, item.width, item.height)) is not None:
                summary.width, summary.height = size  # the tile's shape is the cut's
                ratio = item.own.ratio(size[0] / size[1]) if item.own is not None else None
                if ratio:  # his work: the shape of the size he gave, as it is cut
                    area = size[0] * size[1]
                    summary.width = round(math.sqrt(area * ratio))
                    summary.height = round(math.sqrt(area / ratio))
        if item.sharper is not None:
            summary.picture = item.sharper.item_id
            summary.restored = item.sharper.restored
        if item.kind == ItemKind.PHOTO:
            summary.title = photo_title(item)
            summary.subtitle = photo_line(item)
        return summary


class PlaceCount(BaseModel):
    """A place of the catalogue's works, for Szukaj's "Muzeum"."""

    key: str
    name: str
    city: str = ""
    count: int = 0
    #: A work of the place to show beside its name.
    item_id: str = ""
    #: The source that is its own collection ("rijks"), "" when it has none.
    source: str = ""


#: Terms for the owner's own works ("Moje" in the app's "+"): those with a
#: heart, and those on any other playlist. Not in the vocabulary: museums
#: have none of them.
MINE_FAVORITES = "mine:favorites"
MINE_PLAYLISTS = "mine:playlists"
MINE = (MINE_FAVORITES, MINE_PLAYLISTS)


class PlaylistRules(BaseModel):
    """Smart playlist filter. Empty lists mean "any"; lists are OR-ed
    internally, the different fields AND-ed together."""

    query: str = ""
    artists: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    #: Styles, subjects, periods and techniques from library.vocabulary
    #: (``"subject:sea"``, ``"years:1880-1914"``).
    terms: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    kinds: list[ItemKind] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    #: Museums left out: every source but these ("wszystkie poza Yale"),
    #: so that a museum added later comes in on its own. Like
    #: ``exclude_ids``, an exception: alone it is no rule.
    exclude_sources: list[str] = Field(default_factory=list)
    #: Where the works are (:mod:`.places`: "Q190804", "name:…"): Szukaj's
    #: "Muzeum" (Mateusz 2026-11-08), whichever source brings the picture.
    places: list[str] = Field(default_factory=list)
    #: Places left out: an exception, like ``exclude_sources``.
    exclude_places: list[str] = Field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    favorites_only: bool = False
    #: Only works the owner kept (not those the server added to the catalogue).
    kept_only: bool = False
    #: Works the owner removed from this smart playlist although they match.
    exclude_ids: list[str] = Field(default_factory=list)
    #: Words for how the works look ("mglisty poranek nad wodą"): of the
    #: works the other rules find, those that look so, nearest first
    #: (``frame_server.looks``, Mateusz 2026-11-13). The museums are asked
    #: by searches Haiku makes of it (``ai.look_words``), what they bring
    #: judged by how it looks; ``search_key`` leaves it out (what a museum
    #: brought for it is no word's answer).
    look: str = ""
    #: A work's title, or words of it ("Gwiaździsta noc"): works whose title
    #: has them, in Polish or as the museums were asked them; not those that
    #: only mention them (Mateusz 2026-11-13: "szukanie po tytule dzieła").
    title: str = ""
    #: A work's id: the works that look like it, nearest first, the other
    #: rules narrowing them (``frame_server.looks``; Mateusz 2026-11-13,
    #: "Szukaj podobnych" on a work's card). Only the catalogue's works:
    #: no museum is asked; ``search_key`` leaves it out. With it, ``look``
    #: is not asked.
    like: str = ""
    #: What of ``like`` is asked (Mateusz 2026-11-17: "Podobne tematem",
    #: "Podobne stylem"): "" both its subject and its style, "subject" or
    #: "style" alone.
    like_by: Literal["", "subject", "style"] = ""

    @model_validator(mode="before")
    @classmethod
    def _museums_as_places(cls, data: Any) -> Any:
        """Museums chosen as sources before there were places (rules kept
        before 1.124, an older app): a museum's own collection becomes its
        places; sources gathering pictures from many stay sources."""
        if not isinstance(data, dict):
            return data
        changes: dict[str, Any] = {}
        for old, new in (("sources", "places"), ("exclude_sources", "exclude_places")):
            sources = data.get(old)
            if not sources:
                continue
            places, kept = migrate_sources(sources)
            if places:
                changes[new] = list(dict.fromkeys([*(data.get(new) or []), *places]))
                changes[old] = kept
        return {**data, **changes} if changes else data

    def search_key(self) -> str:
        """What a museum search for these rules asks, as a short key: the
        words, artists, terms, colours and years (museums chosen or left out
        are checked on their own); empty when it asks for none of them."""
        words = " ".join(self.query.casefold().split())
        asked = [
            words,
            sorted(self.artists),
            sorted(self.terms),
            sorted(self.colors),
            self.year_from,
            self.year_to,
        ]
        title = " ".join(self.title.casefold().split())
        if title:  # only then: the keys of searches without one stay as they were
            asked.append(title)
        if not any(a not in ("", [], None) for a in asked):
            return ""
        text = json.dumps(asked, ensure_ascii=False)
        return "s:" + hashlib.sha1(text.encode()).hexdigest()[:16]

    def is_empty(self) -> bool:
        """No filter at all: the whole catalogue (exceptions don't count)."""
        return not (
            self.query.strip()
            or self.look.strip()
            or self.like.strip()
            or self.title.strip()
            or self.artists
            or self.styles
            or self.subjects
            or self.terms
            or self.colors
            or self.kinds
            or self.sources
            or self.places
            or self.year_from is not None
            or self.year_to is not None
            or self.favorites_only
            or self.kept_only
        )

    def asks_mine(self) -> bool:
        """Only the owner's own works: favourites or those on playlists,
        which no museum can bring."""
        return any(t in MINE for t in self.terms)


class PlaylistKind(StrEnum):
    SMART = "smart"
    MANUAL = "manual"
    ALBUM = "album"  # mirrors a shared iCloud album


class AlbumOrder(StrEnum):
    """In which order an album's photos are shown."""

    RANDOM = "random"
    NEWEST = "newest"  # taken most recently first
    OLDEST = "oldest"  # taken longest ago first
    ADDED = "added"  # added to the album most recently first


#: How a playlist's works are put in order (Mateusz 2026-11-12): by
#: artist (then year), year made, when added, format (portrait first) or
#: quality (the long side of the picture shown, largest first).
PlaylistSortKey = Literal["artist", "year", "added", "format", "quality"]


class PlaylistSort(BaseModel):
    """A playlist's order, in the app and on the frame (when it does not
    shuffle). ``reverse`` turns the key's own direction round; works whose
    value is not known (no year, no size) stay last either way."""

    key: PlaylistSortKey
    reverse: bool = False


class AlbumSource(BaseModel):
    """The shared iCloud album an album playlist mirrors."""

    url: str
    order: AlbumOrder = AlbumOrder.RANDOM


class AlbumSync(BaseModel):
    """The last synchronisation of an album playlist."""

    at: str
    name: str = ""  # the album's own name in Photos
    count: int = 0
    added: int = 0
    error: str = ""


class Playlist(BaseModel):
    id: int | None = None
    name: str
    description: str = ""
    kind: PlaylistKind = PlaylistKind.SMART
    rules: PlaylistRules = Field(default_factory=PlaylistRules)
    item_ids: list[str] = Field(default_factory=list)  # manual and album playlists
    album: AlbumSource | None = None  # album playlists
    #: The Discover theme the playlist was made from.
    theme: str | None = None
    #: Who made it: only they change it. Others see it when ``shared``.
    owner: str = OWNER_ID
    shared: bool = False
    #: Once a smart playlist's most works ("Ile dzieł"). Gone (Mateusz,
    #: 2026-11-14): every smart playlist takes all that match. The field
    #: stays so stored playlists and older apps still load; it is always None.
    limit: int | None = None
    #: The order its owner chose; None: :meth:`order` (artist for a smart
    #: playlist, the order of adding for a manual one).
    sort: PlaylistSort | None = None
    created_at: str = ""
    updated_at: str = ""

    @field_validator("limit", mode="before")
    @classmethod
    def _no_limit(cls, value: object) -> None:
        """A limit, stored or sent by an older app, is dropped."""
        return None

    @property
    def order(self) -> PlaylistSort:
        """The order its works are in: the chosen one, else the default."""
        if self.sort is not None:
            return self.sort
        if self.kind == PlaylistKind.SMART:
            return PlaylistSort(key="artist")
        return PlaylistSort(key="added", reverse=True)  # as they were added

    def visible_to(self, user_id: str) -> bool:
        return self.shared or self.owner == user_id

    @property
    def is_favorites(self) -> bool:
        """The owner's hearts: "Ulubione", which is always there."""
        return self.kind == PlaylistKind.SMART and self.rules.favorites_only


class PlaylistSummary(BaseModel):
    id: int
    name: str
    description: str
    kind: PlaylistKind
    rules: PlaylistRules
    item_count: int
    cover_item_ids: list[str]
    #: The main colour of each cover work, in the same order: the app's glow
    #: behind "Teraz prezentowane".
    cover_colors: list[ColorSwatch] = Field(default_factory=list)
    album: AlbumSource | None = None
    album_sync: AlbumSync | None = None
    theme: str | None = None
    owner: str = OWNER_ID
    #: The owner's name, for a playlist someone else made.
    owner_name: str = ""
    shared: bool = False
    #: The viewer made it (and may change it).
    mine: bool = True
    limit: int | None = None
    #: The order its works are in (:attr:`Playlist.order`); None for an album.
    sort: PlaylistSort | None = None


class FacetValue(BaseModel):
    value: str
    count: int


class Facets(BaseModel):
    artists: list[FacetValue]
    styles: list[FacetValue]
    subjects: list[FacetValue]
    colors: list[FacetValue]
    sources: list[FacetValue]
    kinds: list[FacetValue]


class Note(BaseModel):
    """What a language model wrote about one item (ai): its keywords, a
    Polish description... One per item and kind, kept until the item, its
    source text (``source_hash``) or the prompt (``prompt_version``) change."""

    item_id: str
    kind: str  # "keywords", "pl_text"
    model: str
    prompt_version: str
    source_hash: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
