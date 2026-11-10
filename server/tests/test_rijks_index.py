"""The Rijksmuseum's collection kept at home, read over OAI-PMH a few hours
a night (library/rijks_index.py, Mateusz 2026-11-10)."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from frame_server.library import rijks_index
from frame_server.library.museums import Access, Discovery, museum

PDM = "http://creativecommons.org/publicdomain/mark/1.0/"
INC = "http://rightsstatements.org/vocab/InC/1.0/"


def _edm(
    work: str,
    title: str,
    kind: str = "painting",
    *,
    maker: str = "Rembrandt van Rijn",
    date: str = "c. 1638",
    rights: str = PDM,
    top: bool = False,
    picture: bool = True,
    deleted: bool = False,
) -> str:
    """One OAI-PMH record as the Rijksmuseum writes it (trimmed)."""
    sets = ["260238", "261208"] + (["260214"] if top else [])
    header = "".join(f"<setSpec>{s}</setSpec>" for s in sets)
    if deleted:
        return (
            f'<record><header status="deleted"><identifier>https://id.rijksmuseum.nl/{work}'
            f"</identifier><datestamp>2026-11-10T00:00:00Z</datestamp>{header}</header></record>"
        )
    shown = (
        f'<edm:isShownBy rdf:resource="https://iiif.micr.io/{work}x/full/max/0/default.jpg"/>'
        if picture
        else ""
    )
    return f"""<record><header><identifier>https://id.rijksmuseum.nl/{work}</identifier>
<datestamp>2026-10-15T15:07:28Z</datestamp>{header}</header><metadata>
<rdf:RDF xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:edm="http://www.europeana.eu/schemas/edm/" xmlns:edmfp="http://www.europeanafashion.eu/edmfp/"
 xmlns:mrel="http://id.loc.gov/vocabulary/relators/" xmlns:ore="http://www.openarchives.org/ore/terms/"
 xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:skos="http://www.w3.org/2004/02/skos/core#">
