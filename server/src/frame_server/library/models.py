"""Library data model shared by the database, the API and the importers."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..imaging.layout import Crop, Fit


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


class Look(BaseModel):
    """How a photo sent once from the camera roll ("Zdjęcie na ramkę") is
    shown, in place of the settings' presentation for photos: over the
    whole frame or in a passe-partout; the style is always automatic."""

    fit: Literal[Fit.FILL, Fit.FIT] = Fit.FILL
    mat: Literal["white", "cream", "grey", "black", "picture", "picture_dark"] = "white"
    margin: float = Field(0.05, ge=0, le=0.3)


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
    #: What a language model sees in the picture (ai.keywords): words in
    #: English and Polish searched with the rest of the text, and the
    #: vocabulary's subjects (``"subject:sea"``) it found.
    keywords: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    #: One of the works its museum counts among its most important.
    highlight: bool = False
    suitability: float | None = None
    # colors.tint_spread: ~0 when the picture has no colour of its own.
    tint_spread: float | None = None
    favorite: bool = False
    excluded: bool = False
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

    @property
    def file_stem(self) -> str:
        return self.id.replace(":", "_").replace("/", "_")


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
    suitability: float | None
    pooled: bool = False
    #: The Polish title, where a list shows it ("Teraz"); None elsewhere.
    title_pl: str | None = None

    @classmethod
    def of(cls, item: Item) -> ItemSummary:
        return cls(**item.model_dump(include=set(cls.model_fields)))


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
    year_from: int | None = None
    year_to: int | None = None
    favorites_only: bool = False
    #: Only works the owner kept (not those the server added to the catalogue).
    kept_only: bool = False
    min_suitability: float | None = None
    #: Works the owner removed from this smart playlist although they match.
    exclude_ids: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """No filter at all: the whole catalogue (exceptions don't count)."""
        return not (
            self.query.strip()
            or self.artists
            or self.styles
            or self.subjects
            or self.terms
            or self.colors
            or self.kinds
            or self.sources
            or self.year_from is not None
            or self.year_to is not None
            or self.favorites_only
            or self.kept_only
            or self.min_suitability is not None
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
    created_at: str = ""
    updated_at: str = ""

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
    album: AlbumSource | None = None
    album_sync: AlbumSync | None = None
    theme: str | None = None


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
