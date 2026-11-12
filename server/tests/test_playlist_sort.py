"""The order of a playlist's works, chosen in the app and kept with the
playlist: the app's grid and the frame (when it does not shuffle) follow it
(Mateusz 2026-11-12: "Do playlist dodaj opcję ich sortowania")."""

from __future__ import annotations

from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.library import Item, ItemKind, Library, PlaylistRules
from frame_server.library.models import Playlist, PlaylistKind, PlaylistSort, SharperCopy
from frame_server.library.repo import ordered


def _item(
    n: int,
    artist: str = "Giorgio de Chirico",
    year: int | None = None,
    added_at: str = "",
    size: tuple[int, int] | None = None,
    source: str = "wikiart",
) -> Item:
    width, height = size or (None, None)
    return Item(
        id=f"{source}:{n}",
        source=source,
        source_id=str(n),
        title=f"Work {n}",
        artist=artist,
        year=year,
        added_at=added_at,
        width=width,
        height=height,
    )


def _ids(items: list[Item]) -> list[str]:
    return [i.id.split(":")[1] for i in items]


def test_by_artist_then_year_with_the_nameless_last() -> None:
    items = [
        _item(1, "Monet", 1880),
        _item(2, "", 1700),
        _item(3, "Chirico", 1920),
        _item(4, "Monet", 1870),
        _item(5, "Chirico", None),
    ]
    assert _ids(ordered(items, PlaylistSort(key="artist"))) == ["3", "5", "4", "1", "2"]
    # Z to A, each one's works still the oldest first.
    back = ordered(items, PlaylistSort(key="artist", reverse=True))
    assert _ids(back) == ["4", "1", "3", "5", "2"]


def test_by_year_with_the_undated_last_either_way() -> None:
    items = [_item(1, year=1914), _item(2), _item(3, year=1888), _item(4, year=1914)]
    assert _ids(ordered(items, PlaylistSort(key="year"))) == ["3", "1", "4", "2"]
    assert _ids(ordered(items, PlaylistSort(key="year", reverse=True))) == ["1", "4", "3", "2"]


def test_by_when_added_the_latest_first() -> None:
    items = [
        _item(1, added_at="2026-11-01T10:00:00+00:00"),
        _item(2, added_at="2026-11-03T10:00:00+00:00"),
        _item(3, added_at="2026-11-02T10:00:00+00:00"),
    ]
    assert _ids(ordered(items, PlaylistSort(key="added"))) == ["2", "3", "1"]
    assert _ids(ordered(items, PlaylistSort(key="added", reverse=True))) == ["1", "3", "2"]
    # A manual playlist's own order of adding, whatever the library's dates.
    added = ["wikiart:2", "wikiart:1", "wikiart:3"]
    assert _ids(ordered(items, PlaylistSort(key="added"), added=added)) == ["3", "1", "2"]


def test_by_format_portrait_first() -> None:
    items = [
        _item(1, size=(1600, 900)),
        _item(2, size=(900, 1600)),
        _item(3),
        _item(4, size=(1000, 1000)),
    ]
    assert _ids(ordered(items, PlaylistSort(key="format"))) == ["2", "4", "1", "3"]
    assert _ids(ordered(items, PlaylistSort(key="format", reverse=True))) == ["1", "4", "2", "3"]


def test_by_quality_the_largest_picture_first_and_the_unknown_last() -> None:
    sharper = SharperCopy(
        url="https://x/y.jpg", item_id="wmc:9", source="wmc", width=4000, height=3000
    )
    items = [
        _item(1, size=(600, 450)),
        _item(2, size=(2400, 3000)),
        # The Met says only its thumbnail's size: not known.
        _item(3, size=(400, 300), source="met"),
        _item(4, size=(600, 450)).model_copy(update={"sharper": sharper}),
    ]
    assert _ids(ordered(items, PlaylistSort(key="quality"))) == ["4", "2", "1", "3"]
    # The lowest first: the ones worth a better copy.
    assert _ids(ordered(items, PlaylistSort(key="quality", reverse=True))) == ["1", "2", "4", "3"]
    # A downloaded original's size counts once known.
    side = {"met:3": 5000}
    by_cache = ordered(items, PlaylistSort(key="quality"), lambda i: side.get(i.id) or None)
    assert _ids(by_cache)[0] == "3"


