"""Wellcome Collection, London: an open catalogue API without a key.

Its pictures are prints, drawings and paintings gathered around the history
of medicine: Indian gouaches, Japanese woodcuts, Dürer, Rembrandt, Goya,
Hogarth, Gillray and Rowlandson (Mateusz 2026-11-04, "muzea brytyjskie").
Most carry the Public Domain Mark; works under CC BY and its non-commercial
variants come only with "Użytek prywatny". Medical pictures (diseased
bodies, anatomy, wounds) are left out. Pictures come over IIIF in full
size (often 2000-4000 px). No published request limits.

A work's title holds its description after the subject ("An election
banquet. Engraving by W. Hogarth, 1755."): the subject is the title, the
technique comes from the physical description.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .models import Item
from .museums import Discovery, Museum, cc_name, strip_html

#: Licences on offer to everyone, and with private use only.
PUBLIC = ("pdm", "cc-0")
PRIVATE = ("cc-by", "cc-by-nc", "cc-by-nc-nd")
LICENCES = {
    "pdm": "Public Domain Mark 1.0",
    "cc-0": "CC0 1.0",
    **{code: cc_name(code.removeprefix("cc-"), "4.0") for code in PRIVATE},
}

#: Genres (as the API's filter names them) of each kind of picture.
PAINTINGS = ("Paintings", "Gouaches", "Watercolor painting")
DRAWINGS = ("Drawings", "Watercolor painting")
PRINTS = (
    "Woodcuts",
    "Etching",
    "Engraving and Engravings",
    "Lithography",
    "Aquatint",
    "Wood engravings",
    "Caricature",
    "Prints",
)

#: Photographs and photomechanical copies: never what the frame looks for.
_NOT_ART = re.compile(r"\b(photo\w*|process print\w*|half-?tone\w*|reproduction)\b", re.IGNORECASE)

#: Medical pictures rather than art (Mateusz 2026-11-04: "niepokoi mnie ten
#: zbiór chorób i operacji"): diseased bodies (Christopher D'Alton's
#: watercolours for the Royal Free Hospital), anatomy, wounds, surgical
#: instruments. Scenes with doctors and surgeons (Dutch genre paintings,
#: portraits) stay.
_MEDICAL = re.compile(
    r"\b(diseas\w*|tumou?rs?|rash\w*|abs?cess\w*|lesions?|sores|ulcer\w*|swellings?|"
    r"gangren\w*|syphili\w*|smallpox|leprosy|cancer\w*|carcinom\w*|patholog\w*|"
    r"dermatolog\w*|anatom\w*|dissect\w*|viscera|skeletons?|circulatory|nervous system|"
    r"muscles|foetus\w*|fetus\w*|embryos?|deformit\w*|amputat\w*|surgical instruments?|"
    r"wounds?|injur\w*|corpses?|cadavers?|genital\w*|penis|vagina\w*|vulva|"
    r"royal free hospital|d' ?alton)\b",
    re.IGNORECASE,
)

#: Words that open the sentence describing the picture rather than its
#: subject ("Coloured etching by J. Gillray", "Pen and ink drawing").
_MODIFIER = (
    r"(?:(?:hand-)?colou?r(?:ed)?|line|stipple|wood|soft-ground|oil|pen|and|ink|pencil|"
    r"chalk|crayon|brush|wash|red|black|white|sepia|india|indian|water-?colou?r|tempera|"
    r"gouache|lithograph(?:ic)?|chromo-?lithograph(?:ic)?|mezzotint|aquatint|engraved|etched)"
)
_TECHNIQUE = (
    r"(?:oil painting|painting|water-?colou?r|gouache|drawing|sketch|woodcut|etching|engraving|"
    r"lithograph|chromolithograph|aquatint|mezzotint|print|pastel|tempera|photograph)s?"
)
_DESCRIPTION = re.compile(
    rf"^(?:(?:by|after)\b|(?:{_MODIFIER}[ -]){{0,4}}{_TECHNIQUE}\b)", re.IGNORECASE
)
_YEAR = re.compile(r"\b(1[0-9]{3})\b")


def split_title(title: str) -> tuple[str, str]:
    """ "An election banquet. Engraving by W. Hogarth, 1755." -> ("An
    election banquet", "Engraving"): the subject, and the technique the rest
    names (empty when the title is the subject only)."""
    title = title.strip()
    pieces = re.split(r"(?<=\.)\s+", title)
    for at in range(1, len(pieces)):
        if _DESCRIPTION.match(pieces[at]):
            subject = " ".join(pieces[:at]).rstrip(" .")
            technique = re.split(r"\s+(?:by|after|attributed|from|on)\b|,", pieces[at])[0]
            return subject or title, technique.strip(" .")
    return title.rstrip("."), ""


def _medium(physical: str) -> str:
    """ "1 print : etching, with engraving ; image 37.2 x 34.4 cm" ->
    "etching, with engraving"."""
    _, colon, rest = physical.partition(":")
    if not colon:
        return ""
    rest = re.sub(r"\([^)]*\)\s*:?", "", rest)
    return rest.split(";")[0].strip(" .:")


def _place(label: str) -> str:
    """ "Edo [Tokyo]" (or "Edo [Tokyo") -> "Edo", "[India]" -> "India"; the
    catalogue's "No place, unknown, or undetermined" -> ""."""
    if label.casefold().startswith("no place"):
        return ""
    label = re.sub(r"\s*\([^)]*\)", "", label)
    bare = re.sub(r"\s*\[[^\]]*(?:\]|$)", "", label).strip(" ,.:]")
    return bare or label.strip(" []?,.:")


class WellcomeCollection(Museum):
    key = "wellcome"
    name = "Wellcome Collection"
    api = "https://api.wellcomecollection.org/catalogue/v2"
    page_size = 100
    include = "contributors,production,genres,subjects,notes"
    kinds: ClassVar[dict[str, tuple[str, ...]]] = {
        "any": (*PAINTINGS, "Drawings", *PRINTS),
        "painting": PAINTINGS,
        "drawing": DRAWINGS,
        "print": PRINTS,
        "poster": ("Posters",),
    }

    def _licences(self) -> tuple[str, ...]:
        return (*PUBLIC, *PRIVATE) if self.private_use else PUBLIC

    def _map(self, d: dict[str, Any]) -> Item | None:
        thumb = d.get("thumbnail") or {}
        url = str(thumb.get("url") or "")
        licence = str((thumb.get("license") or {}).get("id") or "")
        if "/full/" not in url or licence not in self._licences() or not d.get("id"):
            return None
        iiif = url.split("/full/")[0].replace("/thumbs/", "/image/")
        genres = [str(g.get("label") or "") for g in d.get("genres") or []]
        physical = str(d.get("physicalDescription") or "")
        title, technique = split_title(str(d.get("title") or ""))
        if _NOT_ART.search(" ".join((*genres, technique, physical.partition(";")[0]))):
            return None
        subjects = [str(s.get("label")) for s in d.get("subjects") or [] if s.get("label")]
        if _MEDICAL.search(" ".join((str(d.get("title") or ""), *subjects))):
            return None
        people = [
            c
            for c in d.get("contributors") or []
            if c.get("agent", {}).get("type") != "Organisation"
        ]
        primary = next((c for c in people if c.get("primary")), people[0] if people else {})
        production = d.get("production") or []
        dates = [str(x.get("label") or "") for p in production for x in p.get("dates") or []]
        places = [str(x.get("label") or "") for p in production for x in p.get("places") or []]
        year = next((int(m.group(1)) for t in [*dates, title] if (m := _YEAR.search(t))), None)
        reference = str(d.get("referenceNumber") or "")
        return self._item(
            str(d["id"]),
            title=title,
            artist=str((primary.get("agent") or {}).get("label") or ""),
            date_text=dates[0].strip(" []?.") if dates else "",
            year=year,
            medium=_medium(physical) or technique,
            classification=", ".join(g for g in genres if g),
            subjects=subjects,
            culture=_place(places[0]) if places else "",
            credit=f"{self.name}, {reference}" if reference else self.name,
            license=LICENCES[licence],
            url=f"https://wellcomecollection.org/works/{d['id']}",
            description=strip_html(d.get("description")),
            image_url=f"{iiif}/full/!2560,2560/0/default.jpg",
            thumb_url=f"{iiif}/full/!600,600/0/default.jpg",
        )

    def _get(self, params: dict[str, Any], limit: int, page: int) -> tuple[int, list[Item]]:
        resp = self.http.get(
            f"{self.api}/works",
            params={
                **params,
                "workType": "k",  # pictures
                "items.locations.license": ",".join(self._licences()),
                "availabilities": "online",
                "include": self.include,
                "pageSize": min(limit, self.page_size),
                "page": page,
            },
        )
        if resp.status_code == 400:  # a page past the end
            return 0, []
        resp.raise_for_status()
        body = resp.json()
        items = [i for d in body.get("results") or [] if (i := self._map(d))]
        return int(body.get("totalResults") or len(items)), items

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if not query.strip():
            return self.discover(Discovery(kind="painting"), limit, page)
        return self._at_home(
            query,
            limit,
            page,
            lambda: self._get({"query": query.strip()}, limit, page),
            kinds=self.kinds["any"],
        )

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        genres = self.kinds.get(spec.kind)
        if spec.highlight or not genres:
            return 0, []
        if (index := self._index()) is not None:
            return self._from_dump(
                index, spec.style, kinds=genres, spec=spec, limit=limit, page=page
            )
        params: dict[str, Any] = {"genres.label": ",".join(genres)}
        if spec.style.strip():
            params["query"] = spec.style.strip()
        if spec.year_from is not None:
            params["production.dates.from"] = f"{spec.year_from:04d}-01-01"
        if spec.year_to is not None:
            params["production.dates.to"] = f"{spec.year_to:04d}-12-31"
        return self._get(params, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        if (record := self._from_index(source_id)) is not None:
            return self._map(record)
        resp = self.http.get(f"{self.api}/works/{source_id}", params={"include": self.include})
        if resp.status_code in (404, 410):
            return None
        resp.raise_for_status()
        return self._map(resp.json())
