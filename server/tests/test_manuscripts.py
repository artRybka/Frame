"""„Rękopisy i miniatury” in Szukaj: the catalogue keeps no manuscripts, so
the museums that can filter by them are asked; the others stay quiet."""

from __future__ import annotations

from pathlib import Path

import httpx

from frame_server.library.models import PlaylistRules
from frame_server.library.museums import Access, Discovery, MetropolitanMuseum
from frame_server.library.paris import ParisMusees
from frame_server.library.smithsonian import Smithsonian
from frame_server.library.vam import VictoriaAndAlbert
from frame_server.library.vocabulary import MANUSCRIPTS, category_fits, museum_kind
from frame_server.library.yale import YaleMuseums
from frame_server.web.discover_api import MuseumSearch

MET_LEAF = {
    "objectID": 453359,
    "isPublicDomain": True,
    "primaryImage": "https://images.metmuseum.org/full.jpg",
    "primaryImageSmall": "https://images.metmuseum.org/small.jpg",
    "title": "Illustrated Manuscript",
    "classification": "Codices",
    "objectName": "Illustrated manuscript",
    "medium": "Ink, opaque watercolor and gold on paper",
}


def test_manuscripts_alone_are_asked_of_the_museums() -> None:
    rules = PlaylistRules(terms=[MANUSCRIPTS])
    assert museum_kind(rules.terms) == "manuscript"
    search = MuseumSearch(rules=rules, spec=Discovery(kind="manuscript"), keys=[], limit=8)
    assert not search.empty
    assert search.asked(["met", "vam"]) == ["met", "vam"]


def test_the_met_finds_manuscripts_in_every_department() -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"total": 1, "objectIDs": [453359]})
        return httpx.Response(200, json=MET_LEAF)

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        total, items = MetropolitanMuseum(http).discover(Discovery(kind="manuscript"))
    params = sent[0].url.params
    assert params["q"] == "manuscript" and "departmentId" not in params
    assert total == 1 and category_fits(items[0], [MANUSCRIPTS])


def test_the_va_asks_for_cuttings_from_manuscripts() -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"info": {"record_count": 0}, "records": []})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        VictoriaAndAlbert(http, access=Access(private_use=True)).discover(
            Discovery(kind="manuscript")
        )
    assert sent[0].url.params["q_object_type"] == "manuscript cutting"


def test_museums_without_manuscripts_bring_no_paintings_instead(tmp_path: Path) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"asked {request.url}")

    access = Access(private_use=True, paris_token="t", data_dir=tmp_path)
    spec = Discovery(kind="manuscript")
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        for source in (YaleMuseums, ParisMusees):
            assert source(http, access=access).discover(spec) == (0, [])
        # Its manuscripts are Freer's folios: asked for by type.
        smithsonian = Smithsonian(http, access=Access(smithsonian_key="k"))
        assert smithsonian.kinds["manuscript"] == "Manuscripts"
