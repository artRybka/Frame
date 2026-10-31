"""Discover's work of the day: the pick, the page Claude writes, the API."""

from __future__ import annotations

import copy
import io
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from PIL import Image
from test_ai import GOOD_KEY, FakeAnthropic

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import OPUS
from frame_server.ai.daily import clean, short
from frame_server.config import Settings
from frame_server.daily import HISTORY_KEY, of_season, round_anniversary
from frame_server.library import Item, ItemKind
from frame_server.service import FrameService
from frame_server.web import create_app

DAY = date(2026, 10, 30)
DESCRIPTION = (
    "A great wave rises over three boats while Mount Fuji sits small in the trough. "
    "The print belongs to the series Thirty-six Views of Mount Fuji. "
    "It is among the most reproduced works of Japanese art."
)
ANSWER: dict[str, Any] = {
    "title": "Wielka fala w Kanagawie",
    "teaser": (
        "Fala z pazurami i święta góra schowana w jej dolinie. "
        "Drugie zdanie, które już nie zmieściłoby się w dwóch wierszach kafelka."
    ),
    "focus": {"x": 0.64, "y": 1.4},
    "why_today": "Jutro mija 266 lat od urodzin Hokusaia.",
    "headline": "Pocztówka z pielgrzymki.",
    "context": ["Hokusai miał około siedemdziesięciu lat.", "Nowością był błękit pruski."],
    "artist": "Katsushika Hokusai, malarz i rysownik z Edo, zmieniał imię ponad trzydzieści razy.",
    "composition": {
        "views": [
            {
                "title": "Spojrzenie",
                "grid": "none",
                "text": "Oko biegnie łukiem fali do Fudżi.",
                "marks": [
                    {
                        "shape": "arrow",
                        "points": [
                            {"x": 0.0, "y": 0.97},
                            {"x": 0.2, "y": 0.3},
                            {"x": 0.4, "y": 0.1},
                        ],
                        "title": "Łuk fali",
                        "text": "grzywa w pazurach",
                    },
                    {
                        "shape": "loop",
                        "points": [{"x": 0.64, "y": 0.66}, {"x": 1.7, "y": -0.2}],
                        "title": "Fudżi",
                        "text": "mała i nieruchoma",
                    },
                    {"shape": "triangle", "points": [{"x": 0.3, "y": 0.5}], "title": "Za mało"},
                    {"shape": "spiral", "points": [{"x": 0.3, "y": 0.5}], "title": "Nie ma"},
                ],
            },
            {"title": "Pusta", "grid": "golden", "text": "", "marks": []},
            {
                "title": "Geometria",
                "grid": "fibonacci",
                "text": "Szczyt w złotym punkcie.",
                "marks": [
                    {
                        "shape": "rect",
                        "points": [{"x": 0.1, "y": 0.1}, {"x": 0.3, "y": 0.5}],
                        "title": "Kartusz",
                        "text": "",
                    }
                ],
            },
        ],
    },
    "colour": "Dwa błękity i biel papieru.",
    "details": [
        {
            "title": "Pazury piany",
            "text": "Grzbiet rozpada się w palce.",
            "x": 0.4,
            "y": 0.1,
            "w": 0.2,
            "h": 0.3,
        },
        {
            "title": "Wioślarze",
            "text": "Twarze to kilka kresek.",
            "x": 0.9,
            "y": 0.75,
            "w": 0.3,
            "h": 0.4,
        },
        {"title": "", "text": "Bez tytułu.", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
        {"title": "Bez kadru", "text": "", "x": "lewo", "y": 0.1, "w": 0.2, "h": 0.2},
    ],
    "on_frame": "Błękit i biel to czyste tusze ramki.",
    "similar": [
        {"id": "met:2", "why": "ta sama seria"},
        {"id": "met:404", "why": "nie z listy"},
        {"id": "met:2", "why": "drugi raz"},
    ],
    "legacy": [
        {
            "year": "1905",
            "who": "Claude Debussy",
            "title": "Morze",
            "text": "Fala na okładce partytury.",
            "quote": "",
            "search": "Debussy La Mer",
        }
    ],
    "sources": ["obraz", "Wikipedia", "nie-źródło"],
}


#: The pictures in these tests are 900 × 600 px: the model answers in pixels.
SIZE = (900, 600)


def pixels(answer: dict[str, Any], size: tuple[int, int] = SIZE) -> dict[str, Any]:
    """``answer`` as the model gives it: its fractions in pixels of the picture."""
    out = copy.deepcopy(answer)
    w, h = size

    def scale(raw: dict[str, Any], keys: str) -> None:
        for key in keys:
            if isinstance(raw.get(key), int | float):
                raw[key] = raw[key] * (w if key in "xw" else h)

    if isinstance(out.get("focus"), dict):
        scale(out["focus"], "xy")
    for view in (out.get("composition") or {}).get("views") or out.get("views") or []:
        for mark in view.get("marks") or []:
            for point in mark.get("points") or []:
                scale(point, "xy")
    for detail in out.get("details") or []:
        scale(detail, "xywh")
    return out


ANSWER_PX = pixels(ANSWER)


def written(fake: FakeAnthropic) -> list[dict[str, Any]]:
    """The questions that wrote a page (not the checks of its composition)."""
    return [
        p
        for p in fake.asked
        if p["model"] == OPUS and not p["system"][0]["text"].startswith("Sprawdzasz")
    ]


def _offline() -> httpx.Client:
    """Wikidata and Wikipedia answer nothing in tests."""
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))


