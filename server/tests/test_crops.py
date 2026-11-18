"""Museum photographs cut down to the work in them (Mateusz 2026-11-14):
the corners set on the picture's edges, the cut kept beside the museum's
photograph, Haiku picking the works and Opus placing the corners, at night
and when a card opens, and the owner's correction, paper switch and
restore."""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
from test_ai import FakeAnthropic, _message, fake  # noqa: F401  (fixture)

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU, OPUS
from frame_server.ai.crops import (
    STRIPS_NOTE,
    on_photo_edge,
    plate_for_chart,
    read_layers,
    strips_fit,
    tilted,
)
from frame_server.imaging.cut import (
    backdrop_quad,
    sheet_out_to_strips,
    snap,
    thin_backdrop,
    valid,
    warp,
    worth_cutting,
)
from frame_server.library.models import Cut, Item, ItemKind, ItemSummary
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


def _answer(client: FakeAnthropic, data: dict[str, Any]) -> None:
    def results(batch_id: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                custom_id=r["custom_id"],
                result=SimpleNamespace(type="succeeded", message=_message(data)),
            )
            for r in client.batches[batch_id]
        ]

    client.messages.batches.results = results


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


def test_paper_is_kept_and_the_plate_is_the_alternative() -> None:
    sheet = grid([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)])
    plate = grid([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])
    data = {
        "layers": [{"kind": "sheet", "corners": sheet}, {"kind": "plate", "corners": plate}],
        "work": 1,
        "with_paper": None,  # Opus would cut the paper away: never by itself
    }
    read = read_layers(data)
    assert read is not None
    shown, without = read
    assert shown is not None and shown[0] == (0.1, 0.1)
    assert without is not None and without[0] == (0.2, 0.2)
    # The plate alone, the sheet filling the photograph (a print, MNW): the
    # paper stays, the plate is the alternative.
    alone = {"layers": [{"kind": "plate", "corners": plate}], "work": 0, "with_paper": None}
    assert read_layers(alone) == (None, [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])


def test_a_sketchbook_page_is_the_work_not_the_book_around_it() -> None:
    # Bierstadt's tree (Met, Mateusz 2026-11-14): the book's block listed
    # as a sheet too, the page chosen; the block is no paper to keep.
    block = grid([(0.19, 0.1), (0.8, 0.1), (0.8, 0.89), (0.19, 0.89)])
    page = grid([(0.2, 0.11), (0.79, 0.11), (0.79, 0.88), (0.2, 0.88)])
    data = {
        "layers": [{"kind": "sheet", "corners": block}, {"kind": "sheet", "corners": page}],
        "work": 1,
        "with_paper": None,
    }
    read = read_layers(data)
    assert read is not None
    shown, without = read
    assert shown is not None and shown[0] == (0.2, 0.11) and without is None


def test_works_opus_would_not_cut_are_asked_again(service: FrameService) -> None:
    crops = service.crops
    state = crops.state()
    state["asked"] = {
        "met:1": {"v": 1, "at": "2026-11-14"},  # the judge saw nothing
        "met:2": {"v": 1, "at": "2026-11-14", "critic": False},  # Opus unsure
        "met:3": {"v": 1, "broken": True},
    }
    crops._save(state)
    assert set(crops.asked()) == {"met:1", "met:3"}


# -- the night -----------------------------------------------------------------------


def test_haiku_picks_opus_sets_the_corners_and_the_work_is_cut(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "mnw:1", title="Portret", pooled=True)
    crops = service.crops
    fake.ended = True
    _answer(fake, {"surround": ["backdrop", "frame"]})
    assert crops.order() and crops.collect()
    judge = fake.batches["batch_1"][0]["params"]
    assert judge["model"] == HAIKU
    assert crops.state()["claims"]["mnw:1"]["around"] == ["backdrop", "frame"]

    _answer(fake, CORNERS)
    assert crops.order()
    critic = fake.batches["batch_2"][0]["params"]
    assert critic["model"] == OPUS
    assert [b["type"] for b in critic["messages"][0]["content"]] == ["image", "image", "text"]
    assert crops.collect() is True

    item = service.library.get("mnw:1")
    assert item is not None and item.cut is not None and item.cut.by == "auto"
    shown = item.cut_shown()
    assert shown is not None and _near(shown, TRUE, 0.003)
    # The original is the work; the museum's photograph is kept whole.
    with Image.open(service.images.image_path(item)) as kept:
        assert abs(kept.width - 540) <= 10
    assert service.images.full_path(item).is_file()
    with Image.open(service.images.museum_photo(item)) as whole:
        assert whole.size == (W, H)
    with Image.open(service.images.thumb_path(item)) as thumb:
        assert abs(thumb.width / thumb.height - 540 / 440) < 0.05
    summary = ItemSummary.of(item)
    assert summary.cropped and summary.cut
    assert abs(summary.width / summary.height - 540 / 440) < 0.05
    (written,) = crops.written()
    assert written["id"] == "mnw:1"
    assert not crops.order()  # nothing left
    assert service.claude.spending.by_kind()["crops"] > 0


