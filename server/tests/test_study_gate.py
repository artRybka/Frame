"""Which works get no "Studium dzieła" (Mateusz 2026-11-13): the rules, the
sheet's pixels and Haiku for a pale sheet between them; a small picture is
drawn larger by the creative restorer first."""

from __future__ import annotations

import io
import threading
from datetime import date
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from test_ai import GOOD_KEY, FakeAnthropic
from test_daily import ANSWER_PX, _app, _catalogue, _like
from test_sheet import PRINT

from frame_server.ai import AiConfigUpdate, study_fit
from frame_server.ai.client import Answer
from frame_server.ai.composition import draft, plate_of, question
from frame_server.ai.daily import Box
from frame_server.library import Item, ItemKind
from frame_server.library import paper as sheet
from frame_server.library.verdict import Place, Why, against
from frame_server.service import FrameService
from frame_server.study_gate import EMPTY, SCATTERED, StudyGate

PAPER = (243, 238, 226)
INK = (70, 64, 58)


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _empty_sheet() -> Image.Image:
    """Church's "Dyliżans": one small sketch in a corner of a large page."""
    img = Image.new("RGB", (600, 840), PAPER)
    draw = ImageDraw.Draw(img)
    for k in range(12):
        draw.line((120 + 6 * k, 140, 150 + 5 * k, 260), fill=INK, width=2)
    return img


def _scattered() -> Image.Image:
    """Church's Betesda: faint figures and notes scattered over the sheet."""
    img = Image.new("RGB", (900, 560), PAPER)
    draw = ImageDraw.Draw(img)
    for x, y in [(80, 70), (330, 90), (620, 60), (760, 300), (120, 380), (480, 430), (560, 220)]:
        draw.line((x, y, x + 14, y + 34), fill=INK, width=1)
        draw.line((x + 14, y, x, y + 34), fill=INK, width=1)
    return img


def _portrait() -> Image.Image:
    """A finished portrait drawing: pale, but one figure over the sheet."""
    img = Image.new("RGB", (600, 800), PAPER)
    draw = ImageDraw.Draw(img)
    draw.ellipse((230, 120, 370, 290), outline=INK, width=2)
    for k in range(9):
        draw.line((180 + 25 * k, 300, 150 + 35 * k, 720), fill=INK, width=2)
    return img


