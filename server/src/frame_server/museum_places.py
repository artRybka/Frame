"""What Wikidata says of the places works are in (:mod:`.library.places`).

At night: the museums known only by a name (Europeana's data providers,
holders found before their Wikidata item was kept) get their item, and the
items get their name and city ("Museo del Prado", "Madryt"). While someone
types in Szukaj's "Muzeum": museums Wikidata knows by that name, also those
no work of the catalogue is in yet.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from .holders import _where as holders_where
from .library import Item, ItemKind
from .library.models import Note
from .library.places import QID, Place, fold, known_places
from .library.wikidata import API, Wikidata
from .library.wikidata_places import KINDS, claim_ids, statements

if TYPE_CHECKING:
    from .library import Library

log = logging.getLogger(__name__)

#: Names looked up, and places named, in one night at most.
NAMES_A_NIGHT = 60
PLACES_A_NIGHT = 200
#: Wikidata items asked about at once (the API's limit).
BATCH = 50
#: What a city is (P31): a city, a big city, a capital, a town, a
#: municipality with town rights; a district (Śródmieście, Camden) is not.
CITY_TYPES = frozenset(
    {
        "Q515",
        "Q1549591",
        "Q1637706",
        "Q5119",
        "Q200250",
        "Q3957",
        "Q22865",
        "Q21518270",
        "Q1093829",
        "Q13218382",
        "Q2264924",
        "Q3184121",
        "Q484170",
        "Q747074",
        "Q1066984",
        "Q15127012",
    }
)
#: How far up "located in" (P131) a city is looked for.
CITY_STEPS = 3
#: Words of a search hit's description that make it a place works are in.
_INSTITUTION = re.compile(
    r"\b(muse\w*|muze\w*|museo|musée|galler\w*|galeri\w*|galleria|pinakothe\w*|pinacote\w*|"
    r"collection|kolekcj\w*|zbi[oó]r\w*|librar\w*|bibliote\w*|church|kości[oó]\w*|cathedral|"
    r"katedr\w*|basilica|bazylik\w*|abbey|opactw\w*|monaster\w*|klasztor\w*|palace|pałac\w*|"
    r"castle|zamek|zamku|kunsthalle|kunstmuseum|kunsthistorisches|archive|archiwum|"
    r"chapel|kaplic\w*|academy|akademi\w*)\b",
    re.IGNORECASE,
)


#: How wide a place's picture is asked for (a band across the panel, 2×).
PICTURE_WIDTH = 720


class PlaceHit(BaseModel):
    """A museum Szukaj's "Muzeum" can choose."""

    key: str
    name: str
    city: str = ""
    #: Works of the catalogue in it (0: one Wikidata knows of, none here yet).
    count: int = 0
    #: A work of the place to show beside it, "" when there is none.
    item_id: str = ""
    #: Its own collection is one of our sources ("rijks").
    source: str = ""
    #: A picture of a work in it, for a place with none in the catalogue
    #: (``GET /api/places/<key>/picture`` finds one); "" when unknown.
    picture: str = ""


def commons_picture(file: str, width: int = PICTURE_WIDTH) -> str:
    """The address of a Commons file, ``width`` pixels wide."""
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + quote(file.replace(" ", "_"))
        + f"?width={width}"
    )


def _label(entity: dict[str, Any]) -> str:
    labels = entity.get("labels") or {}
    for lang in ("pl", "en"):
        if label := str((labels.get(lang) or {}).get("value") or ""):
            return label
    return ""


def _ids(entity: dict[str, Any], prop: str) -> list[str]:
    out: list[str] = []
    for claim in (entity.get("claims") or {}).get(prop) or []:
        if claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            out.append(value["id"])
    return out


