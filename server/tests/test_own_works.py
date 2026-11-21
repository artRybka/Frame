"""Works of the owner's own ("Dodaj własne dzieło", Mateusz 2026-11-15):
the photograph sent, the work found in it by Opus and cut out of its frame,
hints read off it, the work added with what he wrote, described again,
photographed again, corrected and deleted."""

from __future__ import annotations

import io
import os
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_ai import FakeAnthropic, _message, fake  # noqa: F401  (fixture)
from test_crops import CORNERS, H, W, photo

from frame_server.ai.client import OPUS, SONNET
from frame_server.library.models import ItemKind, ItemSummary
from frame_server.service import FrameService


@pytest.fixture(autouse=True)
def _claude_cuts(request: pytest.FixtureRequest) -> None:
    """Here Opus finds his works in their photographs, as before the
    phone did (``test_the_phone_finds_the_work_and_opus_is_asked_nothing``)."""
    if "service" in request.fixturenames:
        from frame_server.ai.config import AiConfigUpdate

        service = request.getfixturevalue("service")
        service.ai_config.update(AiConfigUpdate(crops_on_phone=False))


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
            # An app that writes the technique as one line: the two are not known.
            "technique": "",
            "support": "",
            "by": "",  # the owner's
        }
        assert work["cut"]["by"] == "auto" and work["cut"]["shape"] == "rectangle"
        # The photograph waits no longer.
        assert client.post(f"/api/own/photos/{token}/find").status_code == 404

    item = service.library.get(work["id"])
    assert item is not None and item.kind == ItemKind.OWN
    # The original is the painting alone; the photograph whole stays.
    # Its shape is his size's (55 × 46 cm), not the corners' (540 × 440 px).
    with Image.open(service.images.image_path(item)) as img:
        assert abs(img.width / img.height - 55 / 46) < 0.005
    assert service.images.full_path(item).is_file()
    assert service.sizes.size(item) is not None
    assert (service.sizes.size(item).height, service.sizes.size(item).width) == (46, 55)  # type: ignore[union-attr]
    summary = ItemSummary.of(item)
    assert summary.cropped and summary.own is not None and summary.own.hangs == "Salon"
    # The tile has the shape of his size too, not the corners'.
    assert summary.width and summary.height
    assert abs(summary.width / summary.height - 55 / 46) < 0.005

    # A work added before its picture took his size's shape: cut anew once.
    own = item.own
    bare = service.library.update(item.id, own=None)
    assert bare is not None and service.images.recut(bare)
    with Image.open(service.images.image_path(item)) as img:
        assert abs(img.width / img.height - 55 / 46) > 0.01
    service.library.update(item.id, own=own)
    assert service.own_works.reshape() == 1
    with Image.open(service.images.image_path(item)) as img:
        assert abs(img.width / img.height - 55 / 46) < 0.005
    assert service.own_works.reshape() == 0


def test_the_phone_finds_the_work_and_opus_is_asked_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Mateusz 2026-11-21 20:44 UTC: „kadrowanie moich własnych dzieł na
    # pewno chce robić na iPhone, bez Opus”.
    from frame_server.ai.config import AiConfigUpdate

    service.ai_config.update(AiConfigUpdate(crops_on_phone=True))
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(CORNERS))[1]
    with _client(service) as client:
        sent = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(photo()))})
        token = sent.json()["token"]
        found = client.post(f"/api/own/photos/{token}/find").json()
        assert found["phone_cuts"] and found["corners"] is None and not found["looked"]
        assert fake.asked == []
        # What the phone found itself is kept: the frame's edge with it.
        corners = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        frame = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        kept = client.post(
            f"/api/own/photos/{token}/found", json={"corners": corners, "surround": frame}
        ).json()
        assert kept["looked"] and kept["phone_cuts"] and kept["surround_kind"] == "frame"
        assert client.post(f"/api/own/photos/{token}/find").json()["corners"] == corners
        added = client.post(
            "/api/own/works", json={"token": token, "corners": corners, "text": TEXT}
        )
        assert added.status_code == 200, added.text
        assert added.json()["cut"]["surround"] is not None
        assert all(p["model"] != OPUS for p in fake.asked)


def test_the_frame_about_a_work_of_his_own_holds_it_in_the_shape_of_his_size(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    """Mateusz 2026-11-18 21:44 UTC, his "Out of the box" (29 × 40 cm) on
    the card with its frame on: "Podwójny obraz po wyświetleniu ramy -
    sprawdzisz z czego wynika i jak naprawić? (To mój skan)". The work is
    shown in the shape of his size; the frame's photograph, set straight
    by the frame's own corners, held the work 5% wider, and showed beside
    the work laid on it: the picture's edge twice, left and right."""
    from test_crops import FRAME, PAINTING

    from frame_server.ai.crops import framed as as_framed

    fake.messages.create = lambda **params: (fake.asked.append(params), _message(CORNERS))[1]
    # Narrower than the corners say (540 × 440 px), by a tenth.
    text = TEXT | {"height_cm": 44, "width_cm": 48}
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(photo()))}).json()[
            "token"
        ]
        found = client.post(f"/api/own/photos/{token}/find").json()
        added = client.post(
            "/api/own/works",
            json={"token": token, "corners": found["corners"], "shape": "rectangle", "text": text},
        )
        assert added.status_code == 200, added.text
    item = service.library.get(added.json()["id"])
    assert item is not None
    x0, y0, x1, y1 = FRAME
    edge = [(x0 / W, y0 / H), (x1 / W, y0 / H), (x1 / W, y1 / H), (x0 / W, y1 / H)]
    item = service.crops.set_by_owner(item, frame=edge)
    cut = item.cut
    assert cut is not None and cut.framed_kind == "frame" and cut.framed_inner is not None
    with Image.open(service.images.image_path(item)) as img:
        shown = img.width / img.height
    assert abs(shown - 48 / 44) < 0.005

    def place(of: Any) -> float:
        left, top, right, bottom = of.framed_inner
        return float((right - left) * of.framed_aspect / (bottom - top))

    # The work's place in the frame has the shape the work is shown in…
    assert abs(place(cut) - shown) < 0.005
    # …which the frame's own corners do not give it.
    assert abs(place(as_framed(cut)) - 540 / 440) < 0.01
    # The frame's photograph is that picture: the painting where the work
    # is laid, the gilt frame about it.
    around = service.images.framed(item, 4000)
    assert around is not None and abs(around.width / around.height - cut.framed_aspect) < 0.005
    a = np.asarray(around.convert("RGB")).astype(int)
    left, top, right, bottom = cut.framed_inner
    for x, y in ((left, 0.5), (right, 0.5), (0.5, top), (0.5, bottom)):
        px, py = x * around.width, y * around.height
        inside = a[round(py + (0.5 - y) * 16), round(px + (0.5 - x) * 16)]
        outside = a[round(py - (0.5 - y) * 16), round(px - (0.5 - x) * 16)]
        assert inside[2] > inside[0] + 40, (x, y)  # the painting, bluish
        assert abs(outside - (200, 160, 60)).max() < 30, (x, y)  # the frame
    assert abs(left - (PAINTING[0] - x0) / (x1 - x0)) < 0.01
    assert abs(bottom - (PAINTING[3] - y0) / (y1 - y0)) < 0.01

    # A frame set before it took the work's shape (to 1.145.244): given it
    # once after a start, the work's pictures as they are.
    service.library.update(item.id, cut=as_framed(cut))
    assert service.own_works.reshape() == 0
    again = service.library.get(item.id)
    assert again is not None and again.cut is not None
    assert (again.cut.framed_aspect, again.cut.framed_inner) == (
        cut.framed_aspect,
        cut.framed_inner,
    )
    # He gives another size: the frame goes with the work.
    with _client(service) as client:
        told = client.put(f"/api/own/works/{item.id}", json=text | {"width_cm": 52})
        assert told.status_code == 200, told.text
    wider = service.library.get(item.id)
    assert wider is not None and wider.cut is not None
    assert abs(place(wider.cut) - 52 / 44) < 0.005
    # A museum's work has no size to go by: its frame is as it was.
    plain = wider.cut
    assert as_framed(plain, None).framed_aspect == as_framed(plain).framed_aspect


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
        # The technique and the support as he wrote the two (Mateusz 2026-11-19
        # 20:38 UTC), kept beside the line the app wrote of them for the card.
        two = {**TEXT, "title": "Klif", "technique": " olej ", "support": "płótno"}
        split = client.put(f"/api/own/works/{work['id']}", json=two).json()
        assert split["medium"] == "olej na płótnie"
        assert (split["own"]["technique"], split["own"]["support"]) == ("olej", "płótno")
        listed = client.get(
            "/api/library/items", params={"kind": "own", "source": "upload", "sort": "recent"}
        ).json()
        assert listed["items"][0]["own"]["support"] == "płótno"
        # An app that knows the line alone changes it: the two are not kept
        # to say another thing than the line.
        line = client.put(
            f"/api/own/works/{work['id']}", json={**TEXT, "title": "Klif", "medium": "akwarela"}
        ).json()
        assert line["medium"] == "akwarela"
        assert (line["own"]["technique"], line["own"]["support"]) == ("", "")
        stored = service.library.get(work["id"])
        assert stored is not None
        # Cut anew to the shape of the size he gave now.
        with Image.open(service.images.image_path(stored)) as img:
            assert abs(img.width / img.height - 55 / 46) < 0.005
        # A size far off the photograph (a slip) leaves the corners' shape.
        client.put(f"/api/own/works/{work['id']}", json={**TEXT, "width_cm": 550})
        with Image.open(service.images.image_path(stored)) as img:
            assert abs(img.width / img.height - 540 / 448) < 0.02
        client.put(f"/api/own/works/{work['id']}", json={**TEXT, "title": "Klif"})

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


