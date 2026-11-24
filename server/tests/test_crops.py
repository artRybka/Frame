"""Museum photographs cut down to the work in them (Mateusz 2026-11-14):
the corners set on the picture's edges, the cut kept beside the museum's
photograph, and the owner's correction, paper switch and restore. The
phone's model finds the work (``test_phone_crops``); Haiku and Opus did
until 2026-11-23."""

from __future__ import annotations

from typing import Any

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.imaging.cut import (
    snap,
    thin_backdrop,
    valid,
    warp,
    worth_cutting,
)
from frame_server.library.models import Cut, Item, ItemKind
from frame_server.service import FrameService

W, H = 900, 700
#: The painting inside its frame, on a grey board: true corners in px.
FRAME = (150, 100, 750, 600)
PAINTING = (180, 130, 720, 570)
TRUE = [(180 / W, 130 / H), (720 / W, 130 / H), (720 / W, 570 / H), (180 / W, 570 / H)]


def photo() -> Image.Image:
    """A painting in a gilt frame on a grey board."""
    rng = np.random.default_rng(1)
    a = np.full((H, W, 3), 120, dtype=np.uint8)
    x0, y0, x1, y1 = FRAME
    a[y0:y1, x0:x1] = (200, 160, 60)
    x0, y0, x1, y1 = PAINTING
    inner = rng.integers(20, 90, size=(y1 - y0, x1 - x0, 3), dtype=np.uint8)
    inner[..., 2] += 80
    a[y0:y1, x0:x1] = inner
    return Image.fromarray(a)


def sheet(strip: int = 9, board: tuple[int, int, int] = (250, 248, 240)) -> Image.Image:
    """A drawing on toned paper lying on a white board, ``strip`` px of
    the board showing (Perugino's Saint Sebastian, Cleveland)."""
    rng = np.random.default_rng(2)
    a = np.zeros((H, W, 3), dtype=np.uint8)
    a[:] = board
    paper = rng.integers(120, 190, size=(H - 2 * strip, W - 2 * strip, 3), dtype=np.uint8)
    a[strip : H - strip, strip : W - strip] = paper
    return Image.fromarray(a)


def grid(corners: list[tuple[float, float]]) -> list[list[float]]:
    return [[x * 1000, y * 1000] for x, y in corners]


#: Opus's answer: the frame and its opening, a few thousandths off.
OFF = [(0.205, 0.19), (0.795, 0.19), (0.795, 0.81), (0.205, 0.81)]
CORNERS = {
    "layers": [
        {
            "kind": "frame_outer",
            "corners": grid([(0.17, 0.14), (0.83, 0.14), (0.83, 0.86), (0.17, 0.86)]),
        },
        {"kind": "frame_inner", "corners": grid(OFF)},
    ],
    "work": 1,
    "with_paper": None,
    "shape": "rectangle",
    "confident": True,
    "note": "A painting in a gilt frame on a grey board",
}


def _work(
    service: FrameService, item_id: str, picture: Image.Image | None = None, **fields: Any
) -> Item:
    source, _, source_id = item_id.partition(":")
    fields.setdefault("kind", ItemKind.ARTWORK)
    item = Item(
        id=item_id,
        source=source,
        source_id=source_id,
        thumb_url=f"https://example.org/{source_id}.jpg",
        image_url=f"https://example.org/{source_id}-big.jpg",
        width=W,
        height=H,
        **fields,
    )
    img = picture or photo()
    path = service.images.image_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=95)
    thumb = img.copy()
    thumb.thumbnail((640, 640))
    thumb.save(service.images.thumb_path(item), "JPEG")
    return service.library.upsert(item)


def _near(a: list[tuple[float, float]], b: list[tuple[float, float]], by: float) -> bool:
    return all(abs(x - u) <= by and abs(y - v) <= by for (x, y), (u, v) in zip(a, b, strict=True))


# -- the corners and the cut ---------------------------------------------------------


def test_corners_are_set_on_the_pictures_own_edges() -> None:
    quad = valid(OFF)
    assert quad is not None and not _near(quad, TRUE, 0.004)
    snapped = snap(photo(), quad)
    assert _near(snapped, TRUE, 0.003)
    cut = warp(photo(), snapped)
    assert abs(cut.width - 540) <= 8 and abs(cut.height - 440) <= 8
    # The cut holds the painting only: no gold, no grey board.
    a = np.asarray(cut, dtype=int)
    assert (a[..., 2] - a[..., 0]).mean() > 60


