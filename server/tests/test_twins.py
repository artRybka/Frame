"""One work under other titles, and details of works, told by their pictures
(frame_server.library.twins; Vermeer, Mateusz 2026-11-09)."""

from __future__ import annotations

import random
import threading
from typing import Any

import pytest
from PIL import Image, ImageDraw, ImageOps
from test_sharper import _detail, _print

from frame_server.library import Item, PlaylistRules
from frame_server.library.twins import VERSION
from frame_server.library.verdict import copy_whys
from frame_server.library.vocabulary import is_detail, is_openverse_copy
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


def _large(seed: int, size: tuple[int, int] = (2400, 2000)) -> Image.Image:
    """A made-up painting drawn at its full size, fine shapes all over (a
    small one enlarged is too smooth for a detail of it to be told)."""
    rng = random.Random(seed)
    img = Image.new("RGB", size, (235, 225, 200))
    draw = ImageDraw.Draw(img)
    for _ in range(5000):
        x, y = rng.randrange(size[0]), rng.randrange(size[1])
        w, h = rng.randrange(6, 90), rng.randrange(6, 90)
        tone = tuple(rng.randrange(256) for _ in range(3))
        shape = draw.ellipse if rng.random() < 0.5 else draw.rectangle
        shape((x, y, x + w, y + h), fill=tone, outline=(20, 20, 20))
    return img


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


def test_two_museums_are_never_one_work(service: FrameService) -> None:
    """Even through a third picture: the one under another artist's name
    is a copy of one of them (by its hash), never both."""
    painting = _print(5, (600, 700))
    _work(service, "met:1", painting, title="A")
    _work(service, "rijks:2", painting, title="B")
    _work(service, "wmc:3", painting, title="C", artist="Gerard ter Borch")
    service.twins.look()
    assert _ids(service, "") >= {"met:1", "rijks:2"}
    copy = service.library.get("wmc:3")
    assert copy is not None and copy.copy_of in {"met:1", "rijks:2"}


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
    service.twins.search_delay = 0
    from frame_server.web.library_api import list_items

    list_items(service, q="")  # no search: nothing to look at
    list_items(service, q="vermeer", sort="relevance")
    assert asked.wait(5)
    assert len(keys) == 1 and len(keys[0]) == 1


def test_details_by_title_and_openverse_copies() -> None:
    def item(source: str, title: str, url: str = "") -> Item:
        return Item(id=f"{source}:1", source=source, source_id="1", title=title, url=url)

    assert copy_whys(item("wmc", "Young Woman with a Water Jug (detal)"))
    assert copy_whys(item("wikiart", "The Procuress, detail (supposed self-portrait)"))
    assert copy_whys(item("wmc", "Vermeer - Girl reading a Letter at an Open Window, detail"))
    assert not copy_whys(item("met", "Architectural Detail"))
    assert not copy_whys(item("wmc", "Fragment of an Altarpiece"))
    assert not copy_whys(item("wmc", "The Art of Painting"))
    raw = item("openverse", "Young Woman Water Pitcher", "https://www.rawpixel.com/image/1015474")
    met = item("openverse", "Study of a Young Woman", "https://www.metmuseum.org/art/1")
    flickr = item("openverse", "Monet", "https://www.flickr.com/photos/1")
    assert is_openverse_copy(raw) and is_openverse_copy(met) and not is_openverse_copy(flickr)


def test_other_titles_on_commons_are_no_part_of_the_title() -> None:
    from frame_server.library.duplicates import title_key

    long = "Study of a young woman.[1] Inne tytuły: Portrait of a Young Woman."
    assert title_key(long, "Jan Vermeer") == title_key("Study of a Young Woman")


