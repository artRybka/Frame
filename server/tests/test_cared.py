"""The night's tidying looks first at the works the owner cares about:
Favourites, playlists and Discover (Mateusz 2026-11-11), and the night's
tasks come in packages for the app."""

from __future__ import annotations

import logging
from typing import Any

from test_ai import FakeAnthropic, fake  # noqa: F401  (fixture)
from test_gatekeeper import _work

from frame_server import logbuffer
from frame_server.cared import KEPT, REST, SHOWN
from frame_server.library import Playlist, PlaylistKind, PlaylistRules
from frame_server.night import GROUPS, NightQueue, tasks
from frame_server.service import FrameService


def _cared(service: FrameService) -> None:
    for n in range(1, 7):
        _work(service, f"europeana:{n}", title=f"Dzieło {n}", artist="Jan Kowalski", pooled=True)
    _work(service, "europeana:9", title="Pejzaż", artist="Anna Nowak", pooled=True)
    service.library.set_favorite("owner", "europeana:2", True)
    service.library.save_playlist(
        Playlist(name="Moje", kind=PlaylistKind.MANUAL, item_ids=["europeana:4"])
    )
    service.library.save_playlist(
        Playlist(name="Nowak", kind=PlaylistKind.SMART, rules=PlaylistRules(artists=["anna nowak"]))
    )
    service.cared.forget()


def test_favourites_and_playlists_are_kept_smart_playlists_shown(
    service: FrameService,
) -> None:
    _cared(service)
    assert service.cared.rank("europeana:2") == KEPT
    assert service.cared.rank("europeana:4") == KEPT
    assert service.cared.rank("europeana:9") == SHOWN
    assert service.cared.rank("europeana:5") == REST
    order = service.cared.first(["europeana:5", "europeana:9", "europeana:4"], lambda i: [i])
    assert order == ["europeana:4", "europeana:9", "europeana:5"]


def test_discovers_works_count_as_shown(service: FrameService, monkeypatch) -> None:
    from frame_server.web import discover_api

    _cared(service)
    monkeypatch.setattr(discover_api, "shown_ids", lambda svc: {"europeana:6", "europeana:2"})
    service.cared.forget()
    assert service.cared.rank("europeana:6") == SHOWN
    assert service.cared.rank("europeana:2") == KEPT  # the better rank stays


