"""The composition's marks: where they land and whether they hold. Points in
the picture's pixels, marks that mean something, a grid only under a take
that lies on it, the analysis asked apart in steps (Opus, a Haiku check over
the marks drawn on the picture, the grid measured by the server, Sonnet's
movement, the text written last in one voice), and pages written before
written again."""

from __future__ import annotations

from typing import Any

from PIL import Image
from test_daily import ANSWER, SIZE, _catalogue, pixels

from frame_server.ai import grid as grids
from frame_server.ai import lines as found_lines
from frame_server.ai.check import SYSTEM as CHECK_SYSTEM
from frame_server.ai.check import checked
from frame_server.ai.check import question as check_question
from frame_server.ai.client import HAIKU, OPUS, SONNET, AiUnavailable, Answer
from frame_server.ai.composition import (
    BEFORE,
    CHOSEN,
    COST,
    KIND,
    LET_ALL,
    REWORK_KEY,
    ComposeJob,
    compose,
    merged,
)
from frame_server.ai.composition import SYSTEM as COMPOSITION_SYSTEM
from frame_server.ai.daily import (
    CHECK_ROUND,
    CHECKED,
    ROUND,
    TAKE,
    Key,
    View,
    _mark,
    _view,
    clean,
    takes,
    to_fractions,
)
from frame_server.ai.motion import SYSTEM as MOTION_SYSTEM
from frame_server.ai.motion import Movement, movement
from frame_server.ai.pen import SYSTEM as PEN_SYSTEM
from frame_server.ai.prose import PROSE, PROSE_KEY
from frame_server.ai.prose import SYSTEM as PROSE_SYSTEM
from frame_server.ai.sketch import PHI, beats, draw, grid_fits, measure, measures
from frame_server.ai.sketch import spiral as sketch_spiral
from frame_server.ai.study import KIND as STUDY
from frame_server.library.models import Note
from frame_server.library.wikidata import _sections_first
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
    assert _drawn("rhythm", (0.1, 0.5), (0.2, 0.5), (0.3, 0.5)) is None  # an old one: no pairs
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


def _mark_raw(mark: Any) -> dict[str, Any]:
    return {"shape": mark.shape, "points": [p.model_dump() for p in mark.points]}


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


def test_a_golden_spiral() -> None:
    spiral = _drawn("spiral", (1.3, 0.47), (0.75, 0.93), (0.4, 0.35))  # it may start outside
    assert spiral is not None and spiral.anchor() == spiral.points[-1]  # its eye
    assert _drawn("spiral", (0.4, 0.35), (0.5, 0.5), (0.41, 0.36)) is None  # around nothing
    text = measure(spiral, (1000, 600))
    assert text.startswith("oko w (400, 210") and "zgodnie z ruchem wskazówek zegara" in text
    assert text.endswith("zaczyna się poza obrazem")
    flipped = _drawn("spiral", (1.3, 0.47), (0.75, 0.1), (0.4, 0.35))
    assert "przeciwnie do wskazówek zegara" in measure(flipped, (1000, 600))
    # Every quarter turn its radius shrinks by φ.
    path = sketch_spiral((1000.0, 0.0), (0.0, 1000.0), (0.0, 0.0))
    quarter = next(p for p in path if p[0] <= 1e-6 and p[1] > 0)
    assert abs(quarter[1] - 1000 / PHI) < 1
    eye = _take("golden", {**_mark_raw(spiral), "title": "Spirala"})
    assert eye.grid == "golden"  # its eye lies on the section (0.4 ≈ 0.382)


def test_more_grids() -> None:
    column = {"shape": "line", "points": _points((0.335, 0.1), (0.335, 0.9)), "title": "Oś"}
    assert _take("3x2", column).grid == "3x2"  # a third across
    assert _take("2x3", column).grid == "none"  # the half across only
    level = {"shape": "line", "points": _points((0.0, 0.5), (1.0, 0.5)), "title": "Horyzont"}
    assert _take("3x2", level).grid == "3x2" and _take("2x3", level).grid == "none"