def _print_on_sheet() -> Image.Image:
    """Lucas's mezzotint: a dark plate in the middle of a wide margin."""
    img = Image.new("RGB", (900, 620), PAPER)
    plate = Image.effect_noise((480, 260), 60).convert("RGB")
    plate = Image.eval(plate, lambda v: v // 3)
    img.paste(plate, (210, 130))
    ImageDraw.Draw(img).text((380, 420), "AUTUMNAL SUN SET", fill=INK)
    return img


def test_the_sheet_tells_the_extremes() -> None:
    empty = sheet.read(_empty_sheet())
    assert empty is not None and empty.empty and not empty.scattered
    scattered = sheet.read(_scattered())
    assert scattered is not None and scattered.scattered and not scattered.empty
    portrait = sheet.read(_portrait())
    assert portrait is not None and portrait.pale
    assert not portrait.empty and not portrait.scattered and portrait.plate is None
    painted = Image.effect_noise((400, 300), 80).convert("RGB")
    assert sheet.read(Image.eval(painted, lambda v: v // 2)) is None  # no light sheet


def test_a_print_in_a_wide_margin_has_its_plate() -> None:
    found = sheet.read(_print_on_sheet())
    assert found is not None and found.plate is not None
    assert not found.empty and not found.scattered
    x, y, w, h = found.plate
    assert abs(x - 210 / 900) < 0.02 and abs(y - 130 / 620) < 0.02
    assert abs(w - 480 / 900) < 0.03 and abs(h - 260 / 620) < 0.03


def _work(service: FrameService, item_id: str, img: Image.Image, **fields: Any) -> Item:
    item = Item(
        id=item_id,
        kind=ItemKind.ARTWORK,
        source=item_id.split(":")[0],
        source_id=item_id.split(":")[1],
        title=fields.pop("title", "Untitled"),
        artist="Frederic Edwin Church",
        year=1869,
        classification=fields.pop("classification", "Drawing"),
        medium="Graphite on paper",
        thumb_url=f"https://example.org/{item_id}/thumb.jpg",
        image_url=f"https://example.org/{item_id}/image.jpg",
        width=fields.pop("width", 3000),
        height=fields.pop("height", 2000),
        **fields,
    )
    stored = service.library.upsert(item)
    path = service.images.thumb_path(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_jpeg(img))
    return stored


class FakeClaude:
    def __init__(self, fit: bool, why: str = "kartka roboczych szkiców") -> None:
        self.fit, self.why = fit, why
        self.asked: list[str] = []

    def ask(self, kind: str, params: dict[str, Any], on_text: Any = None) -> Answer:
        self.asked.append(kind)
        assert params["model"] == study_fit.MODEL
        return Answer({"what": "a sheet", "fit": self.fit, "why": self.why}, False, 0.0008, "h")


def _gate(service: FrameService, claude: FakeClaude | None) -> StudyGate:
    gate = StudyGate(service.library, service.images, claude, lambda: True)  # type: ignore[arg-type]
    service.study.gate = gate
    return gate


def test_the_rules_set_aside_sketchbooks_designs_and_photographs(service: FrameService) -> None:
    gate = _gate(service, FakeClaude(True))
    blank = Image.new("RGB", (400, 300), (90, 60, 40))
    sheet_ = _work(service, "aic:1", blank, title="Various Studies near the Pool of Bethesda")
    book = _work(service, "aic:2", blank, classification="sketchbook")
    album = _work(service, "aic:3", blank, classification="album/sketchbook", title="Shôki")
    plan = _work(service, "aic:4", blank, classification="Architectural drawing")
    wallpaper = _work(service, "met:5", blank, title="Design for a Wallpaper", classification="")
    study = _work(service, "met:6", blank, title="Study of a Head", classification="Painting")
    assert against(sheet_, Place.STUDIED) == (Why.SKETCHES,)
    assert gate.why_not(sheet_) == "kartka szkiców albo notatek"
    assert against(book, Place.STUDIED) == (Why.SKETCHES,)
    assert against(album, Place.STUDIED) == ()
    assert gate.why_not(plan) == gate.why_not(wallpaper) == "projekt, plan albo rysunek techniczny"
    assert gate.why_not(study) is None  # an oil study may be worth a page
    photo = sheet_.model_copy(update={"id": "upload:1", "kind": ItemKind.PHOTO, "title": "Kot"})
    assert gate.why_not(photo) == "własne zdjęcie"
    # Shown and proposed as before: the reasons are the study's alone.
    for place in Place:
        if place is not Place.STUDIED:
            assert Why.SKETCHES not in against(sheet_, place)


def test_the_pixels_set_aside_an_empty_page_and_scattered_notes(service: FrameService) -> None:
    claude = FakeClaude(True)
    gate = _gate(service, claude)
    empty = _work(service, "cooperhewitt:1", _empty_sheet(), title="Stagecoach, Pompeii, Italy")
    notes = _work(service, "cooperhewitt:2", _scattered(), title="Jerusalem")
    assert gate.why_not(empty, ask=True) == EMPTY
    assert gate.why_not(notes, ask=True) == SCATTERED
    assert claude.asked == []  # free
    assert gate.unfit() == {empty.id, notes.id}
    assert service.study.status(empty) == ("off", EMPTY)


def test_haiku_judges_a_pale_sheet_between_them_once(service: FrameService) -> None:
    claude = FakeClaude(False, "kartka roboczych szkiców z notatkami")
    gate = _gate(service, claude)
    pale = _work(service, "aic:7", _portrait(), title="Figures")
    # Opening the card's lists asks nothing; the card itself asks once.
    assert gate.why_not(pale) is None and claude.asked == []
    assert gate.why_not(pale, ask=True) == "kartka roboczych szkiców z notatkami"
    assert gate.why_not(pale, ask=True) == "kartka roboczych szkiców z notatkami"
    assert claude.asked == [study_fit.KIND]
    # Never the study of the day either.
    service.daily.study_unfit = gate.unfit
    assert pale.id not in {i.id for i in service.daily.pool(date(2026, 11, 13), [])}

    fine = FakeClaude(True, "skończony portret")
    gate = _gate(service, fine)
    ingres = _work(service, "aic:8", _portrait(), title="Charles Gounod")
    assert gate.why_not(ingres, ask=True) is None
    assert gate.why_not(ingres, ask=True) is None and fine.asked == [study_fit.KIND]
    # A painting is no question at all.
    painted = Image.eval(Image.effect_noise((400, 300), 80).convert("RGB"), lambda v: v // 2)
    oil = _work(service, "aic:9", painted, classification="Painting", title="Cotopaxi")
    assert gate.why_not(oil, ask=True) is None and fine.asked == [study_fit.KIND]


def test_what_the_curator_set_aside_has_no_study(service: FrameService) -> None:
    gate = StudyGate(
        service.library, service.images, None, lambda: True, lambda: {"aic:10": "notes"}
    )
    item = _work(service, "aic:10", _portrait(), title="Figures")
    assert gate.why_not(item, ask=True) == "notes"


def test_the_card_has_no_button_and_the_server_takes_no_order(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False, daily=False))
    with TestClient(app) as client:
        _catalogue(svc)
        sheet_ = _work(svc, "aic:11", _scattered(), title="Sheet of Studies")
        empty = _work(svc, "aic:12", _empty_sheet(), title="Stagecoach")
        for item in (sheet_, empty):
            view = client.get(f"/api/study/{item.id}").json()
            assert view["status"] == "off", view
            resp = client.post(f"/api/study/{item.id}")
            assert resp.status_code == 409 and "nie dostaje studium" in resp.json()["detail"]
        assert client.get("/api/study/met:1").json()["status"] == "none"


def test_a_print_is_analysed_on_its_plate(service: FrameService) -> None:
    item = _work(service, "aic:122071", _print_on_sheet(), title="Autumnal Sun Set")
    service.images.image_path(item).parent.mkdir(parents=True, exist_ok=True)
    service.images.image_path(item).write_bytes(_jpeg(_print_on_sheet()))
    plate = plate_of(service.images, item)
    assert plate is not None and abs(plate.x - 210 / 900) < 0.02
    # Opus saw no field (Lucas's, 2026-11-13): the plate the pixels found is.
    _catalogue(service)
    met = service.library.get("met:1")
    assert met is not None
    params = question(service.images, met, service.daily.job.sources(met))
    view = {k: v for k, v in PRINT["composition"]["views"][0].items() if k != "pole"}
    answer = {"composition": {"views": [view]}}
    box = Box(x=0.1, y=0.1, w=0.8, h=0.6)
    found = draft(answer, params, box)
    assert found is not None and found.field == box
    # In the field the horizon runs from edge to edge through its middle.
    assert [(round(p.x, 3), round(p.y, 3)) for p in found.view.marks[0].points] == [
        (0, 0.5),
        (1, 0.5),
    ]
    whole = draft(answer, params)
    assert whole is not None and whole.field is None
    # A field the answer gives stands.
    told = draft(PRINT, params, Box(x=0.3, y=0.3, w=0.2, h=0.2))
    assert told is not None and told.field == box


def test_a_small_picture_is_drawn_larger_before_its_study(tmp_path: Path) -> None:
    from test_restorer import FakePainter

    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = ANSWER_PX
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False, daily=False))
    painter = FakePainter()
    svc.painter = painter  # type: ignore[assignment]
    svc.restorer.painter = painter  # type: ignore[assignment]
    with TestClient(app) as client:
        _catalogue(svc)
        _like(svc)
        picture = Image.eval(Image.effect_noise((900, 640), 60).convert("RGB"), lambda v: v // 2)
        small = _work(svc, "aic:20", picture, classification="Painting", width=900, height=640)
        svc.images.image_path(small).parent.mkdir(parents=True, exist_ok=True)
        svc.images.image_path(small).write_bytes(_jpeg(picture))
        drawn = threading.Event()
        parts: list[str] = []
        real = svc.restorer.restore

        def restore(item: Item) -> Item:
            assert svc.study.job.stages.get(item.id) == "restoring"
            out = real(item)
            drawn.set()
            return out

        svc.restorer.restore = restore  # type: ignore[method-assign]

        def step(item: Any, status: str, error: str) -> None:
            progress = svc.study.progress(item.id)
            parts.append(progress.part if progress else status)

        svc.study.on_step = step
        svc.ai.start()
        try:
            client.post("/api/study/aic:20")
            assert drawn.wait(10)
            for _ in range(200):
                if client.get("/api/study/aic:20?wait=1").json()["status"] in ("ready", "failed"):
                    break
        finally:
            svc.ai.stop()
        assert painter.asked == [("restorer", "2K")]
        assert parts[0] == "restoring" and "sources" in parts
        restored = svc.library.get("aic:20")
        assert restored is not None and restored.sharper is not None and restored.sharper.restored
        # A large picture goes straight to its study.
        assert not svc.study._restorable(svc.library.get("met:3"))  # type: ignore[arg-type]
