"""Museum photographs cut down to the work in them (Mateusz 2026-11-14):
the corners set on the picture's edges, the cut kept beside the museum's
photograph, Haiku picking the works and Opus placing the corners, at night
and when a card opens, and the owner's correction, paper switch and
restore."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
from test_ai import FakeAnthropic, _message, fake  # noqa: F401  (fixture)

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU, OPUS
from frame_server.ai.crops import read_layers
from frame_server.imaging.cut import snap, valid, warp, worth_cutting
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
    "confident": True,
    "note": "A painting in a gilt frame on a grey board",
}


def _work(service: FrameService, item_id: str, **fields: Any) -> Item:
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
    img = photo()
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
        corners = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        put = client.put("/api/library/items/mnw:7/cut", json={"corners": corners})
        assert put.status_code == 200, put.text
        assert put.json()["cut"]["by"] == "owner"
        assert put.json()["cut"]["work"][0] == [0.1, 0.1]
        bad = client.put("/api/library/items/mnw:7/cut", json={"corners": corners[:3]})
        assert bad.status_code == 422

        gone = client.delete("/api/library/items/mnw:7/cut").json()
        assert gone["cut"]["work"] is None and gone["cut"]["by"] == "owner"
    item = service.library.get("mnw:7")
    assert item is not None and item.cut_shown() is None
    assert not service.images.full_path(item).exists()
    with Image.open(service.images.image_path(item)) as whole:
        assert whole.size == (W, H)  # the museum's photograph again
    assert not service.crops.now(item)  # never cut again by itself


def test_a_cut_of_another_picture_is_never_applied(service: FrameService) -> None:
    item = _work(service, "mnw:3", pooled=True)
    cut = Cut(work=TRUE, aspect=W / H, picture="other:1", at="2026-11-14T10:00:00+00:00")
    item = service.library.update("mnw:3", cut=cut) or item
    assert item.cut_shown() is None and item.cut_version() == ""
    service.images.recut(item)
    with Image.open(service.images.image_path(item)) as kept:
        assert kept.size == (W, H)