def test_only_paper_is_cut_by_nobody_and_an_unsure_answer_changes_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "mnk:1", pooled=True)
    _work(service, "mnk:2", pooled=True)
    crops = service.crops
    fake.ended = True

    def results(batch_id: str) -> list[SimpleNamespace]:
        first = {"w0": {"surround": ["paper_margin"]}, "w1": {"surround": ["easel"]}}
        return [
            SimpleNamespace(
                custom_id=r["custom_id"],
                result=SimpleNamespace(
                    type="succeeded",
                    message=_message(
                        first[r["custom_id"]]
                        if batch_id == "batch_1"
                        else {**CORNERS, "confident": False}
                    ),
                ),
            )
            for r in fake.batches[batch_id]
        ]

    fake.messages.batches.results = results
    assert crops.order() and crops.collect()
    order = fake.batches["batch_1"]
    ids = {r["custom_id"]: i for r, i in zip(order, crops.state()["asked"], strict=False)}
    assert len(ids) == 2
    paper = next(
        i for i in (service.library.get("mnk:1"), service.library.get("mnk:2")) if i and i.cut
    )
    assert paper.cut is not None and paper.cut.has_paper and paper.cut_shown() is None
    assert crops.order() and crops.collect()  # Opus unsure: nothing cut
    for item_id in ("mnk:1", "mnk:2"):
        item = service.library.get(item_id)
        assert item is not None and item.cut_shown() is None
        assert not service.images.full_path(item).exists()
    assert not crops.order()


def test_the_switch_and_the_owners_photos_ask_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "upload:1", pooled=False)
    assert service.crops.candidates({}) == []
    _work(service, "mnw:1", pooled=True)
    service.ai_config.update(AiConfigUpdate(crops=False))
    assert not service.crops.order()
    assert not service.crops.now(service.library.get("mnw:1"))  # type: ignore[arg-type]
    assert fake.batches == {} and fake.asked == []


# -- the card and the owner ----------------------------------------------------------------


