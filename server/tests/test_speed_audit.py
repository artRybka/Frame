"""What the audit of 2026-11-14 made quicker answers as before: what is
worked out of a work once (its reasons, its texts without accents), the
language model's settings and counts kept while unchanged, a kept thumbnail
read in one go."""

from __future__ import annotations

import asyncio
import gc
import io
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from PIL import Image

from frame_server import memory, night
from frame_server import storage as storage_module
from frame_server.ai import AiConfigUpdate
from frame_server.ai.config import STATE_KEY
from frame_server.ai.keywords import KIND
from frame_server.config import Settings
from frame_server.library import Item, ItemKind, Library, Look, Playlist, PlaylistRules, zoom
from frame_server.library import repo as repo_module
from frame_server.library.memo import PerItem
from frame_server.library.models import Note, SharperCopy
from frame_server.library.repo import Abandoned, asked_by
from frame_server.library.search_index import folded_fields, folded_text
from frame_server.library.term_index import TermIndex
from frame_server.library.verdict import Why, whys
from frame_server.player import TILE_WORKS_KEY
from frame_server.service import FrameService
from frame_server.storage import MEASURE_MAX_AGE, USAGE_KEY, StorageUsage
from frame_server.web import app as app_module
from frame_server.web import create_app, discover_api
from frame_server.web.compress import GZIP_FROM


def _work(item_id: str = "met:1", **kw: Any) -> Item:
    kw.setdefault("kind", ItemKind.ARTWORK)
    return Item(id=item_id, source=item_id.split(":")[0], source_id=item_id, **kw)


# -- worked out once of each record ------------------------------------------


def test_a_record_is_worked_on_once_and_its_copy_anew() -> None:
    asked: list[str] = []

    def title(item: Item) -> str:
        asked.append(item.title)
        return item.title.upper()

    memo = PerItem(title)
    work = _work(title="Żółw")
    assert memo(work) == "ŻÓŁW" and memo(work) == "ŻÓŁW"
    assert asked == ["Żółw"]
    # The library never changes a record where it stands: it puts a copy in
    # its place, and that one is asked anew.
    other = work.model_copy(update={"title": "Bocian"})
    assert memo(other) == "BOCIAN" and memo(work) == "ŻÓŁW"
    assert asked == ["Żółw", "Bocian"]


def test_a_record_changed_where_it_stands_is_asked_again() -> None:
    work = _work(title="Żółw", artist="Józef Chełmoński")
    assert whys(work) == () and folded_text(work).startswith("zolw jozef chelmonski")
    assert folded_fields(work)[:2] == ("jozef chelmonski", "zolw")
    work.title = "Postage stamp"
    work.classification = "Stamps"
    assert whys(work) == (Why.POSTAL,)
    assert folded_text(work).startswith("postage stamp") and folded_fields(work)[1] == (
        "postage stamp"
    )


def test_nothing_is_kept_of_a_record_let_go() -> None:
    memo = PerItem(lambda item: item.title)
    work = _work(title="Żółw")
    memo(work)
    assert len(memo) == 1
    del work
    gc.collect()
    assert len(memo) == 0


def test_the_library_answers_by_the_record_it_holds_now(service: FrameService) -> None:
    library = service.library
    library.upsert(_work(title="Bociany", artist="Józef Chełmoński"))
    assert library.query(PlaylistRules(query="bociany"))[0] == 1
    library.update("met:1", title="Żurawie")
    assert library.query(PlaylistRules(query="bociany"))[0] == 0
    assert library.query(PlaylistRules(query="zurawie"))[0] == 1
    library.update("met:1", classification="Sculpture")
    held = library.get("met:1")
    assert held is not None and whys(held) == (Why.SCULPTURE,)


# -- the language model's settings and counts --------------------------------


def test_the_settings_are_read_again_only_when_saved_anew(service: FrameService) -> None:
    store = service.ai_config
    first = store.config
    assert store.config is first
    store.update(AiConfigUpdate(monthly_limit_usd=7))
    assert store.config is not first and store.config.monthly_limit_usd == 7
    # Written past the store (a restored backup): read as it is saved.
    saved = store.config.model_dump() | {"monthly_limit_usd": 9}
    service.library.set_state(STATE_KEY, saved)
    assert store.config.monthly_limit_usd == 9


