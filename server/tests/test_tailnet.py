"""Tailscale built into the app: the owner keeps the key on the server,
every phone of the household reads it to join the tailnet."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.tailnet import AddressInvalid, KeyInvalid, clean, clean_address
from frame_server.web import create_app

OWNER = {"Authorization": "Bearer secret"}
KEY = "tskey-auth-kAbCdEf1CNTRL-0123456789abcdefABCDEF"


def _app(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        api_token="secret",
    )
    return create_app(settings)


def _member(client: TestClient) -> dict[str, str]:
    code = client.post("/api/users/invites", json={"name": "Paulina"}, headers=OWNER).json()["code"]
    token = client.post("/api/join", json={"code": code, "device": "iPhone"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_the_owner_saves_the_key_and_every_phone_reads_it(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        empty = client.get("/api/tailnet", headers=OWNER).json()
        assert empty == {
            "key_set": False,
            "key_tail": None,
            "key": None,
            "saved_at": None,
            "address": None,
        }

        saved = client.put("/api/tailnet/key", json={"key": f"  {KEY}\n"}, headers=OWNER)
        assert saved.status_code == 200, saved.text
        assert saved.json()["key"] == KEY
        assert saved.json()["key_tail"] == KEY[-4:]
        assert saved.json()["saved_at"]

        member = _member(client)
        read = client.get("/api/tailnet", headers=member).json()
        assert read["key"] == KEY
        assert client.put("/api/tailnet/key", json={"key": KEY}, headers=member).status_code == 403
        assert client.delete("/api/tailnet/key", headers=member).status_code == 403

        gone = client.delete("/api/tailnet/key", headers=OWNER).json()
        assert gone["key_set"] is False and gone["key"] is None
        assert client.get("/api/tailnet", headers=member).json()["key"] is None


def test_without_a_token_nobody_reads_the_key(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        client.put("/api/tailnet/key", json={"key": KEY}, headers=OWNER)
        assert client.get("/api/tailnet").status_code == 401
        wrong = {"Authorization": "Bearer wrong"}
        assert client.get("/api/tailnet", headers=wrong).status_code == 401


def test_only_a_tailscale_key_is_kept(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        for wrong in ["", "   ", "sk-ant-123456789", "tskey-auth-abc", f"{KEY} more"]:
            answer = client.put("/api/tailnet/key", json={"key": wrong}, headers=OWNER)
            assert answer.status_code == 400, wrong
        assert client.get("/api/tailnet", headers=OWNER).json()["key_set"] is False


@pytest.mark.parametrize(
    ("given", "kept"),
    [(KEY, KEY), (f"\t{KEY} ", KEY), ("tskey-client-abcdefgh12345", "tskey-client-abcdefgh12345")],
)
def test_clean_keeps_the_key_as_pasted(given: str, kept: str) -> None:
    assert clean(given) == kept


def test_clean_refuses_what_is_not_a_key() -> None:
    with pytest.raises(KeyInvalid):
        clean("tskey-")


def test_the_owners_phone_hands_over_the_servers_address(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        address = "http://synology.tail8a7550.ts.net:8099"
        saved = client.put("/api/tailnet/address", json={"address": f" {address}/ "}, headers=OWNER)
        assert saved.status_code == 200, saved.text
        assert saved.json()["address"] == address

        member = _member(client)
        assert client.get("/api/tailnet", headers=member).json()["address"] == address
        answer = client.put("/api/tailnet/address", json={"address": address}, headers=member)
        assert answer.status_code == 403
        assert client.delete("/api/tailnet/address", headers=member).status_code == 403

        # The key and the address are kept apart.
        client.put("/api/tailnet/key", json={"key": KEY}, headers=OWNER)
        client.delete("/api/tailnet/key", headers=OWNER)
        assert client.get("/api/tailnet", headers=OWNER).json()["address"] == address

        wrong = client.put(
            "/api/tailnet/address", json={"address": "http://192.168.1.5:8099"}, headers=OWNER
        )
        assert wrong.status_code == 400
        assert client.delete("/api/tailnet/address", headers=OWNER).json()["address"] is None


@pytest.mark.parametrize(
    "address",
    [
        "http://100.95.9.80:8099",
        "https://nas.tail1234.ts.net",
        "http://synology:8099",
        "http://[fd7a:115c:a1e0::1]:8099",
    ],
)
def test_clean_address_takes_tailscale_addresses(address: str) -> None:
    assert clean_address(address) == address


@pytest.mark.parametrize(
    "address",
    [
        "",
        "synology.tail1234.ts.net:8099",
        "ftp://100.95.9.80",
        "http://192.100.3.185:8099",
        "http://100.95.9.80:8099/api",
        "http://example.com",
        "http://localhost:8099",
        "http://100.95.9.80:99999",
    ],
)
def test_clean_address_refuses_the_rest(address: str) -> None:
    with pytest.raises(AddressInvalid):
        clean_address(address)
