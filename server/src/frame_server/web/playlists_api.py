"""Playlists: smart (rule-based) and manual."""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from ..library import (
    AlbumSync,
    ItemSummary,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    PlaylistSort,
    PlaylistSummary,
)
from ..library.duplicates import Works
from ..library.icloud import album_token
from ..service import FrameService
from ..users import User
from .deps import CurrentUser, require_token, service
from .library_api import museum_trouble

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


class Holding(BaseModel):
    """A playlist holding a work: ``item_id`` is the copy it holds, the one
    to take out (another source's copy of the work counts too)."""

    playlist_id: int
    item_id: str


class AlbumLink(BaseModel):
    url: str


class AlbumCheck(BaseModel):
    name: str
    count: int


def _playlist(svc: FrameService, playlist_id: int, user: User) -> Playlist:
    """A playlist ``user`` sees: theirs or a shared one."""
    playlist = svc.library.playlist(playlist_id)
    if playlist is None or not playlist.visible_to(user.id):
        raise HTTPException(404, f"no playlist {playlist_id}")
    return playlist


def _own(svc: FrameService, playlist_id: int, user: User) -> Playlist:
    """A playlist ``user`` may change: only its maker does."""
    playlist = _playlist(svc, playlist_id, user)
    if playlist.owner != user.id:
        raise HTTPException(403, "to playlista innej osoby")
    return playlist


def summary(svc: FrameService, playlist: Playlist) -> PlaylistSummary:
    """As the app shows it: with its maker's name when someone else made it."""
    found = svc.library.playlist_summary(playlist)
    if not found.mine:
        found.owner_name = svc.users.name_of(playlist.owner)
    return found


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
    """Whether this is its maker's one "Ulubione" playlist, which always stays."""
    return playlist.is_favorites and not any(
        p.is_favorites and p.owner == playlist.owner
        for p in svc.library.playlists()
        if p.id != playlist.id
    )


def _detail(svc: FrameService, playlist: Playlist) -> PlaylistDetail:
    items = svc.library.playlist_items(playlist)  # in its own order
    if playlist.kind == PlaylistKind.SMART:
        items = items[:DETAIL_LIMIT]  # e.g. one made before empty rules were refused
    # Pictures not yet laid over their artist's other works (a smart
    # playlist's are taken in from the museums as it fills): a copy under
    # another title is one work by the next look (library/twins.py).
    svc.twins.after_search(items)
    return PlaylistDetail(
        playlist=summary(svc, playlist),
        item_ids=playlist.item_ids,
        items=[ItemSummary.of(i) for i in items],
    )


class PlaylistOrder(BaseModel):
    ids: list[int]


@router.get("/playlists", response_model=list[PlaylistSummary])
def list_playlists(svc: Svc, user: CurrentUser) -> list[PlaylistSummary]:
    """The asking person's playlists and the shared ones of others, in the
    order they arranged the cards (their "Ulubione" first until then)."""
    return [summary(svc, p) for p in svc.library.arranged_playlists(user.id)]


@router.put("/playlists/order", response_model=list[PlaylistSummary])
def arrange_playlists(order: PlaylistOrder, svc: Svc, user: CurrentUser) -> list[PlaylistSummary]:
    """A card moved in Playlisty: the asking person's order from now on
    (each person has their own; Propozycje and Ukryte are not playlists)."""
    svc.library.arrange_playlists(user.id, order.ids)
    return list_playlists(svc, user)


@router.post("/playlists", response_model=PlaylistDetail)
def create_playlist(playlist: Playlist, svc: Svc, user: CurrentUser) -> PlaylistDetail:
    playlist = _checked(playlist).model_copy(update={"owner": user.id})
    if playlist.kind == PlaylistKind.ALBUM:
        playlist = playlist.model_copy(update={"item_ids": []})
    saved = svc.library.save_playlist(playlist.model_copy(update={"id": None}))
    svc.kept.soon(saved.item_ids)  # a manual playlist's originals stay on the server
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
def get_playlist(playlist_id: int, svc: Svc, user: CurrentUser) -> PlaylistDetail:
    return _detail(svc, _playlist(svc, playlist_id, user))


@router.put("/playlists/{playlist_id}", response_model=PlaylistDetail)
def update_playlist(
    playlist_id: int, playlist: Playlist, svc: Svc, user: CurrentUser
) -> PlaylistDetail:
    existing = _own(svc, playlist_id, user)
    # An app from before "Wspólna" sends no ``shared``: the playlist stays as it is.
    shared = playlist.shared if "shared" in playlist.model_fields_set else existing.shared
    # The order is set on its own (``/sort``); the editor sends none.
    sort = playlist.sort if "sort" in playlist.model_fields_set else existing.sort
    playlist = _checked(playlist).model_copy(
        update={"owner": existing.owner, "shared": shared, "sort": sort}
    )
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


