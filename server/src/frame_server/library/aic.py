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
#: The size the AIC's website downloads a public-domain work in (its
#: "Download image" button, ``DamsImageService::getUrl``): the picture fit
#: into 3000×3000. Asked with our User-Agent from home it came back whole
#: (2975×2250 for a Degas pastel), from Cloudflare's cache, with no
#: challenge (Mateusz 2026-11-05).
AIC_LARGE = 3000
AIC_LARGE_SIZE = f"!{AIC_LARGE},{AIC_LARGE}"
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


def _large_width(width: int, height: int | None) -> int:
    """The width of the picture fit into :data:`AIC_LARGE` square."""
    side = max(width, height or 0)
    return width if side <= AIC_LARGE else width * AIC_LARGE // side


def aic_original(base: str, width: int | None, height: int | None) -> str:
    """The address of an AIC work's original: in the website's download size
    (:data:`AIC_LARGE_SIZE`) when that is wider than :data:`AIC_ORIGINAL`,
    else the widest allowed width (:func:`aic_picture`); a tall narrow
    picture is wider at 1686 than fit into 3000×3000."""
    if width and _large_width(width, height) > AIC_ORIGINAL:
        return f"{base}/full/{AIC_LARGE_SIZE}/0/default.jpg"
    return aic_picture(base, AIC_ORIGINAL, width)


def aic_large_size(url: str, width: int | None, height: int | None) -> tuple[int, int] | None:
    """The size the download address ``url`` gives the picture in
    (``width`` × ``height`` as the API tells), fit into :data:`AIC_LARGE`
    square; None for any other address or an unknown size."""
    if not width or not height or not url.startswith(AIC_IIIF + "/"):
        return None
    if f"/full/{AIC_LARGE_SIZE}/" not in url:
        return None
    side = max(width, height)
    if side <= AIC_LARGE:
        return width, height
    return round(width * AIC_LARGE / side), round(height * AIC_LARGE / side)


def aic_fallback(url: str, width: int | None) -> str | None:
    """The allowed-width address (:data:`AIC_ORIGINAL`) to try when the
    download size (``url``) is refused; None for any other address."""
    if not url.startswith(AIC_IIIF + "/") or f"/full/{AIC_LARGE_SIZE}/" not in url:
        return None
    return aic_picture(_AIC_SIZE.sub("", url), AIC_ORIGINAL, width)


def aic_original_resized(url: str, width: int | None, height: int | None) -> str:
    """``url`` (an AIC work's original stored by an older version) as
    :func:`aic_original` gives it now; other addresses as they are."""
    if not url.startswith(AIC_IIIF + "/") or not _AIC_SIZE.search(url):
        return url
    return aic_original(_AIC_SIZE.sub("", url), width, height)


def aic_resized(url: str, most: int, width: int | None) -> str:
    """``url`` (an AIC IIIF address stored by an older version, e.g. with
    ``full/full``) in an allowed width; other addresses as they are."""
    if not url.startswith(AIC_IIIF + "/") or not _AIC_SIZE.search(url):
        return url
    return aic_picture(_AIC_SIZE.sub("", url), most, width)
