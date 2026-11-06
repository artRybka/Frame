"""Automatic picture style: which rendering preset (imaging.PRESETS) suits
a picture, from what it is and what colours it has."""

from __future__ import annotations

import re

from PIL import Image

from .colors import tint_spread, tint_strength
from .models import Item, ItemKind
from .vocabulary import GREY_PAINTING_SPREAD, is_painting

#: Presentation.preset value: choose for each picture.
AUTO = "auto"

#: Below this tint spread a picture has no colour of its own beyond one tint
#: (pencil, ink, etchings, B&W and sepia photos). Paintings are
#: measured against ``GREY_PAINTING_SPREAD`` instead: a dark, warm oil (Rembrandt's
#: "Study of an Old Man in Profile", ~0.012) lies on one brown line just like
#: a sepia photo, yet its browns, ochres and flesh are colour.
MONOCHROME_SPREAD = 0.012
#: ... and only a picture tinted less than this (``colors.tint_strength``) is
#: black and white. Sepia, albumen and salted paper prints, brown ink and
#: chalk on cream or blue paper keep their tone (Mateusz 2026-11-06: "Sepia
#: powinna jednak zostać sepią"); measured on Cleveland's scans, neutral
#: prints and photos lie at 0.008–0.015, visibly warm ones from 0.017 up.
NEUTRAL_TINT = 0.015

# Matched as word starts in classification, medium and styles; museums
# describe works in English, Dutch (Rijksmuseum), French and Polish.
_PHOTO = re.compile(r"\b(photograph|gelatin silver|albumen|daguerreotyp|fotografi|foto\b)", re.I)
_GRAPHIC = re.compile(
    r"\b(print|woodblock|woodcut|wood engraving|engraving|etching|aquatint|drypoint|mezzotint|"
    r"lithograph|chromolithograph|screenprint|serigraph|linocut|stencil|poster|illustration|"
    r"ukiyo|prent|houtsnede|ets\b|gravure|estampe|affiche|drzeworyt|miedzioryt|akwafort|"
    r"litografi|plakat|ilustracj|grafika)",
    re.I,
)


def toned_only(item: Item) -> bool:
    """Whether ``item``'s picture has no colour of its own beyond one tint
    (pencil, ink, etchings, B&W and sepia photos); it is black and white
    when that tint is faint too (``NEUTRAL_TINT``). A painting counts only
    when its picture is a grey copy."""
    limit = GREY_PAINTING_SPREAD if is_painting(item) else MONOCHROME_SPREAD
    return item.tint_spread is not None and item.tint_spread < limit


def auto_preset(item: Item, tint: float | None = None) -> str:
    """The preset for ``item``: black-and-white pictures in black and white,
    photos as photos, prints and posters as graphics, the rest as paintings.
    ``tint`` is the picture's ``colors.tint_strength``; without it a picture
    with one tint only counts as black and white."""
    if toned_only(item) and (tint is None or tint < NEUTRAL_TINT):
        return "bw"
    if item.kind == ItemKind.PHOTO:
        return "photo"
    text = " ".join((item.classification, item.medium, *item.styles))
    if _PHOTO.search(text):
        return "photo"
    if _GRAPHIC.search(text):
        return "graphic"
    return "painting"


def preset_for_photo(img: Image.Image) -> str:
    """A one-off photo sent from the phone: B&W ones in black and white,
    sepia ones as photos."""
    grey = tint_spread(img) < MONOCHROME_SPREAD and tint_strength(img) < NEUTRAL_TINT
    return "bw" if grey else "photo"