def test_the_count_is_kept_until_a_work_a_note_or_the_settings_change(
    service: FrameService,
) -> None:
    library, worker = service.library, service.ai
    service.ai_config.set_key("sk-ant-test-0000abcd")
    job = worker.jobs[KIND]
    looked: list[str] = []
    wanted = job.wanted

    def counted(item: Item) -> bool:
        looked.append(item.id)
        return wanted(item)

    job.wanted = counted  # type: ignore[method-assign]
    library.upsert(_work("met:1", title="Bociany"))
    library.upsert(_work("met:2", title="Żurawie", pooled=True))
    assert worker.progress(KIND).waiting == 1 and sorted(looked) == ["met:1", "met:2"]
    assert worker.progress(KIND).waiting == 1 and len(looked) == 2  # kept

    library.update("met:2", show_count=1)  # a pooled work once shown is the owner's
    assert worker.progress(KIND).waiting == 2 and len(looked) == 4

    held = library.get("met:1")
    assert held is not None
    library.save_note(
        Note(
            item_id="met:1",
            kind=KIND,
            model="m",
            prompt_version=job.prompt_version,
            source_hash=job.source_hash(held),
            data={"refused": True},
        )
    )
    progress = worker.progress(KIND)
    assert (progress.done, progress.waiting, progress.refused) == (1, 1, 1)

    service.ai_config.update(AiConfigUpdate(keywords_artworks=False))
    progress = worker.progress(KIND)
    assert (progress.done, progress.waiting) == (1, 0)


def test_a_photo_sent_once_is_counted_each_time(service: FrameService) -> None:
    """Whether it waits follows from "Historia przesłanych", which changes
    none of what the kept count is made of."""
    service.ai_config.set_key("sk-ant-test-0000abcd")
    sent = service.library.upsert(_work("own:1", kind=ItemKind.PHOTO, look=Look()))
    assert service.ai.progress(KIND).waiting == 0
    service.player.remember_sent(sent)
    assert service.ai.progress(KIND).waiting == 1


# -- a kept thumbnail ---------------------------------------------------------


def test_a_kept_thumbnail_is_read_whole_and_a_missing_one_is_none(service: FrameService) -> None:
    images = service.images
    work = _work("met:1")
    assert images.thumb_bytes(work.id) is None and images.thumb_bytes(work.id, tile=True) is None
    path = images.thumb_path(work)
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = jpeg_bytes((90, 120, 200), (640, 480))
    path.write_bytes(kept)
    assert images.thumb_bytes(work.id) == kept
    tile = images.thumb_bytes(work.id, tile=True)
    assert tile is not None and tile == images.tile(path).read_bytes()
    assert images.thumb_bytes("owned:nothing.jpg") is None


def test_the_app_gets_a_kept_thumbnail_and_its_tile(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, seed_library=False, scheduler=False))
    kept = jpeg_bytes((90, 120, 200), (640, 480))
    with TestClient(app) as client:
        thumbs = tmp_path / "library" / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        (thumbs / "met_1.jpg").write_bytes(kept)
        answer = client.get("/api/library/items/met:1/thumb")
        assert answer.status_code == 200 and answer.content == kept
        assert answer.headers["content-type"] == "image/jpeg"
        assert answer.headers["cache-control"] == "max-age=86400"
        assert answer.headers["content-length"] == str(len(kept))
        tile = client.get("/api/library/items/met:1/thumb", params={"tile": "true"})
        assert tile.status_code == 200 and tile.headers["cache-control"] == "max-age=86400"
        with Image.open(io.BytesIO(tile.content)) as img:
            assert img.size == (640, 480)  # nothing around it to cut


def test_a_phone_that_holds_a_thumbnail_is_told_it_is_still_the_one(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, seed_library=False, scheduler=False))
    kept = jpeg_bytes((90, 120, 200), (640, 480))
    address = "/api/library/items/met:1/thumb"
    with TestClient(app) as client:
        thumbs = tmp_path / "library" / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        (thumbs / "met_1.jpg").write_bytes(kept)
        stamp = client.get(address).headers["etag"]
        assert stamp.startswith('"') and stamp.endswith('"')
        for held in (stamp, f"W/{stamp}", f'"another", {stamp}'):
            same = client.get(address, headers={"If-None-Match": held})
            assert same.status_code == 304 and same.content == b""
            assert "content-length" not in same.headers  # nor a length of nothing
            assert same.headers["etag"] == stamp  # kept for another day
            assert same.headers["cache-control"] == "max-age=86400"
        other = client.get(address, headers={"If-None-Match": '"another"'})
        assert other.status_code == 200 and other.content == kept
        # The tile is a file of its own, with a stamp of its own.
        tile = client.get(address, params={"tile": "true"})
        again = client.get(
            address, params={"tile": "true"}, headers={"If-None-Match": tile.headers["etag"]}
        )
        assert again.status_code == 304
        # Another picture of the work (a better copy): sent whole, a new stamp.
        newer = jpeg_bytes((200, 120, 90), (640, 480))
        (thumbs / "met_1.jpg").write_bytes(newer + b"\0")
        changed = client.get(address, headers={"If-None-Match": stamp})
        assert changed.status_code == 200 and changed.content == newer + b"\0"
        assert changed.headers["etag"] != stamp


