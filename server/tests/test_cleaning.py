"""A work shown cleaned (``Item.cleaned``, ``frame_server.cleaning``): its
aged varnish taken off or its sheet de-yellowed, as the work's picture
everywhere, with its colours measured on the cleaned picture."""

from __future__ import annotations

import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
from test_recovery import YELLOWED, _chroma, _keep, _painting, _sheet, _under_varnish

from frame_server.imaging import recovery
from frame_server.imaging.color import linear_to_u8, u8_to_linear
from frame_server.library.models import Cut, ItemSummary, SharperCopy

#: The white linen of ``_painting``.
LINEN = (slice(55, 75), slice(100, 135))


def _warmth(picture: Image.Image | np.ndarray, where: tuple[slice, slice] = LINEN) -> float:
    """Red over blue of a patch: 1 for a neutral white, more under a varnish."""
    rgb = np.asarray(picture.convert("RGB") if isinstance(picture, Image.Image) else picture)
    patch = u8_to_linear(rgb[where]).reshape(-1, 3).mean(0)
    return float(patch[0] / patch[2])


def _app(service):
    from frame_server.web import create_app

    app = create_app(service.settings)
    return app, app.state.service


def test_the_whole_picture_is_cleaned_as_the_sum_says() -> None:
    lin = _painting()
    varnished = _under_varnish(lin, 0.8)
    whole = np.asarray(recovery.unvarnished(varnished, 0.6)).astype(int)
    by_sum = linear_to_u8(recovery.unvarnish(u8_to_linear(np.asarray(varnished)), 0.6)).astype(int)
    assert np.abs(whole - by_sum).max() <= 2
    # With no slider, a work is kept at a careful share of the proposal.
    proposed = recovery.read_varnish(varnished).strength
    assert recovery.kept_strength(varnished) == round(recovery.CAREFUL * proposed, 2)
    assert 0 < recovery.kept_strength(varnished) < proposed


def test_a_varnish_taken_off_is_the_works_picture_everywhere(service) -> None:
    app, svc = _app(service)
    with TestClient(app) as client:
        oil = _keep(svc, _under_varnish(_painting(), 0.8), number=1, year=1650)
        svc.importer.measure_again(oil)
        before = svc.library.get(oil.id)
        as_it_came = svc.images.image_path(oil).read_bytes()
        assert _warmth(Image.open(svc.images.image_path(oil))) > 1.6

        done = client.put(f"/api/library/items/{oil.id}/cleaned", params={"made": "oil"})
        assert done.status_code == 200, done.text
        cleaned = done.json()["cleaned"]
        assert cleaned["kind"] == "varnish" and cleaned["made"] == "oil"
        assert 0.3 <= cleaned["strength"] <= 0.75 and cleaned["at"]

        stored = svc.library.get(oil.id)
        # The original and the thumbnail are the cleaned picture, the
        # museum's own is kept beside them.
        assert _warmth(Image.open(svc.images.image_path(oil))) < 1.35
        assert svc.images.full_path(oil).read_bytes() == as_it_came
        thumb = Image.open(svc.images.ensure_thumb(stored))
        assert _warmth(thumb) < 1.35
        # Its colours are measured on the cleaned picture.
        assert stored.colors != before.colors
        # The lists know: a mark, and the pictures kept by the app are had anew.
        summary = ItemSummary.of(stored)
        assert summary.cleaned == "varnish" and summary.cleaned_at == cleaned["at"]
        # Nothing more to offer, and the comparison shows it as it came.
        told = client.get(f"/api/library/items/{oil.id}/recovery", params={"made": "oil"})
        assert told.json()["kind"] == "none"
        shown = client.get(f"/api/library/items/{oil.id}/cleaned/before")
        assert shown.status_code == 200 and shown.headers["content-type"] == "image/jpeg"
        assert _warmth(Image.open(io.BytesIO(shown.content))) > 1.6

        # "Przywróć werniks": the very picture that came, its colours again.
        back = client.delete(f"/api/library/items/{oil.id}/cleaned")
        assert back.status_code == 200 and back.json()["cleaned"] is None
        assert svc.images.image_path(oil).read_bytes() == as_it_came
        assert not svc.images.full_path(oil).exists()
        again = svc.library.get(oil.id)
        assert again.colors == before.colors
        assert ItemSummary.of(again).cleaned == "" and ItemSummary.of(again).cleaned_at == ""
        # Given up twice is given up.
        assert client.delete(f"/api/library/items/{oil.id}/cleaned").status_code == 200


def test_a_sheet_is_deyellowed_and_what_has_nothing_to_offer_is_refused(service) -> None:
    app, svc = _app(service)
    with TestClient(app) as client:
        drawing = _keep(svc, _sheet(YELLOWED), number=3, medium="pen and ink on paper")
        sheet = (slice(5, 35), slice(20, 220))
        assert _chroma(np.asarray(Image.open(svc.images.image_path(drawing)))[sheet]) > 0.04
        done = client.put(f"/api/library/items/{drawing.id}/cleaned", params={"made": "paper"})
        assert done.status_code == 200, done.text
        assert done.json()["cleaned"]["kind"] == "paper"
        assert _chroma(np.asarray(Image.open(svc.images.image_path(drawing)))[sheet]) < 0.025
        assert ItemSummary.of(svc.library.get(drawing.id)).cleaned == "paper"

        toned = _keep(svc, _sheet(YELLOWED), number=4, medium="chalk on blue paper")
        late = _keep(svc, _under_varnish(_painting(), 0.8), number=2, year=1975)
        photo = _keep(svc, _sheet(YELLOWED), number=5, classification="Photographs")
        for item, made in ((toned, "paper"), (late, "oil"), (photo, "paper")):
            refused = client.put(f"/api/library/items/{item.id}/cleaned", params={"made": made})
            assert refused.status_code == 422, refused.text
            assert svc.library.get(item.id).cleaned is None
        assert client.put(f"/api/library/items/{toned.id}/cleaned").status_code == 422


