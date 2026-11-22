"""Barwy: works found by their colours (Mateusz 2026-11-21 23:05: a third
switch beside Treść and Forma in "Podobne do", "nie na zasadzie odcisku,
tylko przeliczenia (jak do paska koloru) i wyszukania dzieł z najbliższą
paletą", off at first; 23:08 "Liczenie koloru zdjęcia - róbmy na iPhone";
23:42 "Ok. Wdrażamy.").

A work's palette is its bar (``Item.colors``): a painting's tonal masses
and its accents (``tonal.bar``, an accent counted by ``amount``, what there
is of it, not by its place on the bar), another work's dominant colours
and accents (``colors.analyse``). A photograph's palette is
:func:`of_picture`, which the phone makes the same way
(``ios/…/PhoneLook.swift`` ``PhonePalette``, held to this by
``PhonePaletteTests``) and sends with its numbers.

Two palettes are as far apart as the least colour has to be moved to make
one of the other (the earth mover's distance, approximated by Sinkhorn),
in OKLab with colour (a, b) counted twice as lightness, as the bar's own
colours are told apart (``colors._distance``). On the sketches of
2026-11-21 (``/mnt/project-files/kolor-szukaj/``) the paper of drawings and
the dark grounds of paintings drew the rest: so colours count by how
coloured they are too (:data:`EMPHASIS`), and a painting is compared with
paintings, a work on paper with works on paper (``colors.painting``; a
photograph with paintings).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from frame_server.imaging.color import linear_to_oklab, u8_to_linear
from frame_server.library import colors as C
from frame_server.library import tonal
from frame_server.library.models import ColorSwatch, Item, ItemKind

#: The most colours of a palette.
K = 8
#: A colour counts ``1 + EMPHASIS`` times as much once it is
#: :data:`CHROMA_FULL` coloured (OKLab chroma), as much as its share when
#: grey: a beige paper and a dark ground no longer outweigh a blue and a red.
EMPHASIS = 2.0
CHROMA_FULL = 0.10
#: Sinkhorn's softness and its steps.
SOFT = 0.03
STEPS = 60
#: The works looked at closely: those nearest by :func:`summary`.
AMONG = 4000
#: How far a work's palette may be for "Barwy" alone, and beside "Treść" or
#: "Forma" (looser: the shape has chosen already), ``STEP`` further for
#: each step of a list scrolled to its end. Set on the sketches of
#: 2026-11-21 (the sixth nearest of four works at 0.038-0.049 alone,
#: 0.071-0.075 among the same subject); to be set again on his whole
#: catalogue once the new bars are counted.
ALONE = 0.06
BESIDE = 0.09
STEP = 0.01
LEAST = 8
MOST = 1000
#: The catalogue's palettes are read again at most this often.
AGAIN = 600.0
#: A photograph's own picture, as ``colors._grid``: its longer side.
GRID = 128
#: Its colours: k-means on (L, 2a, 2b), as ``tonal.clusters``, from its
#: pixels taken evenly from the darkest to the lightest (no chance: the
#: phone gets the same), ``ROUNDS`` rounds.
CLUSTERS = tonal.CLUSTERS
ROUNDS = 25


def _weights(colours: np.ndarray, shares: np.ndarray) -> np.ndarray:
    chroma = np.hypot(colours[:, 1], colours[:, 2])
    w = np.maximum(shares, 1e-4) * (1 + EMPHASIS * np.minimum(chroma / CHROMA_FULL, 1.0))
    return np.asarray(w / w.sum(), dtype=np.float32)


def palette(
    colours: Sequence[Sequence[float]] | np.ndarray, shares: Sequence[float] | np.ndarray
) -> np.ndarray:
    """A palette: at most :data:`K` colours (OKLab), the largest, each with
    its weight (its share, by how coloured it is, summing to 1), as rows
    (L, a, b, weight)."""
    c = np.asarray(colours, dtype=np.float32).reshape(-1, 3)
    s = np.asarray(shares, dtype=np.float32).reshape(-1)
    order = np.argsort(-s, kind="stable")[:K]
    c, s = c[order], s[order]
    out = np.zeros((len(c), 4), dtype=np.float32)
    out[:, :3] = c
    out[:, 3] = _weights(c, s)
    return out


def of_swatches(swatches: Sequence[ColorSwatch]) -> np.ndarray | None:
    """A work's palette from its bar; None without one."""
    if not swatches:
        return None
    colours = np.asarray([C._lab(s.hex) for s in swatches])
    shares = [s.amount if s.amount is not None else s.weight for s in swatches]
    return palette(colours, shares)


