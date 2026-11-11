"""What the app's requests are for, as the museums' requests they cause are
counted in Konfiguracja → Diagnostyka (Mateusz 2026-11-07: "kto pytał").

:class:`Purposes` marks every request of the app and of the panel: the
museum requests it sends are counted under its purpose (:func:`purpose_of`)
and never wait for the quiet after a start (:meth:`.HostGuard.calm`). The
server's own work in the background marks itself where it starts
(:func:`.hosts.asking_for`).
"""

from __future__ import annotations

from typing import Any

from ..library.hosts import asking_for

#: Path beginnings and what they are for, the first that fits.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("/panel/", "ramka"),
    ("/api/themes", "Odkrywaj"),
    ("/api/suggestions", "Odkrywaj"),
    ("/api/daily", "Odkrywaj"),
    ("/api/discover/", "Szukaj"),
    ("/api/terms", "Szukaj"),
    ("/api/vocabulary", "Szukaj"),
    ("/api/museums", "Szukaj"),
    ("/api/study", "studium"),
    ("/api/studies", "studium"),
    ("/api/playlists", "playlisty"),
    ("/api/library/", "karta dzieła"),
)


def purpose_of(path: str) -> str | None:
    """What a request to ``path`` is for; None for the rest of the app."""
    if path.startswith("/api/library/items/"):
        if path.endswith("/thumb"):
            return "miniatury"
        if path.endswith("/copies") or path.endswith("/copy") or path.endswith("/sharpen"):
            return "kopie"
    for prefix, why in _PREFIXES:
        if path.startswith(prefix):
            return why
    return None


class Purposes:
    """ASGI middleware: the app's and the panel's requests marked as theirs."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not path.startswith(("/api/", "/panel/")):
            await self.app(scope, receive, send)
            return
        with asking_for(purpose_of(path) or "aplikacja", app=True):
            await self.app(scope, receive, send)