def test_a_work_of_his_own_gets_a_curators_note_with_his_words_kept() -> None:
    """Mateusz 2026-11-16: "Dzieło dodane ręcznie powinno mieć normalnie
    tworzoną notatkę": Sonnet's note as for a museum work with no
    description (however long his own note), his note one of its facts,
    nothing asked of Wikidata; his title, date and technique stay."""
    from frame_server.ai.pl_text import PlTextJob, clean, request_text, written_for
    from frame_server.library import Item
    from frame_server.library.models import OwnWork

    long_note = "Prezent od dziadka na ślub rodziców. " * 8
    item = Item(
        id="upload:abc", kind=ItemKind.OWN, source="upload", source_id="abc",
        title="Klif nad morzem", artist="Stefan Nowak", date_text="ok. 1965",
        medium="olej na płótnie", description=long_note,
        own=OwnWork(hangs="Salon", origin="po dziadku", height_cm=46, width_cm=55),
    )  # fmt: skip
    assert PlTextJob.applies(item)
    assert written_for(item) == "note"
    asked = request_text(item, None)  # type: ignore[arg-type]  # never read for his own
    assert "domowej kolekcji" in asked and "Prezent od dziadka" in asked
    assert "46 × 55 cm" in asked and "po dziadku" in asked and "Muzeum" not in asked
    text = clean(
        {"title": "Klify", "frame": "Wysoki klif nad spokojnym morzem w popołudniowym świetle.",
         "full": "Wysoki klif nad spokojnym morzem.", "medium": "olej", "date": "1965",
         "artist_note": "", "sources": ["obraz"], "style": "opis"},
        item, None,
    )  # fmt: skip
    assert text is not None and text.written == "note"
    assert (text.title, text.date, text.medium) == (
        "Klif nad morzem",
        "ok. 1965",
        "olej na płótnie",
    )


def _glare(img: np.ndarray, cx: int, cy: int) -> np.ndarray:
    yy, xx = np.mgrid[0 : img.shape[0], 0 : img.shape[1]]
    g = np.exp(-(((xx - cx) / 90) ** 2 + ((yy - cy) / 60) ** 2)) * 0.85
    return np.clip(img * (1 - g[..., None]) + 255 * g[..., None], 0, 255).astype(np.uint8)


def test_the_lamps_reflection_is_taken_out_by_two_photographs_from_the_side(
    service: FrameService,
) -> None:
    """The scan of three (Mateusz 2026-11-16): where the first photograph
    has a glare the side ones have not, their pixels take its place; the
    rest of it is left as it was."""
    rng = np.random.default_rng(1)
    h, w = 1600, 1200
    work = cv2.resize(
        rng.integers(0, 200, (40, 30, 3), dtype=np.uint8), (w, h), interpolation=cv2.INTER_CUBIC
    )
    work = cv2.add(work, rng.integers(0, 30, (h, w, 3), dtype=np.uint8))

    def side(dx: int, cx: int) -> np.ndarray:
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32([[dx, 10], [w + dx * 0.7, -15], [w + dx, h + 5], [dx * 1.2, h]])
        seen = cv2.warpPerspective(
            work, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(90, 90, 90)
        )
        return _glare(seen, cx, 500)

    def png(img: np.ndarray) -> bytes:
        out = io.BytesIO()
        Image.fromarray(img).save(out, "PNG")
        return out.getvalue()

    first = _glare(work, 400, 500)
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.png", png(first))}).json()[
            "token"
        ]
        for n, (dx, cx) in enumerate([(-60, 700), (60, 150)], start=1):
            sent = client.post(
                f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(side(dx, cx)))}
            )
            assert sent.status_code == 200, sent.text
            assert sent.json() == {"sides": n}
        merged = client.post(f"/api/own/photos/{token}/merge")
        assert merged.status_code == 200, merged.text
        assert merged.json()["used"] == 2 and 0.003 < merged.json()["replaced"] < 0.05
        assert (merged.json()["width"], merged.json()["height"]) == (w, h)
        got = client.get(f"/api/own/photos/{token}")
        assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
        assert client.get("/api/own/photos/0123456789abcdef01234567").status_code == 404
        assert client.post("/api/own/photos/0123456789abcdef01234567/merge").status_code == 404

    with Image.open(service.own_works.path(token)) as img:
        out = np.asarray(img.convert("RGB")).astype(int)
    lamp = (slice(450, 550), slice(330, 470))
    assert np.abs(first[lamp].astype(int) - work[lamp]).mean() > 60
    assert np.abs(out[lamp] - work[lamp]).mean() < 12
    # Away from the glare only the JPEG has touched it (the noise is fine grained).
    away = (slice(1000, 1500), slice(100, 1100))
    assert np.abs(out[away] - first[away]).mean() < 9
    assert not list(service.own_works.incoming.glob(f"{token}-side*"))


def test_of_several_from_one_side_the_scan_is_made_of_the_one_nearest_thirty_degrees(
    service: FrameService,
) -> None:
    """Mateusz 2026-11-18 ("może kolejne zdjęcia nie muszą być dokładnie
    pod 30° i trzeba pozwolić na więcej skanów pod różnymi kątami?"; he
    chose the one arc): the phone takes a few photographs on its way round
    the work and says from where. The scan is made as it was, of one from
    each side; the others are kept beside it to learn from."""
    from frame_server import own_works

    first = _jpeg(photo())
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", first)}).json()["token"]
        # On the way out to the left, then where it is meant; the right the same.
        for n, angle in enumerate([-14.2, -27.6, 16.0, 33.1, 24.9, 41.0], start=1):
            sent = client.post(
                f"/api/own/photos/{token}/sides",
                params={"angle": angle},
                files={"file": ("s.jpg", first)},
            )
            assert sent.status_code == 200 and sent.json() == {"sides": n}, sent.text
        assert own_works.SIDES == 6
        full = client.post(
            f"/api/own/photos/{token}/sides", params={"angle": 30}, files={"file": ("s.jpg", first)}
        )
        assert full.status_code == 422
        assert (
            client.post(
                f"/api/own/photos/{token}/sides",
                params={"angle": 120},
                files={"file": ("s.jpg", first)},
            ).status_code
            == 422
        )
        merged = client.post(
            f"/api/own/photos/{token}/merge", json={"trace": {"pinned": 1.4, "side1_rate": 0.3}}
        )
        assert merged.status_code == 200 and merged.json()["used"] == 2, merged.text
        kept = client.get("/api/debug/own-scans").json()[0]
        assert sorted(kept["files"]) == ["first.jpg"] + [f"more{n}.jpg" for n in (1, 2, 3, 4)] + [
            "side1.jpg",
            "side2.jpg",
        ]
        assert kept["angles"] == {"side1.jpg": -27.6, "side2.jpg": 33.1} | {
            "more1.jpg": -14.2,
            "more2.jpg": 16.0,
            "more3.jpg": 24.9,
            "more4.jpg": 41.0,
        }
        assert kept["trace"] == {"pinned": 1.4, "side1_rate": 0.3}
        assert client.get(f"/api/debug/own-scans/{token}/more4.jpg").status_code == 200
    assert not list(service.own_works.incoming.glob(f"{token}-side*"))
    assert not service.own_works.path(token).with_suffix(own_works.ANGLES).exists()

    # Where the phone did not say (an app before the one arc): all of them.
    here = [service.own_works.incoming / f"{token}-side{n}.jpg" for n in (1, 2, 3)]
    chosen = own_works.OwnWorks.chosen
    assert chosen(here, {}) == (here, [])
    assert chosen(here, {1: -30.0, 3: 30.0}) == (here, [])
    assert chosen(here[:2], {1: -30.0, 2: 29.0}) == (here[:2], [])
    # Both from one side: the scan is made of the one.
    assert chosen(here[:2], {1: -16.0, 2: -29.0}) == ([here[1]], [here[0]])
    assert chosen(here, {1: 12.0, 2: -35.0, 3: 27.0}) == ([here[1], here[2]], [here[0]])


def test_side_photographs_of_something_else_change_nothing() -> None:
    from frame_server.imaging.glare import merge

    rng = np.random.default_rng(2)
    first = rng.integers(0, 255, (600, 450, 3), dtype=np.uint8)
    other = rng.integers(0, 255, (600, 450, 3), dtype=np.uint8)
    done = merge(first, [other])
    assert done.used == 0 and done.replaced == 0 and done.image is first