@router.put("/playlists/{playlist_id}/sort", response_model=PlaylistDetail)
def sort_playlist(
    playlist_id: int,
    svc: Svc,
    user: CurrentUser,
    sort: Annotated[PlaylistSort | None, Body()] = None,
) -> PlaylistDetail:
    """The order of the playlist's works, in the app and on the frame when
    it does not shuffle (Mateusz 2026-11-12); null: back to the default."""
    existing = _own(svc, playlist_id, user)
    if existing.kind == PlaylistKind.ALBUM:
        raise HTTPException(409, "an album keeps the order chosen for it")
    saved = svc.library.save_playlist(existing.model_copy(update={"sort": sort}))
    if saved.order != existing.order:
        svc.player.playlist_changed(playlist_id)  # the frame's next ones follow
    return _detail(svc, saved)


@router.delete("/playlists/{playlist_id}")
def delete_playlist(playlist_id: int, svc: Svc, user: CurrentUser) -> dict[str, bool]:
    if _only_favorites(svc, _own(svc, playlist_id, user)):
        raise HTTPException(409, "Ulubione zostają zawsze")
    settings = svc.player.settings
    if settings.playlist_id == playlist_id:
        settings.playlist_id = None
        svc.player.save_settings(settings)
    deleted = svc.library.delete_playlist(playlist_id)
    svc.albums.deleted(playlist_id)  # an album's photos go with it
    return {"deleted": deleted}


@router.post("/playlists/{playlist_id}/items", response_model=PlaylistDetail)
def add_items(playlist_id: int, body: ItemIds, svc: Svc, user: CurrentUser) -> PlaylistDetail:
    playlist = _own(svc, playlist_id, user)
    if playlist.kind != PlaylistKind.MANUAL:
        raise HTTPException(400, "items can only be added to manual playlists")

    ids = playlist.item_ids + [i for i in body.item_ids if i not in playlist.item_ids]
    for item_id in ids:  # museum works found by search join the library now
        try:
            svc.importer.save(item_id)
        except httpx.HTTPError as err:
            raise HTTPException(502, museum_trouble(item_id.partition(":")[0], err)) from err
    # A work the playlist has from another source is not added again.
    works = Works(i for i in map(svc.library.get, playlist.item_ids) if i is not None)
    for item_id in ids[len(playlist.item_ids) :]:
        item = svc.library.get(item_id)
        if item is not None and works.group_of(item) is not None:
            ids.remove(item_id)
        elif item is not None:
            works.add(item)
    saved = svc.library.save_playlist(playlist.model_copy(update={"item_ids": ids}))
    svc.kept.soon(ids[len(playlist.item_ids) :])  # their originals stay on the server
    return _detail(svc, saved)


@router.delete("/playlists/{playlist_id}/items/{item_id:item}", response_model=PlaylistDetail)
def remove_item(playlist_id: int, item_id: str, svc: Svc, user: CurrentUser) -> PlaylistDetail:
    """Take one work out of a playlist. A smart or album playlist remembers it
    as an exception; clearing ``rules.exclude_ids`` brings it back."""
    playlist = _own(svc, playlist_id, user)
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


@router.get("/items/{item_id:item}/playlists", response_model=list[Holding])
def item_playlists(item_id: str, svc: Svc, user: CurrentUser) -> list[Holding]:
    """The asking person's manual playlists that hold this work, as the
    app's "Do playlisty" ticks them: the item itself or another copy of the
    same work, which adding would not add again."""
    works = svc.library.works() if svc.library.get(item_id) is not None else None
    group = works.group_index(item_id) if works is not None else None
    found: list[Holding] = []
    for playlist in svc.library.arranged_playlists(user.id):
        if playlist.kind != PlaylistKind.MANUAL or playlist.owner != user.id:
            continue
        assert playlist.id is not None
        if item_id in playlist.item_ids:
            found.append(Holding(playlist_id=playlist.id, item_id=item_id))
        elif works is not None and group is not None:
            held = next((i for i in playlist.item_ids if works.group_index(i) == group), None)
            if held is not None:
                found.append(Holding(playlist_id=playlist.id, item_id=held))
    return found


@router.post("/playlists/{playlist_id}/sync")
def sync_album(playlist_id: int, svc: Svc, user: CurrentUser) -> dict[str, Any]:
    """Sync an album playlist with its album now; returns the job."""
    playlist = _playlist(svc, playlist_id, user)
    if playlist.kind != PlaylistKind.ALBUM:
        raise HTTPException(400, "only album playlists sync")
    return {"job_id": svc.albums.start_sync(playlist_id).id}


@router.get("/playlists/{playlist_id}/sync", response_model=AlbumSync | None)
def last_sync(playlist_id: int, svc: Svc, user: CurrentUser) -> AlbumSync | None:
    _playlist(svc, playlist_id, user)
    return svc.library.album_sync(playlist_id)


@router.post("/playlists/{playlist_id}/play", status_code=202)
async def play(playlist_id: int, svc: Svc, user: CurrentUser) -> dict[str, Any]:
    _playlist(svc, playlist_id, user)  # "Ulubione" too: only deleting it is refused
    settings = svc.player.settings
    settings.playlist_id = playlist_id
    svc.player.save_settings(settings)
    svc.player.set_hold(None)
    svc.background(svc.player.next("playlist", picks=False))  # its own first picture
    return {"accepted": True}
