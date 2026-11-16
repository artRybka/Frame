"""Works of the owner's own ("Dodaj własne dzieło", Mateusz 2026-11-15):
the photograph sent, the work found in it by Opus and cut out of its frame,
hints read off it, the work added with what he wrote, described again,
photographed again, corrected and deleted."""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import cv2
import numpy as np
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
        assert (
            client.post(
                f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(first))}
            ).status_code
            == 422
        )
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
