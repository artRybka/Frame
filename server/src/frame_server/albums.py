"""Album playlists: each mirrors one shared iCloud album.

A sync brings new photos in with a thumbnail, takes the ones gone from the
album out of the playlist, and deletes photos no playlist holds any more.
Originals are downloaded when they are about to be shown (see
``icloud.fetch_original``) and trimmed like museum originals.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from .library import AlbumOrder, AlbumSource, AlbumSync, Job, Playlist, PlaylistKind
from .library.icloud import check_album, fetch_original, sync_album

if TYPE_CHECKING:
    from .service import FrameService

log = logging.getLogger(__name__)

#: Older settings: the one album and the last sync of it.
LEGACY_SYNC_KEY = "album_sync"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Albums:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self.library = service.library
        service.images.fetchers["icloud"] = lambda item: fetch_original(service.importer, item)

    def playlists(self) -> list[Playlist]:
        return [p for p in self.library.playlists() if p.kind == PlaylistKind.ALBUM and p.album]

    def check(self, url: str) -> tuple[str, int]:
        """The album's name and number of photos; raises on a bad link."""
        with self.service.importer.http() as http:
            return check_album(http, url)

    def start_sync(self, playlist_id: int) -> Job:
        """Sync one album playlist in the background (one sync per playlist)."""
        description = f"album:{playlist_id}"
        for job in self.service.importer.jobs.values():
            if job.description == description and not job.finished:
                return job

        def work(job: Job) -> None:
            self.sync(playlist_id, job)

        return self.service.importer.start_job(description, work)

    def sync_all(self) -> list[Job]:
        return [self.start_sync(p.id) for p in self.playlists() if p.id is not None]

    def sync(self, playlist_id: int, job: Job | None = None) -> AlbumSync | None:
        playlist = self.library.playlist(playlist_id)
        if playlist is None or playlist.album is None:
            return None
        try:
            listing = sync_album(self.service.importer, playlist.album.url, job)
        except (httpx.HTTPError, ValueError, KeyError) as err:
            log.warning("album %s: sync failed: %s", playlist.name, err)
            old = self.library.album_sync(playlist_id)
            sync = (old or AlbumSync(at=_now())).model_copy(update={"error": str(err)})
            self.library.set_album_sync(playlist_id, sync)
            if job is not None:
                job.error = str(err)
            return sync
        # Saved again from the latest copy: the owner may have edited it meanwhile.
        current = self.library.playlist(playlist_id)
        if current is None:
            self.forget_orphans()
            return None
        changed = current.item_ids != listing.item_ids
        if changed:
            self.library.save_playlist(current.model_copy(update={"item_ids": listing.item_ids}))
        sync = AlbumSync(
            at=_now(), name=listing.name, count=len(listing.item_ids), added=len(listing.added)
        )
        self.library.set_album_sync(playlist_id, sync)
        self.forget_orphans()
        if changed:
            self.service.player.playlist_changed(playlist_id)
        return sync

    def forget_orphans(self) -> int:
        """Delete album photos that no playlist holds any more."""
        held = {i for p in self.library.playlists() for i in p.item_ids}
        state = self.service.player.state
        held |= {state.current_item_id or "", *state.current_group}
        gone = 0
        for item in self.library.query(include_excluded=True)[1]:
            if item.source == "icloud" and item.id not in held:
                self.library.delete(item.id)
                self.service.images.remove(item)
                gone += 1
        return gone

    def deleted(self, playlist_id: int) -> None:
        """An album playlist went: so do its sync record and its photos."""
        self.library.set_album_sync(playlist_id, None)
        self.forget_orphans()

    def migrate(self) -> Playlist | None:
        """Older settings had one album as a mode of the frame: it becomes an
        album playlist with the photos already synced, played if the album
        was. Runs once; returns the new playlist."""
        from .player import SETTINGS_KEY
        from .schedule import FrameSettings

        raw = self.library.get_state(SETTINGS_KEY, {})
        if not isinstance(raw, dict) or not ({"album_url", "mode"} & raw.keys()):
            return None
        url = str(raw.get("album_url") or "").strip()
        mirrored = [p for p in self.playlists() if p.album and p.album.url == url]
        playlist = mirrored[0] if url and mirrored else None
        if url and playlist is None:
            legacy = self.library.get_state(LEGACY_SYNC_KEY) or {}
            photos = [
                i.id for i in self.library.query(include_excluded=True)[1] if i.source == "icloud"
            ]
            order = AlbumOrder.RANDOM if raw.get("shuffle", True) else AlbumOrder.NEWEST
            playlist = self.library.save_playlist(
                Playlist(
                    name=legacy.get("name") or "Album iCloud",
                    kind=PlaylistKind.ALBUM,
                    album=AlbumSource(url=url, order=order),
                    item_ids=photos,
                )
            )
            if legacy.get("at"):
                assert playlist.id is not None
                self.library.set_album_sync(
                    playlist.id,
                    AlbumSync(at=legacy["at"], name=legacy.get("name", ""), count=len(photos)),
                )
            log.info("album %s is now a playlist (%d photos)", playlist.name, len(photos))
        settings = FrameSettings.model_validate(raw)
        if raw.get("mode") == "album":
            settings.playlist_id = playlist.id if playlist else None
        # Saved without the old keys, so this runs once.
        self.library.set_state(SETTINGS_KEY, settings.model_dump(mode="json"))
        return playlist
