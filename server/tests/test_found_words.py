"""A work a museum found for a search shows for it only when it has the
words asked, as typed or as the museums were asked them (Mateusz
2026-11-09: for "vermeer" Getty gave ter Borch and Yale three sheep; for
"nocna straż" the Rijksmuseum's "Night Watch" is right)."""

from __future__ import annotations

from test_ai import FakeAnthropic
from test_search_words import fake  # noqa: F401  (a fixture)

from frame_server.library import Item, PlaylistRules
from frame_server.library.phrases import quote
from frame_server.service import FrameService

NIGHT_WATCH = {"polish": True, "english": "night watch", "french": "ronde de nuit"}


def _found(service: FrameService, n: int, rules: PlaylistRules, **fields: object) -> None:
    service.library.upsert(
        Item(
            id=f"getty:{n}",
            source="getty",
            source_id=str(n),
            found_for=[rules.search_key()],
            **fields,  # type: ignore[arg-type]
        )
    )


def test_a_museums_answer_without_the_words_is_left_out(service: FrameService) -> None:
    vermeer = PlaylistRules(query="vermeer")
    _found(service, 1, vermeer, title="The Milkmaid", artist="Johannes Vermeer")
    _found(service, 2, vermeer, title="The Music Lesson", artist="Gerard ter Borch")
    _found(service, 3, vermeer, title="Three Sheep", artist="Unknown")
    _found(service, 4, vermeer, title="Copy", keywords=["after Vermeer's Lacemaker"])
    # Only mentioned in the museum's description: not the words' answer
    # either (Mateusz 2026-11-13).
    _found(service, 5, vermeer, title="Sea", description="Painted after Vermeer")
    total, items = service.library.query(vermeer)
    assert total == 2 and {i.id for i in items} == {"getty:1", "getty:4"}
    # The chip says what picking it shows.
    assert service.library.term_index().word_count("vermeer") == 2


def test_the_words_as_the_museums_were_asked_count(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    fake.answer = NIGHT_WATCH
    rules = PlaylistRules(query=quote(["nocna straż"]))
    _found(service, 1, rules, title="The Night Watch", artist="Rembrandt van Rijn")
    _found(service, 2, rules, title="Ronde de nuit", artist="Félix Ziem")
    _found(service, 3, rules, title="Justice", artist="Master of the E-Series Tarocchi")
    # Before the words were ever translated: only what has them as typed.
    assert service.library.query(rules)[0] == 0
    service.search_words.wording("nocna straż")
    asked = len(fake.asked)
    assert service.search_words.known("Nocna  straż") == ("night watch", "ronde de nuit")
    service.library.upsert(Item(id="aic:9", source="aic", source_id="9", title="Sea"))
    total, items = service.library.query(rules)
    assert total == 2 and {i.id for i in items} == {"getty:1", "getty:2"}
    # The catalogue's search asks the model nothing.
    assert len(fake.asked) == asked
    assert service.search_words.known("gitara") == ()
    assert len(fake.asked) == asked