def test_the_gatekeeper_and_the_audit_ask_about_cared_works_first(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _cared(service)
    asked = [i.id for i in service.gatekeeper.candidates({})]
    assert asked[:3] == ["europeana:2", "europeana:4", "europeana:9"]
    service.audit.per_night = 3
    picked = [i.id for i in service.audit.candidates({})]
    assert set(picked) == {"europeana:2", "europeana:4", "europeana:9"}


def test_the_judge_asks_about_pairs_of_cared_works_first(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
    monkeypatch,
) -> None:
    _cared(service)
    suspects = ["europeana:1|europeana:3", "europeana:5|europeana:2", "europeana:6|europeana:9"]
    monkeypatch.setattr(service.twins, "suspects", lambda: list(suspects))
    pairs = service.twins_judge._pairs({})
    assert [key for key, *_ in pairs] == [
        "europeana:5|europeana:2",
        "europeana:6|europeana:9",
        "europeana:1|europeana:3",
    ]


def test_the_tidying_runs_before_the_rijks_index(service: FrameService) -> None:
    names = [t.name for t in tasks(service)]
    for name in ("twins", "twins judge", "gatekeeper", "audit", "kept originals"):
        assert names.index(name) < names.index("rijks")
        # ... and before the catalogue takes new works in (2026-11-11: it
        # took 1 h 43 min of the night, the copies got five minutes).
        assert names.index(name) < names.index("catalogue")
    assert names.index("twins") < names.index("twins judge")
    # What the gatekeeper sets aside the judge is not asked about.
    assert names.index("gatekeeper") < names.index("twins judge")
    assert names.index("catalogue") < names.index("grouping") < names.index("rijks")


def test_every_task_has_a_package(service: FrameService) -> None:
    queue = NightQueue(service, tasks(service))
    view: dict[str, Any] = queue.view()
    keys = [key for key, _label, _about in GROUPS]
    assert [g["key"] for g in view["groups"]] == keys
    assert all(t["group"] in keys for t in view["tasks"])
    listed = [name for g in view["groups"] for name in g["tasks"]]
    assert sorted(listed) == sorted(t["name"] for t in view["tasks"])
    duplicates = next(g for g in view["groups"] if g["key"] == "duplicates")
    assert duplicates["tasks"] == ["twins", "gatekeeper", "twins judge", "audit"]


# -- secrets in the log -------------------------------------------------------------------


def test_a_urls_secrets_never_reach_the_log() -> None:
    """2026-11-11: WikiArt's login stood in a failed request's URL with its
    accessCode and secretCode."""
    buffer = logbuffer.LogBuffer()
    log = logging.getLogger("test.secrets")
    log.addHandler(buffer)
    try:
        log.warning(
            "a museum stopped answering: Server error '500' for url "
            "'https://www.wikiart.org/en/api/2/login?accessCode=abc123&secretCode=s3cr3t'"
        )
        log.warning("GET https://data.rijksmuseum.nl/search?type=painting&pageToken=XYZ&key=k1 200")
    finally:
        log.removeHandler(buffer)
    first, second = buffer.lines(2)
    assert "abc123" not in first and "s3cr3t" not in first
    assert "accessCode=[ukryte]&secretCode=[ukryte]'" in first
    assert "pageToken=XYZ" in second and "key=[ukryte] 200" in second


def test_secrets_already_on_disk_are_left_out_when_read(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(logbuffer, "_path", tmp_path / "server.log")
    (tmp_path / "server.log").write_text(
        "2026-11-11 00:48:48,443 WARNING x: url 'https://x.org/login?accessCode=abc&secretCode=def'\n"
    )
    [line] = logbuffer.day_lines("2026-11-11", 10) or []
    assert "abc" not in line.split("?", 1)[1] and "secretCode=[ukryte]" in line


# -- what the tidying of copies changed (Mateusz 2026-11-11) ------------------------------


def _client(service: FrameService):
    from fastapi.testclient import TestClient

    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    return TestClient(app)


def test_the_pictures_changes_are_listed_and_kept_apart_for_good(service: FrameService) -> None:
    from test_sharper import _print
    from test_twins import _work as _picture

    painting = _print(1, (600, 700))
    _picture(service, "wmc:1", painting, title="Lekcja muzyki", year=1662)
    _picture(service, "wikiart:2", painting.resize((420, 490)), title="The music lesson")
    service.twins.look()
    [entry] = service.twins.log.entries()
    assert entry["relation"] == "copy" and entry["by"] in ("pictures", "hash")
    copy, whole = entry["a"], entry["b"]
    assert {copy, whole} == {"wmc:1", "wikiart:2"}
    stored = service.library.get(copy)
    assert stored is not None and stored.copy_of == whole

    assert service.twins.separate(copy, whole)
    stored = service.library.get(copy)
    assert stored is not None and not stored.copy_of
    assert service.twins.log.entries() == []
    # Never joined again, by the pictures or by the judge.
    _picture(service, "europeana:3", painting.resize((400, 467)), title="Die Musikstunde")
    service.twins.look()
    one, other = service.library.get(copy), service.library.get(whole)
    assert one is not None and other is not None
    assert (one.copy_of or one.id) != (other.copy_of or other.id)
    assert not service.twins.apply(copy, whole, "same")


def test_the_judges_changes_are_the_doubtful_ones(service: FrameService) -> None:
    from test_sharper import _print
    from test_twins import _work as _picture

    painting = _print(12, (600, 700))
    _picture(service, "met:1", painting, title="A")
    _picture(service, "wmc:3", painting.crop((100, 0, 400, 700)), title="C", artist="Unknown")
    said = {"why": "B is a crop of A", "critic": "No sign of a whole work in B"}
    assert service.twins.apply("wmc:3", "met:1", "a_detail_of_b", said)
    [entry] = service.twins.log.entries()
    assert entry == {**entry, "a": "wmc:3", "b": "met:1", "relation": "detail", "by": "judge"}
    assert entry["why"] == said["why"] and entry["critic"] == said["critic"]

    with _client(service) as client:
        listed = client.get("/api/night/changes").json()
        [doubtful] = listed["doubtful"]
        assert doubtful["a"]["id"] == "wmc:3" and doubtful["relation_name"] == "Detal dzieła"
        assert listed["sure"] == []
        after = client.post("/api/night/changes/apart", json={"a": "wmc:3", "b": "met:1"}).json()
        assert after["doubtful"] == []
    part = service.library.get("wmc:3")
    assert part is not None and not part.detail_of


def test_a_task_says_what_it_did_in_words() -> None:
    from frame_server.night import Done, _outcome, plural

    assert [plural(n, "kopia", "kopie", "kopii") for n in (1, 3, 5, 12, 22)] == [
        "1 kopia",
        "3 kopie",
        "5 kopii",
        "12 kopii",
        "22 kopie",
    ]
    assert _outcome(Done(41, "41 kopii, 14 detali")) == {
        "count": 41,
        "nothing": False,
        "summary": "41 kopii, 14 detali",
    }
    assert _outcome(3) == {"count": 3, "nothing": False}