def test_what_is_no_picture_is_no_cut() -> None:
    assert valid([(0, 0), (1, 0), (1, 1)]) is None  # three corners
    assert valid([(0.4, 0.4), (0.5, 0.4), (0.5, 0.5), (0.4, 0.5)]) is None  # a speck
    assert valid([(0.1, 0.1), (0.9, 0.9), (0.9, 0.1), (0.1, 0.9)]) is None  # crossed
    assert not worth_cutting([(0, 0), (1, 0), (1, 1), (0, 1)])


def test_a_cut_of_another_picture_is_never_applied(service: FrameService) -> None:
    item = _work(service, "mnw:3", pooled=True)
    cut = Cut(work=TRUE, aspect=W / H, picture="other:1", at="2026-11-14T10:00:00+00:00")
    item = service.library.update("mnw:3", cut=cut) or item
    assert item.cut_shown() is None and item.cut_version() == ""
    service.images.recut(item)
    with Image.open(service.images.image_path(item)) as kept:
        assert kept.size == (W, H)


def test_a_sheet_on_a_thin_strip_of_board_is_told_from_a_work_to_the_edges() -> None:
    def small(img: Image.Image) -> Image.Image:
        img.thumbnail((640, 640))
        return img

    assert thin_backdrop(small(sheet(strip=9)))
    assert not thin_backdrop(small(sheet(strip=0)))  # the drawing runs to the edges
    assert not thin_backdrop(small(photo()))  # a wide board: the judge sees that
    margin = Image.new("RGB", (W, H), (236, 230, 214))  # a print's wide blank margin
    margin.paste(Image.fromarray(np.full((300, 400, 3), 60, dtype=np.uint8)), (250, 200))
    assert not thin_backdrop(small(margin))


SHEET_CORNERS = {
    "layers": [
        {
            "kind": "sheet",
            "corners": grid([(0.01, 0.013), (0.99, 0.013), (0.99, 0.987), (0.01, 0.987)]),
        }
    ],
    "work": 0,
    "with_paper": None,
    "shape": "rectangle",
    "confident": True,
    "note": "A drawing on prepared paper on a white board",
}


def test_the_owners_corners_keep_his_framing(service: FrameService) -> None:
    # The audit of 2026-11-15: his corrected corners wiped his framings for
    # the frame; they show the same part of the photograph now, and again
    # on the whole photograph once he gives the cut up.
    from frame_server.imaging.layout import Crop
    from frame_server.library.models import Framing

    item = _work(service, "mnw:7", pooled=True)
    crops = service.crops
    item = crops.apply(item, Cut(work=TRUE, aspect=round(W / H, 5)))
    face = Crop(x=0.3, y=0.4, zoom=2.0)  # set on the cut picture
    item = service.library.update(item.id, framing={"portrait": Framing(detail=face)}) or item
    x0, y0 = TRUE[0]
    x1, y1 = TRUE[2]
    spot = (x0 + face.x * (x1 - x0), y0 + face.y * (y1 - y0))  # on the photograph
    wider = [(0.15, 0.12), (0.85, 0.12), (0.85, 0.88), (0.15, 0.88)]
    item = crops.set_by_owner(item, corners=wider)
    detail = item.framing["portrait"].detail
    assert detail is not None
    assert abs(0.15 + detail.x * 0.7 - spot[0]) < 0.01
    assert abs(0.12 + detail.y * 0.76 - spot[1]) < 0.01
    assert detail.zoom > face.zoom  # the picture is larger: the same face closer
    item = crops.give_up(item)
    whole = item.framing["portrait"].detail
    assert whole is not None and abs(whole.x - spot[0]) < 0.01 and abs(whole.y - spot[1]) < 0.01


def test_a_study_written_on_a_cut_given_back_keeps_its_boxes() -> None:
    from frame_server.ai.daily import Note, seen_before

    cut = Cut(
        aspect=round(W / H, 5),
        shape="round",
        undone=TRUE,
        undone_at="2026-11-14T10:00:00+00:00",
        at="2026-11-15T16:00:00+00:00",
    )
    item = Item(id="mnw:30", source="mnw", source_id="30", cut=cut)
    on_cut = Note.model_construct(created_at="2026-11-14T20:00:00+00:00")
    before = Note.model_construct(created_at="2026-11-13T20:00:00+00:00")
    assert seen_before(item, on_cut, None).cut == TRUE
    assert seen_before(item, before, None).cut == []


# -- the audit of 2026-11-15: 28 of 178 cuts wrong ---------------------------------------


def _bands(*bands: tuple[int, int]) -> Image.Image:
    """Nested rectangles, each ``(inset px, grey)`` inside the one before."""
    a = np.zeros((H, W, 3), dtype=np.uint8)
    for inset, grey in bands:
        a[inset : H - inset, inset : W - inset] = grey
    return Image.fromarray(a)


