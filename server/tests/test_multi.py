from __future__ import annotations

import io
from itertools import combinations

import numpy as np
import pytest
from conftest import jpeg_bytes
from PIL import Image

from frame_server.imaging import RenderSettings, render_multi, render_original
from frame_server.imaging.grids import GRIDS, MAX_PHOTOS, MIN_PHOTOS, choose, grid_rects
from frame_server.imaging.layout import Fit, Orientation
from frame_server.library import ItemKind, Playlist, PlaylistKind
from frame_server.schedule import FrameSettings, Presentation

LANDSCAPE = (2560, 1440)
PORTRAIT = (1440, 2560)


def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


@pytest.mark.parametrize("canvas", [LANDSCAPE, PORTRAIT])
def test_every_grid_fits_the_canvas_without_overlaps(canvas: tuple[int, int]) -> None:
    assert sorted(GRIDS) == list(range(MIN_PHOTOS, MAX_PHOTOS + 1))
    for count, grids in GRIDS.items():
        assert [g.id for g in grids] == ["A", "B", "C"][: len(grids)]
        for grid in grids:
            rects = grid_rects(grid, canvas, 0.07)
            assert len(rects) == count
            for x, y, w, h in rects:
                assert x > 0 and y > 0 and x + w < canvas[0] and y + h < canvas[1]
                assert min(w, h) > 150
            assert not any(_overlap(a, b) for a, b in combinations(rects, 2)), grid.key


def test_portrait_canvas_transposes_the_grid() -> None:
    pair = GRIDS[2][0]  # two portrait windows side by side
    (_, _, w, h), _ = grid_rects(pair, LANDSCAPE, 0.07)
    assert h > w
    (_, _, w, h), _ = grid_rects(pair, PORTRAIT, 0.07)
    assert w > h  # two landscape windows, one above the other


def test_automatic_grid_matches_shapes() -> None:
    portraits = [3 / 4] * 3
    grid, rects, order = choose(portraits, LANDSCAPE, 0.07, seed="x")
    assert grid.name == "Tryptyk"
    assert sorted(order) == [0, 1, 2]
    # One portrait among landscapes lands in the tall window.
    shapes = [4 / 3, 3 / 4, 4 / 3]
    grid, rects, order = choose(shapes, LANDSCAPE, 0.07, pinned="C")
    tall = next(i for i, r in enumerate(rects) if r[3] > r[2])
    assert order[tall] == 1


def test_pinned_grid_and_stable_automatic_choice() -> None:
    shapes = [4 / 3] * 4
    assert choose(shapes, LANDSCAPE, 0.07, pinned="B")[0].id == "B"
    first = choose(shapes, LANDSCAPE, 0.07, seed="a,b,c,d")[0]
    assert all(choose(shapes, LANDSCAPE, 0.07, seed="a,b,c,d")[0] == first for _ in range(5))


def test_render_multi_composes_one_board() -> None:
    colours = [(200, 40, 40), (40, 40, 200), (40, 160, 40), (220, 200, 40)]
    sources = [jpeg_bytes(c, (300, 400) if i % 2 else (400, 300)) for i, c in enumerate(colours)]
    settings = RenderSettings()
    settings.layout.fit = Fit.MULTI
    settings.layout.margin = 0.07
    result = render_multi(sources, settings)
    assert result.panel.shape == (1440, 2560, 3)
    settings.layout.orientation = Orientation.PORTRAIT
    assert render_multi(sources, settings).preview.shape == (2560, 1440, 3)
    single = render_multi(sources[:1], settings)  # one photo: a passe-partout
    assert single.panel.shape == (1440, 2560, 3)
    board = np.asarray(render_multi(sources, settings, seed="s").original_image(), dtype=np.float32)
    fast = np.asarray(render_original(sources, settings, multi=True, seed="s"), dtype=np.float32)
    assert np.abs(board - fast).mean() < 0.5


def test_photos_keep_their_own_fits() -> None:
    old = FrameSettings.model_validate({"photo": {"preset": "photo", "fit": "auto"}})
    assert old.photo.fit == Fit.FILL
    art = FrameSettings.model_validate({"art": {"fit": "multi"}})
    assert art.art.fit == Fit.FIT
    # Automatic framing is no longer offered; photos have no caption.
    old = FrameSettings.model_validate({"art": {"fit": "auto"}, "photo": {"label": True}})
    assert old.art.fit == Fit.FIT and not old.photo.label
    with pytest.raises(ValueError):
        Presentation(multi_count=9)


def _photo(service, n: int, size: tuple[int, int] = (400, 300)):
    return service.importer.add_upload(
        jpeg_bytes((30 * n % 255, 80, 160), size), kind=ItemKind.PHOTO, title=f"Photo {n}"
    )


async def test_player_shows_boards_of_photos(service) -> None:
    photos = [_photo(service, n, (300, 400) if n % 3 == 0 else (400, 300)) for n in range(7)]
    playlist = service.library.save_playlist(
        Playlist(name="Rolka", kind=PlaylistKind.MANUAL, item_ids=[p.id for p in photos])
    )
    player = service.player
    settings = player.settings
    settings.playlist_id = playlist.id
    settings.shuffle = False
    settings.photo = Presentation(preset="photo", fit=Fit.MULTI, margin=0.07, multi_count=3)
    player.save_settings(settings)

    first = await player.next()
    state = player.state
    # Tests have no panel, so the only error allowed is the push reporting that.
    assert first is not None and "panel not configured" in (state.last_error or "")
    board = [state.current_item_id, *state.current_group]
    assert len(board) == 3 and len(set(board)) == 3
    assert not set(board) & set(state.queue)  # taken out of the rotation
    assert service.store.current().extra["item_ids"] == board

    # A redraw keeps the same photos; more photos per board takes new ones.
    await player.restyle()
    assert player.state.current_group == state.current_group
    settings = player.settings
    settings.photo = settings.photo.model_copy(update={"multi_count": 5})
    player.save_settings(settings)
    await player.restyle()
    group = player.state.current_group
    assert len(group) == 4 and group[:2] == state.current_group

    settings = player.settings
    settings.photo = settings.photo.model_copy(update={"multi_random": True})
    player.save_settings(settings)
    await player.next()
    assert MIN_PHOTOS <= len(player.state.current_group) + 1 <= MAX_PHOTOS


def test_preview_of_a_board(service) -> None:
    from fastapi.testclient import TestClient

    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    photos = [_photo(svc, n) for n in range(4)]
    playlist = svc.library.save_playlist(
        Playlist(name="Rolka", kind=PlaylistKind.MANUAL, item_ids=[p.id for p in photos])
    )
    with TestClient(app) as client:
        settings = client.get("/api/settings").json()
        settings["playlist_id"] = playlist.id
        settings["photo"].update(fit="multi", margin=0.07, multi_count=2)
        assert client.put("/api/settings", json=settings).status_code == 200
        response = client.get(f"/api/library/items/{photos[0].id}/preview")
        assert response.status_code == 200
        assert Image.open(io.BytesIO(response.content)).size == (1280, 720)
        framing = client.get(f"/api/library/items/{photos[0].id}/framing").json()
        assert framing["fit"] == "multi" and framing["windows"] == []