def test_a_work_of_his_own_is_kept_as_large_as_he_photographed_it(
    service: FrameService,
) -> None:
    """Mateusz 2026-11-16: "Dla własnych dzieł ustaw zdecydowanie wyższą
    jakość niż 4000px". The phone's 48 MP whole waits, is kept beside the
    work, and the work cut out of all its pixels is served in tiles to the
    full-screen viewer; the original the card and the frame work on stays
    an original's size."""
    from frame_server.library.images import FINE_TILE, IMAGE_MAX

    big = photo().resize((8064, 6272), Image.Resampling.BICUBIC)
    mine = [[0.2, 0.18], [0.8, 0.18], [0.8, 0.82], [0.2, 0.82]]
    with _client(service) as client:
        sent = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(big))}).json()
        assert (sent["width"], sent["height"]) == big.size  # not made smaller
        token = sent["token"]
        # The phone sets the corners on a smaller copy.
        small = client.get(f"/api/own/photos/{token}", params={"side": 3000})
        assert small.status_code == 200
        with Image.open(io.BytesIO(small.content)) as img:
            assert max(img.size) == 3000
        assert client.get(f"/api/own/photos/{token}", params={"side": 20}).status_code == 422

        work = client.post(
            "/api/own/works",
            json={"token": token, "corners": mine, "by": "owner", "text": {"title": "Duże"}},
        ).json()
        item = service.library.get(work["id"])
        assert item is not None
        images = service.images
        with Image.open(images.master_path(item)) as img:
            assert img.size == big.size
        with Image.open(images.full_path(item)) as img:
            assert max(img.size) == IMAGE_MAX  # "Pełny kadr", as before
        with Image.open(images.image_path(item)) as img:
            assert max(img.size) == IMAGE_MAX
            shape = img.width / img.height

        fine = client.get(f"/api/library/items/{work['id']}/fine").json()
        # Three fifths of 8064 px across: far more than the original has.
        assert 4700 < fine["width"] < 4900 and abs(fine["width"] / fine["height"] - shape) < 0.01
        tiles = fine["tiles"]
        assert len(tiles) == 3 * 2 and fine["stamp"]
        assert abs(sum(t["w"] for t in tiles[:3]) - 1) < 1e-9
        assert abs(sum(t["h"] for t in tiles[::3]) - 1) < 1e-9
        assert tiles[4]["x"] == tiles[1]["x"] and tiles[4]["y"] == tiles[0]["h"]
        got = client.get(f"/api/library/items/{work['id']}/fine/{tiles[4]['id']}")
        assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
        with Image.open(io.BytesIO(got.content)) as img:
            assert img.width == tiles[4]["pixels"] <= FINE_TILE
        assert client.get(f"/api/library/items/{work['id']}/fine/9-9").status_code == 404

        # "Popraw kadr": cut anew out of all its pixels, the tiles new.
        put = client.put(
            f"/api/library/items/{work['id']}/cut",
            json={"corners": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]},
        )
        assert put.status_code == 200, put.text
        wider = client.get(f"/api/library/items/{work['id']}/fine").json()
        assert wider["width"] > 6000 and wider["stamp"] != fine["stamp"]

        # A small photograph in its place: nothing more than its original.
        token = client.post("/api/own/photos", files={"file": ("q.jpg", _jpeg(photo()))}).json()[
            "token"
        ]
        new = client.put(
            f"/api/own/works/{work['id']}/photo",
            json={"token": token, "corners": mine, "by": "owner"},
        )
        assert new.status_code == 200, new.text
        assert client.get(f"/api/library/items/{work['id']}/fine").json()["tiles"] == []
        assert not images.master_path(item).exists() and not images.fine_dir(item).exists()

        # A museum's work has none.
        assert client.get("/api/library/items/upload:nothing/fine").status_code == 404


def test_a_scans_photographs_are_kept_two_weeks(service: FrameService) -> None:
    """Mateusz 2026-11-16 ("Tak, przez 14 dni"): the first photograph as
    it came and its side ones stay for the merging to be tuned on."""
    from frame_server.own_works import SCANS_SECONDS

    first = _jpeg(photo())
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", first)}).json()["token"]
        # Without side photographs it is no scan.
        client.post(f"/api/own/photos/{token}/merge")
        assert client.get("/api/debug/own-scans").json() == []
        for _ in range(2):
            client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.jpg", first)})
        client.post(f"/api/own/photos/{token}/merge")
        kept = client.get("/api/debug/own-scans").json()
        assert [s["token"] for s in kept] == [token] and kept[0]["used"] == 2
        assert sorted(kept[0]["files"]) == ["first.jpg", "side1.jpg", "side2.jpg"]
        got = client.get(f"/api/debug/own-scans/{token}/side2.jpg")
        assert got.status_code == 200 and len(got.content) == kept[0]["files"]["side2.jpg"]
        assert client.get(f"/api/debug/own-scans/{token}/scan.json").status_code == 404
        assert client.get(f"/api/debug/own-scans/{token}/..%2Ffirst.jpg").status_code == 404

    folder = service.own_works.scans / token
    service.own_works.prune()
    assert folder.is_dir()
    old = time.time() - SCANS_SECONDS - 60
    os.utime(folder, (old, old))
    service.own_works.prune()
    assert not folder.exists()


def test_the_phone_merges_a_kept_scan_itself_for_the_trial(service: FrameService) -> None:
    """Mateusz 2026-11-19 00:12 UTC: "Najpierw próba na iPhonie". The phone
    is given a kept scan's photographs as the server's merge reads them,
    and what it made of them itself is kept beside them to be compared.
    Nothing of his collection changes."""
    first = _jpeg(photo())
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", first)}).json()["token"]
        for _ in range(2):
            client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.jpg", first)})
        client.post(f"/api/own/photos/{token}/merge")
        scan = f"/api/debug/own-scans/{token}"
        folder = service.own_works.scans / token

        got = client.get(f"{scan}/first.jpg/pixels")
        assert got.status_code == 200, got.text
        assert int(got.headers["content-length"]) == len(got.content)
        pixels = np.load(io.BytesIO(got.content))
        with Image.open(folder / "first.jpg") as img:
            assert np.array_equal(pixels, np.asarray(img.convert("RGB")))
        side = np.load(io.BytesIO(client.get(f"{scan}/side2.jpg/pixels").content))
        assert side.shape == pixels.shape and side.dtype == np.uint8
        for name in ("side3.jpg", "scan.json", "phone.npy"):
            assert client.get(f"{scan}/{name}/pixels").status_code == 404

        # What the phone made of them, and what it noted: beside the scan,
        # which is no younger for it (two weeks and it goes).
        old = time.time() - 3600
        os.utime(folder, (old, old))
        made = io.BytesIO()
        np.save(made, pixels[::-1])
        put = client.put(f"{scan}/phone.npy", content=made.getvalue())
        assert put.status_code == 200, put.text
        assert put.json() == {"bytes": len(made.getvalue())}
        note = {"seconds": 5.2, "model": "iPhone18,2", "took": {"laid": 2.1}}
        assert client.put(f"{scan}/phone.json", json=note).status_code == 200
        kept = client.get("/api/debug/own-scans").json()[0]
        assert kept["files"]["phone.npy"] == len(made.getvalue()) and "phone.json" in kept["files"]
        assert client.get(f"{scan}/phone.json").json() == note
        back = np.load(io.BytesIO(client.get(f"{scan}/phone.npy").content))
        assert np.array_equal(back, pixels[::-1])
        assert abs(folder.stat().st_mtime - old) < 2

        # No picture, no note, a photograph of the scan's, no such scan:
        # nothing is taken, and what was there stays.
        assert client.put(f"{scan}/phone.npy", content=b"nothing").status_code == 422
        assert client.put(f"{scan}/phone.json", content=b"[1]").status_code == 422
        assert client.put(f"{scan}/first.jpg", content=first).status_code == 404
        other = f"/api/debug/own-scans/{'0' * 24}/phone.npy"
        assert client.put(other, content=made.getvalue()).status_code == 404
        assert client.get(f"{scan}/phone.npy").content == made.getvalue()
        assert not list(service.own_works.incoming.glob("*.part"))
        with Image.open(folder / "first.jpg") as img:
            assert np.array_equal(pixels, np.asarray(img.convert("RGB")))


def test_the_phone_makes_the_scan_and_the_server_keeps_it(service: FrameService) -> None:
    """Mateusz 2026-11-19 07:42 UTC: "Tak, składaj na iPhonie" (some 4 s
    there against 34 s here). The phone sends the scan it made of its own
    photographs: it is kept in the first photograph's place as the
    server's own would be, and the photographs as they came are kept.
    The server makes none of its own beside it (08:08 UTC: "nie róbmy
    porównań dla każdego skanu")."""
    import json

    from test_reflections import CORNERS as WORK
    from test_reflections import _three

    from frame_server.imaging.reflections import merge

    clean, first, sides = _three()
    seen = [(0.22, 0.2), (0.78, 0.2), (0.78, 0.8), (0.22, 0.8)]
    inner = (slice(540, 660), slice(440, 600))  # the lamp in the middle of the work

    def png(img: np.ndarray) -> bytes:
        out = io.BytesIO()
        Image.fromarray(img).save(out, "PNG")
        return out.getvalue()

    def off(path: Path) -> float:
        with Image.open(path) as img:
            got = np.asarray(img.convert("RGB")).astype(int)
        return float(np.abs(got[inner] - clean[inner]).mean())

    def sent(client: TestClient) -> str:
        token = client.post("/api/own/photos", files={"file": ("p.png", png(first))}).json()
        assert token["phone"] is True  # no chart set its colours: the phone may merge it
        for side in sides:
            client.post(
                f"/api/own/photos/{token['token']}/sides", files={"file": ("s.png", png(side))}
            )
        return str(token["token"])

    def scan(corners: list[tuple[float, float]], **more: object) -> dict[str, str]:
        note = {"corners": corners, "used": 2, "replaced": 0.0661, **more}
        return {"note": json.dumps(note)}

    # What the phone makes: the same merging, of the photographs it took.
    phone = merge(first, sides, seen, True)
    assert phone.used == 2 and phone.removed > 0.03
    picture = _jpeg(Image.fromarray(phone.image))
    told = {"seconds": 3.9, "model": "iPhone19,7", "took": {"laid": 0.96, "whole": 0.57}}

    with _client(service) as client:
        token = sent(client)
        path = service.own_works.path(token)
        folder = service.own_works.scans / token
        veiled = off(path)
        url = f"/api/own/photos/{token}/merged"

        # No scan of this photograph: another size, no picture where light
        # was taken off, corners or a note that are none. Nothing changes.
        small = _jpeg(Image.fromarray(phone.image[::2, ::2]))
        for files, data in (
            ({"file": ("m.jpg", small)}, scan(seen)),
            ({"file": ("m.jpg", b"nothing")}, scan(seen)),
            ({}, scan(seen)),
            ({"file": ("m.jpg", picture)}, scan([(0, 0), (0, 0), (0, 0), (0, 0)])),
            ({"file": ("m.jpg", picture)}, scan(seen, used=9)),
            ({"file": ("m.jpg", picture)}, {"note": "[]"}),
        ):
            assert client.post(url, files=files or None, data=data).status_code == 422
        assert client.post(f"/api/own/photos/{'0' * 24}/merged", data=scan(seen)).status_code == 404
        assert off(path) == veiled and not folder.exists()
        assert len(list(service.own_works.incoming.glob(f"{token}-side*.jpg"))) == 2

        made = client.post(
            url,
            files={"file": ("m.jpg", picture)},
            data=scan(seen, trace={"arc": 11.5}, phone=told),
        )
        assert made.status_code == 200, made.text
        assert made.json()["used"] == 2 and made.json()["replaced"] == 0.0661
        assert made.json()["corners"] == [list(c) for c in seen]
        # The phone's own file is the photograph that waits now.
        assert path.read_bytes() == picture and off(path) < veiled / 2
        assert not list(service.own_works.incoming.glob(f"{token}-side*.jpg"))
        kept = client.get("/api/debug/own-scans").json()[0]
        assert kept["phone"] == told and kept["trace"] == {"arc": 11.5}
        assert kept["used"] == 2 and kept["replaced"] == 0.0661
        # The photographs as they came, and nothing the server made beside them.
        assert set(kept["files"]) == {"first.jpg", "side1.jpg", "side2.jpg"}
        assert off(folder / "first.jpg") == veiled

        # He sets the corners wider than what the phone had cleaned: it
        # merges again within his and sends that, which takes the first
        # one's place; adding the work then merges nothing here.
        wider = merge(first, sides, WORK, True)
        again = _jpeg(Image.fromarray(wider.image))
        twice = client.post(url, files={"file": ("m.jpg", again)}, data=scan(WORK, replaced=0.07))
        assert twice.status_code == 200, twice.text
        noted = client.get("/api/debug/own-scans").json()[0]
        assert noted["again"] and noted["replaced"] == 0.07 and noted["phone"] == {}
        assert np.allclose(noted["corners"], WORK) and path.read_bytes() == again
        added = client.post(
            "/api/own/works", json={"token": token, "corners": WORK, "by": "owner", "text": TEXT}
        )
        assert added.status_code == 200, added.text
        assert client.get("/api/debug/own-scans").json()[0]["again"] == noted["again"]

        # "Na wprost" has the first photograph back as ever, and then no
        # scan of the phone's replaces it: he chose the one photograph.
        token = sent(client)
        path = service.own_works.path(token)
        url = f"/api/own/photos/{token}/merged"
        assert (
            client.post(url, files={"file": ("m.jpg", picture)}, data=scan(seen)).status_code == 200
        )
        assert client.post(f"/api/own/photos/{token}/single").json() == {"single": True}
        assert off(path) == veiled
        assert (
            client.post(url, files={"file": ("m.jpg", picture)}, data=scan(seen)).status_code == 422
        )

        # Nothing taken off: no picture comes, and the photograph stays.
        token = sent(client)
        path = service.own_works.path(token)
        nothing = client.post(
            f"/api/own/photos/{token}/merged", data=scan(seen, replaced=0, doubt=True)
        )
        assert nothing.status_code == 200, nothing.text
        assert off(path) == veiled
        last = client.get("/api/debug/own-scans").json()[0]
        assert last["token"] == token and last["replaced"] == 0 and last["doubt"] is False


