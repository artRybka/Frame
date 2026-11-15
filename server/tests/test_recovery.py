"""The card's colour recovery preview: the varnish sum with its proposed
strength, a yellowed sheet de-yellowed, and what the card is told
(Mateusz 2026-11-15: „Zbudować bez modelu”)."""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.imaging import recovery
from frame_server.imaging.color import linear_to_oklab, linear_to_u8, u8_to_linear
from frame_server.library.models import Item

ALPHA = np.asarray(recovery.ALPHA, dtype=np.float32)


def _painting() -> np.ndarray:
    """A picture in linear light: a sky, flesh, a dark ground and a patch
    of white linen, with a little grain."""
    rng = np.random.default_rng(7)
    lin = np.empty((120, 160, 3), np.float32)
    lin[:60] = (0.30, 0.42, 0.62)
    lin[60:] = (0.10, 0.07, 0.05)
    lin[40:90, 30:70] = (0.62, 0.42, 0.33)
    lin[50:80, 95:140] = (0.80, 0.80, 0.80)
    return np.clip(lin * rng.uniform(0.93, 1.0, lin.shape[:2])[..., None], 0, 1).astype(np.float32)


def _under_varnish(lin: np.ndarray, d: float) -> Image.Image:
    return Image.fromarray(linear_to_u8(lin * np.exp(-d * ALPHA)))


def _chroma(rgb: np.ndarray) -> float:
    lab = linear_to_oklab(u8_to_linear(rgb.reshape(-1, 3))).mean(0)
    return float(np.hypot(lab[1], lab[2]))


def test_the_white_under_a_varnish_tells_how_thick_it_is() -> None:
    for d in (0.4, 0.8, 1.2):
        found = recovery.read_varnish(_under_varnish(_painting(), d))
        assert found.white == pytest.approx(d, abs=0.08)
        assert len(found.tops) == len(recovery.STEPS)
        assert list(found.tops) == sorted(found.tops)  # lighter with every step


def test_taking_the_varnish_off_gives_the_white_back() -> None:
    varnished = u8_to_linear(np.asarray(_under_varnish(_painting(), 0.8)))
    linen = (slice(55, 75), slice(100, 135))
    assert _chroma(linear_to_u8(varnished[linen])) > 0.05  # yellow now
    clean = recovery.unvarnish(varnished, 0.8)
    assert _chroma(linear_to_u8(clean[linen])) < 0.01
    assert float(clean.max()) <= 1.0
    # Nothing of the sky's blue was lost to the range.
    sky = clean[10:30, 10:150].mean((0, 1))
    assert sky[2] > sky[1] > sky[0]


def test_the_phone_sum_is_the_servers() -> None:
    picture = _under_varnish(_painting(), 0.9)
    found = recovery.read_varnish(picture)
    lin = u8_to_linear(np.asarray(picture))
    for strength in (0.0, 0.35, 0.7, 1.6):
        top = float(np.interp(strength, recovery.STEPS, found.tops))
        phone = np.clip(lin * np.asarray(recovery.gains(strength, top), np.float32), 0, 1)
        ours = recovery.unvarnish(lin, strength)
        assert np.abs(linear_to_u8(phone).astype(int) - linear_to_u8(ours).astype(int)).max() <= 3


def test_the_proposal_is_what_conservations_took_moved_by_the_white() -> None:
    assert recovery.propose(None) == 0.69  # no white to go by: the typical strength
    assert recovery.propose(0.78) == 0.69
    assert recovery.propose(1.6) == pytest.approx(0.89, abs=0.01)
    assert recovery.propose(0.4) < recovery.propose(0.8) < recovery.propose(1.2)
    # A white that is white already: little to take, and never nothing.
    assert recovery.propose(0.0) == recovery.LEAST
    assert recovery.LEAST <= recovery.propose(0.15) < recovery.propose(0.3)


def test_a_white_no_varnish_explains_is_not_gone_by() -> None:
    # A picture with no white at all, its lightest thing a green.
    lin = np.empty((80, 80, 3), np.float32)
    lin[:] = (0.05, 0.12, 0.04)
    lin[20:60, 20:60] = (0.30, 0.75, 0.20)
    found = recovery.read_varnish(Image.fromarray(linear_to_u8(lin)))
    assert found.white is None
    assert found.strength == recovery.TYPICAL


