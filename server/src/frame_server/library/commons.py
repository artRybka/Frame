"""Clean up Wikimedia Commons metadata (and repair what older versions stored).

Commons ``extmetadata`` values are rendered wikitext. The Artwork template
adds hidden QuickStatements spans (``title QS:P1476,pl:"..."``), multilingual
fields come as ``{{pl|...}}{{en|...}}`` blocks with visible language labels
("Polish: "), and plain tag stripping glues all of it into one string such as
``Polish:  Żniwiarkatitle QS:P1476,pl:"Żniwiarka"label QS:Lpl,"Żniwiarka"``.

:func:`commons_html` reads the HTML (used on import); :func:`commons_plain`
repairs text that was already flattened (used to fix stored items).
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from .markup import (
    VECTOR,
    commons_rendition,
    drop_tags,
    extension,
    strip_language_prefix,
    strip_markup,
)

if TYPE_CHECKING:
    from .models import Item
    from .repo import Library

PREFERRED_LANGS = ("pl", "en")

# Language labels as Commons renders them, in English and Polish interfaces.
LANGUAGE_NAMES: dict[str, tuple[str, ...]] = {
    "pl": ("Polish", "polski"),
    "en": ("English", "angielski"),
    "de": ("German", "Deutsch", "niemiecki"),
    "fr": ("French", "français", "francuski"),
    "ru": ("Russian", "русский", "rosyjski"),
    "uk": ("Ukrainian", "українська", "ukraiński"),
    "be": ("Belarusian", "białoruski"),
    "lt": ("Lithuanian", "lietuvių", "litewski"),
    "cs": ("Czech", "čeština", "czeski"),
    "sk": ("Slovak", "słowacki"),
    "it": ("Italian", "italiano", "włoski"),
    "es": ("Spanish", "español", "hiszpański"),
    "nl": ("Dutch", "Nederlands", "niderlandzki"),
    "la": ("Latin", "łaciński"),
    "hu": ("Hungarian", "węgierski"),
    "sv": ("Swedish", "szwedzki"),
}
_LANG_BY_NAME = {n.casefold(): code for code, names in LANGUAGE_NAMES.items() for n in names}
# A label starts the text, a line, or is glued to the previous block's last
# character ("ŻniwiarkaEnglish: ..."); "written in French: " is left alone.
_LABEL = re.compile(
    r"(?:^|(?<=\n)|(?<=\S))(?P<name>"
    + "|".join(sorted((re.escape(n) for n in _LANG_BY_NAME), key=len, reverse=True))
    + r")\s*:[ \t ]+",
    re.IGNORECASE,
)
# The hidden QuickStatements tails of the Artwork template's fields.
_QS_TAIL = re.compile(
    r"(?:title|label|date|medium|object type|genre|depicted people|depicted place"
    r"|inscription|location)?\s?QS:.*",
    re.DOTALL,
)
_QS_STRING = r'"((?:[^"\\]|\\.)*)"'
_QS_TITLE = re.compile(r"P1476,([a-z-]+):" + _QS_STRING)
_QS_LABEL = re.compile(r"\bL([a-z-]+),\s?" + _QS_STRING)
_QS_YEAR = re.compile(r"P571,\+?(\d{3,4})-")

_VOID = {"br", "hr", "img", "input", "meta", "link", "wbr", "col", "source", "area"}
_BLOCK = {"p", "div", "li", "tr", "table", "ul", "ol", "dd", "dt", "h1", "h2", "h3", "h4"}


class _Visible(HTMLParser):
    """Visible text, grouped by the outermost ``lang`` it sits in."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # (tag, hidden, lang) per open element.
        self.stack: list[tuple[str, bool, str | None]] = []
        self.parts: list[tuple[str | None, str]] = []

    def _hidden(self) -> bool:
        return bool(self.stack) and self.stack[-1][1]

    def _lang(self) -> str | None:
        return next((lang for _, _, lang in self.stack if lang), None)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID:
            if tag == "br" and not self._hidden():
                self.parts.append((self._lang(), "\n"))
            return
        a = {k: v or "" for k, v in attrs}
        style = a.get("style", "").replace(" ", "").casefold()
        classes = a.get("class", "").split()
        hidden = (
            self._hidden()
            or "display:none" in style
            or "language" in classes
            or "langlabel" in " ".join(classes)
        )
        self.stack.append((tag, hidden, a.get("lang") or None))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and not self._hidden():
            self.parts.append((self._lang(), "\n"))

    def handle_endtag(self, tag: str) -> None:
        if not any(t == tag for t, _, _ in self.stack):
            return  # stray end tag
        while self.stack:
            open_tag, hidden, _ = self.stack.pop()
            if open_tag == tag:
                break
        if tag in _BLOCK and not hidden and not self._hidden():
            self.parts.append((self._lang(), "\n\n" if tag == "p" else "\n"))

    def handle_data(self, data: str) -> None:
        if not self._hidden():
            self.parts.append((self._lang(), data))


