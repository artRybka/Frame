"""Playlists: smart (rule-based) and manual."""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..library import (
    AlbumSync,
    ItemSummary,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    PlaylistSummary,
)
from ..library.duplicates import Works
from ..library.icloud import album_token
from ..service import FrameService
from .deps import require_token, service

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["playlists"])
Svc = Annotated[FrameService, Depends(service)]


class PlaylistDetail(BaseModel):
    playlist: PlaylistSummary
    item_ids: list[str]
    items: list[ItemSummary]


class RulesPreview(BaseModel):
    count: int
    items: list[ItemSummary]


class ItemIds(BaseModel):
    item_ids: list[str]


class AlbumLink(BaseModel):
    url: str


class AlbumCheck(BaseModel):
    name: str
    count: int


def _playlist(svc: FrameService, playlist_id: int) -> Playlist:
    playlist = svc.library.playlist(playlist_id)
    if playlist is None:
        raise HTTPException(404, f"no playlist {playlist_id}")
    return playlist


#: A smart playlist's detail lists this many works at most (its count is all).
DETAIL_LIMIT = 400


def _checked(playlist: Playlist) -> Playlist:
    """An album playlist needs a shared album's link; its photos come from
    the album, not from the request. A smart playlist needs some rule: with
    none it would be the whole catalogue."""
    if playlist.kind == PlaylistKind.SMART and playlist.rules.is_empty():
        raise HTTPException(422, "a smart playlist needs at least one rule")
    if playlist.kind != PlaylistKind.ALBUM:
        return playlist.model_copy(update={"album": None})
    if playlist.album is None:
        raise HTTPException(422, "an album playlist needs the album's link")
    try:
        album_token(playlist.album.url)
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    return playlist


def _only_favorites(svc: FrameService, playlist: Playlist) -> bool:
    """Whether this is the one "Ulubione" playlist, which always stays."""
    return playlist.is_favorites and not any(
        p.is_favorites for p in svc.library.playlists() if p.id != playlist.id
    )


def _detail(svc: FrameService, playlist: Playlist) -> PlaylistDetail:
    items = svc.library.playlist_items(playlist, sort="artist")
    if playlist.kind == PlaylistKind.SMART:
        items = items[:DETAIL_LIMIT]  # e.g. one made before empty rules were refused
    return PlaylistDetail(
        playlist=svc.library.playlist_summary(playlist),
        item_ids=playlist.item_ids,
        items=[ItemSummary.of(i) for i in items],
    )


@router.get("/playlists", response_model=list[PlaylistSummary])
def list_playlists(svc: Svc) -> list[PlaylistSummary]:
    return [svc.library.playlist_summary(p) for p in svc.library.playlists()]


@router.post("/playlists", response_model=PlaylistDetail)
def create_playlist(playlist: Playlist, svc: Svc) -> PlaylistDetail:
    playlist = _checked(playlist)
    if playlist.kind == PlaylistKind.ALBUM:
        playlist = playlist.model_copy(update={"item_ids": []})
    saved = svc.library.save_playlist(playlist.model_copy(update={"id": None}))
    if saved.kind == PlaylistKind.ALBUM and saved.id is not None:
        svc.albums.start_sync(saved.id)  # thumbnails of its photos, in the background
    return _detail(svc, saved)


@router.post("/albums/check", response_model=AlbumCheck)
def check_album(link: AlbumLink, svc: Svc) -> AlbumCheck:
    """Whether a shared album's link works: its name and number of photos."""
    try:
        album_token(link.url)
        name, count = svc.albums.check(link.url)
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    except httpx.HTTPError as err:
        raise HTTPException(502, f"iCloud: {err}") from err
    return AlbumCheck(name=name, count=count)


@router.post("/playlists/preview", response_model=RulesPreview)
def preview_rules(rules: PlaylistRules, svc: Svc) -> RulesPreview:
    total, items = svc.library.query(rules, sort="suitability", limit=24)
    return RulesPreview(count=total, items=[ItemSummary.of(i) for i in items])


@router.get("/playlists/{playlist_id}", response_model=PlaylistDetail)
def get_playlist(playlist_id: int, svc: Svc) -> PlaylistDetail:
    return _detail(svc, _playlist(svc, playlist_id))


