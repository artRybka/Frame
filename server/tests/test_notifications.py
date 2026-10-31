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
