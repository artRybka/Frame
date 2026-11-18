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
    service: FrameService,
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
    with _client(service) as client:
        token, merged = scan(first, sides, client)
        assert merged["used"] == 2 and merged["doubt"] and merged["replaced"] > 0
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
