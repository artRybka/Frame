"""Droga dzieła: how a work went from its maker to where it hangs now
(Mateusz 2026-11-10, "S1").

Museums keep the record: the Art Institute of Chicago its provenance and
the exhibitions it went to, the Cleveland Museum of Art its owners one by
one with their dates, the National Gallery of Art, the Rijksmuseum and the
Louvre their provenance as a text (the Louvre also its loans to
exhibitions), Wikidata the owners (P127) and exhibitions (P608) of works
any museum holds. A work from somewhere else (Wikimedia Commons, Europeana,
an archive's photograph) that hangs in one of these museums gets that
museum's record: by the museum's id on the work's Wikidata item, or by the
museum's own copy of the picture (``Item.sharper``). Haiku only retells
that record in Polish, as a few stops on a road: a year, a place, one
sentence, and what kind of stop it was (the app draws the road between
them). Code then keeps only stops whose every year and sum of money is in
the record; without a record, or with fewer than two stops left, the study
has no such section. Nothing is made up and nothing is looked up twice:
what was found (also nothing) is kept as a note of :data:`KIND`, looked for
in the background when the page opens.
"""

from __future__ import annotations

import logging
import math
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel

from ..library import Item, ItemKind, nga
from ..library.louvre import ARK as LOUVRE_ARK
from ..library.markup import strip_markup
from ..library.models import Note
from ..library.museums import client
from ..library.wikidata import Wikidata
from .client import HAIKU, AiUnavailable, request
from .daily import _object, _str

if TYPE_CHECKING:
    from ..library import Library
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "journey"
SWITCH = "journey"
VERSION = "journey-1"
#: "None" as it is kept since more records are read (the National Gallery,
#: the Rijksmuseum, the Louvre, and museums' records of works from
#: elsewhere): a "none" from before is looked for once more.
NONE_VERSION = "journey-1/records-2"
#: The record sent to the model, at most.
RECORD_CHARS = 7000
#: Exhibitions put in the record, at most (all are counted).
EXHIBITIONS_SENT = 30
#: A source that could not be asked is left alone this long (seconds):
#: the page asks on every refresh while a journey is being looked for.
RETRY_AFTER = 600.0
MAX_STOPS = 9
TEXT_MAX = 160
#: What kind of stop it is: the app's drawing for it.
KINDS = (
    "made",  # the maker's studio
    "shown",  # an exhibition
    "home",  # kept by someone at home
    "inherited",  # passed on by a will or to an heir
    "sold",  # sold or bought, often with its price
    "gift",  # given
    "travel",  # crossing a sea or moved far
    "war",  # war, seizure, hiding
    "stolen",  # theft and return
    "restored",  # conservation
    "museum",  # where it is now
)

SYSTEM = f"""You retell the journey of one artwork, from its maker to where it is now, \
for a Polish art app. You get the museum's own record: its provenance (who owned it, when, \
how it passed on) and the exhibitions it went to. Use only that record: never add an owner, \
a date, a price, a place or an event it does not give, and never guess why something happened. \
The record may be in French, and may end in the museum's notes: a year that is only a book's, a \
letter's or a catalogue's there is no stop.

Answer in Polish:
- "headline": at most 45 characters, the journey in a few words, e.g. "Z pracowni w Paryżu do \
Chicago".
- "lead": one sentence of at most 110 characters, what is most remarkable in this journey.
- "from_where": the first stop's place in the genitive with "z", e.g. "z Paryża"; "" when unknown.
- "stops": 2 to {MAX_STOPS} stops, oldest first: where it was made (when the record or the data \
says), each change of owner (a sale with its price when given, a gift, an heir), a war, theft \
or seizure, at most three exhibitions that matter (the first showing, one far away), and last \
where it is now (kind "museum" when it is a museum). Merge what happened in one place in one \
year into one stop. Leave out owners the record gives no date for unless they matter.
  Each stop: "year" as the record gives it ("1900", "1884–1886", "przed 1891", "ok. 1700"); \
"place": the city in Polish ("Paryż", "Nowy Jork"), "" when unknown; "lat" and "lon": the city's \
coordinates, 0 when there is no place; "kind": one of {", ".join(KINDS)}; "owner": true when \
the work comes to a new owner here (the maker counts as the first); "detour": true for an \
exhibition away from which the work came back to the same owner; "text": one sentence of at \
most {TEXT_MAX} characters, natural Polish, with the one or two most telling words (a name, a \
price) between ** and **. A sentence says only what the record's lines about this stop say: \
never join in an exhibition or an event from another line, and never repeat the year or the \
place, which the app shows beside it. Write prices and years exactly as the record does, only \
in Polish form ("800 franków", "20 000 dolarów")."""