def test_a_scan_merged_as_the_server_no_longer_merges_is_made_again_here(
    service: FrameService,
) -> None:
    """The app is updated apart from the server. A lamp's wide light on
    his e-paper frame's screen left a violet patch (2026-11-19 11:01 UTC:
    "zobacz na łatkę w górnej części ekranu po zasłonięciu lampy"), and
    the merging was changed on both: a scan the app of before makes after
    the server's update is merged as before. The phone says how its core
    merges; what says less than the server's own (or nothing, the app
    before it said) is made again here of its kept photographs after a start."""
    import json

    from test_reflections import _three

    from frame_server import own_works
    from frame_server.imaging.reflections import merge
    from frame_server.own_works import SCAN_INFO

    _, first, sides = _three()
    seen = [(0.22, 0.2), (0.78, 0.2), (0.78, 0.8), (0.22, 0.8)]
    assert own_works.PHONE_MERGING < own_works.MERGING

    def png(img: np.ndarray) -> bytes:
        out = io.BytesIO()
        Image.fromarray(img).save(out, "PNG")
        return out.getvalue()

    picture = _jpeg(Image.fromarray(merge(first, sides, seen, True).image))
    works = service.own_works
    added: dict[int | None, str] = {}
    tokens: dict[int | None, str] = {}
    with _client(service) as client:
        for said in (None, own_works.MERGING, own_works.MERGING + 3):
            token = client.post("/api/own/photos", files={"file": ("p.png", png(first))}).json()[
                "token"
            ]
            for side in sides:
                client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(side))})
            note: dict[str, object] = {"corners": seen, "used": 2, "replaced": 0.0661}
            if said is not None:
                note["merging"] = said
            made = client.post(
                f"/api/own/photos/{token}/merged",
                files={"file": ("m.jpg", picture)},
                data={"note": json.dumps(note)},
            )
            assert made.status_code == 200, made.text
            noted = json.loads((works.scans / token / SCAN_INFO).read_text())
            # No more than the server's own, whatever a newer app says.
            assert noted["merging"] == (
                own_works.PHONE_MERGING if said is None else own_works.MERGING
            )
            work = client.post(
                "/api/own/works",
                json={"token": token, "corners": seen, "by": "owner", "text": TEXT},
            )
            assert work.status_code == 200, work.text
            added[said], tokens[said] = work.json()["id"], token
        bad = client.post(
            f"/api/own/photos/{token}/merged",
            data={"note": json.dumps({"corners": seen, "used": 2, "replaced": 0, "merging": -1})},
        )
        assert bad.status_code == 422

    # After a start only the one merged as before is made again, here.
    assert works.scanned_again() == 1
    assert works.scanned_again() == 0
    for said, token in tokens.items():
        info = json.loads((works.scans / token / SCAN_INFO).read_text())
        assert info["merging"] == own_works.MERGING
        assert bool(info.get("again")) is (said is None), said
        assert info["item"] == added[said]


def test_a_veil_over_the_whole_glass_is_left_alone() -> None:
    """Mateusz's print behind glass (2026-11-16): reflections over much of
    the picture are no lamp's glare, and patches from the side photographs
    only spoiled it. Left as it is until the three are merged otherwise."""
    from frame_server.imaging.glare import MOST, merge

    rng = np.random.default_rng(3)
    h, w = 800, 600
    work = cv2.resize(
        rng.integers(0, 200, (40, 30, 3), dtype=np.uint8), (w, h), interpolation=cv2.INTER_CUBIC
    )
    work = cv2.add(work, rng.integers(0, 30, (h, w, 3), dtype=np.uint8))
    first = work
    for cx, cy in [(150, 150), (450, 150), (150, 400), (450, 400), (300, 650), (300, 280)]:
        first = _glare(first, cx, cy)
    done = merge(first, [work, work])
    assert done.used == 2 and done.replaced == 0 and done.image is first
    # One lamp is still taken out.
    one = merge(_glare(work, 300, 400), [work, work])
    assert 0 < one.replaced < MOST


def test_three_photographs_of_a_work_behind_glass_are_merged_within_its_corners(
    service: FrameService,
) -> None:
    """Mateusz 2026-11-16 (his print behind glass): what the glass
    mirrors goes within the work's corners, the phone's here; the
    corners he then sets wider than what was cleaned have the scan's
    photographs merged once more."""
    from test_reflections import CORNERS, Y0, _coded, _glass, _scene, _three

    clean, first, sides = _three()
    # One lamp more, mirrored at the work's upper rim.
    first = _coded(_scene() + _glass(0.14, None, (520, 600)) + _glass(0, None, (550, Y0 + 4)))

    def png(img: np.ndarray) -> bytes:
        out = io.BytesIO()
        Image.fromarray(img).save(out, "PNG")
        return out.getvalue()

    # The lamp in the middle of the work.
    inner = (slice(540, 660), slice(440, 600))

    # The one at its upper rim, beyond the corners the phone saw.
    rim = (slice(Y0 + 1, Y0 + 7), slice(470, 630))

    def off(path: Path, where: tuple[slice, slice]) -> float:
        with Image.open(path) as img:
            got = np.asarray(img.convert("RGB")).astype(int)
        return float(np.abs(got[where] - clean[where]).mean())

    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.png", png(first))}).json()[
            "token"
        ]
        for photo_ in sides:
            client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(photo_))})
        path = service.own_works.path(token)
        veiled, veiled_rim = off(path, inner), off(path, rim)
        # A little within the work: what the phone (or Opus) saw of it.
        seen = [(0.22, 0.2), (0.78, 0.2), (0.78, 0.8), (0.22, 0.8)]
        assert (
            client.post(
                f"/api/own/photos/{token}/merge", json={"corners": [(0, 0), (0, 0), (0, 0), (0, 0)]}
            ).status_code
            == 422
        )
        # No key, so Opus finds no work: the rectangle the phone's camera
        # followed is where the reflections go (a poor one is none).
        poor = client.post(
            f"/api/own/photos/{token}/merge", json={"outline": [(0, 0), (0, 0), (0, 0), (0, 0)]}
        )
        assert poor.status_code == 200 and poor.json()["corners"] is None
        for photo_ in sides:
            client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(photo_))})
        merged = client.post(f"/api/own/photos/{token}/merge", json={"outline": seen})
        assert merged.status_code == 200, merged.text
        assert merged.json()["used"] == 2 and merged.json()["replaced"] > 0.03
        assert merged.json()["corners"] == [list(c) for c in seen]
        scan = client.get("/api/debug/own-scans").json()[0]
        assert scan["corners"] == [list(c) for c in seen] and "again" not in scan
        # No lamp within them; the one at the rim beyond is still there.
        assert off(path, inner) < veiled / 2
        assert off(path, rim) > veiled_rim * 0.8

        added = client.post(
            "/api/own/works",
            json={"token": token, "corners": CORNERS, "by": "owner", "text": TEXT},
        )
        assert added.status_code == 200, added.text
        again = client.get("/api/debug/own-scans").json()[0]
        assert np.allclose(again["corners"], CORNERS, atol=1e-4) and again["again"]

    item = service.library.get(added.json()["id"])
    assert item is not None
    whole = service.images.museum_photo(item, urgent=True)
    assert off(whole, inner) < veiled / 2 and off(whole, rim) < veiled_rim / 2

    # "Jedno zdjęcie" on the page that shows the two (2026-11-16 19:00
    # UTC): the first photograph as it came is the work, lamps and all,
    # and his wider corners do not merge the scan's again.
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.png", png(first))}).json()[
            "token"
        ]
        assert client.post(f"/api/own/photos/{token}/single").status_code == 404  # no scan yet
        for photo_ in sides:
            client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(photo_))})
        path = service.own_works.path(token)
        assert client.post(f"/api/own/photos/{token}/merge", json={"outline": seen}).json()[
            "replaced"
        ]
        assert off(path, inner) < veiled / 2
        assert client.post(f"/api/own/photos/{token}/single").json() == {"single": True}
        assert off(path, inner) > veiled * 0.9
        added = client.post(
            "/api/own/works",
            json={"token": token, "corners": CORNERS, "by": "owner", "text": TEXT},
        )
        assert added.status_code == 200, added.text
        kept = client.get("/api/debug/own-scans").json()[0]
        assert kept["single"] and "again" not in kept
        assert client.post("/api/own/photos/nope/single").status_code == 404
    item = service.library.get(added.json()["id"])
    assert item is not None
    whole = service.images.museum_photo(item, urgent=True)
    assert off(whole, inner) > veiled * 0.9