def _clusters(fine: np.ndarray) -> list[tuple[np.ndarray, float]]:
    """``tonal.clusters`` with its centres taken evenly from the darkest
    pixel to the lightest, as the phone can take them too."""
    weighted = (fine * np.array([1.0, 2.0, 2.0], dtype=np.float32)).astype(np.float32)
    k = min(CLUSTERS, len(weighted))
    order = np.argsort(weighted[:, 0], kind="stable")
    centres = weighted[order[np.linspace(0, len(weighted) - 1, k).astype(int)]].copy()
    owner = np.zeros(len(weighted), dtype=int)
    for _ in range(ROUNDS):
        d = (centres**2).sum(1)[None] - 2 * weighted @ centres.T
        owner = np.asarray(np.argmin(d, 1))
        for j in range(k):
            members = weighted[owner == j]
            if len(members):
                centres[j] = members.mean(0)
    out = []
    for j in range(k):
        pixels = fine[owner == j]
        if not len(pixels):
            continue
        chroma = np.hypot(pixels[:, 1], pixels[:, 2])
        core = pixels[chroma >= np.median(chroma)].mean(0)
        core[0] = pixels[:, 0].mean()
        out.append((core, len(pixels) / len(fine)))
    return out


def colours_of(grid: np.ndarray) -> np.ndarray:
    """A photograph's colours from its OKLab picture (:func:`picture`): its
    masses (``tonal.masses``) from the darkest, then its small colours
    that no mass is (``tonal.APART`` off each, as the bar's accents), each
    with its share, as rows (L, a, b, share): what the phone sends."""
    fine = np.asarray(grid, dtype=np.float32).reshape(-1, 3)
    found = _clusters(fine)
    mains = tonal.masses(found)
    small = [
        (c, w)
        for c, w in found
        if w < tonal.BAND and min(C._distance(c, m) for m, _ in mains) >= tonal.APART
    ]
    return np.asarray([[*c, w] for c, w in [*mains, *small]], dtype=np.float32)


def of_grid(grid: np.ndarray) -> np.ndarray:
    """A photograph's palette from its OKLab picture."""
    rows = colours_of(grid)
    return palette(rows[:, :3], rows[:, 3])


def picture(rgb: np.ndarray) -> np.ndarray:
    """An 8-bit sRGB picture (already no longer than :data:`GRID`) in OKLab."""
    return np.asarray(linear_to_oklab(u8_to_linear(np.asarray(rgb, dtype=np.uint8))))


def of_picture(img: object) -> np.ndarray:
    """A photograph's palette (``PIL.Image``), as ``colors._grid`` reads it."""
    from PIL import Image

    assert isinstance(img, Image.Image)
    return of_grid(linear_to_oklab(C._grid(img, GRID)))