SCHEMA = _object(
    headline=_str(),
    lead=_str(),
    from_where=_str(),
    stops={
        "type": "array",
        "items": _object(
            year=_str(),
            place=_str(),
            lat={"type": "number"},
            lon={"type": "number"},
            kind={"type": "string", "enum": list(KINDS)},
            owner={"type": "boolean"},
            detour={"type": "boolean"},
            text=_str(),
        ),
    },
)


class Stop(BaseModel):
    year: str
    place: str = ""
    lat: float = 0.0
    lon: float = 0.0
    kind: str = "home"
    owner: bool = False
    detour: bool = False
    #: One Polish sentence, the telling words between ** and **.
    text: str


class Journey(BaseModel):
    """The work's way to where it is now: the study's "Droga dzieła"."""

    headline: str
    lead: str = ""
    stops: list[Stop]
    #: From the first stop to the last, when both years are known.
    years: int | None = None
    #: As the crow flies from the first place to the last, when far.
    km: int | None = None
    #: "z Paryża": where ``km`` is counted from.
    from_where: str = ""
    #: Owners one after another, the maker first.
    hands: int | None = None
    #: Exhibitions in the museum's record.
    exhibitions: int | None = None
    #: Whose record it is ("Art Institute of Chicago", "Wikidata").
    source: str = ""


class Record(BaseModel):
    """What a museum says of a work's way: the text the model reads."""

    text: str
    exhibitions: int = 0
    source: str = ""


# -- the records -----------------------------------------------------------------------------


