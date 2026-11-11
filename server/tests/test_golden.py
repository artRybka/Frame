"""The decisions made so far as test data, and the measurements of the
slow steps (docs/PLAN.md 3.3zzz154)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_sharper import _print
from test_twins import _work as _picture

from frame_server import golden
from frame_server.library.duplicates import same_work
from frame_server.library.models import Item, ItemKind
from frame_server.service import FrameService


def _client(service: FrameService) -> TestClient:
    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    return TestClient(app)


def _settled(service: FrameService) -> None:
    """A copy told by its picture, two copies told by their descriptions, a
    detail and a pair the owner kept apart."""
    painting = _print(1, (600, 700))
    _picture(service, "wmc:1", painting, title="Lekcja muzyki", year=1662)
    _picture(service, "wikiart:2", painting.resize((420, 490)), title="The music lesson")
    service.twins.look()
    other = _print(2, (600, 700))
    _picture(service, "met:10", other, title="View of Delft", year=1660)
    _picture(service, "wmc:11", _print(3, (600, 700)), title="View of Delft", year=1661)
    whole = _print(12, (600, 700))
    _picture(service, "met:20", whole, title="The Milkmaid")
    _picture(service, "wmc:21", whole.crop((100, 0, 400, 700)), title="Jug", artist="Unknown")
    assert service.twins.apply("wmc:21", "met:20", "a_detail_of_b")
    _picture(service, "wmc:30", _print(4, (600, 700)), title="The Lacemaker")
    _picture(service, "wikiart:31", _print(5, (600, 700)), title="The Lacemaker, a copy")
    assert service.twins.separate("wmc:30", "wikiart:31")


def test_what_is_settled_is_listed_without_pictures(service: FrameService) -> None:
    _settled(service)
    # The owner's own photograph is in none of it.
    service.library.upsert(
        Item(id="upload:1", kind=ItemKind.PHOTO, source="upload", source_id="1", title="Wakacje")
    )
    data = golden.decisions(service)
    same = {(frozenset((p["a"], p["b"])), p["by"]) for p in data["same"]}
    assert (frozenset(("wmc:1", "wikiart:2")), "pictures") in same or (
        frozenset(("wmc:1", "wikiart:2")),
        "hash",
    ) in same
    assert (frozenset(("met:10", "wmc:11")), "description") in same
    assert data["details"] == [{"a": "wmc:21", "b": "met:20"}]
    assert {"a": "wikiart:31", "b": "wmc:30", "by": "owner"} in data["apart"]
    assert "upload:1" not in data["items"]
    brief = data["items"]["met:10"]
    assert brief["title"] == "View of Delft" and brief["year"] == 1660
    assert not {"description", "colors", "keywords", "framing"} & set(brief)

    with _client(service) as client:
        assert client.get("/api/debug/decisions").json()["details"] == data["details"]


def test_a_rule_is_measured_against_what_is_settled(service: FrameService) -> None:
    _settled(service)
    data = golden.decisions(service)
    tally = golden.measure(data)
    # The descriptions hold their own pairs together, and know nothing of
    # the copy only its picture told ("Lekcja muzyki", "The music lesson").
    assert tally["same by description"] == {"together": 1}
    by_picture = next(v for k, v in tally.items() if k in ("same by pictures", "same by hash"))
    assert by_picture == {"together": 1}  # named a copy: the grouping keeps to it
    assert tally["apart by owner"] == {"apart": 1}
    assert tally["apart by detail"] == {"apart": 1}

    # A rule that joins whatever one artist made: everything kept apart goes.
    def careless(a: Item, b: Item) -> bool:
        return a.artist == b.artist or same_work(a, b)

    assert golden.measure(data, careless)["apart by owner"] == {"joined": 1}


def test_the_round_says_where_its_time_went(
    service: FrameService, caplog: pytest.LogCaptureFixture
) -> None:
    painting = _print(1, (600, 700))
    _picture(service, "wmc:1", painting, title="Lekcja muzyki", year=1662)
    _picture(service, "wikiart:2", painting.resize((420, 490)), title="The music lesson")
    with caplog.at_level(logging.INFO, logger="frame_server.library.twins"):
        service.twins.look()
    [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("twins: time:")]
    for step in ("candidates", "hashes", "keypoints", "pairs", "writes", "grouping"):
        assert f"{step} " in line
    assert "hashes" in line and "(2)" in line  # two pictures hashed


def test_the_library_counts_its_regroupings(service: FrameService) -> None:
    library = service.library
    library.upsert(Item(id="met:1", source="met", source_id="1", title="A", artist="X"))
    library.works()
    made, seconds = library.regrouped()
    library.works()  # still there: nothing made
    assert library.regrouped() == (made, seconds)
    # A copy named: the groups are made anew when next asked for.
    library.upsert(Item(id="wmc:2", source="wmc", source_id="2", title="B", artist="X"))
    library.update("wmc:2", copy_of="met:1")
    library.works()
    assert library.regrouped()[0] == made + 1


def test_the_saved_decisions_are_measured_from_a_file(
    service: FrameService, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _settled(service)
    saved = tmp_path / "decisions.json"
    saved.write_text(json.dumps(golden.decisions(service)), encoding="utf-8")
    assert golden.main([str(saved)]) == 0
    told = capsys.readouterr().out
    assert "same by description: 1 together" in told
    assert "apart by owner: 1 apart" in told
    assert golden.main([]) == 2
