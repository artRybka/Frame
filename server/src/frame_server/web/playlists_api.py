"""Playlists: smart (rule-based) and manual."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..library import ItemSummary, Playlist, PlaylistKind, PlaylistRules, PlaylistSummary
from ..schedule import Mode
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


def _playlist(svc: FrameService, playlist_id: int) -> Playlist:
    playlist = svc.library.playlist(playlist_id)
    if playlist is None:
        raise HTTPException(404, f"no playlist {playlist_id}")
    return playlist


def _detail(svc: FrameService, playlist: Playlist) -> PlaylistDetail:
    items = svc.library.playlist_items(playlist, sort="artist")
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
    saved = svc.library.save_playlist(playlist.model_copy(update={"id": None}))
    return _detail(svc, saved)


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
    saved = svc.library.save_playlist(
        playlist.model_copy(update={"id": playlist_id, "created_at": existing.created_at})
    )
    return _detail(svc, saved)


@router.delete("/playlists/{playlist_id}")
def delete_playlist(playlist_id: int, svc: Svc) -> dict[str, bool]:
    _playlist(svc, playlist_id)
    settings = svc.player.settings
    if settings.playlist_id == playlist_id:
        settings.playlist_id = None
        svc.player.save_settings(settings)
    return {"deleted": svc.library.delete_playlist(playlist_id)}


@router.post("/playlists/{playlist_id}/items", response_model=PlaylistDetail)
def add_items(playlist_id: int, body: ItemIds, svc: Svc) -> PlaylistDetail:
    playlist = _playlist(svc, playlist_id)
    if playlist.kind != PlaylistKind.MANUAL:
        raise HTTPException(400, "items can only be added to manual playlists")
    ids = playlist.item_ids + [i for i in body.item_ids if i not in playlist.item_ids]
    return _detail(svc, svc.library.save_playlist(playlist.model_copy(update={"item_ids": ids})))


@router.delete("/playlists/{playlist_id}/items/{item_id}", response_model=PlaylistDetail)
def remove_item(playlist_id: int, item_id: str, svc: Svc) -> PlaylistDetail:
    playlist = _playlist(svc, playlist_id)
    ids = [i for i in playlist.item_ids if i != item_id]
    return _detail(svc, svc.library.save_playlist(playlist.model_copy(update={"item_ids": ids})))


@router.post("/playlists/{playlist_id}/play", status_code=202)
async def play(playlist_id: int, svc: Svc) -> dict[str, Any]:
    _playlist(svc, playlist_id)
    settings = svc.player.settings
    settings.mode = Mode.ART
    settings.playlist_id = playlist_id
    svc.player.save_settings(settings)
    svc.player.set_hold(None)
    svc.background(svc.player.next("playlist"))
    return {"accepted": True}
