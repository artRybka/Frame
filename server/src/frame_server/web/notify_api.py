"""Notifications on the phone (Ramka → trybik → Konfiguracja → Powiadomienia):
the APNs key, the phones and what each wants, a test. See notifications.py."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ..notifications import KINDS, TEAM_ID, PushDevice, PushError, PushKey, key_id_from
from ..service import FrameService
from .deps import require_token, service

router = APIRouter(
    prefix="/api/notifications", dependencies=[Depends(require_token)], tags=["notifications"]
)
Svc = Annotated[FrameService, Depends(service)]

NO_KEY = "brak klucza APNs: dodaj plik AuthKey_….p8 z konta Apple Developer"
KEY_BYTES = 4096


class Kind(BaseModel):
    key: str
    title: str
    hint: str


class NotificationsView(BaseModel):
    key: PushKey | None
    kinds: list[Kind]
    #: The phone that asked (``?device=``), None until it registers.
    device: PushDevice | None = None
    devices: int = 0


class DeviceUpdate(BaseModel):
    sandbox: bool = False
    kinds: list[str] | None = None  # None: keep (a new phone gets all)
    name: str = ""


class TestRequest(BaseModel):
    device: str


class TestResult(BaseModel):
    ok: bool
    error: str | None = None


def _view(svc: FrameService, device: str | None = None) -> NotificationsView:
    notifier = svc.notifier
    return NotificationsView(
        key=notifier.key(),
        kinds=[Kind(key=k, title=t, hint=h) for k, (t, h) in KINDS.items()],
        device=notifier.device(device) if device else None,
        devices=len(notifier.devices()),
    )


@router.get("", response_model=NotificationsView)
def get_notifications(svc: Svc, device: Annotated[str | None, Query()] = None) -> NotificationsView:
    return _view(svc, device)


@router.put("/devices/{token}", response_model=NotificationsView)
def put_device(token: str, update: DeviceUpdate, svc: Svc) -> NotificationsView:
    """The app's device token (sent on every start, it may change) and the
    kinds this phone wants."""
    try:
        found = svc.notifier.register(
            token, sandbox=update.sandbox, kinds=update.kinds, name=update.name
        )
    except PushError as err:
        raise HTTPException(400, str(err)) from err
    return _view(svc, found.token)


@router.delete("/devices/{token}", response_model=NotificationsView)
def delete_device(token: str, svc: Svc) -> NotificationsView:
    svc.notifier.forget(token)
    return _view(svc)


@router.put("/key", response_model=NotificationsView)
async def put_key(
    svc: Svc,
    file: Annotated[UploadFile, File()],
    key_id: Annotated[str | None, Form()] = None,
    team_id: Annotated[str | None, Form()] = None,
    device: Annotated[str | None, Form()] = None,
) -> NotificationsView:
    """The APNs key (AuthKey_<key id>.p8): its id from the file name unless given."""
    pem = await file.read(KEY_BYTES + 1)
    if len(pem) > KEY_BYTES:
        raise HTTPException(400, "to nie jest klucz APNs (plik AuthKey_….p8)")
    found = key_id or key_id_from(file.filename or "")
    if not found:
        raise HTTPException(400, "podaj identyfikator klucza (10 znaków z nazwy AuthKey_….p8)")
    try:
        svc.notifier.save_key(pem, found, team_id or TEAM_ID)
    except PushError as err:
        raise HTTPException(400, str(err)) from err
    return _view(svc, device)


@router.delete("/key", response_model=NotificationsView)
def delete_key(svc: Svc, device: Annotated[str | None, Query()] = None) -> NotificationsView:
    svc.notifier.delete_key()
    return _view(svc, device)


@router.post("/test", response_model=TestResult)
async def test(request: TestRequest, svc: Svc) -> TestResult:
    """A notification to this phone now; Apple's answer if it fails."""
    notifier = svc.notifier
    if notifier.key() is None:
        raise HTTPException(409, NO_KEY)
    if notifier.device(request.device) is None:
        raise HTTPException(404, "ten telefon nie jest zapisany na serwerze")
    results = await notifier.send(
        "test",
        "Frame",
        "Powiadomienia działają. Tak będą wyglądać wiadomości z ramki.",
        only=request.device,
    )
    sent = results.get(request.device.lower())
    if sent is None:
        return TestResult(ok=False, error="nie wysłano")
    return TestResult(ok=sent.ok, error=None if sent.ok else describe(sent.reason))


def describe(reason: str | None) -> str:
    """Apple's reason, with what to do about the common ones."""
    hints = {
        "InvalidProviderToken": "Apple nie przyjmuje klucza: czy to klucz APNs tego zespołu?",
        "ExpiredProviderToken": "zegar serwera się spieszy lub spóźnia",
        "BadDeviceToken": "token telefonu nie pasuje: otwórz aplikację ponownie",
        "Unregistered": "aplikacja na telefonie wyłączyła powiadomienia",
        "DeviceTokenNotForTopic": "token jest z innej aplikacji",
        "TopicDisallowed": "klucz nie obejmuje aplikacji Frame",
    }
    if reason is None:
        return "nieznany błąd"
    return f"{hints[reason]} ({reason})" if reason in hints else reason
