"""Works of the owner's own ("Dodaj własne dzieło", Mateusz 2026-11-15):
the photograph sent, the work found in it by Opus and cut out of its frame,
hints read off it, the work added with what he wrote, described again,
photographed again, corrected and deleted."""

from __future__ import annotations

import io
import os
import time

from fastapi.testclient import TestClient
from PIL import Image
from test_ai import FakeAnthropic, _message, fake  # noqa: F401  (fixture)
from test_crops import CORNERS, H, W, photo

from frame_server.ai.client import OPUS, SONNET
from frame_server.library.models import ItemKind, ItemSummary
from frame_server.service import FrameService


def _jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=95)
    return out.getvalue()


def _client(service: FrameService) -> TestClient:
    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    return TestClient(app)


TEXT = {
    "title": "Klif nad morzem",
    "artist": "Stefan Nowak",
    "date_text": "ok. 1965",
    "medium": "olej na płótnie",
    "description": "Prezent od dziadka na ślub rodziców.",
    "hangs": "Salon",
    "origin": "Rodzinne, po dziadku",
    "height_cm": 46,
    "width_cm": 55,
}


def test_a_photograph_becomes_a_work_cut_out_of_its_frame(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(CORNERS))[1]
    with _client(service) as client:
        sent = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(photo()))})
        assert sent.status_code == 200, sent.text
        token = sent.json()["token"]
        assert (sent.json()["width"], sent.json()["height"]) == (W, H)
        assert sent.json()["corners"] is None  # not asked yet

        found = client.post(f"/api/own/photos/{token}/find").json()
        assert [p["model"] for p in fake.asked] == [OPUS]
        assert "owner took with a phone" in fake.asked[0]["messages"][0]["content"][-1]["text"]
        assert found["shape"] == "rectangle"
        corners = found["corners"]
        assert corners is not None
        # Snapped onto the frame's opening, as for a museum's photograph.
        assert abs(corners[0][0] - 180 / W) < 0.02 and abs(corners[2][1] - 570 / H) < 0.02

        added = client.post(
            "/api/own/works",
            json={"token": token, "corners": corners, "shape": found["shape"], "text": TEXT},
        )
        assert added.status_code == 200, added.text
        work = added.json()
        assert work["kind"] == "own" and work["source"] == "upload"
        assert work["title"] == "Klif nad morzem" and work["year"] == 1965
        assert work["medium"] == "olej na płótnie"
        assert work["own"] == {
            "hangs": "Salon",
            "origin": "Rodzinne, po dziadku",
            "height_cm": 46.0,
            "width_cm": 55.0,
        }
        assert work["cut"]["by"] == "auto" and work["cut"]["shape"] == "rectangle"
        # The photograph waits no longer.
        assert client.post(f"/api/own/photos/{token}/find").status_code == 404

    item = service.library.get(work["id"])
    assert item is not None and item.kind == ItemKind.OWN
    # The original is the painting alone; the photograph whole stays.
    with Image.open(service.images.image_path(item)) as img:
        assert abs(img.width / img.height - 540 / 440) < 0.05
    assert service.images.full_path(item).is_file()
    assert service.sizes.size(item) is not None
    assert (service.sizes.size(item).height, service.sizes.size(item).width) == (46, 55)  # type: ignore[union-attr]
    summary = ItemSummary.of(item)
    assert summary.cropped and summary.own is not None and summary.own.hangs == "Salon"


def test_his_corners_his_description_a_new_photograph_and_delete(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    whole = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    mine = [[0.2, 0.18], [0.8, 0.18], [0.8, 0.82], [0.2, 0.82]]
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(photo()))}).json()[
            "token"
        ]
        work = client.post(
            "/api/own/works",
            json={"token": token, "corners": mine, "by": "owner", "text": {"title": "Szkic"}},
        ).json()
        assert work["cut"]["by"] == "owner" and work["own"]["height_cm"] is None
        # "Moje dzieła" in Playlisty: his works, the last added first.
        listed = client.get(
            "/api/library/items", params={"kind": "own", "source": "upload", "sort": "recent"}
        ).json()
        assert [i["id"] for i in listed["items"]] == [work["id"]]
        assert listed["items"][0]["own"]["height_cm"] is None
        assert service.sizes.size(service.library.get(work["id"])) is None  # type: ignore[arg-type]
        assert not fake.asked  # nothing asked of Claude

        again = client.put(f"/api/own/works/{work['id']}", json={**TEXT, "title": "Klif"}).json()
        assert again["title"] == "Klif" and again["own"]["hangs"] == "Salon"
        assert again["cut"]["by"] == "owner"  # the cut stays

        # "Popraw kadr" on his work, as on a museum's.
        put = client.put(f"/api/library/items/{work['id']}/cut", json={"corners": whole[:4]})
        assert put.status_code in (200, 422)  # the whole photograph is no cut
        put = client.put(
            f"/api/library/items/{work['id']}/cut",
            json={"corners": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]},
        )
        assert put.status_code == 200, put.text

        # "Zrób zdjęcie ponownie": a new photograph, cut; the text stays.
        token = client.post("/api/own/photos", files={"file": ("q.jpg", _jpeg(photo()))}).json()[
            "token"
        ]
        new = client.put(
            f"/api/own/works/{work['id']}/photo",
            json={"token": token, "corners": mine, "by": "owner"},
        )
        assert new.status_code == 200, new.text
        assert new.json()["title"] == "Klif" and new.json()["cut"]["work"][0] == [0.2, 0.18]

        # A museum's work is no work of his.
        bad = client.put("/api/own/works/met:1", json=TEXT)
        assert bad.status_code == 404

        assert client.delete(f"/api/library/items/{work['id']}").json() == {"deleted": True}
        assert service.library.get(work["id"]) is None


def test_hints_are_read_off_the_cut_picture(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    read = {
        "signature": "St. Nowak 65",
        "artist": "St. Nowak",
        "date": "1965",
        "technique": "oil",
        "support": "canvas",
        "title": "Pejzaż morski z klifem",
        "sure": True,
    }
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(read))[1]
    corners = [[0.2, 0.18], [0.8, 0.18], [0.8, 0.82], [0.2, 0.82]]
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(photo()))}).json()[
            "token"
        ]
        hints = client.post("/api/own/hints", json={"token": token, "corners": corners})
        assert hints.status_code == 200, hints.text
        assert hints.json() == read
        assert [p["model"] for p in fake.asked] == [SONNET]
        assert client.post("/api/own/hints", json={"token": "nope"}).status_code == 404
        no_picture = client.post("/api/own/photos", files={"file": ("x.jpg", b"nope")})
        assert no_picture.status_code == 422


def test_without_a_key_nothing_is_found_and_old_photographs_go(service: FrameService) -> None:
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(photo()))}).json()[
            "token"
        ]
        assert client.post(f"/api/own/photos/{token}/find").status_code == 503
        assert client.post("/api/own/hints", json={"token": token}).status_code == 503
    path = service.own_works.path(token)
    old = time.time() - 2 * 24 * 3600
    os.utime(path, (old, old))
    service.own_works.prune()
    assert not path.exists()