def _aic(http: httpx.Client, source_id: str, data_dir: Path | None) -> Record | None:
    resp = http.get(
        f"https://api.artic.edu/api/v1/artworks/{source_id}",
        params={"fields": "provenance_text,exhibition_history"},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    provenance = strip_markup(str(data.get("provenance_text") or "")).strip()
    shows = [s.strip() for s in str(data.get("exhibition_history") or "").split("\n") if s.strip()]
    if not provenance and not shows:
        return None
    text = f"Provenance: {provenance or '(none)'}"
    if shows:
        text += "\n\nExhibitions:\n" + "\n".join(strip_markup(s) for s in shows[:EXHIBITIONS_SENT])
    return Record(text=text, exhibitions=len(shows), source="Art Institute of Chicago")


def _cma(http: httpx.Client, source_id: str, data_dir: Path | None) -> Record | None:
    """By the record's id or the accession number (Wikidata's P11110)."""
    resp = http.get(f"https://openaccess-api.clevelandart.org/api/artworks/{source_id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    owners = sorted(data.get("provenance") or [], key=lambda p: p.get("sortorder") or 0)
    lines = [
        f"{p.get('date') or 'undated'}: {strip_markup(str(p.get('description') or ''))}"
        for p in owners
        if p.get("description")
    ]
    exhibitions = data.get("exhibitions") or {}
    shows = [
        strip_markup(str(e.get("description") or e.get("title") or ""))
        for part in ("current", "legacy")
        for e in exhibitions.get(part) or []
    ]
    shows = [s for s in shows if s]
    if not lines and not shows:
        return None
    text = "Provenance:\n" + ("\n".join(lines) or "(none)")
    if shows:
        text += "\n\nExhibitions:\n" + "\n".join(shows[:EXHIBITIONS_SENT])
    return Record(text=text, exhibitions=len(shows), source="Cleveland Museum of Art")


def _nga(http: httpx.Client, source_id: str, data_dir: Path | None) -> Record | None:
    """From the gallery's open data kept at home (library/nga.py): its
    provenance, the notes it gives after it last."""
    try:
        text = nga.provenance(data_dir, source_id)
    except sqlite3.Error as err:
        raise ValueError(f"the National Gallery's index: {err}") from err
    if text is None:  # no index yet, or one from before it kept this
        raise ValueError("the National Gallery's index is not ready")
    text = re.sub(r"\n{3,}", "\n\nNotes:\n", text.strip(), count=1)
    if not text:
        return None
    return Record(text=f"Provenance: {text}", source="National Gallery of Art")


#: Rijksmuseum's Linked Art: the type of its provenance statement.
_RIJKS_PROVENANCE = "http://vocab.getty.edu/aat/300444174"
_ENGLISH = "http://vocab.getty.edu/aat/300388277"


def _rijks(http: httpx.Client, source_id: str, data_dir: Path | None) -> Record | None:
    resp = http.get(
        f"https://id.rijksmuseum.nl/{source_id}", headers={"Accept": "application/ld+json"}
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    said = [
        r
        for r in resp.json().get("referred_to_by") or []
        if r.get("content")
        and any(c.get("id") == _RIJKS_PROVENANCE for c in r.get("classified_as") or [])
    ]
    english = [r for r in said if any(x.get("id") == _ENGLISH for x in r.get("language") or [])]
    if not said:
        return None
    # Its sources stand in braces: "{Hoet I, 1752, p. 99, no. 15.}".
    text = re.sub(r"\{[^{}]*\}", "", strip_markup(str((english or said)[0]["content"])))
    text = " ".join(text.split())
    return Record(text=f"Provenance: {text}", source="Rijksmuseum") if text else None


#: The Louvre's history of a work, at most (some go on into an essay).
LOUVRE_HISTORY_CHARS = 3500


def _louvre(http: httpx.Client, source_id: str, data_dir: Path | None) -> Record | None:
    """The entry's history ("objectHistory", French), its former owners,
    how and when it came, and the exhibitions it was lent to."""
    resp = http.get(f"{LOUVRE_ARK}{source_id.removeprefix('cl')}.json")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    try:
        entry = resp.json()
    except ValueError as err:  # the bot wall's page instead of the entry
        raise httpx.HTTPError(f"no JSON for {source_id}") from err
    if not isinstance(entry, dict):
        return None
    history = strip_markup(str(entry.get("objectHistory") or "")).strip()
    owners = [
        str(o.get("value") or "").strip()
        for o in entry.get("previousOwner") or []
        if isinstance(o, dict) and o.get("value")
    ]
    shows = [
        " ".join(str(e.get("value") or "").split())
        for e in entry.get("exhibition") or []
        if isinstance(e, dict) and e.get("value")
    ]
    if not history and not owners and not shows:
        return None
    came = []
    for a in entry.get("acquisitionDetails") or []:
        if not isinstance(a, dict) or not a.get("mode"):
            continue
        dates = "; ".join(
            f"{d.get('type') or 'date'}: {d.get('value')}"
            for d in a.get("dates") or []
            if isinstance(d, dict) and d.get("value")
        )
        came.append(f"{a['mode']} ({dates})" if dates else str(a["mode"]))
    text = f"History (the museum's own, in French):\n{history[:LOUVRE_HISTORY_CHARS] or '(none)'}"
    if owners:
        text += "\n\nFormer owners: " + "; ".join(owners)
    if came:
        text += "\n\nCame to the Louvre: " + "; ".join(came)
    if shows:
        text += "\n\nLent to exhibitions:\n" + "\n".join(shows[:EXHIBITIONS_SENT])
    return Record(text=text, exhibitions=len(shows), source="Musée du Louvre")


#: How a museum's record is asked for: (http, the work's id there, the data
#: folder).
Reader = Callable[[httpx.Client, str, Path | None], Record | None]
#: Museums whose own record tells the way.
MUSEUMS: dict[str, Reader] = {
    "aic": _aic,
    "cma": _cma,
    "nga": _nga,
    "rijks": _rijks,
    "louvre": _louvre,
}
#: The same museums by their name in the record.
MUSEUM_NAMES = (
    "Art Institute of Chicago",
    "Cleveland Museum of Art",
    "National Gallery of Art",
    "Rijksmuseum",
    "Musée du Louvre",
)
#: Wikidata's properties that hold a work's id in those museums: a work
#: from elsewhere that hangs there is asked for by it.
BRIDGES = {
    "P4610": "aic",  # Art Institute of Chicago artwork ID
    "P11110": "cma",  # Cleveland Museum of Art ID: the accession number
    "P4683": "nga",  # National Gallery of Art artwork ID
    "P13234": "rijks",  # Rijksmuseum ID (Linked Art)
    "P9394": "louvre",  # Louvre Museum ARK ID
}


def bridges(claims: dict[str, Any]) -> list[tuple[str, str]]:
    """(museum, the work's id there) for each of :data:`BRIDGES` the
    Wikidata item's ``claims`` give."""
    found = []
    for prop, museum in BRIDGES.items():
        for claim in claims.get(prop) or []:
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if claim.get("rank") != "deprecated" and isinstance(value, str) and value.strip():
                found.append((museum, value.strip()))
                break
    return found


def _time(claim: dict[str, Any], prop: str) -> str:
    for q in (claim.get("qualifiers") or {}).get(prop) or []:
        value = (q.get("datavalue") or {}).get("value")
        if isinstance(value, dict) and (match := re.match(r"[+-](\d{4})", str(value.get("time")))):
            return match.group(1)
    return ""


def _label(entity: dict[str, Any]) -> str:
    labels = entity.get("labels") or {}
    for lang in ("en", "pl"):
        if label := str(labels.get(lang, {}).get("value") or ""):
            return label
    return ""


def claims_of(http: httpx.Client, qid: str) -> dict[str, Any]:
    """The statements of the work's Wikidata item; {} without one."""
    if not qid:
        return {}
    work = Wikidata._entities(http, [qid], "claims").get(qid) or {}
    return work.get("claims") or {}


def from_wikidata(http: httpx.Client, qid: str) -> Record | None:
    """Owners (P127) and exhibitions (P608) of the work, with their years."""
    return from_claims(http, claims_of(http, qid))


def from_claims(http: httpx.Client, claims: dict[str, Any]) -> Record | None:
    owned = [c for c in claims.get("P127") or [] if c.get("rank") != "deprecated"]
    shown = [c for c in claims.get("P608") or [] if c.get("rank") != "deprecated"]
    if len(owned) < 2 and not shown:
        return None  # only the museum: no way to tell

    def target(claim: dict[str, Any]) -> str:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        return str(value.get("id") or "") if isinstance(value, dict) else ""

    ids = [t for t in (target(c) for c in [*owned, *shown]) if t]
    names = Wikidata._many(http, ids, "labels") if ids else {}

    def line(claim: dict[str, Any]) -> str:
        name = _label(names.get(target(claim)) or {})
        start, end = _time(claim, "P580"), _time(claim, "P582")
        span = f"{start}–{end}" if start and end else f"from {start}" if start else ""
        when = _time(claim, "P585") or span or (f"until {end}" if end else "")
        return f"{when or 'undated'}: {name}" if name else ""

    owners = [w for w in (line(c) for c in owned) if w]
    owners.sort(key=lambda w: (_YEAR.findall(w) or ["9999"])[0])
    shows = [w for w in (line(c) for c in shown) if w]
    text = "Owners (from Wikidata):\n" + ("\n".join(owners) or "(none)")
    if shows:
        text += "\n\nExhibitions:\n" + "\n".join(shows[:EXHIBITIONS_SENT])
    return Record(text=text, exhibitions=len(shows), source="Wikidata")


# -- checking the answer ------------------------------------------------------------------------

_YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-2][0-9])(?!\d)")
#: A sum or a number: three digits or more, maybe in groups ("800", "20 000", "$20,000").
_SUM = re.compile(r"\d{1,3}(?:[  .,]\d{3})+|\d{3,}")


def _digits(text: str) -> str:
    return re.sub(r"(?<=\d)[  .,](?=\d{3}\b)", "", text)


def _known(stop: dict[str, Any], record: str, item: Item) -> bool:
    """Every year and every sum the stop names is in the record, or is the
    work's own date."""
    said = f"{stop.get('year') or ''} {stop.get('text') or ''}"
    own = f"{item.date_text} {item.year or ''}"
    plain = _digits(record)
    for year in _YEAR.findall(said):
        if not re.search(rf"(?<!\d){year}(?!\d)", f"{record} {own}"):
            return False
    for amount in _SUM.findall(said):
        number = re.sub(r"\D", "", amount)
        if len(number) >= 4 and _YEAR.fullmatch(number):
            continue  # a year: checked above
        if not re.search(rf"(?<!\d){number}(?!\d)", plain):
            return False
    return True


def _km(a: Stop, b: Stop) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(h))


