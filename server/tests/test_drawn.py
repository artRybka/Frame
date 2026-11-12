"""The study sheet drawn by the image model (``ai.drawn``, ``drawn``).

Mateusz 2026-11-12 22:14: "Jest świetnie. Wdrażamy." The model here is a
stand-in that draws what it is asked for with PIL: nothing is asked of
Google.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter
from test_composition import _old_page
from test_daily import _app, _catalogue

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import AiUnavailable
from frame_server.ai.daily import CHECK_ROUND, ROUND, Box, Mark, Spot, View
from frame_server.ai.drawn import (
    AT_ONCE,
    KIND,
    LINES,
    SPILL,
    UNDERLAY,
    draw,
    focus,
    lines_prompt,
    said,
)
from frame_server.ai.gemini import MODEL, URL, Ask, GeminiRejected, NoCredit, NotDrawn, Painter
from frame_server.ai.jobs import listed
from frame_server.ai.redraw import PenJob
from frame_server.drawn import KEY_REJECTED, LIMIT, NO_CREDIT, SINCE, DrawnSheets
from frame_server.imaging import drawn as imaging
from frame_server.imaging.sheet import BLEED, LONG, PAGE, bleed
from frame_server.service import FrameService

GOOGLE_KEY = "AIza-test-key-wxyz"


def _scene(size: tuple[int, int] = (900, 600)) -> Image.Image:
    """A boat on water under a sky with a sun: things to lay a study on."""
    img = Image.new("RGB", size, (150, 185, 215))
    canvas = ImageDraw.Draw(img)
    w, h = size
    canvas.rectangle((0, h * 0.55, w, h), fill=(60, 95, 130))
    canvas.ellipse((w * 0.68, h * 0.12, w * 0.8, h * 0.3), fill=(250, 225, 150))
    canvas.polygon(
        [(w * 0.25, h * 0.6), (w * 0.55, h * 0.6), (w * 0.5, h * 0.72), (w * 0.3, h * 0.72)],
        fill=(90, 50, 35),
    )
    canvas.polygon([(w * 0.4, h * 0.2), (w * 0.4, h * 0.58), (w * 0.54, h * 0.58)], fill="white")
    canvas.rectangle((w * 0.05, h * 0.4, w * 0.18, h * 0.55), fill=(70, 110, 60))
    return img.filter(ImageFilter.GaussianBlur(1.2))


def _spots(*points: tuple[float, float]) -> list[Spot]:
    return [Spot(x=x, y=y) for x, y in points]


def _take() -> View:
    return View(
        title="Układ",
        text="Żagiel jest dominantą. Horyzont dzieli obraz.",
        marks=[
            Mark(
                shape="triangle",
                points=_spots((0.4, 0.2), (0.4, 0.58), (0.54, 0.58)),
                title="Żagiel",
                text="dominanta",
            ),
            Mark(
                shape="line",
                points=_spots((0.02, 0.55), (0.98, 0.55)),
                title="Horyzont",
                text="dzieli obraz",
            ),
            # no title: not the model's
            Mark(shape="line", points=_spots((0.1, 0.9), (0.9, 0.9)), title=""),
            Mark(
                shape="loop",
                points=_spots((0.74, 0.21), (0.82, 0.32)),
                title="Słońce",
                text="akcent",
            ),
        ],
    )


class Stand:
    """The model's stand-in: a paler copy of the picture as its study (a
    little smaller and shifted, as the model's are), the marks drawn where
    the question says with the pencils it names, a stain let out to the
    left margin."""

    def __init__(
        self, view: View, leave_out: int | None = None, far: bool = False, always: bool = False
    ) -> None:
        self.always = always
        self.view = view
        self.leave_out = leave_out
        self.far = far
        self.asked: list[str] = []

    def __call__(self, prompt: str, pictures: Any) -> tuple[Image.Image, float]:
        picture = pictures[0]
        if prompt.startswith(UNDERLAY[:40]):
            self.asked.append("underlay")
            k = 1024 / max(picture.size)
            small = picture.resize((round(picture.width * k), round(picture.height * k)))
            paper = Image.new("RGB", small.size, PAGE[False])
            study = Image.blend(small, paper, 0.45)
            if self.far:  # another framing altogether
                study = study.crop((0, 0, study.width // 2, study.height // 2)).resize(small.size)
                return study.transpose(Image.Transpose.FLIP_LEFT_RIGHT), 0.05
            return study.transform(
                study.size, Image.Transform.AFFINE, (1.01, 0, 3, 0, 1.01, -2)
            ), 0.05
        if prompt == SPILL:
            self.asked.append("spill")
            out = picture.copy()
            m = (picture.width - round(picture.width / (1 + 2 * 0.06))) // 2
            ImageDraw.Draw(out).ellipse(
                (-m, picture.height * 0.6, m * 3, picture.height * 0.8), fill=(120, 150, 180)
            )
            return out.filter(ImageFilter.GaussianBlur(3)), 0.043
        self.asked.append("lines")
        colours = re.findall(r"pencil \((#[0-9a-fA-F]{6})\)", prompt)
        marks = [m for m in self.view.marks if m.title]
        assert len(colours) == len(marks)
        out = picture.copy()
        canvas = ImageDraw.Draw(out)
        w, h = out.size
        for n, (mark, colour) in enumerate(zip(marks, colours, strict=True)):
            if n == self.leave_out and (self.always or self.asked.count("lines") == 1):
                continue
            pts = [(p.x * w, p.y * h) for p in mark.points]
            if mark.shape == "loop":
                (cx, cy), (kx, ky) = pts
                rx, ry = abs(kx - cx), abs(ky - cy)
                canvas.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=colour, width=6)
            elif mark.shape == "triangle":
                canvas.line([*pts, pts[0]], fill=colour, width=6)
            else:
                canvas.line(pts, fill=colour, width=6)
        return out, 0.052


def test_the_model_is_asked_three_things_and_the_sheet_is_taken_apart() -> None:
    """21:29: "Model rysuje sam, z opisu"; 21:59: coloured lines "absolutnie
    muszą zostać"; "wyjścia szkicem i akwarelą … do krawędzi ekranu"."""
    view = _take()
    stand = Stand(view)
    sheet = draw(_scene(), view, stand, seed=3)
    assert stand.asked == ["underlay", "lines", "spill"]
    assert sheet.cost == {"underlay": 0.05, "lines": 0.052, "spill": 0.043}
    # The page: the field, the sheet's long side long, with the margin on each side.
    assert sheet.size == (LONG, LONG * 2 // 3)
    page = Image.open(io.BytesIO(sheet.page))
    assert page.size == (LONG + 2 * bleed(LONG), sheet.size[1])
    rgb = np.asarray(page.convert("RGB"), np.int16)
    paper = np.array(PAGE[False], np.int16)
    m = bleed(LONG)
    # Its right margin is bare paper, its left one holds what ran out.
    assert np.abs(rgb[:, -m // 2 :] - paper).max() <= 6
    stain = np.abs(rgb[int(sheet.size[1] * 0.65) : int(sheet.size[1] * 0.75), : m // 2] - paper)
    assert stain.sum(axis=2).mean() > 40
    assert np.abs(rgb[: sheet.size[1] // 3, : m // 2] - paper).max() <= 6
    # The study lies where the work does: the sail's white, the hull's brown.
    at = lambda x, y: rgb[int(y * sheet.size[1]), m + int(x * LONG)]  # noqa: E731
    assert at(0.44, 0.5).min() > 225 and at(0.4, 0.66)[0] > at(0.4, 0.66)[2] + 20
    # A line for each titled mark, in a pencil of its own, where the mark lies.
    assert len(sheet.layers) == 3 and all(sheet.layers)
    assert len(set(sheet.colours)) == 3
    for layer, mark in zip(
        sheet.layers, [view.marks[0], view.marks[1], view.marks[3]], strict=True
    ):
        assert layer is not None
        img = Image.open(io.BytesIO(layer))
        assert img.mode == "RGBA" and img.size == sheet.size
        *rgb, alpha = (np.asarray(band) for band in img.split())
        assert max(band.max() for band in rgb) == 0  # as much black as there is pencil
        ys, xs = np.nonzero(alpha > 120)
        assert len(xs) > 300
        if mark.title == "Horyzont":
            assert abs(np.median(ys) / sheet.size[1] - 0.55) < 0.02
            assert xs.min() < 0.1 * LONG and xs.max() > 0.9 * LONG
        elif mark.title == "Słońce":
            assert xs.min() / LONG > 0.62 and xs.max() / LONG < 0.86
            assert ys.max() / sheet.size[1] < 0.36
        else:
            assert xs.min() / LONG > 0.36 and xs.max() / LONG < 0.58
    # Each number stands on its own line.
    assert [len(spots) for spots in sheet.numbers] == [1, 1, 1]
    for layer, [(x, y)] in zip(sheet.layers, sheet.numbers, strict=True):
        assert layer is not None
        alpha = np.asarray(Image.open(io.BytesIO(layer)).split()[3])
        px, py = round(x * sheet.size[0]), round(y * sheet.size[1])
        assert alpha[max(py - 6, 0) : py + 7, max(px - 6, 0) : px + 7].max() > 120
    # Another take of the work (23:20: "gdy zamawiam ponowną analizę, a podkład
    # od Gemini już jest, to rób nim tylko kolorowe kreski"): over the study it
    # has, its lines alone are asked for, and its page is the same one.
    assert sheet.under is not None and sheet.under.spilt is not None
    other = view.model_copy(update={"marks": view.marks[1:2]})
    again = Stand(other)
    anew = draw(_scene(), other, again, seed=3, under=sheet.under)
    assert again.asked == ["lines"] and anew.cost == {"lines": 0.052}
    assert anew.page == sheet.page and anew.under is sheet.under
    assert len(anew.layers) == 1 and anew.layers[0] is not None
    # A take without a mark to draw costs nothing more.
    bare = view.model_copy(update={"marks": []})
    free = draw(_scene(), bare, again, seed=3, under=sheet.under)
    assert again.asked == ["lines"] and free.cost == {} and free.page == sheet.page


def test_a_mark_left_out_is_asked_for_once_more_and_a_strange_study_is_refused() -> None:
    view = _take()
    stand = Stand(view, leave_out=1)
    sheet = draw(_scene(), view, stand)
    assert stand.asked == ["underlay", "lines", "lines", "spill"]
    assert all(sheet.layers) and sheet.cost["lines"] == 0.104
    # Left out both times: the sheet goes without that line (the app draws it).
    stand = Stand(view, leave_out=1, always=True)
    sheet = draw(_scene(), view, stand)
    assert stand.asked == ["underlay", "lines", "lines", "spill"]
    assert [layer is not None for layer in sheet.layers] == [True, False, True]
    # A study that is not the work's framing is asked for again, then given up.
    stand = Stand(view, far=True)
    with pytest.raises(NotDrawn):
        draw(_scene(), view, stand)
    assert stand.asked == ["underlay", "underlay"]

    # A spill that cannot be had is left out; the sheet is paid for.
    def no_spill(prompt: str, pictures: Any) -> tuple[Image.Image, float]:
        if prompt == SPILL:
            raise NotDrawn("no picture")
        return Stand(view)(prompt, pictures)

    sheet = draw(_scene(), view, no_spill)
    rgb = np.asarray(Image.open(io.BytesIO(sheet.page)).convert("RGB"), np.int16)
    m = bleed(LONG)
    assert np.abs(rgb[:, : m // 2] - np.array(PAGE[False], np.int16)).max() <= 6
    assert "spill" not in sheet.cost


def test_what_the_model_is_told() -> None:
    view = _take()
    assert focus(view) == "„Żagiel”; „Słońce”"
    marks = [m for m in view.marks if m.title]
    assert said(marks[0]) == "TRIANGLE with its corners at (40, 20), (40, 58), (54, 58)"
    assert said(marks[2]).startswith("LOOP round what lies between 66 and 82 across")
    prompt = lines_prompt(marks, imaging.PENCILS[:3], view.text)
    assert "1. BLUE pencil (#2446B4). „Żagiel” (dominanta): TRIANGLE" in prompt
    assert view.text in prompt and "{MARKS}" not in prompt and "{TEXT}" not in prompt
    # Nothing is written on the sheet: the numbers and notes are the app's.
    assert "NOTHING IS WRITTEN" in LINES and "{FOCUS}" in UNDERLAY


class FakeGoogle:
    """Google's side: what it was asked, and what it answers."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.posts: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []

    def __enter__(self) -> FakeGoogle:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, url: str, headers: dict[str, str], params: Any = None) -> Any:
        import httpx

        status = 200 if headers["x-goog-api-key"] == GOOGLE_KEY else 400
        return httpx.Response(status, json={}, request=httpx.Request("GET", url))

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
        import httpx

        assert url == URL
        self.posts.append(json)
        self.headers.append(headers)
        out = io.BytesIO()
        Image.new("RGB", (64, 48), (10, 200, 30)).save(out, "PNG")
        body = {
            "outputs": [{"type": "image", "data": base64.b64encode(out.getvalue()).decode()}],
            "usage": {
                "total_input_tokens": 2000,
                "total_output_tokens": 1320,
                "total_thought_tokens": 100,
                "output_tokens_by_modality": [{"modality": "image", "tokens": 1120}],
            },
        }
        return httpx.Response(self.status, json=body, request=httpx.Request("POST", url))


def test_the_painter_asks_google_and_counts_what_it_cost(service: FrameService) -> None:
    google = FakeGoogle()
    painter = Painter(service.ai_config, service.claude, http=lambda: google)
    assert not painter.enabled()
    with pytest.raises(AiUnavailable):
        painter.paint(KIND, "draw", [_scene((90, 60))])
    assert google.posts == []
    with pytest.raises(GeminiRejected):
        painter.check_key("wrong")
    painter.check_key(GOOGLE_KEY)
    service.ai_config.set_gemini_key(f" {GOOGLE_KEY}\n")
    assert painter.enabled() and service.ai_config.gemini_tail == "wxyz"
    img, usd = painter.paint(KIND, "draw", [_scene((90, 60))], size="2K")
    assert img.size == (64, 48) and img.getpixel((5, 5)) == (10, 200, 30)
    # 2000 in at 1.50, 300 of text and thought at 7.50, a picture of 1120 at 30, per million.
    assert usd == round((2000 * 1.5 + 300 * 7.5 + 1120 * 30) / 1e6, 4)
    asked = google.posts[0]
    assert asked["model"] == MODEL == "gemini-nano-banana-2.1"
    assert asked["response_format"] == {"type": "image", "image_size": "2K"}
    assert [part["type"] for part in asked["input"]] == ["text", "image"]
    assert google.headers[0]["x-goog-api-key"] == GOOGLE_KEY
    # Counted as its own kind in the image model's own month, apart from
    # Claude's, and under a limit of its own.
    assert service.painter.spending.by_kind() == {KIND: usd}
    assert service.claude.spending.by_kind() == {}
    assert painter.budget_left() == pytest.approx(5.0 - usd)
    service.ai_config.update(AiConfigUpdate(monthly_limit_usd=0))  # Claude's: not this model's
    painter.check_budget()
    service.ai_config.update(AiConfigUpdate(monthly_limit_usd=5))
    service.ai_config.update(AiConfigUpdate(gemini_monthly_limit_usd=usd / 2))
    with pytest.raises(AiUnavailable):
        painter.paint(KIND, "draw", [])
    assert len(google.posts) == 1
    service.ai_config.update(AiConfigUpdate(gemini_monthly_limit_usd=10))
    for status, error in ((402, NoCredit), (403, GeminiRejected), (400, NotDrawn)):
        google.status = status
        with pytest.raises(error):
            painter.paint(KIND, "draw", [])
    assert service.painter.spending.by_kind() == {KIND: usd}  # nothing had: nothing spent


class Stood:
    """The stand-in in the model's place in a running server: asked at once
    (``paint``) and through the Batch, whose answers come when it is
    ``ready``."""

    def __init__(self, svc: FrameService) -> None:
        self.svc = svc
        self.calls: list[str] = []
        self.batches: list[list[Ask]] = []
        self.ready = False
        self.refuse = ""  # the names' ending the model will not draw
        svc.ai_config.set_gemini_key(GOOGLE_KEY)
        svc.painter.paint = self.paint  # type: ignore[method-assign]
        svc.painter.batch = self.batch  # type: ignore[method-assign]
        svc.painter.batched = self.batched  # type: ignore[method-assign]

    def _stand(self) -> Stand:
        return Stand(_shown(self.svc).inside())

    def paint(self, kind: str, prompt: str, pictures: Any, size: str = "1K") -> Any:
        self.calls.append(kind)
        return self._stand()(prompt, pictures)

    def batch(self, kind: str, asks: Any) -> str:
        assert kind == KIND
        self.batches.append(list(asks))
        return f"batches/{len(self.batches)}"

    def batched(self, kind: str, batch: str) -> Any:
        if not self.ready:
            return None
        asks = self.batches[int(batch.rsplit("/", 1)[1]) - 1]
        answers: dict[str, Any] = {}
        for ask in asks:
            if self.refuse and ask.name.endswith(self.refuse):
                answers[ask.name] = NotDrawn("Google answered 400", "image_recitation")
            else:
                picture, usd = self._stand()(ask.prompt, ask.pictures)
                answers[ask.name] = (picture, round(usd / 2, 4))
        return answers


def _shown(svc: FrameService) -> View:
    item = svc.library.get("met:1")
    assert item is not None
    view = svc.sheets.view(item)
    assert view is not None
    return view


def _step(svc: FrameService) -> bool:
    """A step of the background, the batch looked at whenever it is taken."""
    svc.drawn._looked = 0.0
    return svc.drawn.ahead()


def test_a_new_pages_sheet_is_drawn_at_once_and_the_app_gets_it(tmp_path: Path) -> None:
    """Mateusz 2026-11-12 22:32: "Nowe od razu"."""
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        _catalogue(svc)
        # Without Google's key nothing changes: the server's own sheet.
        view = client.get("/api/ai").json()
        assert view["gemini_key_set"] is False and view["drawn"] is True
        assert view["drawn_usd"] == 0.15 and view["drawn_batch_usd"] == 0.075
        assert svc.drawn.ahead() is False

        stood = Stood(svc)
        assert svc.drawn.at_once() == [] and svc.drawn.ahead() is False
        _old_page(svc)  # written after the sheets began to be drawn: a new page
        work = client.get("/api/study/met:1").json()["work"]
        assert work["composition_drawn"] is None and work["composition_drawn_pending"] is True
        assert work["composition_sheet"]  # shown meanwhile
        assert [item.id for item, _ in svc.drawn.at_once()] == ["met:1"]
        assert svc.drawn.saved() == [] and stood.batches == []
        assert svc.drawn.ahead() is True
        assert stood.calls == [KIND] * 3 and svc.drawn.at_once() == []

        work = client.get("/api/study/met:1").json()["work"]
        sheet = work["composition_drawn"]
        assert work["composition_drawn_pending"] is False and work["composition_sheet"]
        assert sheet["bleed"] == BLEED and abs(sheet["aspect"] - 1.5) < 0.01
        got = client.get(sheet["sheet"])
        assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
        assert "max-age" in got.headers["cache-control"]
        page = Image.open(io.BytesIO(got.content))
        assert page.size == (LONG + 2 * bleed(LONG), LONG * 2 // 3)
        # Its marks: which of the take's each is, its colour, its line, its number.
        shown = _shown(svc)
        titled = [n for n, m in enumerate(shown.marks) if m.title]
        assert [m["mark"] for m in sheet["marks"]] == titled and titled
        for mark in sheet["marks"]:
            assert re.fullmatch(r"#[0-9a-f]{6}", mark["colour"])
            line = client.get(mark["layer"])
            assert line.headers["content-type"] == "image/png"
            assert Image.open(io.BytesIO(line.content)).size == (LONG, LONG * 2 // 3)
            assert mark["numbers"] and all(
                0 <= at["x"] <= 1 and 0 <= at["y"] <= 1 for at in mark["numbers"]
            )
        assert len({m["colour"] for m in sheet["marks"]}) == len(titled)
        # Kept: nothing more is drawn, nor asked of Google, a restart or not.
        assert svc.drawn.ahead() is False and stood.calls == [KIND] * 3
        again = DrawnSheets(svc.library, svc.images, svc.painter)
        item = svc.library.get("met:1")
        assert item is not None and again.meta(item, shown) is not None
        assert again.ahead() is False
        assert client.get("/api/composition/drawn?item=met%3A1&v=other").status_code == 404
        assert client.get(sheet["sheet"].replace("part=page", "part=m9")).status_code == 404
        assert client.get(sheet["sheet"].replace("part=page", "part=..")).status_code == 404
        # The words of a mark put right are not another sheet; where it lies is.
        marks = [m.model_copy(update={"text": "inaczej"}) for m in shown.marks]
        assert DrawnSheets.key(shown.model_copy(update={"marks": marks})) == DrawnSheets.key(shown)
        moved = [
            m.model_copy(update={"points": [Spot(x=p.x * 0.9, y=p.y) for p in m.points]})
            for m in shown.marks
        ]
        assert DrawnSheets.key(shown.model_copy(update={"marks": moved})) != DrawnSheets.key(shown)
        # The owner's switch off, or the key forgotten: the sheet drawn stays shown.
        assert client.put("/api/ai", json={"drawn": False}).json()["drawn"] is False
        assert client.get("/api/study/met:1").json()["work"]["composition_drawn"] is not None
        assert client.put("/api/ai", json={"drawn": True}).json()["drawn"] is True
        assert client.delete("/api/ai/gemini-key").json()["gemini_key_set"] is False
        assert client.get("/api/study/met:1").json()["work"]["composition_drawn"] is not None


def test_saved_pages_go_through_the_batch_and_an_analysis_made_anew_at_once(
    tmp_path: Path,
) -> None:
    """22:32: "zapisane przez Batch po aktualizacji dla obniżenia kosztu lub
    poprzez "Wykonaj ponowną analizę" od razu"."""
    from test_ai import GOOD_KEY
    from test_composition import _made_again

    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        _catalogue(svc)
        _old_page(svc, **{CHECK_ROUND: ROUND})
        svc.library.set_state(SINCE, "9999")  # the sheets began to be drawn after it
        stood = Stood(svc)
        work = client.get("/api/study/met:1").json()["work"]
        assert work["composition_drawn"] is None and work["composition_drawn_pending"] is False
        assert svc.drawn.at_once() == []
        assert [item.id for item, _ in svc.drawn.saved()] == ["met:1"]
        assert client.get("/api/ai").json()["drawn_waiting"] == 1

        # First round: the studies. Nothing is asked at once.
        assert _step(svc) is False and stood.calls == []
        [[study]] = stood.batches
        assert study.prompt.startswith(UNDERLAY[:40]) and len(study.pictures) == 1
        view = client.get("/api/ai").json()
        assert (view["drawn_waiting"], view["drawn_in_batch"]) == (0, 1)
        assert _step(svc) is False and len(stood.batches) == 1  # Google is at it
        stood.ready = True
        assert _step(svc) is True  # the studies came
        assert svc.drawn._batch() is not None and svc.drawn._batch()["round"] == "lines"
        # Second round: over each study its lines, and what runs out of it.
        stood.ready = False
        assert _step(svc) is False
        lines, spill = stood.batches[1]
        item = svc.library.get("met:1")
        assert item is not None
        stem = f"{item.file_stem}-{svc.drawn.key(_shown(svc))}"
        assert study.name.startswith(f"{item.file_stem}-u")  # the work's, whatever the take
        assert lines.name == f"{stem}/lines" and "pencil (#" in lines.prompt
        assert spill.name == f"{study.name}/spill" and spill.prompt == SPILL
        assert spill.pictures[0].width > lines.pictures[0].width  # padded with its paper
        # The server starts anew meanwhile: the batch is where it was.
        svc.drawn = DrawnSheets(svc.library, svc.images, svc.painter)
        assert svc.drawn.ahead() is False and len(stood.batches) == 2
        stood.ready = True
        assert _step(svc) is True
        assert svc.drawn._batch() is None and svc.drawn.saved() == []
        # The study and what runs out of it are kept for the work.
        under = sorted(path.name for path in svc.drawn.dir.glob(f"{study.name}-*"))
        assert under == [f"{study.name}-spill.png", f"{study.name}-study.png"]
        work = client.get("/api/study/met:1").json()["work"]
        assert len(work["composition_drawn"]["marks"]) >= 1
        first_page = client.get(work["composition_drawn"]["sheet"]).content
        kept = svc.drawn.meta(item, _shown(svc))
        assert kept is not None and kept["cost"] == {
            "underlay": 0.025,
            "lines": 0.026,
            "spill": 0.0215,
        }
        assert _step(svc) is False and len(stood.batches) == 2 and stood.calls == []
        # More than Google takes at once: half as many are handed over.
        full = stood.batch

        def crowded(kind: str, asks: Any) -> str:
            if len(asks) > 1:
                raise ValueError("send fewer at a time")
            return full(kind, asks)

        svc.painter.batch = crowded  # type: ignore[method-assign]
        fields = [Box(x=0.0, y=0.0, w=1.0, h=h) for h in (0.9, 0.8, 0.7)]  # studies of their own
        takes = [(item, _shown(svc).model_copy(update={"field": box})) for box in fields]
        svc.drawn.saved = lambda: takes  # type: ignore[method-assign]
        assert svc.drawn._begin() is False and len(stood.batches[-1]) == 1
        state = svc.drawn._batch()
        assert state is not None and len(state["takes"]) == 1
        svc.drawn._set_batch(None)
        svc.painter.batch = full  # type: ignore[method-assign]
        stood.batches.pop()
        # A saved take of a work that has its study goes straight to the lines'
        # round, and two takes of one work ask for one study between them.
        svc.drawn.saved = lambda: [(item, _shown(svc))]  # type: ignore[method-assign]
        assert svc.drawn._begin() is True
        state = svc.drawn._batch()
        assert state is not None and (state["round"], state["name"]) == ("lines", "")
        svc.drawn._set_batch(None)
        svc.drawn.saved = lambda: [takes[0], takes[0]]  # type: ignore[method-assign]
        assert svc.drawn._begin() is False and len(stood.batches[-1]) == 1
        state = svc.drawn._batch()
        assert state is not None and len(state["takes"]) == 2
        del svc.drawn.saved  # type: ignore[attr-defined]
        svc.drawn._set_batch(None)
        stood.batches.pop()

        # "Wykonaj ponowną analizę": the new take's sheet is drawn at once.
        svc.ai_config.set_key(GOOD_KEY)
        client.post("/api/study/met:1/composition")
        _made_again(svc)
        assert listed(svc.library, AT_ONCE) == {"met:1"}
        work = client.get("/api/study/met:1").json()["work"]
        assert work["composition_drawn"] is None and work["composition_drawn_pending"] is True
        assert [item.id for item, _ in svc.drawn.at_once()] == ["met:1"]
        # 23:20: "a podkład od Gemini już jest, to rób nim tylko kolorowe kreski".
        assert svc.drawn.ahead() is True and stood.calls == [KIND]
        assert listed(svc.library, AT_ONCE) == set() and len(stood.batches) == 2
        work = client.get("/api/study/met:1").json()["work"]
        assert work["composition_drawn"] is not None
        assert client.get(work["composition_drawn"]["sheet"]).content == first_page
        anew = svc.drawn.meta(item, _shown(svc))
        assert anew is not None and anew["cost"] == {"lines": 0.052}
        # The work's picture is another now: its study is thrown away with it.
        measured = imaging.measure
        imaging.measure = lambda work, study: (None, 99.0)  # type: ignore[assignment]
        assert svc.drawn._under(item, _shown(svc), _scene()) is None
        imaging.measure = measured  # type: ignore[assignment]
        assert not list(svc.drawn.dir.glob(f"{study.name}-*"))
        # The take it had before keeps its sheet, should he go back to it.
        assert client.put("/api/study/met:1/composition", json={"shown": 0}).status_code == 200
        assert client.get("/api/study/met:1").json()["work"]["composition_drawn"] is not None
        assert svc.drawn.ahead() is False
        # With the image model the pen (Opus) has nothing to draw at night.
        pen = next(job for job in svc.ai.jobs.values() if isinstance(job, PenJob))
        assert pen.enabled() is False
        client.put("/api/ai", json={"drawn": False})
        assert pen.enabled() is True and svc.drawn.ahead() is False


def test_trouble_with_the_key_is_told_and_a_work_the_model_refuses_is_left(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        _catalogue(svc)
        stood = Stood(svc)
        _old_page(svc)

        # The key's credit is used up: said in Konfiguracja, nothing asked for an hour.
        def broke(kind: str, prompt: str, pictures: Any, size: str = "1K") -> Any:
            stood.calls.append("broke")
            raise NoCredit("no credit")

        svc.painter.paint = broke  # type: ignore[method-assign]
        assert svc.drawn.ahead() is False and svc.drawn.error == NO_CREDIT
        assert client.get("/api/ai").json()["gemini_error"] == "no_credit"
        assert svc.drawn.ahead() is False and stood.calls == ["broke"]
        work = client.get("/api/study/met:1").json()["work"]
        assert work["composition_drawn_pending"] is False  # none is drawn now
        # Another key given: checked for nothing, never sent back, tried again at once.
        svc.painter.check_key = lambda key: None  # type: ignore[method-assign]
        view = client.put("/api/ai/gemini-key", json={"key": f" {GOOGLE_KEY} "}).json()
        assert view["gemini_key_set"] and view["gemini_key_tail"] == "wxyz"
        assert GOOGLE_KEY not in str(view) and view["gemini_error"] is None

        def refused(kind: str, prompt: str, pictures: Any, size: str = "1K") -> Any:
            raise GeminiRejected("no")

        svc.painter.paint = refused  # type: ignore[method-assign]
        assert svc.drawn.ahead() is False and svc.drawn.error == KEY_REJECTED

        def rejects(key: str) -> None:
            raise GeminiRejected("Google did not accept the key")

        svc.painter.check_key = rejects  # type: ignore[method-assign]
        assert client.put("/api/ai/gemini-key", json={"key": "bad"}).status_code == 400
        assert client.put("/api/ai/gemini-key", json={"key": " "}).status_code == 400
        # The month's limit: said too.
        svc.drawn.again()
        svc.painter.paint = Painter(svc.ai_config, svc.claude).paint  # type: ignore[method-assign]
        svc.painter.spending.add(KIND, 1.0)
        svc.ai_config.update(AiConfigUpdate(gemini_monthly_limit_usd=1))
        assert svc.drawn.ahead() is False and svc.drawn.error == LIMIT
        view = client.get("/api/ai").json()
        assert view["gemini_monthly_limit_usd"] == 1 and view["gemini_error"] == LIMIT
        assert view["gemini_spent_usd"] >= 1.0 and view["gemini_spent_by_kind"][KIND] >= 1.0
        assert KIND not in view["spent_by_kind"]  # Claude's month is another
        svc.ai_config.update(AiConfigUpdate(gemini_monthly_limit_usd=10))

        # A picture that cannot be had now is tried again later, however often.
        picture = svc.images.picture

        def gone(item: Any, urgent: bool = False) -> Any:
            raise OSError("no picture")

        svc.images.picture = gone  # type: ignore[method-assign]
        for _ in range(3):
            svc.drawn.again()
            assert svc.drawn.ahead() is True and svc.drawn.at_once() == []
        svc.images.picture = picture  # type: ignore[method-assign]

        # A work the model will not redraw: tried twice, then left with the
        # server's own sheet, and not paid for again.
        def will_not(kind: str, prompt: str, pictures: Any, size: str = "1K") -> Any:
            stood.calls.append("will not")
            raise NotDrawn("Google answered 400", "image_recitation")

        stood.calls.clear()
        svc.painter.paint = will_not  # type: ignore[method-assign]
        svc.drawn.again()
        assert svc.drawn.ahead() is True and svc.drawn.error is None
        assert svc.drawn.at_once() == [] and svc.drawn.ahead() is False  # in an hour
        svc.drawn.again()
        assert svc.drawn.ahead() is True and stood.calls == ["will not"] * 2
        svc.drawn.again()
        assert svc.drawn.at_once() == [] and svc.drawn.ahead() is False
        fresh = DrawnSheets(svc.library, svc.images, svc.painter)
        assert fresh.at_once() == [] and fresh.saved() == []
        work = client.get("/api/study/met:1").json()["work"]
        assert work["composition_drawn"] is None and work["composition_drawn_pending"] is False


def test_the_batch_keeps_within_the_months_limit_and_leaves_what_is_refused(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app):
        _catalogue(svc)
        _old_page(svc)
        svc.library.set_state(SINCE, "9999")
        stood = Stood(svc)
        # Nothing is handed over that the month's limit does not hold.
        svc.painter.spending.add(KIND, 0.99)
        svc.ai_config.update(AiConfigUpdate(gemini_monthly_limit_usd=1))
        assert _step(svc) is False and stood.batches == [] and svc.drawn.error == LIMIT
        svc.ai_config.update(AiConfigUpdate(gemini_monthly_limit_usd=10))
        svc.drawn.again()
        # The model refuses the work's study, twice: left.
        item = svc.library.get("met:1")
        assert item is not None
        stood.ready, stood.refuse = True, svc.drawn._under_name(item, _shown(svc))
        assert _step(svc) is False and len(stood.batches) == 1
        assert _step(svc) is True and svc.drawn._batch() is None
        assert _step(svc) is False and len(stood.batches) == 2
        assert _step(svc) is True
        assert _step(svc) is False and len(stood.batches) == 2 and svc.drawn.saved() == []
        # The lines refused: the study alone is no sheet, but it is kept for the work.
        svc.drawn._tried = {}
        stood.refuse = "/lines"
        assert _step(svc) is False and _step(svc) is True  # the studies came
        assert _step(svc) is False and len(stood.batches) == 4  # the second round
        assert _step(svc) is True and svc.drawn._batch() is None
        assert svc.drawn.meta(item, _shown(svc)) is None
        assert len(list(svc.drawn.dir.glob("*-study.png"))) == 1
        assert len(list(svc.drawn.dir.glob("*-spill.png"))) == 1
        # Tried again, its lines alone are asked for over that study.
        stood.refuse = ""
        svc.drawn._tried = {}
        assert _step(svc) is True  # nothing to ask in the first round
        assert _step(svc) is False and len(stood.batches) == 5
        assert [ask.name.rsplit("/", 1)[1] for ask in stood.batches[4]] == ["lines"]

        # A batch Google lost is handed over again.
        def lost(kind: str, batch: str) -> Any:
            raise NotDrawn("the batch expired")

        svc.painter.batched = lost  # type: ignore[method-assign]
        assert _step(svc) is False and svc.drawn._batch() is None
        svc.painter.batched = stood.batched  # type: ignore[method-assign]
        assert _step(svc) is True and _step(svc) is False and len(stood.batches) == 6
        assert _step(svc) is True
        kept = svc.drawn.meta(item, _shown(svc))
        assert kept is not None and kept["cost"] == {"lines": 0.026}
