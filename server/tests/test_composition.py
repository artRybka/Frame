"""The composition's marks: where they land and whether they hold. Points in
the picture's pixels, marks that mean something, a grid only under a take
that lies on it, and a check by Claude over the marks drawn on the picture."""

from __future__ import annotations

from typing import Any

from PIL import Image
from test_daily import ANSWER, SIZE, _catalogue, pixels

from frame_server.ai.check import KIND as CHECK
from frame_server.ai.check import SYSTEM as CHECK_SYSTEM
from frame_server.ai.check import CheckJob, check
from frame_server.ai.client import Answer
from frame_server.ai.daily import (
    CHECK_ROUND,
    CHECKED,
    ROUND,
    View,
    _mark,
    _view,
    clean,
    takes,
    to_fractions,
)
from frame_server.ai.sketch import draw, grid_fits, measure, measures
from frame_server.ai.study import KIND as STUDY
from frame_server.library.models import Note
from frame_server.service import FrameService


def _points(*xy: tuple[float, float]) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in xy]


def _drawn(shape: str, *xy: tuple[float, float]) -> Any:
    return _mark({"shape": shape, "points": _points(*xy), "title": "Ślad"})


def test_pixels_become_fractions_and_fractions_stay() -> None:
    data = to_fractions(pixels(ANSWER), SIZE)
    assert data["focus"] == {"x": 0.64, "y": 1.4}  # cut to the picture later, by clean()
    arrow = data["composition"]["views"][0]["marks"][0]
    assert arrow["points"][1] == {"x": 0.2, "y": 0.3}
    assert data["details"][0] == {**ANSWER["details"][0], "x": 0.4, "y": 0.1, "w": 0.2, "h": 0.3}
    # A model that answered in fractions after all is not divided again.
    fractions = {"focus": {"x": 0.5, "y": 0.25}}
    assert to_fractions(fractions, SIZE) == fractions
    assert to_fractions(pixels(ANSWER), None) == pixels(ANSWER)  # size unknown


def test_marks_that_mean_nothing_go() -> None:
    assert _drawn("rhythm", (0.1, 0.5), (0.2, 0.5), (0.3, 0.5)) is None  # no longer drawn
    assert _drawn("triangle", (0.1, 0.1), (0.5, 0.5), (0.9, 0.9)) is None  # a line
    assert _drawn("rect", (0.2, 0.2), (0.2, 0.6)) is None
    loop = _drawn("loop", (0.5, 0.5), (0.5, 0.5))  # around nothing: made a small loop
    assert loop is not None and loop.points[1].x - loop.points[0].x >= 0.015


def test_lines_are_drawn_as_meant() -> None:
    diagonal = _drawn("line", (0.02, 0.97), (0.98, 0.03))
    assert [(p.x, p.y) for p in diagonal.points] == [(0, 1), (1, 0)]  # corner to corner
    horizon = _drawn("line", (0.05, 0.62), (0.95, 0.628))
    assert horizon.points[0].y == horizon.points[1].y == 0.624
    axis = _drawn("line", (0.497, 0.1), (0.503, 0.9))
    assert axis.points[0].x == axis.points[1].x == 0.5
    slant = _drawn("line", (0.1, 0.2), (0.6, 0.7))
    assert [(p.x, p.y) for p in slant.points] == [(0.1, 0.2), (0.6, 0.7)]


def test_great_lines_run_past_the_edges() -> None:
    wedge = _drawn("line", (-0.2, 0.9), (0.43, 0.3), (1.3, 1.2))
    assert [(p.x, p.y) for p in wedge.points] == [(-0.2, 0.9), (0.43, 0.3), (1.3, 1.2)]
    pyramid = _drawn("triangle", (0.6, 0.15), (-3.0, 1.2), (1.2, 2.5))
    assert [(p.x, p.y) for p in pyramid.points] == [(0.6, 0.15), (-0.5, 1.2), (1.2, 1.5)]
    loop = _drawn("loop", (1.2, 0.5), (1.3, 0.6))  # a thing ringed is on the picture
    assert all(0 <= p.x <= 1 for p in loop.points)


def _take(grid: str, *marks: dict[str, Any]) -> View:
    view = _view({"title": "Geometria", "grid": grid, "text": "", "marks": list(marks)})
    assert view is not None
    return view