def test_the_pictures_own_lines() -> None:
    size = (1600, 1000)
    diagonal = measure(_drawn("line", (0.0, 1.0), (1.0, 0.0)), size)
    assert "biegnie po przekątnej obrazu" in diagonal
    # From the top left corner at right angles to the other diagonal: in
    # pixels along (1000, 1600), here to (300, 480).
    golden = measure(_drawn("line", (0.0, 0.0), (0.1875, 0.48)), size)
    assert "złoty trójkąt" in golden
    rabatment = measure(_drawn("line", (0.625, 0.1), (0.625, 0.9)), size)
    assert "linii rabatu" in rabatment


def test_a_rhythm_is_a_stroke_along_each_form() -> None:
    # Three masts, foot and top each (one given top first): parallel strokes.
    masts = _drawn(
        "rhythm", (0.2, 0.8), (0.21, 0.3), (0.4, 0.3), (0.4, 0.8), (0.6, 0.82), (0.59, 0.32)
    )
    assert masts is not None and len(masts.points) == 6
    strokes = beats([(p.x * 1000, p.y * 1000) for p in masts.points])
    assert len(strokes) == 3
    directions = {round((b[0] - a[0]) / (b[1] - a[1]), 6) for a, b in strokes}
    assert len(directions) == 1  # parallel
    (a, b) = strokes[1]
    assert b[1] - a[1] > 500  # a little longer than the mast (500 px)
    assert _drawn("rhythm", (0.2, 0.8), (0.2, 0.3), (0.4, 0.3), (0.4, 0.8)) is None  # two: echo
    dot = _drawn("rhythm", (0.2, 0.8), (0.2, 0.3), (0.4, 0.3), (0.4, 0.3), (0.5, 0.3), (0.5, 0.8))
    assert dot is None  # a pair that is a dot is no beat
    text = measure(masts, (1000, 1000))
    assert text.startswith("3 kreski pod kątem 9") and "odstępy" in text


def test_rays_run_into_a_vanishing_point() -> None:
    rays = _drawn("rays", (0.5, 0.45), (0.0, 0.0), (1.0, 0.0), (0.5, 0.46), (-0.2, 0.9))
    assert rays is not None
    # The point kept first, an end on it left out; ends may lie outside.
    assert [(p.x, p.y) for p in rays.points] == [(0.5, 0.45), (0.0, 0.0), (1.0, 0.0), (-0.2, 0.9)]
    assert rays.anchor() == rays.points[0]
    text = measure(rays, (1000, 500))
    assert text.startswith("punkt zbiegu (500, 225") and "3 promienie" in text
    assert _drawn("rays", (0.5, 0.45), (0.0, 0.0)) is None  # one ray is a line
    # A vanishing point on the golden section keeps the grid.
    assert (
        _take(
            "golden", {**_mark_raw(_drawn("rays", (0.38, 0.4), (0, 0), (1, 0))), "title": "Zbieg"}
        ).grid
        == "golden"
    )


def test_a_movement_is_drawn_with_speed_lines() -> None:
    flight = _drawn("motion", (0.9, 0.6), (0.6, 0.65), (0.3, 0.5))
    assert flight is not None and len(flight.points) == 3
    picture = Image.new("RGB", (300, 200), (40, 70, 140))
    view = View(title=TAKE, marks=[flight])
    drawn = draw(picture, view)
    assert drawn.getpixel((90, 100)) != (40, 70, 140)  # the arrow's tip
    assert "kąt" in measure(flight, (300, 200))


def test_one_take_is_shown() -> None:
    def take(title: str, *marks: dict[str, Any]) -> View:
        raw = {"title": title, "grid": "none", "text": "", "marks": list(marks)}
        view = _view({**raw, "marks": list(marks) or [CHECKED_TAKE["marks"][0]]})
        assert view is not None
        return view

    old = takes([take("Geometria detali"), take("Spojrzenie"), take("Światło"), take("Geometria")])
    assert [v.title for v in old] == [TAKE]  # "Geometria", called as the analysis
    assert takes([take("Spojrzenie"), take("Rytm")]) == []
    new = take(TAKE, {"shape": "line", "points": _points((0, 0.5), (1, 0.5)), "title": "Pas"})
    assert takes([take("Geometria"), new]) == [new]


def test_the_marks_are_drawn_on_the_picture() -> None:
    view = _view(ANSWER["composition"]["views"][0])
    assert view is not None
    picture = Image.new("RGB", (300, 200), (40, 70, 140))
    drawn = draw(picture, view)
    assert drawn.size == (300, 200) and drawn.getpixel((10, 190)) != (40, 70, 140)
    assert picture.getpixel((10, 190)) == (40, 70, 140)  # the picture itself is left alone


