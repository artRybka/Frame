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
from PIL import Image, ImageDraw, ImageOps, ImageStat
from test_ai import GOOD_KEY, FakeAnthropic, _message

from frame_server import daily as daily_module
from frame_server import sizes
from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU, OPUS, SONNET
from frame_server.ai.daily import (
    INCOMPLETE,
    TAKE,
    Pigment,
    clean,
    missing,
    short,
    unfinished,
    vary_hedges,
)
from frame_server.ai.pl_text import PolishText
from frame_server.ai.study import KIND as STUDY
from frame_server.config import Settings
from frame_server.daily import HISTORY_KEY, of_season, round_anniversary
from frame_server.library import Item, ItemKind
from frame_server.library.models import Note, SharperCopy
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
        {"id": "met:5", "why": "ta sama epoka"},
        {"id": "met:404", "why": "nie z listy"},
        {"id": "met:5", "why": "drugi raz"},
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
    "born": 1760,
    "died": 1849,
    "milestones": [
        {"year": 1831, "text": "seria „36 widoków góry Fudżi”."},
        {"year": 1779, "text": "pierwsze drzeworyty"},
        {"year": 1900, "text": "po śmierci"},
    ],
    "events": [
        {"year": 1825, "text": "edykt o odpędzaniu obcych statków."},
        {"year": 1600, "text": "przed urodzinami"},
    ],
    "pigments": [
        {
            "name": "błękit pruski",
            "hex": "#1f3a6b",
            "where": "fala i niebo",
            "text": "Sprowadzany z Europy.",
        },
        {"name": "bez barwy", "hex": "niebieski", "where": "", "text": ""},
    ],
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


def composing(params: dict[str, Any]) -> bool:
    """A question about the composition: its analysis, its check, its
    movement or its text written last."""
    return params["system"][0]["text"].startswith(
        ("Sprawdzasz", "Piszesz „Analizę", "Dopisujesz", "Piszesz ostateczny tekst")
    )


def written(fake: FakeAnthropic) -> list[dict[str, Any]]:
    """The questions that wrote a page (not its composition)."""
    return [p for p in fake.asked if p["model"] == OPUS and not composing(p)]


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
        terms=["style:ukiyo-e"],
    )
    _add(
        service,
        "met:2",
        title="South Wind, Clear Sky",
        artist="Katsushika Hokusai",
        year=1831,
        terms=["style:ukiyo-e"],
    )
    _add(service, "met:3", title="Water Lilies", artist="Claude Monet", year=1906)
    _add(service, "met:4", title="The Harvesters", artist="Pieter Bruegel", year=1565)


def _like(service: FrameService) -> None:
    """A work like the Great Wave by another artist ("Podobne dzieła")."""
    _add(
        service,
        "met:5",
        title="Evening Snow at Kanbara",
        artist="Utagawa Hiroshige",
        year=1833,
        terms=["style:ukiyo-e"],
    )


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
    essay = clean(ANSWER, ["met:5", "met:3"])
    assert essay is not None
    assert essay.teaser == "Fala z pazurami i święta góra schowana w jej dolinie."  # fits the tile
    assert essay.focus is not None and (essay.focus.x, essay.focus.y) == (0.64, 1.0)
    assert essay.headline == "Pocztówka z pielgrzymki"
    views = essay.composition.views
    # One take: an empty one and "Geometria detali" go, "Geometria" is the analysis.
    assert [v.title for v in views] == [TAKE]
    assert [m.title for m in views[0].marks] == ["Kartusz"]
    assert views[0].grid == "none"  # not a grid the app draws
    # Drawn by 0.42 apps as numbered points and lines.
    points = essay.composition.points
    assert [(p.title, p.x, p.y) for p in points] == [("Kartusz", 0.2, 0.3)]
    assert essay.composition.lines == []
    assert [(s.id, s.why) for s in essay.similar] == [("met:5", "ta sama epoka")]
    # Fragments stay on the picture; one without a title or a box goes.
    assert [d.title for d in essay.details] == ["Pazury piany", "Wioślarze"]
    boat = essay.details[1]
    assert (boat.x, boat.y, boat.w, boat.h) == (0.7, 0.6, 0.3, 0.4)
    assert essay.sources == ["obraz", "Wikipedia"]
    assert clean({**ANSWER, "teaser": "  "}, []) is None
    assert short("Bardzo długie zdanie " * 10, 40) == "Bardzo długie zdanie Bardzo długie…"


def test_old_rhythms_are_no_longer_shown() -> None:
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
    assert [v.title for v in essay.composition.views] == [TAKE]


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
        _like(app.state.service)
        wave = app.state.service.library.get("met:1")
        app.state.service.library.upsert(
            wave.model_copy(update={"artist_bio": "Japanese, 1760–1849"})
        )
        _today_is(app.state.service, "met:1")
        work = client.get("/api/daily").json()
        assert work["size"] is None  # looked up in the background (here: nothing found)
        app.state.service.library.save_note(
            Note(
                item_id="met:1",
                kind=sizes.KIND,
                model="",
                prompt_version=sizes.VERSION,
                data={"height": 25.7, "width": 37.9},
            )
        )
        work = client.get("/api/daily").json()
        assert work["size"] == {"height": 25.7, "width": 37.9}
        assert work["item"]["item"]["id"] == "met:1"
        assert work["title"] == "Under the Wave off Kanagawa"
        assert work["date"] == "ca. 1830–32"  # the museum's, with no Polish texts
        assert work["written"] is False and work["writing"] is False
        assert work["teaser"].startswith("A great wave rises")
        assert work["context"] == [DESCRIPTION]
        assert work["headline"] == "Co mówi muzeum" and work["artist"] == ""
        assert work["focus"] is None
        assert work["composition"] is None
        # Like it, by another artist: Hokusai's own are "Inne prace artysty".
        assert [s["item"]["item"]["id"] for s in work["similar"]] == ["met:5"]
        assert work["similar"][0]["why"] == ""
        assert [w["item"]["id"] for w in work["by_artist"]] == ["met:2"]
        # The artist's line stays on the work (the years under the name in
        # "O autorze"), not on the works in the lists.
        assert work["item"]["item"]["artist_bio"] == "Japanese, 1760–1849"
        assert (work["born"], work["died"]) == (1760, 1849)  # from the museum, unwritten
        assert work["milestones"] == [] and work["pigments"] == []
        assert work["similar"][0]["item"]["item"]["artist_bio"] == ""

        # Discover's tile: the text at once, without the lists under it.
        tile = client.get("/api/daily?lists=false").json()
        assert tile["item"]["item"]["id"] == "met:1" and tile["partial"] is True
        assert tile["teaser"] == work["teaser"] and tile["similar"] == []
        assert work["partial"] is False

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        assert client.get(f"/api/daily?day={tomorrow}").status_code == 400
        assert client.get("/api/daily?day=2001-01-01").status_code == 404