def _box(inset: float) -> list[tuple[float, float]]:
    return [
        (inset / W, inset / H),
        (1 - inset / W, inset / H),
        (1 - inset / W, 1 - inset / H),
        (inset / W, 1 - inset / H),
    ]


def test_a_sheets_side_keeps_its_paper_from_the_border_line_inside() -> None:
    # A woodcut's top paper cut away (MNK 314364): the snap took the black
    # border line printed just inside the sheet's edge.
    picture = _bands((0, 150), (60, 230), (68, 30), (71, 230))
    paper = _box(60)
    assert not _near(snap(picture, paper), paper, 0.004)  # the line wins
    assert _near(snap(picture, paper, "sheet"), paper, 0.003)
    # Opus's line out on the board: the paper's edge is the only one.
    assert _near(snap(picture, _box(54), "sheet"), paper, 0.003)


def test_a_paintings_side_stays_off_the_gilt_slip_outside() -> None:
    # A still life on copper (MNK 338944): the snap took the slip's outer
    # edge, the slip was kept.
    picture = _bands((0, 20), (53, 200), (60, 120))
    painting = _box(60)
    assert not _near(snap(picture, painting), painting, 0.004)
    assert _near(snap(picture, painting, "frame_inner"), painting, 0.003)


def test_a_print_is_shown_on_its_whole_sheet() -> None:
    # Mateusz 2026-11-21: „Dla rysunku i grafiki zostawimy tylko jedno
    # kadrowanie - »do kartki«”; 18:17 „Tak” to the sheet shown, not the plate.
    sheet_quad = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    plate = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    for paper in (True, False):
        cut = Cut(work=sheet_quad, plate=plate, paper=paper, aspect=1.0)
        assert cut.shown() == sheet_quad and cut.framed_by() is None
    from frame_server.ai.crops import framed

    assert framed(cut).framed_kind == ""


SHEET_BOX = (120, 80, 780, 620)
PLATE_BOX = (240, 170, 660, 500)


def print_on_sheet() -> Image.Image:
    rng = np.random.default_rng(3)
    a = np.full((H, W, 3), 110, dtype=np.uint8)
    x0, y0, x1, y1 = SHEET_BOX
    a[y0:y1, x0:x1] = (238, 232, 218)
    x0, y0, x1, y1 = PLATE_BOX
    a[y0:y1, x0:x1] = rng.integers(40, 120, size=(y1 - y0, x1 - x0, 3), dtype=np.uint8)
    return Image.fromarray(a)