CHECKED_TAKE = {
    "title": TAKE,
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


def test_haiku_checks_each_mark_and_place(service: FrameService) -> None:
    from frame_server.ai.check import CHECK_SIDE
    from frame_server.ai.daily import picture

    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    view = _view(CHECKED_TAKE | {"marks": [*CHECKED_TAKE["marks"], HORIZON]})
    assert view is not None
    keys = [Key(x=0.5, y=0.5, title="szczyt", main=True), Key(x=0.2, y=0.9, title="łódź")]
    img = picture(service.images, item, CHECK_SIDE)
    params = check_question(img, view, keys, {"Fudżi": ["szczyt", "zbocze"]})
    assert params["model"] == HAIKU and params["system"][0]["text"] == CHECK_SYSTEM
    content = params["messages"][0]["content"]
    assert [b["type"] for b in content].count("image") == 2  # clean, and the take drawn
    text = content[-1]["text"]
    assert "OBRAZ: 900 × 600 px" in text and "Pomiary serwera:" in text
    assert "loop „Fudżi”" in text and "na: szczyt; zbocze" in text
    # A loop is shown as the box it is drawn in, and moved as one.
    assert "punkty: (540, 372) (648, 468)" in text
    assert "P1. (450, 300) – na: szczyt – główny" in text

    reply = {
        "marks": [
            {"n": 1, "verdict": "move", "points": _points((580, 370), (680, 470)), "why": "obok"},
            {"n": 2, "verdict": "drop", "points": [], "why": "nie ma horyzontu"},
        ],
        "points": [
            {"n": 1, "verdict": "move", "point": {"x": 540, "y": 300}, "why": ""},
            {"n": 2, "verdict": "drop", "point": {"x": 0, "y": 0}, "why": ""},
        ],
        "text": "Oko biegnie do Fudżi.",
    }
    found = checked(view, keys, reply, img.size)
    (mark,) = found.view.marks
    assert mark.title == "Fudżi" and (mark.points[0].x, mark.points[0].y) == (0.7, 0.7)
    assert (round(mark.points[1].x * 900), round(mark.points[1].y * 600)) == (680, 470)
    assert [(k.title, k.x) for k in found.keys] == [("szczyt", 0.6)]
    assert found.keys[0].main
    assert found.view.text == "Oko biegnie do Fudżi."
    assert found.changes[1] == "usunięty ślad 2 „Horyzont”: nie ma horyzontu"
    # A check that would leave nothing, or none at all: the take as it was.
    every = {"marks": [{"n": n, "verdict": "drop"} for n in (1, 2)], "points": [], "text": ""}
    assert checked(view, keys, every, img.size).view == view
    assert checked(view, keys, None, img.size).changes == []


HORIZON = {"shape": "line", "points": _points((0.0, 0.6), (1.0, 0.6)), "title": "Horyzont"}


def _sea(size: tuple[int, int] = (900, 600), horizon: float = 0.62) -> Image.Image:
    """A light sky over a dark sea."""
    img = Image.new("RGB", size, (200, 215, 235))
    img.paste((20, 40, 90), (0, round(size[1] * horizon), size[0], size[1]))
    return img


def test_the_pictures_own_lines_are_found_in_code() -> None:
    found = found_lines.find(_sea())
    (edge,) = [e for e in found.edges if e.axis == "y"]
    assert abs(edge.pos - 0.62) < 0.01 and edge.run() > 0.9 and edge.name == "L1"
    assert "granica" in edge.kind and edge.side().startswith("jaśniej nad")
    level, upright, _ = found_lines.directions(_sea())
    assert level > 0.9 and upright < 0.05
    assert found_lines.find(Image.new("RGB", (300, 200), (40, 70, 140))).edges == []


def test_the_grid_is_chosen_by_what_lies_on_it() -> None:
    sea = found_lines.find(_sea(horizon=0.665))
    # The horizon named a little off (0.69: beside the thirds) moves onto the
    # picture's own line, which lies on them.
    horizon = Key(x=0.5, y=0.69, title="horyzont", axis="y")
    face = Key(x=0.34, y=0.5, title="twarz", main=True)
    choice = grids.choose([face, horizon], sea)
    assert choice.grid == "thirds"
    assert abs(choice.held[1].key.y - 0.665) < 0.01 and choice.held[1].edge is not None
    assert len(choice.kept()) == 2  # the horizon is named: no free line
    assert grids.choose([face, horizon], found_lines.Found([], [])).grid == "none"
    # Nothing on any grid's lines: none.
    assert grids.choose([Key(x=0.45, y=0.45, title="x", main=True)], sea).grid == "none"
    # A long boundary in the middle counts by itself (but not as the main one).
    middle = found_lines.find(_sea(horizon=0.5))
    alone = grids.choose([Key(x=0.5, y=0.2, title="oś", axis="x")], middle)
    assert alone.grid == "none"  # two on the halves, neither main
    with_face = grids.choose([Key(x=0.5, y=0.2, title="oś", axis="x", main=True)], middle)
    assert with_face.grid == "halves" and with_face.held[-1].free
    # A take keeps what its grid was chosen by, so the grid stays under it.
    view = _view(
        {
            "title": TAKE,
            "grid": "halves",
            "marks": [CHECKED_TAKE["marks"][0]],
            "keys": [k.model_dump() for k in with_face.kept()],
        }
    )
    assert view is not None and view.grid == "halves" and len(view.keys) == 2


def test_the_steps_are_put_together() -> None:
    view = _view(CHECKED_TAKE | {"text": "Jeden. Dwa. Trzy."})
    assert view is not None
    flight = _mark({"shape": "motion", "points": _points((0.1, 0.9), (0.5, 0.3)), "title": "Lot"})
    assert flight is not None
    choice = grids.Choice("thirds", [grids.Held(Key(x=1 / 3, y=0.5, title="oś", axis="x"))])
    both = merged(view, choice, Movement("dynamiczna", "Ruch.", 0, 1, [flight]))
    assert both.text == "Jeden. Ruch. Dwa. Trzy."
    assert both.grid == "thirds" and [m.shape for m in both.marks] == ["loop", "motion"]
    swapped = merged(view, None, Movement("statyczna", "Spokój.", 2, 0, []))
    assert swapped.text == "Jeden. Spokój. Trzy." and swapped.grid == "none"
    # The text written last: the movement's marks, not its sentence.
    unsaid = merged(view, None, Movement("dynamiczna", "Ruch.", 0, 1, [flight]), said=False)
    assert unsaid.text == "Jeden. Dwa. Trzy." and len(unsaid.marks) == 2
    answer = {
        "sentence": "Ruch.",
        "replaces": 0,
        "where": 0,
        "marks": [{"shape": "motion", "points": _points((90, 540), (450, 180)), "title": "Lot"}],
    }
    found = movement(answer, (900, 600))
    assert found is not None and found.marks[0].points[0].x == 0.1
    assert movement({"sentence": ""}, (900, 600)) is None


ANALYSIS = {
    "composition": {
        "views": [
            {
                "title": TAKE,
                "grid": "none",
                "text": "Kompozycja otwarta: fala tnie lewą krawędź.",
                "marks": [
                    {
                        "shape": "rhythm",
                        "points": _points(
                            (0.2, 0.8), (0.2, 0.4), (0.4, 0.8), (0.4, 0.4), (0.6, 0.8), (0.6, 0.4)
                        ),
                        "title": "Rytm łodzi",
                        "text": "trzy łodzie",
                    }
                ],
            }
        ]
    }
}


#: Opus's analysis, in pixels of a 900 × 600 picture: no grid, no
#: movement, the places it rests on; a loop as the box around the thing.
ANALYSIS_V6 = {
    "composition": {
        "views": [
            {
                "title": TAKE,
                "text": "Fala zamyka lewą stronę. Kompozycja otwarta: fala tnie krawędź. "
                "Mała góra równoważy wielką falę.",
                "points": [
                    {"x": 300, "y": 200, "na": "grzbiet fali", "os": "xy", "waga": "główny"},
                    {"x": 610, "y": 400, "na": "szczyt Fudżi", "os": "xy", "waga": "ważny"},
                    {"x": 450, "y": 590, "na": "łódź", "os": "y", "waga": "ważny"},
                ],
                "marks": [
                    {
                        "shape": "loop",
                        "points": _points((550, 360), (650, 440)),
                        "title": "Fudżi",
                        "text": "przeciwwaga",
                        "na": ["szczyt", "zbocze"],
                        "po": "stożek góry",
                    },
                    {
                        "shape": "line",
                        "points": _points((0, 300), (900, 300)),
                        "title": "Horyzont",
                        "text": "",
                        "na": ["brzeg", "brzeg"],
                    },
                ],
            }
        ]
    }
}


#: Sonnet's pen sketch, in pixels of the picture it got (900 × 600 fits whole).
SKETCH = {
    "szkic": [
        {"co": "grzbiet fali", "points": _points((0, 420), (200, 180), (420, 150)), "ostra": False},
        {"co": "horyzont", "points": _points((0, 300), (900, 300)), "ostra": True},
        {"co": "Fudżi", "points": _points((560, 440), (610, 380), (660, 440)), "ostra": True},
        {"co": "łódź", "points": _points((300, 560), (450, 590), (600, 560)), "zamknieta": True},
        {"co": "kropka", "points": _points((10, 10))},  # no stroke
    ]
}


#: The text as the writer puts it together at the end.
WRITTEN = (
    "Wielka fala zamyka lewą stronę i tnie krawędź, więc morze trwa dalej poza kadrem. "
    "Grzbiet fali leży na przecięciu linii trójpodziału, a łuki fali niosą ruch. "
    "Mała Fudżi w dole odpowiada na ten ciężar."
)


def _pipeline(asked: list[dict[str, Any]], analysis: dict[str, Any] = ANALYSIS_V6) -> Any:
    """Every step answering: Opus, the Haiku check, Sonnet's movement and
    its pen sketch, and the writer of the text."""

    def ask(params: dict[str, Any]) -> Answer:
        asked.append(params)
        system = params["system"][0]["text"]
        if system == CHECK_SYSTEM:
            reply: dict[str, Any] = {
                "marks": [
                    {"n": 1, "verdict": "move", "points": _points((560, 360), (660, 440))},
                    {"n": 2, "verdict": "drop", "points": [], "why": "brak horyzontu"},
                ],
                "points": [{"n": 3, "verdict": "drop", "point": {"x": 0, "y": 0}}],
                "text": "",
            }
            return Answer(reply, False, 0.01, HAIKU)
        if system == PROSE_SYSTEM:
            return Answer({"text": WRITTEN}, False, 0.015, OPUS)
        if system == PEN_SYSTEM:
            return Answer(SKETCH, False, 0.02, SONNET)
        if system == MOTION_SYSTEM:
            reply = {
                "budowa": "dynamiczna",
                "sentence": "Przeważają łuki fali, więc kompozycja jest dynamiczna.",
                "replaces": 0,
                "where": 2,
                "marks": [
                    {
                        "shape": "motion",
                        "points": _points((100, 500), (300, 200), (450, 150)),
                        "na": ["dół", "grzbiet", "pióropusz"],
                        "title": "Fala",
                        "text": "wali się",
                    }
                ],
                "why": "łuki",
            }
            return Answer(reply, False, 0.03, SONNET)
        return Answer(analysis, False, 0.07, OPUS)

    return ask


def test_the_analysis_is_asked_apart_in_steps(service: FrameService) -> None:
    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    asked: list[dict[str, Any]] = []
    found = compose(service.images, item, service.daily.job.sources(item), _pipeline(asked))
    first, check, motion, sketch, writer = asked
    assert first["system"][0]["text"] == COMPOSITION_SYSTEM and first["model"] == OPUS
    assert first["output_config"]["effort"] == "medium"
    text = first["messages"][0]["content"][1]["text"]
    assert "OBRAZ: 900 × 600 px" in text and "OPIS MUZEUM" not in text  # the picture alone
    assert check["model"] == HAIKU and "loop „Fudżi”" in check["messages"][0]["content"][-1]["text"]
    assert motion["model"] == SONNET
    assert "po: stożek góry" in check["messages"][0]["content"][-1]["text"]
    # The pen sketch: the picture alone, smaller, by the cheaper model.
    assert sketch["model"] == SONNET and sketch["system"][0]["text"] == PEN_SYSTEM
    assert [b["type"] for b in sketch["messages"][0]["content"]] == ["image", "text"]
    # The writer gets the draft and the facts, no picture.
    assert writer["model"] == OPUS and writer["output_config"]["effort"] == "low"
    (content,) = writer["messages"][0]["content"]
    assert content["type"] == "text"
    facts = content["text"]
    assert "Fala zamyka lewą stronę." in facts and "Siatka: trójpodział." in facts
    assert "grzbiet fali: na linii" in facts and "Budowa: dynamiczna." in facts
    (view,) = found["composition"]["views"]
    assert view["title"] == TAKE and view["grid"] == "thirds"
    assert view["text"] == WRITTEN
    assert found[PROSE_KEY] == PROSE
    assert [m["shape"] for m in view["marks"]] == ["loop", "motion"]
    assert [k["title"] for k in view["keys"]] == ["grzbiet fali", "szczyt Fudżi"]
    assert found[CHECKED][0].startswith("przesunięty ślad 1 „Fudżi”")
    assert found[CHECK_ROUND] == ROUND
    assert found[COST] == {
        "analysis": 0.07, "check": 0.01, "motion": 0.03, "sketch": 0.02, "text": 0.015
    }  # fmt: skip
    # The loop came as a box and is kept as its centre and a corner, moved by the check.
    loop = view["marks"][0]
    assert (round(loop["points"][0]["x"] * 900), round(loop["points"][0]["y"] * 600)) == (610, 400)
    # The sketch goes into the take, for the sheet: four strokes, the dot left out.
    assert len(view["sketch"]) == 4 and view["sketch"][1]["sharp"] and view["sketch"][3]["closed"]
    assert view["field"] is None
    # An unusable analysis gives the page nothing.
    refused = compose(
        service.images, item, service.daily.job.sources(item), lambda p: Answer(None, True, 0, "o")
    )
    assert refused == {}


def test_a_step_that_fails_leaves_the_rest(service: FrameService) -> None:
    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None

    def ask(params: dict[str, Any]) -> Answer:
        if params["model"] == OPUS:
            return Answer(ANALYSIS_V6, False, 0.07, OPUS)
        raise AiUnavailable("the month's limit")

    found = compose(service.images, item, service.daily.job.sources(item), ask)
    (view,) = found["composition"]["views"]
    assert [m["title"] for m in view["marks"]] == ["Fudżi", "Horyzont"]  # unchecked
    assert view["grid"] == "thirds"  # measured
    assert view["text"].startswith("Fala zamyka lewą stronę.")  # the draft, unwritten
    assert found[CHECKED] == [] and PROSE_KEY not in found


def _old_page(service: FrameService, **extra: Any) -> None:
    """A study written before: its takes as the old prompt drew them."""
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
            data={**essay.model_dump(), CHECK_ROUND: 3, **extra},
        )
    )


