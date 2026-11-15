"""„Do sprawdzenia”: each finding's remedy in one tap (Mateusz 2026-11-15,
„Pełne poprawki jednym dotknięciem”): the corrected title, maker or date,
"Przytnij" by Opus told what the audit saw, "Ukryj", a problem done
elsewhere, and the gatekeeper's notes in Polish."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from test_ai import FakeAnthropic, _message, fake  # noqa: F401  (fixture)
from test_crops import CORNERS, _work

from frame_server.ai.client import HAIKU, OPUS
from frame_server.library.models import Note
from frame_server.service import FrameService

FINDING = {
    "id": "mnk:1",
    "at": "2026-11-15T02:00:00+00:00",
    "problems": [
        {"field": "title", "problem": "Imię to Juliusz, nie Julian"},
        {"field": "picture", "problem": "Na zdjęciu widoczna jest linijka w dolnej części"},
    ],
}


def _client(service: FrameService) -> TestClient:
    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    return TestClient(app)


def _found(service: FrameService, finding: dict[str, Any] = FINDING) -> None:
    state = service.audit.state()
    state["written"] = [finding]
    service.audit._save(state)


def _answers(fake: FakeAnthropic, *answers: dict[str, Any]) -> None:  # noqa: F811
    left = iter(answers)
    fake.messages.create = lambda **params: (
        fake.asked.append(params),
        _message(next(left)),
    )[1]


def test_the_night_audit_gives_the_corrected_title_with_its_problem(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    item = _work(service, "mnk:1", title="Portret prof. Juliana Kosińskiego")
    claim = service.audit.claim(
        item,
        {
            "problems": [
                {
                    "field": "title",
                    "problem": "Imię to Juliusz",
                    "fix": "Portret prof. Juliusza Kosińskiego",
                    "fix_pl": "Portret prof. Juliusza Kosińskiego",
                },
                {"field": "picture", "problem": "Linijka", "fix": "x", "fix_pl": "y"},
            ]
        },
    )
    assert claim == {
        "problems": [
            {
                "field": "title",
                "problem": "Imię to Juliusz",
                "fix": "Portret prof. Juliusza Kosińskiego",
                "fix_pl": "Portret prof. Juliusza Kosińskiego",
            },
            {"field": "picture", "problem": "Linijka"},  # nothing to put on a picture
        ]
    }


def test_a_title_is_suggested_and_mended_with_its_polish_title(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "mnk:1", title="Portret prof. Juliana Kosińskiego", pooled=True)
    service.library.save_note(
        Note(
            item_id="mnk:1",
            kind="pl_text",
            model=HAIKU,
            prompt_version="1",
            data={"title": "Portret prof. Juliana Kosińskiego", "frame": "", "full": ""},
        )
    )
    _found(service)
    fixes = [
        {
            "field": "title",
            "fix": "Portret prof. Juliusza Kosińskiego",
            "fix_pl": "Portret profesora Juliusza Kosińskiego",
        }
    ]
    _answers(fake, {"fixes": fixes})
    with _client(service) as client:
        review = client.post("/api/ai/review/mnk:1/suggest").json()
        (title, picture) = review["findings"][0]["problems"]
        assert title["fix"] == "Portret prof. Juliusza Kosińskiego"
        assert title["fix_pl"] == "Portret profesora Juliusza Kosińskiego"
        assert picture["fix"] == ""
        assert [p["model"] for p in fake.asked] == [HAIKU]
        assert "Juliusz, nie Julian" in str(fake.asked[0]["messages"])
        # Asked once: a second look has its values already.
        client.post("/api/ai/review/mnk:1/suggest")
        assert len(fake.asked) == 1

        after = client.post(
            "/api/ai/review/mnk:1/fix",
            json={"field": "title", "value": title["fix"], "value_pl": title["fix_pl"]},
        ).json()
        (left,) = after["findings"][0]["problems"]
        assert left["field"] == "picture"  # the title done, the picture still waits
    item = service.library.get("mnk:1")
    assert item is not None and item.title == "Portret prof. Juliusza Kosińskiego"
    note = service.library.note("mnk:1", "pl_text")
    assert note is not None and note.data["title"] == "Portret profesora Juliusza Kosińskiego"
    assert not service.pl_text.fresh(item, note)  # the Polish text written anew later


def test_a_date_mended_gives_the_year_and_the_last_problem_leaves_the_list(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "mnk:1", title="The Seasons", date_text="1932", year=1932)
    _found(service, {**FINDING, "problems": [{"field": "date", "problem": "Po śmierci"}]})
    with _client(service) as client:
        bad = client.post("/api/ai/review/mnk:1/fix", json={"field": "picture", "value": "x"})
        assert bad.status_code == 422
        after = client.post(
            "/api/ai/review/mnk:1/fix", json={"field": "date", "value": "ok. 1897"}
        ).json()
        assert after["findings"] == []
    item = service.library.get("mnk:1")
    assert item is not None and item.date_text == "ok. 1897" and item.year == 1897


def test_przytnij_asks_opus_told_what_the_audit_saw_and_keeps_the_owners_cut(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "mnk:1", title="Geneigter Mädchenkopf", pooled=True)
    _found(service)
    _answers(fake, CORNERS)
    with _client(service) as client:
        review = client.post("/api/ai/review/mnk:1/cut").json()
        (left,) = review["findings"][0]["problems"]
        assert left["field"] == "title"
    (asked,) = fake.asked
    assert asked["model"] == OPUS
    assert "linijka w dolnej części" in str(asked["messages"])
    item = service.library.get("mnk:1")
    assert item is not None and item.cut is not None and item.cut.by == "owner"
    assert item.cut_shown() is not None
    assert not service.crops.now(item)  # never cut again by itself


def test_przytnij_says_so_when_nothing_is_found(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "mnk:1", pooled=True)
    _found(service)
    _answers(fake, {**CORNERS, "layers": [], "work": None})
    with _client(service) as client:
        answer = client.post("/api/ai/review/mnk:1/cut")
        assert answer.status_code == 422
        assert "Popraw kadr" in answer.json()["detail"]
    assert len(service.audit.written()[0]["problems"]) == 2  # still waits


def test_ukryj_and_a_problem_done_elsewhere(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "mnk:1", pooled=True)
    _work(service, "mnk:2", pooled=True)
    _found(service)
    state = service.audit.state()
    state["written"] = [*state["written"], {**FINDING, "id": "mnk:2"}]
    service.audit._save(state)
    with _client(service) as client:
        after = client.delete("/api/ai/review/mnk:2/problems/picture").json()
        assert [len(f["problems"]) for f in after["findings"]] == [2, 1]
        hidden = client.post("/api/ai/review/mnk:1/hide").json()
        assert [f["item"]["id"] for f in hidden["findings"]] == ["mnk:2"]
        assert client.post("/api/ai/review/nope:1/hide").status_code == 404
    item = service.library.get("mnk:1")
    assert item is not None and item.excluded


def test_the_gatekeepers_notes_in_polish(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "wmc:1", title="Foto", pooled=True)
    _work(service, "wmc:2", title="Bekendmaking", pooled=True)
    claim = service.gatekeeper.claim(
        service.library.get("wmc:1"),  # type: ignore[arg-type]
        {"why": "Men on a hunt", "not_art": True, "why_pl": "Mężczyźni na polowaniu"},
    )
    assert claim == {
        "seen_as": "not_art",
        "why": "Men on a hunt",
        "why_pl": "Mężczyźni na polowaniu",
    }
    state = service.gatekeeper.state()
    state["written"] = [
        {"id": "wmc:1", "at": "2026-11-15T02:00:00+00:00", **claim},
        {"id": "wmc:2", "at": "2026-11-14T02:00:00+00:00", "seen_as": "text", "why": "A page"},
    ]
    service.gatekeeper._save(state)
    _answers(fake, {"notes": ["Strona z tekstem"]})
    assert service.review_fixes.translate() == 1
    assert "1. A page" in str(fake.asked[0]["messages"])
    assert service.review_fixes.translate() == 0  # all in Polish now
    with _client(service) as client:
        review = client.get("/api/ai/review").json()
    assert [e["why"] for e in review["set_aside"]] == ["Mężczyźni na polowaniu", "Strona z tekstem"]
