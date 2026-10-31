"""Notifications on the owner's phone, over Apple's push service (APNs).

The iOS app asks iOS for a device token and leaves it here with the kinds
it wants (``PushDevice``). The server talks to APNs itself with a token
signed by the owner's APNs key (an ``AuthKey_<id>.p8`` from the Apple
Developer account, uploaded in the app and kept in data/push/), so the
phone hears from the frame wherever it is: APNs reaches it, not this server.

What is told (``KINDS``): the battery under 20 %, a picture that did not
reach the frame, a new picture on the frame, a new server version, and the
work of the day at 8:30. The events come from the rest of the server
(``Notifier.battery``, ``ended``, ``shown``); the clock-driven ones from
``watch``.

A study being written is followed on the Lock Screen and in the Dynamic
Island (a Live Activity the app starts): the app leaves the activity's own
push token here (``Notifier.follow_study``) and each step of the study is
pushed to it (``Notifier.study_step``), so it moves on with the app closed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from pydantic import BaseModel

from .births import search_name

if TYPE_CHECKING:
    from .library import Item, Library
    from .service import FrameService
    from .store import ContentInfo

log = logging.getLogger(__name__)

# The Apple Developer team and the app's bundle id (ios/project.yml).
TEAM_ID = "3MQRJF4A9D"
TOPIC = "com.artrybka.frame"
# Pushes to Live Activities go to the app's topic with this ending.
LIVE_SUFFIX = ".push-type.liveactivity"
HOSTS = {False: "https://api.push.apple.com", True: "https://api.sandbox.push.apple.com"}

# What the app can switch, in its order, with the texts of its toggles.
KINDS: dict[str, tuple[str, str]] = {
    "battery": ("Bateria poniżej 20%", "Raz na rozładowanie, gdy ramka działa na baterii."),
    "send_failed": ("Błąd wysyłki", "Obraz nie dotarł na ramkę."),
    "changed": ("Zmiana dzieła", "Ramka pokazuje nowy obraz: z harmonogramu lub z aplikacji."),
    "server_update": ("Nowa wersja serwera", "Gotowa do instalacji w aplikacji."),
    "daily": ("Studium dnia", "Nowe studium dzieła w Odkrywaj, codziennie o 8:30."),
    "study": ("Studium gotowe", "Gdy skończy się pisać zamówione studium dzieła."),
    "week_artist": ("Artysta tygodnia", "W poniedziałek o 9:00."),
    "birthday": ("Rocznica urodzin", "Urodziny artystów Twoich ulubionych dzieł, o 10:00."),
}
# The kinds of the first release: a phone registered then gets the later
# ones switched on as they come (``PushDevice.seen``).
FIRST_KINDS = ["battery", "send_failed", "changed", "server_update", "daily"]

BATTERY_LOW = 20
# Told once below ``BATTERY_LOW``; again only after charging or this level.
BATTERY_REARM = 25
DAILY_AT = time(8, 30)
# The day's page not written yet at 8:30: wait for it until then, at most.
DAILY_WAIT_UNTIL = time(9, 0)
# Started later than this (the NAS was off), the day goes without.
DAILY_LATEST = time(12, 0)
UPDATE_EVERY = timedelta(minutes=10)
WEEK_AT = time(9, 0)  # Mondays
WEEK_LATEST = time(14, 0)
BIRTHDAY_AT = time(10, 0)
BIRTHDAY_LATEST = time(15, 0)
BIRTHDAYS_MAX = 3  # a day, the artists with most favourites first
# Favourite artists looked up on Wikidata at a time, once an hour.
BIRTHS_EVERY = timedelta(hours=1)
BIRTHS_BATCH = 15
# Apple takes a provider token for an hour and wants it no more often than
# every 20 minutes.
JWT_FOR = timedelta(minutes=40)
BODY_CHARS = 180

DEVICES_KEY = "push_devices"
BATTERY_KEY = "push_battery_told"
DAILY_KEY = "push_daily_day"
UPDATE_KEY = "push_update_version"
WEEK_SENT_KEY = "push_week_artist"
BIRTHDAY_SENT_KEY = "push_birthday_day"
STUDY_ACTIVITIES_KEY = "push_study_activities"

# A study's Live Activity: with no word for this long it says to open the app.
STUDY_STALE = timedelta(minutes=15)
# Once over, how long it stays on the Lock Screen: ready (a tap opens it),
# or why not.
STUDY_READY_FOR = timedelta(hours=1)
STUDY_FAILED_FOR = timedelta(minutes=15)
STUDY_ON_WAY = ("waiting", "sources", "writing", "details")

# APNs answers meaning the token is no good any more.
GONE = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}
_TOKEN = re.compile(r"^[0-9a-f]{32,200}$")
_KEY_ID = re.compile(r"^[A-Z0-9]{10}$")


class PushError(ValueError):
    """Something the app shows as it is (Polish)."""


class PushKey(BaseModel):
    key_id: str
    team_id: str
    added_at: str


class PushDevice(BaseModel):
    token: str
    sandbox: bool = False  # a build from Xcode; TestFlight and the App Store are not
    kinds: list[str] = list(KINDS)
    #: The kinds there were when it last chose (None: the first release's).
    seen: list[str] | None = None
    name: str = ""
    added_at: str = ""
    last_sent_at: str | None = None
    last_error: str | None = None


class StudyActivity(BaseModel):
    """A study followed on a phone's Lock Screen: its Live Activity's token."""

    item_id: str
    token: str
    sandbox: bool = False
    added_at: str = ""


@dataclass
class Sent:
    status: int
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == 200


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def short(text: str, limit: int = BODY_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def load_key(pem: bytes) -> ec.EllipticCurvePrivateKey:
    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except (ValueError, TypeError) as err:
        raise PushError("to nie jest klucz APNs (plik AuthKey_….p8)") from err
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise PushError("to nie jest klucz APNs (plik AuthKey_….p8)")
    return key


def key_id_from(filename: str) -> str | None:
    match = re.search(r"AuthKey_([A-Z0-9]{10})", filename or "")
    return match.group(1) if match else None


class Apns:
    """Sends to APNs with a provider token (JWT, ES256) of the owner's key."""

    def __init__(
        self,
        pem: bytes,
        key_id: str,
        team_id: str,
        topic: str = TOPIC,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.key = load_key(pem)
        self.key_id = key_id
        self.team_id = team_id
        self.topic = topic
        self.transport = transport
        self._jwt: tuple[str, datetime] | None = None

    def token(self, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        if self._jwt and now - self._jwt[1] < JWT_FOR:
            return self._jwt[0]
        header = _b64(json.dumps({"alg": "ES256", "kid": self.key_id}).encode())
        claims = _b64(json.dumps({"iss": self.team_id, "iat": int(now.timestamp())}).encode())
        signing_input = f"{header}.{claims}".encode()
        r, s = decode_dss_signature(self.key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
        signature = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        jwt = f"{header}.{claims}.{signature}"
        self._jwt = (jwt, now)
        return jwt

    def client(self) -> httpx.AsyncClient:
        if self.transport is not None:
            return httpx.AsyncClient(transport=self.transport, timeout=20)
        return httpx.AsyncClient(http2=True, timeout=20)

    async def send(
        self,
        client: httpx.AsyncClient,
        device: str,
        payload: dict[str, Any],
        *,
        sandbox: bool,
        collapse: str | None = None,
        expires: datetime | None = None,
        live: bool = False,
    ) -> Sent:
        """``live``: to a Live Activity's token, not to the app's."""
        headers = {
            "authorization": f"bearer {self.token()}",
            "apns-topic": self.topic + LIVE_SUFFIX if live else self.topic,
            "apns-push-type": "liveactivity" if live else "alert",
            "apns-priority": "10",
        }
        if collapse:
            headers["apns-collapse-id"] = collapse[:64]
        if expires:
            headers["apns-expiration"] = str(int(expires.timestamp()))
        try:
            response = await client.post(
                f"{HOSTS[sandbox]}/3/device/{device}", json=payload, headers=headers
            )
        except httpx.HTTPError as err:
            return Sent(0, f"brak połączenia z Apple: {err.__class__.__name__}")
        if response.status_code == 200:
            return Sent(200)
        try:
            reason = str(response.json().get("reason") or response.status_code)
        except ValueError:
            reason = str(response.status_code)
        if reason in ("ExpiredProviderToken", "InvalidProviderToken"):
            self._jwt = None
        return Sent(response.status_code, reason)


class Notifier:
    def __init__(
        self,
        data_dir: Path,
        library: Library,
        *,
        topic: str = TOPIC,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.folder = data_dir / "push"
        self.library = library
        self.topic = topic
        self.transport = transport
        self._apns: Apns | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Future[object]] = set()

    # -- the key -------------------------------------------------------------

    @property
    def _key_file(self) -> Path:
        return self.folder / "key.json"

    def key(self) -> PushKey | None:
        try:
            return PushKey.model_validate_json(self._key_file.read_text())
        except (OSError, ValueError):
            return None

    def save_key(self, pem: bytes, key_id: str, team_id: str = TEAM_ID) -> PushKey:
        key_id, team_id = key_id.strip().upper(), team_id.strip().upper()
        if not _KEY_ID.match(key_id):
            raise PushError("brak identyfikatora klucza (10 znaków, jak w nazwie AuthKey_….p8)")
        if not _KEY_ID.match(team_id):
            raise PushError("identyfikator zespołu ma 10 znaków")
        load_key(pem)
        self.delete_key()
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"AuthKey_{key_id}.p8"
        path.write_bytes(pem)
        os.chmod(path, 0o600)
        info = PushKey(key_id=key_id, team_id=team_id, added_at=_now())
        self._key_file.write_text(info.model_dump_json(indent=2))
        self._apns = None
        return info

    def delete_key(self) -> None:
        for path in self.folder.glob("AuthKey_*.p8"):
            path.unlink(missing_ok=True)
        self._key_file.unlink(missing_ok=True)
        self._apns = None

    def apns(self) -> Apns | None:
        if self._apns is None and (info := self.key()) is not None:
            try:
                pem = (self.folder / f"AuthKey_{info.key_id}.p8").read_bytes()
                self._apns = Apns(pem, info.key_id, info.team_id, self.topic, self.transport)
            except (OSError, PushError) as err:
                log.warning("APNs key unusable: %s", err)
        return self._apns

    # -- the phones ----------------------------------------------------------

    def devices(self) -> list[PushDevice]:
        stored = self.library.get_state(DEVICES_KEY, [])
        devices = [PushDevice.model_validate(d) for d in stored]
        for device in devices:
            seen = device.seen if device.seen is not None else FIRST_KINDS
            new = [k for k in KINDS if k not in seen]
            if new or device.seen is None:
                wanted = set(device.kinds) | set(new)
                device.kinds = [k for k in KINDS if k in wanted]
                device.seen = list(KINDS)
        return devices

    def _save(self, devices: list[PushDevice]) -> None:
        self.library.set_state(DEVICES_KEY, [d.model_dump() for d in devices])

    def device(self, token: str) -> PushDevice | None:
        return next((d for d in self.devices() if d.token == token.lower()), None)

    def register(
        self, token: str, *, sandbox: bool, kinds: list[str] | None = None, name: str = ""
    ) -> PushDevice:
        token = token.strip().lower()
        if not _TOKEN.match(token):
            raise PushError("nieprawidłowy token urządzenia")
        devices = self.devices()
        found = next((d for d in devices if d.token == token), None)
        if found is None:
            found = PushDevice(token=token, sandbox=sandbox, added_at=_now(), seen=list(KINDS))
            devices.append(found)
        found.sandbox = sandbox
        if kinds is not None:
            found.kinds = [k for k in KINDS if k in kinds]
            found.seen = list(KINDS)
        if name:
            found.name = name[:60]
        self._save(devices)
        return found

    def forget(self, token: str) -> None:
        self._save([d for d in self.devices() if d.token != token.lower()])

    def wanted(self, kind: str) -> bool:
        return self.key() is not None and any(kind in d.kinds for d in self.devices())

    # -- sending -------------------------------------------------------------

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def notify(
        self,
        kind: str,
        title: str,
        body: str,
        *,
        route: str | None = None,
        collapse: str | None = None,
        expires: datetime | None = None,
    ) -> None:
        """Send in the background, from the event loop or any thread."""
        if not self.wanted(kind):
            return
        coro = self.send(kind, title, body, route=route, collapse=collapse, expires=expires)
        self._spawn(coro)

    def _spawn(self, coro: Coroutine[Any, Any, object]) -> None:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        future: asyncio.Future[object]
        if running is not None:
            future = running.create_task(coro)
        elif self._loop is not None and not self._loop.is_closed():
            future = asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(coro, self._loop), loop=self._loop
            )
        else:
            coro.close()
            return
        self._tasks.add(future)
        future.add_done_callback(self._tasks.discard)

    async def send(
        self,
        kind: str,
        title: str,
        body: str,
        *,
        route: str | None = None,
        collapse: str | None = None,
        expires: datetime | None = None,
        only: str | None = None,
    ) -> dict[str, Sent]:
        """To every phone that wants ``kind`` (``only``: that one, whatever
        it wants); a token APNs says is gone is forgotten. A token from
        the other environment (a build from Xcode) is tried there too."""
        apns = self.apns()
        if apns is None:
            return {}
        devices = self.devices()
        if only is not None:
            targets = [d for d in devices if d.token == only.lower()]
        else:
            targets = [d for d in devices if kind in d.kinds]
        payload: dict[str, Any] = {
            "aps": {"alert": {"title": title, "body": short(body)}, "sound": "default"},
            "kind": kind,
        }
        if route:
            payload["route"] = route
        results: dict[str, Sent] = {}
        async with apns.client() as client:
            for device in targets:
                sent = await apns.send(
                    client,
                    device.token,
                    payload,
                    sandbox=device.sandbox,
                    collapse=collapse,
                    expires=expires,
                )
                if sent.reason == "BadDeviceToken":
                    other = await apns.send(
                        client,
                        device.token,
                        payload,
                        sandbox=not device.sandbox,
                        collapse=collapse,
                        expires=expires,
                    )
                    if other.ok:
                        device.sandbox = not device.sandbox
                        sent = other
                results[device.token] = sent
                if sent.ok:
                    device.last_sent_at, device.last_error = _now(), None
                else:
                    device.last_error = sent.reason
                    log.warning("APNs %s to …%s: %s", kind, device.token[-6:], sent.reason)
        # Saved again from the latest list: the app may have changed it meanwhile.
        current = {d.token: d for d in self.devices()}
        for token, sent in results.items():
            if token not in current:
                continue
            if sent.reason in GONE and sent.status in (400, 410):
                del current[token]
                continue
            changed = next(d for d in targets if d.token == token)
            current[token] = current[token].model_copy(
                update={
                    "sandbox": changed.sandbox,
                    "last_sent_at": changed.last_sent_at,
                    "last_error": changed.last_error,
                }
            )
        self._save(list(current.values()))
        if sent_ok := sum(s.ok for s in results.values()):
            log.info("APNs %s sent to %d phone(s)", kind, sent_ok)
        return results

    # -- what is told --------------------------------------------------------

    def battery(self, level: int, on_battery: bool) -> None:
        """A battery reading: told once under ``BATTERY_LOW`` on battery."""
        told = bool(self.library.get_state(BATTERY_KEY, False))
        if not on_battery or level >= BATTERY_REARM:
            if told:
                self.library.set_state(BATTERY_KEY, False)
            return
        if level < BATTERY_LOW and not told:
            self.library.set_state(BATTERY_KEY, True)
            self.notify(
                "battery",
                f"Bateria ramki: {level}%",
                "Podłącz ramkę do ładowarki, zanim się rozładuje.",
                collapse="battery",
                route="frame",
            )

    def ended(self, failed: bool, title: str, message: str | None) -> None:
        """A send ended (progress.py); only a failure is told."""
        if not failed:
            return
        what = f"„{title}” nie dotarł na ramkę." if title else "Obraz nie dotarł na ramkę."
        body = f"{what} {message}" if message else what
        self.notify("send_failed", "Błąd wysyłki", body, route="now")

    def shown(self, title: str, artist: str, origin: str | None) -> None:
        """The frame drew a picture it did not show before."""
        how = {"schedule": "z harmonogramu", "app": "z aplikacji"}.get(origin or "")
        body = " · ".join(p for p in (artist, f"zmiana {how}" if how else "") if p)
        self.notify(
            "changed",
            f"Na ramce: {title}" if title else "Na ramce nowy obraz",
            body or "Ramka pokazuje nowy obraz.",
            collapse="changed",
            route="now",
        )

    def study_ready(self, item_id: str, title: str) -> None:
        """A study asked for on a work's card is written."""
        self.notify(
            "study",
            "Studium gotowe",
            _ready_body(title),
            route=f"study/{item_id}",
            collapse=f"study-{item_id}"[:64],
        )

    # -- studies on the Lock Screen (Live Activity) ----------------------------

    def study_activities(self, item_id: str | None = None) -> list[StudyActivity]:
        stored = self.library.get_state(STUDY_ACTIVITIES_KEY, [])
        found = [StudyActivity.model_validate(a) for a in stored]
        return [a for a in found if item_id is None or a.item_id == item_id]

    def _save_activities(self, activities: list[StudyActivity]) -> None:
        self.library.set_state(STUDY_ACTIVITIES_KEY, [a.model_dump() for a in activities])

    def follow_study(self, item_id: str, token: str, *, sandbox: bool) -> StudyActivity:
        """The token of the Live Activity following ``item_id``'s study (it
        may change while the activity runs: the newest replaces the old)."""
        token = token.strip().lower()
        if not _TOKEN.match(token):
            raise PushError("nieprawidłowy token Live Activity")
        kept = [a for a in self.study_activities() if a.token != token]
        activity = StudyActivity(item_id=item_id, token=token, sandbox=sandbox, added_at=_now())
        self._save_activities([*kept, activity])
        return activity

    def unfollow_study(self, token: str) -> None:
        self._forget_activities({token.lower()})

    def study_step(self, item_id: str, status: str, error: str = "", title: str = "") -> None:
        """A step of a study asked for (study.py): to its Live Activities;
        "ready" also as "Studium gotowe", on the Lock Screen card when there
        is one (it lights the screen up), as a notification otherwise."""
        followed = bool(self.study_activities(item_id))
        if status == "ready" and not followed:
            self.study_ready(item_id, title)
        elif followed:
            self._spawn(self._study_step(item_id, status, error, title))

    async def _study_step(self, item_id: str, status: str, error: str, title: str) -> None:
        alert = None
        if status == "ready" and self.wanted("study"):
            alert = ("Studium gotowe", _ready_body(title))
        results = await self.push_study(item_id, status, error, alert=alert)
        if alert and not any(sent.ok for sent in results.values()):
            await self.send(
                "study", *alert, route=f"study/{item_id}", collapse=f"study-{item_id}"[:64]
            )

    async def push_study(
        self,
        item_id: str,
        status: str,
        error: str = "",
        *,
        alert: tuple[str, str] | None = None,
        only: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Sent]:
        """The study's step to the Live Activities following it (``only``:
        that one). Under way it moves them on; over ("ready", "failed", or
        "stopped" when the server lost it) it ends them, and they are
        forgotten here."""
        activities = [
            a for a in self.study_activities(item_id) if only is None or a.token == only.lower()
        ]
        over = status not in STUDY_ON_WAY
        apns = self.apns()
        if apns is None or not activities:
            if over and activities:  # no key (any more): nothing will reach them
                self._forget_activities({a.token for a in activities})
            return {}
        now = now or datetime.now(UTC)
        aps: dict[str, Any] = {
            "timestamp": int(now.timestamp()),
            "event": "end" if over else "update",
            "content-state": {"status": status, "error": error},
        }
        if over:
            keep = STUDY_READY_FOR if status == "ready" else STUDY_FAILED_FOR
            aps["dismissal-date"] = int((now + keep).timestamp())
        else:
            aps["stale-date"] = int((now + STUDY_STALE).timestamp())
        if alert:
            aps["alert"] = {"title": alert[0], "body": short(alert[1]), "sound": "default"}
        payload = {"aps": aps}
        results: dict[str, Sent] = {}
        async with apns.client() as client:
            for activity in activities:
                sent = await apns.send(
                    client, activity.token, payload, sandbox=activity.sandbox, live=True
                )
                if sent.reason == "BadDeviceToken":
                    other = await apns.send(
                        client, activity.token, payload, sandbox=not activity.sandbox, live=True
                    )
                    if other.ok:
                        sent = other
                results[activity.token] = sent
                if not sent.ok:
                    log.warning(
                        "APNs study %s to …%s: %s", status, activity.token[-6:], sent.reason
                    )
        gone = {
            token
            for token, sent in results.items()
            if over or (sent.reason in GONE and sent.status in (400, 410))
        }
        self._forget_activities(gone)
        return results

    def _forget_activities(self, tokens: set[str]) -> None:
        if tokens:
            self._save_activities([a for a in self.study_activities() if a.token not in tokens])


def _ready_body(title: str) -> str:
    return f"„{title}”: można czytać." if title else "Można czytać."


# -- the clock ----------------------------------------------------------------


def item_title(service: FrameService, item: Item) -> str:
    """A work's title, in Polish where known."""
    polish = service.pl_text.text(item)
    return polish.title if polish and polish.title else item.title


def works(count: int) -> str:
    """ "1 dzieło", "3 dzieła", "12 dzieł"."""
    if count == 1:
        return "1 dzieło"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} dzieła"
    return f"{count} dzieł"


def shown_text(service: FrameService, content: ContentInfo | None) -> tuple[str, str]:
    """Title and artist of the picture on the frame, in Polish where known."""
    if content is None:
        return "", ""
    item_id = content.extra.get("item_id") if content.extra else None
    item = service.library.get(str(item_id)) if item_id else None
    if item is None:
        return content.title, ""
    polish = service.pl_text.text(item)
    return (polish.title if polish and polish.title else item.title), item.artist


async def daily_tick(service: FrameService, now: datetime | None = None) -> bool:
    """The work of the day at 8:30 (the frame's time zone); True once sent."""
    notifier = service.notifier
    tz = service.player.settings.tz()
    local = (now or datetime.now(UTC)).astimezone(tz)
    day = local.date()
    if not DAILY_AT <= local.time() < DAILY_LATEST:
        return False
    if notifier.library.get_state(DAILY_KEY) == day.isoformat() or not notifier.wanted("daily"):
        return False
    item = await asyncio.to_thread(service.daily.pick, day)
    if item is None:
        return False
    essay = await asyncio.to_thread(service.daily.job.essay, item)
    if essay is None and local.time() < DAILY_WAIT_UNTIL and service.ai_config.enabled("daily"):
        return False  # its page is still being written
    polish = service.pl_text.text(item)
    title = (essay.title if essay and essay.title else None) or (
        polish.title if polish and polish.title else item.title
    )
    teaser = essay.teaser if essay else ""
    body = ". ".join(p for p in (item.artist, teaser) if p) or "Zobacz w Odkrywaj."
    notifier.library.set_state(DAILY_KEY, day.isoformat())
    end_of_day = datetime.combine(day + timedelta(days=1), time(0), tz)
    await notifier.send(
        "daily", f"Studium dnia: {title}", body, route="daily", collapse="daily", expires=end_of_day
    )
    return True


async def update_tick(service: FrameService) -> bool:
    """A new server version, told once per version."""
    from .updates import UpdateFolder

    notifier = service.notifier
    if not notifier.wanted("server_update"):
        return False
    view = UpdateFolder(service.settings.data_dir / "update").view()
    version = view.latest_version
    if not view.update_available or not version:
        return False
    if notifier.library.get_state(UPDATE_KEY) == version:
        return False
    notifier.library.set_state(UPDATE_KEY, version)
    await notifier.send(
        "server_update",
        f"Nowa wersja serwera: {version}",
        f"Teraz działa {view.version}. Zainstaluj w aplikacji: Ramka → kafelek Serwer.",
        route="server",
        collapse="server_update",
    )
    return True


async def week_tick(service: FrameService, now: datetime | None = None) -> bool:
    """The artist of the week on Monday at 9:00, once a week."""
    from .library.themes import weekly_themes

    notifier = service.notifier
    local = (now or datetime.now(UTC)).astimezone(service.player.settings.tz())
    if local.weekday() != 0 or not WEEK_AT <= local.time() < WEEK_LATEST:
        return False
    year, week, _ = local.isocalendar()
    stamp = f"{year}-W{week:02d}"
    if notifier.library.get_state(WEEK_SENT_KEY) == stamp or not notifier.wanted("week_artist"):
        return False
    themes = await asyncio.to_thread(weekly_themes, service.library, local.date())
    theme = next((t for t in themes if t.key.startswith("week-artist-")), None)
    notifier.library.set_state(WEEK_SENT_KEY, stamp)
    if theme is None:
        return False
    body = theme.description.removeprefix("Artysta tygodnia.").strip() or "Zobacz w Odkrywaj."
    await notifier.send(
        "week_artist",
        f"Artysta tygodnia: {theme.name}",
        body,
        route=f"theme/{theme.key}",
        collapse="week_artist",
    )
    return True


async def births_tick(service: FrameService) -> int:
    """Birthdays of a few more favourite artists from Wikidata."""
    births = service.births
    if not service.notifier.wanted("birthday"):
        return 0
    artists = [a for a, _ in (await asyncio.to_thread(births.favourites)).most_common()]
    missing = births.missing(artists)[:BIRTHS_BATCH]
    if not missing:
        return 0
    return await asyncio.to_thread(births.look_up, missing)


async def birthday_tick(service: FrameService, now: datetime | None = None) -> int:
    """Today's birthdays of the favourite works' artists, at 10:00; how many."""
    notifier = service.notifier
    local = (now or datetime.now(UTC)).astimezone(service.player.settings.tz())
    day = local.date()
    if not BIRTHDAY_AT <= local.time() < BIRTHDAY_LATEST:
        return 0
    if notifier.library.get_state(BIRTHDAY_SENT_KEY) == day.isoformat():
        return 0
    if not notifier.wanted("birthday"):
        return 0
    favourites = await asyncio.to_thread(service.births.favourites)
    notifier.library.set_state(BIRTHDAY_SENT_KEY, day.isoformat())
    born_today = service.births.today(day, [a for a, _ in favourites.most_common()])
    for artist, born in born_today[:BIRTHDAYS_MAX]:
        years = day.year - born.year
        await notifier.send(
            "birthday",
            f"Urodziny: {search_name(artist)}",
            f"{years}. rocznica urodzin (ur. {born.day}.{born.month:02d}.{born.year}). "
            f"W Twoich ulubionych: {works(favourites[artist])}.",
            route=f"artist/{artist}",
            collapse=f"birthday-{artist}"[:64],
        )
    return len(born_today[:BIRTHDAYS_MAX])


async def settle_studies(service: FrameService) -> int:
    """On start: Live Activities of studies the server was writing when it
    stopped end, saying so (or ready, if it got that far); how many."""
    notifier = service.notifier
    ended = 0
    for item_id in dict.fromkeys(a.item_id for a in notifier.study_activities()):
        item = service.library.get(item_id)
        status, error = service.study.status(item)
        if status in STUDY_ON_WAY:
            continue
        if status in ("ready", "failed"):
            await notifier.push_study(item_id, status, error)
        else:
            await notifier.push_study(item_id, "stopped")
        ended += 1
    return ended


async def watch(service: FrameService) -> None:
    """The clock-driven notifications, a look a minute."""
    service.notifier.bind(asyncio.get_running_loop())
    try:
        await settle_studies(service)
    except Exception:
        log.exception("study activities")
    await asyncio.sleep(30)
    last_update = last_births = datetime.min.replace(tzinfo=UTC)
    while True:
        try:
            await daily_tick(service)
            await week_tick(service)
            await birthday_tick(service)
            now = datetime.now(UTC)
            if now - last_update >= UPDATE_EVERY:
                last_update = now
                await update_tick(service)
            if now - last_births >= BIRTHS_EVERY:
                last_births = now
                await births_tick(service)
        except Exception:
            log.exception("notifications")
        await asyncio.sleep(60)
