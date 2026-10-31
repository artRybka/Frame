"""People on the server (users.py): who is asking, joining with an
invitation, and the owner's Konfiguracja → Domownicy."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..library.seed import ensure_favorites
from ..service import FrameService
from ..users import JoinError, Role, User
from .deps import CurrentUser, require_owner, service

router = APIRouter(prefix="/api", tags=["users"])
Svc = Annotated[FrameService, Depends(service)]
Owner = Annotated[User, Depends(require_owner)]


class MeView(BaseModel):
    id: str
    name: str
    role: Role
    #: This phone, when it joined with an invitation (None: the server's token).
    device_id: str | None = None
    #: Studies this person may still order today (None: no limit).
    studies_left: int | None = None
    #: Whether the server can have people (it has a token of its own).
    people: bool = True


class JoinRequest(BaseModel):
    code: str = Field(min_length=8, max_length=200)
    device: str = Field("", max_length=60)


class Joined(BaseModel):
    #: The phone's own token: shown this once, kept in its Keychain.
    token: str
    me: MeView


class DeviceView(BaseModel):
    id: str
    name: str
    added_at: str
    last_seen_at: str | None = None


class PersonView(BaseModel):
    id: str
    name: str
    role: Role
    devices: list[DeviceView]
    playlists: int = 0
    favorites: int = 0


class InviteView(BaseModel):
    id: str
    name: str
    user_id: str | None = None
    expires_at: str


class PeopleView(BaseModel):
    people: bool
    users: list[PersonView]
    invites: list[InviteView]
    study_limit: int


class InviteRequest(BaseModel):
    """A new member (``name``) or a new phone of someone there (``user_id``,
    the owner's own too)."""

    name: str = Field("", max_length=40)
    user_id: str | None = None


class NewInvite(BaseModel):
    #: The one-time code (shown once; the server keeps its hash).
    code: str
    invite: InviteView


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class PeopleSettings(BaseModel):
    study_limit: int = Field(ge=0, le=100)


def _me(svc: FrameService, user: User, request: Request) -> MeView:
    device = getattr(request.state, "device", None)
    return MeView(
        id=user.id,
        name=user.name,
        role=user.role,
        device_id=device.id if device is not None else None,
        studies_left=svc.users.studies_left(user, date.today()),
        people=svc.users.enabled,
    )


def _people(svc: FrameService) -> PeopleView:
    users = svc.users
    playlists = svc.library.playlists()
    hearts = svc.library.fans()
    return PeopleView(
        people=users.enabled,
        users=[
            PersonView(
                id=u.id,
                name=u.name,
                role=u.role,
                devices=[
                    DeviceView(
                        id=d.id, name=d.name, added_at=d.added_at, last_seen_at=d.last_seen_at
                    )
                    for d in users.devices(u.id)
                ],
                playlists=sum(p.owner == u.id for p in playlists),
                favorites=len(hearts.get(u.id, ())),
            )
            for u in users.users()
        ],
        invites=[
            InviteView(id=i.id, name=i.name, user_id=i.user_id, expires_at=i.expires_at)
            for i in users.invites()
        ],
        study_limit=users.study_limit(),
    )


@router.get("/me", response_model=MeView)
def me(svc: Svc, user: CurrentUser, request: Request) -> MeView:
    """Who this phone is on the server: the app shows a member no Konfiguracja."""
    return _me(svc, user, request)


@router.delete("/me/device", status_code=204)
def leave(svc: Svc, user: CurrentUser, request: Request) -> None:
    """This phone leaves ("Odłącz ten telefon"): its token stops working."""
    device = getattr(request.state, "device", None)
    if device is None:
        raise HTTPException(409, "ten telefon używa tokenu serwera")
    svc.users.remove_device(device.id)


@router.post("/join", response_model=Joined)
def join(body: JoinRequest, svc: Svc, request: Request) -> Joined:
    """A phone redeems the owner's invitation (no token needed: the code is
    the proof). It gets its own token, once."""
    try:
        token, user, device = svc.users.join(body.code.strip(), body.device)
    except JoinError as err:
        raise HTTPException(403, str(err)) from err
    ensure_favorites(svc.library, user.id)  # their own "Ulubione" from the start
    request.state.device = device
    return Joined(token=token, me=_me(svc, user, request))


@router.get("/users", response_model=PeopleView)
def people(svc: Svc, _: Owner) -> PeopleView:
    return _people(svc)


@router.post("/users/invites", response_model=NewInvite)
def invite(body: InviteRequest, svc: Svc, _: Owner) -> NewInvite:
    try:
        code, found = svc.users.invite(body.name, body.user_id)
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    return NewInvite(
        code=code,
        invite=InviteView(
            id=found.id, name=found.name, user_id=found.user_id, expires_at=found.expires_at
        ),
    )


@router.delete("/users/invites/{invite_id}", response_model=PeopleView)
def cancel_invite(invite_id: str, svc: Svc, _: Owner) -> PeopleView:
    svc.users.cancel_invite(invite_id)
    return _people(svc)


@router.delete("/users/devices/{device_id}", response_model=PeopleView)
def remove_device(device_id: str, svc: Svc, _: Owner) -> PeopleView:
    """ "Odbierz dostęp": that phone's token stops working at once."""
    if not svc.users.remove_device(device_id):
        raise HTTPException(404, f"no device {device_id}")
    return _people(svc)


@router.put("/users/settings", response_model=PeopleView)
def put_settings(body: PeopleSettings, svc: Svc, _: Owner) -> PeopleView:
    svc.users.set_study_limit(body.study_limit)
    return _people(svc)


@router.put("/users/{user_id}", response_model=PeopleView)
def rename(user_id: str, body: Rename, svc: Svc, _: Owner) -> PeopleView:
    try:
        found = svc.users.rename(user_id, body.name)
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    if found is None:
        raise HTTPException(404, f"no user {user_id}")
    return _people(svc)


@router.delete("/users/{user_id}", response_model=PeopleView)
def remove(user_id: str, svc: Svc, _: Owner) -> PeopleView:
    """A member leaves the household: their phones stop working, their
    hearts and private playlists go; playlists they shared stay, now the
    owner's. Their phones hear nothing more."""
    try:
        removed = svc.users.remove_user(user_id)
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    if not removed:
        raise HTTPException(404, f"no user {user_id}")
    owner = svc.users.owner()
    playing = svc.player.settings.playlist_id
    for playlist in svc.library.playlists():
        if playlist.owner != user_id or playlist.id is None:
            continue
        if playlist.shared and not playlist.is_favorites:
            svc.library.save_playlist(playlist.model_copy(update={"owner": owner.id}))
        elif playlist.id != playing:
            svc.library.delete_playlist(playlist.id)
            svc.albums.deleted(playlist.id)
        else:  # on the frame now: it plays on, the owner's
            svc.library.save_playlist(playlist.model_copy(update={"owner": owner.id}))
    for device in svc.notifier.devices():
        if device.user == user_id:
            svc.notifier.forget(device.token)
    return _people(svc)
