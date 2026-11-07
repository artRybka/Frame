"""The grid under a composition, chosen by the server.

A model asked to fit the golden section or the thirds finds one in nearly
every picture: something always lies near some line. So the analysis
(``ai.composition``) names only the places the picture rests on (its
:class:`~.daily.Key` points: the dominant, a face, the horizon, an upright
edge), and the grid is measured here: the places are first moved onto the
picture's own lines found in code (``ai.lines``) when one runs within
:data:`SNAP`, strong boundaries in the middle of the picture that no place
names count as well, and a grid is kept only when the main place and one
more lie on its lines, or three do (:func:`pick`). What lies on it goes to
the writer of the text (``ai.prose``) as a fact; it no longer gets a
sentence of its own (Haiku's, put in after the first one: Mateusz
2026-11-07).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .daily import Key
from .lines import Edge, Found
from .sketch import CUTS, NEAR_LINE, ON_LINE

#: A place counting on one side moves onto a line of the picture this near.
SNAP = 0.03
#: A line of the picture's run may fall short of the place by this much.
SNAP_REACH = 0.15
#: Where a grid line can lie at all (every grid's lines are within it):
#: only boundaries here count by themselves.
BAND = (0.25, 0.75)
#: A boundary counting by itself runs at least this share of the side…
FREE_RUN = 0.35
#: …and at most this many of them per axis.
FREE_PER_AXIS = 2
#: The grids tried, the simpler first (it wins a tie). "3x2" and "2x3"
#: matched pictures by chance too often in the trial (Mateusz 2026-11-03).
TRIED = ("halves", "thirds", "golden")
NAMES = {
    "golden": "złoty podział",
    "thirds": "trójpodział (3×3)",
    "halves": "połowy (2×2)",
    "3x2": "trójpodział w poziomie, połowy w pionie (3×2)",
    "2x3": "połowy w poziomie, trójpodział w pionie (2×3)",
}


@dataclass
class Held:
    """A place the grid is measured by: a key point of the analysis, maybe
    moved onto a line of the picture (``edge``, ``was`` its place before),
    or a line of the picture that no point names (``free``)."""

    key: Key
    edge: Edge | None = None
    free: bool = False
    was: float | None = None


@dataclass
class Choice:
    grid: str
    held: list[Held] = field(default_factory=list)

    def kept(self) -> list[Key]:
        """What the take keeps of it (:attr:`View.keys`)."""
        return [h.key for h in self.held]


def snap(keys: list[Key], edges: list[Edge]) -> list[Held]:
    """The key points, each counting on one side moved onto the nearest line
    of the picture of that side within :data:`SNAP` that runs past it."""
    held = []
    for key in keys:
        found = Held(key=key)
        if key.axis in ("x", "y"):
            here, along = (key.x, key.y) if key.axis == "x" else (key.y, key.x)
            near = [
                e
                for e in edges
                if e.axis == key.axis
                and abs(e.pos - here) <= SNAP
                and e.start - SNAP_REACH <= along <= e.end + SNAP_REACH
            ]
            if near:
                edge = min(near, key=lambda e: abs(e.pos - here))
                moved = {key.axis: edge.pos}
                found = Held(key=key.model_copy(update=moved), edge=edge, was=here)
        held.append(found)
    return held


def free(held: list[Held], edges: list[Edge]) -> list[Held]:
    """The picture's long boundaries in :data:`BAND` that no point lies on."""
    used = {h.edge.name for h in held if h.edge is not None}
    kept: dict[str, list[Held]] = {}
    for e in edges:
        if e.name in used or not BAND[0] <= e.pos <= BAND[1]:
            continue
        if "granica" not in e.kind or e.run() < FREE_RUN:
            continue
        key = Key(
            x=e.pos if e.axis == "x" else 0.5,
            y=e.pos if e.axis == "y" else 0.5,
            title=f"linia w obrazie: {e.kind}, {e.side()}",
            axis=e.axis,
        )
        kept.setdefault(e.axis, []).append(Held(key=key, edge=e, free=True))
    return [h for axis in kept.values() for h in axis[:FREE_PER_AXIS]]


def hits(key: Key, grid: str) -> list[tuple[str, float, float]]:
    """How far the place lies from the grid's nearest line on each side
    that counts: (side, distance, the line)."""
    across, down = CUTS[grid]
    found = []
    if "x" in key.axis:
        d, cut = min((abs(key.x - c), c) for c in across)
        found.append(("x", d, cut))
    if "y" in key.axis:
        d, cut = min((abs(key.y - c), c) for c in down)
        found.append(("y", d, cut))
    return found


def score(held: list[Held], grid: str) -> tuple[int, int, bool]:
    """The grid's points (a main place counts twice, on a line twice as
    much as near it), how many lie on its lines, and whether a main one
    does (a key point on a line of the picture counts as main)."""
    points, on, main_on = 0, 0, False
    for h in held:
        weight = 2 if h.key.main else 1
        for _, d, _ in hits(h.key, grid):
            if d <= ON_LINE:
                points += 2 * weight
                on += 1
                main_on |= weight == 2 or (h.edge is not None and not h.free)
            elif d <= NEAR_LINE:
                points += weight
    return points, on, main_on


def pick(held: list[Held], tried: tuple[str, ...] = TRIED) -> str:
    """The grid most of it lies on, when the main place and one more lie on
    its lines or three do; "none" otherwise."""
    best: tuple[str, int] | None = None
    for grid in tried:
        points, on, main_on = score(held, grid)
        if ((main_on and on >= 2) or on >= 3) and (best is None or points > best[1]):
            best = (grid, points)
    return best[0] if best else "none"


def choose(keys: list[Key], found: Found) -> Choice:
    """The grid under a take: its key points snapped to the picture's lines
    and the lines no point names."""
    held = snap(keys, found.edges)
    held += free(held, found.edges)
    return Choice(grid=pick(held), held=held)