def test_a_work_is_scanned_again_from_the_photographs_kept(
    service: FrameService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mateusz 2026-11-17 09:19 UTC, shown what 1.145.216 does with the
    lamp on his drawing: "Jest idealnie! Czy poprzednie skany przerobią
    się po wydaniu?". A work scanned before a release has what the scan
    came to then; its photographs are kept two weeks, and it is made of
    them once more, with its cut and what he wrote as they were. By
    itself (09:30 UTC: "a może być po aktualizacji która zmieniła sposób
    łączenia zdjęć?"): after a start, when the merging has changed."""
    import json

    from test_reflections import _three

    from frame_server import own_works
    from frame_server.own_works import SCAN_INFO, OwnWorks

    clean, first, sides = _three()

    def png(img: np.ndarray) -> bytes:
        out = io.BytesIO()
        Image.fromarray(img).save(out, "PNG")
        return out.getvalue()

    inner = (slice(540, 660), slice(440, 600))

    def off(path: Path) -> float:
        with Image.open(path) as img:
            got = np.asarray(img.convert("RGB")).astype(int)
        return float(np.abs(got[inner] - clean[inner]).mean())

    seen = [(0.22, 0.2), (0.78, 0.2), (0.78, 0.8), (0.22, 0.8)]
    # A release that took next to nothing out.
    monkeypatch.setattr(OwnWorks, "_merge", staticmethod(lambda *_: (2, 0.01, False)))
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.png", png(first))}).json()[
            "token"
        ]
        for photo_ in sides:
            client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(photo_))})
        veiled = off(service.own_works.path(token))
        client.post(f"/api/own/photos/{token}/merge", json={"outline": seen})
        added = client.post(
            "/api/own/works", json={"token": token, "corners": seen, "by": "owner", "text": TEXT}
        )
        assert added.status_code == 200, added.text
        # A work of one photograph has no scan.
        other = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(photo()))}).json()
        plain = client.post("/api/own/works", json={"token": other["token"], "text": TEXT})
        assert plain.status_code == 200, plain.text
    monkeypatch.undo()

    works = service.own_works
    item = service.library.get(added.json()["id"])
    one = service.library.get(plain.json()["id"])
    assert item is not None and one is not None and item.cut is not None
    assert off(service.images.museum_photo(item, urgent=True)) > veiled * 0.9
    note = works.scans / token / SCAN_INFO
    info = json.loads(note.read_text())
    assert info["item"] == item.id and info["release"]
    assert works.scan_of(item) == token and works.scan_of(one) is None
    with pytest.raises(LookupError):
        works.rescan(one)

    # Added before scans noted their work: it is the one that looks like it.
    del info["item"]
    note.write_text(json.dumps(info))
    assert works.scan_of(one) is None
    assert works.scan_of(item) == token
    assert json.loads(note.read_text())["item"] == item.id

    # After a start nothing is made again while photographs are merged
    # as they were when the scan was made one…
    assert info["merging"] == own_works.MERGING
    assert works.scanned_again() == 0
    # …and after an update that changed it, his work is.
    monkeypatch.setattr(own_works, "MERGING", own_works.MERGING + 1)
    assert works.scanned_again() == 1
    assert works.scanned_again() == 0
    again = service.library.get(item.id)
    assert again is not None
    assert off(service.images.museum_photo(again, urgent=True)) < veiled / 2
    assert again.cut is not None and again.cut.work == item.cut.work
    assert again.cut.at > item.cut.at and again.title == TEXT["title"]
    info = json.loads(note.read_text())
    assert info["again"] and info["used"] == 2 and info["replaced"] > 0.03

    # He chose the one photograph over the scan: nothing to make it of.
    info["single"] = info["again"]
    note.write_text(json.dumps(info))
    assert works.scan_of(item) is None


def test_the_work_is_looked_for_once_in_a_scan(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    """With no corners from the phone the merge asks Opus for them, and
    the phone's own asking after it costs nothing more."""
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(CORNERS))[1]
    first = _jpeg(photo())
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", first)}).json()["token"]
        client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.jpg", first)})
        merged = client.post(f"/api/own/photos/{token}/merge").json()
        assert merged["corners"] is not None and merged["shape"] == "rectangle"
        found = client.post(f"/api/own/photos/{token}/find").json()
        assert found["corners"] == merged["corners"]
        assert len(fake.asked) == 1


