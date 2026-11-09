"""The Getty: its Open Content works, each kind asked for on its own."""

from __future__ import annotations

from typing import Any

import httpx

from frame_server.library.getty import CC0, IIIF, GettyMuseum
from frame_server.library.museums import PRIVATE_LICENCE, Access, Discovery
from frame_server.library.vocabulary import MANUSCRIPTS, PHOTOGRAPHY, category_fits, set_aside

IMAGE = "81288db0-270f-4049-a6c0-20c283c81b00"
WORK = "4b55bf5f-0000-4000-8000-000000000001"


def _hit(**changes: Any) -> dict[str, Any]:
    """A result of the site's search, as it came on 2026-11-06."""
    hit: dict[str, Any] = {
        "id": f"object/{WORK}",
        "primary_name": "The Three Marys",
        "is_parent": False,
        "producers": [
            {
                "primary_name": "Julia Margaret Cameron",
                "suffix": "British, born India, 1815 - 1879",
                "role": ["Photographer"],
            }
        ],
        "culture": [],
        "date_created": "1864",
        "manifest": {"license": CC0, "thumbUuid": IMAGE, "numItems": 1},
        "slug_with_path": "/object/106ABC",
    }
    return {**hit, **changes}


def _answer(sent: list[httpx.Request], hits: list[dict[str, Any]]):
    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"total": len(hits), "data": hits})

    return answer


def test_a_photograph_found_as_one_is_one() -> None:
    sent: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(_answer(sent, [_hit()]))) as http:
        total, items = GettyMuseum(http).search_kind("Cameron", "photograph")
    work = items[0]
    assert total == 1 and work.id == f"getty:{WORK}" and work.classification == "Photograph"
    assert work.artist == "Julia Margaret Cameron" and work.year == 1864
    assert work.artist_bio == "British, born India, 1815 - 1879" and work.culture == "British"
    assert work.image_url == f"{IIIF}/{IMAGE}/full/!2560,2560/0/default.jpg"
    assert work.license == "CC0 1.0" and work.url.endswith("/object/106ABC")
    assert category_fits(work, [PHOTOGRAPHY]) and set_aside(work)
    params = sent[0].url.params
    # Stereographs and the albums holding the photographs: never.
    assert params["q"] == "Cameron -stereograph" and params["is_parent"] == "false"
    assert params.get_list("classification_and_object_type") == ["Photograph"]
    assert params["open_content"] == "true"


def test_a_search_without_a_kind_asks_for_paintings_and_drawings() -> None:
    sent: list[httpx.Request] = []
    hits = [_hit(producers=[{"primary_name": "Vincent van Gogh", "suffix": "Dutch, 1853 - 1890"}])]
    with httpx.Client(transport=httpx.MockTransport(_answer(sent, hits))) as http:
        total, items = GettyMuseum(http).search("van Gogh", limit=8)
    kinds = [r.url.params["classification_and_object_type"] for r in sent]
    assert kinds == ["Painting", "Drawing"] and total == 2
    assert [i.classification for i in items] == ["Painting", "Drawing"]
    assert all(r.url.params["size"] == "4" for r in sent)
    assert not category_fits(items[0], [PHOTOGRAPHY])


def test_leaves_of_manuscripts_by_decade() -> None:
    sent: list[httpx.Request] = []
    leaf = _hit(producers=[{"primary_name": "Unknown maker, French"}], date_created="about 1460")
    with httpx.Client(transport=httpx.MockTransport(_answer(sent, [leaf]))) as http:
        getty = GettyMuseum(http)
        _, items = getty.discover(Discovery(kind="manuscript", year_from=1440, year_to=1465))
        assert getty.discover(Discovery(kind="poster")) == (0, [])
        assert getty.discover(Discovery(kind="decorative")) == (0, [])
    assert len(sent) == 1
    assert sent[0].url.params.get_list("decade_range") == ["1440", "1450", "1460"]
    assert sent[0].url.params["classification_and_object_type"] == "Illuminated Manuscript"
    assert items[0].artist == "" and items[0].year == 1460
    assert category_fits(items[0], [MANUSCRIPTS])


def test_works_outside_open_content_only_for_private_use() -> None:
    closed = _hit(
        manifest={"license": "https://rightsstatements.org/vocab/InC/1.0/", "thumbUuid": IMAGE}
    )
    sent: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(_answer(sent, [closed]))) as http:
        assert GettyMuseum(http).search_kind("x", "photograph")[1] == []
        home = GettyMuseum(http, access=Access(private_use=True))
        _, items = home.search_kind("x", "photograph")
    assert items[0].license == PRIVATE_LICENCE
    assert "open_content" not in sent[1].url.params


def test_a_work_is_found_again_by_its_id() -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        kind = request.url.params["classification_and_object_type"]
        hits = [_hit()] if kind == "Illuminated Manuscript" else []
        return httpx.Response(200, json={"total": len(hits), "data": hits})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        getty = GettyMuseum(http)
        found = getty.fetch(WORK)
        assert getty.fetch("../etc") is None
    assert found is not None and found.classification == "Illuminated Manuscript"
    assert len(sent) == 2 and sent[0].url.params["q"] == f"{WORK} -stereograph"


def test_a_page_past_a_types_last_is_empty_not_a_failure() -> None:
    """The site's search answers 400 to a page beyond a type's results, and
    every search's second page failed with it (2026-11-09)."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.params["classification_and_object_type"] == "Drawing":
            return httpx.Response(400, json={"error": "from beyond total"})
        return httpx.Response(200, json={"total": 30, "data": [_hit()]})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        total, items = GettyMuseum(http).search("Cameron", limit=8, page=2)
        assert total == 30 and len(items) == 1
        try:
            GettyMuseum(http).search("Cameron", limit=8, page=1)
        except httpx.HTTPStatusError:
            pass  # the first page's refusal is a failure still
        else:
            raise AssertionError("a first page refused is no empty page")