def _placed(stop: Stop) -> bool:
    return (
        bool(stop.place)
        and -90 <= stop.lat <= 90
        and -180 <= stop.lon <= 180
        and (stop.lat != 0 or stop.lon != 0)
    )


def read(data: dict[str, Any], record: Record, item: Item) -> Journey | None:
    """The model's answer as a journey, only what the record supports."""
    stops: list[Stop] = []
    for raw in (data.get("stops") or [])[:MAX_STOPS]:
        if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
            continue
        if not _known(raw, record.text, item):
            log.info("journey of %s: a stop not in the record left out: %r", item.id, raw)
            continue
        try:
            stop = Stop.model_validate(
                {
                    **raw,
                    "text": " ".join(str(raw["text"]).split())[: TEXT_MAX + 40],
                    "kind": raw.get("kind") if raw.get("kind") in KINDS else "home",
                }
            )
        except ValueError:
            continue
        stops.append(stop)
    if len(stops) < 2:
        return None
    if record.source in MUSEUM_NAMES:  # a museum's own record: it ends there
        last = (
            next(s for s in reversed(stops) if not s.detour)
            if any(not s.detour for s in stops)
            else stops[-1]
        )
        last.kind = "museum"
    years = [int(y) for s in (stops[0], stops[-1]) for y in _YEAR.findall(s.year)[:1]]
    span = years[1] - years[0] if len(years) == 2 and years[1] >= years[0] else None
    placed = [s for s in stops if _placed(s) and not s.detour]
    km = round(_km(placed[0], placed[-1]), -1) if len(placed) >= 2 else None
    hands = sum(1 for s in stops if s.owner)
    return Journey(
        headline=str(data.get("headline") or "").strip()[:60] or "Droga dzieła",
        lead=str(data.get("lead") or "").strip()[:160],
        stops=stops,
        years=span if span else None,
        km=int(km) if km and km >= 50 else None,
        from_where=str(data.get("from_where") or "").strip()[:40] if km and km >= 50 else "",
        hands=hands if hands >= 2 else None,
        exhibitions=record.exhibitions or None,
        source=record.source,
    )