class MuseumPlaces:
    """Asks Wikidata about the places of the catalogue's works."""

    def __init__(self, library: Library, http: Callable[[], httpx.Client]) -> None:
        self.library = library
        self.http = http

    # -- at night ------------------------------------------------------------------

    def at_night(self, quiet: Callable[[], bool] = lambda: True) -> int:
        """Names into items, items into names and cities; how many were
        learnt."""
        learnt = self.originals(quiet) + self.find_items(quiet) + self.name_places(quiet)
        if learnt:
            self.library.save_places()
        return learnt

    def find_items(self, quiet: Callable[[], bool] = lambda: True) -> int:
        """The Wikidata items of museums known only by their names."""
        places = known_places()
        names: dict[str, str] = {}
        for item in self.library.all_items():
            key = item.held_at
            if key.startswith("name:"):
                names.setdefault(key, item._held_by())
        found = 0
        with self.http() as http:
            for name in places.unresolved(names.values())[:NAMES_A_NIGHT]:
                if not quiet():
                    break
                try:
                    hits = self.search(http, name, 3)
                except (httpx.HTTPError, ValueError) as err:
                    log.info("museum %r: %s", name, err)
                    break
                exact = [h for h in hits if fold(h[1]) == fold(name)]
                if hit := (exact or hits)[:1]:
                    places.alias(name, hit[0][0])
                    found += 1
                else:
                    places.not_found(name)
        return found

    def name_places(self, quiet: Callable[[], bool] = lambda: True) -> int:
        """Names and cities of the places of the catalogue's works."""
        places = known_places()
        chosen = [
            key
            for playlist in self.library.playlists()
            for key in (*playlist.rules.places, *playlist.rules.exclude_places)
        ]
        # Those playlists choose first: their chips show the names.
        keys = places.unnamed([*chosen, *(item.held_at for item in self.library.all_items())])
        keys = keys[:PLACES_A_NIGHT]
        named = 0
        with self.http() as http:
            for start in range(0, len(keys), BATCH):
                if not quiet():
                    break
                try:
                    named += self._name(http, keys[start : start + BATCH])
                except (httpx.HTTPError, ValueError) as err:
                    log.info("places' names: %s", err)
                    break
        return named

    def _name(self, http: httpx.Client, keys: list[str]) -> int:
        entities = Wikidata._entities(http, keys, "labels|claims")
        cities = self._cities(http, entities)
        places = known_places()
        named = 0
        for key in keys:
            entity = entities.get(key) or {}
            if name := _label(entity):
                places.learn(key, name, cities.get(key, ""))
                named += 1
        return named

    def _cities(self, http: httpx.Client, entities: dict[str, Any]) -> dict[str, str]:
        """The city each of ``entities`` is in, climbing "located in" a few
        steps (a museum in Śródmieście is in Warszawa)."""
        at = {k: (_ids(e, "P131")[:1] or [""])[0] for k, e in entities.items()}
        found: dict[str, str] = {}
        for _ in range(CITY_STEPS):
            asked = sorted({v for k, v in at.items() if v and k not in found})
            if not asked:
                break
            up: dict[str, Any] = {}
            for start in range(0, len(asked), BATCH):
                up.update(Wikidata._entities(http, asked[start : start + BATCH], "labels|claims"))
            for key, where in list(at.items()):
                if key in found or not where:
                    continue
                entity = up.get(where) or {}
                if CITY_TYPES & set(_ids(entity, "P31")):
                    found[key] = _label(entity)
                else:
                    at[key] = (_ids(entity, "P131")[:1] or [""])[0]
        return found

    # -- reproductions ------------------------------------------------------------------

    def originals(self, quiet: Callable[[], bool] = lambda: True) -> int:
        """Reproductions of paintings (:func:`reproduction`) placed where
        their originals are; how many were."""
        asked = self.library.notes(ORIGINAL_NOTE)
        waiting = [
            (item, made)
            for item in self.library.all_items()
            if not item.reproduction
            and (made := reproduction(item))
            and (item.id not in asked or asked[item.id].prompt_version != ORIGINAL_VERSION)
        ]
        found = 0
        with self.http() as http:
            for item, made in waiting[:ORIGINALS_A_NIGHT]:
                if not quiet():
                    break
                try:
                    qid, name = self.original_place(http, item)
                except (httpx.HTTPError, ValueError, KeyError) as err:
                    log.info("original of %s: %s", item.id, err)
                    break
                if qid:
                    self.library.update(item.id, place=qid, holder=name, reproduction=made)
                    log.info("%s is a copy of a work in %s (%s)", item.id, name, qid)
                    found += 1
                self.library.save_note(
                    Note(
                        item_id=item.id,
                        kind=ORIGINAL_NOTE,
                        model="",
                        prompt_version=ORIGINAL_VERSION,
                        data={"place": qid},
                    )
                )
        return found

    def original_place(self, http: httpx.Client, item: Item) -> tuple[str, str]:
        """Where the painting ``item`` copies is: (its Wikidata item, its
        name); ("", "") when Wikidata does not know the painting."""
        creators = self._people(http, item.artist.split("\n")[0])
        words = [w for w in re.findall(r"[^\W\d_]{3,}", item.title)][:6]
        if not creators or not words:
            return "", ""
        resp = http.get(
            API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": " ".join(
                    [
                        *words,
                        statements("P170", tuple(creators)),
                        statements("P31", PAINTINGS),
                    ]
                ),
                "srnamespace": 0,
                "srlimit": 1,
                "srprop": "",
                "format": "json",
            },
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search") or []
        if not hits:
            return "", ""
        work = str(hits[0]["title"])
        entity = Wikidata._entities(http, [work], "claims").get(work) or {}
        where = holders_where(entity)[:1]
        if not where:
            return "", ""
        place = Wikidata._entities(http, where, "labels").get(where[0]) or {}
        return where[0], _label(place)

    @staticmethod
    def _people(http: httpx.Client, name: str) -> list[str]:
        """Wikidata's items of artists called ``name`` (a few, the likeliest
        first)."""
        resp = http.get(
            API,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "type": "item",
                "limit": 7,
                "format": "json",
            },
        )
        resp.raise_for_status()
        out: list[str] = []
        for hit in resp.json().get("search") or []:
            description = str(hit.get("description") or "")
            if re.search(r"\d{3,4}|painter|artist|malarz|sculptor|engraver", description, re.I):
                out.append(str(hit["id"]))
        return out[:3]

    # -- while typing ------------------------------------------------------------------

    @staticmethod
    def search(http: httpx.Client, text: str, limit: int = 7) -> list[tuple[str, str, str]]:
        """Museums (churches, libraries) Wikidata knows by ``text``: (item,
        name, description), Polish where it has them."""
        resp = http.get(
            API,
            params={
                "action": "wbsearchentities",
                "search": text,
                "language": "pl",
                "uselang": "pl",
                "type": "item",
                "limit": 20,
                "format": "json",
            },
        )
        resp.raise_for_status()
        out: list[tuple[str, str, str]] = []
        for hit in resp.json().get("search") or []:
            qid = str(hit.get("id") or "")
            description = str(hit.get("description") or "")
            name = str(hit.get("label") or "")
            if QID.match(qid) and name and _INSTITUTION.search(f"{description} {name}"):
                out.append((qid, name, description))
            if len(out) == limit:
                break
        return out

    def picture(self, key: str) -> str:
        """A Commons file of a work in the place ``key`` (a painting first),
        found once and kept; "" when Wikidata knows none."""
        places = known_places()
        known = places.picture(key)
        if known is not None:
            return known
        qid = places.canon(key)
        if not QID.match(qid):
            return ""
        with self.http() as http:
            file = self._picture(http, qid)
        places.pictured(qid, file)
        self.library.save_places()
        return file

    @staticmethod
    def _picture(http: httpx.Client, qid: str) -> str:
        for kinds in (KINDS["painting"], KINDS["any"]):
            resp = http.get(
                API,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": " ".join(
                        [statements("P195", (qid,)), statements("P31", kinds), "haswbstatement:P18"]
                    ),
                    "srnamespace": 0,
                    "srlimit": 1,
                    "srprop": "",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            found = resp.json().get("query", {}).get("search") or []
            if not found:
                continue
            work = str(found[0]["title"])
            entity = Wikidata._entities(http, [work], "claims").get(work) or {}
            files = claim_ids(entity, "P18")
            if files:
                return files[0]
        return ""

    def hits(self, text: str, limit: int = 7) -> list[PlaceHit]:
        """Museums Wikidata knows by ``text``, for Szukaj's "Muzeum"."""
        places = known_places()
        with self.http() as http:
            found = self.search(http, text, limit)
        out: list[PlaceHit] = []
        heard = False
        for qid, name, _ in found:
            place: Place | None = places.place(qid)
            if place is None and not places.name(qid):
                places.heard(qid, name)
                heard = True
            out.append(
                PlaceHit(
                    key=qid,
                    name=place.name if place else name,
                    city=place.city if place else "",
                    source=place.source if place else "",
                    picture=commons_picture(file) if (file := places.picture(qid)) else "",
                )
            )
        if heard:
            self.library.save_places()
        return out