def test_old_pages_are_written_again_as_the_owner_lets_them(
    service: FrameService, monkeypatch: Any
) -> None:
    monkeypatch.setattr("frame_server.ai.composition.LET_ALL", 0)  # a round he was not asked of
    _catalogue(service)
    job = service.ai.jobs[KIND]
    assert isinstance(job, ComposeJob)
    item = service.library.get("met:1")
    assert item is not None
    _old_page(service)
    old = service.library.note("met:1", STUDY)
    assert old is not None
    # Shown as today, under the new name, until written again.
    essay = service.study.essay(item)
    assert essay is not None and [v.title for v in essay.composition.views] == [TAKE]
    assert not job.wanted(item)  # not let yet
    job.let(["met:2"])
    assert not job.wanted(item)
    job.let(["met:1"])
    assert job.wanted(item)
    assert service.library.get_state(REWORK_KEY) == ["met:1"]
    params = job.params(item)
    assert params["system"][0]["text"] == COMPOSITION_SYSTEM

    def ask(more: dict[str, Any]) -> Answer:
        return Answer(None, True, 0.0, "o")  # the check refused: the take stays

    answer = job.revise(item, params, Answer(pixels(ANALYSIS), False, 0.2, "o"), ask)
    note = Note(
        item_id="met:1",
        kind=KIND,
        model="o",
        prompt_version=job.prompt_version,
        source_hash=job.source_hash(item),
        data=answer.data or {},
    )
    job.apply(item, service.library.save_note(note))
    page = service.library.note("met:1", STUDY)
    assert page is not None and page.data[CHECK_ROUND] == ROUND
    views = page.data["composition"]["views"]
    assert [v["title"] for v in views] == [TAKE]
    assert views[0]["marks"][0]["shape"] == "rhythm"
    assert page.data[BEFORE] == old.data["composition"]  # kept to go back to
    assert page.data["teaser"] == old.data["teaser"]  # the rest of the page as it was
    assert not job.wanted(item)  # once

    # A page left without its composition gets it unasked.
    _old_page(service, composition={"views": []})
    job.let([])
    assert job.wanted(item)
    # All of them, once let.
    _old_page(service)
    job.let([])
    assert not job.wanted(item)
    job.let(True)
    assert job.wanted(item)