def test_equals_are_settled_by_title_then_id() -> None:
    items = [_item(n, year=1920) for n in (3, 1, 2)]
    assert _ids(ordered(items, PlaylistSort(key="year"))) == ["1", "2", "3"]
    assert _ids(ordered(items, PlaylistSort(key="year", reverse=True))) == ["1", "2", "3"]


def test_a_smart_playlist_is_by_artist_until_its_owner_chooses(tmp_path) -> None:
    library = Library(tmp_path / "lib.db")
    library.upsert(_item(1, "B", 1900, "2026-11-01T10:00:00+00:00"))
    library.upsert(_item(2, "A", 1950, "2026-11-01T11:00:00+00:00"))
    library.upsert(_item(3, "A", 1910, "2026-11-10T10:00:00+00:00"))  # fetched for it
    playlist = library.save_playlist(
        Playlist(
            name="Wszystko",
            kind=PlaylistKind.SMART,
            rules=PlaylistRules(artists=["A", "B"]),
            created_at="2026-11-09T14:00:00+00:00",
        )
    )
    # The default: by artist, the works fetched for it last.
    assert _ids(library.playlist_items(playlist)) == ["2", "1", "3"]
    assert library.playlist_summary(playlist).sort == PlaylistSort(key="artist")
    # A chosen order is the whole order, fetched works among the others.
    chosen = library.save_playlist(playlist.model_copy(update={"sort": PlaylistSort(key="year")}))
    assert _ids(library.playlist_items(chosen)) == ["1", "3", "2"]
    assert library.playlist_summary(chosen).sort == PlaylistSort(key="year")


def test_a_manual_playlist_keeps_its_order_of_adding_until_sorted(tmp_path) -> None:
    library = Library(tmp_path / "lib.db")
    for n, year in ((1, 1900), (2, 1800), (3, 1850)):
        library.upsert(_item(n, year=year))
    playlist = library.save_playlist(
        Playlist(
            name="Moje", kind=PlaylistKind.MANUAL, item_ids=["wikiart:3", "wikiart:1", "wikiart:2"]
        )
    )
    assert _ids(library.playlist_items(playlist)) == ["3", "1", "2"]
    assert library.playlist_summary(playlist).sort == PlaylistSort(key="added", reverse=True)
    latest = playlist.model_copy(update={"sort": PlaylistSort(key="added")})
    assert _ids(library.playlist_items(latest)) == ["2", "1", "3"]
    by_year = playlist.model_copy(update={"sort": PlaylistSort(key="year")})
    assert _ids(library.playlist_items(by_year)) == ["2", "3", "1"]


def test_the_app_sets_the_order_and_the_frame_follows(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    ids = []
    for n, year in ((1, 1930), (2, 1910), (3, 1920)):
        added = svc.importer.add_upload(
            jpeg_bytes((40 * n, 40, 200)), kind=ItemKind.OWN, title=f"Work {n}", artist="Chirico"
        )
        svc.library.update(added.id, year=year)
        ids.append(added.id)
    first, second, third = ids

    with TestClient(app) as client:
        made = client.post(
            "/api/playlists", json={"name": "Chirico", "rules": {"artists": ["Chirico"]}}
        ).json()
        playlist_id = made["playlist"]["id"]
        assert made["playlist"]["sort"] == {"key": "artist", "reverse": False}
        assert client.post(f"/api/playlists/{playlist_id}/play").status_code == 202

        detail = client.put(
            f"/api/playlists/{playlist_id}/sort", json={"key": "year", "reverse": True}
        ).json()
        assert detail["playlist"]["sort"] == {"key": "year", "reverse": True}
        assert [i["id"] for i in detail["items"]] == [first, third, second]
        # The frame's next ones in that order (when it does not shuffle).
        assert [i.id for i in svc.player.candidates()] == [first, third, second]
        assert svc.player.state.queue == []  # drawn again

        # The editor sends the playlist without its order: the order stays.
        edited = client.put(
            f"/api/playlists/{playlist_id}",
            json={"name": "De Chirico", "rules": {"artists": ["Chirico"]}},
        ).json()
        assert edited["playlist"]["sort"] == {"key": "year", "reverse": True}

        # Back to the default.
        back = client.put(f"/api/playlists/{playlist_id}/sort", json=None).json()
        assert back["playlist"]["sort"] == {"key": "artist", "reverse": False}
