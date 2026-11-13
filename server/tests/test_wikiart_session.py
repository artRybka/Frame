"""WikiArt's login and what a card shows when a museum does not answer
(2026-11-13: a WikiArt work's card came up empty, with "Serwer odpowiedział
502: wikiart:…: WikiArt refused a login lately; not asked for 30 min")."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from frame_server.library.hosts import OverBudget
from frame_server.library.museums import Access, LoginRefused, WikiArt, museum

EMPTY = {"data": [], "hasMore": False}


@pytest.fixture(autouse=True)
def fresh_wikiart(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("_sessions", "_refused", "_artists", "_named", "_tokens"):
        monkeypatch.setattr(WikiArt, name, {})
    monkeypatch.setattr(WikiArt, "_loaded", set())


def _access(tmp_path: Path | None = None) -> Access:
    return Access(private_use=True, wikiart_keys=("acc", "sec"), data_dir=tmp_path)


def test_a_request_our_guard_held_back_is_no_refused_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The background's share of the hour spent (or a resting host) asked
    WikiArt nothing; it stopped WikiArt for half an hour, the owner's card
    too, and the background then spent the next half hour the same way."""
    held = [True]
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        if held[0]:
            raise OverBudget("www.wikiart.org: its quota is spent", request=request)
        sent.append(request.url.path.rsplit("/", 1)[-1])
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"SessionKey": "s1"})
        return httpx.Response(200, json=EMPTY)

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        wikiart = museum("wikiart", http, _access())
        with pytest.raises(OverBudget):
            wikiart.search("Rothko")
        assert WikiArt._refused == {}
        held[0] = False
        assert wikiart.search("Rothko") == (0, [])
    assert sent == ["login", "PaintingSearch"]


def test_a_login_without_an_answer_is_no_refused_login() -> None:
    calls = [0]

    def answer(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        if calls[0] == 1:
            raise httpx.ConnectTimeout("no answer", request=request)
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"SessionKey": "s1"})
        return httpx.Response(200, json=EMPTY)

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        wikiart = museum("wikiart", http, _access())
        with pytest.raises(httpx.ConnectTimeout):
            wikiart.search("Rothko")
        assert wikiart.search("Rothko") == (0, [])


