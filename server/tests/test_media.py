"""How a work is made, looked up where its source does not say
(frame_server.media): Wyspiański's pastel "Śpiący Staś" from WikiArt came
with no technique and the app painted it in oil (Mateusz 2026-11-12)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient
from test_holders import FakeWeb, _artwork_page, _claim, _commons, _labels

from frame_server.config import Settings
from frame_server.holders import Holders
from frame_server.library import Item, Library
from frame_server.library.museums import Access, europeana_medium
from frame_server.media import Media, commons_medium, wikidata_medium
from frame_server.service import FrameService
from frame_server.web.app import create_app


class FakeImporter:
    def __init__(self, sources: tuple[str, ...] = ("wikiart", "vam", "europeana", "wmc")) -> None:
        self._sources = list(sources)

    def sources(self) -> list[str]:
        return self._sources

    def access(self) -> Access:
        return Access(private_use=True)


class Web(FakeWeb):
    """Commons and Wikidata, and the records of WikiArt, the V&A and Europeana."""

    def __init__(self, *args: Any, records: dict[str, Any] | None = None, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.records = records or {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host in ("www.wikiart.org", "api.vam.ac.uk", "api.europeana.eu"):
            self.asked.append(request)
            key = request.url.params.get("id") or request.url.path.rsplit("/", 1)[-1]
            if key in self.records:
                return httpx.Response(200, json=self.records[key])
            return httpx.Response(404)
        return super().handler(request)


def _media(tmp_path: Path, web: Web) -> tuple[Media, Library]:
    library = Library(tmp_path / "lib.db")
    holders = Holders(library, web.client)
    return Media(library, FakeImporter(), holders), library  # type: ignore[arg-type]


def _stas(**fields: Any) -> Item:
    return Item(
        id="wikiart:58f489b6edc2c9a1b02ebd74",
        source="wikiart",
        source_id="58f489b6edc2c9a1b02ebd74",
        title="Sleeping Staś",
        artist="Stanisław Wyspiański",
        classification="Painting",
        url="https://www.wikiart.org/en/stanislaw-wyspianski/sleeping-stas-1904",
        **fields,
    )


# -- reading what the pages say ----------------------------------------------------


def test_commons_technique_templates() -> None:
    def page(value: str) -> str:
        return _artwork_page(f" |medium = {value}\n |dimensions = 1\n")

    assert commons_medium(page("{{Technique|pastel|paper}}")) == "pastel on paper"
    assert commons_medium(page("{{oil on canvas}}")) == "oil on canvas"
    assert (
        commons_medium(page("{{Technique |1= Black chalk|2= |and=|over= |adj= |mounted= }}"))
        == "Black chalk"
    )
    assert commons_medium(page("{{Technique|tempera|panel|and=gold}}")) == (
        "tempera and gold on panel"
    )
    assert commons_medium(page("Pastel on cardboard")) == "Pastel on cardboard"
    assert commons_medium(page("{{en|1=Oil on canvas}} {{pl|1=olej na płótnie}}")) == (
        "Oil on canvas"
    )
    assert commons_medium(page("<!-- unknown -->")) == ""
    assert commons_medium(page("{{unknown}}")) == ""
    assert commons_medium(_artwork_page(" |technique = {{Technique|watercolor|paper}}\n")) == (
        "watercolor on paper"
    )
    assert commons_medium(_artwork_page(" |wikidata = Q1\n")) == ""


def test_wikidata_materials_of_the_whole_first(tmp_path: Path) -> None:
    web = Web({}, {"Q2": _labels(en="pastel"), "Q3": _labels(en="paper"), "Q4": _labels(en="wood")})
    framed = _claim("Q4")
    framed["qualifiers"] = {"P518": [{}]}  # the frame's
    work = {"claims": {"P186": [_claim("Q2"), _claim("Q3"), framed]}}
    with web.client() as http:
        assert wikidata_medium(http, work) == "pastel, paper"
        assert wikidata_medium(http, {"claims": {"P186": [framed]}}) == "wood"
        assert wikidata_medium(http, {"claims": {}}) == ""


def test_wikidata_type_naming_a_technique(tmp_path: Path) -> None:
    web = Web({}, {"Q5": _labels(en="pastel artwork"), "Q6": _labels(en="artwork")})
    with web.client() as http:
        assert wikidata_medium(http, {"claims": {"P31": [_claim("Q5")]}}) == "pastel artwork"
        assert wikidata_medium(http, {"claims": {"P31": [_claim("Q6")]}}) == ""


def test_europeana_medium_in_english_and_by_concept() -> None:
    delft = {
        "proxies": [
            {"dctermsMedium": {"def": ["http://data.europeana.eu/concept/2728"]}},
            {
                "dcFormat": {"def": ["96.5 cm", "115.7 cm"]},
                "dctermsMedium": {"nl-NL": ["doek"], "en-GB": ["canvas"]},
            },
        ],
        "concepts": [
            {"about": "http://data.europeana.eu/concept/2728", "prefLabel": {"en": ["Canvas"]}}
        ],
    }
    assert europeana_medium(delft) == "Canvas, canvas"
    swedish = {"proxies": [{"dcFormat": {"sv": ["Olja på duk"]}}]}
    assert europeana_medium(swedish) == "Olja på duk"
    sizes = {"proxies": [{"dcFormat": {"def": ["96.5 cm", "12 x 14"]}}]}
    assert europeana_medium(sizes) == ""


# -- looking it up -----------------------------------------------------------------


def test_wikiart_record_names_the_pastel(tmp_path: Path) -> None:
    record = {
        "id": "58f489b6edc2c9a1b02ebd74",
        "title": "Sleeping Staś",
        "image": "https://uploads.wikiart.org/x.jpg!Large.jpg",
        "media": ["pastel", "paper"],
    }
    web = Web({}, {}, records={"58f489b6edc2c9a1b02ebd74": record})
    media, library = _media(tmp_path, web)
    library.upsert(_stas())
    assert media.look(_stas(), 5) == ("found", "pastel, paper")
    stored = library.get(_stas().id)
    assert stored is not None and stored.medium == "pastel, paper"
    # Known from now on: nothing asked again.
    asked = len(web.asked)
    assert media.known(stored) == ("found", "pastel, paper")
    assert media.look(stored, 5) == ("found", "pastel, paper")
    assert len(web.asked) == asked


def test_a_search_without_the_technique_keeps_the_one_found(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    library.upsert(_stas(medium="pastel, paper"))
    library.upsert(_stas())  # the search's answer again, with no technique
    stored = library.get(_stas().id)
    assert stored is not None and stored.medium == "pastel, paper"


def test_commons_page_then_wikidata(tmp_path: Path) -> None:
    web = Web(
        {"8030452": _artwork_page(" |medium = {{Technique|oil|canvas}}\n")},
        {},
    )
    media, library = _media(tmp_path, web)
    library.upsert(_commons())
    assert media.look(_commons(), 5) == ("found", "oil on canvas")

    web = Web(
        {"8030452": _artwork_page(" |wikidata = Q1\n")},
        {
            "Q1": {"claims": {"P186": [_claim("Q2"), _claim("Q3")]}},
            "Q2": _labels(en="oil paint"),
            "Q3": _labels(en="cardboard"),
        },
    )
    media, library = _media(tmp_path / "b", web)
    library.upsert(_commons())
    assert media.look(_commons(), 5) == ("found", "oil paint, cardboard")
    note = library.note(_commons().id, "medium")
    assert note is not None and note.data["from"] == "wikidata"


def test_nobody_says_and_it_is_not_asked_again_soon(tmp_path: Path) -> None:
    web = Web({"8030452": _artwork_page(" |date = 1920\n")}, {})
    media, library = _media(tmp_path, web)
    library.upsert(_commons())
    assert media.look(_commons(), 5) == ("none", "")
    stored = library.get(_commons().id)
    assert stored is not None and stored.medium == ""
    assert media.known(stored) == ("none", "")


def test_what_the_museum_named_is_never_looked_up(tmp_path: Path) -> None:
    web = Web({}, {})
    media, _ = _media(tmp_path, web)
    item = _stas(medium="oil on canvas")
    assert media.look(item, 5) == ("found", "oil on canvas")
    assert web.asked == []


def test_vam_object_record(tmp_path: Path) -> None:
    record = {"record": {"materialsAndTechniques": "Tempera on panel"}}
    web = Web({}, {}, records={"O135178": record})
    media, library = _media(tmp_path, web)
    icon = Item(id="vam:O135178", source="vam", source_id="O135178", classification="Icon")
    library.upsert(icon)
    assert media.look(icon, 5) == ("found", "Tempera on panel")


def test_the_card_asks_for_it(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    record = {"id": "58f489b6edc2c9a1b02ebd74", "image": "x.jpg", "media": ["pastel", "paper"]}
    web = Web({}, {}, records={"58f489b6edc2c9a1b02ebd74": record})
    svc.media = Media(svc.library, FakeImporter(), Holders(svc.library, web.client))  # type: ignore[arg-type]
    with TestClient(app) as client:
        # After the start's tidying, which leaves out works nobody keeps.
        svc.library.upsert(_stas(favorite=True))
        assert client.get(f"/api/library/items/{_stas().id}").json()["medium"] == ""
        view = client.post(f"/api/library/items/{_stas().id}/medium?wait=5").json()
        assert view == {"status": "found", "medium": "pastel, paper"}
        assert client.get(f"/api/library/items/{_stas().id}").json()["medium"] == "pastel, paper"


def test_a_record_that_cannot_be_read_is_asked_again(tmp_path: Path) -> None:
    web = Web({}, {})  # WikiArt answers 404 for everything but its records ...

    def refused(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.wikiart.org":
            return httpx.Response(500, text="Free API limit exceeded")
        return Web.handler(web, request)

    library = Library(tmp_path / "lib.db")
    holders = Holders(library, lambda: httpx.Client(transport=httpx.MockTransport(refused)))
    media = Media(library, FakeImporter(), holders)  # type: ignore[arg-type]
    library.upsert(_stas())
    assert media.look(_stas(), 5) == ("none", "")
    assert library.note(_stas().id, "medium") is None  # not "nobody knows" for a month
    assert media.known(_stas()) is None or media.known(_stas()) == ("none", "")


def test_the_cards_look_is_not_held_back_while_the_app_is_in_use() -> None:
    # As the background's, its requests waited while the app was in use:
    # the card asked, waited and got nothing (1.145.61 on the NAS).
    import threading

    from frame_server.library import hosts

    seen: list[tuple[str, bool]] = []

    def look() -> None:
        seen.append((hosts.purpose(), hosts.deferrable()))

    thread = threading.Thread(target=look, name="work-medium")
    thread.start()
    thread.join()
    assert seen == [("technika dzieła", False)]
