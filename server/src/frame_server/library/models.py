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


class Framing(BaseModel):
    """Corrections saved by the user for one orientation of the frame."""

    fill: Crop | None = None  # FILL: the part shown
    details: list[Crop] | None = Field(None, min_length=2, max_length=2)  # DETAILS


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
    min_suitability: float | None = None


class PlaylistKind(StrEnum):
    SMART = "smart"
    MANUAL = "manual"


class Playlist(BaseModel):
    id: int | None = None
    name: str
    description: str = ""
    kind: PlaylistKind = PlaylistKind.SMART
    rules: PlaylistRules = Field(default_factory=PlaylistRules)
    item_ids: list[str] = Field(default_factory=list)  # manual playlists
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