def test_a_take_under_another_title_counts(service: FrameService) -> None:
    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    retitled = {"composition": {"views": [{**ANALYSIS["composition"]["views"][0]}]}}
    retitled["composition"]["views"][0]["title"] = "Analiza kompozycji: Trouville"

    found = compose(
        service.images, item, service.daily.job.sources(item), _pipeline([], pixels(retitled))
    )
    views = found["composition"]["views"]
    assert [v["title"] for v in views] == [TAKE]
    assert views[0]["marks"][0]["title"] == "Rytm łodzi"


def test_an_answer_without_a_take_is_asked_again_when_let(service: FrameService) -> None:
    _catalogue(service)
    job = service.ai.jobs[KIND]
    assert isinstance(job, ComposeJob)
    item = service.library.get("met:1")
    assert item is not None
    _old_page(service)
    job.let(["met:1"])
    params = job.params(item)
    empty = {"composition": {"views": [{"title": "Analiza kompozycji", "marks": []}]}}
    answer = job.revise(item, params, Answer(empty, False, 0.2, "o"), lambda p: p)
    assert answer.data is not None and answer.data["unusable"] is True
    assert answer.data["answer"] == empty  # kept, to see why
    note = Note(
        item_id="met:1",
        kind=KIND,
        model="o",
        prompt_version=job.prompt_version,
        source_hash=job.source_hash(item),
        data=answer.data,
    )
    job.apply(item, service.library.save_note(note))
    job.forget()
    # Not waiting for ever: shown as failed, and not paid for again by itself.
    assert job.failed() == {"met:1"} and not job.wanted(item)
    job.let(["met:1"])  # let again: asked once more
    assert service.library.note("met:1", KIND) is None
    assert job.failed() == set() and job.wanted(item)