@router.put("/playlists/{playlist_id}", response_model=PlaylistDetail)
def update_playlist(playlist_id: int, playlist: Playlist, svc: Svc) -> PlaylistDetail:
    existing = _playlist(svc, playlist_id)
    playlist = _checked(playlist)
    if _only_favorites(svc, existing):
        # It may be renamed and narrowed, but stays the hearts' playlist.
        rules = playlist.rules.model_copy(update={"favorites_only": True})
        playlist = playlist.model_copy(
            update={"kind": PlaylistKind.SMART, "rules": rules, "album": None}
        )
    update: dict[str, Any] = {"id": playlist_id, "created_at": existing.created_at}
    relinked = False
    if playlist.album is not None:
        # The photos are the album's; another link brings another album's.
        relinked = existing.album is None or existing.album.url != playlist.album.url
        update["item_ids"] = [] if relinked else existing.item_ids
        if playlist.album != existing.album:
            svc.player.playlist_changed(playlist_id)  # e.g. another order
    saved = svc.library.save_playlist(playlist.model_copy(update=update))
    if relinked or (existing.album is not None and saved.album is None):
        svc.albums.deleted(playlist_id)  # the photos of the old album go
    if relinked:
        svc.albums.start_sync(playlist_id)
    return _detail(svc, saved)


@router.delete("/playlists/{playlist_id}")
def delete_playlist(playlist_id: int, svc: Svc) -> dict[str, bool]:
    if _only_favorites(svc, _playlist(svc, playlist_id)):
        raise HTTPException(409, "Ulubione zostają zawsze")
    settings = svc.player.settings
    if settings.playlist_id == playlist_id:
        settings.playlist_id = None
        svc.player.save_settings(settings)
    deleted = svc.library.delete_playlist(playlist_id)
    svc.albums.deleted(playlist_id)  # an album's photos go with it
    return {"deleted": deleted}


@router.post("/playlists/{playlist_id}/items", response_model=PlaylistDetail)
def add_items(playlist_id: int, body: ItemIds, svc: Svc) -> PlaylistDetail:
    playlist = _playlist(svc, playlist_id)
    if playlist.kind != PlaylistKind.MANUAL:
        raise HTTPException(400, "items can only be added to manual playlists")

    ids = playlist.item_ids + [i for i in body.item_ids if i not in playlist.item_ids]
    for item_id in ids:  # museum works found by search join the library now
        try:
            svc.importer.save(item_id)
        except httpx.HTTPError as err:
            raise HTTPException(502, f"{item_id}: {err}") from err
    # A work the playlist has from another source is not added again.
    works = Works(i for i in map(svc.library.get, playlist.item_ids) if i is not None)
    for item_id in ids[len(playlist.item_ids) :]:
        item = svc.library.get(item_id)
        if item is not None and works.group_of(item) is not None:
            ids.remove(item_id)
        elif item is not None:
            works.add(item)
    return _detail(svc, svc.library.save_playlist(playlist.model_copy(update={"item_ids": ids})))


@router.delete("/playlists/{playlist_id}/items/{item_id}", response_model=PlaylistDetail)
def remove_item(playlist_id: int, item_id: str, svc: Svc) -> PlaylistDetail:
    """Take one work out of a playlist. A smart or album playlist remembers it
    as an exception; clearing ``rules.exclude_ids`` brings it back."""
    playlist = _playlist(svc, playlist_id)
    if playlist.kind == PlaylistKind.MANUAL:
        ids = [i for i in playlist.item_ids if i != item_id]
        update: dict[str, Any] = {"item_ids": ids}
    else:
        rules = playlist.rules
        if item_id not in rules.exclude_ids:
            rules = rules.model_copy(update={"exclude_ids": [*rules.exclude_ids, item_id]})
        update = {"rules": rules}
    saved = svc.library.save_playlist(playlist.model_copy(update=update))
    if svc.player.settings.playlist_id == playlist_id:
        svc.player.unqueue(item_id)
    return _detail(svc, saved)


@router.post("/playlists/{playlist_id}/sync")
def sync_album(playlist_id: int, svc: Svc) -> dict[str, Any]:
    """Sync an album playlist with its album now; returns the job."""
    playlist = _playlist(svc, playlist_id)
    if playlist.kind != PlaylistKind.ALBUM:
        raise HTTPException(400, "only album playlists sync")
    return {"job_id": svc.albums.start_sync(playlist_id).id}


@router.get("/playlists/{playlist_id}/sync", response_model=AlbumSync | None)
def last_sync(playlist_id: int, svc: Svc) -> AlbumSync | None:
    _playlist(svc, playlist_id)
    return svc.library.album_sync(playlist_id)


@router.post("/playlists/{playlist_id}/play", status_code=202)
async def play(playlist_id: int, svc: Svc) -> dict[str, Any]:
    if _only_favorites(svc, _playlist(svc, playlist_id)):
        raise HTTPException(409, "Ulubione zostają zawsze")
    settings = svc.player.settings
    settings.playlist_id = playlist_id
    svc.player.save_settings(settings)
    svc.player.set_hold(None)
    svc.background(svc.player.next("playlist", picks=False))  # its own first picture
    return {"accepted": True}
