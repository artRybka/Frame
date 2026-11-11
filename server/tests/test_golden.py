"""The decisions made so far as test data, and the measurements of the
slow steps (docs/PLAN.md 3.3zzz155)."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_sharper import _print
from test_twins import _work as _picture

from frame_server import golden
from frame_server.library.artists import IDS_STATE, PEOPLE_STATE
from frame_server.library.duplicates import same_work
from frame_server.library.models import Item, ItemKind, PlaylistRules
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
    # A copy named: the two works alone are grouped anew, at once.
    library.upsert(Item(id="wmc:2", source="wmc", source_id="2", title="B", artist="X"))
    library.update("wmc:2", copy_of="met:1")
    assert [i.id for i in library.works().groups[-1]] == ["met:1", "wmc:2"]
    assert library.regrouped() == (made, seconds)
    assert library.regrouped_in_part()[0] == 1


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


def test_the_works_kept_with_a_reason_against_are_listed(
    service: FrameService, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """What the owner kept that the rules call a copy or "Sztuki inne": the
    list he decides the one verdict by (docs/RULES.md, stage 4)."""

    def add(item_id: str, **kw: object) -> None:
        source, _, source_id = item_id.partition(":")
        kw.setdefault("artist", "Claude Monet")
        kw.setdefault("classification", "Painting")
        service.library.upsert(Item(id=item_id, source=source, source_id=source_id, **kw))

    add("met:1", title="Poplars")  # a painting: no reason
    add("wikiart:2", title="Haystacks, detail", favorite=True)
    add("europeana:3", title="Cathedral", classification="Postage stamp")
    add("met:4", title="Bust", classification="Sculpture")
    add("wikiart:5", title="Bridge, detail", pooled=True)  # the server's: not his
    add("wmc:6", title="Regatta (page 41 crop)", seen_as="not_art")  # two reasons
    data = golden.decisions(service)
    kept = {entry["id"]: entry for entry in data["kept"]}
    assert set(kept) == {"wikiart:2", "europeana:3", "met:4", "wmc:6"}
    assert kept["wikiart:2"] == {
        "id": "wikiart:2",
        "why": ["detail"],
        "liked": True,
        "studied": kept["wikiart:2"]["studied"],
    }
    assert kept["wmc:6"]["why"] == ["seen", "reproduction"]
    assert kept["met:4"]["why"] == ["sculpture"] and not kept["met:4"]["studied"]
    assert all(entry["id"] in data["items"] for entry in data["kept"])

    by_reason = golden.kept_against(data)
    assert {name: [w["id"] for w in works] for name, works in by_reason.items()} == {
        "detal dzieła": ["wikiart:2"],
        "znaczek albo banknot": ["europeana:3"],
        "rzeźba": ["met:4"],
        "odłożone przez Strażnika": ["wmc:6"],
    }
    assert by_reason["detal dzieła"][0]["title"] == "Haystacks, detail"
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert golden.main([str(path)]) == 0
    assert "kept, rzeźba: 1 (0 may be the work of the day)" in capsys.readouterr().out


def test_the_whole_catalogue_is_saved_and_asked_away_from_the_server(
    service: FrameService, tmp_path: Path
) -> None:
    """Every work of art as the library has it, a hidden one too, none of
    the owner's photographs; read back, it is a library that answers as the
    server's does."""
    _settled(service)
    service.library.upsert(
        Item(id="upload:1", kind=ItemKind.PHOTO, source="upload", source_id="1", title="Wakacje")
    )
    service.library.update("met:10", excluded=True, keywords=["harbour"])
    with _client(service) as client:
        answer = client.get("/api/debug/catalogue")
    assert answer.status_code == 200
    saved = tmp_path / "catalogue.jsonl.gz"
    saved.write_bytes(answer.content)
    works = {item.id: item for item in golden.works(saved)}
    art = [i for i in service.library.query(include_excluded=True)[1] if i.source != "upload"]
    assert set(works) == {i.id for i in art} and "upload:1" not in works
    for item in art:  # as the library has them: no field lost on the way
        assert works[item.id] == item
    assert works["met:10"].excluded and works["met:10"].keywords == ["harbour"]

    library = golden.library_of(saved, tmp_path / "away.db")
    try:
        ours = service.library.query(PlaylistRules(query="Lacemaker"))[1]
        theirs = library.query(PlaylistRules(query="Lacemaker"))[1]
        assert ours and [i.id for i in theirs] == [i.id for i in ours]
    finally:
        library.close()


def test_who_the_artists_are_goes_with_the_catalogue(service: FrameService, tmp_path: Path) -> None:
    """What Wikidata told of the artists is saved too, and a library made
    of the catalogue away from the server keeps it."""
    _settled(service)
    ids = {"Jan Vermeer": ["Q41264", "2026-11-01"], "Nobody Known": ["", "2026-11-01"]}
    people = {"Q41264": {"en": "Johannes Vermeer", "born": 1632, "died": 1675}}
    service.library.set_state(IDS_STATE, ids)
    service.library.set_state(PEOPLE_STATE, people)
    with _client(service) as client:
        catalogue = client.get("/api/debug/catalogue")
        answer = client.get("/api/debug/artists")
    assert answer.status_code == 200
    assert answer.json() == {"ids": ids, "people": people}
    saved, told = tmp_path / "catalogue.jsonl.gz", tmp_path / "artists.json"
    saved.write_bytes(catalogue.content)
    told.write_bytes(answer.content)
    library = golden.library_of(saved, tmp_path / "away.db", told)
    try:
        assert golden.artists(library) == {"ids": ids, "people": people}
    finally:
        library.close()


def test_a_large_catalogue_is_written_in_pieces(
    service: FrameService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for n in range(400):
        title = " ".join(uuid.uuid4().hex for _ in range(8))  # nothing to pack
        service.library.upsert(Item(id=f"met:{n}", source="met", source_id=str(n), title=title))
    monkeypatch.setattr(golden, "PIECE", 4096)
    pieces = list(golden.catalogue(service.library))
    assert len(pieces) > 2 and all(pieces)
    saved = tmp_path / "catalogue.jsonl.gz"
    saved.write_bytes(b"".join(pieces))
    assert len(golden.works(saved)) == 400
