"""People on the server: the owner and household members (Domownicy).

The owner is whoever holds the server's own token (``FRAME_API_TOKEN``):
it always works, so the owner can never be locked out. Every other phone has
a token of its own, made when it joins with a one-time invitation the owner
shows as a QR code. The server keeps only hashes of tokens and codes.

A member uses the whole app but Konfiguracja: their own hearts, playlists
and notifications; the frame, its schedule and the library are shared.
Decisions: Mateusz, 2026-10-31 (docs/DECISIONS.md, D-users)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field

from .library import Library
from .library.viewer import OWNER_ID

STATE_KEY = "people"
INVITE_FOR = timedelta(minutes=30)
#: Wrong codes allowed before ``join`` waits (per server, not per phone:
#: there is one household).
JOIN_TRIES = 5
JOIN_WINDOW = 600.0  # seconds
#: How often a phone's "last seen" is written (not at every request).
SEEN_EVERY = timedelta(minutes=5)
STUDIES_A_DAY = 5
OWNER_NAME = "Właściciel"


class Role(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class User(BaseModel):
    id: str
    name: str
    role: Role = Role.MEMBER
    created_at: str = ""

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER


class Device(BaseModel):
    """A phone that joined: its token's hash, never the token."""

    id: str
    user_id: str
    name: str = ""
    token_hash: str
    added_at: str = ""
    last_seen_at: str | None = None


class Invite(BaseModel):
    id: str
    code_hash: str
    #: The person it brings in: a new member (``name``) or someone already
    #: there (``user_id``: a new phone of theirs, the owner's too).
    name: str = ""
    user_id: str | None = None
    created_at: str = ""
    expires_at: str = ""


class StudyOrders(BaseModel):
    day: str = ""
    count: int = 0


class People(BaseModel):
    """As kept in the library's state."""

    owner_name: str = ""
    users: list[User] = Field(default_factory=list)
    devices: list[Device] = Field(default_factory=list)
    invites: list[Invite] = Field(default_factory=list)
    #: Studies a member may order a day (Konfiguracja → Domownicy).
    study_limit: int = STUDIES_A_DAY
    studies: dict[str, StudyOrders] = Field(default_factory=dict)