def _add(service: FrameService, item_id: str, **kw: Any) -> Item:
    kw.setdefault("kind", ItemKind.ARTWORK)
    kw.setdefault("suitability", 0.7)
    kw.setdefault("width", 3000)
    kw.setdefault("height", 2000)
    item = service.library.upsert(
        Item(id=item_id, source=item_id.split(":")[0], source_id=item_id, **kw)
    )
    for path in (service.images.thumb_path(item), service.images.image_path(item)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg_bytes((40, 70, 140), (900, 600)))
    return item


def _catalogue(service: FrameService) -> None:
    _add(
        service,
        "met:1",
        title="Under the Wave off Kanagawa",
        artist="Katsushika Hokusai",
        date_text="ca. 1830–32",
        year=1831,
        description=DESCRIPTION,
        suitability=0.95,
    )
    _add(service, "met:2", title="South Wind, Clear Sky", artist="Katsushika Hokusai", year=1831)
    _add(service, "met:3", title="Water Lilies", artist="Claude Monet", year=1906)
    _add(service, "met:4", title="The Harvesters", artist="Pieter Bruegel", year=1565)


def _today_is(service: FrameService, item_id: str) -> None:
    """Today's pick made, so the page tests do not hang on the date."""
    service.library.set_state(HISTORY_KEY, {date.today().isoformat(): item_id})


@pytest.fixture
def offline(service: FrameService) -> FrameService:
    service.daily.job._http = _offline()
    service.later.search = lambda query, limit: (0, [], [])
    return service


def test_the_work_of_the_day_is_picked_once_and_kept(offline: FrameService) -> None:
    _catalogue(offline)
    first = offline.daily.pick(DAY)
    assert first is not None
    _add(offline, "met:5", title="Better still", artist="Someone Else", suitability=0.99)
    again = offline.daily.pick(DAY)
    assert again is not None and again.id == first.id
    assert offline.daily.history() == {DAY.isoformat(): first.id}
    assert offline.daily.day_of(first.id) == DAY


def test_a_dark_masterpiece_can_be_the_work_of_the_day(offline: FrameService) -> None:
    # No e-paper threshold: a low score left out Rembrandt and Vermeer.
    _add(offline, "met:9", title="Self-Portrait", artist="Rembrandt", suitability=0.2)
    found = offline.daily.pick(DAY)
    assert found is not None and found.id == "met:9"


def test_an_artist_waits_a_month_and_a_work_a_year(offline: FrameService) -> None:
    _catalogue(offline)
    picked = [offline.daily.pick(DAY + timedelta(days=n)) for n in (0, 1, 2)]
    assert all(picked)
    assert {i.artist for i in picked if i} == {
        "Katsushika Hokusai",
        "Claude Monet",
        "Pieter Bruegel",
    }
    # Hokusai's other print waits for the month, the works shown for the year.
    assert offline.daily.pick(DAY + timedelta(days=3)) is None
    found = offline.daily.pick(DAY + timedelta(days=40))
    hokusai = {"met:1", "met:2"} - {i.id for i in picked if i}
    assert found is not None and {found.id} == hokusai


def test_the_season_and_round_anniversaries() -> None:
    snow = Item(id="a:1", source="a", source_id="1", title="Snow at Louveciennes")
    assert of_season(snow, date(2026, 1, 10)) and not of_season(snow, date(2026, 7, 10))
    born = Item(id="a:2", source="a", source_id="2", artist_bio="Japanese, 1760–1849", year=1831)
    assert round_anniversary(born, date(2049, 3, 1))  # 1849 + 200
    assert not round_anniversary(born, date(2026, 3, 1))


def test_an_answer_is_cleaned() -> None:
    essay = clean(ANSWER, ["met:2", "met:3"])
    assert essay is not None
    assert essay.teaser == "Fala z pazurami i święta góra schowana w jej dolinie."  # fits the tile
    assert essay.focus is not None and (essay.focus.x, essay.focus.y) == (0.64, 1.0)
    assert essay.headline == "Pocztówka z pielgrzymki"
    views = essay.composition.views
    # An empty take goes; "Geometria" comes first, whatever the answer's order.
    assert [v.title for v in views] == ["Geometria", "Spojrzenie"]
    assert [m.title for m in views[1].marks] == ["Łuk fali", "Fudżi"]
    assert (views[1].marks[1].points[1].x, views[1].marks[1].points[1].y) == (1.0, 0.0)
    assert views[0].grid == "none"  # not a grid the app draws
    # Drawn by 0.42 apps as numbered points and lines.
    points = essay.composition.points
    assert [(p.title, p.x, p.y) for p in points] == [("Kartusz", 0.2, 0.3)]
    assert essay.composition.lines == []
    assert [(s.id, s.why) for s in essay.similar] == [("met:2", "ta sama seria")]
    # Fragments stay on the picture; one without a title or a box goes.
    assert [d.title for d in essay.details] == ["Pazury piany", "Wioślarze"]
    boat = essay.details[1]
    assert (boat.x, boat.y, boat.w, boat.h) == (0.7, 0.6, 0.3, 0.4)
    assert essay.sources == ["obraz", "Wikipedia"]
    assert clean({**ANSWER, "teaser": "  "}, []) is None
    assert short("Bardzo długie zdanie " * 10, 40) == "Bardzo długie zdanie Bardzo długie…"