# -- Szukaj: a count let go, the next pages of a list --------------------------


def _catalogue(library: Library, count: int) -> list[Item]:
    return [
        library.upsert(_work(f"met:{n}", title=f"Rain no. {n}", artist="Jan Deszcz", year=1800 + n))
        for n in range(count)
    ]


def test_a_count_stops_once_its_asker_has_let_go(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    _catalogue(library, 12)
    index = library.term_index()
    with pytest.raises(Abandoned), asked_by(lambda: True):
        index.word_count("rain")
    # Nothing was kept of it: asked again, it is counted to the end.
    with asked_by(lambda: False):
        assert index.word_count("rain") == 12
    assert library.query(PlaylistRules(query="rain"), limit=0)[0] == 12


def test_the_next_page_follows_the_order_of_the_one_before(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    _catalogue(library, 9)
    rules = PlaylistRules(query="rain")
    total, first = library.query(rules, sort="recent", limit=3, paged=True)
    whole = library.query(rules, sort="recent")[1]
    assert total == 9 and first == whole[:3]

    # A museum's work joins meanwhile, and comes first in a new look.
    library.upsert(_work("aic:new", title="Rain today", artist="Jan Deszcz"))
    assert library.query(rules, sort="recent", limit=1)[1][0].id == "aic:new"
    # The list that is scrolled goes on where it was: no work twice.
    total, second = library.query(rules, sort="recent", offset=3, limit=3, paged=True)
    assert total == 9 and [i.id for i in second] == [i.id for i in whole[3:6]]
    # Asked without it (the server's own lists), the library as it is now.
    assert library.query(rules, sort="recent", offset=3, limit=3)[1][0].id == whole[2].id

    # A work hidden or liked since: hidden at once, its heart as it is now.
    library.update(whole[6].id, excluded=True)
    library.update(whole[7].id, favorite=True)
    third = library.query(rules, sort="recent", offset=6, limit=3, paged=True)[1]
    assert [i.id for i in third] == [whole[7].id, whole[8].id] and third[0].favorite
    # One with no picture found so while scrolling is left out too.
    less = rules.model_copy(update={"exclude_ids": [whole[8].id]})
    last = library.query(less, sort="recent", offset=6, limit=3, paged=True)[1]
    assert [i.id for i in last] == [whole[7].id]

    # The first page is always a new look.
    again = library.query(rules, sort="recent", limit=3, paged=True)[1]
    assert again[0].id == "aic:new"


def test_an_old_order_is_not_followed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = Library(tmp_path / "lib.db")
    _catalogue(library, 6)
    rules = PlaylistRules(query="rain")
    whole = library.query(rules, sort="recent", limit=2, paged=True)
    assert whole[0] == 6
    library.upsert(_work("aic:new", title="Rain today", artist="Jan Deszcz"))
    monkeypatch.setattr(repo_module, "ORDER_KEPT", 0.0)
    total = library.query(rules, sort="recent", offset=2, limit=2, paged=True)[0]
    assert total == 7  # looked for anew


def test_the_owners_own_lists_are_always_looked_for_anew(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    works = _catalogue(library, 6)
    for work in works:
        library.update(work.id, favorite=True)
    rules = PlaylistRules(favorites_only=True)
    assert library.query(rules, limit=2, paged=True)[0] == 6
    library.update(works[0].id, favorite=False)
    assert library.query(rules, offset=2, limit=2, paged=True)[0] == 5


TITLES = [
    "The Starry Night",
    "Starry Night Over the Rhône",
    "Gwiaździsta noc",
    "Nocna straż",
    "The Night Watch",
    "Night watchman at the gate",
    "L'Étoile",
    "'t Hooft's garden",
    "Portrait of a Man (detail)",
    "A Man",
    "Żółw na łące",
    "No. 5, 1948",
    "St. Jerome in His Study",
    "Sunflowers",
    "Sun",
]
ASKED = [
    "starry night",
    "star",
    "night",
    "night watch",
    "night watches",
    "nocnej strazy",
    "noc",
    "gwiazdzista noc",
    "the",
    "the starry",
    "a man",
    "man",
    "l'et",
    "etoile",
    "'t ho",
    "(detail",
    "...",
    "no. 5",
    "st. jer",
    "zolw",
    "Żółw",
    "sun",
    "sunf",
    "of a",
    "in his",
    "rhone",
    "194",
    "xyz",
]


def test_titles_by_their_words_starts_are_those_a_look_at_every_title_finds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = Library(tmp_path / "lib.db")
    for n, title in enumerate(TITLES):
        library.upsert(_work(f"met:{n}", title=title, artist="Jan Deszcz"))
    index = library.term_index()
    asked = [[words] for words in ASKED] + [[a, b] for a, b in zip(ASKED, ASKED[5:], strict=False)]
    quick = [index.titles(forms, limit=10) for forms in asked]
    assert sum(1 for found in quick if found) > 20
    # Every title looked at, as before the index of their words.
    monkeypatch.setattr(TermIndex, "_titled_with", lambda self, wanted: self._titles)
    index._titled.clear()
    assert [index.titles(forms, limit=10) for forms in asked] == quick


def test_a_new_index_takes_the_titles_words_of_the_one_before(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    for n, title in enumerate(TITLES):
        library.upsert(_work(f"met:{n}", title=title, artist="Jan Deszcz"))
    before = library.term_index()
    assert [hit.title for hit in before.titles(["sunf"])] == ["Sunflowers"]
    library.update("met:0", show_count=1)  # the catalogue changed, no title did
    same = library._build_term_index()
    same.warm(before)
    assert same._title_words is before._title_words
    library.upsert(_work("met:new", title="Sunflower field", artist="Jan Deszcz"))
    other = library._build_term_index()
    other.warm(before)
    assert other._title_words is not before._title_words
    assert [hit.title for hit in other.titles(["sunf"])] == ["Sunflowers", "Sunflower field"]


# -- Odkrywaj and the start ----------------------------------------------------


def test_the_search_index_is_made_once_when_two_wait_for_it(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    _catalogue(library, 6)
    made: list[int] = []
    make = library._make_search

    def counted() -> Any:
        made.append(1)
        return make()

    library._make_search = counted  # type: ignore[method-assign]
    # A new index is asked for behind (as when the one there is worn by
    # changes) while a thread that waits for it is making it already.
    with library._search_lock:
        library._make_search_later()
        index = library._make_search()
    for _ in range(200):
        if not library._search_building:
            break
        time.sleep(0.01)
    assert made == [1] and library.search_index() is index
    # One worn by changes is still made anew.
    for n in range(6):
        for year in (1700, 1701):
            library.update(f"met:{n}", year=year)
    for _ in range(200):
        if not library._search_building and library.search_index() is not index:
            break
        time.sleep(0.01)
    # (Twice when the first new one was ready before the last changes.)
    assert len(made) >= 2 and library.search_index() is not index


def test_a_list_among_some_works_is_that_part_of_the_whole_list(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    _catalogue(library, 8)
    # One work twice: the best copy stands for it in the whole list.
    twice = [
        library.upsert(_work(f"{source}:77", title="Rain at Dusk", artist="Jan Deszcz", year=1850))
        for source in ("wmc", "rijks")
    ]
    whole = library.query(PlaylistRules(query="rain"), sort="recent")[1]
    stands = [i.id for i in whole if i.id in {c.id for c in twice}]
    assert len(stands) == 1
    some = {"met:1", "met:5", *(c.id for c in twice), "none:0"}
    total, part = library.query(PlaylistRules(query="rain"), sort="recent", among=some)
    assert [i.id for i in part] == [i.id for i in whole if i.id in some]
    assert total == 3 and stands[0] in {i.id for i in part}
    assert library.query(PlaylistRules(query="rain"), limit=0, among=some)[0] == 3


def test_the_row_of_works_to_zoom_is_what_the_whole_list_has_of_them(
    service: FrameService,
) -> None:
    library = service.library
    try:
        zoom.known({"100", "200", "300", "400"})
        sharper = SharperCopy(
            url="https://upload.wikimedia.org/nw.jpg",
            item_id="wmc:200",
            source="wmc",
            width=3840,
            height=3124,
        )
        works = [
            _work("rijks:1", title="De Nachtwacht", artist="Rembrandt", sharper=sharper),
            _work("wmc:100", title="Garden of Earthly Delights", artist="Bosch"),
            # One work twice: only the copy that stands for it counts.
            _work("wmc:300", title="The Milkmaid", artist="Johannes Vermeer", year=1660),
            _work("rijks:3", title="The Milkmaid", artist="Johannes Vermeer", year=1660),
            _work("wmc:400", title="A Part", artist="Bosch", part_of="wmc:100"),
            _work("met:5", title="Wheat Field", artist="Vincent van Gogh"),
        ]
        for work in works:
            library.upsert(work.model_copy(update={"pooled": True}))
        service.library.set_state(TILE_WORKS_KEY, {"at": time.time(), "items": []})
        whole = library.query(limit=None, proposing=True)[1]
        expected = sorted(
            (i for i in whole if zoom.zooms(i)), key=lambda i: (not i.favorite, i.title.casefold())
        )
        row = discover_api._zoom_row(service)
        assert row is not None
        assert [r.item.id for r in row.items] == [i.id for i in expected]
        assert {"rijks:1", "wmc:100"} <= {i.id for i in expected}
        assert "wmc:400" not in {i.id for i in expected}
    finally:
        zoom.known(())


def test_the_cards_wait_after_works_came_in_but_not_with_a_hole_in_a_cover(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = service.library
    cover = library.upsert(_work("met:1", title="Rain", artist="Jan Deszcz", pooled=True))
    monkeypatch.setattr(discover_api, "_cards", (time.monotonic(), {"rain": (1, [cover])}))
    monkeypatch.setattr(discover_api, "_cards_from", discover_api._cards_key(service))
    made = discover_api._cards[0]
    assert not discover_api._cards_stale(service, made)
    # Works come in (a search in Szukaj): the round waits its time.
    library.upsert(_work("met:2", title="Snow", artist="Jan Deszcz", pooled=True))
    assert not discover_api._cards_stale(service, made)
    assert discover_api._cards_stale(service, made - discover_api.CARDS_TTL)
    # A cover's work hidden: its card would show a hole, so at once.
    library.update("met:2", excluded=True)
    assert not discover_api._cards_stale(service, made)
    library.update("met:1", excluded=True)
    assert discover_api._cards_stale(service, made)
    library.update("met:1", excluded=False)
    assert not discover_api._cards_stale(service, made)
    library.delete("met:1")
    assert discover_api._cards_stale(service, made)
    # Another day (the covers of the day, the week's themes): at once.
    library.upsert(cover)
    monkeypatch.setattr(discover_api, "_cards_from", discover_api._cards_key(service))
    assert not discover_api._cards_stale(service, made)
    monkeypatch.setattr(
        discover_api, "_cards_from", (("another day",), *discover_api._cards_from[1:])
    )
    assert discover_api._cards_stale(service, made)


def test_the_apps_larger_answers_go_out_gzipped(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, seed_library=False, scheduler=False))
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        for n in range(80):
            svc.library.upsert(
                _work(f"met:{n}", title=f"Rain no. {n} " + "ż" * 40, artist="Jan Deszcz")
            )
        large = client.get("/api/library/items", params={"limit": 80})
        assert large.status_code == 200 and large.headers["content-encoding"] == "gzip"
        assert "Accept-Encoding" in large.headers["vary"]
        assert int(large.headers["content-length"]) == large.num_bytes_downloaded
        plain = client.get(
            "/api/library/items", params={"limit": 80}, headers={"Accept-Encoding": "identity"}
        )
        assert "content-encoding" not in plain.headers
        assert plain.json() == large.json() and len(plain.json()["items"]) == 80
        assert large.num_bytes_downloaded < plain.num_bytes_downloaded // 3
        assert plain.num_bytes_downloaded >= GZIP_FROM
        # A short answer, a picture, the panel's: as they are.
        small = client.get("/api/library/items", params={"limit": 2})
        assert small.status_code == 200 and "content-encoding" not in small.headers
        thumbs = tmp_path / "library" / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        (thumbs / "met_1.jpg").write_bytes(jpeg_bytes((90, 120, 200), (1600, 1200)))
        thumb = client.get("/api/library/items/met:1/thumb")
        assert thumb.status_code == 200 and "content-encoding" not in thumb.headers
        panel = client.get("/panel/content.json")
        assert "content-encoding" not in panel.headers


# -- the disk's measure, kept --------------------------------------------------


def test_konfiguracja_is_shown_the_kept_measure_and_a_new_one_next_time(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = service.storage
    item = service.library.upsert(_work("aic:1"))
    service.images.store(item, jpeg_bytes((200, 40, 40)))
    first = storage.view().usage  # never measured: measured now
    assert first.originals_bytes > 0
    assert storage.view().usage == first  # fresh: the one kept

    # Old by now, and the disk is slow: the page gets the one kept at once.
    old = first.model_copy(update={"measured_at": first.measured_at - 2 * MEASURE_MAX_AGE})
    storage._usage = old
    service.images.remove(item)
    slow, measure = threading.Event(), storage._measure

    def slowly() -> StorageUsage:
        slow.wait(10)
        return measure()

    monkeypatch.setattr(storage, "_measure", slowly)
    monkeypatch.setattr(storage_module, "SHOWN_WAIT", 0.05)
    assert storage.view().usage == old
    again = storage._again
    assert again is not None and again.is_alive()
    assert storage.view().usage == old and storage._again is again  # one at a time
    slow.set()
    again.join(10)
    assert storage.view().usage.originals_bytes == 0  # the new one

    # A fast disk answers within the wait: the new one at once.
    storage._usage = old
    monkeypatch.setattr(storage_module, "SHOWN_WAIT", 10.0)
    assert storage.view().usage.originals_bytes == 0
    # What decides by the measure never takes an old one.
    storage._usage = old
    assert storage.usage().measured_at > old.measured_at


def test_the_disks_measure_is_kept_over_a_restart_and_taken_anew_after_a_trim(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, seed_library=False, scheduler=False)
    service = FrameService(settings)
    assert service.storage._usage is None
    service.storage.measure_behind()  # none kept: measured beside, after a start
    again = service.storage._again
    assert again is not None
    again.join(10)
    measured = service.storage._usage
    assert measured is not None
    service.storage.measure_behind()  # one kept: nothing to do
    assert service.storage._again is again
    _written(service.library, USAGE_KEY)
    service.library.close()

    service = FrameService(settings)
    assert service.storage._usage == measured
    # Trimmed: that number is wrong now, and a new one is taken at once,
    # beside, for Konfiguracja opened later.
    item = service.library.upsert(_work("aic:1"))
    service.images.store(item, jpeg_bytes((200, 40, 40)))
    service.storage.forget()
    again = service.storage._again
    assert again is not None
    again.join(10)
    anew = service.storage._usage
    assert anew is not None and anew != measured and anew.originals_bytes > 0
    _written(service.library, USAGE_KEY)
    service.library.close()
    assert FrameService(settings).storage._usage == anew


def _written(library: Library, key: str) -> None:
    """Wait for the state kept for later (``keep_state``) to reach the disk."""
    deadline = time.monotonic() + 10
    while key in library._pending and time.monotonic() < deadline:
        time.sleep(0.01)
    assert key not in library._pending


# -- the server's memory, read from outside ---------------------------------------


def test_the_memory_reading_says_what_the_process_and_the_machine_have(tmp_path: Path) -> None:
    proc, cgroup = tmp_path / "proc", tmp_path / "cgroup"
    (proc / "self").mkdir(parents=True)
    cgroup.mkdir()
    (proc / "self" / "status").write_text(
        "Name:\tpython\nVmHWM:\t 2400000 kB\nVmRSS:\t 1843200 kB\nVmSwap:\t  409600 kB\n"
    )
    (proc / "meminfo").write_text(
        "MemTotal:        8388608 kB\nMemFree:  100 kB\nMemAvailable:    1048576 kB\n"
        "SwapTotal:       2097152 kB\nSwapFree:        1048576 kB\n"
    )
    (cgroup / "memory.max").write_text("max\n")
    (cgroup / "memory.current").write_text(f"{3 * 1024**3}\n")
    assert memory.reading(proc, cgroup) == {
        "process_mb": {"resident_peak": 2343, "resident": 1800, "swapped": 400},
        "machine_mb": {"total": 8192, "available": 1024, "swap_total": 2048, "swap_free": 1024},
        "container_mb": {"used": 3072},
    }
    # Not Linux: no numbers, no error.
    assert memory.reading(tmp_path / "none", tmp_path / "none") == {
        "process_mb": {},
        "machine_mb": {},
        "container_mb": {},
    }


def test_the_owner_reads_the_servers_memory(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, seed_library=False, scheduler=False))
    with TestClient(app) as client:
        read = client.get("/api/debug/memory").json()
        assert read["works"] == 0
        assert {"process_mb", "machine_mb", "container_mb"} <= read.keys()
        assert read["process_mb"].get("resident", 1) > 0


# -- the start ---------------------------------------------------------------


def test_a_list_waits_for_the_search_index_while_it_is_made(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    _catalogue(library, 6)
    assert library._search is None
    found: list[int] = []
    asking = threading.Thread(
        target=lambda: found.append(library.query(PlaylistRules(query="rain"))[0])
    )
    with library._search_lock:  # another thread is making it
        asking.start()
        asking.join(0.3)
        # Not looked for work after work beside the one that makes it.
        assert asking.is_alive() and not found
    asking.join(10)
    assert found == [6] and library._search is not None


def test_discovers_cards_stand_again_after_a_restart(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = service.library
    cover = [
        library.upsert(_work(f"met:{n}", title=f"Rain no. {n}", artist=f"Jan Deszcz {n}"))
        for n in range(4)
    ]
    monkeypatch.setattr(discover_api, "_cards", (0.0, {}))
    monkeypatch.setattr(discover_api, "_cards_from", ())
    key = discover_api._cards_key(service)
    discover_api._keep_cards(service, key, {"rain": (7, cover), "snow": (0, [])})
    library.delete("met:3")  # gone since: left out of its cover
    assert discover_api.restore_cards(service)
    stamp, cards = discover_api._cards
    assert cards == {"rain": (7, cover[:3]), "snow": (0, [])}
    # Shown as they are: worked out again in the start's own turn, not by
    # the first visit (as cards after works came in, until they are old).
    assert not discover_api._cards_stale(service, stamp)
    assert discover_api._cards_stale(service, stamp - discover_api.CARDS_TTL)
    assert discover_api._theme_cards(service) is cards
    # ... giving way to the app's questions between the cards.
    rested: list[int] = []
    monkeypatch.setattr(discover_api, "give_way", lambda: rested.append(1))
    discover_api.cards_after_start(service)
    assert rested and discover_api._cards[1] is not cards
    assert discover_api._cards_from == discover_api._cards_key(service)
    # The round's own cards are the ones kept now.
    assert (
        library.get_state(discover_api.CARDS_STATE)["cards"].keys() == discover_api._cards[1].keys()
    )
    # Cards there already are not replaced by the kept ones.
    assert not discover_api.restore_cards(service)


def test_cards_of_another_day_or_another_shape_are_not_taken(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = service.library
    work = library.upsert(_work("met:1", title="Rain", artist="Jan Deszcz"))
    monkeypatch.setattr(discover_api, "_cards", (0.0, {}))
    monkeypatch.setattr(discover_api, "_cards_from", ())
    assert not discover_api.restore_cards(service)  # none kept
    discover_api._keep_cards(service, discover_api._cards_key(service), {"rain": (1, [work])})
    kept = library.get_state(discover_api.CARDS_STATE)
    for other in (
        {**kept, "day": "2020-01-01"},
        {**kept, "made": ["a curator's card that is no more"]},
        {"cards": kept["cards"]},
        {**kept, "cards": {"rain": "seven"}},
        {**kept, "cards": {}},
    ):
        library.keep_state(discover_api.CARDS_STATE, other)
        assert not discover_api.restore_cards(service)
        assert discover_api._cards == (0.0, {})
    # A round nobody has cards from does not rest: someone waits for it.
    rested: list[int] = []
    monkeypatch.setattr(discover_api, "give_way", lambda: rested.append(1))
    discover_api.cards_after_start(service)
    assert not rested and discover_api._cards[1]


def test_the_starts_work_goes_piece_after_piece_and_past_one_that_fails(
    service: FrameService, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    done: list[str] = []

    def failing() -> None:
        raise RuntimeError("no names")

    monkeypatch.setattr(service.player, "drop_spare_copies", lambda: done.append("works"))
    monkeypatch.setattr(service.player, "top_up", lambda: done.append("suggestions"))
    monkeypatch.setattr(service.library, "search_index", lambda: done.append("index"))
    monkeypatch.setattr(service.library, "term_index", failing)
    monkeypatch.setattr(discover_api, "suggestion_rows", lambda _: done.append("rows"))
    monkeypatch.setattr(discover_api, "cards_after_start", lambda _: done.append("cards"))
    monkeypatch.setattr(service.library, "recount", lambda: done.append("counts"))
    with caplog.at_level("INFO", logger="frame_server.web.app"):
        app_module.after_start(service)
    # (The fixture's server does not ask the museums: no topping up.)
    assert done == ["works", "index", "rows", "cards", "counts"]
    monkeypatch.setattr(service.settings, "seed_library", True)
    monkeypatch.setattr(service.library, "term_index", lambda: done.append("terms"))
    del done[:]
    app_module.after_start(service)
    assert done == ["works", "index", "terms", "rows", "cards", "counts", "suggestions"]
    assert "start: the suggestions' index failed" in caplog.text
    assert "start: the search index in " in caplog.text


def test_the_starts_work_rests_while_the_app_is_answered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(night, "_answering", 0)
    started = time.monotonic()
    night.give_way()
    assert time.monotonic() - started < 0.05
    # Until the answer is out...
    night.answering(1)
    out = threading.Timer(0.2, night.answering, args=(-1,))
    out.start()
    started = time.monotonic()
    night.give_way(5.0)
    assert 0.15 <= time.monotonic() - started < 3.0
    out.join()
    # ... but not for longer than it is given.
    night.answering(1)
    started = time.monotonic()
    night.give_way(0.2)
    assert 0.2 <= time.monotonic() - started < 3.0


def test_the_apps_questions_are_counted_while_answered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(Settings(data_dir=tmp_path, seed_library=False, scheduler=False))
    monkeypatch.setattr(night, "_answering", 0)
    seen: list[int] = []

    def rows(_: FrameService) -> list[Any]:
        seen.append(night._answering)
        return []

    monkeypatch.setattr(discover_api, "suggestion_rows", rows)
    with TestClient(app) as client:
        assert client.get("/api/suggestions").json() == []
        assert seen == [1] and night._answering == 0
        assert client.get("/api/no-such-thing").status_code == 404
        assert client.get("/api/health").status_code == 200
        assert night._answering == 0


def _playing_hearts(service: FrameService) -> tuple[list[str], Item]:
    """The frame plays the hearts, all of them shown lately; the line as
    it stands, and a work that has joined them since (not in the line)."""
    library, player = service.library, service.player
    works = [
        service.importer.add_upload(
            jpeg_bytes((40 * n, 40, 200)), kind=ItemKind.OWN, title=f"Work {n}", artist="Ala"
        )
        for n in range(1, 6)
    ]
    lately = datetime.now(UTC).isoformat(timespec="seconds")
    for item in works[:4]:
        library.update(item.id, favorite=True, last_shown_at=lately)
    playlist = library.save_playlist(
        Playlist(name="Ulubione", rules=PlaylistRules(favorites_only=True))
    )
    settings = player.settings
    settings.playlist_id = playlist.id
    player.save_settings(settings)
    line = [i.id for i in player.upcoming(8)]
    library.update(works[4].id, favorite=True)
    return line, works[4]


def test_teraz_does_not_wait_for_the_lists_the_start_is_making(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, player = service.library, service.player
    line, new = _playing_hearts(service)
    # The server has just started: its thread is at the search index.
    library.made_after_start = True
    looked: list[list[str]] = []
    look = threading.Thread(target=lambda: looked.append([i.id for i in player.upcoming(8)]))
    with library._search_lock:
        monkeypatch.setattr(library, "_search", None)
        assert library.search_coming() and not library.lists_made()
        look.start()
        look.join(5)
        # The line of before the restart, at once.
        assert looked == [line]
    library.make_lists()
    assert not library.search_coming() and library.lists_made()
    assert player.upcoming(8)[0].id == new.id  # caught up at the next look


def test_a_look_at_the_line_waits_for_the_index_as_before_when_no_start_makes_it(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, player = service.library, service.player
    _, new = _playing_hearts(service)
    looked: list[str] = []
    look = threading.Thread(target=lambda: looked.append(player.upcoming(8)[0].id))
    with library._search_lock:
        monkeypatch.setattr(library, "_search", None)
        look.start()
        look.join(0.3)
        assert look.is_alive() and not looked
    look.join(10)
    assert looked == [new.id]


async def test_the_loop_does_not_wait_for_the_lists_before_the_line_is_looked_at(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, player = service.library, service.player
    _playing_hearts(service)
    made: list[bool] = []

    def upcoming(limit: int = 8) -> list[Item]:
        made.append(library.lists_made())
        return []

    def pop_next(*_: Any) -> None:
        made.append(library.lists_made())

    monkeypatch.setattr(player, "upcoming", upcoming)
    monkeypatch.setattr(player, "_pop_next", pop_next)
    for look in (player.render_ahead, player.prefetch, player.next):
        made.clear()
        library._search_lock.acquire()  # another thread is making it
        try:
            monkeypatch.setattr(library, "_search", None)
            looking = asyncio.create_task(look())
            await asyncio.sleep(0.2)  # the loop goes on: the app is answered
            assert not looking.done() and not made
        finally:
            library._search_lock.release()
        await asyncio.wait_for(looking, 10)
        assert made and all(made)  # looked at with the lists there


async def test_a_stream_left_before_its_first_line_is_no_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(Settings(data_dir=tmp_path, seed_library=False, scheduler=False))
    svc: FrameService = app.state.service
    svc.library.upsert(_work("met:1", title="Rain", artist="Jan Deszcz"))
    left = threading.Event()
    # The sources take their time; the app has gone on to another work.
    monkeypatch.setattr(svc.copies, "look", lambda item, emit, gone: left.wait(10))
    monkeypatch.setattr(night, "_answering", 0)
    asked = [{"type": "http.request", "body": b"", "more_body": False}]
    sent: list[dict[str, Any]] = []
    before_it_left: list[int] = []

    async def receive() -> dict[str, Any]:
        if asked:
            return asked.pop()
        await asyncio.sleep(0.2)
        before_it_left[:] = [m["status"] for m in sent if m["type"] == "http.response.start"]
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    path = "/api/library/items/met:1/copies"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},  # as uvicorn's
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"accept-encoding", b"gzip")],  # as the app asks
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8099),
    }
    try:
        # Not Starlette's "No response returned." (13 tracebacks in the
        # log in two minutes of browsing, 2026-11-14).
        await asyncio.wait_for(app(scope, receive, send), 10)
    finally:
        left.set()
    # The stream's head went out at once, not held for a body to pack.
    assert before_it_left == [200]
    assert night._answering == 0


async def test_an_answer_that_ended_before_its_body_still_has_its_head() -> None:
    from frame_server.web.compress import Compressed

    head = {
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"application/json")],
    }

    async def cut_short(scope: dict[str, Any], receive: Any, send: Any) -> None:
        await send(head)

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/themes",
        "headers": [(b"accept-encoding", b"gzip")],
    }
    await Compressed(cut_short)(scope, None, send)
    assert sent == [head]
