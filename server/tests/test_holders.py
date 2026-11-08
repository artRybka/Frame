"""The museum a work is in, apart from where its picture is from
(Item.held_by, frame_server.holders)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.holders import Holders, commons_file, institution, work_qid
from frame_server.library import Item, ItemKind, Library
from frame_server.library.duplicates import RANKS
from frame_server.library.models import COLLECTIONS, ItemSummary, SharperCopy
from frame_server.service import FrameService
from frame_server.web.app import create_app

MNW = "Muzeum Narodowe w Warszawie"


def _commons(**fields: Any) -> Item:
    return Item(
        id="wmc:8030452",
        source="wmc",
        source_id="8030452",
        museum="Wikimedia Commons",
        title="Skąpiec",
        artist="Tadeusz Makowski",
        url="https://commons.wikimedia.org/wiki/File:Tadeusz_Makowski_Skapiec.jpg",
        **fields,
    )


def _artwork_page(params: str) -> str:
    return "=={{int:filedesc}}==\n{{Artwork\n |artist = {{Creator:Tadeusz Makowski}}\n" + params


# -- what is known without asking ----------------------------------------------


def test_collections_are_the_museums_among_the_sources() -> None:
    assert {source for source, rank in RANKS.items() if rank == 0} == COLLECTIONS


def test_a_museum_work_is_where_its_museum_says() -> None:
    item = Item(id="mnw:1", source="mnw", source_id="1", museum=MNW)
    assert item.held_by == MNW
    assert ItemSummary.of(item).held_by == MNW


def test_commons_is_where_the_picture_is_from_not_the_museum() -> None:
    assert _commons().held_by == ""


def test_a_sharper_copy_from_the_museum_names_it() -> None:
    copy = SharperCopy(url="u", item_id="mnw:7", source="mnw", museum=MNW, width=1, height=1)
    assert _commons(sharper=copy).held_by == MNW
    other = copy.model_copy(update={"source": "openverse", "museum": "Openverse"})
    assert _commons(sharper=other).held_by == ""


def test_looked_up_museum_wins_over_a_copy() -> None:
    copy = SharperCopy(url="u", item_id="mnw:7", source="mnw", museum=MNW, width=1, height=1)
    assert _commons(sharper=copy, holder="Muzeum Narodowe w Krakowie").held_by == (
        "Muzeum Narodowe w Krakowie"
    )


def test_europeana_names_its_provider_and_openverse_a_museum_host() -> None:
    item = Item(id="europeana:1", source="europeana", source_id="1", credit="Nationalmuseum")
    assert item.held_by == "Nationalmuseum"
    met = Item(
        id="openverse:1",
        source="openverse",
        source_id="1",
        url="https://www.metmuseum.org/art/collection/search/436535",
    )
    assert met.held_by == "Metropolitan Museum of Art"
    flickr = met.model_copy(update={"url": "https://www.flickr.com/photos/1"})
    assert flickr.held_by == ""


def test_photos_have_no_museum() -> None:
    photo = Item(id="upload:1", source="upload", source_id="1", kind=ItemKind.PHOTO, museum="x")
    assert photo.held_by == ""


def test_a_reimport_keeps_the_museum_looked_up(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    library.upsert(_commons(holder=MNW))
    library.upsert(_commons())
    stored = library.get("wmc:8030452")
    assert stored is not None and stored.held_by == MNW


# -- Commons pages ---------------------------------------------------------------


def test_commons_page_fields() -> None:
    page = _artwork_page(" |institution = {{Institution:Muzeum Narodowe w Krakowie}}\n}}\n")
    assert institution(page) == ("", "Muzeum Narodowe w Krakowie")
    assert institution(_artwork_page(" |institution = {{Institution|wikidata=Q153306}}\n")) == (
        "Q153306",
        "",
    )
    linked = _artwork_page(" |institution = [[w:pl:Muzeum Śląskie|Muzeum Śląskie]]\n")
    assert institution(linked) == ("", "Muzeum Śląskie")
    assert institution(_artwork_page(" |institution = \n")) == ("", "")
    assert work_qid(_artwork_page(" |wikidata = Q12345\n")) == "Q12345"
    assert work_qid(_artwork_page(" |wikidata = \n")) == ""


def test_commons_file_of_items() -> None:
    assert commons_file(_commons()) == ("8030452", "")
    openverse = Item(
        id="openverse:x",
        source="openverse",
        source_id="x",
        url="https://commons.wikimedia.org/w/index.php?curid=123",
    )
    assert commons_file(openverse) == ("123", "")
    by_title = openverse.model_copy(
        update={"url": "https://commons.wikimedia.org/wiki/File:Jan_Matejko%2C_Sta%C5%84czyk.jpg"}
    )
    assert commons_file(by_title) == ("", "File:Jan Matejko, Stańczyk.jpg")
    flickr = openverse.model_copy(update={"url": "https://www.flickr.com/photos/1"})
    assert commons_file(flickr) == ("", "")


# -- looking it up -----------------------------------------------------------------


class FakeWeb:
    """Commons and Wikidata as the lookup asks them."""

    def __init__(self, wikitext: dict[str, str], entities: dict[str, Any], p18: str = "") -> None:
        self.wikitext = wikitext  # by page id or title
        self.entities = entities
        self.p18 = p18
        self.asked: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        params = request.url.params
        if request.url.host == "commons.wikimedia.org":
            key = params.get("pageids") or params.get("titles") or ""
            if key not in self.wikitext:
                return httpx.Response(200, json={"query": {"pages": [{"missing": True}]}})
            page = {
                "title": key if not key.isdigit() else "File:X.jpg",
                "revisions": [{"slots": {"main": {"content": self.wikitext[key]}}}],
            }
            return httpx.Response(200, json={"query": {"pages": [page]}})
        if params.get("action") == "wbgetentities":
            ids = params["ids"].split("|")
            return httpx.Response(
                200, json={"entities": {i: self.entities[i] for i in ids if i in self.entities}}
            )
        if params.get("list") == "search":
            hits = [{"title": self.p18}] if self.p18 and "P18=" in params["srsearch"] else []
            return httpx.Response(200, json={"query": {"search": hits}})
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def _labels(pl: str = "", en: str = "") -> dict[str, Any]:
    labels = {}
    if pl:
        labels["pl"] = {"value": pl}
    if en:
        labels["en"] = {"value": en}
    return {"labels": labels}


def _claim(qid: str, rank: str = "normal", ended: bool = False) -> dict[str, Any]:
    claim: dict[str, Any] = {
        "rank": rank,
        "mainsnak": {"datavalue": {"value": {"id": qid}}},
    }
    if ended:
        claim["qualifiers"] = {"P582": [{}]}
    return claim


def _holders(tmp_path: Path, web: FakeWeb) -> tuple[Holders, Library]:
    library = Library(tmp_path / "lib.db")
    return Holders(library, web.client), library


def test_collection_of_the_work_on_wikidata(tmp_path: Path) -> None:
    web = FakeWeb(
        {"8030452": _artwork_page(" |wikidata = Q1\n")},
        {
            "Q1": {
                "claims": {
                    "P195": [
                        _claim("Q9", ended=True),  # a former owner
                        _claim("Q8"),
                        _claim("Q153306", rank="preferred"),
                    ]
                }
            },
            "Q153306": _labels(pl=MNW, en="National Museum in Warsaw"),
        },
    )
    holders, library = _holders(tmp_path, web)
    library.upsert(_commons())
    assert holders.look(_commons(), 5) == ("found", MNW)
    stored = library.get("wmc:8030452")
    assert stored is not None and stored.holder == MNW and stored.held_by == MNW
    asked = len(web.asked)
    assert holders.look(_commons(), 5) == ("found", MNW)  # known now
    assert len(web.asked) == asked


def test_institution_on_the_commons_page(tmp_path: Path) -> None:
    web = FakeWeb(
        {
            "8030452": _artwork_page(" |institution = {{Institution:National Museum in Kraków}}\n"),
            "Institution:National Museum in Kraków": "{{Institution\n |wikidata = Q1\n}}",
        },
        {"Q1": _labels(pl="Muzeum Narodowe w Krakowie", en="National Museum in Kraków")},
    )
    holders, _ = _holders(tmp_path, web)
    assert holders.find(_commons()) == "Muzeum Narodowe w Krakowie"


def test_institution_without_wikidata_keeps_its_name(tmp_path: Path) -> None:
    web = FakeWeb({"8030452": _artwork_page(" |institution = {{Institution:Louvre}}\n")}, {})
    holders, _ = _holders(tmp_path, web)
    assert holders.find(_commons()) == "Louvre"


def test_work_found_by_its_picture(tmp_path: Path) -> None:
    web = FakeWeb(
        {"8030452": _artwork_page(" |title = Skąpiec\n")},
        {"Q5": {"claims": {"P276": [_claim("Q6")]}}, "Q6": _labels(en="Private collection")},
        p18="Q5",
    )
    holders, _ = _holders(tmp_path, web)
    assert holders.find(_commons()) == "Private collection"


def test_nobody_knows_and_it_is_remembered(tmp_path: Path) -> None:
    web = FakeWeb({"8030452": _artwork_page(" |title = Skąpiec\n")}, {})
    holders, library = _holders(tmp_path, web)
    library.upsert(_commons())
    assert holders.look(_commons(), 5) == ("none", "")
    assert holders.known(_commons()) == ("none", "")
    later = datetime.now(UTC) + timedelta(days=31)
    holders.clock = lambda: later
    assert holders.known(_commons()) is None  # asked again after a month


def test_the_library_copy_from_a_museum(tmp_path: Path) -> None:
    web = FakeWeb({}, {})
    holders, library = _holders(tmp_path, web)
    library.upsert(
        Item(
            id="mnw:7",
            source="mnw",
            source_id="7",
            museum=MNW,
            title="Skąpiec",
            artist="Tadeusz Makowski",
            year=1932,
        )
    )
    item = _commons(year=1932)
    library.upsert(item)
    assert holders.find(item) == MNW
    assert web.asked == []


def test_a_failed_look_is_tried_again_soon(tmp_path: Path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    library = Library(tmp_path / "lib.db")
    holders = Holders(library, lambda: httpx.Client(transport=httpx.MockTransport(down)))
    assert holders.look(_commons(), 5) == ("none", "")
    assert holders.known(_commons()) == ("none", "")
    later = datetime.now(UTC) + timedelta(minutes=11)
    holders.clock = lambda: later
    assert holders.known(_commons()) is None


def test_museum_works_need_no_look(tmp_path: Path) -> None:
    holders, _ = _holders(tmp_path, FakeWeb({}, {}))
    item = Item(id="mnw:1", source="mnw", source_id="1", museum=MNW)
    assert holders.look(item, 1) == ("found", MNW)
    photo = Item(id="upload:1", source="upload", source_id="1", kind=ItemKind.PHOTO)
    assert holders.look(photo, 1) == ("off", "")


# -- the card ------------------------------------------------------------------------


def test_card_asks_for_the_museum(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    web = FakeWeb(
        {"8030452": _artwork_page(" |wikidata = Q1\n")},
        {"Q1": {"claims": {"P195": [_claim("Q2")]}}, "Q2": _labels(pl=MNW)},
    )
    svc.holders.http = web.client
    with TestClient(app) as client:
        # After the start's tidying, which leaves out works nobody keeps.
        svc.library.upsert(_commons(favorite=True))
        assert client.get("/api/library/items/wmc:8030452").json()["held_by"] == ""
        view = client.post("/api/library/items/wmc:8030452/holder?wait=5").json()
        assert view == {"status": "found", "name": MNW, "key": "Q2"}
        assert client.get("/api/library/items/wmc:8030452").json()["held_by"] == MNW
