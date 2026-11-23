"""Galeria: works one after another on the whole screen, the app's first tab
(Mateusz 2026-11-23: "Kolejność losowa, ale podyktowana polubieniami i
podobieństwem do polubionych").

Each person's own: their hearts (a guest's too, for their own Galeria), the
works that look like the hearted ones (``Looks.neighbours``), the hearted
artists' other works, and a few of the catalogue's good works for
something new. A person with no hearts yet starts from their Propozycje
dnia and what the household likes. The works given out lately are
remembered for each person, so the next batch brings others.
"""

from __future__ import annotations

import random
import threading
from collections.abc import Callable
from datetime import date

from .library.models import Item, ItemKind, PlaylistRules
from .library.repo import Library
from .library.verdict import Place, against

#: ``gallery_seen:<user id>``: the works last given out, the newest last.
SEEN_KEY = "gallery_seen"
#: How many works given out are not given again.
SEEN_MOST = 400
#: Hearted works whose look-alikes are asked for in one batch.
SEEDS = 6
#: Look-alikes asked for each of them.
NEAR = 12
#: How likely each kind of work is drawn: a look-alike of a hearted work,
#: a hearted artist's other work, a hearted work again, a good work.
WEIGHTS = {"near": 4.0, "artist": 2.0, "heart": 1.0, "good": 1.0}
#: The catalogue's good works kept for a person for the day.
GOOD_POOL = 240
#: Hearted artists whose other works are asked for in one batch.
ARTISTS = 8
#: Works of one artist in a batch at most (a run of one artist's works
#: is no gallery).
SAME_ARTIST = 2

Neighbours = Callable[[str, int], list[str]]

_good: dict[tuple[str, str, int, int], list[str]] = {}
_good_lock = threading.Lock()


def seen_key(user: str) -> str:
    return f"{SEEN_KEY}:{user}"


def _good_works(library: Library, user: str, day: date) -> list[str]:
    """The catalogue's good works in the day's order (one query of the
    whole catalogue, kept for the day)."""
    key = (user, day.isoformat(), id(library), library.catalogue_version)
    with _good_lock:
        found = _good.get(key)
        if found is None:
            _, items = library.query(
                PlaylistRules(kinds=[ItemKind.ARTWORK]),
                sort="good",
                seed=day.toordinal(),
                limit=GOOD_POOL,
                user=user,
                proposing=True,
            )
            found = [i.id for i in items]
            for old in [k for k in _good if k[1:] != key[1:]]:
                del _good[old]
            _good[key] = found
        return list(found)  # the caller draws from it


def _artists_works(library: Library, artists: list[str], user: str, day: date) -> list[str]:
    if not artists:
        return []
    _, items = library.query(
        PlaylistRules(kinds=[ItemKind.ARTWORK], artists=artists),
        sort="good",
        seed=day.toordinal(),
        limit=GOOD_POOL,
        user=user,
        proposing=True,
    )
    return [i.id for i in items]


def next_works(
    library: Library,
    user: str,
    count: int,
    neighbours: Neighbours,
    starters: Callable[[], list[str]] = list,
    day: date | None = None,
    rng: random.Random | None = None,
) -> list[Item]:
    """The next ``count`` works of ``user``'s Galeria, remembered as given
    out. ``starters``: the works to start from without hearts (their
    Propozycje dnia)."""
    day = day or date.today()
    rng = rng or random.Random()
    seen_list: list[str] = list(library.get_state(seen_key(user), []))
    seen = set(seen_list)
    shut = library.hidden().ids | library.hidden(user).ids | library.spare_copies()
    hearts = [i for i in library.favorites(user) if library.get(i) is not None]
    household = sorted(library.household_likes())

    pools: dict[str, list[str]] = {k: [] for k in WEIGHTS}
    if hearts:
        pools["heart"] = list(hearts)
        for seed in rng.sample(hearts, min(SEEDS, len(hearts))):
            pools["near"].extend(neighbours(seed, NEAR))
        artists = sorted({it.artist for i in hearts if (it := library.get(i)) and it.artist})
        some = rng.sample(artists, min(ARTISTS, len(artists)))
        pools["artist"] = _artists_works(library, some, user, day)
    else:
        pools["heart"] = starters() + household
        for seed in rng.sample(household, min(SEEDS, len(household))):
            pools["near"].extend(neighbours(seed, NEAR))
    pools["good"] = _good_works(library, user, day)

    def fits(item_id: str, own: bool) -> Item | None:
        if item_id in seen or item_id in shut:
            return None
        item = library.get(item_id)
        if item is None or item.kind != ItemKind.ARTWORK:
            return None
        if not own and against(item, Place.PROPOSED):
            return None
        return item

    for name in pools:
        rng.shuffle(pools[name])
    out: list[Item] = []
    taken: set[str] = set()
    artists_seen: dict[str, int] = {}
    #: Works passed over for their artist, by pool: drawn after all if
    #: the batch is short of other artists.
    skipped: dict[str, list[str]] = {k: [] for k in WEIGHTS}

    def draw(relax: bool) -> bool:
        live = [k for k in WEIGHTS if pools[k]]
        while live:
            name = rng.choices(live, [WEIGHTS[k] for k in live])[0]
            item_id = pools[name].pop()
            if not pools[name]:
                live.remove(name)
            if item_id in taken:
                continue
            item = fits(item_id, own=name == "heart")
            if item is None:
                continue
            if not relax and artists_seen.get(item.artist, 0) >= SAME_ARTIST:
                skipped[name].append(item_id)
                continue
            taken.add(item_id)
            artists_seen[item.artist] = artists_seen.get(item.artist, 0) + 1
            out.append(item)
            return True
        return False

    while len(out) < count and draw(relax=False):
        pass
    if len(out) < count:
        # Too few artists for two at most each: more of the same then.
        for name, ids in skipped.items():
            pools[name].extend(reversed(ids))
        while len(out) < count and draw(relax=True):
            pass
    if len(out) < count and len(seen_list) > 0:
        # Everything was given out lately: start the round again.
        seen.clear()
        seen_list = []
        pools["good"] = [i for i in _good_works(library, user, day) if i not in taken]
        pools["heart"] = [i for i in hearts if i not in taken]
        rng.shuffle(pools["good"])
        while len(out) < count and draw(relax=True):
            pass
    seen_list = (seen_list + [i.id for i in out])[-SEEN_MOST:]
    library.keep_state(seen_key(user), seen_list)
    return out
