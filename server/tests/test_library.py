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
    ArtInstituteChicago,
    ClevelandMuseum,
    MetropolitanMuseum,
    WikimediaCommons,
)


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