def test_the_date_under_the_title_is_polish_once_the_texts_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        svc: FrameService = app.state.service
        _catalogue(svc)
        _today_is(svc, "met:1")
        polish = PolishText(title="Wielka fala", frame="", full="", date="ok. 1830–1832")
        monkeypatch.setattr(svc.pl_text, "text", lambda item: polish)
        assert client.get("/api/daily").json()["date"] == "ok. 1830–1832"
        # Texts without a date: the museum's words.
        undated = polish.model_copy(update={"date": ""})
        monkeypatch.setattr(svc.pl_text, "text", lambda item: undated)
        assert client.get("/api/daily").json()["date"] == "ca. 1830–32"


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
        _like(svc)
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
        assert [v["title"] for v in work["composition"]["views"]] == [TAKE]
        assert work["composition"]["views"][0]["marks"][0]["shape"] == "rect"
        assert [(s["item"]["item"]["id"], s["why"]) for s in work["similar"]] == [
            ("met:5", "ta sama epoka")
        ]
        assert work["legacy"][0]["who"] == "Claude Debussy" and work["legacy"][0]["item"] is None
        # The artist's line of life, in order and within it; the paints named.
        assert (work["born"], work["died"]) == (1760, 1849)
        assert [(m["year"], m["text"]) for m in work["milestones"]] == [
            (1779, "pierwsze drzeworyty"),
            (1831, "seria „36 widoków góry Fudżi”"),
        ]
        assert [(p["name"], p["hex"]) for p in work["pigments"]] == [("błękit pruski", "#1F3A6B")]
        assert [(e["year"], e["text"]) for e in work["events"]] == [
            (1825, "edykt o odpędzaniu obcych statków")
        ]
        details = work["details"]
        assert [d["title"] for d in details] == ["Pazury piany", "Wioślarze"]
        assert details[0]["image"].startswith(f"/api/daily/detail?day={date.today()}&n=0&v=")
        # Cut from the original (900 × 600 here): 0.3 × 0.4 of it.
        cut = client.get(details[1]["image"])
        assert cut.status_code == 200 and cut.headers["content-type"] == "image/jpeg"
        assert Image.open(io.BytesIO(cut.content)).size == (270, 240)
        assert client.get(f"/api/daily/detail?day={date.today()}&n=5").status_code == 404
        # Asked on a picture the model reads as it is: its boxes are kept as written.
        kept = svc.library.note("met:1", svc.daily.job.kind)
        assert kept is not None and kept.data["boxes"] == 2

        (asked,) = written(fake)
        content = asked["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert "OBRAZ: 900 × 600 px" in content[1]["text"]  # the pixels it points in
        assert "met:5 | Utagawa Hiroshige" in content[1]["text"]  # the works to choose from
        assert "met:2 | Katsushika Hokusai" not in content[1]["text"]  # not the artist's own
        assert asked["timeout"] > 120
        assert "Analizy kompozycji tu nie piszesz" in asked["system"][0]["text"]
        # Its composition asked apart, then checked over the marks drawn on
        # the picture (the clean picture, then the take drawn), then its movement,
        # then its text written in one voice.
        analysis, check, *rest = [p for p in fake.asked if p not in written(fake)]
        assert analysis["system"][0]["text"].startswith("Piszesz „Analizę kompozycji”")
        assert analysis["messages"][0]["content"][0]["type"] == "image"
        images = [b for b in check["messages"][0]["content"] if b["type"] == "image"]
        assert len(images) == 2 and check["model"] == HAIKU
        assert [p["model"] for p in rest][-2:] == [SONNET, OPUS]

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
    assert len(ids) == 4 and ids[0] == "met:21"  # the owner's favourites first
    assert not {"met:1", "met:2"} & set(ids)  # not the work, not "Podobne dzieła"
    assert len({w.title for w in works}) == 4
    # The same four each time the page opens.
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


#: An answer with the text and the note about the artist and nothing else,
#: as Claude once gave one (Hopper's "Nighthawks", 2026-11-02).
HALF = {
    **ANSWER,
    "composition": {"views": []},
    "colour": "",
    "details": [],
    "on_frame": "",
    "similar": [],
    "legacy": [],
    "sources": [],
}
HALF_PX = pixels(HALF)


def _answers(fake: FakeAnthropic, *pages: dict[str, Any]) -> None:
    """The pages written in turn (the last one from then on); a check of
    the composition gets the page's answer, which it cannot use."""
    left = list(pages)

    def create(**params: Any) -> Any:
        fake.asked.append(params)
        page = left[0] if composing(params) or len(left) == 1 else left.pop(0)
        return _message(page)

    fake.messages.create = create


def _claude(tmp_path: Path, *pages: dict[str, Any]) -> tuple[Any, FrameService, FakeAnthropic]:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    _answers(fake, *pages)
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False))
    return app, svc, fake


def _whole(work: dict[str, Any]) -> bool:
    return bool(work["composition"] and work["colour"] and work["details"] and work["on_frame"])


def test_what_a_page_lacks() -> None:
    assert missing(ANSWER) == []
    assert missing(clean(ANSWER, []).model_dump()) == []  # type: ignore[union-attr]
    half = clean(HALF, [])
    assert half is not None
    assert missing(half.model_dump()) == ["composition", "colour", "details", "on_frame"]
    assert unfinished(half.model_dump())
    assert not unfinished({**half.model_dump(), INCOMPLETE: ["composition"]})
    # A page with only its details missing is whole enough to keep.
    assert not unfinished({**ANSWER, "details": []})