def test_the_round_of_the_study_sheet_is_let_for_every_page(service: FrameService) -> None:
    # Mateusz 2026-11-12: "Przeróbmy proszę wszystkie dotychczasowe."
    assert ROUND == LET_ALL == 8
    _catalogue(service)
    job = service.ai.jobs[KIND]
    assert isinstance(job, ComposeJob)
    item = service.library.get("met:1")
    assert item is not None
    _old_page(service, **{CHECK_ROUND: 7})
    assert job.rework() == [] and job.wanted(item)  # no list to set
    # The one he picked among a page's analyses stays, and a page of this round too.
    _old_page(service, **{CHECK_ROUND: 7, CHOSEN: True})
    job.forget()
    assert not job.wanted(item)
    _old_page(service, **{CHECK_ROUND: ROUND})
    job.forget()
    assert not job.wanted(item)


def test_what_wikipedia_says_of_the_composition_comes_first() -> None:
    text = "Intro.\n\n== History ==\n" + "x" * 500 + "\n\n== Composition ==\nA pyramid.\n"
    found = _sections_first(text, ("compos",))
    assert found.index("== Composition ==") < found.index("== History ==")
    assert found.startswith("Intro.")


def test_the_owner_lets_pages_be_written_again(tmp_path: Any, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient
    from test_daily import _app

    monkeypatch.setattr("frame_server.ai.composition.LET_ALL", 0)
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        _catalogue(svc)
        _old_page(svc)
        shown = client.get("/api/ai/composition").json()
        assert shown == {"rework": [], "waiting": [], "failed": [], "done": []}
        shown = client.put("/api/ai/composition", json={"rework": ["met:1"]}).json()
        assert shown["rework"] == ["met:1"] and shown["waiting"] == ["met:1"]
        assert client.put("/api/ai/composition", json={"rework": True}).json()["rework"] is True


def _made_again(service: FrameService, item_id: str = "met:1") -> None:
    """The analysis asked for anew, as the worker makes it (the check refused)."""
    job = service.ai.jobs[KIND]
    assert isinstance(job, ComposeJob)
    item = service.library.get(item_id)
    assert item is not None and job.wanted(item)
    params = job.params(item)
    answer = job.revise(
        item,
        params,
        Answer(pixels(ANALYSIS), False, 0.2, "o2"),
        lambda p: Answer(None, True, 0, "o"),
    )
    note = Note(
        item_id=item_id,
        kind=KIND,
        model="o2",
        prompt_version=job.prompt_version,
        source_hash=job.source_hash(item),
        data=answer.data or {},
    )
    job.apply(item, service.library.save_note(note))


def test_the_owner_asks_for_the_analysis_anew_and_picks_one(tmp_path: Any) -> None:
    from fastapi.testclient import TestClient
    from test_ai import GOOD_KEY
    from test_daily import _app

    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        _catalogue(svc)
        assert client.post("/api/study/met:1/composition").status_code == 409  # no key
        svc.ai_config.set_key(GOOD_KEY)
        assert client.post("/api/study/met:1/composition").status_code == 409  # no page
        _old_page(svc, **{CHECK_ROUND: ROUND})
        job = svc.ai.jobs[KIND]
        assert isinstance(job, ComposeJob)
        item = svc.library.get("met:1")
        assert item is not None and not job.wanted(item)  # up to date: nothing by itself
        first = client.get("/api/study/met:1").json()["work"]
        assert first["composition_versions"] == [] and first["composition_pending"] is False

        state = client.post("/api/study/met:1/composition").json()
        assert state == {"pending": True, "versions": 1}  # the one shown kept first
        work = client.get("/api/study/met:1").json()["work"]
        assert work["composition_pending"] is True
        assert [v["shown"] for v in work["composition_versions"]] == [True]
        assert work["composition"] == first["composition"]  # shown until the new one comes

        _made_again(svc)
        assert client.get("/api/study/met:1/composition").json() == {
            "pending": False,
            "versions": 2,
        }
        work = client.get("/api/study/met:1").json()["work"]
        assert [v["shown"] for v in work["composition_versions"]] == [False, True]
        assert work["composition"]["views"][0]["marks"][0]["shape"] == "rhythm"
        assert not job.wanted(item)  # made once

        # And once more: three kept.
        client.post("/api/study/met:1/composition")
        _made_again(svc)
        page = svc.library.note("met:1", STUDY)
        assert page is not None and len(page.data["composition_versions"]) == 3

        # The owner goes back to the first: shown, and left be by a rework of all.
        assert client.put("/api/study/met:1/composition", json={"shown": 0}).status_code == 200
        work = client.get("/api/study/met:1").json()["work"]
        assert [v["shown"] for v in work["composition_versions"]] == [True, False, False]
        assert work["composition"] == first["composition"]
        job.let(True)
        assert not job.wanted(item)
        assert client.put("/api/study/met:1/composition", json={"shown": 7}).status_code == 404


def test_an_analysis_asked_anew_that_gives_no_take(service: FrameService) -> None:
    _catalogue(service)
    job = service.ai.jobs[KIND]
    assert isinstance(job, ComposeJob)
    item = service.library.get("met:1")
    assert item is not None
    _old_page(service, **{CHECK_ROUND: ROUND})
    assert job.again(item) and job.pending("met:1")
    params = job.params(item)
    empty = {"composition": {"views": [{"title": "Analiza kompozycji", "marks": []}]}}
    answer = job.revise(item, params, Answer(empty, False, 0.2, "o"), lambda p: p)
    note = Note(
        item_id="met:1",
        kind=KIND,
        model="o",
        prompt_version=job.prompt_version,
        source_hash=job.source_hash(item),
        data=answer.data or {},
    )
    job.apply(item, service.library.save_note(note))
    # No longer on its way, the page as it was, and not asked again by itself.
    assert not job.pending("met:1") and not job.wanted(item)
    page = service.library.note("met:1", STUDY)
    assert page is not None and len(page.data["composition_versions"]) == 1
    assert job.again(item) and job.wanted(item)  # asked anew: once more
