"""One work under other titles, and details of works, told by their pictures
(frame_server.library.twins; Vermeer, Mateusz 2026-11-09)."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from PIL import Image, ImageOps
from test_sharper import _detail, _print

from frame_server.library import Item, PlaylistRules
from frame_server.library.twins import VERSION
from frame_server.library.vocabulary import is_copy, is_detail, is_openverse_copy
from frame_server.service import FrameService


def _work(service: FrameService, item_id: str, img: Image.Image, **fields: Any) -> Item:
    source, _, source_id = item_id.partition(":")
    fields.setdefault("artist", "Johannes Vermeer")
    item = Item(
        id=item_id,
        source=source,
        source_id=source_id,
        width=img.width,
        height=img.height,
        pooled=True,
        **fields,
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path, "JPEG", quality=90)
    service.library.upsert(item)
    return item


def _ids(service: FrameService, query: str) -> set[str]:
    return {i.id for i in service.library.query(PlaylistRules(query=query))[1]}


def test_one_painting_under_three_titles_is_one_work(service: FrameService) -> None:
    painting = _print(1, (600, 700))
    _work(service, "wmc:1", painting, title="Lekcja muzyki", year=1662)
    _work(service, "wikiart:2", painting.resize((420, 490)), title="The music lesson", year=1665)
    _work(service, "europeana:9~3", painting.resize((400, 467)), title="Die Musikstunde")
    _work(service, "wikiart:4", _print(2, (600, 700)), title="The Astronomer", year=1668)
    assert len(_ids(service, "vermeer")) == 4

    assert service.twins.look() == 4
    stored = {i: service.library.get(i) for i in ("wmc:1", "wikiart:2", "europeana:9~3")}
    assert all(i is not None and i.twins_seen == VERSION for i in stored.values())
    # Shown once, in the best copy; the other painting stays.
    assert _ids(service, "vermeer") == {"europeana:9~3", "wikiart:4"}
    assert service.library.spare_copies() == {"wmc:1", "wikiart:2"}
    # Looked at once.
    assert service.twins.look() == 0


def test_a_detail_of_a_painting_shown_whole_is_left_out(service: FrameService) -> None:
    painting = _print(3, (600, 700))
    _work(service, "met:1", painting, title="Young Woman with a Water Pitcher")
    strip = painting.crop((150, 0, 400, 700))
    _work(service, "wmc:2", strip, title="Young Woman with a Water Pitcher")
    _work(service, "wmc:3", _detail(painting), title="Kobieta z dzbanem")
    service.twins.look()
    for item_id in ("wmc:2", "wmc:3"):
        item = service.library.get(item_id)
        assert item is not None and item.detail_of == "met:1" and is_detail(item)
    assert _ids(service, "vermeer") == {"met:1"}


def test_a_framed_copy_is_no_proof_of_a_detail(service: FrameService) -> None:
    """Of two pictures from Commons, one around the other, either can be the
    whole (the other a detail, or a frame around it): they are copies."""
    painting = _print(4, (600, 700))
    framed = ImageOps.expand(painting, border=90, fill=(120, 80, 30))
    _work(service, "wmc:1", painting, title="Alegoria malarstwa")
    _work(service, "wmc:2", framed, title="The Art of Painting")
    service.twins.look()
    for item_id in ("wmc:1", "wmc:2"):
        item = service.library.get(item_id)
        assert item is not None and not item.detail_of
    assert len(_ids(service, "vermeer")) == 1


def test_other_artists_and_two_museums_are_not_compared(service: FrameService) -> None:
    painting = _print(5, (600, 700))
    _work(service, "met:1", painting, title="A")
    _work(service, "rijks:2", painting, title="B")
    _work(service, "wmc:3", painting, title="C", artist="Gerard ter Borch")
    service.twins.look()
    assert _ids(service, "") >= {"met:1", "rijks:2", "wmc:3"}


def test_a_search_looks_at_its_artists(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    painting = _print(6, (600, 700))
    _work(service, "wmc:1", painting, title="Mleczarka")
    _work(service, "rijks:2", painting.resize((500, 583)), title="The Milkmaid")
    asked = threading.Event()
    keys: list[set[str]] = []

    def look(wanted: set[str] | None = None, **_: object) -> int:
        keys.append(set(wanted or ()))
        asked.set()
        return 0

    monkeypatch.setattr(service.twins, "look", look)
    from frame_server.web.library_api import list_items

    list_items(service, q="")  # no search: nothing to look at
    list_items(service, q="vermeer", sort="relevance")
    assert asked.wait(5)
    assert len(keys) == 1 and len(keys[0]) == 1


def test_details_by_title_and_openverse_copies() -> None:
    def item(source: str, title: str, url: str = "") -> Item:
        return Item(id=f"{source}:1", source=source, source_id="1", title=title, url=url)

    assert is_copy(item("wmc", "Young Woman with a Water Jug (detal)"))
    assert is_copy(item("wikiart", "The Procuress, detail (supposed self-portrait)"))
    assert is_copy(item("wmc", "Vermeer - Girl reading a Letter at an Open Window, detail"))
    assert not is_copy(item("met", "Architectural Detail"))
    assert not is_copy(item("wmc", "Fragment of an Altarpiece"))
    assert not is_copy(item("wmc", "The Art of Painting"))
    raw = item("openverse", "Young Woman Water Pitcher", "https://www.rawpixel.com/image/1015474")
    met = item("openverse", "Study of a Young Woman", "https://www.metmuseum.org/art/1")
    flickr = item("openverse", "Monet", "https://www.flickr.com/photos/1")
    assert is_openverse_copy(raw) and is_openverse_copy(met) and not is_openverse_copy(flickr)


def test_other_titles_on_commons_are_no_part_of_the_title() -> None:
    from frame_server.library.duplicates import title_key

    long = "Study of a young woman.[1] Inne tytuły: Portrait of a Young Woman."
    assert title_key(long, "Jan Vermeer") == title_key("Study of a Young Woman")
