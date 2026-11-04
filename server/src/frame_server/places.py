"""The place a photo was taken, by name: "Kraków", "Rzym, Włochy".

Photos from shared albums and the camera roll carry their coordinates; the
tiles, the cards and the frame show the town they name (Mateusz,
2026-11-04: variant B). The names come from OpenStreetMap's Nominatim, in
Polish, as its usage policy asks: one request at a time and at most one a
second (``library.hosts.PACE``), our name in the User-Agent, and every
answer kept. Coordinates are rounded to about a kilometre before they are
sent, which keeps the photos' exact spots at home and lets the photos of
one outing share one answer.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import httpx

from .library.models import ItemKind
from .library.museums import client as museum_client

if TYPE_CHECKING:
    from .library import Item, Library

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
#: Answers kept, by rounded coordinates: ``{"50.06,19.94": "Kraków"}``.
STATE_KEY = "places"
#: Decimal places the coordinates keep (two: about a kilometre).
ROUNDING = 2
#: Places looked up in one go, at most (a second each).
AT_ONCE = 200
#: The address parts that name a town, the best first.
LOCALITY = (
    "city",
    "town",
    "village",
    "hamlet",
    "municipality",
    "suburb",
    "county",
    "state",
)
#: Photos from home name only the town; elsewhere the country follows.
HOME_COUNTRY = "pl"


def client() -> httpx.Client:
    """The sources' client: our name in the User-Agent, the hosts' paces."""
    return museum_client()


def key(lat: float, lon: float) -> str:
    return f"{lat:.{ROUNDING}f},{lon:.{ROUNDING}f}"


def name_of(answer: dict[str, Any]) -> str:
    """The town (and, abroad, the country) in a Nominatim answer; ""."""
    address = answer.get("address") or {}
    town = next((str(address[k]) for k in LOCALITY if address.get(k)), "")
    country = str(address.get("country") or "")
    if not town:
        return country
    if country and str(address.get("country_code") or "").lower() != HOME_COUNTRY:
        return f"{town}, {country}"
    return town


def wanted(item: Item) -> bool:
    """A photo with coordinates whose place nobody looked up yet."""
    info = item.photo
    return (
        item.kind == ItemKind.PHOTO
        and info is not None
        and info.latitude is not None
        and info.longitude is not None
        and info.place is None
    )


class Places:
    def __init__(self, library: Library) -> None:
        self.library = library
        self._lock = threading.Lock()

    def _ask(self, http: httpx.Client, lat: float, lon: float) -> str:
        resp = http.get(
            NOMINATIM,
            params={
                "lat": f"{lat:.{ROUNDING}f}",
                "lon": f"{lon:.{ROUNDING}f}",
                "format": "jsonv2",
                "zoom": 14,
                "addressdetails": 1,
                "accept-language": "pl",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return name_of(data) if isinstance(data, dict) else ""

    def fill(self, limit: int = AT_ONCE) -> int:
        """Names the places of photos that have none yet; how many photos
        got one. Does nothing while another fill runs."""
        if not self._lock.acquire(blocking=False):
            return 0
        try:
            return self._fill(limit)
        finally:
            self._lock.release()

    def _fill(self, limit: int) -> int:
        photos = [i for i in self.library.all_items() if wanted(i)]
        if not photos:
            return 0
        known: dict[str, str] = dict(self.library.get_state(STATE_KEY, {}) or {})
        names: dict[str, str] = {}
        asked = 0
        with client() as http:
            for item in photos:
                assert item.photo is not None
                assert item.photo.latitude is not None and item.photo.longitude is not None
                spot = key(item.photo.latitude, item.photo.longitude)
                if spot not in known:
                    if asked == limit:
                        continue
                    try:
                        known[spot] = self._ask(http, item.photo.latitude, item.photo.longitude)
                    except (httpx.HTTPError, ValueError) as err:
                        log.warning("place of %s: %s", spot, err)
                        break  # the rest another time
                    asked += 1
                names[item.id] = known[spot]
        if asked:
            self.library.set_state(STATE_KEY, known)
        with self.library.batch():
            for item_id, name in names.items():
                latest = self.library.get(item_id)
                if latest is None or latest.photo is None:
                    continue
                self.library.update(item_id, photo=latest.photo.model_copy(update={"place": name}))
        if names:
            log.info("places: %d photos named (%d asked)", len(names), asked)
        return len(names)
