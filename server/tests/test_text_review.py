"""The Polish texts kept, looked over at the owner's tap
(frame_server.ai.text_review, Mateusz 2026-11-14): the translations checked
by Haiku, a note by Sonnet where the museum's text is not about the work,
the notes written before the five styles written anew; a text whose new
answer did not come stays as it was."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_ai import GOOD_KEY, FakeAnthropic, _message
from test_polish import DESCRIPTION, NOTE_ANSWER, PL_ANSWER, _add, _answers, fake  # noqa: F401
from test_study_refresh import _answers as _batch_answers

from frame_server.ai.client import HAIKU, SONNET
from frame_server.ai.pl_text import KIND, PROMPT_VERSION, PolishText
from frame_server.ai.text_review import TextReview
from frame_server.config import Settings
from frame_server.library import Item
from frame_server.library.models import Note
from frame_server.service import FrameService
from frame_server.web import create_app


def _kept(service: FrameService, item: Item, **text: Any) -> None:
    """A text kept as before 1.145.112: no word on the museum's text."""
    data = PolishText(
        title="Stary tytuł", frame="Stary tekst na ramkę.", full="Stary pełny tekst.", **text
    ).model_dump()
    data.pop("about_work")
    service.library.save_note(
        Note(
            item_id=item.id,
            kind=KIND,
            model=SONNET if text.get("written") == "note" else HAIKU,
            prompt_version=PROMPT_VERSION,
            source_hash=service.pl_text.source_hash(item),
            data=data,
        )
    )


def test_a_new_translation_keeps_haikus_word(service: FrameService, fake: FakeAnthropic) -> None:  # noqa: F811
    _answers(fake, {**PL_ANSWER, "about_work": True})
    item = _add(service, "met:1", description=DESCRIPTION)
    service.ai.run_one(KIND, "met:1")
    text = service.pl_text.text(item)
    assert text is not None and text.about_work is True
    assert service.text_review.view()["unchecked"] == 0


def test_the_translations_are_checked_and_a_general_one_gets_a_note(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    review: TextReview = service.text_review
    about = _add(service, "met:1", description=DESCRIPTION)
    general = _add(service, "met:2", description=DESCRIPTION)
    _kept(service, about)
    _kept(service, general)
    _kept(service, _add(service, "met:3", description=""), written="note", sources=["obraz"])
    _kept(service, _add(service, "met:4", description=""), written="note", style="opis")
    view = review.view()
    assert (view["translations"], view["unchecked"], view["unstyled"]) == (2, 2, 1)
    assert view["check_usd"] > 0 and view["restyle_usd"] > view["check_usd"]
    assert not view["running"]

    assert review.start(check=True, restyle=False) == 2
    assert review.start() == 0  # one order at a time
    assert review.look() is True
    (checks,) = fake.batches.values()
    assert [r["custom_id"] for r in checks] == ["c0", "c1"]
    params = checks[0]["params"]
    assert params["model"] == HAIKU
    (content,) = params["messages"][0]["content"]  # text only, no picture
    assert "Tekst muzeum:" in content["text"] and "steamboat" in content["text"]
    assert review.view()["checking"] == 2

    assert review.collect() is False  # still running
    fake.ended = True
    _batch_answers(
        fake, {"c0": _message({"about_work": True}), "c1": _message({"about_work": False})}
    )
    assert review.look() is True  # the note for met:2 ordered
    notes = fake.batches["batch_2"]
    assert [r["custom_id"] for r in notes] == ["n0"]
    question = notes[0]["params"]["messages"][0]["content"][1]["text"]
    assert notes[0]["params"]["model"] == SONNET
    assert "Tekst muzeum (ogólny, nie o tym dziele" in question
    view = review.view()
    assert (view["checked"], view["found"], view["writing"]) == (2, 1, 1)
    # The translation stays shown until its note is in.
    kept = service.pl_text.text(general)
    assert kept is not None and kept.written == "translation" and kept.about_work is False

    _batch_answers(fake, {"n0": _message({**NOTE_ANSWER, "style": "temat"})})
    assert review.look() is False
    text = service.pl_text.text(general)
    assert text is not None and text.written == "note" and text.general and text.style == "temat"
    first = service.pl_text.text(about)
    assert first is not None and first.written == "translation" and first.about_work is True
    view = review.view()
    assert (view["written"], view["unchecked"], view["general"]) == (1, 0, 0)
    assert view["spent_usd"] > 0 and not view["running"]


def test_the_old_notes_are_written_anew_and_a_failed_one_stays(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    review: TextReview = service.text_review
    one = _add(service, "met:3", description="")
    two = _add(service, "met:4", description="")
    _kept(service, one, written="note", sources=["obraz"])
    _kept(service, two, written="note", sources=["obraz"])
    _kept(service, _add(service, "met:1", description=DESCRIPTION))  # not asked: no check

    assert review.start(check=False, restyle=True) == 2
    review.look()
    (notes,) = fake.batches.values()
    assert [r["custom_id"] for r in notes] == ["n0", "n1"]
    assert {r["params"]["model"] for r in notes} == {SONNET}
    fake.ended = True
    _batch_answers(fake, {"n0": _message({**NOTE_ANSWER, "style": "warsztat"}), "n1": None})
    assert review.look() is False
    text = service.pl_text.text(one)
    assert text is not None and text.style == "warsztat" and not text.general
    old = service.pl_text.text(two)
    assert old is not None and old.full == "Stary pełny tekst." and old.style == ""
    view = review.view()
    assert (view["written"], view["unstyled"], view["unchecked"]) == (1, 1, 1)


def test_the_app_starts_it(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    client = TestClient(app)
    _kept(svc, _add(svc, "met:1", description=DESCRIPTION))
    assert client.post("/api/ai/text-review", json={}).status_code == 409  # no key
    svc.claude.factory = FakeAnthropic
    svc.ai_config.set_key(GOOD_KEY)
    view = client.get("/api/ai").json()["text_review"]
    assert view["unchecked"] == 1 and view["check_usd"] > 0
    body = {"check": False, "restyle": True}
    assert client.post("/api/ai/text-review", json=body).status_code == 409  # no notes
    view = client.post("/api/ai/text-review", json={"check": True}).json()["text_review"]
    assert view["running"] and view["checking"] == 1