# -- reproductions -------------------------------------------------------------------

#: Ways of copying a picture that came long after the old masters, with the
#: year they came, and what the card calls them. A "painting" by Jan van Eyck
#: in such a technique is a copy: its place is the original's (Mateusz
#: 2026-11-08, wariant A). Engravings "after" a painting stay works of their
#: own, kept where they are.
COPYING: tuple[tuple[re.Pattern[str], int, str], ...] = (
    (re.compile(r"chromo-?lithogra\w*|chromolitogra\w*", re.IGNORECASE), 1837, "Chromolitografia"),
    (re.compile(r"oleogra\w*|oleodruk\w*", re.IGNORECASE), 1860, "Oleodruk"),
    (re.compile(r"photogravure|heliogravure|fotograwiur\w*", re.IGNORECASE), 1850, "Fotograwiura"),
    (re.compile(r"collotype|lichtdruck|światłodruk\w*", re.IGNORECASE), 1856, "Światłodruk"),
    (re.compile(r"half-?tone|process print|autotyp\w*", re.IGNORECASE), 1880, "Autotypia"),
    (re.compile(r"\bphotograph\w*|\bfotografi\w*", re.IGNORECASE), 1839, "Fotografia"),
)
#: An artist's life in their bio or name: "ok. 1390–1441", "(1390-1441)".
_LIFE = re.compile(r"(\d{3,4})\s*[–-]\s*(\d{3,4})")
#: Words of "a copy after": "after J. van Eyck", "nach", "d'après", "według".
_AFTER = re.compile(r"\b(after|nach|d['’]apr[eè]s|naar|według|wg\.?)\b", re.IGNORECASE)
#: What a painting is (P31) on Wikidata.
PAINTINGS = KINDS["painting"]
#: Reproductions looked up in one night at most.
ORIGINALS_A_NIGHT = 30
ORIGINAL_NOTE = "original"
ORIGINAL_VERSION = "original-1"


def reproduction(item: Item) -> str:
    """What ``item``'s picture is when it is a later copy of an older
    painting ("Chromolitografia"), "" when it is the work itself: its
    technique came after the artist died, or it says "after" the artist."""
    if item.kind != ItemKind.ARTWORK or item.look is not None or not item.artist:
        return ""
    told = " ".join((item.medium, item.classification, item.title, item.description[:400]))
    life = _LIFE.search(f"{item.artist_bio} {item.artist}")
    died = int(life.group(2)) if life else None
    for pattern, since, name in COPYING:
        if not pattern.search(told):
            continue
        if died is not None and died < since:
            return name
        if died is None and _AFTER.search(told):
            return name
    return ""