def _px(box: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = box
    return [(x0 / W, y0 / H), (x1 / W, y0 / H), (x1 / W, y1 / H), (x0 / W, y1 / H)]


PRINT_CORNERS = {
    "layers": [
        {"kind": "sheet", "corners": grid(_px(SHEET_BOX))},
        {"kind": "plate", "corners": grid(_px(PLATE_BOX))},
    ],
    "work": 1,
    "with_paper": 0,
    "shape": "rectangle",
    "confident": True,
    "note": "An etching on its sheet",
}


def test_a_sheet_filling_the_photograph_is_shown_whole() -> None:
    plate = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    cut = Cut(work=None, plate=plate, aspect=1.0)
    assert cut.shown() is None and cut.framed_by() is None


def test_the_owner_sets_a_prints_sheet_as_its_cut(service: FrameService) -> None:
    crops = service.crops
    aspect = round(W / H, 5)
    item = _work(service, "aic:7", picture=print_on_sheet(), pooled=True)
    item = crops.apply(
        item, Cut(work=_px(SHEET_BOX), plate=_px(PLATE_BOX), aspect=aspect, shape="rectangle")
    )
    wider = _px((100, 60, 800, 640))
    item = crops.set_by_owner(item, corners=wider)
    assert item.cut is not None and item.cut.work == wider and item.cut.surround is None
    assert item.cut_shown() == wider and item.cut.framed_kind == ""


#: The frame's outer edge in :func:`photo`.
FRAME_EDGE = [(150 / W, 100 / H), (750 / W, 100 / H), (750 / W, 600 / H), (150 / W, 600 / H)]


def _cut_by_model(service: FrameService, item_id: str) -> Item:
    """The work cut as the phone's model cuts it: the painting, its frame's edge around."""
    item = service.library.get(item_id)
    assert item is not None
    cut = Cut(
        work=TRUE,
        around=["easel", "frame"],
        aspect=round(W / H, 5),
        picture=item.picture_key(),
        shape="rectangle",
        by="auto",
        surround=FRAME_EDGE,
        surround_kind="frame",
        surround_asked=True,
    )
    return service.crops.apply(item, cut)


def test_the_owner_corrects_and_restores_the_models_cut(service: FrameService) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    _work(service, "mnw:7", pooled=True)
    cut = _cut_by_model(service, "mnw:7").cut
    assert cut is not None and cut.framed_kind == "frame"
    with TestClient(app) as client:
        full = client.get("/api/library/items/mnw:7/full?side=450")
        assert full.status_code == 200
        inframe = client.get("/api/library/items/mnw:7/framed?side=500")
        assert inframe.status_code == 200 and inframe.headers["content-type"] == "image/jpeg"
        corners = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        put = client.put("/api/library/items/mnw:7/cut", json={"corners": corners})
        assert put.status_code == 200, put.text
        assert put.json()["cut"]["by"] == "owner"
        # His corners reach past the frame's edge: nothing around to show.
        assert put.json()["cut"]["framed_kind"] == ""
        assert client.get("/api/library/items/mnw:7/framed").status_code == 404
        assert put.json()["cut"]["work"][0] == [0.1, 0.1]
        bad = client.put("/api/library/items/mnw:7/cut", json={"corners": corners[:3]})
        assert bad.status_code == 422
        # He sets the frame's edge himself: around his corners, "W ramie"
        # again; the work's pictures stay.
        before = service.images.image_path(service.library.get("mnw:7")).stat().st_mtime_ns
        frame = [[0.05, 0.04], [0.95, 0.04], [0.95, 0.96], [0.05, 0.96]]
        mine = client.put("/api/library/items/mnw:7/cut", json={"frame": frame}).json()["cut"]
        assert mine["surround_by"] == "owner" and mine["framed_kind"] == "frame"
        assert mine["work"][0] == [0.1, 0.1] and mine["surround"][0] == [0.05, 0.04]
        assert client.get("/api/library/items/mnw:7/framed?side=500").status_code == 200
        after = service.images.image_path(service.library.get("mnw:7")).stat().st_mtime_ns
        assert after == before
        # The work cut anew keeps his frame.
        tighter = [[0.12, 0.12], [0.88, 0.12], [0.88, 0.88], [0.12, 0.88]]
        again = client.put("/api/library/items/mnw:7/cut", json={"corners": tighter}).json()["cut"]
        assert again["surround"][0] == [0.05, 0.04] and again["framed_kind"] == "frame"
        nothing = client.put("/api/library/items/mnw:7/cut", json={"frame": frame[:2]})
        assert nothing.status_code == 422
        # "Bez marginesu" with no plate known asks nobody and cuts nothing more.
        bare = client.put("/api/library/items/mnw:7/cut", json={"paper": False}).json()["cut"]
        assert bare["work"][0] == [0.12, 0.12] and bare["plate"] is None

        gone = client.delete("/api/library/items/mnw:7/cut").json()
        assert gone["cut"]["work"] is None and gone["cut"]["by"] == "owner"
    item = service.library.get("mnw:7")
    assert item is not None and item.cut_shown() is None
    assert not service.images.full_path(item).exists()
    with Image.open(service.images.image_path(item)) as whole:
        assert whole.size == (W, H)  # the museum's photograph again


def test_the_owners_framing_moves_onto_the_cut_picture(service: FrameService) -> None:
    # Wyspiański's „Macierzyństwo” (2026-11-15): a close-up of the face
    # saved for the portrait frame shows the same face once the work is cut.
    from frame_server.ai.crops import framing_within
    from frame_server.imaging.layout import Crop
    from frame_server.library.models import Framing

    face = Crop(x=0.404, y=0.321, zoom=3.915)
    _work(service, "wikiart:1", pooled=True, framing={"portrait": Framing(detail=face)})
    item = _cut_by_model(service, "wikiart:1")
    shown = item.cut_shown()
    assert shown is not None
    detail = item.framing["portrait"].detail
    assert detail is not None
    x0, y0 = shown[0]
    x1, y1 = shown[2]
    # The same spot of the photograph, now in the cut picture's terms.
    assert abs(x0 + detail.x * (x1 - x0) - face.x) < 0.01
    assert abs(y0 + detail.y * (y1 - y0) - face.y) < 0.01
    assert 1.0 <= detail.zoom < face.zoom
    # A framing on a picture filling the cut stays whole.
    whole = framing_within(
        {"landscape": Framing(fill=Crop())}, [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    )
    fill = whole["landscape"].fill
    assert fill is not None and (fill.x, fill.y, fill.zoom) == (0.5, 0.5, 1.0)
