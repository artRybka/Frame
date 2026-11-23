"""Copies of one work by the Wikidata item their pictures name
(frame_server.work_ids, Twins.join_work): three Commons files of van Gogh's
stolen "Poppy Flowers" looked nothing alike to the pictures and the judge
(Mateusz 2026-11-23)."""

from __future__ import annotations

from typing import Any

import httpx
from test_sharper import _print
from test_twins import _work

from frame_server.library.twins import pair_key
from frame_server.service import FrameService
from frame_server.work_ids import NONE, WorkIds

POPPIES = "Q4118041"


def _page(qid: str) -> str:
    return "=={{int:filedesc}}==\n{{Artwork\n |artist = {{Creator:Vincent van Gogh}}\n" + (
        f" |wikidata = {qid}\n}}}}\n" if qid else "}}\n"
    )


def _three(service: FrameService) -> None:
    """Three files of one painting that look nothing alike (made-up pictures
    of their own each), and a fourth work."""
    for n, title in enumerate(
        ("Vase with Viscaria (Vase with Lychnis, Poppy Flowers)", "Vase with Lychnis", "Lychnis"),
        start=1,
    ):
        _work(service, f"wmc:{n}", _print(40 + n), title=title, artist="Vincent van Gogh")
    _work(service, "wmc:9", _print(49), title="Sunflowers", artist="Vincent van Gogh")
    service.twins.look()


def _commons(pages: dict[str, str], entities: dict[str, Any] | None = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "commons.wikimedia.org":
            ids = request.url.params["pageids"].split("|")
            listed = [
                {"pageid": int(i), "revisions": [{"slots": {"main": {"content": pages[i]}}}]}
                for i in ids
                if i in pages
            ]
            return httpx.Response(200, json={"query": {"pages": listed}})
        asked = request.url.params["ids"].split("|")
        return httpx.Response(
            200, json={"entities": {q: (entities or {}).get(q, {}) for q in asked}}
        )

    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def _groups(service: FrameService, ids: list[str]) -> set[int | None]:
    grouped = service.library.works()
    return {grouped.group_index(i) for i in ids}


def test_pictures_naming_one_work_become_one(service: FrameService) -> None:
    _three(service)
    ids = ["wmc:1", "wmc:2", "wmc:3"]
    assert len(_groups(service, ids)) == 3  # the pictures could not tell
    pages = {"1": _page(POPPIES), "2": _page(POPPIES), "3": _page(POPPIES), "9": _page("")}
    works = WorkIds(service.library, service.twins, _commons(pages))
    read, joined = works.at_night()
    assert read == 4 and joined == 2
    assert len(_groups(service, ids)) == 1
    assert _groups(service, ["wmc:9"]) != _groups(service, ids)
    sunflowers = service.library.get("wmc:9")
    assert sunflowers is not None and sunflowers.work_qid == NONE
    entry = service.twins.log.entries()[0]
    assert entry["by"] == "wikidata" and POPPIES in entry["why"]
    # Read once: the next night asks Commons nothing.
    assert WorkIds(service.library, service.twins, _commons({})).at_night() == (0, 0)


def test_the_owners_word_keeps_them_apart(service: FrameService) -> None:
    _three(service)
    service.twins.separate("wmc:1", "wmc:2")
    pages = {"1": _page(POPPIES), "2": _page(POPPIES)}
    WorkIds(service.library, service.twins, _commons(pages)).at_night()
    assert len(_groups(service, ["wmc:1", "wmc:2"])) == 2


def test_a_detail_naming_the_work_stays_a_detail(service: FrameService) -> None:
    _three(service)
    service.library.update("wmc:3", detail_of="wmc:1")
    pages = {"1": _page(POPPIES), "2": _page(POPPIES), "3": _page(POPPIES)}
    WorkIds(service.library, service.twins, _commons(pages)).at_night()
    detail = service.library.get("wmc:3")
    assert detail is not None and detail.detail_of == "wmc:1" and not detail.copy_of
    assert len(_groups(service, ["wmc:1", "wmc:2"])) == 1


def test_a_museums_record_named_by_the_work_joins_it(service: FrameService) -> None:
    _work(service, "wmc:1", _print(41), title="Poppy Flowers", artist="Vincent van Gogh")
    _work(service, "met:436524", _print(42), title="Vase with Lychnis", artist="Vincent van Gogh")
    service.twins.look()
    entities = {
        POPPIES: {
            "claims": {
                "P3634": [{"mainsnak": {"datavalue": {"value": "436524"}}}],
            }
        }
    }
    WorkIds(service.library, service.twins, _commons({"1": _page(POPPIES)}, entities)).at_night()
    met = service.library.get("met:436524")
    assert met is not None and met.work_qid == POPPIES
    assert len(_groups(service, ["wmc:1", "met:436524"])) == 1
    assert pair_key("wmc:1", "met:436524") not in service.twins.apart()