def test_a_small_detail_is_found_in_the_large_picture(service: FrameService) -> None:
    """A head of "The Night Watch" is 40 px of the painting's thumbnail:
    it is laid over the painting's large picture (Mateusz 2026-11-09)."""
    painting = _large(7)
    whole = _work(service, "rijks:1", painting.resize((600, 500)), title="The Night Watch")
    service.library.update("rijks:1", width=2400, height=2000)
    path = service.images.image_path(whole)
    path.parent.mkdir(parents=True, exist_ok=True)
    painting.save(path, "JPEG", quality=92)
    head = painting.crop((900, 700, 1280, 1020)).resize((760, 640))
    _work(service, "wmc:2", head, title="The Nightwatch Jan Brughman")
    # Another work whose title shares the word: no detail of it.
    _work(service, "wmc:3", _large(8, (760, 640)), title="The Nightwatch, a study")
    service.twins.look()
    head_item = service.library.get("wmc:2")
    other = service.library.get("wmc:3")
    assert head_item is not None and head_item.detail_of == "rijks:1"
    assert other is not None and not other.detail_of
    assert _ids(service, "rembrandt vermeer night") <= {"rijks:1", "wmc:3"}


def test_the_first_maker_named_and_file_name_details() -> None:
    from frame_server.library.twins import artist_key, title_words

    lundens = artist_key("Gerrit Lundens")
    assert artist_key("Przypisywany Gerrit Lundens / Według Rembrandt") == lundens
    assert artist_key("attributed to Gerrit Lundens") == lundens
    assert artist_key("after Rembrandt") == artist_key("Rembrandt")
    assert "nightwatch" in title_words("The Night Watch") & title_words("The Nightwatch")
    assert not title_words("Portrait of a Young Woman")
    detail = Item(id="wmc:1", source="wmc", source_id="1", title="Night_Watch_detail_1")
    assert is_detail(detail)
    assert not is_detail(Item(id="wmc:2", source="wmc", source_id="2", title="Detailed_Map"))


def _wall(painting: Image.Image) -> Image.Image:
    """A photograph of the painting in its frame on a museum's wall, the
    wall and the floor around it (Commons, Openverse; Mateusz 2026-11-10)."""
    framed = ImageOps.expand(painting.resize((420, 490)), border=36, fill=(150, 110, 40))
    room = Image.new("RGB", (1500, 1100), (200, 196, 186))
    draw = ImageDraw.Draw(room)
    draw.rectangle((0, 900, 1500, 1100), fill=(90, 70, 50))
    room.paste(framed, (520, 220))
    return room


def test_a_painting_on_a_wall_is_no_copy_of_it(service: FrameService) -> None:
    painting = _print(9, (600, 700))
    _work(service, "met:1", painting, title="Young Woman with a Lute")
    _work(service, "wmc:2", _wall(painting), title="Vermeer at the Met, gallery 964")
    service.twins.look()
    photo = service.library.get("wmc:2")
    assert photo is not None and photo.scene_of == "met:1" and not photo.copy_of
    assert copy_whys(photo)
    assert _ids(service, "vermeer") == {"met:1"}


def test_one_scan_under_two_names_is_one_work(service: FrameService) -> None:
    """Europeana's "Johannes Vermeer van Delft" and Commons' Jan Vermeer:
    their pictures' hashes find each other whoever the sources name."""
    painting = _print(10, (600, 700))
    _work(service, "wmc:1", painting, title="Alegoria malarstwa", artist="Jan Vermeer")
    _work(
        service,
        "wikiart:2",
        painting.resize((480, 560)),
        title="Die Malkunst",
        artist="Pieter de Hooch",
    )
    service.twins.look()
    hashed = [service.library.get(i) for i in ("wmc:1", "wikiart:2")]
    assert all(i is not None and len(i.picture_hash) == 64 for i in hashed)
    assert len(_ids(service, "")) == 1