def test_a_half_written_page_is_asked_for_again(tmp_path: Path) -> None:
    app, svc, fake = _claude(tmp_path, HALF_PX, ANSWER_PX)
    with TestClient(app) as client:
        _catalogue(svc)
        _today_is(svc, "met:1")
        svc.ai.start()
        try:
            work = client.get("/api/daily?wait=10").json()
        finally:
            svc.ai.stop()
        assert work["written"] is True and _whole(work)
        assert [v["title"] for v in work["composition"]["views"]] == [TAKE]
        assert len(written(fake)) == 2
        note = svc.library.note("met:1", "daily")
        assert note is not None and INCOMPLETE not in note.data
        client.get("/api/daily")
        assert len(written(fake)) == 2


def test_a_page_half_written_twice_is_kept_as_it_is(tmp_path: Path) -> None:
    app, svc, fake = _claude(tmp_path, HALF_PX)
    with TestClient(app) as client:
        _catalogue(svc)
        _today_is(svc, "met:1")
        svc.ai.start()
        try:
            work = client.get("/api/daily?wait=10").json()
        finally:
            svc.ai.stop()
        assert work["written"] is True and work["context"] and not _whole(work)
        note = svc.library.note("met:1", "daily")
        assert note is not None
        assert note.data[INCOMPLETE] == ["colour", "details", "on_frame"]
        # Asked twice, and not again: no question each time the page opens.
        client.get("/api/daily")
        assert len(written(fake)) == 2


def test_a_half_written_page_from_before_is_written_again(tmp_path: Path) -> None:
    """A day's page kept half written (and its study, a copy of it) before
    such answers were asked for twice: written again once, the study too."""
    app, svc, fake = _claude(tmp_path, ANSWER_PX)
    with TestClient(app) as client:
        _catalogue(svc)
        _today_is(svc, "met:1")
        item = svc.library.get("met:1")
        assert item is not None
        half = clean(HALF, [])
        assert half is not None
        for job in (svc.daily.job, svc.study.job):
            svc.library.save_note(
                Note(
                    item_id="met:1",
                    kind=job.kind,
                    model=OPUS,
                    prompt_version=job.prompt_version,
                    source_hash=job.source_hash(item),
                    data=half.model_dump(),
                )
            )
        svc.library.set_state("study_items", ["met:1"])
        assert svc.daily.job.essay(item) is None and svc.study.essay(item) is None
        svc.ai.start()
        try:
            work = client.get("/api/daily?wait=10").json()
            for _ in range(40):  # its study made of it as the question ends
                if svc.study.essay(item) is not None:
                    break
                time.sleep(0.05)
        finally:
            svc.ai.stop()
        assert work["written"] is True and _whole(work)
        assert len(written(fake)) == 1
        view = client.get("/api/study/met:1").json()
        assert view["status"] == "ready" and _whole(view["work"])
        assert view["work"]["why_today"] == "Jutro mija 266 lat od urodzin Hokusaia."


def test_a_study_written_again_mends_the_days_half_page(offline: FrameService) -> None:
    """The study asked for again while the day's page is half written: the
    day's page becomes the study, with its own "why today"."""
    _catalogue(offline)
    offline.ai_config.set_key(GOOD_KEY)
    _today_is(offline, "met:1")
    item = offline.library.get("met:1")
    assert item is not None
    half = clean(HALF, [])
    whole = clean(ANSWER, [])
    assert half is not None and whole is not None
    daily, study = offline.daily.job, offline.study.job
    for job, essay in ((daily, half), (study, whole)):
        offline.library.save_note(
            Note(
                item_id="met:1",
                kind=job.kind,
                model=OPUS,
                prompt_version=job.prompt_version,
                source_hash=job.source_hash(item),
                data={**essay.model_dump(), "why_today": "Dziś" if job is daily else ""},
            )
        )
    assert offline.daily.ask(item) is None  # no question: the study is the page
    essay = daily.essay(item)
    assert essay is not None and essay.composition.views and essay.why_today == "Dziś"


