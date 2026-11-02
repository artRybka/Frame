"""What a work led to ("Co z niego wyrosło"): later works looked up once in
the museums, with what was found kept."""

from __future__ import annotations

from frame_server.ai.daily import Legacy
from frame_server.later import LaterWorks, same_work
from frame_server.library import Item, ItemKind
from frame_server.service import FrameService

WAVE = Legacy(
    year="1897",
    who="Camille Claudel",
    title="Fala",
    text="Trzy kąpiące się kobiety pod falą z onyksu.",
    search="Claudel The Wave",
)
LETTER = Legacy(
    year="1888", who="Vincent van Gogh", title="List do Thea", text="Pisze o fali.", search=""
)


def _work(item_id: str, title: str, artist: str) -> Item:
    return Item(
        id=item_id, source="met", source_id=item_id, kind=ItemKind.ARTWORK, title=title,
        artist=artist,
    )  # fmt: skip


def test_a_museum_copy_needs_the_author_and_a_title_word() -> None:
    assert same_work(_work("met:9", "The Wave", "Camille Claudel"), WAVE)
    assert not same_work(_work("met:9", "The Waltz", "Camille Claudel"), WAVE)
    assert not same_work(_work("met:9", "The Wave", "Gustave Courbet"), WAVE)


def test_later_works_are_looked_up_once(service: FrameService) -> None:
    asked: list[str] = []
    museum = [
        _work("met:9", "The Waltz", "Camille Claudel"),
        _work("met:8", "The Wave", "Camille Claudel"),
    ]

    def search(query: str, limit: int) -> tuple[int, list[Item], list[str]]:
        asked.append(query)
        return len(museum), museum, []

    later = LaterWorks(service.library, search)
    item = _work("met:1", "Under the Wave off Kanagawa", "Katsushika Hokusai")
    found = later.look(item, [WAVE, LETTER])
    wave, letter = found.values()
    assert wave.item is not None and wave.item.id == "met:8"
    assert letter.item is None
    assert asked == ["Claudel The Wave"]  # no search words, no museum

    # Kept, not asked again.
    assert later.missing(item.id, [WAVE, LETTER]) == []
    assert later.look_soon(item, [WAVE, LETTER]) is False
    assert later.known(item.id) == found


def test_the_catalogue_copy_is_looked_for_once_an_hour(service: FrameService) -> None:
    later = LaterWorks(service.library, lambda query, limit: (0, [], []))
    now = [0.0]
    later.clock = lambda: now[0]
    item = service.library.upsert(_work("met:1", "Under the Wave off Kanagawa", "Hokusai"))
    assert later.in_catalogue(item, WAVE) is None
    assert later.in_catalogue(item, LETTER) is None  # no search words: not looked for

    # Not looked for again on every page (a second on a NAS)...
    service.library.upsert(_work("met:8", "The Wave", "Camille Claudel"))
    now[0] = 600.0
    assert later.in_catalogue(item, WAVE) is None
    # ...only once the hour is over.
    now[0] = 3601.0
    copy = later.in_catalogue(item, WAVE)
    assert copy is not None and copy.id == "met:8"
    # The copy set aside is not shown, though kept.
    service.library.update("met:8", excluded=True)
    now[0] = 3700.0
    assert later.in_catalogue(item, WAVE) is None