def test_a_cut_work_is_cut_then_cleaned(service) -> None:
    _, svc = _app(service)
    oil = _keep(svc, _under_varnish(_painting(), 0.8), number=1, year=1650)
    with Image.open(svc.images.image_path(oil)) as kept:
        whole = kept.size
    # The right half of the photograph is the work.
    half = [(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)]
    cut = Cut(work=half, aspect=round(whole[0] / whole[1], 5), by="owner", at="t1")
    svc.crops.apply(oil, cut)
    cut_only = Image.open(svc.images.image_path(oil)).convert("RGB")
    assert cut_only.width < whole[0] * 0.6

    done = svc.cleaning.clean(svc.library.get(oil.id), "oil")
    assert done.cleaned is not None and done.cut is not None
    both = Image.open(svc.images.image_path(oil)).convert("RGB")
    assert both.size == cut_only.size
    linen = (slice(55, 75), slice(20, 55))  # the linen, in the half kept
    assert _warmth(cut_only, linen) > 1.6 > 1.35 > _warmth(both, linen)
    with Image.open(svc.images.full_path(oil)) as full:
        assert full.size == whole  # the museum's photograph, whole and as it came
        assert _warmth(full) > 1.6
    # The comparison shows the work cut, not cleaned.
    assert svc.images.before_cleaning(done).size == cut_only.size

    # The cleaning given up: the cut stays.
    svc.cleaning.give_up(svc.library.get(oil.id))
    back = Image.open(svc.images.image_path(oil)).convert("RGB")
    assert back.size == cut_only.size and _warmth(back, linen) > 1.6
    assert svc.images.full_path(oil).is_file()


def test_a_thumbnail_had_from_its_address_is_cleaned_too(service, monkeypatch) -> None:
    _, svc = _app(service)
    oil = _keep(svc, _under_varnish(_painting(), 0.8), number=1, year=1650)
    done = svc.cleaning.clean(oil, "oil")
    # The original is pruned; the thumbnail comes from the museum again.
    svc.images.drop_picture(done)
    monkeypatch.setattr(
        svc.images, "_thumbnail", lambda item, urgent: _under_varnish(_painting(), 0.8)
    )
    assert _warmth(Image.open(svc.images.ensure_thumb(done))) < 1.35


def test_another_copy_is_left_as_it_comes_and_the_restorers_drawing_is_cleaned(service) -> None:
    _, svc = _app(service)
    oil = _keep(svc, _under_varnish(_painting(), 0.8), number=1, year=1650)
    first = svc.cleaning.clean(oil, "oil")
    assert first.cleaned is not None and first.cleaned.picture == ""

    def copy(item_id: str, restored: bool = False) -> SharperCopy:
        return SharperCopy(
            url="https://images.example/copy.jpg",
            item_id=item_id,
            source="commons",
            width=160,
            height=120,
            restored=restored,
        )

    # Another photograph takes the picture's place: nobody knows its
    # colours, so it is shown as it comes (Mateusz 2026-11-15 18:54).
    with_copy = svc.library.update(oil.id, sharper=copy("wmc:9"))
    svc.images.adopt(with_copy, _under_varnish(_painting(), 0.3))
    after = svc.cleaning.renew(first)
    assert after.cleaned == first.cleaned and after.cleaned_shown() is None
    assert ItemSummary.of(after).cleaned == ""
    assert _warmth(Image.open(svc.images.image_path(oil))) > 1.2
    assert not svc.images.full_path(oil).exists()

    # The work's own picture again: the one the cleaning was read on.
    own = svc.library.update(oil.id, sharper=None)
    svc.images.adopt(own, _under_varnish(_painting(), 0.8))
    assert own.cleaned_shown() is not None
    assert _warmth(Image.open(svc.images.image_path(oil))) < 1.35

    # The restorer draws it larger, from the picture as it came…
    assert _warmth(svc.restorer._picture(own)) > 1.6
    drawn = svc.library.update(oil.id, sharper=copy("owned:x.jpg", restored=True))
    svc.images.adopt(drawn, _under_varnish(_painting(), 0.8))
    assert drawn.cleaned_shown() is None
    # …and the drawing is cleaned the same.
    kept = svc.cleaning.renew(own)
    assert kept.cleaned is not None and kept.cleaned.drawn == "owned:x.jpg"
    assert kept.cleaned.strength == first.cleaned.strength and kept.cleaned.picture == ""
    assert kept.cleaned_shown() is not None and ItemSummary.of(kept).cleaned == "varnish"
    assert _warmth(Image.open(svc.images.image_path(oil))) < 1.35
    assert _warmth(Image.open(svc.images.full_path(oil))) > 1.6

    # A drawing of a picture that was not shown cleaned is left as drawn.
    other = _keep(svc, _under_varnish(_painting(), 0.8), number=2, year=1650)
    cleaned = svc.cleaning.clean(other, "oil")
    stale = svc.library.update(other.id, sharper=copy("wmc:9"))
    svc.images.adopt(stale, _under_varnish(_painting(), 0.3))
    redrawn = svc.library.update(other.id, sharper=copy("owned:y.jpg", restored=True))
    svc.images.adopt(redrawn, _under_varnish(_painting(), 0.3))
    assert svc.cleaning.renew(stale).cleaned == cleaned.cleaned
    assert svc.library.get(other.id).cleaned_shown() is None
