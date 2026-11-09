"""Works fetched from the museums for a smart playlist come last in it
(Mateusz 2026-11-09: "dzieła (dociągane) z muzeów dawaj na koniec playlist")."""

from __future__ import annotations

from frame_server.library import Item, Library, PlaylistRules
from frame_server.library.models import Playlist, PlaylistKind


def _item(n: int, artist: str, added_at: str) -> Item:
    return Item(
        id=f"aic:{n}",
        source="aic",
        source_id=str(n),
        title=f"Work {n}",
        artist=artist,
        added_at=added_at,
    )


def test_works_fetched_for_a_playlist_come_after_the_others(tmp_path) -> None:
    library = Library(tmp_path / "lib.db")
    library.upsert(_item(1, "Vincent van Gogh", "2026-11-01T10:00:00+00:00"))
    library.upsert(_item(2, "Vincent van Gogh", "2026-11-02T10:00:00+00:00"))
    playlist = library.save_playlist(
        Playlist(
            name="Van Gogh",
            kind=PlaylistKind.SMART,
            rules=PlaylistRules(artists=["Vincent van Gogh"]),
            created_at="2026-11-09T14:00:00+00:00",
        )
    )
    # Kept by the editor's search just before saving, then fetched after.
    library.upsert(_item(3, "Vincent van Gogh", "2026-11-09T13:40:00+00:00"))
    library.upsert(_item(4, "Vincent van Gogh", "2026-11-09T14:01:00+00:00"))
    ids = [i.id for i in library.playlist_items(playlist, sort="recent")]
    assert ids == ["aic:2", "aic:1", "aic:4", "aic:3"]


def test_a_playlist_without_its_date_keeps_its_order(tmp_path) -> None:
    library = Library(tmp_path / "lib.db")
    library.upsert(_item(1, "Vincent van Gogh", "2026-11-01T10:00:00+00:00"))
    library.upsert(_item(2, "Vincent van Gogh", "2026-11-09T14:01:00+00:00"))
    playlist = library.save_playlist(
        Playlist(
            name="Van Gogh",
            kind=PlaylistKind.SMART,
            rules=PlaylistRules(artists=["Vincent van Gogh"]),
        )
    )
    playlist = playlist.model_copy(update={"created_at": ""})
    ids = [i.id for i in library.playlist_items(playlist, sort="recent")]
    assert ids == ["aic:2", "aic:1"]