def test_a_grid_stays_only_under_what_lies_on_it() -> None:
    horizon = {"shape": "line", "points": _points((0.0, 0.62), (1.0, 0.62)), "title": "Horyzont"}
    assert _take("golden", horizon).grid == "golden"
    assert _take("thirds", horizon).grid == "thirds"  # near 2/3 is near enough
    middle = {"shape": "line", "points": _points((0.0, 0.5), (1.0, 0.5)), "title": "Horyzont"}
    assert _take("golden", middle).grid == "none"  # halfway lies on neither
    face = {"shape": "loop", "points": _points((0.335, 0.3), (0.38, 0.36)), "title": "Twarz"}
    assert _take("thirds", face).grid == "thirds"
    arrow = {"shape": "arrow", "points": _points((0.1, 0.9), (0.62, 0.38)), "title": "Wzrok"}
    assert _take("golden", arrow).grid == "none"  # a path proves no grid
    wedge = {"shape": "line", "points": _points((0.0, 0.9), (0.4, 0.37), (1.2, 1.1)), "title": "V"}
    assert _take("golden", wedge).grid == "golden"  # its apex lies on the section
    # Two diagonals crossing in the middle: the 2×2 grid, not the thirds.
    one = {"shape": "line", "points": _points((0.1, 0.1), (0.9, 0.9)), "title": "Przekątna"}
    two = {"shape": "line", "points": _points((0.1, 0.9), (0.9, 0.1)), "title": "Przekątna"}
    assert _take("halves", one, two).grid == "halves"
    assert _take("thirds", one, two).grid == "none"
    assert grid_fits(_take("none", arrow))


def test_the_server_measures_what_the_eye_cannot() -> None:
    horizon = _drawn("line", (0.0, 0.6), (1.0, 0.6))
    text = measure(horizon, (1000, 800))
    assert "poziomo" in text and "złoty podział 0.618: o 0.018" in text
    diagonal = _drawn("line", (0.0, 1.0), (1.0, 0.0))
    assert "z rogu do rogu" in measure(diagonal, (1000, 800))
    wedge = measure(_drawn("line", (-0.1, 1.0), (0.5, 0.2), (1.1, 1.0)), (1000, 800))
    assert wedge.startswith("wierzchołek (500, 160") and "ramiona pod kątem" in wedge
    assert wedge.endswith("biegnie poza obraz")
    cross = _take(
        "none",
        {"shape": "line", "points": _points((0.0, 0.0), (1.0, 1.0)), "title": "A"},
        {"shape": "line", "points": _points((0.0, 1.0), (1.0, 0.0)), "title": "B"},
    )
    (found,) = [m for m in measures(cross, (1000, 800)) if m.startswith("Przecięcie")]
    assert found.startswith("Przecięcie śladów 1 i 2 w (500, 400)") and "połowa: o 0.000" in found


def test_the_takes_come_in_order() -> None:
    def take(title: str) -> View:
        view = _view(
            {"title": title, "grid": "none", "text": "", "marks": [CHECKED_TAKE["marks"][0]]}
        )
        assert view is not None
        return view

    shown = takes(
        [take("Geometria detali"), take("Spojrzenie"), take("Światło"), take("Geometria")]
    )
    assert [v.title for v in shown] == ["Geometria", "Spojrzenie", "Geometria detali"]
    old = takes([take("Spojrzenie"), take("Geometria"), take("Światło")])
    assert [v.title for v in old] == ["Geometria", "Spojrzenie"]  # an old third take stays out


def test_the_marks_are_drawn_on_the_picture() -> None:
    view = _view(ANSWER["composition"]["views"][0])
    assert view is not None
    picture = Image.new("RGB", (300, 200), (40, 70, 140))
    drawn = draw(picture, view)
    assert drawn.size == (300, 200) and drawn.getpixel((10, 190)) != (40, 70, 140)
    assert picture.getpixel((10, 190)) == (40, 70, 140)  # the picture itself is left alone


CHECKED_TAKE = {
    "title": "Spojrzenie",
    "grid": "none",
    "text": "Oko biegnie łukiem fali do Fudżi.",
    "marks": [
        {
            "shape": "loop",
            "points": _points((0.66, 0.7), (0.72, 0.62)),
            "title": "Fudżi",
            "text": "przesunięta na szczyt",
        }
    ],
}