def distances(asked: np.ndarray, colours: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """How far ``asked`` (rows L, a, b, weight) lies from each palette
    (``colours`` (N, K, 3), ``weights`` (N, K), a missing colour weighing
    0): Sinkhorn's earth mover's distance."""
    a = asked[:, 3].astype(np.float64)
    pa = asked[:, :3].astype(np.float64)
    d = pa[None, :, None, :] - colours[:, None, :, :].astype(np.float64)
    cost = np.sqrt(d[..., 0] ** 2 + 4 * (d[..., 1] ** 2 + d[..., 2] ** 2))
    kern = np.exp(-cost / SOFT)
    w = weights.astype(np.float64)
    v = np.ones_like(w)
    u = np.ones((len(colours), len(a)))
    for _ in range(STEPS):
        u = a[None, :] / np.maximum(np.einsum("nij,nj->ni", kern, v), 1e-300)
        v = w / np.maximum(np.einsum("nij,ni->nj", kern, u), 1e-300)
    plan = u[:, :, None] * kern * v[:, None, :]
    return np.asarray((plan * cost).sum((1, 2)))


def summary(rows: np.ndarray) -> np.ndarray:
    """A palette in nine numbers, to find the works worth comparing: its
    colour where a fifth, half and four fifths of it lie from the darkest
    (a and b counted twice)."""
    order = np.argsort(rows[:, 0], kind="stable")
    r = rows[order]
    edge = np.cumsum(r[:, 3]) - r[:, 3] / 2
    out = []
    for q in (0.2, 0.5, 0.8):
        i = int(np.argmin(np.abs(edge - q)))
        out += [float(r[i, 0]), 2 * float(r[i, 1]), 2 * float(r[i, 2])]
    return np.asarray(out, dtype=np.float32)


@dataclass
class _Index:
    ids: list[str]
    at: dict[str, int]
    colours: np.ndarray  # (N, K, 3)
    weights: np.ndarray  # (N, K)
    summaries: np.ndarray  # (N, 9)
    painted: np.ndarray  # (N,) bool
    stamp: object
    made: float


class Palettes:
    """The catalogue's palettes, read from its works' bars when asked and
    again when the catalogue has changed (at most every :data:`AGAIN`)."""

    def __init__(self, items: Callable[[], list[Item]], stamp: Callable[[], object]) -> None:
        self._items = items
        self._stamp = stamp
        self._index: _Index | None = None
        self._lock = threading.Lock()

    def _get(self) -> _Index:
        with self._lock:
            now = time.monotonic()
            stamp = self._stamp()
            index = self._index
            if index is None or (index.stamp != stamp and now - index.made >= AGAIN):
                index = self._index = self._make(stamp, now)
            return index

    def _make(self, stamp: object, now: float) -> _Index:
        ids: list[str] = []
        rows: list[np.ndarray] = []
        painted: list[bool] = []
        for item in self._items():
            if item.kind != ItemKind.ARTWORK or not item.colors:
                continue
            p = of_swatches(item.colors)
            if p is None:
                continue
            ids.append(item.id)
            rows.append(p)
            painted.append(C.painting(item.medium, item.classification))
        colours = np.zeros((len(rows), K, 3), dtype=np.float32)
        weights = np.zeros((len(rows), K), dtype=np.float32)
        summaries = np.zeros((len(rows), 9), dtype=np.float32)
        for n, p in enumerate(rows):
            colours[n, : len(p)] = p[:, :3]
            weights[n, : len(p)] = p[:, 3]
            summaries[n] = summary(p)
        return _Index(
            ids,
            {i: n for n, i in enumerate(ids)},
            colours,
            weights,
            summaries,
            np.asarray(painted, dtype=bool),
            stamp,
            now,
        )

    def of(self, item_id: str) -> tuple[np.ndarray, bool] | None:
        """A work's palette and whether it is painted, or None."""
        index = self._get()
        n = index.at.get(item_id)
        if n is None:
            return None
        keep = index.weights[n] > 0
        rows = np.concatenate([index.colours[n][keep], index.weights[n][keep, None]], 1)
        return rows, bool(index.painted[n])

    def near(self, asked: np.ndarray, painted: bool, count: int = MOST) -> list[tuple[str, float]]:
        """The works of ``asked``'s kind (painted or not) whose palettes lie
        nearest it, nearest first, with their distances."""
        index = self._get()
        same = np.flatnonzero(index.painted == painted)
        if not len(same):
            return []
        gap = ((index.summaries[same] - summary(asked)[None]) ** 2).sum(1)
        if len(same) > AMONG:
            same = same[np.argpartition(gap, AMONG)[:AMONG]]
        d = distances(asked, index.colours[same], index.weights[same])
        order = np.argsort(d, kind="stable")[:count]
        return [(index.ids[same[i]], float(d[i])) for i in order]

    def ranked(self, asked: np.ndarray, ids: Sequence[str]) -> list[tuple[str, float]]:
        """``ids`` that have palettes, nearest ``asked`` first."""
        index = self._get()
        at = [index.at[i] for i in ids if i in index.at]
        if not at:
            return []
        d = distances(asked, index.colours[at], index.weights[at])
        order = np.argsort(d, kind="stable")
        return [(index.ids[at[i]], float(d[i])) for i in order]


def enough(near: list[tuple[str, float]], floor: float) -> list[str]:
    """Of ``near`` (nearest first), those within ``floor``, though
    :data:`LEAST` however far, :data:`MOST` at most."""
    within = sum(1 for _, d in near if d <= floor)
    return [i for i, _ in near[: min(max(within, LEAST), MOST)]]


def floor(beside: bool, further: int = 0) -> float:
    """How far a palette may be: alone or beside the shape, ``further``
    steps on."""
    return (BESIDE if beside else ALONE) + STEP * min(max(further, 0), 3)
