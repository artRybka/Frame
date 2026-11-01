"""Keys of art sources, entered in the app's Konfiguracja → Źródła dzieł.

Keys and tokens are given in the app, not in frame.env or the add-on
options (Mateusz, 2026-11-01). A key saved in the app wins over one still
in frame.env (Europeana's had one before). The server checks a key with its
service before keeping it, and never sends it back, only its last
characters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from .ai.config import clean_key

if TYPE_CHECKING:
    from .config import Settings
    from .library import Library

STATE_KEY = "source_keys"
PARIS_API = "https://apicollections.parismusees.paris.fr/graphql"
KEY_TAIL = 4


class KeyRejected(Exception):
    """The service says the key is not valid."""


class KeyUnchecked(Exception):
    """The service did not answer, so the key could not be checked."""


def _get(url: str, param: str) -> Callable[[httpx.Client, str], httpx.Response]:
    return lambda http, key: http.get(url, params={param: key})


def _paris(http: httpx.Client, key: str) -> httpx.Response:
    query = (
        '{ nodeQuery(limit: 1, filter: {conditions: [{field: "type", value: "oeuvre"}]})'
        " { count } }"
    )
    return http.post(PARIS_API, json={"query": query}, headers={"auth-token": key})


@dataclass(frozen=True)
class KeyedSource:
    key: str  # the source's key in MUSEUMS
    name: str
    #: Where a free key is made.
    signup: str
    #: What the source brings, and what happens without a key.
    about: str
    #: A cheap request that answers 200 with a good key (401/403 with a bad one).
    ask: Callable[[httpx.Client, str], httpx.Response]


SOURCES: tuple[KeyedSource, ...] = (
    KeyedSource(
        key="si",
        name="Smithsonian",
        signup="https://api.data.gov/signup/",
        about="Muzea sztuki Smithsonian (sztuka amerykańska, portrety, sztuka Azji), "
        "obrazy CC0. Bez klucza to źródło jest wyłączone.",
        ask=_get("https://api.si.edu/openaccess/api/v1.0/search?q=painting&rows=1", "api_key"),
    ),
    KeyedSource(
        key="paris",
        name="Paris Musées",
        signup="https://apicollections.parismusees.paris.fr/user/register",
        about="14 muzeów miasta Paryża (Petit Palais, Carnavalet, Victor Hugo), obrazy CC0. "
        "Token: Mon compte → Auth Tokens. Bez niego to źródło jest wyłączone.",
        ask=_paris,
    ),
    KeyedSource(
        key="europeana",
        name="Europeana",
        signup="https://pro.europeana.eu/page/get-api",
        about="Bez własnego klucza Europeana działa na wspólnym kluczu demo z niższymi limitami.",
        ask=_get("https://api.europeana.eu/record/v2/search.json?query=painting&rows=1", "wskey"),
    ),
)
BY_KEY = {s.key: s for s in SOURCES}


class SourceKeys:
    def __init__(self, settings: Settings, library: Library) -> None:
        self.settings = settings
        self.library = library

    def _saved(self) -> dict[str, str]:
        saved = self.library.get_state(STATE_KEY)
        return dict(saved) if isinstance(saved, dict) else {}

    def _from_env(self, source: str) -> str | None:
        if source == "europeana":
            key = self.settings.europeana_key
            return key if key and key != "api2demo" else None
        return None

    def get(self, source: str) -> str | None:
        """The app's key, else frame.env's."""
        return self._saved().get(source) or self._from_env(source)

    def from_app(self, source: str) -> bool:
        return bool(self._saved().get(source))

    def tail(self, source: str) -> str | None:
        key = self.get(source)
        return key[-KEY_TAIL:] if key else None

    def check(self, source: str, key: str, http: httpx.Client | None = None) -> None:
        """Ask the service with ``key``; raises if it refuses or is silent."""
        spec = BY_KEY[source]
        own = http is None
        client = http or httpx.Client(timeout=15.0, follow_redirects=True)
        try:
            resp = spec.ask(client, key)
        except httpx.HTTPError as err:
            raise KeyUnchecked(f"{spec.name}: {err}") from err
        finally:
            if own:
                client.close()
        if resp.status_code in (401, 403):
            raise KeyRejected(f"{spec.name} did not accept the key")
        if resp.status_code != 200:
            raise KeyUnchecked(f"{spec.name} answered {resp.status_code}")

    def set(self, source: str, key: str | None) -> None:
        """Keep the app's key (None forgets it: frame.env's applies again)."""
        if source not in BY_KEY:
            raise KeyError(source)
        saved = self._saved()
        if key:
            saved[source] = clean_key(key)
        else:
            saved.pop(source, None)
        self.library.set_state(STATE_KEY, saved)