def test_claude_checks_the_takes_over_its_marks(service: FrameService) -> None:
    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    data = to_fractions(pixels(ANSWER), SIZE)
    asked: list[dict[str, Any]] = []

    def ask(params: dict[str, Any]) -> Answer:
        asked.append(params)
        reply = {"views": [CHECKED_TAKE], "changes": ["Spojrzenie, ślad 2: kółko na szczycie"]}
        return Answer(pixels(reply, (900, 600)), False, 0.05, "claude-opus-5-5")

    checked = check(service.images, item, data, ask)
    (params,) = asked
    assert params["system"][0]["text"] == CHECK_SYSTEM
    content = params["messages"][0]["content"]
    assert [b["type"] for b in content].count("image") == 3  # clean, Spojrzenie, Geometria
    text = content[-1]["text"]
    assert "OBRAZ: 900 × 600 px" in text and "Pomiary serwera:" in text
    assert "loop „Fudżi”" in text and "(576, 396)" in text  # its points in pixels
    views = checked["composition"]["views"]
    assert [v["title"] for v in views] == ["Spojrzenie"]
    assert views[0]["marks"][0]["points"][0] == {"x": 0.66, "y": 0.7}
    assert checked[CHECKED] == ["Spojrzenie, ślad 2: kółko na szczycie"]
    assert checked["teaser"] == data["teaser"]  # the rest of the page as it was

    # An unusable check leaves the takes as they were.
    def refuse(params: dict[str, Any]) -> Answer:
        return Answer(None, True, 0.0, "claude-opus-5-5")

    assert check(service.images, item, data, refuse) == {**data, CHECKED: [], CHECK_ROUND: ROUND}
    assert check(service.images, item, {"teaser": "x"}, refuse) == {"teaser": "x"}


def _old_page(service: FrameService, **extra: Any) -> None:
    """A study written before the check: its takes as they were drawn."""
    essay = clean(ANSWER, [])
    assert essay is not None
    item = service.library.get("met:1")
    assert item is not None
    service.library.save_note(
        Note(
            item_id="met:1",
            kind=STUDY,
            model="claude-opus",
            prompt_version="study-1/daily-7",
            source_hash=service.study.job.source_hash(item),
            data={**essay.model_dump(), **extra},
        )
    )


def test_old_pages_are_checked_once(service: FrameService) -> None:
    _catalogue(service)
    job = service.ai.jobs[CHECK]
    assert isinstance(job, CheckJob)
    item = service.library.get("met:1")
    assert item is not None
    beats = _points((0.1, 0.5), (0.2, 0.5), (0.3, 0.5))
    rhythm = {"shape": "rhythm", "points": beats, "title": "Fale"}
    _old_page(service)
    page = service.library.note("met:1", STUDY)
    assert page is not None
    views = [*page.data["composition"]["views"], {**CHECKED_TAKE, "title": "Rytm"}]
    views[-1]["marks"] = [rhythm]
    service.library.save_note(
        page.model_copy(update={"data": {**page.data, "composition": {"views": views}}})
    )
    # Shown as today: "Geometria" first, no "Rytm".
    essay = service.study.essay(item)
    assert essay is not None
    assert [v.title for v in essay.composition.views] == ["Geometria", "Spojrzenie"]
    job._pages = (0.0, set())
    assert job.wanted(item)
    params = job.params(item)
    assert params["system"][0]["text"] == CHECK_SYSTEM

    reply = {"views": [CHECKED_TAKE], "changes": ["kółko na szczycie"]}
    answer = job.revise(item, params, Answer(pixels(reply), False, 0.05, "o"), lambda p: None)  # type: ignore[arg-type,return-value]
    note = Note(
        item_id="met:1",
        kind=CHECK,
        model="o",
        prompt_version=job.prompt_version,
        source_hash=job.source_hash(item),
        data=answer.data or {},
    )
    job.apply(item, service.library.save_note(note))
    page = service.library.note("met:1", STUDY)
    assert page is not None and page.data[CHECKED] == ["kółko na szczycie"]
    views = page.data["composition"]["views"]
    assert [v["title"] for v in views] == ["Spojrzenie"]
    assert views[0]["marks"][0]["points"][0] == {"x": 0.66, "y": 0.7}
    assert page.data["teaser"] == clean(ANSWER, []).teaser  # type: ignore[union-attr]
    assert not job.wanted(item)  # once
    assert page.data[CHECK_ROUND] == ROUND

    # A page checked by the first round is checked once more.
    first = {k: v for k, v in page.data.items() if k != CHECK_ROUND}
    service.library.save_note(page.model_copy(update={"data": first}))
    job._pages = (0.0, set())
    assert job.wanted(item)