def test_the_card_cuts_at_once_and_the_owner_corrects_and_restores(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    _work(service, "mnw:7", pooled=True)
    answers = iter([{"surround": ["easel", "frame"]}, CORNERS])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    with TestClient(app) as client:
        seen = client.post("/api/library/items/mnw:7/cut/check?wait=30").json()
        assert seen["changed"] and seen["item"]["cut"]["by"] == "auto"
        assert [p["model"] for p in fake.asked] == [HAIKU, OPUS]
        again = client.post("/api/library/items/mnw:7/cut/check?wait=30").json()
        assert not again["changed"] and len(fake.asked) == 2  # asked once

        full = client.get("/api/library/items/mnw:7/full?side=450")
        assert full.status_code == 200
        # "W ramie": the frame's edge came with the corners.
        assert seen["item"]["cut"]["framed_kind"] == "frame"
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
        # He sets the frame's edge himself („Tak, drugie narożniki dla ramy”):
        # around his corners, "W ramie" again; the work's pictures stay.
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

        gone = client.delete("/api/library/items/mnw:7/cut").json()
        assert gone["cut"]["work"] is None and gone["cut"]["by"] == "owner"
    item = service.library.get("mnw:7")
    assert item is not None and item.cut_shown() is None
    assert not service.images.full_path(item).exists()
    with Image.open(service.images.image_path(item)) as whole:
        assert whole.size == (W, H)  # the museum's photograph again
    assert not service.crops.now(item)  # never cut again by itself


def test_a_museum_work_only_looked_at_is_cut_too(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
    monkeypatch: Any,
) -> None:
    # Kauffmann's Muses (MNW, Mateusz 2026-11-14): opened from a museum,
    # not in the library yet; the card's check took it as nothing to do.
    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    looked_at = _work(service, "mnw:8", pooled=True)
    service.library.delete("mnw:8")
    assert service.library.get("mnw:8") is None
    monkeypatch.setattr(service.importer, "resolve", lambda item_id: looked_at)
    answers = iter([{"surround": ["backdrop", "frame"]}, CORNERS])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    with TestClient(app) as client:
        seen = client.post("/api/library/items/mnw:8/cut/check?wait=30").json()
    assert seen["changed"] and seen["item"]["cut"]["by"] == "auto"
    stored = service.library.get("mnw:8")
    assert stored is not None and stored.pooled and stored.cut_shown() is not None


def test_a_cut_of_another_picture_is_never_applied(service: FrameService) -> None:
    item = _work(service, "mnw:3", pooled=True)
    cut = Cut(work=TRUE, aspect=W / H, picture="other:1", at="2026-11-14T10:00:00+00:00")
    item = service.library.update("mnw:3", cut=cut) or item
    assert item.cut_shown() is None and item.cut_version() == ""
    service.images.recut(item)
    with Image.open(service.images.image_path(item)) as kept:
        assert kept.size == (W, H)


def test_the_cards_cut_is_not_held_back_while_the_app_is_in_use(service: FrameService) -> None:
    # As the background's, the card's cut waited for a thumbnail while the
    # owner browsed Odkrywaj; both workers stood and every card after them
    # waited 60 s for nothing (1.145.136 on the NAS, 2026-11-14 23:20).
    from frame_server.library import hosts

    crops = service.crops
    crops._setup()
    assert crops._pool is not None
    seen = crops._pool.submit(lambda: (hosts.purpose(), hosts.deferrable())).result()
    assert seen == ("kadrowanie", False)


# -- a thin strip of backdrop -----------------------------------------------------------


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


def test_a_thin_backdrop_the_judge_missed_is_cut_away(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Haiku saw nothing around Perugino's Saint Sebastian (2026-11-15).
    _work(service, "cma:1", picture=sheet(), pooled=True)
    answers = iter([{"surround": []}, SHEET_CORNERS])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    assert service.crops.now(service.library.get("cma:1"))  # type: ignore[arg-type]
    assert [p["model"] for p in fake.asked] == [HAIKU, OPUS]
    assert "backdrop" in fake.asked[1]["messages"][0]["content"][-1]["text"]
    item = service.library.get("cma:1")
    assert item is not None and item.cut is not None and item.cut_shown() is not None
    assert service.crops.asked()["cma:1"]["band"] == 2


def test_works_judged_before_go_to_opus_when_their_card_opens(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "cma:2", picture=sheet(), pooled=True)  # the judge saw nothing
    paper = _work(service, "mnw:3", picture=sheet(), pooled=True)  # only paper
    service.library.update(paper.id, cut=Cut(around=["paper_margin"]))
    _work(service, "cma:4", picture=sheet(strip=0), pooled=True)  # to the edges
    crops = service.crops
    state = crops.state()
    state["asked"] = {i: {"v": 2, "at": "2026-11-14", "q": 2} for i in ("cma:2", "mnw:3", "cma:4")}
    crops._save(state)
    answers = iter([SHEET_CORNERS, SHEET_CORNERS])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    for item_id in ("cma:2", "mnw:3", "cma:4"):
        crops.now(service.library.get(item_id))  # type: ignore[arg-type]
    assert [p["model"] for p in fake.asked] == [OPUS, OPUS]  # no judge again, none for cma:4
    for item_id in ("cma:2", "mnw:3"):
        item = service.library.get(item_id)
        assert item is not None and item.cut is not None and item.cut_shown() is not None
    assert "paper_margin" in service.library.get("mnw:3").cut.around  # type: ignore[union-attr]
    assert not crops.now(service.library.get("cma:2"))  # type: ignore[arg-type]
    assert len(fake.asked) == 2


def test_works_cared_about_are_swept_once_for_a_thin_backdrop(service: FrameService) -> None:
    _work(service, "cma:5", picture=sheet(), pooled=True)
    _work(service, "cma:6", picture=sheet(strip=0), pooled=True)
    _work(service, "cma:7", picture=sheet(), pooled=True)  # nobody cares
    crops = service.crops
    crops.cared = lambda: {"cma:5": 0, "cma:6": 1}
    state = crops.state()
    state["asked"] = {i: {"v": 2, "at": "2026-11-14"} for i in ("cma:5", "cma:6", "cma:7")}
    crops._save(state)
    assert crops.swept() == 1
    state = crops.state()
    assert state["claims"] == {"cma:5": {"around": ["backdrop"], "band": True}}
    assert state["asked"]["cma:5"]["band"] == 2
    assert crops.swept() == 0  # once


# -- a plate that is the work ---------------------------------------------------------------


def test_a_plate_that_is_the_work_is_no_paper_to_choose(service: FrameService) -> None:
    # Wyczółkowski's lithograph on China paper laid on a card (MNK,
    # 2026-11-15): "Z papierem" and "Sama odbitka" were the same picture.
    work = [(0.0537, 0.2137), (0.9362, 0.2216), (0.9426, 0.7871), (0.0507, 0.7867)]
    plate = [(0.0532, 0.2137), (0.9362, 0.2216), (0.9429, 0.7869), (0.0509, 0.7864)]
    twin = Cut(work=work, plate=plate, paper=False, by="owner", around=["mount", "paper_margin"])
    alone = twin.without_twin()
    assert alone.plate is None and alone.paper and alone.around == ["mount"]
    assert alone.shown() == work and alone.has_paper is False
    other = Cut(work=work, plate=[(0.2, 0.3), (0.8, 0.3), (0.8, 0.7), (0.2, 0.7)])
    assert other.without_twin() is other

    _work(service, "mnk:9", pooled=True)
    service.library.update("mnk:9", cut=twin)
    _work(service, "mnk:10", pooled=True)
    service.library.update("mnk:10", cut=other)
    crops = service.crops
    assert crops.untwinned() == 1
    stored = service.library.get("mnk:9")
    assert stored is not None and stored.cut is not None and stored.cut.plate is None
    assert stored.cut.by == "owner" and stored.cut.work == work
    assert service.library.get("mnk:10").cut.plate is not None  # type: ignore[union-attr]
    assert crops.untwinned() == 0  # once


def test_the_strips_alone_are_cut_away_when_opus_is_unsure(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Munch's Evening, Melancholy I (Cleveland, 2026-11-15): the strips
    # found, Opus unsure of a sheet's edge that nearly meets the photograph's.
    quad = backdrop_quad(sheet(strip=9))
    assert quad is not None and _near(
        quad,
        [(9 / W, 9 / H), (1 - 9 / W, 9 / H), (1 - 9 / W, 1 - 9 / H), (9 / W, 1 - 9 / H)],
        0.004,
    )
    assert backdrop_quad(sheet(strip=0)) is None and backdrop_quad(photo()) is None

    _work(service, "cma:11", picture=sheet(), pooled=True)
    crops = service.crops
    state = crops.state()  # asked by 1.145.138: Opus unsure, nothing cut
    state["asked"] = {
        "cma:11": {"v": 2, "at": "2026-11-15", "p": "", "critic": False, "band": True, "q": 2}
    }
    crops._save(state)
    answers = iter([{**SHEET_CORNERS, "confident": False}])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    assert crops.now(service.library.get("cma:11"))  # type: ignore[arg-type]
    assert [p["model"] for p in fake.asked] == [OPUS]
    item = service.library.get("cma:11")
    assert item is not None and item.cut is not None
    shown = item.cut_shown()
    assert shown is not None and _near(shown, quad, 0.004)


def test_a_sheets_side_taken_for_its_plates_gets_it_back(service: FrameService) -> None:
    # Beksiński (MNK, 2026-11-15): "z marginesem" lost the right margin,
    # the sheet's right side lying on the drawing's.
    img = np.asarray(sheet(strip=9)).copy()
    img[60:640, 80:820] = 40  # the drawing on the paper
    picture = Image.fromarray(img)
    s, r = 9 / W, 1 - 9 / W
    plate = [(80 / W, 60 / H), (820 / W, 60 / H), (820 / W, 640 / H), (80 / W, 640 / H)]
    wrong = [(s, 9 / H), (820 / W, 9 / H), (820 / W, 1 - 9 / H), (s, 1 - 9 / H)]
    fixed = sheet_out_to_strips(picture, wrong, plate)
    assert all(abs(x - r) < 0.004 for x, _ in (fixed[1], fixed[2]))
    assert fixed[0] == wrong[0] and fixed[3] == wrong[3]
    right = [(s, 9 / H), (r, 9 / H), (r, 1 - 9 / H), (s, 1 - 9 / H)]
    assert sheet_out_to_strips(picture, right, plate) == right

    item = _work(service, "mnk:12", picture=picture, pooled=True)
    service.crops.apply(item, Cut(work=wrong, plate=plate, by="owner", aspect=W / H))
    assert service.crops.sheets_out() == 1
    stored = service.library.get("mnk:12")
    assert stored is not None and stored.cut is not None and stored.cut.work is not None
    assert abs(stored.cut.work[1][0] - r) < 0.004
    assert service.crops.sheets_out() == 0  # once


# -- the owner's framing ------------------------------------------------------------------


def test_the_owners_framing_moves_onto_the_cut_picture(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Wyspiański's „Macierzyństwo” (2026-11-15): a copy in a thin wooden
    # frame, a close-up of the face saved for the portrait frame; Opus
    # found the frame's opening, and the framing kept the cut from being
    # written. The card asks again, and the close-up shows the same face.
    from frame_server.ai.crops import framing_within
    from frame_server.imaging.layout import Crop
    from frame_server.library.models import Framing

    face = Crop(x=0.404, y=0.321, zoom=3.915)
    _work(service, "wikiart:1", pooled=True, framing={"portrait": Framing(detail=face)})
    crops = service.crops
    state = crops.state()
    state["asked"] = {"wikiart:1": {"v": 2, "at": "2026-11-15", "p": "", "critic": True, "band": 2}}
    crops._save(state)
    answers = iter([{"surround": ["frame"]}, CORNERS])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    assert crops.now(service.library.get("wikiart:1"))  # type: ignore[arg-type]
    assert [p["model"] for p in fake.asked] == [HAIKU, OPUS]
    item = service.library.get("wikiart:1")
    assert item is not None and item.cut is not None
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
    assert not crops.now(item)  # cut: not asked again
    # A framing on a picture filling the cut stays whole.
    whole = framing_within(
        {"landscape": Framing(fill=Crop())}, [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    )
    fill = whole["landscape"].fill
    assert fill is not None and (fill.x, fill.y, fill.zoom) == (0.5, 0.5, 1.0)


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


def test_the_night_cuts_a_copy_picked_after_the_photograph_was_looked_at(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # The audit of 2026-11-15: a sharper copy picked at night took the place
    # of a photograph cut (or looked at) before, and was shown whole until
    # its card was opened.
    from frame_server.library.models import SharperCopy

    cut = _work(service, "mnw:8", pooled=True)
    looked = _work(service, "mnw:9", pooled=True)
    crops = service.crops
    crops.apply(cut, Cut(work=TRUE, aspect=round(W / H, 5)))
    state = crops.state()
    state["asked"] = {
        "mnw:8": {"v": 2, "at": "2026-11-14", "critic": True},
        "mnw:9": {"v": 2, "at": "2026-11-14"},
    }
    crops._save(state)
    assert crops.candidates(crops.asked()) == []
    copy = SharperCopy(
        url="https://example.org/c.jpg", item_id="wmc:1", source="wmc", width=W, height=H
    )
    for item_id in ("mnw:8", "mnw:9"):
        service.library.update(item_id, sharper=copy)
    assert {i.id for i in crops.candidates(crops.asked())} == {"mnw:8", "mnw:9"}
    # Asked about at night, the picture looked at is kept: not asked again.
    fake.ended = True
    _answer(fake, {"surround": []})
    assert crops.order() and crops.collect()
    assert crops.asked()["mnw:9"]["p"] == "wmc:1"
    assert crops.candidates(crops.asked()) == []
    assert looked.id in crops.asked()


def test_a_page_about_a_work_waits_for_its_cut(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # The audit of 2026-11-15: a study read the photograph with its frame
    # and easel when it was written before the work was cut.
    assert service.daily.job.cutting == service.crops.before_page
    assert service.study.job.cutting == service.crops.before_page
    _work(service, "mnw:10", pooled=True)
    answers = iter([{"surround": ["frame"]}, CORNERS])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    item = service.daily.job.cut_first(service.library.get("mnw:10"))  # type: ignore[arg-type]
    assert item.cut_shown() is not None
    # Looked at once: the next page asks nothing.
    assert service.daily.job.cut_first(item).cut == item.cut
    assert [p["model"] for p in fake.asked] == [HAIKU, OPUS]
    # A work outside the library is not looked at (its cut could not be kept).
    outside = Item(id="mnw:11", source="mnw", source_id="11", kind=ItemKind.ARTWORK)
    assert service.crops.before_page(outside) is False


# -- works whose outline is no rectangle -------------------------------------------------


def test_a_work_that_is_no_rectangle_is_never_cut(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Mateusz 2026-11-15: a gunlock engraving cut out along its drawing on a
    # grey board, a round miniature in its gilt frame: „nie kadruj”.
    _work(service, "met:1", picture=sheet(), pooled=True)  # strips the pixels would cut
    answers = iter([{"surround": ["backdrop", "frame"]}, {**CORNERS, "shape": "round"}])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    crops = service.crops
    assert not crops.now(service.library.get("met:1"))  # type: ignore[arg-type]
    assert [p["model"] for p in fake.asked] == [HAIKU, OPUS]
    assert '"shape"' in fake.asked[1]["messages"][0]["content"][-1]["text"]
    item = service.library.get("met:1")
    assert item is not None and item.cut is not None
    assert item.cut.shape == "round" and item.cut_shown() is None and not item.cut.has_paper
    assert not service.images.full_path(item).exists()
    assert crops.written() == []
    assert not crops.now(item)  # never asked again
    assert len(fake.asked) == 2
    assert crops.candidates(crops.asked()) == []
    # The owner may still cut it himself.
    item = crops.set_by_owner(item, corners=TRUE)
    assert item.cut is not None and item.cut.by == "owner" and item.cut_shown() == TRUE


def test_cuts_set_before_the_outline_was_asked_are_given_back_whole(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    from frame_server.imaging.layout import Crop
    from frame_server.library.models import Framing

    crops = service.crops
    aspect = round(W / H, 5)
    face = Crop(x=0.5, y=0.4, zoom=2.0)
    for item_id in ("mnw:21", "mnw:22", "mnw:23"):
        item = _work(service, item_id, pooled=True)
        crops.apply(item, Cut(work=TRUE, aspect=aspect, at="2026-11-14T10:00:00+00:00"))
    service.library.update("mnw:21", framing={"portrait": Framing(detail=face)})
    owner = _work(service, "mnw:24", pooled=True)
    crops.apply(owner, Cut(work=TRUE, aspect=aspect, by="owner"))
    shaped = _work(service, "mnw:25", pooled=True)
    crops.apply(shaped, Cut(work=TRUE, aspect=aspect, shape="rectangle"))
    assert crops.reshaped() == 3
    assert crops.reshaped() == 0  # once
    fake.ended = True

    def results(batch_id: str) -> list[SimpleNamespace]:
        shapes = {"mnw:21": "round", "mnw:22": "irregular", "mnw:23": "rectangle"}
        ids = crops.state()["order"]["ids"]
        return [
            SimpleNamespace(
                custom_id=r["custom_id"],
                result=SimpleNamespace(
                    type="succeeded",
                    message=_message({"shape": shapes[ids[r["custom_id"]]], "note": ""}),
                ),
            )
            for r in fake.batches[batch_id]
        ]

    fake.messages.batches.results = results
    assert crops.order()
    asked = fake.batches["batch_1"]
    assert len(asked) == 3
    assert all(r["params"]["model"] == OPUS for r in asked)
    assert [b["type"] for b in asked[0]["params"]["messages"][0]["content"]] == ["image", "text"]
    assert crops.collect() is True

    for item_id, shape in (("mnw:21", "round"), ("mnw:22", "irregular")):
        item = service.library.get(item_id)
        assert item is not None and item.cut is not None
        assert item.cut.shape == shape and item.cut.by == "auto"
        assert item.cut_shown() is None and item.cut.undone == TRUE
        with Image.open(service.images.image_path(item)) as whole:
            assert whole.size == (W, H)
        assert not crops.now(item)  # never cut again by itself
    # His framing shows the same part of the photograph, now whole.
    detail = service.library.get("mnw:21").framing["portrait"].detail  # type: ignore[union-attr]
    assert detail is not None
    assert abs(detail.x - (TRUE[0][0] + face.x * (TRUE[2][0] - TRUE[0][0]))) < 0.01
    kept = service.library.get("mnw:23")
    assert kept is not None and kept.cut is not None and kept.cut.shape == "rectangle"
    assert kept.cut_shown() == TRUE
    for item_id in ("mnw:24", "mnw:25"):
        assert service.library.get(item_id).cut_shown() == TRUE  # type: ignore[union-attr]
    assert crops.written() == []
    assert not crops.order()


def test_a_card_asks_the_outline_of_a_work_cut_before(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    item = _work(service, "met:2", pooled=True)
    crops = service.crops
    item = crops.apply(item, Cut(work=TRUE, aspect=round(W / H, 5)))
    answers = iter([{"shape": "irregular", "note": "cut out along the drawing"}])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    assert crops.now(item)
    assert [p["model"] for p in fake.asked] == [OPUS]
    stored = service.library.get("met:2")
    assert stored is not None and stored.cut is not None and stored.cut_shown() is None
    assert not crops.now(stored)
    assert len(fake.asked) == 1


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


def test_a_prints_own_paper_margin_is_no_strip_of_board() -> None:
    # Jackson's chiaroscuro woodcut after Veronese (Europeana): the paper
    # runs off the photograph, its plain margin was cut away as board.
    plain = (0.05, 0.05, 0.05, 0.05)
    whole = {
        "layers": [
            {"kind": "sheet", "corners": grid([(0, 0), (1, 0), (1, 1), (0, 1)])},
            {
                "kind": "plate",
                "corners": grid([(0.06, 0.06), (0.94, 0.06), (0.94, 0.94), (0.06, 0.94)]),
            },
        ]
    }
    assert not strips_fit(plain, whole)
    assert not strips_fit(plain, {})  # nothing named: no telling
    # A plate the strips run into: its paper, not board.
    tight = {
        "layers": [
            {
                "kind": "plate",
                "corners": grid([(0.05, 0.05), (0.95, 0.05), (0.95, 0.95), (0.05, 0.95)]),
            }
        ]
    }
    assert not strips_fit(plain, tight)
    # Munch: the strips end on the sheet Opus named.
    assert strips_fit((0.013, 0.013, 0.012, 0.012), SHEET_CORNERS)
    # Only a plate named, all four sides plain and clear of it: board.
    inner = {
        "layers": [
            {"kind": "plate", "corners": grid([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])}
        ]
    }
    assert strips_fit(plain, inner)
    assert not strips_fit((0.05, 0.05, 0.0, 0.05), inner)


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


def test_a_lozenge_is_no_rectangle_at_an_angle() -> None:
    # Mondrian's Victory Boogie-Woogie (WikiArt) cut into an upright square.
    assert tilted([(0.5, 0.02), (0.98, 0.5), (0.5, 0.98), (0.02, 0.5)])
    assert not tilted([(0.1, 0.12), (0.9, 0.1), (0.92, 0.9), (0.08, 0.88)])


def test_cuts_from_the_strips_alone_go_back_to_opus_once(service: FrameService) -> None:
    quad = _box(9)
    item = _work(service, "eu:13", picture=sheet(), pooled=True)
    service.crops.apply(item, Cut(work=quad, around=["backdrop"], aspect=W / H))
    owners = _work(service, "eu:14", picture=sheet(), pooled=True)
    service.crops.apply(owners, Cut(work=quad, by="owner", aspect=W / H))
    crops = service.crops
    state = crops.state()
    state["written"] = [
        {"id": i, "at": "2026-11-15T20:00:00+00:00", "work": quad, "note": STRIPS_NOTE}
        for i in ("eu:13", "eu:14")
    ]
    crops._save(state)
    assert crops.strips_rechecked() == 1
    stored = service.library.get("eu:13")
    assert stored is not None and stored.cut is not None and stored.cut_shown() is None
    assert service.library.get("eu:14").cut.by == "owner"  # type: ignore[union-attr]
    assert crops.state()["claims"] == {"eu:13": {"around": ["backdrop"], "band": True}}
    assert crops.strips_rechecked() == 0  # once


# -- Erichsøe's etching among a colour chart and a ruler (SMK, 2026-11-16) ---------------


def test_a_sheet_under_a_colour_chart_shows_its_plate() -> None:
    plate = [(0.18, 0.09), (0.75, 0.08), (0.77, 0.93), (0.19, 0.93)]
    off = [(0.0, 0.01), (0.8, 0.0), (0.81, 1.0), (0.0, 1.0)]  # runs off left, top, bottom
    found = {"work": off, "plate": plate, "aspect": 0.667}
    assert plate_for_chart(found) == {"work": plate, "plate": None, "aspect": 0.667}
    assert plate_for_chart({**found, "work": None})["work"] == plate  # the photograph
    seen = [(0.05, 0.04), (0.95, 0.04), (0.95, 0.96), (0.05, 0.96)]  # its edges all show
    assert plate_for_chart({**found, "work": seen}) == {**found, "work": seen}
    assert plate_for_chart({"work": off, "plate": None}) == {"work": off, "plate": None}


def test_a_sheets_side_on_the_photographs_edge_stays_there() -> None:
    said = [(0.0, 0.0), (0.8, 0.0), (0.8, 1.0), (0.0, 1.0)]
    snapped = [(0.02, 0.013), (0.81, 0.0), (0.815, 0.98), (0.03, 0.99)]
    assert on_photo_edge(said, snapped) == [(0.0, 0.0), (0.81, 0.0), (0.815, 1.0), (0.0, 1.0)]


def test_a_card_asks_again_a_work_left_uncut_by_the_older_question(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    item = _work(service, "smk:15", pooled=True)
    crops = service.crops
    state = crops.state()  # Opus unsure of the sheet under the chart: nothing cut, never again
    state["asked"] = {
        "smk:15": {"v": 2, "at": "2026-11-12", "p": item.picture_key(), "critic": False, "band": 2}
    }
    crops._save(state)
    answers = iter([{"surround": []}])
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(next(answers)))[1]
    assert not crops.now(service.library.get("smk:15"))  # type: ignore[arg-type]
    assert [p["model"] for p in fake.asked] == [HAIKU]
    assert crops.asked()["smk:15"]["q"] == 2
    assert not crops.now(service.library.get("smk:15"))  # type: ignore[arg-type]
    assert len(fake.asked) == 1  # asked by this question: not again


def test_a_claim_is_asked_of_opus_now_on_demand(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    """Na żądanie (Mateusz 2026-11-17): the works the judge found something
    around are asked of Opus now, at the full price, and kept as the
    night's answers are."""
    _work(service, "mnw:1", title="Portret", pooled=True)
    crops = service.crops
    fake.ended = True
    _answer(fake, {"surround": ["backdrop", "frame"]})
    assert crops.order() and crops.collect()
    assert crops.claims_waiting() == ["mnw:1"]

    fake.answer = CORNERS  # asked now, not in a batch
    fake.asked.clear()
    assert crops.claim_now("mnw:1") is True
    assert [p["model"] for p in fake.asked] == [OPUS] and len(fake.batches) == 1
    item = service.library.get("mnw:1")
    assert item is not None and item.cut is not None and item.cut.by == "auto"
    assert crops.claims_waiting() == [] and crops.claim_now("mnw:1") is None
    assert crops.asked()["mnw:1"]["critic"] is True


# -- "W ramie" (Mateusz 2026-11-17) ------------------------------------------------------


def test_the_frames_edge_is_kept_with_the_cut_and_shown_set_straight(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    from frame_server.ai.crops import corners_in

    found = corners_in(photo(), CORNERS)
    assert found is not None and found["surround_kind"] == "frame"
    outer = [(150 / W, 100 / H), (750 / W, 100 / H), (750 / W, 600 / H), (150 / W, 600 / H)]
    assert _near(found["surround"], outer, 0.004)

    item = _work(service, "mnw:61", pooled=True)
    crops = service.crops
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(CORNERS))[1]
    item = crops.apply(item, Cut(work=TRUE, aspect=round(W / H, 5), around=["frame"]))
    assert item.cut is not None and item.cut.framed_kind == ""  # not asked yet
    assert crops.unsurrounded(item)
    # The card asks Opus for the frame's edge; the cut stays as it was.
    crops.now(item)
    stored = service.library.get("mnw:61")
    assert stored is not None and stored.cut is not None
    cut = stored.cut
    assert cut.surround_asked and cut.surround_kind == "frame" and cut.framed_kind == "frame"
    assert stored.cut_shown() == TRUE
    assert abs(cut.framed_aspect - 600 / 500) < 0.02
    x0, y0, x1, y1 = cut.framed_inner or (0, 0, 0, 0)
    assert abs(x0 - 30 / 600) < 0.01 and abs(y0 - 30 / 500) < 0.01
    assert abs(x1 - 570 / 600) < 0.01 and abs(y1 - 470 / 500) < 0.01
    assert not crops.unsurrounded(stored)
    asked = len(fake.asked)
    crops.now(stored)
    assert len(fake.asked) == asked  # once

    img = service.images.framed(stored, 4000)
    assert img is not None and abs(img.width / img.height - 600 / 500) < 0.02
    a = np.asarray(img.convert("RGB")).astype(int)
    assert abs(a[5, img.width // 2] - (200, 160, 60)).max() < 30  # the gilt frame


def test_a_work_drawn_by_the_restorer_keeps_its_frame(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
    monkeypatch: Any,
) -> None:
    """Mateusz 2026-11-18: "gdy do dzieła … dodałem restauratora, to obraz
    stracił ramę". The drawing is of the work alone; the frame comes from the
    museum's photograph, the drawing laid in it."""
    item = _work(service, "mnw:62", pooled=True)
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(CORNERS))[1]
    item = service.crops.apply(item, Cut(work=TRUE, aspect=round(W / H, 5), around=["frame"]))
    service.crops.now(item)
    stored = service.library.get("mnw:62")
    assert stored is not None and service.images.framed(stored, 4000) is not None

    museum = photo()
    monkeypatch.setattr(service.images, "sample", lambda url, urgent=False: museum.copy())
    x0, y0, x1, y1 = PAINTING
    drawing = Image.new("RGB", ((x1 - x0) * 2, (y1 - y0) * 2), (230, 40, 200))
    buf = io.BytesIO()
    drawing.save(buf, "JPEG", quality=95)
    service.sharper.bring(stored, buf.getvalue(), "Kreatywny restaurator", restored=True)
    drawn = service.library.get("mnw:62")
    assert drawn is not None and drawn.sharper is not None and drawn.sharper.restored
    assert drawn.cut is not None and drawn.cut.framed_kind == "frame"

    img = service.images.framed(drawn, 4000)
    assert img is not None and abs(img.width / img.height - 600 / 500) < 0.02
    a = np.asarray(img.convert("RGB")).astype(int)
    assert abs(a[5, img.width // 2] - (200, 160, 60)).max() < 30  # the gilt frame
    assert abs(a[img.height // 2, img.width // 2] - (230, 40, 200)).max() < 30  # the drawing


def test_a_print_shown_without_its_sheet_shows_the_sheet_around_it() -> None:
    sheet_quad = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    plate = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    cut = Cut(work=sheet_quad, plate=plate, paper=True, aspect=1.0)
    assert cut.framed_by() is None  # with its paper (kept from before): nothing around it
    bare = cut.model_copy(update={"paper": False})
    assert bare.framed_by() == (sheet_quad, "paper")
    from frame_server.ai.crops import framed

    made = framed(bare)
    assert made.framed_kind == "paper" and abs(made.framed_aspect - 1.0) < 0.01


def test_cuts_without_their_frames_edge_are_asked_once_at_night(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    crops = service.crops
    aspect = round(W / H, 5)
    for item_id, around in (("mnw:71", ["frame"]), ("mnw:72", ["backdrop"])):
        item = _work(service, item_id, pooled=True)
        crops.apply(item, Cut(work=TRUE, aspect=aspect, around=around, shape="rectangle"))
    assert crops.surrounded() == 1  # a backdrop alone has no frame to show
    assert crops.surrounded() == 0
    fake.ended = True
    _answer(fake, CORNERS)
    assert crops.order()
    assert crops.collect() is True
    framed_one = service.library.get("mnw:71")
    assert framed_one is not None and framed_one.cut is not None
    assert framed_one.cut.framed_kind == "frame" and framed_one.cut_shown() == TRUE
    assert crops.written() == []
    plain = service.library.get("mnw:72")
    assert plain is not None and plain.cut is not None and plain.cut.framed_kind == ""


# -- a print's margin like a frame (Mateusz 2026-11-18) ------------------------------------------

#: A print on its sheet on a grey board: the sheet and the plate, in px.
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


def test_a_print_with_only_its_paper_around_is_cut_to_its_plate_at_night(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "aic:1", picture=print_on_sheet(), pooled=True)
    crops = service.crops
    fake.ended = True
    _answer(fake, {"surround": ["paper_margin"]})
    assert crops.order() and crops.collect()
    assert crops.state()["claims"]["aic:1"]["around"] == ["paper_margin"]
    _answer(fake, PRINT_CORNERS)
    assert crops.order() and crops.collect()
    item = service.library.get("aic:1")
    assert item is not None and item.cut is not None and not item.cut.paper
    shown = item.cut_shown()
    assert shown is not None and _near(shown, _px(PLATE_BOX), 0.01)
    # The sheet is the card's "W ramie", as a frame would be.
    assert item.cut.framed_kind == "paper"
    framed = service.images.framed(item, 1800)
    assert framed is not None
    assert abs(framed.width / framed.height - 660 / 540) < 0.03


def test_the_plate_alone_on_a_sheet_filling_the_photograph_is_cut_to() -> None:
    plate = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    cut = Cut(work=None, plate=plate, aspect=1.0)
    assert cut.shown() == plate
    by = cut.framed_by()
    assert by is not None and by[1] == "paper" and by[0][2] == (1.0, 1.0)


def test_margins_kept_from_before_go_and_paper_alone_goes_to_opus_once(
    service: FrameService,
) -> None:
    crops = service.crops
    aspect = round(W / H, 5)
    kept = _work(service, "aic:2", picture=print_on_sheet(), pooled=True)
    crops.apply(
        kept,
        Cut(
            work=_px(SHEET_BOX),
            plate=_px(PLATE_BOX),
            paper=True,
            aspect=aspect,
            shape="rectangle",
        ),
    )
    assert service.library.get("aic:2").cut_shown() == _px(SHEET_BOX)  # type: ignore[union-attr]
    alone = _work(service, "aic:3", picture=print_on_sheet(), pooled=True)
    service.library.update(alone.id, cut=Cut(around=["paper_margin"]))
    given_up = _work(service, "aic:4", picture=print_on_sheet(), pooled=True)
    service.library.update(given_up.id, cut=Cut(around=["paper_margin"], by="owner"))

    assert crops.margins_off() == 2
    item = service.library.get("aic:2")
    assert item is not None and item.cut is not None and not item.cut.paper
    assert item.cut_shown() == _px(PLATE_BOX) and item.cut.framed_kind == "paper"
    with Image.open(service.images.image_path(item)) as img:
        assert abs(img.width / img.height - 420 / 330) < 0.05
    claims = crops.state()["claims"]
    assert claims == {"aic:3": {"around": ["paper_margin"], "sheet": True}}
    assert crops.margins_off() == 0  # once


def test_a_card_opened_shows_the_plate_and_asks_opus_for_one_once(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    crops = service.crops
    aspect = round(W / H, 5)
    kept = _work(service, "aic:5", picture=print_on_sheet(), pooled=True)
    crops.apply(
        kept,
        Cut(
            work=_px(SHEET_BOX),
            plate=_px(PLATE_BOX),
            paper=True,
            aspect=aspect,
            shape="rectangle",
        ),
    )
    assert crops.now(service.library.get("aic:5"))  # type: ignore[arg-type]
    assert service.library.get("aic:5").cut_shown() == _px(PLATE_BOX)  # type: ignore[union-attr]
    assert fake.asked == []  # nothing asked for that

    alone = _work(service, "aic:6", picture=print_on_sheet(), pooled=True)
    service.library.update(alone.id, cut=Cut(around=["paper_margin"]))
    state = crops.state()
    state["asked"] = {"aic:6": {"v": 2, "at": "2026-11-14", "p": "", "q": 2, "band": 2}}
    crops._save(state)
    fake.messages.create = lambda **params: (fake.asked.append(params), _message(PRINT_CORNERS))[1]
    assert crops.now(service.library.get("aic:6"))  # type: ignore[arg-type]
    assert [p["model"] for p in fake.asked] == [OPUS]  # straight to Opus
    item = service.library.get("aic:6")
    assert item is not None and item.cut is not None and item.cut.framed_kind == "paper"
    assert not crops.now(item)  # asked once
    assert len(fake.asked) == 1


def test_the_owner_sets_the_sheets_edge_as_a_frames(service: FrameService) -> None:
    crops = service.crops
    aspect = round(W / H, 5)
    item = _work(service, "aic:7", picture=print_on_sheet(), pooled=True)
    item = crops.apply(
        item, Cut(work=_px(SHEET_BOX), plate=_px(PLATE_BOX), aspect=aspect, shape="rectangle")
    )
    wider = _px((100, 60, 800, 640))
    item = crops.set_by_owner(item, frame=wider)
    assert item.cut is not None and item.cut.work == wider and item.cut.surround is None
    assert item.cut_shown() == _px(PLATE_BOX) and item.cut.framed_kind == "paper"
