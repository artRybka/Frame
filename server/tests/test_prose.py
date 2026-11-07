"""The composition text written last in one voice: the grid as facts, the
latest openings to avoid, and pages written before rewritten once with
their marks left as they are."""

from __future__ import annotations

from typing import Any

from test_composition import _old_page
from test_daily import _catalogue

from frame_server.ai import grid as grids
from frame_server.ai import prose
from frame_server.ai.check import page_views
from frame_server.ai.client import OPUS
from frame_server.ai.daily import CHECK_ROUND, ROUND, TAKE, Key
from frame_server.ai.prose import PROSE, PROSE_KEY, ProseJob, grid_facts, opening, rewritten
from frame_server.ai.study import KIND as STUDY
from frame_server.library.models import Note
from frame_server.service import FrameService

TEXT = (
    "Wzrok wchodzi od dołu po łuku fali i dopiero na grzbiecie zatrzymuje się, bo tam pianę "
    "trafia najjaśniejsze światło. Mała góra w dali odpowiada na ten ciężar."
)


def _key(title: str, x: float, y: float) -> Key:
    return Key(title=title, x=x, y=y)


def test_the_grid_is_told_as_facts() -> None:
    near = [
        grids.Held(key=_key("Grzbiet fali", 1 / 3, 0.2)),
        grids.Held(key=_key("Łódź", 0.5, 0.5)),
    ]
    facts = grid_facts("thirds", near)
    assert facts[0] == "Siatka: trójpodział."
    assert "- Grzbiet fali: na linii (lewa pionowa linia)" in facts
    assert not any("Łódź" in f for f in facts)  # halfway lies on no third
    assert grid_facts("none", near) == []
    assert grid_facts("thirds", [grids.Held(key=_key("Łódź", 0.5, 0.5))]) == []


def test_an_opening_is_its_first_words() -> None:
    assert opening("Fala zamyka lewą stronę. Dalej.") == "Fala zamyka lewą stronę."
    assert opening("Raz dwa trzy cztery pięć sześć siedem osiem.").endswith("siedem…")


def test_the_text_replaces_only_the_shown_take() -> None:
    ring = {
        "shape": "loop",
        "points": [{"x": 0.4, "y": 0.4}, {"x": 0.5, "y": 0.5}],
        "title": "Fala",
    }
    old = {"title": TAKE, "grid": "none", "text": "Stary tekst.", "marks": [ring]}
    other = {"title": "Spojrzenie", "grid": "none", "text": "Inny.", "marks": [ring]}
    data = {
        "composition": {"views": [old, other]},
        "composition_versions": [{"composition": {"views": [old]}}, {"composition": {}}],
    }
    out = rewritten(data, TEXT)
    assert out[PROSE_KEY] == PROSE
    assert [v["text"] for v in out["composition"]["views"]] == [TEXT, "Inny."]
    assert out["composition_versions"][0]["composition"]["views"][0]["text"] == TEXT
    assert data["composition"]["views"][0]["text"] == "Stary tekst."  # a copy
    # Nothing usable: only marked done, the text as it was.
    kept = rewritten(data, None)
    assert kept[PROSE_KEY] == PROSE and kept["composition"] == data["composition"]
    # A page written before shows its "Geometria" under the new name.
    geometry = {**old, "title": "Geometria"}
    out = rewritten({"composition": {"views": [geometry]}}, TEXT)
    assert out["composition"]["views"][0] == {**geometry, "text": TEXT}


def test_pages_written_before_are_rewritten_once(service: FrameService) -> None:
    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    _old_page(service, **{CHECK_ROUND: ROUND})
    job = service.ai.jobs[prose.KIND]
    assert isinstance(job, ProseJob)
    assert job.wanted(item)
    page = service.library.note("met:1", STUDY)
    assert page is not None
    marks = page.data["composition"]["views"][0]["marks"]
    params = job.params(item)
    assert params["model"] == OPUS and params["system"][0]["text"] == prose.SYSTEM
    (content,) = params["messages"][0]["content"]
    assert content["type"] == "text"  # no picture
    assert "BRUDNOPIS ANALIZY" in content["text"]
    answer: dict[str, Any] = {"text": TEXT}
    note = Note(
        item_id="met:1",
        kind=prose.KIND,
        model=OPUS,
        prompt_version=job.prompt_version,
        source_hash=job.source_hash(item),
        data=answer,
    )
    job.apply(item, service.library.save_note(note))
    page = service.library.note("met:1", STUDY)
    assert page is not None and page.data[PROSE_KEY] == PROSE
    shown = page_views(page.data)[0]
    assert shown.text == TEXT
    assert page.data["composition"]["views"][0]["marks"] == marks  # the drawing as it was
    assert not job.wanted(item)
    # The next page is told how this one opens.
    assert prose.recent_openings(service.library) == [opening(TEXT)]
    assert prose.recent_openings(service.library, but="met:1") == []


def test_a_page_about_to_be_analysed_again_waits(service: FrameService) -> None:
    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    _old_page(service)  # an older round: the analysis is made again, text and all
    job = service.ai.jobs[prose.KIND]
    assert not job.wanted(item)