def test_a_refused_login_is_told_and_kept_across_a_restart(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    logins = [0]

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            logins[0] += 1
            return httpx.Response(500, json={"Exception": {"Message": "Too many sessions"}})
        return httpx.Response(200, json=EMPTY)

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        wikiart = museum("wikiart", http, _access(tmp_path))
        with pytest.raises(LoginRefused):
            wikiart.search("Rothko")
        assert "Too many sessions" in caplog.text
        # A restart of the server: nothing in memory.
        WikiArt._refused.clear()
        WikiArt._loaded.clear()
        with pytest.raises(LoginRefused):
            museum("wikiart", http, _access(tmp_path)).search("Klee")
    assert logins[0] == 1
    kept = (tmp_path / "hosts" / "wikiart-session.json").read_text()
    assert '"acc"' not in kept and "sec" not in kept  # the codes stay in Konfiguracja


def test_a_session_outlives_a_restart(tmp_path: Path) -> None:
    """WikiArt gives ten sessions an hour; each update of the server spent one."""
    logins = [0]

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            logins[0] += 1
            return httpx.Response(200, json={"SessionKey": f"s{logins[0]}"})
        assert request.url.params["authSessionKey"] == "s1"
        return httpx.Response(200, json=EMPTY)

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        assert museum("wikiart", http, _access(tmp_path)).search("Rothko") == (0, [])
        WikiArt._sessions.clear()
        WikiArt._loaded.clear()
        assert museum("wikiart", http, _access(tmp_path)).search("Klee") == (0, [])
    assert logins[0] == 1


def test_a_young_session_is_not_asked_anew_for_every_complaint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An answer that names the session is taken as "it ran out" only for
    a session old enough to have; a younger one is not spent, and each
    login is one of the hour's ten."""
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    logins = [0]

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            logins[0] += 1
            return httpx.Response(200, json={"SessionKey": f"s{logins[0]}"})
        if request.url.params["authSessionKey"] == "s1":
            return httpx.Response(500, json={"Exception": {"Message": "Session key expired"}})
        return httpx.Response(200, json=EMPTY)

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        wikiart = museum("wikiart", http, _access())
        for term in ("Rothko", "Klee"):
            with pytest.raises(httpx.HTTPStatusError):
                wikiart.search(term)
        assert logins[0] == 1
        clock[0] += WikiArt.RENEW_AFTER
        assert wikiart.search("Hopper") == (0, [])
    assert logins[0] == 2


def test_a_works_record_is_asked_once(tmp_path: Path) -> None:
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path.rsplit("/", 1)[-1])
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"SessionKey": "s1"})
        return httpx.Response(
            200,
            json={
                "id": "5f770eb2edc2c94890168669",
                "title": "The Swing (after Fragonard)",
                "artistName": "Yinka Shonibare",
                "artistUrl": "yinka-shonibare",
                "url": "the-swing-after-fragonard-2001",
                "image": "https://uploads.wikiart.org/swing.jpg!Large.jpg",
                "media": ["mannequin", "cotton"],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        for _ in range(2):
            item = museum("wikiart", http, _access(tmp_path)).fetch("5f770eb2edc2c94890168669")
            assert item is not None and item.medium == "mannequin, cotton"
        # Kept for good: a year on, still not asked again.
        from frame_server.library.records import records

        kept = records(tmp_path)
        found, record = kept.get("wikiart", "5f770eb2edc2c94890168669")
        assert found
        kept.put("wikiart", "5f770eb2edc2c94890168669", record, now=time.time() - 400 * 86400)
        assert museum("wikiart", http, _access(tmp_path)).fetch("5f770eb2edc2c94890168669")
    assert asked == ["login", "Painting"]


def _work() -> object:
    from frame_server.library.models import Item, ItemKind

    return Item(
        id="wikiart:5f770eb2edc2c94890168669",
        source="wikiart",
        source_id="5f770eb2edc2c94890168669",
        kind=ItemKind.ARTWORK,
        title="The Swing (after Fragonard)",
        artist="Yinka Shonibare",
        image_url="https://uploads.wikiart.org/swing.jpg",
        thumb_url="https://uploads.wikiart.org/swing.jpg!Large.jpg",
    )


def test_a_card_shows_the_work_as_a_search_saw_it_while_its_museum_does_not_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import frame_server.library.importer as importer_module
    from frame_server.library import Library
    from frame_server.library.importer import Importer

    work = _work()

    class Refusing:
        def fetch(self, source_id: str) -> None:
            raise LoginRefused("WikiArt refused a login lately; not asked for 30 min")

    monkeypatch.setattr(importer_module, "museum", lambda key, http, access: Refusing())

    def importer() -> Importer:
        return Importer(
            Library(tmp_path / "lib.db"),
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            access=lambda: _access(tmp_path),
        )

    importer().remember([work])  # type: ignore[list-item]
    later = importer()  # after a restart: nothing in memory
    assert later.resolve(work.id) == work  # type: ignore[attr-defined]
    with pytest.raises(LoginRefused):  # one no search showed
        later.resolve("wikiart:unseen")


def test_a_museum_that_does_not_answer_is_told_in_polish() -> None:
    from frame_server.web.library_api import museum_trouble

    refused = museum_trouble("wikiart", LoginRefused("WikiArt refused a login lately"))
    assert refused.startswith("WikiArt odrzucił")
    assert museum_trouble("wikiart", httpx.ConnectTimeout("x")).startswith(
        "WikiArt teraz nie odpowiada"
    )


def test_a_works_own_record_is_asked_of_its_museum_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mateusz 2026-11-13: "gdy mamy na dysku, to po co ich pytamy?"."""
    import frame_server.library.importer as importer_module
    from frame_server.library import Library
    from frame_server.library.importer import Importer

    work = _work()
    asked: list[str] = []

    class Museum:
        def fetch(self, source_id: str) -> object:
            asked.append(source_id)
            return work

    monkeypatch.setattr(importer_module, "museum", lambda key, http, access: Museum())

    def importer() -> Importer:
        return Importer(
            Library(tmp_path / "lib.db"),
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            access=lambda: _access(tmp_path),
        )

    for _ in range(2):  # the second after a restart: nothing in memory
        assert importer().resolve(work.id) == work  # type: ignore[attr-defined]
    assert asked == ["5f770eb2edc2c94890168669"]