# -- the journeys -------------------------------------------------------------------------------


class Journeys:
    """Works' journeys, kept as notes of :data:`KIND` (``{}``: none)."""

    def __init__(
        self,
        library: Library,
        claude: Claude,
        config: AiConfigStore,
        work_qid: Callable[[Item], str] = lambda item: "",
        http: Callable[[], httpx.Client] | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.library = library
        self.claude = claude
        self.config = config
        #: The work's Wikidata item (``Holders.work_qid``).
        self.work_qid = work_qid
        self.http = http
        #: Where the sources' own data are kept (the National Gallery's).
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._looking: set[str] = set()
        #: Works whose record could not be asked for, and when.
        self._failed: dict[str, float] = {}

    def enabled(self) -> bool:
        return self.config.enabled(SWITCH)

    def journey(self, item: Item) -> Journey | None:
        note = self.library.note(item.id, KIND)
        if note is None or note.prompt_version != VERSION or not note.data:
            return None
        return Journey.model_validate(note.data)

    def asked(self, item: Item) -> bool:
        note = self.library.note(item.id, KIND)
        if note is None:
            return False
        return note.prompt_version == (VERSION if note.data else NONE_VERSION)

    def look_soon(self, item: Item) -> bool:
        """Looks the journey up in the background, once; True while it does."""
        if item.kind != ItemKind.ARTWORK or self.asked(item) or not self.enabled():
            return False
        with self._lock:
            if item.id in self._looking:
                return True
            if time.monotonic() - self._failed.get(item.id, -RETRY_AFTER) < RETRY_AFTER:
                return False
            self._looking.add(item.id)
        threading.Thread(target=self._look, args=(item,), name="journey", daemon=True).start()
        return True

    def _look(self, item: Item) -> None:
        try:
            self.look(item)
        except Exception:
            log.exception("journey of %s", item.id)
        finally:
            with self._lock:
                self._looking.discard(item.id)

    def record(self, item: Item) -> Record | None:
        """The record of the work's way: its museum's; else, of a work from
        elsewhere, the museum's whose own copy of the picture it is shown
        in, then the museum's its Wikidata item names (:data:`BRIDGES`);
        else Wikidata's owners and exhibitions. Raises ``httpx.HTTPError``
        or ``ValueError`` when a source could not be asked."""
        asked: set[tuple[str, str]] = set()

        def ask(http: httpx.Client, museum: str, source_id: str) -> Record | None:
            reader = MUSEUMS.get(museum)
            if reader is None or not source_id or (museum, source_id) in asked:
                return None
            asked.add((museum, source_id))
            return reader(http, source_id, self.data_dir)

        with (self.http or client)() as http:
            found = ask(http, item.source, item.source_id)
            if found is None and item.sharper is not None:
                museum, _, source_id = item.sharper.item_id.partition(":")
                found = ask(http, museum, source_id)
            if found is None:
                claims = claims_of(http, self.work_qid(item))
                for museum, source_id in bridges(claims):
                    if museum == item.source:
                        continue  # its own museum: asked above
                    if (found := ask(http, museum, source_id)) is not None:
                        break
                if found is None:
                    found = from_claims(http, claims)
        if found is not None:
            found.text = found.text[:RECORD_CHARS]
        return found

    def look(self, item: Item) -> Journey | None:
        """The record retold, when there is one; kept (also none)."""
        try:
            found = self.record(item)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as err:
            log.info("journey of %s: %s", item.id, err)
            with self._lock:
                self._failed[item.id] = time.monotonic()
            return None  # not kept: asked again later
        journey: Journey | None = None
        model = ""
        if found is not None:
            facts = [
                f"Title: {item.title}",
                f"Maker: {item.artist or '?'}",
                f"Date: {item.date_text or item.year or '?'}",
                f"Now: {item.held_by or item.museum or found.source}",
                "",
                found.text,
            ]
            params = request(
                model=HAIKU,
                system=SYSTEM,
                content=[{"type": "text", "text": "\n".join(facts)}],
                schema=SCHEMA,
                max_tokens=4000,
            )
            try:
                answer = self.claude.ask(KIND, params)
            except AiUnavailable as err:
                log.info("journey of %s not asked: %s", item.id, err)
                with self._lock:
                    self._failed[item.id] = time.monotonic()
                return None
            journey = read(answer.data or {}, found, item)
            model = HAIKU
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model=model,
                prompt_version=VERSION if journey else NONE_VERSION,
                data=journey.model_dump() if journey else {},
            )
        )
        log.info(
            "journey of %s: %s",
            item.id,
            f"{len(journey.stops)} stops" if journey else "none" if found is None else "none kept",
        )
        return journey