class JoinError(Exception):
    """The code is wrong, used or old (or too many tries)."""


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime | None = None) -> str:
    return (moment or _now()).isoformat(timespec="seconds")


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class Users:
    def __init__(self, library: Library, master_token: str | None) -> None:
        self.library = library
        self.master_token = master_token or None
        self._lock = threading.Lock()
        self._failures: list[float] = []

    @property
    def enabled(self) -> bool:
        """People need the server's own token: without one anybody on the
        network is the owner, and a role would mean nothing."""
        return self.master_token is not None

    # -- state ----------------------------------------------------------------

    def _load(self) -> People:
        return People.model_validate(self.library.get_state(STATE_KEY, {}))

    def _save(self, people: People) -> None:
        self.library.set_state(STATE_KEY, people.model_dump(mode="json"))

    def owner(self, people: People | None = None) -> User:
        people = people or self._load()
        return User(id=OWNER_ID, name=people.owner_name or OWNER_NAME, role=Role.OWNER)

    def users(self) -> list[User]:
        people = self._load()
        return [self.owner(people), *people.users]

    def user(self, user_id: str) -> User | None:
        return next((u for u in self.users() if u.id == user_id), None)

    def name_of(self, user_id: str) -> str:
        user = self.user(user_id)
        return user.name if user is not None else ""

    def devices(self, user_id: str | None = None) -> list[Device]:
        devices = self._load().devices
        return [d for d in devices if user_id is None or d.user_id == user_id]

    def invites(self) -> list[Invite]:
        now = _stamp()
        return [i for i in self._load().invites if i.expires_at > now]

    def study_limit(self) -> int:
        return self._load().study_limit

    # -- who is asking ----------------------------------------------------------

    def authenticate(self, token: str | None) -> tuple[User, Device | None] | None:
        """The person (and phone) a token belongs to; None for a wrong one."""
        if not self.enabled:
            return self.owner(), None
        if not token:
            return None
        assert self.master_token is not None
        if hmac.compare_digest(token.encode(), self.master_token.encode()):
            return self.owner(), None
        hashed = digest(token)
        people = self._load()
        device = next(
            (d for d in people.devices if hmac.compare_digest(d.token_hash, hashed)), None
        )
        if device is None:
            return None
        user = next(
            (u for u in [self.owner(people), *people.users] if u.id == device.user_id), None
        )
        if user is None:
            return None
        self._seen(device)
        return user, device

    def _seen(self, device: Device) -> None:
        now = _now()
        seen = device.last_seen_at
        if seen is not None and now - datetime.fromisoformat(seen) < SEEN_EVERY:
            return
        with self._lock:
            people = self._load()
            for d in people.devices:
                if d.id == device.id:
                    d.last_seen_at = _stamp(now)
            self._save(people)

    # -- invitations --------------------------------------------------------------

    def invite(self, name: str = "", user_id: str | None = None) -> tuple[str, Invite]:
        """A one-time code for a new member (``name``) or a new phone of
        someone already there (``user_id``). Returns the code once."""
        if not self.enabled:
            raise ValueError("serwer nie ma tokenu FRAME_API_TOKEN")
        name = name.strip()
        if user_id is None and not name:
            raise ValueError("podaj imię")
        if user_id is not None and self.user(user_id) is None:
            raise ValueError(f"nie ma osoby {user_id}")
        code = secrets.token_urlsafe(16)
        now = _now()
        invite = Invite(
            id=secrets.token_hex(4),
            code_hash=digest(code),
            name=name,
            user_id=user_id,
            created_at=_stamp(now),
            expires_at=_stamp(now + INVITE_FOR),
        )
        with self._lock:
            people = self._load()
            people.invites = [i for i in people.invites if i.expires_at > _stamp(now)]
            people.invites.append(invite)
            self._save(people)
        return code, invite

    def cancel_invite(self, invite_id: str) -> bool:
        with self._lock:
            people = self._load()
            before = len(people.invites)
            people.invites = [i for i in people.invites if i.id != invite_id]
            self._save(people)
            return len(people.invites) < before

    def join(self, code: str, device_name: str = "") -> tuple[str, User, Device]:
        """A phone redeems an invitation: its own token (returned once),
        the person and the phone as kept."""
        with self._lock:
            moment = time.monotonic()
            self._failures = [t for t in self._failures if moment - t < JOIN_WINDOW]
            if len(self._failures) >= JOIN_TRIES:
                raise JoinError("za dużo prób, spróbuj za kilka minut")
            people = self._load()
            hashed = digest(code)
            now = _now()
            invite = next(
                (
                    i
                    for i in people.invites
                    if hmac.compare_digest(i.code_hash, hashed) and i.expires_at > _stamp(now)
                ),
                None,
            )
            if invite is None:
                self._failures.append(moment)
                raise JoinError("zaproszenie jest nieważne albo już wykorzystane")
            people.invites = [i for i in people.invites if i.id != invite.id]
            if invite.user_id is not None:
                user = next(
                    (u for u in [self.owner(people), *people.users] if u.id == invite.user_id),
                    None,
                )
                if user is None:
                    raise JoinError("tej osoby nie ma już na serwerze")
            else:
                user = User(
                    id=f"u-{secrets.token_hex(4)}", name=invite.name, created_at=_stamp(now)
                )
                people.users.append(user)
            token = secrets.token_urlsafe(32)
            device = Device(
                id=secrets.token_hex(4),
                user_id=user.id,
                name=device_name.strip()[:60],
                token_hash=digest(token),
                added_at=_stamp(now),
                last_seen_at=_stamp(now),
            )
            people.devices.append(device)
            self._save(people)
            return token, user, device

    # -- the owner's controls --------------------------------------------------------

    def remove_device(self, device_id: str) -> bool:
        with self._lock:
            people = self._load()
            before = len(people.devices)
            people.devices = [d for d in people.devices if d.id != device_id]
            self._save(people)
            return len(people.devices) < before

    def remove_user(self, user_id: str) -> bool:
        """A member and all their phones; their hearts go with them (their
        playlists are left to the caller)."""
        if user_id == OWNER_ID:
            raise ValueError("właściciela nie można usunąć")
        with self._lock:
            people = self._load()
            if not any(u.id == user_id for u in people.users):
                return False
            people.users = [u for u in people.users if u.id != user_id]
            people.devices = [d for d in people.devices if d.user_id != user_id]
            people.invites = [i for i in people.invites if i.user_id != user_id]
            people.studies.pop(user_id, None)
            self._save(people)
        self.library.forget_person(user_id)
        return True

    def rename(self, user_id: str, name: str) -> User | None:
        name = name.strip()[:40]
        if not name:
            raise ValueError("podaj imię")
        with self._lock:
            people = self._load()
            if user_id == OWNER_ID:
                people.owner_name = name
            else:
                for u in people.users:
                    if u.id == user_id:
                        u.name = name
            self._save(people)
        return self.user(user_id)

    def set_study_limit(self, limit: int) -> None:
        with self._lock:
            people = self._load()
            people.study_limit = max(0, min(limit, 100))
            self._save(people)

    # -- studies a member orders ---------------------------------------------------

    def studies_left(self, user: User, day: date) -> int | None:
        """Studies ``user`` may still order on ``day``; None: no limit."""
        if user.is_owner:
            return None
        people = self._load()
        orders = people.studies.get(user.id)
        used = orders.count if orders is not None and orders.day == day.isoformat() else 0
        return max(0, people.study_limit - used)

    def ordered_study(self, user: User, day: date) -> None:
        if user.is_owner:
            return
        with self._lock:
            people = self._load()
            orders = people.studies.get(user.id)
            if orders is None or orders.day != day.isoformat():
                orders = StudyOrders(day=day.isoformat())
            orders.count += 1
            people.studies[user.id] = orders
            self._save(people)
