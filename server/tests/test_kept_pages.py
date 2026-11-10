"""Records of single works and pages of searches kept on disk (Mateusz
2026-11-07: fewer requests, results served faster, never fewer or worse)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import httpx
import pytest
from test_library import RIJKS_OBJECT
from test_more_museums import _manifest

from frame_server.library import Library
from frame_server.library import pages as pages_module
from frame_server.library.importer import Importer
from frame_server.library.models import Item, ItemKind
from frame_server.library.museums import Access, Rijksmuseum
from frame_server.library.pages import SearchPages, search_pages
from frame_server.library.records import Records, records
from frame_server.library.yale import YaleMuseums


def _rijks(sent: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        if str(request.url).startswith(Rijksmuseum.api):
            items = [{"id": "https://id.rijksmuseum.nl/200108369"}]
            return httpx.Response(200, json={"partOf": {"totalItems": 1}, "orderedItems": items})
        if str(request.url) == "https://id.rijksmuseum.nl/200108369":
            return httpx.Response(200, json=RIJKS_OBJECT)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_rijksmuseum_is_asked_for_each_record_once(tmp_path: Path) -> None:
    sent: list[str] = []
    access = Access(data_dir=tmp_path)
    with _rijks(sent) as http:
        first = Rijksmuseum(http, access=access).search("Milkmaid")
        again = Rijksmuseum(http, access=access).search("Milkmaid")
        assert Rijksmuseum(http, access=access).fetch("1") is None
        assert Rijksmuseum(http, access=access).fetch("1") is None
    assert first == again and first[1][0].title == "The Milkmaid"
    records_asked = [u for u in sent if u.startswith("https://id.")]
    assert records_asked == ["https://id.rijksmuseum.nl/200108369", "https://id.rijksmuseum.nl/1"]
    # Kept whole and compressed: a new mapping applies to it at once.
    assert records(tmp_path).get("rijks", "200108369")[1]["id"] == RIJKS_OBJECT.get("id")


def test_yale_asks_each_record_and_manifest_once(tmp_path: Path) -> None:
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        sent.append(url)
        if "/api/search/" in url:
            items = [{"id": "https://lux.collections.yale.edu/data/object/a"}]
            return httpx.Response(200, json={"partOf": [{"totalItems": 1}], "orderedItems": items})
        if "/data/object/a" in url:
            return httpx.Response(
                200, text='{"x": "https://manifests.collections.yale.edu/yuag/obj/25955"}'
            )
        return httpx.Response(200, json=_manifest("Public domain"))

    access = Access(data_dir=tmp_path)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        first = YaleMuseums(http, access=access).search("Monet", limit=1)
        again = YaleMuseums(http, access=access).search("Monet", limit=1)
    assert first == again and [i.id for i in first[1]] == ["yale:yuag-25955"]
    assert sum("/data/object/a" in u for u in sent) == 1
    assert sum("/yuag/obj/25955" in u for u in sent) == 1
    assert sum("/api/search/" in u for u in sent) == 2  # the search itself, every time


def test_records_expire_and_the_gone_are_remembered(tmp_path: Path) -> None:
    store = Records(tmp_path / "r.sqlite")
    store.put("rijks", "1", {"a": "ü"}, now=1000.0)
    store.put("rijks", "2", None, now=1000.0)
    assert store.get("rijks", "1", now=1000.0 + 86400) == (True, {"a": "ü"})
    assert store.get("rijks", "2", now=1000.0) == (True, None)
    assert store.get("rijks", "1", days=1, now=1000.0 + 2 * 86400) == (False, None)
    assert store.get("yale", "1") == (False, None)


def _work(n: int) -> Item:
    return Item(
        id=f"aic:{n}",
        kind=ItemKind.ARTWORK,
        source="aic",
        source_id=str(n),
        title=f"Work {n}",
        artist="Someone",
        year=1880 + n,
        image_url=f"https://example.org/{n}.jpg",
        thumb_url=f"https://example.org/{n}t.jpg",
    )


def test_pages_come_back_whole_fresh_then_stale_then_gone(tmp_path: Path) -> None:
    store = SearchPages(tmp_path / "p.sqlite", "2")
    key = store.key("aic", "monet", 24, 1, "any", False)
    store.put(key, 120, [_work(1), _work(2)], now=1000.0)
    fresh, total, items = store.get(key, now=1000.0 + 60) or (False, 0, [])
    assert fresh and total == 120 and items == [_work(1), _work(2)]
    assert store.get(key, now=1000.0 + pages_module.FRESH + 1) == (False, 120, items)
    assert store.get(key, now=1000.0 + pages_module.STALE + 1) is None
    # Another way of keeping pages: shown, but asked for again.
    newer = SearchPages(tmp_path / "p.sqlite", "3")
    assert newer.get(key, now=1000.0 + 60) == (False, 120, items)


def test_a_release_keeps_pages_fresh_unless_their_museum_reads_anew(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eight releases a day asked every set opened again (2026-11-07)."""
    store = SearchPages(tmp_path / "p.sqlite", "2")
    aic = store.key("aic", "monet", 24, 1, "any", False)
    met = store.key("met", "monet", 24, 1, "any", False)
    store.put(aic, 1, [_work(1)], now=1000.0)
    store.put(met, 1, [_work(2)], now=1000.0)
    again = SearchPages(tmp_path / "p.sqlite", "2")  # the next release
    assert again.get(aic, now=1060.0) == (True, 1, [_work(1)])
    monkeypatch.setitem(pages_module.READINGS, "met", "2")
    assert again.get(met, now=1060.0) == (False, 1, [_work(2)])
    assert again.get(aic, now=1060.0) == (True, 1, [_work(1)])


