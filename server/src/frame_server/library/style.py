"""Automatic picture style: which rendering preset (imaging.PRESETS) suits
a picture, from what it is and what colours it has."""

from __future__ import annotations

import re

from PIL import Image

from .colors import tint_spread
from .models import Item, ItemKind
from .vocabulary import GREY_PAINTING_SPREAD, is_painting

#: Presentation.preset value: choose for each picture.
AUTO = "auto"

#: Below this tint spread a picture has no colour of its own (pencil, ink,
#: etchings, B&W and sepia photos): black and white ink only. Paintings are
#: measured against ``GREY_PAINTING_SPREAD`` instead: a dark, warm oil (Rembrandt's
#: "Study of an Old Man in Profile", ~0.012) lies on one brown line just like
#: a sepia photo, yet its browns, ochres and flesh are colour.
MONOCHROME_SPREAD = 0.012

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


def auto_preset(item: Item) -> str:
    """The preset for ``item``: colourless pictures in black and white,
    photos as photos, prints and posters as graphics, the rest as paintings.
    A painting goes black and white only when its picture is a grey copy."""
    limit = GREY_PAINTING_SPREAD if is_painting(item) else MONOCHROME_SPREAD
    if item.tint_spread is not None and item.tint_spread < limit:
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
    """A one-off photo sent from the phone: B&W ones in black and white."""
    return "bw" if tint_spread(img) < MONOCHROME_SPREAD else "photo"
