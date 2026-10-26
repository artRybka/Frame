from __future__ import annotations

import json

import httpx
import numpy as np
from conftest import jpeg_bytes
from PIL import Image

from frame_server.imaging.color import linear_to_oklab, u8_to_linear
from frame_server.library import Item, ItemKind, Library, Playlist, PlaylistKind, PlaylistRules
from frame_server.library.colors import analyse, family
from frame_server.library.museums import (
    MUSEUMS,
    ArtInstituteChicago,
    ClevelandMuseum,
    Discovery,
    MetropolitanMuseum,
    Museum,
    Rijksmuseum,
    WikimediaCommons,
)
from frame_server.library.seed import PACKS, SEED_QUERIES


def _item(n: int, **kw) -> Item:
    kw.setdefault("title", f"Picture {n}")
    return Item(id=f"test:{n}", source="test", source_id=str(n), **kw)


def test_query_filters_and_facets(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(
        _item(1, artist="Claude Monet", styles=["Impressionism"], color_tags=["blue"], year=1899)
    )
    lib.upsert(_item(2, artist="Katsushika Hokusai", medium="Color woodblock print", year=1831))
    lib.upsert(_item(3, artist="Claude Monet", color_tags=["warm"], year=1891, favorite=True))
    lib.upsert(_item(4, artist="Someone", excluded=True))

    assert lib.query()[0] == 3
    assert {i.id for i in lib.query(PlaylistRules(artists=["claude monet"]))[1]} == {
        "test:1",
        "test:3",
    }
    assert [i.id for i in lib.query(PlaylistRules(query="woodblock"))[1]] == ["test:2"]
    assert [i.id for i in lib.query(PlaylistRules(colors=["blue"]))[1]] == ["test:1"]
    assert [i.id for i in lib.query(PlaylistRules(year_from=1890, year_to=1895))[1]] == ["test:3"]
    assert [i.id for i in lib.query(PlaylistRules(favorites_only=True))[1]] == ["test:3"]
    assert [i.id for i in lib.query(sort="year")[1]] == ["test:2", "test:3", "test:1"]

    facets = lib.facets()
    assert facets.artists[0].value == "Claude Monet" and facets.artists[0].count == 2
    assert all(f.value != "Someone" for f in facets.artists)


def test_upsert_keeps_user_state(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(_item(1))
    lib.update("test:1", favorite=True)
    lib.upsert(_item(1, title="Renamed"))
    reloaded = Library(tmp_path / "lib.db").get("test:1")
    assert reloaded is not None and reloaded.favorite and reloaded.title == "Renamed"


def test_batch_is_one_transaction(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    with lib.batch():
        for n in range(3):
            lib.upsert(_item(n))
        # Not committed yet: another connection does not see the writes.
        assert Library(tmp_path / "lib.db").count() == 0
    assert Library(tmp_path / "lib.db").count() == 3

    try:
        with lib.batch():
            lib.delete("test:0")
            lib.update("test:1", favorite=True)
            raise RuntimeError("halfway")
    except RuntimeError:
        pass
    # Rolled back on disk and in the cached copy alike.
    assert lib.count() == 3 and not lib.get("test:1").favorite  # type: ignore[union-attr]


def test_playlists_and_state(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in range(5):
        lib.upsert(_item(n, artist="A" if n % 2 else "B"))
    smart = lib.save_playlist(Playlist(name="A only", rules=PlaylistRules(artists=["A"])))
    manual = lib.save_playlist(
        Playlist(name="Picks", kind=PlaylistKind.MANUAL, item_ids=["test:4", "test:0", "gone"])
    )
    assert smart.id is not None and manual.id is not None
    assert {i.id for i in lib.playlist_items(smart)} == {"test:1", "test:3"}
    assert [i.id for i in lib.playlist_items(manual)] == ["test:4", "test:0"]
    assert lib.playlist_summary(manual).item_count == 2
    assert [p.name for p in lib.playlists()] == ["A only", "Picks"]
    assert lib.delete_playlist(smart.id) and lib.playlist(smart.id) is None

    lib.set_state("k", {"a": 1})
    assert lib.get_state("k") == {"a": 1}
    lib.record_shown("test:1", "test")
    assert lib.history()[0]["item_id"] == "test:1"
    assert lib.get("test:1").show_count == 1  # type: ignore[union-attr]


def _lab(rgb: tuple[int, int, int]) -> np.ndarray:
    return linear_to_oklab(u8_to_linear(np.array(rgb, dtype=np.uint8)))


def test_colour_families() -> None:
    assert family(_lab((30, 60, 200))) == "blue"
    assert family(_lab((200, 30, 30))) == "red"
    assert family(_lab((240, 200, 40))) == "yellow"
    assert family(_lab((40, 140, 60))) == "green"
    assert family(_lab((120, 80, 50))) == "brown"
    assert family(_lab((235, 230, 215))) == "white"  # aged paper is not "yellow"
    assert family(_lab((15, 15, 18))) == "black"


def test_analyse_blue_picture() -> None:
    import io

    img = Image.open(io.BytesIO(jpeg_bytes((40, 80, 200))))
    swatches, tags, score = analyse(img)
    assert "blue" in tags and "cool" in tags
    assert swatches[0].hex.startswith("#") and 0 <= score <= 1


def _client(routes: dict[str, dict], sent: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if sent is not None:
            sent.append(request)
        for prefix, body in routes.items():
            if str(request.url).startswith(prefix):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_aic_mapping() -> None:
    body = {
        "pagination": {"total": 1},
        "data": [
            {
                "id": 24645,
                "title": "Under the Wave off Kanagawa",
                "artist_title": "Katsushika Hokusai",
                "artist_display": "Katsushika Hokusai\nJapanese, 1760-1849",
                "date_display": "1830/33",
                "date_start": 1830,
                "medium_display": "Color woodblock print; oban",
                "artwork_type_title": "Print",
                "style_titles": ["Japanese (culture or style)"],
                "subject_titles": ["waves", "Mount Fuji"],
                "place_of_origin": "Japan",
                "description": "<p>Famous &amp; blue.</p>",
                "image_id": "abc",
                "thumbnail": {"width": 6679, "height": 4577},
                "is_public_domain": True,
            },
            {"id": 2, "title": "No image", "is_public_domain": True, "image_id": None},
        ],
    }
    sent: list[httpx.Request] = []
    with _client({"https://api.artic.edu/api/v1/artworks/search": body}, sent) as http:
        total, items = ArtInstituteChicago(http).search("hokusai")
    assert total == 1 and len(items) == 1
    # AIC's bare ``q`` matches everything; the query must also restrict.
    query = json.loads(sent[0].content)["query"]["bool"]
    assert query["must"][0]["simple_query_string"]["query"] == "hokusai"
    assert query["filter"] == [{"term": {"is_public_domain": True}}]
    item = items[0]
    assert item.id == "aic:24645" and item.artist_bio == "Japanese, 1760-1849"
    assert item.description == "Famous & blue." and item.subjects == ["waves", "Mount Fuji"]
    assert item.thumb_url.endswith("/abc/full/600,/0/default.jpg")


def test_cleveland_mapping() -> None:
    record = {
        "id": 111654,
        "title": "South Wind, Clear Sky",
        "creators": [{"description": "Katsushika Hokusai (Japanese, 1760–1849)"}],
        "creation_date": "early 1830s",
        "creation_date_earliest": 1830,
        "technique": "color woodblock print",
        "type": "Print",
        "culture": ["Japan, Edo period (1615–1868)"],
        "share_license_status": "CC0",
        "url": "https://clevelandart.org/art/1930.189",
        "images": {"web": {"url": "https://cdn/x_web.jpg", "width": "900", "height": "617"}},
    }
    with _client(
        {
            "https://openaccess-api.clevelandart.org/api/artworks/": {
                "info": {"total": 1},
                "data": [record],
            }
        }
    ) as http:
        _, items = ClevelandMuseum(http).search("hokusai")
    item = items[0]
    assert item.artist == "Katsushika Hokusai" and item.artist_bio == "Japanese, 1760–1849"
    assert item.width == 900 and item.image_url == "https://cdn/x_web.jpg"


def test_met_mapping() -> None:
    obj = {
        "objectID": 436535,
        "title": "Wheat Field with Cypresses",
        "artistDisplayName": "Vincent van Gogh",
        "objectDate": "1889",
        "objectBeginDate": 1889,
        "isPublicDomain": True,
        "primaryImage": "https://images/original.jpg",
        "primaryImageSmall": "https://images/small.jpg",
        "tags": [{"term": "Landscapes"}],
    }
    routes = {
        "https://collectionapi.metmuseum.org/public/collection/v1.1/search": {
            "total": 1,
            "objectIDs": [436535],
        },
        "https://collectionapi.metmuseum.org/public/collection/v1/objects/436535": obj,
    }
    with _client(routes) as http:
        _, items = MetropolitanMuseum(http).search("van gogh")
    assert items[0].subjects == ["Landscapes"] and items[0].year == 1889


def test_wikimedia_mapping() -> None:
    page = {
        "pageid": 123,
        "title": "File:Chełmoński Babie lato.jpg",
        "imageinfo": [
            {
                "url": "https://upload/full.jpg",
                "thumburl": "https://upload/600px.jpg",
                "descriptionurl": "https://commons/File",
                "width": 3000,
                "height": 2000,
                "extmetadata": {
                    "ObjectName": {"value": "Babie lato"},
                    "DateTimeOriginal": {"value": "1875"},
                    "LicenseShortName": {"value": "Public domain"},
                },
            }
        ],
    }
    body = {"query": {"pages": {"123": page}}}
    with _client({"https://commons.wikimedia.org/w/api.php": body}) as http:
        _, items = WikimediaCommons(http).search("Category:Paintings by Józef Chełmoński")
    item = items[0]
    assert item.artist == "Józef Chełmoński" and item.title == "Babie lato" and item.year == 1875
    assert item.kind == ItemKind.ARTWORK and item.id == "wmc:123"

    page["imageinfo"][0]["extmetadata"]["LicenseShortName"]["value"] = "CC BY-SA 4.0"
    with _client({"https://commons.wikimedia.org/w/api.php": body}) as http:
        assert WikimediaCommons(http).search("Category:X")[1] == []
        _, items = WikimediaCommons(http, private_use=True).search("Category:X")
    assert items[0].license == "CC BY-SA 4.0"


def test_wikimedia_category_pages_by_token() -> None:
    def file(n: int) -> dict:
        info = {"url": f"https://u/{n}.jpg", "extmetadata": {"LicenseShortName": {"value": "CC0"}}}
        return {"pageid": n, "title": f"File:{n}.jpg", "imageinfo": [info]}

    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        start = int(request.url.params.get("gcmcontinue", "0"))
        size = int(request.url.params["gcmlimit"])
        pages = {str(n): file(n) for n in range(start, min(start + size, 5))}
        body: dict = {"query": {"pages": pages}}
        if start + size < 5:
            body["continue"] = {"gcmcontinue": str(start + size), "continue": "gcmcontinue||"}
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        total, items = WikimediaCommons(http).search("Category:X", limit=2, page=2)
        assert [i.source_id for i in items] == ["2", "3"] and total == 6
        total, items = WikimediaCommons(http).search("Category:X", limit=2, page=3)
        assert [i.source_id for i in items] == ["4"] and total == 5


RIJKS_OBJECT = {
    "id": "https://id.rijksmuseum.nl/200108369",
    "type": "HumanMadeObject",
    "classified_as": [
        {
            "notation": [
                {"@language": "nl", "@value": "schilderij"},
                {"@language": "en", "@value": "painting"},
            ]
        }
    ],
    "identified_by": [
        {"type": "Identifier", "content": "SK-A-2344"},
        {
            "type": "Name",
            "content": "Het melkmeisje",
            "language": [{"id": "http://vocab.getty.edu/aat/300388256"}],
        },
        {"type": "Name", "content": "The Milkmaid", "language": [{"id": Rijksmuseum.english}]},
    ],
    "produced_by": {
        "part": [
            {"carried_out_by": [{"notation": [{"@language": "en", "@value": "Johannes Vermeer"}]}]}
        ],
        "timespan": {
            "begin_of_the_begin": "1660-01-01T00:00:00Z",
            "identified_by": [{"content": "c. 1660", "language": [{"id": Rijksmuseum.english}]}],
        },
    },
    "referred_to_by": [
        {
            "classified_as": [{"id": Rijksmuseum.medium_type}],
            "content": "oil on canvas",
            "language": [{"id": Rijksmuseum.english}],
        },
        {"classified_as": [{"id": Rijksmuseum.description_type}], "content": "Een dienstmaagd."},
    ],
    "subject_of": [
        {
            "digitally_carried_by": [
                {
                    "access_point": [{"id": "https://iiif.micr.io/QkOGy/full/max/0/default.jpg"}],
                    "referred_to_by": [
                        {"content": "https://creativecommons.org/publicdomain/mark/1.0/"}
                    ],
                }
            ]
        },
        {
            "digitally_carried_by": [
                {
                    "format": "text/html",
                    "access_point": [
                        {"id": "https://www.rijksmuseum.nl/nl/collectie/object/SK-A-2344"}
                    ],
                }
            ]
        },
    ],
}


def test_rijksmuseum_mapping_and_fallback_to_title() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(Rijksmuseum.api):
            found = "title" in request.url.params
            items = [{"id": "https://id.rijksmuseum.nl/200108369"}] if found else []
            return httpx.Response(
                200, json={"partOf": {"totalItems": len(items)}, "orderedItems": items}
            )
        if url == "https://id.rijksmuseum.nl/200108369":
            assert request.headers["Accept"] == "application/ld+json"
            return httpx.Response(200, json=RIJKS_OBJECT)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        total, items = Rijksmuseum(http).search("Milkmaid")
    assert total == 1
    item = items[0]
    assert item.id == "rijks:200108369" and item.title == "The Milkmaid"
    assert item.artist == "Johannes Vermeer" and item.year == 1660 and item.date_text == "c. 1660"
    assert item.medium == "oil on canvas" and item.classification == "painting"
    assert item.license == "Public Domain Mark 1.0" and item.description == "Een dienstmaagd."
    assert item.thumb_url == "https://iiif.micr.io/QkOGy/full/600,/0/default.jpg"
    assert item.url.endswith("SK-A-2344")


def test_rijksmuseum_skips_works_without_open_image() -> None:
    closed = {**RIJKS_OBJECT, "subject_of": [RIJKS_OBJECT["subject_of"][1]]}
    assert Rijksmuseum(httpx.Client())._map(closed) is None


def test_search_many_walks_pages(tmp_path) -> None:
    from frame_server.library.importer import Importer

    class Counting(Museum):
        key = "aic"
        name = "Counting"
        page_size = 3

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            start = (page - 1) * limit
            return 7, [self._item(str(n), title="x") for n in range(start, min(start + limit, 7))]

        def fetch(self, source_id: str) -> Item | None:
            return None

    original = MUSEUMS["aic"]
    MUSEUMS["aic"] = Counting
    try:
        importer = Importer(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
        assert len(importer.search_many("aic", "x", 5)) == 5
        assert len(importer.search_many("aic", "x", 50)) == 7
    finally:
        MUSEUMS["aic"] = original


def test_packs_use_known_museums() -> None:
    keys = [p.key for p in PACKS]
    assert len(keys) == len(set(keys))
    for _, queries in [("starter", SEED_QUERIES), *[(p.key, p.queries) for p in PACKS]]:
        for source, query, limit in queries:
            assert source in MUSEUMS and query and 0 < limit <= 500


def test_discovery_year_check() -> None:
    spec = Discovery(year_from=1850, year_to=1900)
    assert spec.fits(_item(1, year=1850)) and not spec.fits(_item(2, year=1901))
    assert not spec.fits(_item(3)) and Discovery().fits(_item(3))
    assert Rijksmuseum(httpx.Client())._decades(Discovery(year_from=1855, year_to=1871)) == [
        1850,
        1860,
        1870,
    ]


def test_draw_takes_turns_and_skips_known_or_weak(tmp_path) -> None:
    import random

    from frame_server.library.importer import Importer, Job

    class Fake(Museum):
        name = "Fake"

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            return 0, []

        def fetch(self, source_id: str) -> Item | None:
            return None

        def discover(self, spec, limit=20, page=1):  # type: ignore[no-untyped-def]
            items = [self._item(str(n), year=1800 + n) for n in range(40)]
            return len(items), items[(page - 1) * limit : page * limit]

    class A(Fake):
        key = "aic"

    class B(Fake):
        key = "cma"

    class Importing(Importer):
        def _analysed(self, item: Item) -> Item:
            # Odd ids look weak on e-paper.
            score = 0.2 if int(item.source_id) % 2 else 0.9
            return item.model_copy(update={"suitability": score})

    saved = dict(MUSEUMS)
    MUSEUMS.update(aic=A, cma=B)
    try:
        library = Library(tmp_path / "lib.db")
        library.upsert(A(httpx.Client())._item("10", year=1810))
        importer = Importing(library, None, None)  # type: ignore[arg-type]
        importer.cache = type("Cache", (), {"remove": lambda self, item: None})()
        job = Job(id="j", description="draw")
        spec = Discovery(year_from=1800, year_to=1830)
        importer.draw(spec, 8, ["aic", "cma"], job, min_suitability=0.5, rng=random.Random(3))
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    assert job.done == 8 and job.skipped > 0 and len(set(job.item_ids)) == 8
    assert "aic:10" not in job.item_ids
    assert {i.split(":")[0] for i in job.item_ids} == {"aic", "cma"}
    for item_id in job.item_ids:
        n = int(item_id.split(":")[1])
        assert n % 2 == 0 and n <= 30


def test_search_all_interleaves_and_reports_failures(tmp_path) -> None:
    from frame_server.library.importer import Importer

    def fake(source: str, count: int, fails: bool = False) -> type[Museum]:
        class Fake(Museum):
            key = source
            name = source

            def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
                if fails:
                    raise httpx.ConnectError("down")
                return count, [self._item(str(n)) for n in range(min(limit, count))]

            def fetch(self, source_id: str) -> Item | None:
                return None

        return Fake

    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(a=fake("a", 3), b=fake("b", 1), c=fake("c", 0, fails=True))
    try:
        importer = Importer(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
        total, items, failed = importer.search_all("x", limit=2)
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    assert total == 4 and failed == ["c"]
    assert [i.id for i in items] == ["a:0", "b:0", "a:1"]


def test_fill_adds_only_what_the_playlist_would_pick(tmp_path) -> None:
    import random

    from frame_server.library.importer import Importer, Job

    class Searching(Museum):
        key = "aic"
        name = "Searching"
        page_size = 3

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            # Results mix the artist's works with works about them.
            items = [
                self._item(str(n), artist=query if n % 3 else "Someone Else", year=1880 + n)
                for n in range(12)
            ]
            return len(items), items[(page - 1) * limit : page * limit]

        def fetch(self, source_id: str) -> Item | None:
            return None

    class Importing(Importer):
        def _analysed(self, item: Item) -> Item:
            tags = ["blue"] if int(item.source_id) % 2 else ["warm"]
            return item.model_copy(update={"color_tags": tags})

    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(aic=Searching)
    try:
        importer = Importing(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
        importer.cache = type("Cache", (), {"remove": lambda self, item: None})()
        job = Job(id="j", description="fill")
        rules = PlaylistRules(artists=["Claude Monet"], colors=["blue"], year_to=1890)
        importer.fill(rules, 10, job, rng=random.Random(1))
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    # Monet (n % 3), blue (odd), up to 1890 (n <= 10): 1, 5, 7.
    assert sorted(job.item_ids) == ["aic:1", "aic:5", "aic:7"]
    assert job.done == 3 and job.skipped == 4  # Monet, until 1890, but not blue: 2, 4, 8, 10


def _gradient(dark: tuple[int, int, int], light: tuple[int, int, int]) -> Image.Image:
    t = np.linspace(0, 1, 200)[None, :, None]
    pixels = (np.array(dark) * (1 - t) + np.array(light) * t) * np.ones((150, 1, 1))
    return Image.fromarray(pixels.astype(np.uint8))


def test_tint_spread_tells_monochrome_from_colour() -> None:
    from frame_server.library.colors import tint_spread
    from frame_server.library.style import MONOCHROME_SPREAD

    grey = _gradient((0, 0, 0), (255, 255, 255))
    sepia = _gradient((40, 25, 10), (235, 215, 180))
    ink_on_old_paper = _gradient((30, 30, 30), (240, 228, 200))
    for img in (grey, sepia, ink_on_old_paper):
        assert tint_spread(img) < MONOCHROME_SPREAD
    red_chalk = _gradient((150, 50, 30), (245, 230, 215))
    cyanotype = _gradient((0, 30, 110), (200, 220, 250))
    sky_and_sand = Image.new("RGB", (200, 150), (70, 120, 200))
    sky_and_sand.paste((220, 170, 90), (0, 75, 200, 150))
    for img in (red_chalk, cyanotype, sky_and_sand):
        assert tint_spread(img) > 2 * MONOCHROME_SPREAD


def test_auto_preset_by_kind_metadata_and_colour() -> None:
    from frame_server.library.style import auto_preset

    def item(kind: ItemKind = ItemKind.ARTWORK, spread: float = 0.05, **meta: str) -> Item:
        return Item(id="t:1", kind=kind, source="t", source_id="1", tint_spread=spread, **meta)

    assert auto_preset(item(classification="Painting", medium="Oil on canvas")) == "painting"
    assert auto_preset(item(classification="Print", medium="Color woodblock print")) == "graphic"
    assert auto_preset(item(classification="prent", medium="houtsnede")) == "graphic"
    assert auto_preset(item(classification="Poster")) == "graphic"
    assert auto_preset(item(medium="engraving, hand-colored")) == "graphic"
    assert auto_preset(item(classification="Photograph")) == "photo"
    assert auto_preset(item(ItemKind.PHOTO)) == "photo"
    assert auto_preset(item(ItemKind.OWN)) == "painting"
    # No colour of its own: black and white, whatever it is.
    assert auto_preset(item(spread=0.004, classification="Print", medium="Etching")) == "bw"
    assert auto_preset(item(ItemKind.PHOTO, spread=0.002)) == "bw"
    # Not measured yet: by kind and metadata only.
    assert auto_preset(item(spread=None, medium="Lithograph")) == "graphic"  # type: ignore[arg-type]
    # "Painting" is not a print, "sketch" is not Dutch "ets".
    assert auto_preset(item(classification="Paintings", medium="Oil sketch")) == "painting"


def _etching(colours: list[tuple[int, int, int]]) -> Image.Image:
    """Hatching in dark ink over bands of ``colours``: an etching on old
    paper with one colour, a coloured print with several."""
    import numpy as np

    rng = np.random.default_rng(1)
    pixels = np.zeros((240, 320, 3), dtype=np.uint8)
    for i, colour in enumerate(colours):
        pixels[:, i * 320 // len(colours) : (i + 1) * 320 // len(colours)] = colour
    ink = (rng.random((240, 320)) < 0.35) | (np.arange(320)[None, :] % 7 == 0)
    pixels[ink] = (45, 35, 30)
    return Image.fromarray(pixels)


def test_colourful_works_score_best_on_epaper() -> None:
    from frame_server.library.colors import score

    etching = score(_etching([(238, 226, 198)]))  # sepia ink on yellowed paper
    grey = score(_etching([(225, 225, 225)]))
    print_ = score(_etching([(220, 60, 50), (40, 90, 200), (240, 200, 40), (60, 160, 70)]))
    # However crisp, pictures without colour of their own score below 0.72;
    # a colourful one makes it.
    assert etching <= 0.5 and grey <= 0.5
    assert print_ >= 0.72
    _, _, analysed = analyse(_etching([(238, 226, 198)]))
    assert analysed == etching
