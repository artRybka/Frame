"""Notifications on the phone over APNs (notifications.py, web/notify_api.py)."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi.testclient import TestClient

from frame_server import notifications
from frame_server.config import Settings
from frame_server.notifications import Apns, Notifier, PushError
from frame_server.progress import Stage
from frame_server.updates import ImageInfo, UpdateFolder, UpdaterStatus
from frame_server.web import create_app

PHONE = "ab" * 32
OTHER = "cd" * 32


def _pem() -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class FakeApple:
    """APNs: answers per token (default 200), records what it got."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, str], dict[str, object]]] = []
        self.answers: dict[tuple[str, str], tuple[int, str]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        token = request.url.path.rsplit("/", 1)[-1]
        host = request.url.host
        self.sent.append((host, token, dict(request.headers), json.loads(request.content)))
        status, reason = self.answers.get((host, token), (200, ""))
        if status == 200:
            return httpx.Response(200)
        return httpx.Response(status, json={"reason": reason})


@pytest.fixture
def apple() -> FakeApple:
    return FakeApple()


@pytest.fixture
def notifier(service, apple: FakeApple) -> Notifier:
    service.notifier.transport = httpx.MockTransport(apple)
    service.notifier.save_key(_pem(), "ABCDE12345")
    return service.notifier


def test_the_provider_token_is_signed_with_the_key() -> None:
    pem = _pem()
    apns = Apns(pem, "ABCDE12345", "3MQRJF4A9D")
    jwt = apns.token(datetime(2026, 10, 31, 12, tzinfo=UTC))
    header, claims, signature = jwt.split(".")
    assert json.loads(_unb64(header)) == {"alg": "ES256", "kid": "ABCDE12345"}
    assert json.loads(_unb64(claims))["iss"] == "3MQRJF4A9D"
    raw = _unb64(signature)
    key = serialization.load_pem_private_key(pem, password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    key.public_key().verify(der, f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    # Reused for a while, as Apple asks.
    assert apns.token(datetime(2026, 10, 31, 12, 30, tzinfo=UTC)) == jwt
    assert apns.token(datetime(2026, 10, 31, 13, 0, tzinfo=UTC)) != jwt


def test_only_a_real_apns_key_is_taken(service) -> None:
    with pytest.raises(PushError):
        service.notifier.save_key(b"not a key", "ABCDE12345")
    with pytest.raises(PushError):
        service.notifier.save_key(_pem(), "short")
    info = service.notifier.save_key(_pem(), "abcde12345")
    assert info.key_id == "ABCDE12345" and info.team_id == "3MQRJF4A9D"
    assert (service.settings.data_dir / "push" / "AuthKey_ABCDE12345.p8").is_file()
    assert notifications.key_id_from("AuthKey_ZX9Y8W7V6U.p8") == "ZX9Y8W7V6U"


def test_a_phone_gets_only_what_it_wants(notifier: Notifier, apple: FakeApple) -> None:
    notifier.register(PHONE, sandbox=False)
    notifier.register(OTHER, sandbox=False, kinds=["daily"])
    results = asyncio.run(notifier.send("changed", "Na ramce: Ul", "Monet", route="now"))
    assert list(results) == [PHONE]
    host, token, headers, payload = apple.sent[0]
    assert host == "api.push.apple.com" and token == PHONE
    assert headers["apns-topic"] == "com.artrybka.frame"
    assert headers["authorization"].startswith("bearer ")
    assert payload["aps"]["alert"] == {"title": "Na ramce: Ul", "body": "Monet"}  # type: ignore[index]
    assert payload["kind"] == "changed" and payload["route"] == "now"
    assert notifier.device(PHONE).last_sent_at is not None  # type: ignore[union-attr]


def test_a_token_apple_forgot_is_dropped(notifier: Notifier, apple: FakeApple) -> None:
    notifier.register(PHONE, sandbox=False)
    apple.answers[("api.push.apple.com", PHONE)] = (410, "Unregistered")
    asyncio.run(notifier.send("daily", "Dzieło dnia", "…"))
    assert notifier.devices() == []


def test_a_build_from_xcode_is_found_in_the_sandbox(notifier: Notifier, apple: FakeApple) -> None:
    notifier.register(PHONE, sandbox=False)
    apple.answers[("api.push.apple.com", PHONE)] = (400, "BadDeviceToken")
    results = asyncio.run(notifier.send("daily", "Dzieło dnia", "…"))
    assert results[PHONE].ok
    assert notifier.device(PHONE).sandbox is True  # type: ignore[union-attr]


def test_nothing_is_sent_without_a_key(service, apple: FakeApple) -> None:
    service.notifier.transport = httpx.MockTransport(apple)
    service.notifier.register(PHONE, sandbox=False)
    assert asyncio.run(service.notifier.send("daily", "x", "y")) == {}
    assert apple.sent == []


def _drain(notifier: Notifier) -> None:
    async def wait() -> None:
        await asyncio.sleep(0)
        if notifier._tasks:
            await asyncio.gather(*notifier._tasks)

    asyncio.run(wait())


def test_the_battery_is_told_once_per_discharge(notifier: Notifier, apple: FakeApple) -> None:
    notifier.register(PHONE, sandbox=False)
    told: list[str] = []
    notifier.notify = lambda kind, title, body, **kw: told.append(title)  # type: ignore[method-assign]
    notifier.battery(30, on_battery=True)
    notifier.battery(19, on_battery=True)
    notifier.battery(15, on_battery=True)
    assert told == ["Bateria ramki: 19%"]
    notifier.battery(15, on_battery=False)  # on the charger
    notifier.battery(18, on_battery=True)
    assert told == ["Bateria ramki: 19%", "Bateria ramki: 18%"]


def test_a_reading_from_the_panel_reaches_the_notifier(service) -> None:
    seen: list[tuple[int, bool]] = []
    service.status.on_battery_level = lambda level, on: seen.append((level, on))
    service.status.note_app(datetime.now(UTC), 12, False)
    assert seen == [(12, True)]


def test_a_failed_send_is_told(service) -> None:
    told: list[tuple[str, str]] = []
    service.notifier.notify = lambda kind, title, body, **kw: told.append((kind, body))
    service.progress.begin("Słoneczniki", render=False)
    service.progress.finish(Stage.FAILED, "panel unreachable")
    service.progress.begin("Ul", render=False)
    service.progress.finish(Stage.WAITING, "the frame asks for it at 9:00")
    assert told == [("send_failed", "„Słoneczniki” nie dotarł na ramkę. panel unreachable")]


def test_a_new_picture_on_the_frame_is_told_once(service) -> None:
    told: list[str] = []
    service.notifier.notify = lambda kind, title, body, **kw: told.append(f"{title} | {body}")
    file_id = service.store.current().file_id
    state = service.player.state
    state.last_change_origin = "schedule"
    service.player._save_state(state)
    service.app.report("shown", {"file_id": file_id})
    service.app.report("shown", {"file_id": file_id})  # the same, drawn again
    assert told == ["Na ramce: Frame | zmiana z harmonogramu"]


def test_the_work_of_the_day_goes_out_at_half_past_eight(
    notifier: Notifier, apple: FakeApple, service, monkeypatch
) -> None:
    notifier.register(PHONE, sandbox=False)
    item = type("I", (), {"title": "Ul", "artist": "Claude Monet", "id": "x"})()
    monkeypatch.setattr(service.daily, "pick", lambda day: item)
    monkeypatch.setattr(service.daily.job, "essay", lambda i: None)
    monkeypatch.setattr(service.pl_text, "text", lambda i: None)
    # 8:10 in Warsaw (UTC+1 on 31 October): too early.
    assert not asyncio.run(
        notifications.daily_tick(service, datetime(2026, 10, 31, 7, 10, tzinfo=UTC))
    )
    assert asyncio.run(notifications.daily_tick(service, datetime(2026, 10, 31, 7, 31, tzinfo=UTC)))
    assert not asyncio.run(
        notifications.daily_tick(service, datetime(2026, 10, 31, 8, 0, tzinfo=UTC))
    )
    assert len(apple.sent) == 1
    payload = apple.sent[0][3]
    assert payload["aps"]["alert"]["title"] == "Dzieło dnia: Ul"  # type: ignore[index]
    assert payload["route"] == "daily"
    assert "apns-expiration" in apple.sent[0][2]


def test_a_new_server_version_is_told_once(
    notifier: Notifier, apple: FakeApple, service, monkeypatch
) -> None:
    monkeypatch.setenv("FRAME_RELEASE", "1.47.0")
    notifier.register(PHONE, sandbox=False)
    folder = UpdateFolder(service.settings.data_dir / "update")
    folder.save_status(
        UpdaterStatus(
            alive_at=datetime.now(UTC).isoformat(),
            running=ImageInfo(id="old", version="1.47.0"),
            latest=ImageInfo(id="new", version="1.48.0"),
        )
    )
    assert asyncio.run(notifications.update_tick(service))
    assert not asyncio.run(notifications.update_tick(service))
    assert apple.sent[0][3]["aps"]["alert"]["title"] == "Nowa wersja serwera: 1.48.0"  # type: ignore[index]


# -- the API -------------------------------------------------------------------


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        api_token="secret",
    )
    client = TestClient(create_app(settings))
    client.headers["Authorization"] = "Bearer secret"
    return client


def test_the_app_registers_uploads_the_key_and_tests(tmp_path: Path) -> None:
    apple = FakeApple()
    with _client(tmp_path) as client:
        client.app.state.service.notifier.transport = httpx.MockTransport(apple)  # type: ignore[attr-defined]
        view = client.get("/api/notifications", params={"device": PHONE}).json()
        assert view["key"] is None and view["device"] is None
        assert [k["key"] for k in view["kinds"]] == list(notifications.KINDS)

        view = client.put(f"/api/notifications/devices/{PHONE}", json={"sandbox": False}).json()
        assert view["device"]["kinds"] == list(notifications.KINDS)
        assert client.post("/api/notifications/test", json={"device": PHONE}).status_code == 409

        bad = client.put(
            "/api/notifications/key", files={"file": ("AuthKey_ABCDE12345.p8", b"nope")}
        )
        assert bad.status_code == 400
        view = client.put(
            "/api/notifications/key",
            files={"file": ("AuthKey_ABCDE12345.p8", _pem())},
            data={"device": PHONE},
        ).json()
        assert view["key"]["key_id"] == "ABCDE12345"

        view = client.put(
            f"/api/notifications/devices/{PHONE}", json={"sandbox": False, "kinds": ["daily"]}
        ).json()
        assert view["device"]["kinds"] == ["daily"]

        assert client.post("/api/notifications/test", json={"device": PHONE}).json() == {
            "ok": True,
            "error": None,
        }
        apple.answers[("api.push.apple.com", PHONE)] = (403, "InvalidProviderToken")
        result = client.post("/api/notifications/test", json={"device": PHONE}).json()
        assert result["ok"] is False and "InvalidProviderToken" in result["error"]

        client.delete(f"/api/notifications/devices/{PHONE}")
        assert client.get("/api/notifications").json()["devices"] == 0


# -- studies, the artist of the week, birthdays ---------------------------------


def _work(service, item_id: str, **kw):
    from frame_server.library.models import Item, ItemKind

    kw.setdefault("kind", ItemKind.ARTWORK)
    return service.library.upsert(
        Item(id=item_id, source=item_id.split(":")[0], source_id=item_id, **kw)
    )


def test_a_phone_of_the_first_release_gets_the_new_kinds(notifier: Notifier) -> None:
    from frame_server.notifications import DEVICES_KEY, FIRST_KINDS

    old = {"token": PHONE, "sandbox": False, "kinds": ["battery", "daily"]}
    notifier.library.set_state(DEVICES_KEY, [old])
    device = notifier.device(PHONE)
    assert device is not None
    assert device.kinds == ["battery", "daily", "study", "week_artist", "birthday"]
    assert set(FIRST_KINDS) < set(device.seen or [])
    # Switched off once, it stays off.
    notifier.register(PHONE, sandbox=False, kinds=["daily"])
    assert notifier.device(PHONE).kinds == ["daily"]  # type: ignore[union-attr]


def test_a_written_study_is_told(service) -> None:
    told: list[tuple[str, str, str | None]] = []
    service.notifier.notify = lambda kind, title, body, **kw: told.append(
        (kind, body, kw.get("route"))
    )
    item = _work(service, "met:7", title="Ul", artist="Claude Monet")
    assert service.study.on_step is not None
    service.study.on_step(item, "writing", "")  # nothing follows it on the Lock Screen
    service.study.on_step(item, "ready", "")
    assert told == [("study", "„Ul”: można czytać.", "study/met:7")]


LIVE = "ef" * 40


def _step(notifier: Notifier, *args: str) -> None:
    async def run() -> None:
        notifier.study_step(*args)
        await asyncio.sleep(0)
        if notifier._tasks:
            await asyncio.gather(*notifier._tasks)

    asyncio.run(run())


def test_a_study_moves_on_on_the_lock_screen(notifier: Notifier, apple: FakeApple) -> None:
    notifier.register(PHONE, sandbox=False)
    notifier.follow_study("met:7", LIVE.upper(), sandbox=False)
    _step(notifier, "met:7", "writing")
    _, token, headers, payload = apple.sent[-1]
    assert token == LIVE
    assert headers["apns-topic"] == "com.artrybka.frame.push-type.liveactivity"
    assert headers["apns-push-type"] == "liveactivity"
    aps = payload["aps"]
    assert aps["event"] == "update"  # type: ignore[index]
    assert aps["content-state"] == {"status": "writing", "error": ""}  # type: ignore[index]
    assert aps["stale-date"] > aps["timestamp"]  # type: ignore[index, operator]
    assert "alert" not in aps  # type: ignore[operator]

    # Ready: the Lock Screen card says so and lights up, no second notification.
    _step(notifier, "met:7", "ready", "", "Ul")
    assert len(apple.sent) == 2
    _, token, _, payload = apple.sent[-1]
    aps = payload["aps"]
    assert token == LIVE and aps["event"] == "end"  # type: ignore[index]
    assert aps["content-state"]["status"] == "ready"  # type: ignore[index]
    assert aps["dismissal-date"] - aps["timestamp"] == 3600  # type: ignore[index, operator]
    assert aps["alert"]["body"] == "„Ul”: można czytać."  # type: ignore[index]
    assert notifier.study_activities() == []


def test_a_lost_lock_screen_card_falls_back_to_the_notification(
    notifier: Notifier, apple: FakeApple
) -> None:
    notifier.register(PHONE, sandbox=False)
    notifier.follow_study("met:7", LIVE, sandbox=False)
    apple.answers[("api.push.apple.com", LIVE)] = (410, "Unregistered")
    _step(notifier, "met:7", "ready", "", "Ul")
    assert [(t, h["apns-push-type"]) for _, t, h, _ in apple.sent] == [
        (LIVE, "liveactivity"),
        (PHONE, "alert"),
    ]
    assert apple.sent[-1][3]["route"] == "study/met:7"
    assert notifier.study_activities() == []


def test_a_failed_study_ends_the_card_quietly(notifier: Notifier, apple: FakeApple) -> None:
    notifier.register(PHONE, sandbox=False)
    notifier.follow_study("met:7", LIVE, sandbox=True)
    _step(notifier, "met:7", "failed", "Claude nie napisał studium tego dzieła.")
    ((host, _, _, payload),) = apple.sent
    assert host == "api.sandbox.push.apple.com"
    aps = payload["aps"]
    assert aps["event"] == "end" and "alert" not in aps  # type: ignore[index, operator]
    assert aps["content-state"]["error"] == "Claude nie napisał studium tego dzieła."  # type: ignore[index]


def test_the_app_leaves_the_card_s_token(tmp_path: Path) -> None:
    apple = FakeApple()
    with _client(tmp_path) as client:
        notifier: Notifier = client.app.state.service.notifier  # type: ignore[attr-defined]
        notifier.transport = httpx.MockTransport(apple)
        notifier.save_key(_pem(), "ABCDE12345")
        bad = client.put("/api/study/met:7/activity", json={"token": "nope"})
        assert bad.status_code == 400
        put = client.put("/api/study/met:7/activity", json={"token": LIVE, "sandbox": False})
        assert put.status_code == 204
        # Not on its way (no Claude key here): the card hears why, at once, and ends.
        ((_, token, _, payload),) = apple.sent
        assert token == LIVE
        assert payload["aps"]["event"] == "end"  # type: ignore[index]
        assert payload["aps"]["content-state"]["status"] == "off"  # type: ignore[index]
        assert notifier.study_activities() == []


def test_cards_of_studies_lost_in_a_restart_end(
    notifier: Notifier, apple: FakeApple, service
) -> None:
    notifier.follow_study("met:7", LIVE, sandbox=False)
    assert asyncio.run(notifications.settle_studies(service)) == 1
    assert apple.sent[0][3]["aps"]["content-state"]["status"] == "stopped"  # type: ignore[index]
    assert notifier.study_activities() == []


def test_the_artist_of_the_week_goes_out_on_monday_at_nine(
    notifier: Notifier, apple: FakeApple, service, monkeypatch
) -> None:
    from frame_server.library import themes

    notifier.register(PHONE, sandbox=False)
    week = themes.Theme(
        "week-artist-monet",
        "Claude Monet",
        "Artysta tygodnia. Impresjonista. 12 dzieł na ten tydzień.",
        themes.WEEKLY,
        artists=("Claude Monet",),
    )
    monkeypatch.setattr(themes, "weekly_themes", lambda library, day: [week])
    sunday = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)
    monday_early = datetime(2026, 11, 2, 7, 30, tzinfo=UTC)  # 8:30 in Warsaw
    monday = datetime(2026, 11, 2, 8, 5, tzinfo=UTC)
    assert not asyncio.run(notifications.week_tick(service, sunday))
    assert not asyncio.run(notifications.week_tick(service, monday_early))
    assert asyncio.run(notifications.week_tick(service, monday))
    assert not asyncio.run(notifications.week_tick(service, monday))
    payload = apple.sent[0][3]
    assert payload["aps"]["alert"] == {  # type: ignore[index]
        "title": "Artysta tygodnia: Claude Monet",
        "body": "Impresjonista. 12 dzieł na ten tydzień.",
    }
    assert payload["route"] == "theme/week-artist-monet"


def test_birthdays_of_favourite_artists_go_out_at_ten(
    notifier: Notifier, apple: FakeApple, service
) -> None:
    from frame_server.births import STATE_KEY

    notifier.register(PHONE, sandbox=False)
    _work(service, "met:1", title="Ul", artist="Monet, Claude", favorite=True, year=1891)
    _work(service, "met:2", title="Most", artist="Monet, Claude", favorite=True, year=1899)
    _work(service, "met:3", title="Taniec", artist="Henri Matisse", favorite=True)
    _work(service, "met:4", title="Fale", artist="Hokusai", favorite=False)
    service.library.set_state(
        STATE_KEY,
        {
            "Monet, Claude": {"born": "1840-11-14", "at": "2026-11-01T00:00:00+00:00"},
            "Henri Matisse": {"born": "1869-12-31", "at": "2026-11-01T00:00:00+00:00"},
        },
    )
    morning = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)  # 9:00 in Warsaw
    ten = datetime(2026, 11, 14, 9, 5, tzinfo=UTC)
    assert asyncio.run(notifications.birthday_tick(service, morning)) == 0
    assert asyncio.run(notifications.birthday_tick(service, ten)) == 1
    assert asyncio.run(notifications.birthday_tick(service, ten)) == 0
    payload = apple.sent[0][3]
    assert payload["aps"]["alert"] == {  # type: ignore[index]
        "title": "Urodziny: Claude Monet",
        "body": "186. rocznica urodzin (ur. 14.11.1840). W Twoich ulubionych: 2 dzieła.",
    }
    assert payload["route"] == "artist/Monet, Claude"


