"""Discover's work of the day: the pick, the page Claude writes, the API."""

from __future__ import annotations

import copy
import io
import random
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageOps
from test_ai import GOOD_KEY, FakeAnthropic

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import OPUS
from frame_server.ai.daily import clean, short
from frame_server.ai.study import KIND as STUDY
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
                "title": "Geometria detali",
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
    service.artists.search = lambda query, limit: (0, [], [])
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


def test_the_work_of_the_day_drawn_again(offline: FrameService) -> None:
    _catalogue(offline)
    first = offline.daily.pick(DAY)
    assert first is not None
    second = offline.daily.again(DAY)
    # Another work by another artist; the day keeps it.
    assert second is not None and second.artist != first.artist
    assert offline.daily.pick(DAY) == second
    assert offline.daily.history() == {DAY.isoformat(): second.id}
    third = offline.daily.again(DAY)
    assert third is not None and third.artist not in {first.artist, second.artist}
    # Nothing left: the day keeps the last one.
    assert offline.daily.again(DAY) is None
    assert offline.daily.pick(DAY) == third
    # The next day draws as usual.
    assert offline.daily.skipped(DAY + timedelta(days=1)) == []


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
    assert [v.title for v in views] == ["Geometria", "Geometria detali"]
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
    assert [v.title for v in essay.composition.views] == ["Geometria", "Geometria detali"]


def _app(tmp_path: Path) -> Any:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    svc.daily.job._http = _offline()
    svc.later.search = lambda query, limit: (0, [], [])
    svc.artists.search = lambda query, limit: (0, [], [])
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


