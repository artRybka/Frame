"""The J. Paul Getty Museum, Los Angeles: its Open Content (CC0) works,
pictures at full size over IIIF (Mateusz 2026-11-06, for Rękopisy i
miniatury and Fotografia).

About 92 000 works are open: some 48 000 photographs (Talbot, Cameron,
Le Gray, Nadar, Atget, Watkins; stereographs left out), 7 000 leaves and
miniatures of illuminated manuscripts (the Ludwig collection), and a small
but famous set of paintings (783: Van Gogh's Irises, Manet, Turner) and
drawings. Its Linked Art API (data.getty.edu) has no search but SPARQL
(10-20 s for words), so this asks the search the museum's own site uses
(www.getty.edu/art/collection/api/search): not documented, answers within
a second and filters by open content, type and decade. A result names no
type, so each type is asked for on its own and the work takes the type it
was found by. Works not in the Open Content Program come only with
"Użytek prywatny" (the IIIF server gives them at full size too).
Checked from the owner's Mac and the cloud 2026-11-06 (getty-probe).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .models import Item
from .museums import PRIVATE_LICENCE, Discovery, Kind, Museum, plain_text

API = "https://www.getty.edu/art/collection/api/search"
SITE = "https://www.getty.edu/art/collection"
IIIF = "https://media.getty.edu/iiif/image"
CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"

#: The site's types ("classification_and_object_type") of each kind; a
#: photographic print is a "Print" too, so prints are not asked for.
TYPES: dict[str, tuple[str, ...]] = {
    "painting": ("Painting",),
    "drawing": ("Drawing",),
    "photograph": ("Photograph",),
    "manuscript": ("Illuminated Manuscript",),
    "sculpture": ("Sculpture",),
}
#: What a search without a kind asks for: the frame's pictures.
PICTURES = ("painting", "drawing")
#: Words left out of a kind's search: two pictures side by side are no
#: photograph for the frame.
NOT_WORDS = {"photograph": "-stereograph"}
#: The most decades one request may ask for ("decade_range", either).
MOST_DECADES = 40


def _year(text: str) -> int | None:
    found = re.search(r"\b(\d{3,4})\b", text)
    return int(found.group(1)) if found else None


def _nationality(suffix: str) -> str:
    """The "American" of "American, 1821 - 1887"; nothing of "1415 - 1425"."""
    first, comma, _ = suffix.partition(",")
    return first.strip() if comma and not re.search(r"\d", first) else ""


class GettyMuseum(Museum):
    key: str = "getty"
    name: str = "J. Paul Getty Museum"
    page_size = 100
    random_depth = 5000

    def _map(self, d: dict[str, Any], kind: str) -> Item | None:
        manifest = d.get("manifest") or {}
        uuid = str(manifest.get("thumbUuid") or "")
        work = str(d.get("id") or "").removeprefix("object/")
        if not uuid or not work or "/" in work:
            return None
        free = manifest.get("license") == CC0
        if not free and not self.private_use:
            return None
        makers = [p for p in d.get("producers") or [] if isinstance(p, dict)]
        maker = makers[0] if makers else {}
        artist = str(maker.get("primary_name") or "")
        # As the NGA's: "British, born India, 1815 - 1879", "Flemish,
        # active about 1460 - 1480".
        bio = str(maker.get("suffix") or "").strip()
        cultures = [c for c in d.get("culture") or [] if isinstance(c, str)]
        date = str(d.get("date_created") or "")
        parents = [p for p in d.get("parent_tree") or [] if isinstance(p, dict)]
        return self._item(
            work,
            title=str(d.get("primary_name") or "").strip(),
            # "Unknown", "Unknown maker, American".
            artist="" if artist.lower().startswith(("unknown", "anonymous")) else artist,
            artist_bio=bio,
            date_text=date,
            year=_year(date),
            medium="",
            classification=TYPES[kind][0],
            styles=cultures,
            subjects=[],
            culture=cultures[0] if cultures else _nationality(bio),
            credit="Courtesy of the J. Paul Getty Museum, Los Angeles",
            license="CC0 1.0" if free else PRIVATE_LICENCE,
            url=f"{SITE}{d.get('slug_with_path') or '/' + str(d.get('id'))}",
            # A leaf's manuscript ("Book of Hours"), shown with the title.
            description=str(parents[0].get("primary_name") or "") if parents else "",
            image_url=f"{IIIF}/{uuid}/full/!2560,2560/0/default.jpg",
            thumb_url=f"{IIIF}/{uuid}/full/600,/0/default.jpg",
        )

    def _get(
        self, words: str, kind: str, limit: int, page: int, decades: list[int] | None = None
    ) -> tuple[int, list[Item]]:
        text = " ".join(w for w in (words.strip(), NOT_WORDS.get(kind, "")) if w)
        params: list[tuple[str, Any]] = [
            ("q", text),
            ("from", (page - 1) * limit),
            ("size", limit),
            # Single photographs and leaves, not the albums and books that
            # hold them (their picture is the binding).
            ("is_parent", "false"),
            *(("classification_and_object_type", t) for t in TYPES[kind]),
            *(("decade_range", d) for d in decades or []),
        ]
        if not self.private_use:
            params.append(("open_content", "true"))
        resp = self.http.get(API, params=params)
        if resp.status_code == 400 and page > 1:
            # A page past a type's last: the site's search refuses it
            # instead of answering none (2026-11-09, at every search's
            # second page), and the search failed with it.
            return 0, []
        resp.raise_for_status()
        body = resp.json()
        hits = [h for h in body.get("data") or [] if isinstance(h, dict)]
        return int(body.get("total") or 0), [i for h in hits if (i := self._map(h, kind))]

    def _kinds(
        self, words: str, kinds: tuple[str, ...], limit: int, page: int, decades: list[int] | None
    ) -> tuple[int, list[Item]]:
        """Each kind on its own, a share of ``limit`` each, interleaved."""
        share = max(1, -(-limit // len(kinds)))
        answers = [self._get(words, k, share, page, decades) for k in kinds]
        rows = [items for _, items in answers]
        longest = max(len(r) for r in rows)
        mixed = [r[n] for n in range(longest) for r in rows if n < len(r)]
        return sum(t for t, _ in answers), mixed

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        return self.search_kind(query, "any", limit, page)

    def search_kind(
        self, query: str, kind: Kind, limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        query = plain_text(query)
        if kind == "any":
            return self._kinds(query, PICTURES, limit, page, None)
        if kind not in TYPES:
            return 0, []
        return self._get(query, kind, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.highlight or (spec.kind != "any" and spec.kind not in TYPES):
            return 0, []
        decades: list[int] | None = None
        if spec.year_from is not None or spec.year_to is not None:
            last = spec.year_to if spec.year_to is not None else 2020
            first = spec.year_from if spec.year_from is not None else last - 10 * MOST_DECADES
            if last < first:
                return 0, []
            decades = list(range(first // 10 * 10, last + 1, 10))[-MOST_DECADES:]
        if spec.kind == "any":
            return self._kinds(spec.style, PICTURES, limit, page, decades)
        return self._get(spec.style, spec.kind, limit, page, decades)

    #: The site's search finds a work by its id; the type is not said, so
    #: each is tried (most often a photograph).
    fetch_order: ClassVar[tuple[str, ...]] = (
        "photograph",
        "manuscript",
        "painting",
        "drawing",
        "sculpture",
    )

    def fetch(self, source_id: str) -> Item | None:
        if not re.fullmatch(r"[0-9a-f-]{36}", source_id):
            return None
        for kind in self.fetch_order:
            _, items = self._get(source_id, kind, 1, 1)
            if items:
                return items[0]
        return None
