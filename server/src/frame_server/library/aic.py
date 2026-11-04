"""Addresses of the Art Institute of Chicago's pictures, as its IIIF
server gives them (https://api.artic.edu/docs/, "Image Sizes")."""

from __future__ import annotations

import re

AIC_IIIF = "https://www.artic.edu/iiif/2"
#: The only widths the AIC's IIIF server gives (its API docs, "Image
#: Sizes"; 1200 and 1686 for public-domain works). Any other, ``full`` too,
#: is refused: by its Cloudflare with a challenge that rests the whole host
#: (2026-11-04), or by the server itself when wider than the picture.
AIC_WIDTHS = (112, 200, 400, 600, 800, 843, 1200, 1686)
#: The size the AIC's website uses and asks programs to use: most likely in
#: Cloudflare's cache already, so the lightest on their systems.
AIC_THUMB = 843
AIC_ORIGINAL = 1686
_AIC_SIZE = re.compile(r"/full/[^/]+/0/default\.jpg$")


def aic_width(most: int, width: int | None) -> int:
    """The largest of :data:`AIC_WIDTHS` up to ``most`` and not wider than
    the picture (``width``; ``most`` when not known)."""
    widest = min(most, width) if width else most
    fits = [w for w in AIC_WIDTHS if w <= widest]
    return fits[-1] if fits else AIC_WIDTHS[0]


def aic_picture(base: str, most: int, width: int | None) -> str:
    """The address of an AIC picture (``base``: the IIIF identifier's URL)
    in an allowed width, :func:`aic_width`."""
    return f"{base}/full/{aic_width(most, width)},/0/default.jpg"


def aic_resized(url: str, most: int, width: int | None) -> str:
    """``url`` (an AIC IIIF address stored by an older version, e.g. with
    ``full/full``) in an allowed width; other addresses as they are."""
    if not url.startswith(AIC_IIIF + "/") or not _AIC_SIZE.search(url):
        return url
    return aic_picture(_AIC_SIZE.sub("", url), most, width)
