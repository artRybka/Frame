"""The "Rytm" take asked alone of pages written before it was part of the
question; their third take of another kind ("Światło") is left out."""

from __future__ import annotations

from typing import Any

from test_daily import ANSWER, _catalogue

from frame_server.ai.daily import RHYTHM_ASKED, clean
from frame_server.ai.rhythm import KIND, SCHEMA, RhythmJob, request_text
from frame_server.ai.study import KIND as STUDY
from frame_server.library.models import Note
from frame_server.service import FrameService

LIGHT = {
    "title": "Światło",
    "grid": "none",
    "text": "Światło z okna po lewej modeluje bryły.",
    "marks": [
        {"shape": "arrow", "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.2}], "title": "Okno"}
    ],
}
BEATS = [{"x": 0.1 * n, "y": 0.5} for n in range(1, 6)]
RHYTHM_ANSWER = {
    "views": [
        {
            "title": "Takty",
            "grid": "golden",
            "text": "Grzbiety fal powtarzają się coraz drobniej.",
            "marks": [{"shape": "rhythm", "points": BEATS, "title": "Grzbiety", "text": "co krok"}],
        }
    ]
}


def _old_study(service: FrameService, item_id: str = "met:1") -> None:
    """A study written before "Rytm": Spojrzenie, Geometria and Światło."""
    essay = clean(ANSWER, [])
    assert essay is not None
    data = essay.model_dump()
    data["composition"]["views"].append(LIGHT)
    job = service.study.job
    item = service.library.get(item_id)
    assert item is not None
    service.library.save_note(
        Note(
            item_id=item_id,
            kind=STUDY,
            model="claude-opus",
            prompt_version="study-1/daily-5",
            source_hash=job.source_hash(item),
            data=data,
        )
    )


def _job(service: FrameService) -> RhythmJob:
    job = service.ai.jobs[KIND]
    assert isinstance(job, RhythmJob)
    return job


def _titles(service: FrameService) -> list[str]:
    item = service.library.get("met:1")
    assert item is not None
    essay = service.study.job.essay(item)
    assert essay is not None
    return [v.title for v in essay.composition.views]


def _answer(service: FrameService, data: dict[str, Any]) -> None:
    job, item = _job(service), service.library.get("met:1")
    assert item is not None
    note = Note(
        item_id="met:1",
        kind=KIND,
        model="claude-opus",
        prompt_version=job.prompt_version,
        source_hash=job.source_hash(item),
        data=data,
    )
    job.apply(item, service.library.save_note(note))


def test_an_old_third_take_is_left_out_and_a_rhythm_asked(service: FrameService) -> None:
    _catalogue(service)
    _old_study(service)
    assert _titles(service) == ["Spojrzenie", "Geometria"]  # no "Światło"
    job, item = _job(service), service.library.get("met:1")
    assert item is not None and job.wanted(item)
    assert not job.wanted(service.library.get("met:2"))  # type: ignore[arg-type]
    text = request_text(item, service.library.note("met:1", STUDY).data)  # type: ignore[union-attr]
    assert "UJĘCIE „Geometria”" in text and "Światło" not in text
    assert SCHEMA["properties"]["views"]["items"]["properties"]["marks"]["items"]["properties"][
        "shape"
    ]["enum"] == ["rhythm"]

    _answer(service, RHYTHM_ANSWER)
    assert _titles(service) == ["Spojrzenie", "Geometria", "Rytm"]
    page = service.library.note("met:1", STUDY)
    assert page is not None and page.data[RHYTHM_ASKED] is True
    assert page.prompt_version == "study-1/daily-5"  # still kept as written
    rhythm = page.data["composition"]["views"][2]
    assert rhythm["grid"] == "none" and len(rhythm["marks"][0]["points"]) == 5
    assert not job.wanted(item)


def test_a_picture_without_rhythms_keeps_two_takes_and_is_asked_once(
    service: FrameService,
) -> None:
    _catalogue(service)
    _old_study(service)
    _answer(service, {"views": []})
    assert _titles(service) == ["Spojrzenie", "Geometria"]
    item = service.library.get("met:1")
    assert item is not None and not _job(service).wanted(item)


def test_a_page_written_with_the_rhythm_question_is_not_asked_again(
    service: FrameService,
) -> None:
    _catalogue(service)
    _old_study(service)
    page = service.library.note("met:1", STUDY)
    assert page is not None
    data = {**page.data, RHYTHM_ASKED: True}
    service.library.save_note(page.model_copy(update={"data": data}))
    item = service.library.get("met:1")
    assert item is not None and not _job(service).wanted(item)
