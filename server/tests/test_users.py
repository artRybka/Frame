"""People on the server: the owner, a household member joining with an
invitation, what each may do and what each has of their own."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.library import ItemKind, Look, Playlist, PlaylistRules
from frame_server.library.repo import Library
from frame_server.library.viewer import OWNER_ID
from frame_server.web import create_app

OWNER = {"Authorization": "Bearer secret"}


def _app(tmp_path: Path, token: str | None = "secret"):
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        api_token=token,
    )
    return create_app(settings)


def _add(svc, n: int, artist: str = "Ala"):
    return svc.importer.add_upload(
        jpeg_bytes((40 * n % 255, 80, 120)), kind=ItemKind.OWN, title=f"Work {n}", artist=artist
    )


def _join(client: TestClient, name: str = "Paulina", role: str = "member") -> dict[str, str]:
    invite = client.post("/api/users/invites", json={"name": name, "role": role}, headers=OWNER)
    assert invite.status_code == 200, invite.text
    joined = client.post(
        "/api/join", json={"code": invite.json()["code"], "device": f"iPhone {name}"}
    )
    assert joined.status_code == 200, joined.text
    body = joined.json()
    assert body["me"]["name"] == name
    assert body["me"]["role"] == role
    return {"Authorization": f"Bearer {body['token']}"}


def test_a_member_joins_once_with_an_invitation(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        me = client.get("/api/me", headers=OWNER).json()
        assert me["role"] == "owner" and me["device_id"] is None and me["people"] is True

        invite = client.post("/api/users/invites", json={"name": "Paulina"}, headers=OWNER).json()
        code = invite["code"]
        joined = client.post("/api/join", json={"code": code, "device": "iPhone Pauliny"})
        assert joined.status_code == 200
        member = {"Authorization": f"Bearer {joined.json()['token']}"}
        # Once only.
        again = client.post("/api/join", json={"code": code, "device": "x"})
        assert again.status_code == 403

        me = client.get("/api/me", headers=member).json()
        assert me["name"] == "Paulina" and me["role"] == "member"
        assert me["studies_left"] == 3

        people = client.get("/api/users", headers=OWNER).json()
        paulina = next(u for u in people["users"] if u["name"] == "Paulina")
        assert [d["name"] for d in paulina["devices"]] == ["iPhone Pauliny"]
        assert people["invites"] == []
        # The server keeps only hashes: neither the code nor the token.
        stored = str(app.state.service.library.get_state("people"))
        assert code not in stored and joined.json()["token"] not in stored

        # Her own "Ulubione" is there from the start.
        names = [
            (p["name"], p["mine"]) for p in client.get("/api/playlists", headers=member).json()
        ]
        assert ("Ulubione", True) in names

        # "Odbierz dostęp": her token stops working at once.
        device_id = paulina["devices"][0]["id"]
        assert client.delete(f"/api/users/devices/{device_id}", headers=OWNER).status_code == 200
        assert client.get("/api/me", headers=member).status_code == 401


def test_wrong_codes_wait_after_a_few(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        for _ in range(5):
            assert client.post("/api/join", json={"code": "x" * 22}).status_code == 403
        code = client.post("/api/users/invites", json={"name": "P"}, headers=OWNER).json()["code"]
        tired = client.post("/api/join", json={"code": code})
        assert tired.status_code == 403 and "za dużo" in tired.json()["detail"]


def test_a_member_has_no_konfiguracja(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        member = _join(client)
        for method, path in [
            ("get", "/api/device/config"),
            ("put", "/api/device/config"),
            ("get", "/api/device/app"),
            ("get", "/api/ai"),
            ("put", "/api/ai/key"),
            ("post", "/api/ai/keywords/describe-library"),
            ("get", "/api/sources/keys"),
            ("put", "/api/sources/keys/si"),
            ("delete", "/api/sources/keys/si"),
            ("put", "/api/tailnet/key"),
            ("delete", "/api/tailnet/key"),
            ("get", "/api/library/storage"),
            ("put", "/api/library/storage"),
            ("get", "/api/calibration"),
            ("post", "/api/server/update"),
            ("post", "/api/server/update/check"),
            ("put", "/api/notifications/key"),
            ("delete", "/api/notifications/key"),
            ("get", "/api/users"),
            ("post", "/api/users/invites"),
            ("post", "/api/device/sleep"),
            ("post", "/api/device/restart"),
            ("get", "/api/ai/restorer"),
            ("post", "/api/ai/restorer/favourites"),
            ("get", "/api/debug/own-scans"),
            ("put", "/api/users/u-1/access"),
            ("get", "/api/debug/panel-requests"),
            ("get", "/api/debug/log"),
            ("get", "/api/diagnostics/sources"),
            ("post", "/api/daily/again"),
            ("post", "/api/themes/week-artist/again"),
        ]:
            answer = client.request(method, path, headers=member, json={})
            assert answer.status_code == 403, (method, path, answer.status_code)
        # What she may: the frame's own screens.
        assert client.get("/api/settings", headers=member).status_code == 200
        assert client.get("/api/status", headers=member).status_code == 200
        assert client.get("/api/notifications", headers=member).status_code == 200


def test_a_member_changes_the_schedule_not_the_sources(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        member = _join(client)
        settings = client.get("/api/settings", headers=member).json()
        settings["change_times"] = ["08:00"]
        settings["art"]["mat"] = "black"
        saved = client.put("/api/settings", json=settings, headers=member)
        assert saved.status_code == 200, saved.text
        assert saved.json()["change_times"] == ["08:00"]
        for field, value in [
            ("name", "Ramka Pauliny"),
            ("timezone", "Europe/London"),
            ("private_use", True),
        ]:
            changed = {**saved.json(), field: value}
            assert client.put("/api/settings", json=changed, headers=member).status_code == 403
        assert (
            client.put(
                "/api/settings", json={**saved.json(), "name": "Salon"}, headers=OWNER
            ).status_code
            == 200
        )


def test_hearts_are_each_ones_own(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    a, b = _add(svc, 1), _add(svc, 2)
    with TestClient(app) as client:
        member = _join(client)
        liked = client.patch(f"/api/library/items/{a.id}", json={"favorite": True}, headers=OWNER)
        assert liked.json()["favorite"] is True
        assert client.get(f"/api/library/items/{a.id}", headers=member).json()["favorite"] is False
        client.patch(f"/api/library/items/{b.id}", json={"favorite": True}, headers=member)

        def hearts(headers: dict[str, str]) -> set[str]:
            page = client.get("/api/library/items", params={"favorites": True}, headers=headers)
            return {i["id"] for i in page.json()["items"]}

        assert hearts(OWNER) == {a.id}
        assert hearts(member) == {b.id}
        listed = client.get("/api/library/items", headers=member).json()["items"]
        assert {i["id"]: i["favorite"] for i in listed} == {a.id: False, b.id: True}

        # Stored: someone likes both, so neither is trimmed.
        assert svc.library.get(a.id).favorite and svc.library.get(b.id).favorite
        client.patch(f"/api/library/items/{a.id}", json={"favorite": False}, headers=OWNER)
        assert not svc.library.get(a.id).favorite
        assert svc.library.get(b.id).favorite


def test_playlists_private_shared_and_the_owners_from_before(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    _add(svc, 1, "Ala")
    # One from before there were people: shared.
    old = svc.library.save_playlist(Playlist(name="Ala", rules=PlaylistRules(artists=["Ala"])))
    with svc.library._db() as db:
        db.execute(
            "UPDATE playlists SET data = ? WHERE id = ?",
            ('{"name": "Ala", "rules": {"artists": ["Ala"]}, "created_at": "2026-01-01"}', old.id),
        )
    with TestClient(app) as client:
        member = _join(client)
        mine = client.post(
            "/api/playlists",
            json={"name": "Moje", "kind": "manual", "item_ids": []},
            headers=member,
        ).json()["playlist"]
        assert mine["mine"] is True and mine["shared"] is False

        owner_sees = {p["name"] for p in client.get("/api/playlists", headers=OWNER).json()}
        assert "Moje" not in owner_sees and "Ala" in owner_sees
        member_sees = {p["name"]: p for p in client.get("/api/playlists", headers=member).json()}
        assert member_sees["Ala"]["mine"] is False and member_sees["Ala"]["shared"] is True
        assert member_sees["Ala"]["owner_name"] == "Właściciel"
        assert client.get(f"/api/playlists/{mine['id']}", headers=OWNER).status_code == 404

        # Someone else's shared playlist: played, not changed.
        assert client.post(f"/api/playlists/{old.id}/play", headers=member).status_code == 202
        renamed = {"name": "Nie", "rules": {"artists": ["Ala"]}}
        assert (
            client.put(f"/api/playlists/{old.id}", json=renamed, headers=member).status_code == 403
        )
        assert client.delete(f"/api/playlists/{old.id}", headers=member).status_code == 403

        # An app from before "Wspólna" sends no ``shared``: it stays shared.
        before = {"name": "Ala", "rules": {"artists": ["Ala"]}}
        assert client.put(f"/api/playlists/{old.id}", json=before, headers=OWNER).json()[
            "playlist"
        ]["shared"]

        # Shared from now on.
        shared = {"name": "Moje", "kind": "manual", "item_ids": [], "shared": True}
        assert (
            client.put(f"/api/playlists/{mine['id']}", json=shared, headers=member).status_code
            == 200
        )
        owner_sees = {p["name"] for p in client.get("/api/playlists", headers=OWNER).json()}
        assert "Moje" in owner_sees


def test_a_smart_ulubione_plays_its_makers_hearts(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    a, b = _add(svc, 1), _add(svc, 2)
    with TestClient(app) as client:
        member = _join(client)
        client.patch(f"/api/library/items/{a.id}", json={"favorite": True}, headers=OWNER)
        client.patch(f"/api/library/items/{b.id}", json={"favorite": True}, headers=member)
    hers = next(p for p in svc.library.playlists() if p.is_favorites and p.owner != OWNER_ID)
    # In the background (no one asking), as the frame plays it.
    assert [i.id for i in svc.library.playlist_items(hers)] == [b.id]
    assert [i.id for i in svc.library.query(PlaylistRules(favorites_only=True))[1]] == [a.id]


def test_a_members_studies_a_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    works = [_add(svc, n) for n in range(1, 4)]
    monkeypatch.setattr(svc.study.job, "enabled", lambda: True)
    monkeypatch.setattr(svc.study, "ask", lambda item, again=False: object())
    with TestClient(app) as client:
        member = _join(client)
        assert (
            client.put("/api/users/settings", json={"study_limit": 2}, headers=OWNER).status_code
            == 200
        )
        for work in works[:2]:
            asked = client.post(f"/api/study/{work.id}", headers=member)
            assert asked.status_code == 200, asked.text
        assert asked.json()["studies_left"] == 0
        over = client.post(f"/api/study/{works[2].id}", headers=member)
        assert over.status_code == 429
        # The owner has no limit.
        assert client.post(f"/api/study/{works[2].id}", headers=OWNER).status_code == 200


def test_sent_history_is_each_ones_own(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    photo = svc.importer.add_upload(jpeg_bytes((10, 200, 30)), kind=ItemKind.PHOTO, title="Kot")
    photo = svc.library._update(photo.id, look=Look()) or photo
    svc.player.remember_sent(photo, "u-1234")
    hers = svc.library.playlist(svc.library.get_state("sent_photos_playlist:u-1234"))
    assert hers is not None and hers.owner == "u-1234" and hers.item_ids == [photo.id]
    assert svc.library.get_state("sent_photos_playlist") is None
    assert svc.library.sent_photo_ids() == {photo.id}


def test_owner_hearts_from_before_people_move_over(tmp_path: Path) -> None:
    lib = Library(tmp_path / "library.db")
    from frame_server.library import Item

    with lib._db() as db:
        db.execute(
            "INSERT INTO items (id, data) VALUES (?, ?)",
            (
                "met:1",
                Item(
                    id="met:1", source="met", source_id="1", title="T", favorite=True
                ).model_dump_json(),
            ),
        )
    lib.delete_state("favorites_moved")
    lib._items = None
    lib._move_favorites()
    assert lib.favorites(OWNER_ID) == {"met:1"}


def test_without_a_server_token_everyone_is_the_owner(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path, token=None)) as client:
        me = client.get("/api/me").json()
        assert me["role"] == "owner" and me["people"] is False
        refused = client.post("/api/users/invites", json={"name": "P"})
        assert refused.status_code == 422


def test_each_person_arranges_their_cards(tmp_path: Path) -> None:
    """Playlisty in the order each person moved the cards; their own
    "Ulubione" first until then, new ones after the arranged ones."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        ours = {"A", "B", "C", "Ulubione"}  # besides the ones a new server starts with

        def names(headers: dict[str, str]) -> list[str]:
            listed = client.get("/api/playlists", headers=headers).json()
            return [p["name"] for p in listed if p["name"] in ours]

        def make(name: str, headers: dict[str, str]) -> int:
            body = {"name": name, "kind": "manual", "item_ids": [], "shared": True}
            made = client.post("/api/playlists", json=body, headers=headers)
            return made.json()["playlist"]["id"]

        a = make("A", OWNER)
        b = make("B", OWNER)
        listed = client.get("/api/playlists", headers=OWNER).json()
        fav = next(p["id"] for p in listed if p["name"] == "Ulubione")
        assert names(OWNER) == ["Ulubione", "A", "B"]

        moved = client.put("/api/playlists/order", json={"ids": [b, fav, a]}, headers=OWNER)
        assert moved.status_code == 200, moved.text
        assert [p["name"] for p in moved.json()][:3] == ["B", "Ulubione", "A"]
        make("C", OWNER)
        assert names(OWNER) == ["B", "Ulubione", "A", "C"]

        # The member's own order, their own Ulubione first until then; ids
        # they don't see (the owner's private Ulubione) are dropped, and the
        # owner's order stays.
        member = _join(client)
        assert names(member) == ["Ulubione", "A", "B", "C"]
        client.put("/api/playlists/order", json={"ids": [fav, b]}, headers=member)
        assert names(member) == ["B", "Ulubione", "A", "C"]
        assert names(OWNER) == ["B", "Ulubione", "A", "C"]


