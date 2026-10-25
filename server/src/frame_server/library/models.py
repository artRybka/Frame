"""Library data model shared by the database, the API and the importers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from ..imaging.layout import Crop


class ItemKind(StrEnum):
    ARTWORK = "artwork"  # from a museum collection
    OWN = "own"  # own work / family art, uploaded with a description
    PHOTO = "photo"  # iCloud shared album or camera roll


class ColorSwatch(BaseModel):
    hex: str
    weight: float


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


class Framing(BaseModel):
    """Corrections saved by the user for one orientation of the frame."""

    fill: Crop | None = None  # FILL: the part shown
    details: list[Crop] | None = Field(None, min_length=2, max_length=2)  # DETAILS
    detail: Crop | None = None  # DESCRIPTION: its one close-up
    fit: Crop | None = None  # FIT: the part shown and the window's shape


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
    suitability: float | None = None
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

    @classmethod
    def of(cls, item: Item) -> ItemSummary:
        return cls(**item.model_dump(include=set(cls.model_fields)))


class PlaylistRules(BaseModel):
    """Smart playlist filter. Empty lists mean "any"; lists are OR-ed
    internally, the different fields AND-ed together."""

    query: str = ""
    artists: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
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
    created_at: str = ""
    updated_at: str = ""


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