def test_a_picture_without_its_thumbnail_is_looked_at_later(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from frame_server.library.images import Gone

    painting = _print(11, (600, 700))
    _work(service, "met:1", painting, title="The Milkmaid")
    late = _work(service, "wmc:2", painting, title="Mleczarka")
    service.images.thumb_path(late).unlink()

    def resting(item: Item, urgent: bool = False) -> Any:
        raise RuntimeError("resting")

    monkeypatch.setattr(service.images, "ensure_thumb", resting)
    service.twins.look()
    waiting = service.library.get("wmc:2")
    assert waiting is not None and waiting.twins_seen == 0 and not waiting.picture_hash

    def gone(item: Item, urgent: bool = False) -> Any:
        raise Gone("nothing")

    monkeypatch.setattr(service.images, "ensure_thumb", gone)
    service.twins.look()
    seen = service.library.get("wmc:2")
    assert seen is not None and seen.twins_seen == VERSION


def test_a_large_picture_not_downloaded_is_tried_again(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from frame_server.library.twins import LARGE_VERSION

    painting = _large(12)
    _work(service, "rijks:1", painting.resize((600, 500)), title="The Night Watch")
    service.library.update("rijks:1", width=2400, height=2000)
    head = painting.crop((900, 700, 1280, 1020)).resize((760, 640))
    _work(service, "wmc:2", head, title="The Nightwatch Jan Brughman")
    downloads: list[str] = []

    def sample(url: str, urgent: bool = False) -> Image.Image:
        downloads.append(url)
        return painting

    monkeypatch.setattr(service.images, "sample", sample)
    service.twins.look(downloads=0)
    waiting = service.library.get("wmc:2")
    assert waiting is not None and not waiting.detail_of and waiting.twins_large == 0
    assert waiting.twins_seen == VERSION
    service.twins.look()
    found = service.library.get("wmc:2")
    assert found is not None and found.detail_of == "rijks:1" and len(downloads) == 1
    whole = service.library.get("rijks:1")
    assert whole is not None and whole.twins_large == LARGE_VERSION
    # Done with: no download the next night.
    service.twins.look()
    assert len(downloads) == 1


def test_what_the_pictures_told_survives_a_new_answer(service: FrameService) -> None:
    painting = _print(13, (600, 700))
    _work(service, "met:1", painting, title="The Milkmaid")
    copy = _work(service, "wmc:2", painting.resize((480, 560)), title="Mleczarka")
    service.twins.look()
    before = service.library.get("wmc:2")
    assert before is not None and before.copy_of == "met:1" and before.picture_hash
    service.library.upsert(copy.model_copy(update={"title": "Mleczarka (Vermeer)"}))
    after = service.library.get("wmc:2")
    assert after is not None and after.title == "Mleczarka (Vermeer)"
    assert (after.copy_of, after.twins_seen, after.picture_hash) == (
        "met:1",
        VERSION,
        before.picture_hash,
    )


def test_a_museums_answer_names_the_catalogues_copy(service: FrameService) -> None:
    """Commons' "Het meisje met de parel" the pictures showed to be the
    catalogue's Mauritshuis copy comes with it as its twin; a detail the
    library holds is left out (Mateusz 2026-11-10)."""
    from frame_server.web.library_api import remote_items

    painting = _print(14, (600, 700))
    museum = _work(service, "met:1", painting, title="Girl with a Pearl Earring")
    commons = _work(service, "wmc:2", painting.resize((480, 560)), title="Het meisje met de parel")
    head = _work(service, "wmc:3", _detail(painting), title="Meisje met de parel")
    service.twins.look()
    shown = {r.item.id: r.twin for r in remote_items(service, [museum, commons, head])}
    assert shown == {"met:1": None, "wmc:2": "met:1"}


def test_artist_names_with_a_town_and_file_name_details() -> None:
    from frame_server.library.twins import artist_key

    vermeer = artist_key("Johannes Vermeer")
    assert artist_key("Johannes Vermeer van Delft") == vermeer
    assert artist_key("Johannes Vermeer (Dutch, Delft 1632–1675 Delft)") == vermeer
    assert artist_key("Rembrandt van Rijn") != artist_key("Rembrandt")

    def wmc(url: str) -> Item:
        return Item(id="wmc:1", source="wmc", source_id="1", title="Uliczka", url=url)

    page = "https://commons.wikimedia.org/wiki/File:"
    assert is_detail(wmc(page + "Vermeer_-_The_Little_Street_detail_enfants.JPG"))
    assert is_detail(wmc(page + "Vermeer_Little_Street_(d%C3%A9tail).jpg"))
    assert not is_detail(wmc(page + "The_Little_Street_by_Johannes_Vermeer_(1).jpg"))
    assert not is_detail(wmc(page + "Detailed_map_of_Delft.jpg"))
