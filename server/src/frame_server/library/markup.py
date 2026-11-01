"""Plain text and readable image links from what museums' APIs return.

Some sources put markup into short fields: Commons titles that come from
Wikidata carry the "edit on Wikidata" icon (``<span class="mw-valign-text-top
noprint">…<img …></span>``), and a value cut at a quote leaves a dangling
``<span class=`` behind. Some files are no pictures a frame can read at all
(SVG drawings, PDF and DjVu scans); Commons renders those as PNG or JPEG.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urlsplit

_TAG = re.compile(r"<[a-zA-Z/!][^<>]*>")
# A tag cut off by the end of the text: "Portret <span class=".
_CUT_TAG = re.compile(r"<[a-zA-Z/][^<>]*$")


def drop_tags(text: str, sep: str = "") -> str:
    """``text`` without tags, also a cut-off last one; each tag becomes ``sep``."""
    return _CUT_TAG.sub("", _TAG.sub(sep, text)) if "<" in text else text


def strip_markup(text: str | None) -> str:
    """``text`` without tags, entities decoded, on one line."""
    if not text:
        return ""
    text = drop_tags(text, " ")
    if "&" in text:
        text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# ISO 639-1 codes plus the few longer Wikimedia ones seen in titles.
_LANGUAGE_CODE_LIST = """
aa ab af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co
cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd
gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv
ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg
mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os
pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss
st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo
wa wo xh yi yo za zh zu als ast bar bcl frr fur grc hsb jbo lad lmo nap nds
pms rue sco scn szl vec yue
"""
_LANGUAGE_CODES = frozenset(_LANGUAGE_CODE_LIST.split())
# "en:Night Windows", ":en:…", "w:en:…": an interwiki link written without a
# label shows its target, language code and all.
_LANGUAGE_PREFIX = re.compile(
    r"^:?(?:(?:w|wikipedia|wikt|commons|d):)?(?P<code>[a-z]{2,3})(?:-[a-z]+)*:(?=\S)"
)


def strip_language_prefix(text: str) -> str:
    """``text`` without a leading language code: "en:Night Windows" → "Night Windows"."""
    while (m := _LANGUAGE_PREFIX.match(text)) and m.group("code") in _LANGUAGE_CODES:
        text = text[m.end() :]
    return text


def clean_title(text: str | None) -> str:
    """A title or a name as plain text, without markup or a language prefix."""
    return strip_language_prefix(strip_markup(text))


#: Formats every browser opens; Commons' TIFFs (often 100 MB and more) are
#: better taken as its rendered JPEG too.
WEB_IMAGES = frozenset({"jpg", "jpeg", "png", "gif", "webp"})
#: Formats only a rendered copy can show.
VECTOR = frozenset({"svg", "pdf", "djvu"})
#: Widths Commons renders copies at; any other width is refused (400).
COMMONS_WIDTHS = (500, 960, 1280, 1920, 3840)
#: A Commons original; the API adds a query (``?utm_source=...``) to its links.
_COMMONS_FILE = re.compile(
    r"^(https://upload\.wikimedia\.org/wikipedia/commons)/([0-9a-f]/[0-9a-f]{2})/([^/?#]+)"
    r"(?:\?[^#]*)?$"
)


def extension(url: str) -> str:
    """The file extension of ``url``'s path, lower case; "" without one."""
    name = urlsplit(url).path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].casefold() if "." in name else ""


def commons_rendition(url: str, width: int, original: int | None = None) -> str:
    """A PNG/JPEG copy of the Commons file at ``url``, at most ``width`` wide.

    Bitmaps are never enlarged: Commons refuses widths past the file's own
    (``original``). Returns "" when ``url`` is no Commons original.
    """
    m = _COMMONS_FILE.match(url)
    if not m:
        return ""
    base, folder, name = m.groups()
    ext = extension(url)
    prefix, suffix = {
        "svg": ("", ".png"),
        "tif": ("lossy-page1-", ".jpg"),
        "tiff": ("lossy-page1-", ".jpg"),
        "pdf": ("page1-", ".jpg"),
        "djvu": ("page1-", ".jpg"),
    }.get(ext, ("", ""))
    limit = width if ext == "svg" or not original else min(width, original - 1)
    fits = [w for w in COMMONS_WIDTHS if w <= limit]
    size = fits[-1] if fits else COMMONS_WIDTHS[0]
    return f"{base}/thumb/{folder}/{name}/{prefix}{size}px-{name}{suffix}"