def _sheet(paper: tuple[int, int, int], ink_share: float = 0.2) -> Image.Image:
    """A drawing: a sheet darker at its edges, lines of wash, a patch of white
    chalk and a thick black border at the foot."""
    height, width = 300, 240
    yy, xx = np.mgrid[0:height, 0:width]
    edge = 1 - 0.10 * np.clip(np.hypot(yy / height - 0.5, xx / width - 0.5) * 2, 0, 1) ** 2
    rgb = np.asarray(paper, np.float32)[None, None] * edge[..., None]
    lines = (xx % max(int(1 / ink_share), 2) == 0) & (yy > 40) & (yy < 200)
    rgb[lines] *= 0.7  # a wash lets the sheet through
    rgb[220:250, 60:120] = (250, 250, 248)  # white chalk, opaque
    rgb[285:] = (8, 8, 8)
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


YELLOWED = (226, 205, 160)


def test_a_yellowed_sheet_is_known_and_a_toned_one_left_alone() -> None:
    yellowed = recovery.read_sheet(_sheet(YELLOWED))
    assert yellowed.share > 0.5
    assert recovery.sheet_state(yellowed, "pen and brown ink on paper") == "yellowed"
    # The museum says the paper is blue or prepared: by intent.
    assert recovery.sheet_state(yellowed, "black chalk on blue paper") == "toned"
    assert recovery.sheet_state(yellowed, "silverpoint on prepared paper") == "toned"
    assert recovery.sheet_state(yellowed, "kredka na papierze szarym") == "toned"
    # Its colour says so alone.
    blue = recovery.read_sheet(_sheet((150, 170, 200)))
    assert recovery.sheet_state(blue, "chalk on paper") == "toned"
    brown = recovery.read_sheet(_sheet((120, 90, 60)))
    assert recovery.sheet_state(brown) == "toned"
    white = recovery.read_sheet(_sheet((240, 240, 236)))
    assert recovery.sheet_state(white) == "white"


def test_the_colour_of_the_medium_is_not_the_papers() -> None:
    assert not recovery.toned_by_words("pen and brown ink, grey wash, on paper")
    assert not recovery.toned_by_words("watercolour over graphite")
    assert not recovery.toned_by_words("")
    assert recovery.toned_by_words("charcoal on grey-green paper")
    assert recovery.toned_by_words("ink and colour on silk")
    assert recovery.toned_by_words("pastel, papier brązowy")


def test_a_picture_with_no_bare_sheet_is_not_read() -> None:
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
    assert recovery.sheet_state(recovery.read_sheet(Image.fromarray(noise))) == "hidden"


def test_the_sheet_comes_back_and_what_lies_on_it_stays() -> None:
    drawing = _sheet(YELLOWED)
    before = np.asarray(drawing)
    after = np.asarray(recovery.deyellow(drawing))
    assert after.shape == before.shape
    bare = (slice(5, 35), slice(20, 220))
    assert _chroma(before[bare]) > 0.05
    assert _chroma(after[bare]) < 0.022  # a well-kept sheet: cream, not blue-white
    assert after[bare].mean() > before[bare].mean()
    # Even to its edges: the darker rim went with the field.
    middle, rim = (slice(205, 215), slice(130, 200)), (slice(2, 6), slice(2, 40))
    assert float(before[middle].mean()) - float(before[rim].mean()) > 10
    assert abs(float(after[middle].mean()) - float(after[rim].mean())) < 4
    # White chalk and the black border are as they were.
    assert np.abs(after[225:245, 65:115].astype(int) - before[225:245, 65:115]).max() <= 2
    assert np.abs(after[290:].astype(int) - before[290:]).max() <= 2
    # A line of wash lost its yellow with the sheet under it.
    assert _chroma(after[100:110, 0:1]) < _chroma(before[100:110, 0:1])


