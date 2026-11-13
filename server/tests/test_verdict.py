"""The reasons a work is no picture for the frame, as one list, and what
each place minds of them (docs/RULES.md, stage 4): the table answers as the
places did before it (``test_rules_matrix.EXPECTED``)."""

from __future__ import annotations

from datetime import date

from test_rules_matrix import EXPECTED, PLACES, SPECIMENS, _work

from frame_server.library import ItemKind, PlaylistRules
from frame_server.library.verdict import (
    COPIES,
    MINDS,
    NAMES,
    OTHER_ART,
    STUDY_ONLY,
    Place,
    Why,
    against,
    copy_whys,
    whys,
)
from frame_server.library.vocabulary import (
    PHOTOGRAPHY,
    SCULPTURE,
    object_category,
    other_art,
)
from frame_server.service import FrameService


def test_the_reasons_are_copies_or_sztuki_inne() -> None:
    for name in SPECIMENS:
        for pooled in (True, False):
            item = _work(name, pooled)
            found = set(whys(item))
            assert set(copy_whys(item)) == found & COPIES, name
            assert bool(found - COPIES) == other_art(item), name
            category = object_category(item)
            if category is not None:
                assert OTHER_ART[category] in found, name
            # A search in the museums takes on what has no reason at all.
            assert bool(found) == bool(against(item, Place.SOUGHT)), name


def test_every_kind_of_copy_has_its_reason() -> None:
    told = {name: whys(_work(name, True)) for name in SPECIMENS}
    assert told["obraz z muzeum"] == ()
    assert told["plakat"] == ()
    assert told["detal w tytule"] == (Why.DETAIL,)
    assert told["detal po obrazie"] == (Why.DETAIL,)
    assert told["zdjęcie sali z dziełem"] == (Why.SCENE,)
    assert told["reprodukcja"] == (Why.REPRODUCTION,)
    assert told["szara kopia obrazu"] == (Why.GREY_COPY,)
    assert told["szara grafika z muzeum"] == ()
    assert told["znaczek"] == (Why.POSTAL,)
    assert told["dokument"] == (Why.DOCUMENT,)
    assert told["archiwum fotografii"] == (Why.ARCHIVE_PHOTO,)
    assert told["archiwum sztuki, szare"] == (Why.GREY_SLIDE,)
    assert told["kopia z Openverse"] == (Why.OPENVERSE_COPY,)
    assert told["fotografia z Openverse"] == (Why.OPENVERSE_PHOTO, Why.PHOTOGRAPH)
    assert told["fotografia z muzeum"] == (Why.PHOTOGRAPH,)
    assert told["rękopis"] == (Why.MANUSCRIPT,)
    assert told["rzeźba"] == (Why.SCULPTURE,)
    assert told["ceramika"] == (Why.DECORATIVE,)
    assert told["odłożone przez Strażnika"] == (Why.SEEN,)


def test_every_reason_has_a_name() -> None:
    assert set(NAMES) == set(Why)
    assert set(OTHER_ART.values()) == set(Why) - COPIES - STUDY_ONLY


#: The place of the verdict each place of the rules matrix asks.
ASKS = {
    "katalog": Place.LISTED,
    "katalog, szukane słowem": Place.FOUND,
    "studium dnia": Place.PROPOSED,
    "karta Odkrywaj z katalogu": Place.PROPOSED,
    "odpowiedź muzeum": Place.MUSEUM,
    "Szukaj w muzeach": Place.SOUGHT,
    "karta Odkrywaj z muzeów": Place.SOUGHT,
    "Strażnik": Place.TIDIED,
    "Nocny przegląd": Place.TIDIED,
    "powtórki": Place.COMPARED,
    "studium na karcie": Place.STUDIED,
}
#: Where a place leaves a work out for a reason of its own, not of the
#: work's kind: the work of the day wants a large picture and no archive's
#: slide, the gatekeeper looks at no museum's own works.
OWN_WISHES = {
    ("studium dnia", "archiwum sztuki, kolor"),
    ("studium dnia", "mały obraz"),
    ("Strażnik", "obraz z muzeum"),
    ("Strażnik", "szara grafika z muzeum"),
    ("Strażnik", "plakat"),
    # A page of sketches, a design: no study of the day (as no study at all).
    ("studium dnia", "kartka szkiców"),
    ("studium dnia", "projekt architekta"),
    ("Strażnik", "kartka szkiców"),
    ("Strażnik", "projekt architekta"),
}


def test_the_table_answers_as_every_place_does_today() -> None:
    """The verdict beside the frozen matrix: a work with a reason the place
    minds is left out there, a work without one is shown."""
    assert set(ASKS) == set(PLACES) and set(MINDS) == set(Place)
    for name in SPECIMENS:
        for pooled, marks in zip((True, False), EXPECTED[name], strict=True):
            item = _work(name, pooled)
            for place, mark in zip(PLACES, marks, strict=True):
                shown = not against(item, ASKS[place])
                if (place, name) in OWN_WISHES:
                    assert shown and mark == "-", (name, place)
                else:
                    assert shown == (mark == "+"), (name, pooled, place)


def test_a_category_asked_for_lets_its_works_in() -> None:
    bust = _work("rzeźba", True)
    assert against(bust, Place.SOUGHT) == (Why.SCULPTURE,)
    assert against(bust, Place.SOUGHT, [SCULPTURE]) == ()
    assert against(bust, Place.SOUGHT, [PHOTOGRAPHY]) == (Why.SCULPTURE,)
    assert against(_work("rzeźba", False), Place.FOUND, [SCULPTURE]) == ()
    # A copy stays out whatever is asked for.
    stamp = _work("znaczek", True)
    assert against(stamp, Place.SOUGHT, [SCULPTURE, PHOTOGRAPHY]) == (Why.POSTAL,)


def test_what_the_owner_kept_is_his_to_see_and_never_proposed(service: FrameService) -> None:
    """A detail, a reproduction and a stamp he kept: in Ulubione, found by a
    word (the stamp but listed), on his playlist; on no card of Discover,
    not the work of the day (Mateusz 2026-11-11)."""
    library = service.library
    kept = {
        name: _work(name, False).model_copy(update={"favorite": True})
        for name in ("obraz z muzeum", "detal w tytule", "reprodukcja", "znaczek")
    }
    for item in kept.values():
        library.upsert(item)
    ids = {name: item.id for name, item in kept.items()}
    art = PlaylistRules(kinds=[ItemKind.ARTWORK])

    def found(rules: PlaylistRules, **how: bool) -> set[str]:
        return {i.id for i in library.query(rules, **how)[1]}

    hearts = art.model_copy(update={"favorites_only": True})
    monet = art.model_copy(update={"artists": ["Claude Monet"]})
    assert found(hearts) == set(ids.values())
    assert found(monet) == {ids["obraz z muzeum"], ids["detal w tytule"], ids["reprodukcja"]}
    # The server's own cards: the painting alone...
    assert found(art, proposing=True) == {ids["obraz z muzeum"]}
    assert found(monet, proposing=True) == {ids["obraz z muzeum"]}
    # ... but for a card of his own works, which are his whatever they are.
    assert found(hearts, proposing=True) == set(ids.values())
    assert {i.id for i in service.daily.pool(date(2026, 11, 11), [])} <= {ids["obraz z muzeum"]}