def test_pages_of_one_kind_and_aic_read_anew(tmp_path: Path) -> None:
    """Malarstwo with Monet asked AIC for every work of his and the others
    by any field (his caricatures, Mateusz 2026-11-10): those pages are
    asked again; the others stay fresh."""
    store = SearchPages(tmp_path / "p.sqlite", "2")
    for key in (
        store.key("aic", "monet", 24, 1, "any", False),
        store.key("met", "@by:Claude Monet\t", 24, 1, "painting", False),
        store.key("met", "monet", 24, 1, "any", False),
    ):
        store.put(key, 1, [_work(1)], now=1000.0)
    with store._lock:
        store._db.execute("UPDATE pages SET version = '2/1'")
    fresh = [store.get(k, now=1060.0) for (k,) in store._db.execute("SELECT key FROM pages")]
    assert sorted(f[0] for f in fresh if f) == [False, False, True]


def test_the_oldest_pages_go_first_when_the_room_is_full(tmp_path: Path) -> None:
    store = SearchPages(tmp_path / "p.sqlite")
    for n in range(5):
        store.put(store.key("aic", str(n)), 1, [_work(n)], now=1000.0 + n)
    one = store._db.execute("SELECT MAX(size) FROM pages").fetchone()[0]
    assert store.trim(room=2 * one) == 3
    assert store.get(store.key("aic", "0"), now=1000.0) is None
    assert store.get(store.key("aic", "4"), now=1000.0) is not None


class Counting:
    """A source of one page that counts how often it was asked."""

    def __init__(self) -> None:
        self.asked = 0
        self.answered = threading.Event()

    def search(self, query: str, limit: int = 24, page: int = 1) -> tuple[int, list[Item]]:
        self.asked += 1
        self.answered.set()
        return 7, [_work(self.asked)]


def _importer(tmp_path: Path, source: Counting, monkeypatch: pytest.MonkeyPatch) -> Importer:
    import frame_server.library.importer as importer_module

    monkeypatch.setattr(importer_module, "museum", lambda key, http, access: source)
    importer = Importer(
        Library(tmp_path / "lib.db"),
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        access=lambda: Access(data_dir=tmp_path),
    )
    monkeypatch.setattr(importer, "without_grey", lambda items: items)
    return importer


def test_a_page_outlives_a_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = Counting()
    first = _importer(tmp_path, source, monkeypatch).search("aic", "monet")
    assert source.asked == 1
    # A new process (an update of the server): the page from disk, not asked.
    again = _importer(tmp_path, source, monkeypatch).search("aic", "monet")
    assert again == first and source.asked == 1
    # With private use the licences differ: another page.
    importer = _importer(tmp_path, source, monkeypatch)
    importer._access = lambda: Access(private_use=True, data_dir=tmp_path)
    importer.search("aic", "monet")
    assert source.asked == 2


def test_an_old_page_is_shown_and_asked_again_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Counting()
    _importer(tmp_path, source, monkeypatch).search("aic", "monet")
    store = search_pages(tmp_path)
    store._db.execute("UPDATE pages SET at = ?", (time.time() - pages_module.FRESH - 60,))
    source.answered.clear()
    importer = _importer(tmp_path, source, monkeypatch)
    shown = importer.search("aic", "monet")
    assert shown[1][0].id == "aic:1"  # at once, the old page
    assert source.answered.wait(5)  # and the museum asked behind
    deadline = time.time() + 5
    while time.time() < deadline and importer._asking:
        time.sleep(0.01)
    assert importer.search("aic", "monet")[1][0].id == "aic:2"  # the new one next
    assert source.asked == 2