def test_pastel_keeps_its_colours_where_it_covers_the_sheet() -> None:
    drawing = np.asarray(_sheet(YELLOWED)).copy()
    drawing[100:160, 80:160] = (190, 120, 110)  # a field of pastel, away from the sheet's colour
    picture = Image.fromarray(drawing)
    plain = np.asarray(recovery.deyellow(picture))
    opaque = np.asarray(recovery.deyellow(picture, opaque=True))
    field = (slice(110, 150), slice(90, 150))
    assert np.abs(opaque[field].astype(int) - drawing[field]).max() <= 3
    assert np.abs(plain[field].astype(int) - drawing[field]).max() > 3
    assert _chroma(opaque[5:35, 20:220]) < 0.022  # the bare sheet still comes back


def test_a_large_sheet_is_sent_no_larger_than_the_card_shows() -> None:
    big = _sheet(YELLOWED).resize((2400, 3000))
    assert max(recovery.deyellow(big).size) == recovery.SENT


def _jpeg(picture: Image.Image) -> bytes:
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=95)
    return out.getvalue()


def _keep(svc, picture: Image.Image, **fields) -> Item:
    item = svc.library.upsert(
        Item(
            id=f"met:{fields.pop('number', 1)}",
            source="met",
            source_id="1",
            title="A work",
            image_url="https://images.example/x.jpg",
            thumb_url="https://images.example/t.jpg",
            **fields,
        )
    )
    svc.images.store(item, _jpeg(picture))
    return item


def test_the_card_is_told_what_to_offer(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        oil = _keep(svc, _under_varnish(_painting(), 0.8), number=1, year=1650)
        told = client.get(f"/api/library/items/{oil.id}/recovery", params={"made": "oil"})
        assert told.status_code == 200, told.text
        body = told.json()
        assert body["kind"] == "varnish"
        assert 0.5 <= body["strength"] <= 0.9
        assert body["steps"] == list(recovery.STEPS) and len(body["tops"]) == len(body["steps"])
        assert body["alpha"] == list(recovery.ALPHA) and body["most"] == recovery.D_MAX
        # A painting of our time has no old varnish to take off.
        late = _keep(svc, _under_varnish(_painting(), 0.8), number=2, year=1975)
        told = client.get(f"/api/library/items/{late.id}/recovery", params={"made": "oil"})
        assert told.json()["kind"] == "none"
        # A drawing on a yellowed sheet; the same on paper blue by intent.
        drawing = _keep(svc, _sheet(YELLOWED), number=3, medium="pen and ink on paper")
        told = client.get(f"/api/library/items/{drawing.id}/recovery", params={"made": "paper"})
        assert told.json()["kind"] == "paper"
        toned = _keep(svc, _sheet(YELLOWED), number=4, medium="chalk on blue paper")
        told = client.get(f"/api/library/items/{toned.id}/recovery", params={"made": "paper"})
        assert told.json()["kind"] == "none"
        photo = _keep(svc, _sheet(YELLOWED), number=5, classification="Photographs")
        told = client.get(f"/api/library/items/{photo.id}/recovery", params={"made": "paper"})
        assert told.json()["kind"] == "none"
        assert client.get("/api/library/items/met:none/recovery").status_code == 422


def test_the_deyellowed_sheet_is_sent_and_kept(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        drawing = _keep(svc, _sheet(YELLOWED), number=3, medium="pen and ink on paper")
        sent = client.get(f"/api/library/items/{drawing.id}/recovery/image")
        assert sent.status_code == 200 and sent.headers["content-type"] == "image/jpeg"
        picture = np.asarray(Image.open(io.BytesIO(sent.content)).convert("RGB"))
        assert _chroma(picture[5:35, 20:220]) < 0.025
        kept = list((svc.images.thumbs.parent / "recovery").glob("*.jpg"))
        assert len(kept) == 1
        stamp = kept[0].stat().st_mtime_ns
        again = client.get(f"/api/library/items/{drawing.id}/recovery/image")
        assert again.content == sent.content
        assert kept[0].stat().st_mtime_ns == stamp  # not made twice
        # Pastel is made apart.
        client.get(f"/api/library/items/{drawing.id}/recovery/image", params={"made": "opaque"})
        assert len(list((svc.images.thumbs.parent / "recovery").glob("*.jpg"))) == 2