def _tidy(text: str) -> str:
    text = text.replace(" ", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _pick(found: Sequence[tuple[str, str]], prefer: Sequence[str]) -> str | None:
    """The value in the most preferred language, else the first one."""
    for lang in prefer:
        for code, value in found:
            if code == lang:
                return value
    return found[0][1] if found else None


def _split_languages(text: str, prefer: Sequence[str]) -> str:
    """Keep one language of a flattened ``Polish: ...English: ...`` text."""
    labels = list(_LABEL.finditer(text))
    if not labels:
        return text
    blocks: list[tuple[str, str]] = []
    for n, m in enumerate(labels):
        end = labels[n + 1].start() if n + 1 < len(labels) else len(text)
        value = text[m.end() : end].strip()
        if value:
            blocks.append((_LANG_BY_NAME[m.group("name").casefold()], value))
    return _pick(blocks, prefer) or text[: labels[0].start()].strip()


def _qs_title(raw: str, prefer: Sequence[str]) -> str | None:
    found = [(m.group(1), m.group(2)) for m in _QS_TITLE.finditer(raw)]
    found += [(m.group(1), m.group(2)) for m in _QS_LABEL.finditer(raw)]
    preferred = [(code, v) for code, v in found if code in prefer]
    value = _pick(preferred, prefer)
    return value.replace('\\"', '"').strip() if value else None


def commons_plain(
    text: str, *, title: bool = False, prefer: Sequence[str] = PREFERRED_LANGS
) -> str:
    """Repair a value that was already flattened to text."""
    if not text:
        return ""
    text = drop_tags(text)
    if title and (qs := _qs_title(text, prefer)):
        return qs
    text = _QS_TAIL.sub("", text)
    return _tidy(_split_languages(text, prefer))


def commons_html(
    value: str, *, title: bool = False, prefer: Sequence[str] = PREFERRED_LANGS
) -> str:
    """Visible text of an ``extmetadata`` value, in one language, without QS."""
    if not value:
        return ""
    # Tags first: titles from Wikidata carry an edit icon (``<span class="…">``)
    # inside the QS string, and its quotes would end the string early.
    if title and (qs := _qs_title(html.unescape(drop_tags(value)), prefer)):
        return qs
    parser = _Visible()
    parser.feed(value)
    parser.close()
    groups: dict[str | None, list[str]] = {}
    for lang, data in parser.parts:
        groups.setdefault(lang, []).append(data)
    langs = [lang for lang, parts in groups.items() if lang and "".join(parts).strip()]
    if len(langs) > 1:
        chosen = _pick([(lang, lang) for lang in langs], prefer)
        text = "".join(groups[chosen])
    else:
        text = "".join(data for _, data in parser.parts)
    # Labels and QS outside the usual markup are caught by the text pass.
    return commons_plain(text, prefer=prefer)


def commons_year(text: str) -> int | None:
    """The first year in a date, or the one in its ``date QS:P571,+1879-...`` tail."""
    m = re.search(r"\b(1[0-9]{3})\b", commons_plain(text)) or _QS_YEAR.search(text)
    return int(m.group(1)) if m else None


# Bump when the cleaning rules change, so stored items are cleaned again.
# 2: markup left in titles of any source (Wikidata's edit icon), SVG links.
# 3: language prefixes in titles of any source ("en:Night Windows").
REPAIR_VERSION = 3
REPAIR_STATE_KEY = "commons_text_repair"
# The household's own photos: their captions are left as they were typed.
OWN_SOURCES = frozenset({"upload", "icloud"})


def _repairs(item: Item) -> dict[str, object]:
    fixes: dict[str, object] = {}
    for key in ("title", "artist"):
        value: str = getattr(item, key)
        clean = strip_markup(value) if "<" in value else value
        if item.source not in OWN_SOURCES:
            clean = strip_language_prefix(clean)
        if clean != value:
            fixes[key] = clean
    drawing = item.source in ("wmc", "openverse") and extension(item.image_url) in VECTOR
    if drawing and (image_url := commons_rendition(item.image_url, 3840, item.width)):
        fixes["image_url"] = image_url
        fixes["thumb_url"] = commons_rendition(item.image_url, 500, item.width)
    if item.source != "wmc":
        return fixes
    title = strip_language_prefix(commons_plain(str(fixes.get("title", item.title)), title=True))
    if title and title != item.title:
        fixes["title"] = title
    date_text = commons_plain(item.date_text)
    if date_text != item.date_text:
        fixes["date_text"] = date_text
    description = commons_plain(item.description)
    if description != item.description:
        fixes["description"] = description
    if item.year is None and (year := commons_year(item.date_text)):
        fixes["year"] = year
    return fixes


def repair_library(library: Library) -> int:
    """Clean titles, dates, descriptions and links stored by older versions.

    Runs once per :data:`REPAIR_VERSION`; returns how many items changed.
    """
    if library.get_state(REPAIR_STATE_KEY, 0) >= REPAIR_VERSION:
        return 0
    changed = 0
    _, items = library.query(include_excluded=True)
    with library.batch():
        for item in items:
            if fixes := _repairs(item):
                library.update(item.id, **fixes)
                changed += 1
        library.set_state(REPAIR_STATE_KEY, REPAIR_VERSION)
    return changed