def _own(svc, n: int, by: str = ""):
    from frame_server.library.models import OwnWork

    item = _add(svc, n)
    return svc.library.update(item.id, own=OwnWork(by=by)) or item


def test_a_guest_never_touches_the_frame(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    work = _add(svc, 1)
    with TestClient(app) as client:
        guest = _join(client, "Ania", role="guest")
        me = client.get("/api/me", headers=guest).json()
        assert me["role"] == "guest" and me["studies_left"] == 1
        settings = client.get("/api/settings", headers=guest).json()
        for method, path, body in [
            ("post", f"/api/library/items/{work.id}/show", {}),
            ("post", f"/api/library/items/{work.id}/queue", {}),
            ("post", "/api/player/next", {}),
            ("post", "/api/player/previous", {}),
            ("post", "/api/player/hold", {}),
            ("delete", "/api/player/hold", {}),
            ("put", "/api/settings", settings),
            ("post", "/api/suggestions/play", {}),
            ("post", "/api/playlists/1/play", {}),
            ("post", "/api/device/wake", {}),
            ("post", "/api/device/push", {}),
            ("patch", f"/api/library/items/{work.id}", {"excluded": True}),
        ]:
            answer = client.request(method, path, headers=guest, json=body)
            assert answer.status_code == 403, (method, path, answer.status_code)
        # What a guest may: look, like, search.
        liked = client.patch(
            f"/api/library/items/{work.id}", json={"favorite": True}, headers=guest
        )
        assert liked.status_code == 200 and liked.json()["favorite"] is True
        assert client.get("/api/library/items", headers=guest).status_code == 200
        # A member still wakes the frame (no panel here: not refused for who asks).
        member = _join(client)
        assert client.post("/api/device/wake", headers=member).status_code != 403


def test_a_guests_hearts_are_not_the_households_taste(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    a, b = _add(svc, 1), _add(svc, 2)
    with TestClient(app) as client:
        guest = _join(client, "Ania", role="guest")
        member = _join(client)
        client.patch(f"/api/library/items/{a.id}", json={"favorite": True}, headers=guest)
        client.patch(f"/api/library/items/{b.id}", json={"favorite": True}, headers=member)
        assert svc.library.household_likes() == frozenset({b.id})
        # Both still keep their works in the library.
        assert svc.library.get(a.id).favorite and svc.library.get(b.id).favorite


def test_own_works_are_edited_by_whoever_added_them(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    with TestClient(app) as client:
        member = _join(client)
        guest = _join(client, "Ania", role="guest")
        member_id = client.get("/api/me", headers=member).json()["id"]
        hers = _own(svc, 1, by=member_id)
        owners = _own(svc, 2)
        text = {"title": "Nowy tytuł"}
        assert (
            client.put(f"/api/own/works/{owners.id}", json=text, headers=member).status_code == 403
        )
        assert client.put(f"/api/own/works/{hers.id}", json=text, headers=guest).status_code == 403
        done = client.put(f"/api/own/works/{hers.id}", json=text, headers=member)
        assert done.status_code == 200, done.text
        assert done.json()["title"] == "Nowy tytuł"
        assert svc.library.get(hers.id).own.by == member_id  # kept through "Edytuj opis"
        assert client.put(f"/api/own/works/{hers.id}", json=text, headers=OWNER).status_code == 200
        # Removed by her or the owner, never by another.
        assert client.delete(f"/api/library/items/{hers.id}", headers=guest).status_code == 403
        assert client.delete(f"/api/library/items/{owners.id}", headers=member).status_code == 403
        assert client.delete(f"/api/library/items/{hers.id}", headers=member).status_code == 200
        # Adding is everyone's: the scan's first step answers a guest too.
        assert client.post("/api/own/photos", headers=guest).status_code == 422


def test_each_person_has_studies_a_day_of_their_own(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        member = _join(client)
        guest = _join(client, "Ania", role="guest")
        people = client.get("/api/users", headers=OWNER).json()
        limits = {u["name"]: (u["role"], u["study_limit"]) for u in people["users"]}
        assert limits["Paulina"] == ("member", 3) and limits["Ania"] == ("guest", 1)
        assert limits["Właściciel"] == ("owner", None)
        ania = next(u["id"] for u in people["users"] if u["name"] == "Ania")
        changed = client.put(f"/api/users/{ania}/access", json={"study_limit": 4}, headers=OWNER)
        assert changed.status_code == 200, changed.text
        assert client.get("/api/me", headers=guest).json()["studies_left"] == 4
        assert client.get("/api/me", headers=member).json()["studies_left"] == 3
        # Made a member: the frame is hers too.
        client.put(f"/api/users/{ania}/access", json={"role": "member"}, headers=OWNER)
        assert client.get("/api/me", headers=guest).json()["role"] == "member"
        refused = client.put(f"/api/users/{ania}/access", json={"role": "owner"}, headers=OWNER)
        assert refused.status_code == 422


def test_only_the_owner_looks_for_and_picks_another_copy(tmp_path: Path) -> None:
    """Another copy changes the work's picture for the whole household: the
    owner's to look for and pick (Mateusz 2026-11-20)."""
    app = _app(tmp_path)
    svc = app.state.service
    work = _add(svc, 1)
    with TestClient(app) as client:
        for who in (_join(client), _join(client, "Ania", role="guest")):
            for method, path, body in [
                ("get", f"/api/library/items/{work.id}/copies", None),
                ("put", f"/api/library/items/{work.id}/copy", {"item_id": work.id}),
                ("delete", f"/api/library/items/{work.id}/copy", None),
            ]:
                answer = client.request(method, path, headers=who, json=body)
                assert answer.status_code == 403, (method, path, answer.status_code)