<ore:Aggregation rdf:about="https://id.rijksmuseum.nl/{work}#aggregation">
<edm:isShownAt rdf:resource="https://www.rijksmuseum.nl/nl/collectie/object/{work}"/>
{shown}<edm:rights rdf:resource="{rights}"/></ore:Aggregation>
<edm:ProvidedCHO rdf:about="https://id.rijksmuseum.nl/{work}">
<dcterms:created xml:lang="en">{date}</dcterms:created>
<dc:type rdf:resource="https://id.rijksmuseum.nl/t-{kind}"/>
<dc:creator rdf:resource="https://id.rijksmuseum.nl/a-1"/>
<dc:description xml:lang="nl">Een beschrijving.</dc:description>
<dc:description xml:lang="en">A stone bridge under a stormy sky.</dc:description>
<dc:subject rdf:resource="https://id.rijksmuseum.nl/s-1"/>
<dc:title xml:lang="en">{title}</dc:title>
<dc:title xml:lang="nl">Een titel</dc:title>
<dcterms:medium rdf:resource="https://id.rijksmuseum.nl/m-canvas"/>
<dcterms:medium rdf:resource="https://id.rijksmuseum.nl/m-oil"/>
<edmfp:technique rdf:resource="https://id.rijksmuseum.nl/k-paint"/>
<mrel:spn xml:lang="en">Purchased with support</mrel:spn>
</edm:ProvidedCHO>
<edm:Agent rdf:about="https://id.rijksmuseum.nl/a-1">
<skos:prefLabel xml:lang="en">{maker}</skos:prefLabel></edm:Agent>
<skos:Concept rdf:about="https://id.rijksmuseum.nl/t-{kind}">
<skos:prefLabel xml:lang="en">{kind}</skos:prefLabel></skos:Concept>
<skos:Concept rdf:about="https://id.rijksmuseum.nl/s-1">
<skos:prefLabel xml:lang="en">landscape with bridge</skos:prefLabel></skos:Concept>
<skos:Concept rdf:about="https://id.rijksmuseum.nl/m-canvas">
<skos:prefLabel xml:lang="en">canvas</skos:prefLabel></skos:Concept>
<skos:Concept rdf:about="https://id.rijksmuseum.nl/m-oil">
<skos:prefLabel xml:lang="en">oil paint (paint)</skos:prefLabel></skos:Concept>
<skos:Concept rdf:about="https://id.rijksmuseum.nl/k-paint">
<skos:prefLabel xml:lang="en">paint</skos:prefLabel></skos:Concept>
</rdf:RDF></metadata></record>"""


def _page(records: list[str], token: str = "", size: int = 0, answered: str = "") -> bytes:
    resumption = (
        f'<resumptionToken completeListSize="{size}">{token}</resumptionToken>'
        if token
        else '<resumptionToken completeListSize="0"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
        f"<responseDate>{answered or '2026-11-10T01:30:00Z'}</responseDate>"
        f"<ListRecords>{''.join(records)}{resumption}</ListRecords></OAI-PMH>"
    ).encode()


class Oai:
    """The endpoint: pages by token, a list of changes by ``from``."""

    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages
        self.asked: list[dict[str, list[str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(rijks_index.OAI)
        query = parse_qs(urlsplit(str(request.url)).query)
        self.asked.append(query)
        if "resumptionToken" in query:
            key = query["resumptionToken"][0]
        elif "from" in query:
            key = "from=" + query["from"][0]
        else:
            key = ""
        if key not in self.pages:
            error = '<error code="badResumptionToken">gone</error>'
            body = f'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">{error}</OAI-PMH>'
            return httpx.Response(200, content=body.encode())
        return httpx.Response(200, content=self.pages[key])

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def _no_museum(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"the museum was asked: {request.url}")


def _nothing(request: httpx.Request) -> httpx.Response:
    """The museum's own search, finding nothing (asked for fewer than
    LOCAL_MIN works at home)."""
    assert "/search/collection" in str(request.url)
    return httpx.Response(200, json={"orderedItems": [], "partOf": {"totalItems": 0}})


def _rijks(tmp_path: Path, private_use: bool = False, answer: Any = _no_museum) -> Any:
    http = httpx.Client(transport=httpx.MockTransport(answer))
    return museum("rijks", http, Access(data_dir=tmp_path, private_use=private_use))


def _read(tmp_path: Path, oai: Oai, seconds: float = 3600) -> int:
    return rijks_index.INDEX.read(
        tmp_path, lambda: True, lambda s: True, seconds=seconds, http=oai.client()
    )


FIRST = [
    _edm("1", "Landscape with a Stone Bridge", top=True),
    _edm("2", "The Night Watch", date="1642"),
    _edm("3", "A Sketch of a Mill", "drawing", maker="Jacob van Ruisdael", date="1650 - 1660"),
    _edm("4", "Still in Copyright", maker="Karel Appel", date="1951", rights=INC),
    _edm("5", "No Picture", picture=False),
]
SECOND = [_edm(str(10 + n), f"Portrait {n}", date=f"{1600 + n}") for n in range(20)]


@pytest.fixture
def oai() -> Oai:
    return Oai({"": _page(FIRST, "t1", 25), "t1": _page(SECOND)})


@pytest.fixture(autouse=True)
def _fresh() -> Any:
    yield
    rijks_index.INDEX.failed_at = 0.0
    rijks_index.INDEX.failed_why = ""
    rijks_index.INDEX.reading = False


def test_the_collection_is_read_whole_and_then_searched_at_home(tmp_path: Path, oai: Oai) -> None:
    assert _read(tmp_path, oai) == 2
    assert [q.get("set") for q in oai.asked] == [["260238"], None]
    assert rijks_index.index_path(tmp_path).is_file()
    assert not rijks_index.reading_path(tmp_path).exists()

    source = _rijks(tmp_path)  # any request to the museum fails the test
    total, items = source.search("rembrandt", 24, 1)
    assert total == 22  # the work still in copyright is not shown
    assert items[0].id == "rijks:1" and items[0].highlight  # the Top 1000 first
    work = source.fetch("1")
    assert work is not None and work.title == "Landscape with a Stone Bridge"
    assert work.artist == "Rembrandt van Rijn" and work.year == 1638
    assert work.medium == "oil paint on canvas" and work.classification == "painting"
    assert work.description == "A stone bridge under a stormy sky."
    assert work.license == "Public Domain Mark 1.0"
    assert work.image_url == "https://iiif.micr.io/1x/full/max/0/default.jpg"
    assert work.thumb_url == "https://iiif.micr.io/1x/full/600,/0/default.jpg"
    # Subjects are searched too, descriptions are not.
    assert source.search("bridge landscape", 24, 1)[0] == 23
    assert _rijks(tmp_path, answer=_nothing).search("ruisdael", 24, 1)[0] == 1

    private = _rijks(tmp_path, private_use=True)
    found = private.fetch("4")
    assert found is not None and found.license.startswith("Prawa autorskie")


def test_works_without_a_picture_are_not_kept(tmp_path: Path, oai: Oai) -> None:
    _read(tmp_path, oai)
    index = rijks_index.local_index(tmp_path)
    assert index is not None and index.get("5") is None and index.get("1") is not None


def test_draws_and_kinds_come_from_home(tmp_path: Path, oai: Oai) -> None:
    _read(tmp_path, oai)
    source = _rijks(tmp_path)
    total, items = source.discover(Discovery(kind="drawing"), 24, 1)
    assert total == 1 and items[0].id == "rijks:3"
    total, _ = source.discover(Discovery(kind="painting", year_from=1600, year_to=1610), 24, 1)
    assert total == 11
    assert source.discover(Discovery(style="Baroque"), 24, 1) == (0, [])
    drawn = list(source.random_draw(Discovery(kind="painting"), random.Random(1)))
    assert len(drawn) == 22 and len({i.id for i in drawn}) == 22


def test_a_night_reads_part_and_the_next_takes_up_where_it_stopped(
    tmp_path: Path, oai: Oai
) -> None:
    def api(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"orderedItems": [], "partOf": {"totalItems": 0}})

    assert _read(tmp_path, oai, seconds=0) == 1  # the night's time is up
    assert rijks_index.reading_path(tmp_path).is_file()
    assert rijks_index.local_index(tmp_path) is None
    assert _rijks(tmp_path, answer=api).search("rembrandt", 24, 1) == (0, [])  # asked as before
    state = rijks_index.INDEX.state(tmp_path)
    assert state["reading"] and state["works"] == 4 and not state["index"]

    oai.asked.clear()
    assert _read(tmp_path, oai) == 1
    assert oai.asked == [{"verb": ["ListRecords"], "resumptionToken": ["t1"]}]
    assert rijks_index.local_index(tmp_path) is not None
    assert not rijks_index.INDEX.due(tmp_path)
    assert _read(tmp_path, oai) == 0  # nothing to read for two months


def test_the_night_stops_when_the_app_is_used(tmp_path: Path, oai: Oai) -> None:
    read = rijks_index.INDEX.read(
        tmp_path, lambda: False, lambda s: True, seconds=3600, http=oai.client()
    )
    assert read == 1 and rijks_index.INDEX.due(tmp_path)


def test_two_months_on_only_what_changed_is_read(tmp_path: Path, oai: Oai) -> None:
    _read(tmp_path, oai)
    store = rijks_index.Store(rijks_index.index_path(tmp_path))
    store.set(read_at=str(time.time() - rijks_index.REFRESH_SECONDS - 1))
    store.commit()
    store.close()
    assert rijks_index.INDEX.due(tmp_path)
    oai.pages["from=2026-11-10T01:30:00Z"] = _page(
        [_edm("2", "The Night Watch (restored)", date="1642"), _edm("3", "", deleted=True)],
        answered="2027-01-10T01:30:00Z",
    )
    oai.asked.clear()
    assert _read(tmp_path, oai) == 1
    assert oai.asked[0]["from"] == ["2026-11-10T01:30:00Z"] and oai.asked[0]["set"] == ["260238"]
    source = _rijks(tmp_path)
    work = source.fetch("2")
    assert work is not None and work.title == "The Night Watch (restored)"
    index = rijks_index.local_index(tmp_path)
    assert index is not None and index.get("3") is None
    asks = _rijks(tmp_path, answer=_nothing)
    assert asks.search("restored", 24, 1)[0] == 1 and asks.search("watch", 24, 1)[0] == 1
    store = rijks_index.Store(rijks_index.index_path(tmp_path))
    assert store.get("next_since") == "2027-01-10T01:30:00Z"
    store.close()


def test_a_lost_place_starts_the_reading_again(tmp_path: Path, oai: Oai) -> None:
    _read(tmp_path, oai, seconds=0)
    del oai.pages["t1"]  # the endpoint no longer knows the token
    assert _read(tmp_path, oai) == 0
    oai.pages["t1"] = _page(SECOND)
    assert _read(tmp_path, oai) == 2  # from the start, what was kept stays
    assert rijks_index.local_index(tmp_path) is not None


def test_a_failed_reading_says_why_and_keeps_its_place(tmp_path: Path, oai: Oai) -> None:
    _read(tmp_path, oai, seconds=0)
    broken = Oai({"t1": b"<html>busy</html>"})
    assert _read(tmp_path, broken) == 0
    state = rijks_index.INDEX.state(tmp_path)
    assert state["failed"] and state["reading"]
    assert _read(tmp_path, oai) == 0  # waits an hour after a failure
    rijks_index.INDEX.failed_at = 0.0
    assert _read(tmp_path, oai) == 1 and rijks_index.local_index(tmp_path) is not None


@pytest.mark.parametrize(
    ("date", "year"),
    [
        ("c. 1638", 1638),
        ("1863 - 1900", 1863),
        ("in or after 1793 - 1801", 1793),
        ("c. 800", 800),
        ("50 BC", -50),
        ("18th century", None),
        ("", None),
    ],
)
def test_years_from_the_museum_s_dates(date: str, year: int | None) -> None:
    assert rijks_index._year(date) == year


def test_the_medium_as_a_line() -> None:
    assert rijks_index.medium(["paint"], ["canvas", "oil paint (paint)"]) == "oil paint on canvas"
    assert rijks_index.medium(["etching"], ["paper"]) == "etching on paper"
    assert rijks_index.medium(["striking"], ["silver"]) == "striking, silver"
    assert rijks_index.medium([], ["paper"]) == "paper"
    assert rijks_index.medium([], []) == ""