def test_rhythms_are_no_longer_shown() -> None:
    beats = [{"x": 0.1 * n, "y": 0.5} for n in range(1, 10)]
    rhythm = {
        "title": "Rytm",
        "grid": "none",
        "text": "Fale powtarzają się jak takty.",
        "marks": [{"shape": "rhythm", "points": beats, "title": "Grzbiety fal", "text": "co krok"}],
    }
    composition = {"views": [*ANSWER["composition"]["views"], rhythm]}
    essay = clean({**ANSWER, "composition": composition}, [])
    assert essay is not None
    assert [v.title for v in essay.composition.views] == ["Geometria", "Spojrzenie"]


def _app(tmp_path: Path) -> Any:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    svc.daily.job._http = _offline()
    svc.later.search = lambda query, limit: (0, [], [])
    return app


def test_without_a_key_the_page_shows_what_the_museum_says(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        _catalogue(app.state.service)  # after the start, which tidies the library
        _today_is(app.state.service, "met:1")
        work = client.get("/api/daily").json()
        assert work["item"]["item"]["id"] == "met:1"
        assert work["title"] == "Under the Wave off Kanagawa"
        assert work["written"] is False and work["writing"] is False
        assert work["teaser"].startswith("A great wave rises")
        assert work["context"] == [DESCRIPTION]
        assert work["headline"] == "Co mówi muzeum" and work["artist"] == ""
        assert work["focus"] is None
        assert work["composition"] is None
        assert [s["item"]["item"]["id"] for s in work["similar"]] == ["met:2"]
        assert work["similar"][0]["why"] == "ten sam autor"

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        assert client.get(f"/api/daily?day={tomorrow}").status_code == 400
        assert client.get("/api/daily?day=2001-01-01").status_code == 404


def test_claude_writes_the_page(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = ANSWER_PX
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False))
    with TestClient(app) as client:
        _catalogue(svc)
        _today_is(svc, "met:1")
        svc.ai.start()
        try:
            work = client.get("/api/daily?wait=10").json()
        finally:
            svc.ai.stop()
        assert work["written"] is True and work["model"] == OPUS
        assert work["title"] == "Wielka fala w Kanagawie"
        assert work["why_today"] == "Jutro mija 266 lat od urodzin Hokusaia."
        assert work["headline"] == "Pocztówka z pielgrzymki"
        assert work["artist"].startswith("Katsushika Hokusai, malarz")
        assert work["focus"] == {"x": 0.64, "y": 1.0}
        assert [v["title"] for v in work["composition"]["views"]] == ["Geometria", "Spojrzenie"]
        assert work["composition"]["views"][1]["marks"][0]["shape"] == "arrow"
        assert [(s["item"]["item"]["id"], s["why"]) for s in work["similar"]] == [
            ("met:2", "ta sama seria")
        ]
        assert work["legacy"][0]["who"] == "Claude Debussy" and work["legacy"][0]["item"] is None
        details = work["details"]
        assert [d["title"] for d in details] == ["Pazury piany", "Wioślarze"]
        assert details[0]["image"].startswith(f"/api/daily/detail?day={date.today()}&n=0&v=")
        # Cut from the original (900 × 600 here): 0.3 × 0.4 of it.
        cut = client.get(details[1]["image"])
        assert cut.status_code == 200 and cut.headers["content-type"] == "image/jpeg"
        assert Image.open(io.BytesIO(cut.content)).size == (270, 240)
        assert client.get(f"/api/daily/detail?day={date.today()}&n=5").status_code == 404

        (asked,) = written(fake)
        content = asked["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert "OBRAZ: 900 × 600 px" in content[1]["text"]  # the pixels it points in
        assert "met:2 | Katsushika Hokusai" in content[1]["text"]  # the works to choose from
        assert asked["timeout"] > 120
        # Its composition checked over the marks drawn on the picture: the
        # clean picture, then each take drawn.
        (check,) = [p for p in fake.asked if p not in written(fake)]
        images = [b for b in check["messages"][0]["content"] if b["type"] == "image"]
        assert len(images) == 1 + len(work["composition"]["views"])

        # Asked once: the page is kept.
        client.get("/api/daily")
        assert len(written(fake)) == 1


def test_the_switch_turns_the_page_off(offline: FrameService) -> None:
    _catalogue(offline)
    offline.ai_config.set_key(GOOD_KEY)
    item = offline.daily.pick(DAY)
    assert item is not None
    assert offline.daily.ask(item) is not None
    offline.ai_config.update(AiConfigUpdate(daily=False))
    assert offline.daily.ask(item) is None