def test_konfiguracja_draws_another_work_of_the_day(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        _catalogue(app.state.service)
        _today_is(app.state.service, "met:1")
        answer = client.post("/api/daily/again")
        assert answer.status_code == 200
        drawn = answer.json()
        assert drawn["day"] == date.today().isoformat()
        assert drawn["item"]["item"]["id"] not in {"met:1", "met:2"}  # not Hokusai again
        assert client.get("/api/daily").json()["item"]["item"]["id"] == drawn["item"]["item"]["id"]
        assert client.post("/api/daily/again").status_code == 200
        assert client.post("/api/daily/again").status_code == 409


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
        assert [v["title"] for v in work["composition"]["views"]] == [
            "Geometria",
            "Geometria detali",
        ]
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


def test_other_works_by_the_artist(offline: FrameService) -> None:
    _catalogue(offline)
    for n in range(5, 13):
        _add(offline, f"met:{n}", title=f"View {n} of Mount Fuji", artist="Katsushika Hokusai")
    _add(offline, "met:20", title="View 5 of Mount Fuji", artist="Katsushika Hokusai")  # twin
    _add(offline, "met:21", title="Fine Wind", artist="Katsushika Hokusai", favorite=True)
    _add(offline, "met:22", title="A Bowl", artist="Unknown")
    item = offline.library.get("met:1")
    assert item is not None
    works = offline.artists.works(item, {"met:2"})
    ids = [w.id for w in works]
    assert len(ids) == 6 and ids[0] == "met:21"  # the owner's favourites first
    assert not {"met:1", "met:2"} & set(ids)  # not the work, not "Podobne dzieła"
    assert len({w.title for w in works}) == 6
    # The same six each time the page opens.
    assert [w.id for w in offline.artists.works(item, {"met:2"})] == ids
    # Enough in the catalogue: the museums are not asked.
    assert offline.artists.look_soon(item, len(ids)) is False
    bowl = offline.library.get("met:22")
    assert bowl is not None and offline.artists.works(bowl) == []


def test_too_few_by_the_artist_asks_the_museums_once(offline: FrameService) -> None:
    _catalogue(offline)
    asked: list[str] = []

    def search(query: str, limit: int) -> tuple[int, list[Item], list[str]]:
        asked.append(query)
        hits = [
            Item(
                id="aic:7",
                source="aic",
                source_id="7",
                title="Red Fuji",
                artist="Katsushika Hokusai",
            ),
            Item(id="aic:8", source="aic", source_id="8", title="Copy", artist="Hiroshige"),
        ]
        return 2, hits, []

    offline.artists.search = search
    item = offline.library.get("met:1")
    assert item is not None
    assert [w.id for w in offline.artists.works(item)] == ["met:2"]
    offline.artists.look(item)
    assert [w.id for w in offline.artists.works(item)] == ["met:2", "aic:7"]
    # Asked once, also when the museums have too few.
    assert offline.artists.look_soon(item, 2) is False
    assert asked == ["Katsushika Hokusai"]


def _print(seed: int) -> Image.Image:
    """A made-up print: shapes in many tones, different for each seed."""
    rng = random.Random(seed)
    img = Image.new("RGB", (900, 600), (235, 225, 200))
    draw = ImageDraw.Draw(img)
    for _ in range(160):
        x, y = rng.randrange(900), rng.randrange(600)
        w, h = rng.randrange(10, 120), rng.randrange(10, 120)
        tone = tuple(rng.randrange(256) for _ in range(3))
        shape = draw.ellipse if rng.random() < 0.5 else draw.rectangle
        shape((x, y, x + w, y + h), fill=tone, outline=(20, 20, 20))
    return img


def _copy_of(img: Image.Image) -> Image.Image:
    """The same print photographed elsewhere: greyer paper, a margin, a crop."""
    tinted = Image.blend(img, Image.new("RGB", img.size, (150, 150, 150)), 0.25)
    cropped = tinted.crop((30, 0, 870, 580))
    return ImageOps.expand(cropped, border=40, fill=(200, 200, 195)).resize((640, 460))


def _picture(service: FrameService, item_id: str, img: Image.Image) -> None:
    item = service.library.get(item_id) or Item(
        id=item_id, source=item_id.split(":")[0], source_id=item_id
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=85)


def test_one_picture_is_told_whatever_its_title(tmp_path: Path) -> None:
    from frame_server.library.likeness import SAME, keypoints, matches

    def points(img: Image.Image, name: str) -> Any:
        path = tmp_path / f"{name}.jpg"
        img.save(path, "JPEG")
        found = keypoints(path)
        assert found is not None
        return found

    wave = points(_print(1), "a")
    assert matches(wave, points(_copy_of(_print(1)), "b")) >= SAME
    assert matches(wave, points(_print(2), "c")) < SAME
    plain = tmp_path / "plain.jpg"
    plain.write_bytes(jpeg_bytes((40, 70, 140), (900, 600)))
    assert keypoints(plain) is None  # nothing to go by: no opinion


def test_other_works_leave_out_copies_from_other_sources(offline: FrameService) -> None:
    """The Great Wave from Commons under its Polish title, and the Met's
    under another English one, are the studied work: not "other works"."""
    _catalogue(offline)
    _add(offline, "wmc:wave", title="Wielka fala w Kanagawie", artist="Katsushika Hokusai")
    _add(offline, "aic:wave", title="The Great Wave off Kanagawa", artist="Hokusai")
    _add(offline, "aic:wind", title="Fine Wind, Clear Morning", artist="Katsushika Hokusai")
    _add(offline, "wmc:wind", title="Czerwona Fudżi", artist="Katsushika Hokusai")
    _picture(offline, "met:1", _print(1))
    _picture(offline, "met:2", _print(2))
    _picture(offline, "wmc:wave", _copy_of(_print(1)))
    _picture(offline, "aic:wave", _copy_of(_print(1)).rotate(0.5))
    _picture(offline, "aic:wind", _print(20))
    _picture(offline, "wmc:wind", _copy_of(_print(20)))
    item = offline.library.get("met:1")
    assert item is not None
    ids = {w.id for w in offline.artists.works(item)}
    # Not the work itself in any copy; another work once.
    assert ids in ({"met:2", "aic:wind"}, {"met:2", "wmc:wind"})


def test_the_day_page_is_the_works_study(tmp_path: Path) -> None:
    """Once written, a day's page is its work's study: no new question,
    kept with the day it was written, "why today" only on its day."""
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = ANSWER_PX
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False))
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    with TestClient(app) as client:
        _catalogue(svc)
        svc.library.set_state(HISTORY_KEY, {yesterday: "met:1"})
        svc.ai.start()
        try:
            work = client.get(f"/api/daily?day={yesterday}&wait=10").json()
        finally:
            svc.ai.stop()
        assert work["written"] is True and work["previous"] == []
        for _ in range(40):  # made the study as the question ends
            if svc.study.requested("met:1"):
                break
            time.sleep(0.05)
        assert svc.study.requested("met:1")
        daily_note = svc.library.note("met:1", "daily")
        study_note = svc.library.note("met:1", STUDY)
        assert daily_note is not None and study_note is not None
        assert study_note.created_at == daily_note.created_at
        view = client.get("/api/study/met:1").json()
        assert view["status"] == "ready" and view["work"]["why_today"] == ""
        assert view["work"]["title"] == "Wielka fala w Kanagawie"
        assert len(written(fake)) == 1

        # A day's page from before the two were one: its study on the next round.
        svc.library.delete_notes(STUDY, "met:1")
        svc.library.set_state("study_items", [])
        svc.daily.adopt_all()
        assert svc.study.requested("met:1") and svc.study.essay(svc.library.get("met:1"))  # type: ignore[arg-type]
        assert len(written(fake)) == 1