def test_a_birthday_is_found_on_wikidata_only_for_the_right_person(service) -> None:
    from frame_server.births import Births, search_name

    assert search_name("Monet, Claude (1840-1926)") == "Claude Monet"
    _work(service, "met:1", title="Ul", artist="Monet, Claude", favorite=True, year=1891)

    def wikidata(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params["action"] == "wbsearchentities":
            assert params["search"] == "Claude Monet"
            return httpx.Response(200, json={"search": [{"id": "Q1"}, {"id": "Q2"}, {"id": "Q3"}]})

        def born(time: str, precision: int = 11) -> list[dict[str, object]]:
            value = {"time": time, "precision": precision}
            return [{"mainsnak": {"datavalue": {"value": value}}}]

        human = [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]
        return httpx.Response(
            200,
            json={
                "entities": {
                    "Q1": {"claims": {"P31": [], "P569": born("+1840-11-14T00:00:00Z")}},
                    "Q2": {"claims": {"P31": human, "P569": born("+1990-03-01T00:00:00Z")}},
                    "Q3": {"claims": {"P31": human, "P569": born("+1840-11-14T00:00:00Z")}},
                }
            },
        )

    births = Births(service.library)
    assert births.missing(["Monet, Claude"]) == ["Monet, Claude"]
    with httpx.Client(transport=httpx.MockTransport(wikidata)) as client:
        assert births.look_up(["Monet, Claude"], client) == 1
    assert str(births.born("Monet, Claude")) == "1840-11-14"
    assert births.missing(["Monet, Claude"]) == []
    from datetime import date

    assert births.today(date(2026, 11, 14), ["Monet, Claude"])
    assert not births.today(date(2026, 11, 15), ["Monet, Claude"])