def test_the_white_balance_he_sets_is_the_works_and_stays_when_it_is_scanned_again(
    service: FrameService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mateusz 2026-11-17 16:27 UTC: "Gdy przy robieniu zdjęcia dzieła nie
    zostanie wykryta karta koloru dodaj suwak regulacji balansu bieli".
    His works hang under warm lamps (a white wall with 3.3 times the red
    of its blue). What the slider says goes with the cut: the work's
    photograph is kept in that balance, whole and cut, and a scan made
    again after an update has the same."""
    import json

    from frame_server.imaging import balance
    from frame_server.own_works import SCAN_INFO, OwnWorks

    # A grey stays as light as it was; warmer is more red and less blue.
    for at in (-1.0, -0.4, 0.3, 1.0):
        red, green, blue = balance.gains(at)
        assert abs(0.2126 * red + 0.7152 * green + 0.0722 * blue - 1) < 1e-6
        assert (red > green > blue) == (at > 0)
    assert balance.gains(0) == (1.0, 1.0, 1.0) and balance.gains(5) == balance.gains(1)
    plain = photo()
    assert balance.apply(plain, 0) is plain

    def warmth(path: Path) -> float:
        with Image.open(path) as img:
            got = np.asarray(img.convert("RGB")).astype(float)
        return float(got[..., 0].mean() / got[..., 2].mean())

    # The photograph as a lamp makes it: what -0.6 takes back.
    table: list[int] = []
    for gain in balance.gains(-0.6):
        table += [
            round(255 * balance._coded(min(1.0, balance._linear(level / 255) / gain)))
            for level in range(256)
        ]
    under_lamp = plain.point(table)
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(under_lamp))}).json()[
            "token"
        ]
        lit = warmth(service.own_works.path(token))
        too_far = client.post(
            "/api/own/works", json={"token": token, "text": TEXT, "balance": -1.5}
        )
        assert too_far.status_code == 422
        added = client.post("/api/own/works", json={"token": token, "text": TEXT, "balance": -0.6})
        assert added.status_code == 200, added.text
    item = service.library.get(added.json()["id"])
    assert item is not None
    with Image.open(service.images.museum_photo(item, urgent=True)) as img:
        got = np.asarray(img.convert("RGB").reduce(8)).astype(int)
    # The photograph as it was before the lamp (but for the JPEG's grain).
    assert float(np.abs(got - np.asarray(plain.reduce(8)).astype(int)).mean()) < 2
    assert warmth(service.images.museum_photo(item, urgent=True)) < 0.8 * lit

    # A scan: the balance is noted beside its photographs…
    monkeypatch.setattr(OwnWorks, "_merge", staticmethod(lambda *_: (2, 0.01, False)))
    seen = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    with _client(service) as client:
        token = client.post("/api/own/photos", files={"file": ("p.jpg", _jpeg(under_lamp))}).json()[
            "token"
        ]
        for _ in range(2):
            client.post(
                f"/api/own/photos/{token}/sides", files={"file": ("s.jpg", _jpeg(under_lamp))}
            )
        client.post(f"/api/own/photos/{token}/merge", json={"outline": seen})
        scanned = client.post(
            "/api/own/works",
            json={"token": token, "corners": seen, "by": "owner", "text": TEXT, "balance": -0.6},
        )
        assert scanned.status_code == 200, scanned.text
    work = service.library.get(scanned.json()["id"])
    assert work is not None
    assert json.loads((service.own_works.scans / token / SCAN_INFO).read_text())["balance"] == -0.6
    cool = warmth(service.images.museum_photo(work, urgent=True))
    assert cool < 0.8 * lit
    # …and made again of them, the work is as cool as he set it.
    again = service.own_works.rescan(work)
    assert abs(warmth(service.images.museum_photo(again, urgent=True)) - cool) < 0.02


def test_he_chooses_between_the_scan_and_the_one_photograph_of_a_relief(
    service: FrameService, caplog: pytest.LogCaptureFixture
) -> None:
    """Mateusz 2026-11-17 22:43 UTC: "wybór pomiędzy obrazem składanym
    (inteligentnym) a z pojedynczego zdjęcia - zawsze go dawaj, a w
    sytuacji gdzie podejrzewasz płaskorzeźbę albo dzieło które wymaga
    pojedynczego zdjęcia ustawiaj je jako domyślne". Three photographs
    that show no one flat work were left as the first one, with nothing
    to choose; now the scan is made of them all the same, and the answer
    says the one photograph is the one proposed. What he then goes on
    with is what the work is made of again after an update."""
    import json

    from test_reflections import CORNERS, _relief, _three

    from frame_server.own_works import SCAN_INFO

    first, sides = _relief()

    def png(img: np.ndarray) -> bytes:
        out = io.BytesIO()
        Image.fromarray(img).save(out, "PNG")
        return out.getvalue()

    def shown(path: Path) -> np.ndarray:
        with Image.open(path) as img:
            return np.asarray(img.convert("RGB")).astype(int)

    def scan(
        first_: np.ndarray, sides_: list[np.ndarray], client: TestClient, choice: bool = True
    ) -> tuple[str, dict[str, Any]]:
        token = client.post("/api/own/photos", files={"file": ("p.png", png(first_))}).json()[
            "token"
        ]
        for side in sides_:
            client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(side))})
        merged = client.post(
            f"/api/own/photos/{token}/merge", json={"corners": CORNERS, "choice": choice}
        )
        assert merged.status_code == 200, merged.text
        return token, merged.json()

    works = service.own_works
    with _client(service) as client, caplog.at_level("INFO", logger="frame_server.own_works"):
        token, merged = scan(first, sides, client)
        assert merged["used"] == 2 and merged["doubt"] and merged["replaced"] > 0
        # What the scan's time went on is in his log (2026-11-18 23:34 UTC:
        # "teraz trwa to zdecydowanie za długo").
        told = [r.getMessage() for r in caplog.records if "merged in" in r.getMessage()]
        assert len(told) == 1 and token in told[0]
        assert all(part in told[0] for part in ("core(s)", "read", "laid", "whole", "written"))
        info = json.loads((works.scans / token / SCAN_INFO).read_text())
        assert info["doubt"] is True
        # The scan waits in the photograph's place, the first one beside it.
        took = shown(works.scans / token / "first.jpg")
        made = shown(works.path(token))
        assert np.abs(made - took).mean() > 0.5

        # The one photograph, as proposed: back in its place, and no scan's.
        assert client.post(f"/api/own/photos/{token}/single").status_code == 200
        assert np.abs(shown(works.path(token)) - took).mean() < 0.01
        one = client.post("/api/own/works", json={"token": token, "corners": CORNERS, "text": TEXT})
        assert one.status_code == 200, one.text
        assert works.scan_of(service.library.get(one.json()["id"])) is None

        # The scan, his choice against what was proposed: made so again.
        token, merged = scan(first, sides, client)
        assert merged["doubt"]
        kept = client.post(
            "/api/own/works", json={"token": token, "corners": CORNERS, "text": TEXT}
        )
        assert kept.status_code == 200, kept.text
        item = service.library.get(kept.json()["id"])
        assert item is not None and works.scan_of(item) == token
        works.rescan(item)
        info = json.loads((works.scans / token / SCAN_INFO).read_text())
        assert info["replaced"] > 0 and info["doubt"] is True

        # A relief scanned before he was given the choice noted no doubt
        # and was left the one photograph: so it stays.
        del info["doubt"]
        (works.scans / token / SCAN_INFO).write_text(json.dumps(info))
        works.rescan(item)
        assert json.loads((works.scans / token / SCAN_INFO).read_text())["replaced"] == 0

        # An app from before the choice shows the scan alone where
        # anything was taken off: a relief comes to it untouched.
        token, old = scan(first, sides, client, choice=False)
        assert old["used"] == 2 and old["replaced"] == 0 and old["doubt"]
        assert json.loads((works.scans / token / SCAN_INFO).read_text())["doubt"] is False
        assert np.abs(shown(works.path(token)) - took).mean() < 0.01

        # A flat work behind glass: in no doubt, the scan as it was.
        _, glass, beside = _three()
        _, plain = scan(glass, beside, client)
        assert plain["used"] == 2 and not plain["doubt"] and plain["replaced"] > 0.03


def test_the_lens_bend_is_taken_out_of_the_work_he_adds(service: FrameService) -> None:
    """Mateusz 2026-11-18 22:28 UTC, his still life in its frame, the
    frame's straight sides bowed outward: "Zakrzywienie obiektywu iPhone?
    Jakieś możliwości prostowania czy to bardzo skomplikowane?". The
    photograph waits as it was taken (the corners are set on the phone's
    own copy of it); the work added from it is kept without the bend of
    the lens its photograph names, where that lens was measured, and the
    corners and the frame's edge go to where the work is then."""
    import json

    import test_lens as lens_

    from frame_server.own_works import FOUND, LENS, SCAN_INFO, Incoming

    x0, y0, x1, y1 = lens_.FRAME
    frame = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    work = [(x0 + 40, y0 + 40), (x1 - 40, y0 + 40), (x1 - 40, y1 - 40), (x0 + 40, y1 - 40)]

    def drawn(corners: list[tuple[int, int]]) -> list[tuple[float, float]]:
        """Where the lens drew the scene's ``corners``, 0–1."""
        half = float(np.hypot(lens_.W, lens_.H)) / 2
        out = []
        for x, y in corners:
            ux, uy = (x - lens_.W / 2) / half, (y - lens_.H / 2) / half
            f = 1 + lens_.K1 * (ux * ux + uy * uy)
            out.append(
                (
                    round((ux * f * half + lens_.W / 2) / lens_.W, 5),
                    round((uy * f * half + lens_.H / 2) / lens_.H, 5),
                )
            )
        return out

    def near(got: list[tuple[float, float]] | None, true: list[tuple[int, int]]) -> float:
        assert got is not None
        return max(
            max(abs(gx * lens_.W - x), abs(gy * lens_.H - y))
            for (gx, gy), (x, y) in zip(got, true, strict=True)
        )

    def bow(path: Path) -> float:
        with Image.open(path) as img:
            return lens_.bow(np.asarray(img.convert("RGB")))

    taken = lens_.bent(lens_.scene())
    works = service.own_works

    def add(data: bytes, client: TestClient) -> tuple[str, Any]:
        sent = client.post("/api/own/photos", files={"file": ("p.jpg", data)})
        assert sent.status_code == 200, sent.text
        token = sent.json()["token"]
        waiting = works.path(token)
        # As taken while it waits; Opus's frame beside it.
        assert bow(waiting) > 2
        seen = Incoming(
            token=token,
            width=lens_.W,
            height=lens_.H,
            corners=drawn(work),
            surround=drawn(frame),
            surround_kind="frame",
            looked=True,
        )
        waiting.with_suffix(FOUND).write_text(seen.model_dump_json())
        added = client.post(
            "/api/own/works",
            json={"token": token, "corners": drawn(work), "by": "owner", "text": TEXT},
        )
        assert added.status_code == 200, added.text
        assert not waiting.with_suffix(LENS).exists()
        item = service.library.get(added.json()["id"])
        assert item is not None and item.cut is not None
        return token, item

    with _client(service) as client:
        # His phone's main camera: straightened, the corners with it.
        _, item = add(lens_.photograph(img=taken), client)
        assert bow(service.images.museum_photo(item, urgent=True)) < 0.5
        assert near(item.cut.work, work) < 0.6 and near(item.cut.surround, frame) < 0.6
        assert item.cut.framed_kind == "frame"

        # A photograph that names no camera, and another phone's: as taken.
        for data in (
            lens_.photograph(model=None, img=taken),
            lens_.photograph(model="iPhone 16 Pro Max", img=taken),
        ):
            _, plain = add(data, client)
            assert bow(service.images.museum_photo(plain, urgent=True)) > 2
            assert near(plain.cut.work, work) > 2
            assert plain.cut.work == [tuple(c) for c in drawn(work)]

        # A scan notes what took it and what was taken out of its work.
        token = client.post(
            "/api/own/photos", files={"file": ("p.jpg", lens_.photograph(img=taken))}
        ).json()["token"]
        for _ in range(2):
            client.post(
                f"/api/own/photos/{token}/sides",
                files={"file": ("s.jpg", _jpeg(Image.fromarray(taken)))},
            )
        client.post(f"/api/own/photos/{token}/merge", json={"corners": drawn(work)})
        assert bow(works.path(token)) > 2 and bow(works.scans / token / "first.jpg") > 2
        scanned = client.post(
            "/api/own/works", json={"token": token, "corners": drawn(work), "text": TEXT}
        )
        assert scanned.status_code == 200, scanned.text
        info = json.loads((works.scans / token / SCAN_INFO).read_text())
        assert info["lens"]["model"] == lens_.PHONE and info["lens"]["main"]
        assert info["straight"] == lens_.K1
        made = service.library.get(scanned.json()["id"])
        assert made is not None and made.cut is not None
        assert bow(service.images.museum_photo(made, urgent=True)) < 0.5
        assert near(made.cut.work, work) < 0.6
        # Nothing to do after a start; made again, straight as it was.
        assert works.scanned_again() == 0
        again = works.rescan(made)
        assert bow(service.images.museum_photo(again, urgent=True)) < 0.5
        assert again.cut is not None and again.cut.work == made.cut.work


def test_the_cameras_own_table_straightens_the_work_where_it_says_what_was_measured(
    service: FrameService, caplog: pytest.LogCaptureFixture
) -> None:
    """Mateusz 2026-11-19 08:09 UTC: "Korekta obiektywu - a nie ma
    natywnego rozwiązania od Apple w tym zakresie?". The camera gives
    with a photograph the table it would be straightened by, of that very
    photograph; the app sends it with a scan's first one. It is noted,
    and the work is straightened by it where it says of his lens what the
    measurement says. A table that says otherwise is not gone by (the
    measurement is); nor is one of a lens that was not measured, yet."""
    import json
    import logging

    import test_lens as lens_

    from frame_server.own_works import SCAN_INFO

    x0, y0, x1, y1 = lens_.FRAME
    work = [(x0 + 40, y0 + 40), (x1 - 40, y0 + 40), (x1 - 40, y1 - 40), (x0 + 40, y1 - 40)]
    # This photograph's lens, a little other than the few measured: its
    # table says so, the measured number would leave a twelfth of the bow.
    k1 = lens_.K1 * 1.12
    taken = lens_.bent(lens_.scene(), k1)
    own = {"table": lens_.table(k1), "centre": [0.5, 0.5]}
    works = service.own_works

    def drawn(corners: list[tuple[int, int]]) -> list[tuple[float, float]]:
        half = float(np.hypot(lens_.W, lens_.H)) / 2
        out = []
        for x, y in corners:
            ux, uy = (x - lens_.W / 2) / half, (y - lens_.H / 2) / half
            f = 1 + k1 * (ux * ux + uy * uy)
            out.append(
                (
                    round((ux * f * half + lens_.W / 2) / lens_.W, 5),
                    round((uy * f * half + lens_.H / 2) / lens_.H, 5),
                )
            )
        return out

    def scanned(
        client: TestClient, camera: dict[str, object] | None, model: str = lens_.PHONE
    ) -> tuple[Any, dict[str, Any], float]:
        data = {"lens": json.dumps(camera)} if camera is not None else None
        sent = client.post(
            "/api/own/photos",
            files={"file": ("p.jpg", lens_.photograph(model=model, img=taken))},
            data=data,
        )
        assert sent.status_code == 200, sent.text
        token = sent.json()["token"]
        for _ in range(2):
            client.post(
                f"/api/own/photos/{token}/sides",
                files={"file": ("s.jpg", _jpeg(Image.fromarray(taken)))},
            )
        client.post(f"/api/own/photos/{token}/merge", json={"corners": drawn(work)})
        added = client.post(
            "/api/own/works", json={"token": token, "corners": drawn(work), "text": TEXT}
        )
        assert added.status_code == 200, added.text
        item = service.library.get(added.json()["id"])
        assert item is not None and item.cut is not None
        info = json.loads((works.scans / token / SCAN_INFO).read_text())
        with Image.open(service.images.museum_photo(item, urgent=True)) as img:
            return item, info, lens_.bow(np.asarray(img.convert("RGB")))

    def near(got: list[tuple[float, float]] | None) -> float:
        assert got is not None
        return max(
            max(abs(gx * lens_.W - x), abs(gy * lens_.H - y))
            for (gx, gy), (x, y) in zip(got, work, strict=True)
        )

    with _client(service) as client, caplog.at_level(logging.INFO, "frame_server.own_works"):
        # Without the table: the measured number, and a little of the bow left.
        item, info, left = scanned(client, None)
        assert info["straight"] == lens_.K1 and "table" not in info["lens"]
        assert 0.2 < left < 1.0

        # With it: by the table, noted with the scan, and straight.
        item, info, bowed = scanned(client, own)
        assert info["lens"]["table"] == pytest.approx(own["table"])
        assert info["straight"]["table"] == pytest.approx(own["table"])
        assert info["straight"]["centre"] == [0.5, 0.5]
        assert bowed < 0.3 and bowed < left / 2
        assert near(item.cut.work) < 0.6
        assert any("by the camera's own table" in r.getMessage() for r in caplog.records)
        # Made again, it is straightened by what its corners were moved by.
        again = works.rescan(item)
        assert again.cut is not None and again.cut.work == item.cut.work
        with Image.open(service.images.museum_photo(again, urgent=True)) as img:
            assert lens_.bow(np.asarray(img.convert("RGB"))) < 0.3

        # A table that says the lens bends the other way, or twice as
        # much: one of the two is not what it is taken for, and the
        # measurement made his frames straight.
        caplog.clear()
        for other in (lens_.table(-k1), lens_.table(2 * k1)):
            _, info, bowed = scanned(client, {"table": other, "centre": [0.5, 0.5]})
            assert info["straight"] == lens_.K1 and info["lens"]["table"] == pytest.approx(other)
            assert bowed == pytest.approx(left, abs=0.05)
        assert sum("not what was measured" in r.getMessage() for r in caplog.records) == 2

        # What is no table is left out, and the photograph taken all the same.
        for none in ({"table": [0.0, 0.5], "centre": [0.5, 0.5]}, {"table": "x"}, []):
            _, info, bowed = scanned(client, none)  # type: ignore[arg-type]
            assert info["straight"] == lens_.K1 and "table" not in info["lens"]

        # Another phone, its lens not measured: noted, and as taken for now.
        caplog.clear()
        _, info, bowed = scanned(client, own, model="iPhone 16 Pro Max")
        assert "straight" not in info and info["lens"]["table"] == pytest.approx(own["table"])
        assert bowed > 2
        assert any("of a lens not measured" in r.getMessage() for r in caplog.records)


def test_the_phone_takes_the_lens_bend_out_of_its_scan_and_the_server_not_again(
    service: FrameService, caplog: pytest.LogCaptureFixture
) -> None:
    """Mateusz 2026-11-19 09:52 UTC: "Część 2 - prostowanie obiektywu. Czy
    tego także nie lepiej robić na iPhone? Inaczej będziemy niepotrzebnie
    przesyłać materiały na serwer i z powrotem, a telefon i tak pewnie
    zrobi to szybciej." The server tells the phone what the lens's bend
    is; the phone takes it out of the scan it makes and says what by.
    The scan then waits straightened and the work is added from it as it
    came ("Dodaj" was seconds at straightening 48 MP here), its corners,
    said as on the photograph taken, going to where the work is. What the
    server makes of the kept photographs itself it straightens itself."""
    import json
    import logging

    import test_lens as lens_

    from frame_server.imaging import lens
    from frame_server.own_works import MERGING, SCAN_INFO, STRAIGHT, LensBend

    x0, y0, x1, y1 = lens_.FRAME
    work = [(x0 + 40, y0 + 40), (x1 - 40, y0 + 40), (x1 - 40, y1 - 40), (x0 + 40, y1 - 40)]
    true = [(x / lens_.W, y / lens_.H) for x, y in work]
    k1 = lens_.K1 * 1.12
    taken = lens_.bent(lens_.scene(), k1)
    own = {"table": lens_.table(k1), "centre": [0.5, 0.5]}
    works = service.own_works

    def bow(path: Path) -> float:
        with Image.open(path) as img:
            return lens_.bow(np.asarray(img.convert("RGB")))

    def near(got: list[tuple[float, float]] | None) -> float:
        assert got is not None
        return max(
            max(abs(gx * lens_.W - x), abs(gy * lens_.H - y))
            for (gx, gy), (x, y) in zip(got, work, strict=True)
        )

    def sent(
        client: TestClient, camera: dict[str, object] | None, model: str = lens_.PHONE
    ) -> tuple[str, Any]:
        """A scan's photographs with the server, and what it says the
        phone is to straighten by."""
        first = client.post(
            "/api/own/photos",
            files={"file": ("p.jpg", lens_.photograph(model=model, img=taken))},
            data={"lens": json.dumps(camera)} if camera is not None else None,
        )
        assert first.status_code == 200, first.text
        token = first.json()["token"]
        for _ in range(2):
            client.post(
                f"/api/own/photos/{token}/sides",
                files={"file": ("s.jpg", _jpeg(Image.fromarray(taken)))},
            )
        return token, first.json()["straight"]

    def scan(told: object, corners: list[tuple[float, float]], **more: object) -> dict[str, str]:
        # As the app of now says it: merged as the server merges.
        note = {
            "corners": corners,
            "used": 2,
            "replaced": 0.05,
            "straight": told,
            "merging": MERGING,
            **more,
        }
        return {"note": json.dumps(note)}

    with _client(service) as client, caplog.at_level(logging.INFO, "frame_server.own_works"):
        for camera in (None, own):
            token, told = sent(client, camera)
            # By the measured number without the camera's table, by the
            # table with it.
            assert (told["table"] == []) == (camera is None)
            assert told["k1"] == (lens_.K1 if camera is None else 0.0)
            bend = LensBend.model_validate(told).bend()
            assert bend is not None
            # The phone: he sets the corners on its photograph
            # straightened, it says them as on the one taken; the scan it
            # made (here the photograph itself) it straightens.
            corners = lens.bent(true, lens_.W, lens_.H, bend)
            picture = _jpeg(Image.fromarray(lens.straight(taken, bend)))
            url = f"/api/own/photos/{token}/merged"

            # Straightened by what is not this lens's bend here, or with
            # no picture of it: no scan of this photograph.
            other = {"k1": lens_.K1 * 2, "table": [], "centre": [0.5, 0.5]}
            refused = client.post(
                url, files={"file": ("m.jpg", picture)}, data=scan(other, corners)
            )
            assert refused.status_code == 422, refused.text
            assert client.post(url, data=scan(told, corners, replaced=0)).status_code == 422
            assert not works.path(token).with_suffix(STRAIGHT).exists()

            kept = client.post(url, files={"file": ("m.jpg", picture)}, data=scan(told, corners))
            assert kept.status_code == 200, kept.text
            waiting = works.path(token)
            # The phone's own file waits, straight; the photographs kept
            # are as taken.
            assert waiting.read_bytes() == picture and bow(waiting) < (0.5 if camera else 1.0)
            assert bow(works.scans / token / "first.jpg") > 2
            assert waiting.with_suffix(STRAIGHT).exists()
            assert any("and straightened there" in r.getMessage() for r in caplog.records)

            added = client.post(
                "/api/own/works",
                json={"token": token, "corners": corners, "by": "owner", "text": TEXT},
            )
            assert added.status_code == 200, added.text
            assert not waiting.with_suffix(STRAIGHT).exists()
            item = service.library.get(added.json()["id"])
            assert item is not None and item.cut is not None
            # Not straightened once more (it would bow the other way),
            # and the corners where the work is.
            kept_at = service.images.museum_photo(item, urgent=True)
            assert bow(kept_at) < (0.5 if camera else 1.0)
            assert near(item.cut.work) < 0.6
            info = json.loads((works.scans / token / SCAN_INFO).read_text())
            assert info["straight"] == bend.to_json()
            # Made again of the photographs kept: straightened here, by
            # the same, the corners left where they are.
            assert works.scanned_again() == 0
            again = works.rescan(item)
            assert again.cut is not None and again.cut.work == item.cut.work
            assert bow(service.images.museum_photo(again, urgent=True)) < (0.5 if camera else 1.0)

        # "Na wprost" after such a scan: the first photograph back as it
        # was taken, and the work straightened here as it is added.
        token, told = sent(client, own)
        bend = LensBend.model_validate(told).bend()
        assert bend is not None
        corners = lens.bent(true, lens_.W, lens_.H, bend)
        picture = _jpeg(Image.fromarray(lens.straight(taken, bend)))
        url = f"/api/own/photos/{token}/merged"
        assert (
            client.post(
                url, files={"file": ("m.jpg", picture)}, data=scan(told, corners)
            ).status_code
            == 200
        )
        assert client.post(f"/api/own/photos/{token}/single").json() == {"single": True}
        waiting = works.path(token)
        assert bow(waiting) > 2 and not waiting.with_suffix(STRAIGHT).exists()
        added = client.post(
            "/api/own/works", json={"token": token, "corners": corners, "by": "owner", "text": TEXT}
        )
        assert added.status_code == 200, added.text
        item = service.library.get(added.json()["id"])
        assert item is not None and item.cut is not None
        assert bow(service.images.museum_photo(item, urgent=True)) < 0.5
        assert near(item.cut.work) < 0.6

        # A scan the phone sends as taken after one it straightened (an
        # older app's, or his corners set wider) waits as taken again.
        token, told = sent(client, None)
        bend = LensBend.model_validate(told).bend()
        assert bend is not None
        corners = lens.bent(true, lens_.W, lens_.H, bend)
        url = f"/api/own/photos/{token}/merged"
        picture = _jpeg(Image.fromarray(lens.straight(taken, bend)))
        client.post(url, files={"file": ("m.jpg", picture)}, data=scan(told, corners))
        assert works.path(token).with_suffix(STRAIGHT).exists()
        plain = {"note": json.dumps({"corners": corners, "used": 2, "replaced": 0.05})}
        as_taken = _jpeg(Image.fromarray(taken))
        assert client.post(url, files={"file": ("m.jpg", as_taken)}, data=plain).status_code == 200
        assert not works.path(token).with_suffix(STRAIGHT).exists()
        added = client.post(
            "/api/own/works", json={"token": token, "corners": corners, "by": "owner", "text": TEXT}
        )
        item = service.library.get(added.json()["id"])
        assert item is not None and item.cut is not None
        assert bow(service.images.museum_photo(item, urgent=True)) < 1.0
        assert near(item.cut.work) < 0.6

        # A lens that was not measured: the phone is told of no bend, and
        # a scan it says it straightened is none of this photograph.
        token, told = sent(client, own, model="iPhone 16 Pro Max")
        assert told is None
        url = f"/api/own/photos/{token}/merged"
        said = LensBend.of(bend)
        assert said is not None
        refused = client.post(
            url, files={"file": ("m.jpg", picture)}, data=scan(said.model_dump(), corners)
        )
        assert refused.status_code == 422, refused.text
        # The work found in it says the same as the photograph did.
        works.crops.home_corners = lambda img: None  # type: ignore[method-assign]
        assert client.post(f"/api/own/photos/{token}/find").json()["straight"] is None
        token, told = sent(client, None)
        assert client.post(f"/api/own/photos/{token}/find").json()["straight"] == told


def test_his_earlier_scans_are_set_straight_by_themselves(
    service: FrameService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Told (2026-11-18) that his scans of the last two weeks would be
    set straight by themselves: after a start, a work whose kept scan was
    taken by the app's camera before a scan noted its lens is made of its
    photographs once more without the bend, its cut moved to where the
    work is then, once. The one photograph he chose over a scan as well;
    never from a scan the work was photographed again since."""
    import json

    import test_lens as lens_

    from frame_server import own_works
    from frame_server.own_works import SCAN_INFO, OwnWorks

    x0, y0, x1, y1 = lens_.FRAME
    work = [(x0 + 40, y0 + 40), (x1 - 40, y0 + 40), (x1 - 40, y1 - 40), (x0 + 40, y1 - 40)]
    half = float(np.hypot(lens_.W, lens_.H)) / 2

    def drawn(corners: list[tuple[int, int]]) -> list[tuple[float, float]]:
        out = []
        for x, y in corners:
            ux, uy = (x - lens_.W / 2) / half, (y - lens_.H / 2) / half
            f = 1 + lens_.K1 * (ux * ux + uy * uy)
            out.append(
                (
                    round((ux * f * half + lens_.W / 2) / lens_.W, 5),
                    round((uy * f * half + lens_.H / 2) / lens_.H, 5),
                )
            )
        return out

    def near(got: list[tuple[float, float]] | None) -> float:
        assert got is not None
        return max(
            max(abs(gx * lens_.W - x), abs(gy * lens_.H - y))
            for (gx, gy), (x, y) in zip(got, work, strict=True)
        )

    def bow(path: Path) -> float:
        with Image.open(path) as img:
            return lens_.bow(np.asarray(img.convert("RGB")))

    taken = _jpeg(Image.fromarray(lens_.bent(lens_.scene())))
    works = service.own_works
    # Nothing in the glass: the scan is the first photograph.
    monkeypatch.setattr(OwnWorks, "_merge", staticmethod(lambda *_: (2, 0.01, False)))

    def scan(client: TestClient, single: bool = False) -> tuple[str, str]:
        """A work scanned by a release before this one: its scan notes
        nothing of the lens."""
        token = client.post("/api/own/photos", files={"file": ("p.jpg", taken)}).json()["token"]
        for _ in range(2):
            client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.jpg", taken)})
        client.post(f"/api/own/photos/{token}/merge", json={"corners": drawn(work)})
        if single:
            assert client.post(f"/api/own/photos/{token}/single").status_code == 200
        added = client.post(
            "/api/own/works",
            json={"token": token, "corners": drawn(work), "by": "owner", "text": TEXT},
        )
        assert added.status_code == 200, added.text
        note = works.scans / token / SCAN_INFO
        info = json.loads(note.read_text())
        assert info["lens"] is None and "straight" not in info
        del info["lens"]
        note.write_text(json.dumps(info))
        return token, added.json()["id"]

    def photo_of(item_id: str) -> Path:
        item = service.library.get(item_id)
        assert item is not None
        return service.images.museum_photo(item, urgent=True)

    with _client(service) as client:
        token, first = scan(client)
        _, chosen = scan(client, single=True)
        # Photographed again since by one photograph, of which no scan is kept.
        old, retaken = scan(client)
        blocks = np.random.default_rng(9).integers(30, 220, (16, 12, 3), dtype=np.uint8)
        other = _jpeg(Image.fromarray(blocks).resize((lens_.W, lens_.H), Image.Resampling.BICUBIC))
        sent = client.post("/api/own/photos", files={"file": ("p.jpg", other)}).json()
        again = client.put(
            f"/api/own/works/{retaken}/photo",
            json={"token": sent["token"], "corners": drawn(work), "by": "owner"},
        )
        assert again.status_code == 200, again.text
    for item_id in (first, chosen):
        assert bow(photo_of(item_id)) > 2
    his = photo_of(retaken).read_bytes()
    before = service.library.get(first)
    assert before is not None and before.cut is not None and near(before.cut.work) > 2

    assert works.scanned_again() == 2
    for item_id in (first, chosen):
        made = service.library.get(item_id)
        assert made is not None and made.cut is not None
        assert bow(photo_of(item_id)) < 0.5
        assert near(made.cut.work) < 0.6 and made.cut.by == "owner"
        assert made.title == TEXT["title"]
    after = service.library.get(first)
    # Stamped anew (to the second: the same one on a quick machine).
    assert after is not None and after.cut is not None and after.cut.at >= before.cut.at
    info = json.loads((works.scans / token / SCAN_INFO).read_text())
    assert info["straight"] == lens_.K1 and info["again"]
    # The one he photographed again is that photograph still, its cut too.
    assert photo_of(retaken).read_bytes() == his
    assert "straight" not in json.loads((works.scans / old / SCAN_INFO).read_text())
    kept = service.library.get(retaken)
    assert kept is not None and kept.cut is not None
    assert kept.cut.work == [tuple(c) for c in drawn(work)]

    # Once: nothing after the next start, and made again after a later
    # update the corners stay where they are.
    assert works.scanned_again() == 0
    monkeypatch.setattr(own_works, "MERGING", own_works.MERGING + 1)
    assert works.scanned_again() == 1  # the one photograph is not merged
    later = service.library.get(first)
    assert later is not None and later.cut is not None
    assert later.cut.work == after.cut.work and bow(photo_of(first)) < 0.5

    # A scan that is no photograph of the sensor's whole (cut, or from
    # elsewhere) and one that named a lens not measured: as they are.
    measured = lens_.lens.Bend(k1=lens_.K1)
    assert OwnWorks._bend({"width": 6048, "height": 8064}) == measured
    assert OwnWorks._bend({"width": 8064, "height": 6048}) == measured
    assert OwnWorks._bend({"width": 1100, "height": 1400}) is None
    assert OwnWorks._bend({}) is None
    assert OwnWorks._bend({"lens": None, "width": 6048, "height": 8064}) is None
    named = {"model": "iPhone 16 Pro Max", "main": True}
    assert OwnWorks._bend({"lens": named, "width": 6048, "height": 8064}) is None
    assert OwnWorks._bend({"lens": {"model": lens_.PHONE, "main": False}}) is None
    assert OwnWorks._bend({"lens": {"model": lens_.PHONE, "main": True}}) == measured