def test_works_made_at_the_same_time(
    offline: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Made within five years of the work, by others, from other countries first."""
    monkeypatch.setattr(daily_module, "SAME_TIME", 3)
    wave = _add(
        offline, "met:1", title="The Great Wave", artist="Katsushika Hokusai",
        artist_bio="Japanese, 1760–1849", year=1831,
    )  # fmt: skip
    _add(offline, "met:2", title="Fine Wind", artist="Katsushika Hokusai", year=1831)
    _add(
        offline,
        "a:1",
        title="Kanbara",
        artist="Utagawa Hiroshige",
        artist_bio="Japanese",
        year=1833,
    )
    _add(
        offline,
        "a:2",
        title="Lake",
        artist="Thomas Cole",
        artist_bio="American, 1801–1848",
        year=1833,
    )
    _add(
        offline,
        "a:3",
        title="Fighting",
        artist="J. M. W. Turner",
        artist_bio="British, 1775–1851",
        year=1829,
    )
    _add(
        offline,
        "a:4",
        title="Liberty",
        artist="Eugène Delacroix",
        artist_bio="French, 1798–1863",
        year=1830,
    )
    _add(
        offline,
        "a:5",
        title="Ox-Bow",
        artist="Thomas Cole",
        artist_bio="American, 1801–1848",
        year=1836,
    )
    _add(
        offline,
        "a:6",
        title="Late",
        artist="Claude Monet",
        artist_bio="French, 1840–1926",
        year=1906,
    )
    _add(offline, "a:7", title="Anon", artist="Unknown", year=1831)
    picked = offline.daily.same_time(wave)
    ids = [w.id for w in picked]
    assert len(ids) == 3
    assert not {"met:1", "met:2", "a:6", "a:7"} & set(ids)  # not his, not 1906, not nobody's
    assert "a:1" not in ids  # another Japanese work waits while other countries have some
    assert len({w.artist for w in picked}) == 3  # Cole once
    assert offline.daily.same_time(wave) == picked  # the same each time
    assert ids[0] not in {w.id for w in offline.daily.same_time(wave, set(ids[:1]))}
    # Too few from other countries: the rest from anywhere.
    assert {"a:1"} <= {w.id for w in offline.daily.same_time(wave, {"a:2", "a:3"})}
    undated = _add(offline, "x:1", title="Undated", artist="Someone")
    assert offline.daily.same_time(undated) == []


def test_old_pages_get_the_line_of_life_and_paints(offline: FrameService) -> None:
    from frame_server.ai.extras import ExtrasJob

    _catalogue(offline)
    item = offline.library.get("met:1")
    assert item is not None
    page = clean(ANSWER, []).model_dump()  # type: ignore[union-attr]
    for key in ("born", "died", "milestones", "events", "pigments"):
        page.pop(key)
    offline.library.save_note(
        Note(item_id="met:1", kind=STUDY, model=OPUS, prompt_version="x", data=page)
    )
    job = ExtrasJob(offline.daily.job)
    assert job.wanted(item)
    assert not job.wanted(offline.library.get("met:2"))  # type: ignore[arg-type]
    params = job.params(item)
    assert params["messages"][0]["content"][0]["type"] == "text"  # no picture: its colours in words
    assert "Katsushika Hokusai" in params["messages"][0]["content"][0]["text"]
    answer = {k: ANSWER[k] for k in ("born", "died", "milestones", "events", "pigments")}
    job.apply(item, Note(item_id="met:1", kind=job.kind, model="", prompt_version="x", data=answer))
    kept = offline.library.note("met:1", STUDY)
    assert kept is not None and kept.data["teaser"] == page["teaser"]
    assert [m["year"] for m in kept.data["milestones"]] == [1779, 1831]
    assert kept.data["pigments"][0]["name"] == "błękit pruski"
    assert [e["year"] for e in kept.data["events"]] == [1825]
    assert not job.wanted(item)  # once

    # A page with its line of life but no paints, from before the likely ones
    # were asked for: they are, the line is kept.
    before = {k: v for k, v in kept.data.items() if k != "paints"}
    offline.library.save_note(kept.model_copy(update={"data": {**before, "pigments": []}}))
    job._pages = (0.0, set())
    assert job.wanted(item)
    likely = {
        "born": 1700,
        "died": 1790,
        "milestones": [],
        "pigments": [
            {"name": "indygo", "hex": "#2b3a67", "where": "fala", "text": "Najpewniej…"}
            | {"sure": False}
        ],
    }
    job.apply(item, Note(item_id="met:1", kind=job.kind, model="", prompt_version="x", data=likely))
    kept = offline.library.note("met:1", STUDY)
    assert kept is not None and [m["year"] for m in kept.data["milestones"]] == [1779, 1831]
    assert kept.data["pigments"] == [
        {"name": "indygo", "hex": "#2B3A67", "where": "fala", "text": "Najpewniej…", "sure": False}
    ]
    assert not job.wanted(item)
    kept_none = kept.model_copy(update={"data": {**kept.data, "pigments": []}})
    offline.library.save_note(kept_none)  # nothing found: not asked again
    assert not job.wanted(item)

    # A page from before the historical events: only they are added.
    without = {k: v for k, v in kept.data.items() if k != "events"}
    offline.library.save_note(kept.model_copy(update={"data": without}))
    job._pages = (0.0, set())
    assert job.wanted(item)
    job.apply(item, Note(item_id="met:1", kind=job.kind, model="", prompt_version="x", data=ANSWER))
    kept = offline.library.note("met:1", STUDY)
    assert kept is not None and [e["year"] for e in kept.data["events"]] == [1825]
    assert kept.data["pigments"][0]["name"] == "indygo"  # its own paints kept
    assert not job.wanted(item)


def test_the_picture_goes_out_as_the_model_reads_it() -> None:
    from frame_server.ai.daily import model_size

    # The API's own examples: a 4K picture is read at 2576 × 1449; one that
    # fits is read as it is.
    assert model_size(3840, 2160) == (2576, 1449)
    assert model_size(2000, 1500) == (2000, 1500)
    # A kept original of 4:3 is more than the model reads: made smaller here.
    assert model_size(2560, 1920) == (2212, 1659)
    assert model_size(1920, 2560) == (1659, 2212)


def test_boxes_of_a_page_from_before_are_mended(offline: FrameService) -> None:
    from frame_server.ai.daily import BOXES, BOXES_VERSION

    _catalogue(offline)
    item = offline.library.get("met:1")
    assert item is not None
    item = item.model_copy(update={"width": 4000, "height": 3000})
    offline.library.upsert(item)
    page = clean(ANSWER, []).model_dump()  # type: ignore[union-attr]
    page["details"] = [{"title": "Napis", "text": "", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2}]
    page["focus"] = {"x": 0.5, "y": 0.5}
    job = offline.daily.job
    note = Note(item_id="met:1", kind=job.kind, model=OPUS, prompt_version="x", data=page)
    job.fresh = lambda item, note: True  # type: ignore[method-assign]
    offline.library.save_note(note)
    essay = job.essay(item)
    assert essay is not None
    # Read at 2212 × 1659 of the 2560 × 1920 sent: further right and down, larger.
    box = essay.details[0]
    assert box.x == pytest.approx(0.5 * 2560 / 2212) and box.y == pytest.approx(0.5 * 1920 / 1659)
    assert box.w == pytest.approx(0.2 * 2560 / 2212)
    assert essay.focus is not None and essay.focus.x == pytest.approx(0.5 * 2560 / 2212)
    # A page asked for on a picture of the model's size is as it was written.
    offline.library.save_note(note.model_copy(update={"data": {**page, BOXES: BOXES_VERSION}}))
    essay = job.essay(item)
    assert essay is not None and essay.details[0].x == 0.5


def test_the_likely_paints_do_not_all_start_the_same() -> None:
    """Mateusz 2026-11-03: not „Najpewniej” at every paint, synonyms in turn."""
    paints = [
        Pigment(name="ochra", hex="#B0903F", text="Najpewniej ochra, tania ziemia.", sure=False),
        Pigment(name="ultramaryna", hex="#2A4FA0", text="Z lapis lazuli, droga.", sure=True),
        Pigment(name="umbra", hex="#6B4A2B", text="Najpewniej umbra, ziemny pigment.", sure=False),
        Pigment(name="biel", hex="#EEEEE6", text="najpewniej, biel ołowiana.", sure=False),
        Pigment(name="czerń", hex="#111111", text="Czerń kostna, z palonych kości.", sure=False),
    ]
    texts = [p.text for p in vary_hedges(paints)]
    assert texts[0] == "Najpewniej ochra, tania ziemia."
    assert texts[1] == "Z lapis lazuli, droga."
    assert texts[2] == "Prawdopodobnie umbra, ziemny pigment."
    assert texts[3] == "Zapewne biel ołowiana."
    assert texts[4] == "Czerń kostna, z palonych kości."
    assert paints[2].text.startswith("Najpewniej")  # the page's own copy is left as it was


def _art() -> Image.Image:
    """A painting with a red square at (600, 300)–(700, 400) among shapes."""
    rng = random.Random(7)
    art = Image.new("RGB", (1200, 900), (40, 50, 90))
    draw = ImageDraw.Draw(art)
    for _ in range(60):
        x, y = rng.randint(0, 1150), rng.randint(0, 850)
        size = (rng.randint(10, 160), rng.randint(10, 160))
        colour = (rng.randint(0, 120), rng.randint(100, 255), rng.randint(0, 255))
        draw.ellipse((x, y, x + size[0], y + size[1]), fill=colour)
    draw.rectangle((600, 300, 700, 400), fill=(230, 20, 20))
    return art


def test_details_drawn_on_another_copy_are_cut_from_the_picked_one(
    offline: FrameService,
) -> None:
    """Mateusz 2026-11-03 (Hopper's "Automat"): the page's boxes were drawn
    on the work's own copy, with a margin; a sharper copy, cut close, was
    picked since. The fragment is cut from the picked copy, where the box
    lies on it."""
    _catalogue(offline)
    item = offline.library.get("met:1")
    assert item is not None
    art = _art()
    own = Image.new("RGB", (1300, 1000), (120, 100, 60))
    own.paste(art, (50, 50))
    picked = art.crop((10, 8, 1190, 892)).resize((2360, 1768))
    copies = {"https://own/1.jpg": own, "https://sharp/1.jpg": picked}
    offline.images.sample = lambda url, urgent=False: copies[url].copy()  # type: ignore[method-assign]
    sharper = SharperCopy(
        url="https://sharp/1.jpg", item_id="wmc:1", source="wmc", width=2360, height=1768
    )
    item = offline.library.update(item.id, sharper=sharper) or item
    essay = clean(ANSWER, [])
    assert essay is not None
    # The red square on the own copy, as fractions of it.
    box = {"title": "Czerwień", "text": "", "x": 650 / 1300, "y": 350 / 1000, "w": 0.077, "h": 0.1}
    job = offline.daily.job
    offline.library.save_note(
        Note(
            item_id=item.id,
            kind=job.kind,
            model=OPUS,
            prompt_version=job.prompt_version,
            source_hash=job.source_hash(item),
            data={
                **essay.model_dump(),
                "details": [box],
                "boxes": 2,
                "seen": {"copy_id": "", "url": "https://own/1.jpg"},
            },
        )
    )
    path = offline.daily.detail(item, 0)
    assert path is not None and path.is_file()
    cut = Image.open(path).convert("RGB")
    r, g, b = ImageStat.Stat(cut).mean
    assert r > 180 and g < 70 and b < 70  # the red square, not what lies above it
    assert cut.size[0] > 150  # from the sharper copy: twice the own's pixels
    # Its file names both copies: cut again when another copy is picked.
    assert "met" in path.name
    assert offline.daily.detail_path(item, essay.details[0]) != path


def test_a_detail_that_misses_is_drawn_again() -> None:
    """Hopper's "Automat" (2026-11-03): "Twarz pod kapeluszem" cut the wall
    above the hat. The check over the cuts redraws the box that misses and
    keeps the ones that hit."""
    from frame_server.ai.details import mended

    details = [
        {
            "title": "Twarz pod kapeluszem",
            "text": "",
            "x": 0.665,
            "y": 0.3346,
            "w": 0.15,
            "h": 0.1931,
        },
        {"title": "Dłoń i filiżanka", "text": "", "x": 0.59, "y": 0.6371, "w": 0.165, "h": 0.1673},
    ]
    answer = {
        "details": [
            {"n": 1, "ok": False, "x": 1290, "y": 670, "w": 300, "h": 300, "why": "ściana"},
            {"n": 2, "ok": True, "x": 0, "y": 0, "w": 10, "h": 10, "why": ""},
            {"n": 7, "ok": False, "x": 1, "y": 1, "w": 1, "h": 1, "why": ""},
        ]
    }
    found = mended(details, answer, (2000, 1554))
    assert found is not None
    fixed, moved = found
    assert moved == ["Twarz pod kapeluszem"]
    assert fixed[0]["x"] == 1290 / 2000 and fixed[0]["y"] == 670 / 1554
    assert fixed[1] == details[1]  # the one that hit stays as it was
    assert mended(details, None, (2000, 1554)) is None


def test_a_detail_is_drawn_as_its_edges_and_framed_by_the_server() -> None:
    """Mateusz 2026-11-07: "Często chybia / przesuwa się". Told to give a
    corner, a width and a height of set proportions, the model put the thing
    in the box's corner; now it rings the thing with its four edges and the
    server centres the cut on it, with a margin and sane proportions."""
    from frame_server.ai.daily import DETAIL_MARGIN, frame_details, framed

    size = (2000, 1500)
    # A face 180 × 260 px: centred, a margin on every side, made 3:4.
    x, y, w, h = framed((910, 400, 1090, 660), size)
    assert (x + w / 2, y + h / 2) == (1000, 530)
    assert h == pytest.approx(260 * (1 + 2 * DETAIL_MARGIN)) and w == pytest.approx(h * 3 / 4)
    # A signature, long and thin, low in the corner: 4:3, within the picture,
    # the whole of it inside.
    x, y, w, h = framed((1700, 1440, 1990, 1490), size)
    assert w / h == 4 / 3 and x + w <= 2000 and y + h <= 1500
    assert x <= 1700 and y <= 1440 and x + w >= 1990 and y + h >= 1490
    # A speck: made big enough to look at, still centred on it.
    x, y, w, h = framed((500, 500, 520, 520), size)
    assert max(w, h) == 200 and (x + w / 2, y + h / 2) == (510, 510)
    # Edges the wrong way round or past the picture are read as meant.
    assert framed((1100, 660, 900, 400), size) == framed((900, 400, 1100, 660), size)
    x, y, w, h = framed((-50, -50, 150, 150), size)
    assert x == 0 and y == 0

    answer = {
        "details": [
            {"title": "Twarz", "text": "", "where": "środek", "left": 900, "top": 400,
             "right": 1100, "bottom": 660},
            {"title": "Stara", "text": "", "x": 10, "y": 20, "w": 300, "h": 300},
        ]
    }  # fmt: skip
    face, old = frame_details(answer, size)["details"]
    assert "left" not in face and (face["x"], face["w"]) == framed((900, 400, 1100, 660), size)[::2]
    assert face["where"] == "środek"
    assert old == answer["details"][1]  # drawn as before: left as it is
    assert frame_details(answer, None) == answer


def test_a_new_page_has_its_details_checked(offline: FrameService) -> None:
    """Back since 2026-11-07 (Mateusz: "Popraw detale" always hits): a page
    just written has each detail cut and shown to Claude again."""
    from frame_server.ai.client import Answer
    from frame_server.ai.daily import DETAILS_CHECKED, image_block
    from frame_server.ai.details import SYSTEM as DETAILS_SYSTEM

    _catalogue(offline)
    item = offline.library.get("met:1")
    assert item is not None
    width, height = SIZE
    params = {"messages": [{"content": [image_block(Image.new("RGB", SIZE))]}]}
    page = copy.deepcopy(ANSWER)
    page["details"] = [
        {"title": "Pazury piany", "text": "", "left": 360, "top": 60, "right": 540, "bottom": 240},
        {"title": "Wioślarze", "text": "", "left": 600, "top": 420, "right": 780, "bottom": 560},
    ]
    asked: list[dict[str, Any]] = []

    def ask(p: dict[str, Any]) -> Answer:
        asked.append(p)
        if p["system"][0]["text"] == DETAILS_SYSTEM:
            moved = {"n": 2, "ok": False, "x": 450, "y": 300, "w": 180, "h": 180}
            return Answer({"details": [{"n": 1, "ok": True}, moved]}, False, 0.05, OPUS)
        return Answer(None, True, 0, OPUS)  # the composition: nothing

    data = offline.daily.job.revise(item, params, Answer(page, False, 0.3, OPUS), ask).data
    assert data is not None
    foam, rowers = data["details"]
    # Framed by the server, then in fractions.
    assert foam["x"] + foam["w"] / 2 == pytest.approx(450 / width)
    assert foam["y"] + foam["h"] / 2 == pytest.approx(150 / height)
    # The check drew the one that missed anew.
    assert (rowers["x"], rowers["y"]) == (450 / width, 300 / height)
    assert data[DETAILS_CHECKED] == ["Wioślarze"]
    check = next(p for p in asked if p["system"][0]["text"] == DETAILS_SYSTEM)
    assert "WYCINEK 2 „Wioślarze”" in check["messages"][0]["content"][-2]["text"]


def test_the_owner_has_the_details_of_an_older_page_checked(tmp_path: Any) -> None:
    """ "Popraw detale" (Mateusz 2026-11-03: "Na żądanie, przytrzymaniem"):
    the details of a page written before the check, checked when asked; a
    box that misses is drawn anew in every page of the work."""
    from frame_server.ai.client import Answer
    from frame_server.ai.daily import (
        BOXES,
        BOXES_VERSION,
        DETAILS_CHECKED,
        SEEN,
        clean,
        sent_size,
    )
    from frame_server.ai.details import KIND as MEND
    from frame_server.ai.details import MendJob

    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        _catalogue(svc)
        assert client.post("/api/study/met:1/details").status_code == 409  # no key
        svc.ai_config.set_key(GOOD_KEY)
        assert client.post("/api/study/met:1/details").status_code == 409  # no page
        item = svc.library.get("met:1")
        essay = clean(ANSWER, [])
        assert item is not None and essay is not None
        svc.library.save_note(
            Note(
                item_id="met:1",
                kind=STUDY,
                model="claude-opus",
                prompt_version="study-1/daily-7",
                source_hash=svc.study.job.source_hash(item),
                data={**essay.model_dump(), BOXES: BOXES_VERSION},
            )
        )
        job = svc.ai.jobs[MEND]
        assert isinstance(job, MendJob) and not job.wanted(item)
        assert client.get("/api/study/met:1").json()["work"]["details_pending"] is False

        assert client.post("/api/study/met:1/details").json() == {"pending": True, "moved": None}
        assert client.get("/api/study/met:1").json()["work"]["details_pending"] is True
        assert job.wanted(item)

        params = job.params(item)
        width, height = sent_size(params) or (0, 0)
        first = essay.details[0]
        wrong = {"n": 1, "ok": False, "x": 0.1 * width, "y": 0.2 * height}
        answer = job.revise(
            item,
            params,
            Answer({"details": [{**wrong, "w": 0.3 * width, "h": 0.3 * height}]}, False, 0.1, "o"),
            lambda p: Answer(None, True, 0, "o"),
        )
        job.apply(
            item,
            svc.library.save_note(
                Note(
                    item_id="met:1",
                    kind=MEND,
                    model="o",
                    prompt_version=job.prompt_version,
                    source_hash=job.source_hash(item),
                    data=answer.data or {},
                )
            ),
        )
        assert client.get("/api/study/met:1/details").json() == {
            "pending": False,
            "moved": [first.title],
        }
        page = svc.library.note("met:1", STUDY)
        assert page is not None and page.data[DETAILS_CHECKED] == [first.title]
        box = page.data["details"][0]
        assert (box["x"], box["y"]) == pytest.approx((0.1, 0.2), abs=0.01)
        assert SEEN in page.data  # the copy they are drawn on from now on
        assert not job.wanted(item)  # done once
        work = client.get("/api/study/met:1").json()["work"]
        assert work["details_pending"] is False and len(work["details"]) == len(essay.details)


def test_same_time_shows_other_cultures(
    offline: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A European's row has works from other cultural circles (Mateusz
    2026-11-06): nearest in time first, looked for further when there are
    none so near, from different circles first, where the row is seen."""
    monkeypatch.setattr(daily_module, "SAME_TIME", 5)
    milkmaid = _add(
        offline, "met:1", title="The Milkmaid", artist="Johannes Vermeer",
        artist_bio="Dutch, Delft 1632–1675 Delft", year=1658,
    )  # fmt: skip
    for n, (artist, bio, year) in enumerate(
        [
            ("Rembrandt", "Dutch, 1606–1669", 1658),
            ("Velázquez", "Spanish, 1599–1660", 1656),
            ("Poussin", "French, 1594–1665", 1660),
            ("Claude", "French, 1600–1682", 1657),
            ("Ter Borch", "Dutch, 1617–1681", 1659),
            ("Ruisdael", "Dutch, 1628–1682", 1661),
        ]
    ):
        _add(offline, f"e:{n}", title=f"West {n}", artist=artist, artist_bio=bio, year=year)
    _add(
        offline, "a:1", title="Hawk", artist="Kano Tan'yū", culture="Japan", year=1675,
    )  # fmt: skip
    _add(
        offline, "a:2", title="Lotus", artist="Wang Shimin", artist_bio="Chinese, 1592–1680",
        year=1670,
    )  # fmt: skip
    _add(
        offline, "a:3", title="Shah", artist="Hashim", culture="India (Deccan)", year=1678,
    )  # fmt: skip
    _add(
        offline,
        "a:4",
        title="Plum",
        artist="Ogata Kōrin",
        artist_bio="Japanese, 1658–1716",
        year=1700,
    )  # fmt: skip  (too far apart)
    _add(
        offline, "j:1", title="Bridge", artist="Someone", styles=["Japonisme"], year=1658,
    )  # fmt: skip
    picked = offline.daily.same_time(milkmaid)
    ids = [w.id for w in picked]
    assert len(ids) == 5
    assert "a:4" not in ids
    # Two from other circles, second and fifth: East Asia's nearer one
    # (1670 or 1675), then India rather than the other East Asian.
    assert ids[1] in {"a:1", "a:2"} and ids[4] == "a:3"
    assert "j:1" not in ids[1:2]  # Japonisme is a European's
    assert offline.daily.same_time(milkmaid) == picked  # the same each time


def test_works_asked_for_at_once_are_all_kept(offline: FrameService) -> None:
    """2026-11-07: "Popraw detale" on 42 works one after another left one
    waiting for good, put back on the list by a request that read it before
    the worker took it off. The list is changed under one lock."""
    import threading

    from frame_server.ai.jobs import listed, relist

    key = "test_list"
    relist(offline.library, key, "done", on=True)
    ids = [f"w{n}" for n in range(40)]
    threads = [
        threading.Thread(target=relist, args=(offline.library, key, i), kwargs={"on": True})
        for i in ids
    ]
    threads.append(
        threading.Thread(target=relist, args=(offline.library, key, "done"), kwargs={"on": False})
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert listed(offline.library, key) == set(ids)


# -- the curator of the study of the day ----------------------------------------


def _sheet(service: FrameService, item_id: str) -> None:
    """A pale sheet: light paper with a few pencil marks."""
    img = Image.new("RGB", (900, 600), (236, 230, 214))
    draw = ImageDraw.Draw(img)
    for x in (200, 420, 640):
        draw.line((x, 200, x + 30, 260), fill=(150, 145, 135), width=2)
    item = service.library.get(item_id)
    assert item is not None
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    service.images.thumb_path(item).write_bytes(buf.getvalue())


def _curator(fake: FakeAnthropic, *answers: dict[str, Any]) -> list[dict[str, Any]]:
    """The curator's answers in turn; returns its questions."""
    left = list(answers)
    asked: list[dict[str, Any]] = []

    def create(**params: Any) -> Any:
        fake.asked.append(params)
        assert params["model"] == SONNET
        asked.append(params)
        return _message(left.pop(0) if len(left) > 1 else left[0])

    fake.messages.create = create
    return asked


def _numbers(question: dict[str, Any]) -> dict[str, int]:
    """The shortlisted works' numbers by title."""
    texts = [b["text"] for b in question["messages"][0]["content"] if b["type"] == "text"]
    return {t.split("\n")[0].split(". ", 1)[1]: int(t.split(".")[0]) for t in texts}


def test_a_title_that_calls_the_work_a_sketch() -> None:
    def item(title: str) -> Item:
        return Item(id="a:1", source="a", source_id="1", title=title)

    assert daily_module.sketch_title(item("Mixed Studies near the Pool of Bethesda, Jerusalem"))
    assert daily_module.sketch_title(item("Sketchbook page"))
    assert daily_module.sketch_title(item("Study of a Young Woman"))
    assert daily_module.sketch_title(item("Skizzenbuch, Blatt 12"))
    assert not daily_module.sketch_title(item("The Artist's Studio"))
    assert not daily_module.sketch_title(item("Students of the Academy"))


def test_without_the_curator_sketches_and_pale_sheets_go_last(offline: FrameService) -> None:
    _add(offline, "met:1", title="Mixed Studies near the Pool of Bethesda", artist="F. E. Church")
    _add(offline, "met:2", title="A Quiet Page", artist="Someone Pale")
    _sheet(offline, "met:2")
    _add(offline, "met:3", title="The Harvesters", artist="Pieter Bruegel", year=1565)
    found = offline.daily.pick(DAY)
    assert found is not None and found.id == "met:3"
    assert offline.daily.curated() == {}


def test_the_curator_sets_aside_a_sketchbook_page(tmp_path: Path) -> None:
    _, svc, fake = _claude(tmp_path)
    _catalogue(svc)
    _add(svc, "met:6", title="Bethesda", artist="Frederic Edwin Church", year=1868)
    _sheet(svc, "met:6")
    asked = _curator(fake, {"works": [], "choice": 0, "reason": "-"})
    svc.daily.pick(DAY)  # a first look at the day's shortlist (nothing fits)
    numbers = _numbers(asked[0])
    assert set(numbers) <= {
        "Under the Wave off Kanagawa",
        "South Wind, Clear Sky",
        "Water Lilies",
        "The Harvesters",
        "Bethesda",
    }
    # One work per artist, each with its picture; the pale sheet said so.
    assert not {"Under the Wave off Kanagawa", "South Wind, Clear Sky"} <= set(numbers)
    content = asked[0]["messages"][0]["content"]
    assert sum(b["type"] == "image" for b in content) == len(numbers)
    assert any("light sheet" in b.get("text", "") and "Bethesda" in b["text"] for b in content)

    svc.library.set_state(daily_module.UNFIT_KEY, {})
    svc.library.set_state(daily_module.CURATED_KEY, {})
    svc.library.set_state(HISTORY_KEY, {})
    asked.clear()
    answer = {
        "works": [
            {"n": numbers["Bethesda"], "what": "Notatki ołówkiem", "fit": False, "why": "szkic"},
            {"n": numbers["Water Lilies"], "what": "Lilie wodne", "fit": True, "why": "obraz"},
        ],
        "choice": numbers["Water Lilies"],
        "reason": "Najwięcej do oglądania.",
    }
    _curator(fake, answer)
    found = svc.daily.pick(DAY)
    assert found is not None and found.id == "met:3"
    assert svc.daily.unfit() == {"met:6": "Notatki ołówkiem · szkic"}
    assert svc.daily.curated()[DAY.isoformat()] == {
        "item": "met:3",
        "reason": "Najwięcej do oglądania.",
        "unfit": ["met:6"],
        "poor_copy": [],
    }
    # The sheet set aside is never shortlisted again.
    asked = _curator(fake, {"works": [], "choice": 1, "reason": "Pierwsze."})
    assert svc.daily.again(DAY) is not None
    assert "Bethesda" not in _numbers(asked[0])
    assert svc.claude.spending.by_kind().get("study_pick", 0) > 0


def test_a_shortlist_all_set_aside_asks_about_the_next(tmp_path: Path) -> None:
    _, svc, fake = _claude(tmp_path)
    for n in range(14):
        _add(svc, f"met:{n + 10}", title=f"Work {n}", artist=f"Painter {n}")
    first = {
        "works": [{"n": n, "what": "", "fit": False, "why": "szkic"} for n in range(1, 11)],
        "choice": 0,
        "reason": "Same szkice.",
    }
    asked = _curator(fake, first, {"works": [], "choice": 2, "reason": "Drugie."})
    found = svc.daily.pick(DAY)
    assert len(asked) == 2 and len(svc.daily.unfit()) == 10
    assert len(_numbers(asked[1])) == 4
    second = list(_numbers(asked[1]))[1]
    assert found is not None and found.title == second


def test_without_an_answer_the_rules_choose(tmp_path: Path) -> None:
    _, svc, fake = _claude(tmp_path)
    _catalogue(svc)
    _curator(fake, {"works": [], "choice": 42, "reason": "?"})
    found = svc.daily.pick(DAY)
    assert found is not None
    assert svc.daily.curated() == {} and svc.daily.unfit() == {}
    # The switch off: nothing asked.
    svc.ai_config.update(AiConfigUpdate(daily=False))
    asked = _curator(fake, {"works": [], "choice": 1, "reason": "-"})
    assert svc.daily.pick(DAY + timedelta(days=1)) is not None
    assert asked == []


def test_the_copy_counts_in_the_pick(offline: FrameService) -> None:
    # A small picture goes last, one as long as the frame's side first.
    _add(offline, "met:1", title="Small", artist="A Painter", width=1400, height=1000)
    _add(offline, "met:2", title="Middling", artist="B Painter", width=2200, height=1600)
    _add(offline, "met:3", title="Large", artist="C Painter", width=4000, height=3000)
    small, middling, large = (offline.library.get(f"met:{n}") for n in (1, 2, 3))
    assert small and middling and large
    assert daily_module.copy_quality(small) < daily_module.copy_quality(middling)
    assert daily_module.copy_quality(middling) < daily_module.copy_quality(large)
    # A sharper copy found elsewhere is what counts.
    copy = SharperCopy(
        url="https://x/1.jpg", item_id="wmc:1", source="wmc", width=5000, height=4000
    )
    sharper = small.model_copy(update={"sharper": copy})
    assert daily_module.copy_side(sharper) == 5000
    assert daily_module.copy_quality(sharper) == daily_module.copy_quality(large)
    unknown = small.model_copy(update={"width": None, "height": None})
    assert daily_module.copy_quality(unknown) == 0.0


def test_a_grey_copy_is_never_the_study_of_the_day(offline: FrameService) -> None:
    _add(
        offline,
        "met:1",
        title="Starry Night",
        artist="Vincent van Gogh",
        classification="Paintings",
        medium="Oil on canvas",
        tint_spread=0.001,
    )
    _add(offline, "met:2", title="The Harvesters", artist="Pieter Bruegel", year=1565)
    for n in range(5):
        found = offline.daily.pick(DAY + timedelta(days=40 * n))
        assert found is None or found.id != "met:1"


def test_a_poor_photograph_comes_back_with_another_copy(tmp_path: Path) -> None:
    _, svc, fake = _claude(tmp_path)
    _add(svc, "met:1", title="Blurred", artist="A Painter", width=3000, height=2000)
    _add(svc, "met:2", title="Sharp", artist="B Painter", width=3000, height=2000)
    asked = _curator(fake, {"works": [], "choice": 0, "reason": "-"})
    svc.daily.pick(DAY)
    numbers = _numbers(asked[0])
    assert "Photograph: 3000 × 2000 px" in asked[0]["messages"][0]["content"][0]["text"]
    svc.library.set_state(HISTORY_KEY, {})
    answer = {
        "works": [
            {
                "n": numbers["Blurred"],
                "what": "Obraz",
                "fit": False,
                "photo": True,
                "why": "nieostre",
            }
        ],
        "choice": numbers["Sharp"],
        "reason": "Ostre.",
    }
    _curator(fake, answer)
    found = svc.daily.pick(DAY)
    assert found is not None and found.id == "met:2"
    assert svc.daily.poor_copies() == {"met:1": ""} and svc.daily.unfit() == {}
    # Not shortlisted while its photograph is the same ...
    asked = _curator(fake, {"works": [], "choice": 0, "reason": "-"})
    svc.daily.pick(DAY + timedelta(days=400))
    assert "Blurred" not in _numbers(asked[0])
    # ... and back once a sharper copy is shown.
    copy = SharperCopy(
        url="https://x/1.jpg", item_id="wmc:1", source="wmc", width=5000, height=4000
    )
    svc.library.update("met:1", sharper=copy)
    asked = _curator(fake, {"works": [], "choice": 0, "reason": "-"})
    svc.daily.pick(DAY + timedelta(days=800))
    assert "Blurred" in _numbers(asked[0])
