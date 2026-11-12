"""The picture in a dozen strokes of a pen: a step of the composition's
analysis, by Sonnet.

The sheet the analysis is drawn on (``imaging.sheet``) is the picture's
masses as stains and, over them, a few strokes of a pen that say what is
where: a figure's back, a head, the horizon, a table's edge. Which strokes
those are cannot be measured: the strongest contours, the outlines of the
masses and the picture's long straight lines were each tried and each gave
strokes that mean nothing (2026-11-11), and the dense pencil sketch before
them looked to the owner "jak kiepski komiks". So a model that sees what
the picture shows draws them. Opus and Sonnet drew alike on three trial
pictures (stand-ins, one run each), so the cheaper one does it.

A sheet without them is the stains alone: the step may fail.
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from .client import SONNET, request
from .daily import MAX_STROKES, Stroke, _dicts, _list, _object, _str, _stroke, image_block

#: The picture goes out this big: a sketch needs no pixel.
SIDE = 1024
#: Fewer strokes than this say nothing of a picture.
MIN_STROKES = 4

SYSTEM = """Rysujesz piórkiem schematyczny szkic jednego obrazu, taki, jaki malarz robi na kartce \
przed analizą kompozycji: kilkanaście pewnych kresek, po których od razu widać, co gdzie jest. \
Barwne plamy akwareli pod szkicem powstają osobno. Ty dajesz samą kreskę.

JAK TO BĘDZIE NARYSOWANE
Każda kreska to łamana przez podane punkty, pociągnięta stalówką jednym ruchem. Aplikacja \
wygładza ją w miękką linię przez kolejne punkty. Gdy podasz "ostra": true, zostawia proste \
odcinki i ostre narożniki (architektura, meble, ramy). Gdy podasz "zamknieta": true, łączy \
ostatni punkt z pierwszym (głowa, owoc, okno, plama o zwartym kształcie).

CO RYSUJESZ
- Najpierw największe formy, które niosą obraz: sylwetka głównej postaci albo bryły (jedna kreska \
na jeden bok sylwetki: ramię i plecy, linia sukni, grzbiet zwierzęcia), głowa jako zamknięty \
owal, linia horyzontu, krawędź stołu, pień, kalenica dachu, brzeg wody.
- Potem to, bez czego układu nie da się odczytać: druga i trzecia postać w największym skrócie, \
najważniejsze otwory i sprzęty, granica światła i cienia, jeśli dzieli obraz.
- 9–16 kresek. Kreska ma 2–10 punktów. Krótsza niż jedna dwunasta dłuższego boku obrazu powstaje \
tylko jako zamknięty mały kształt (głowa, owoc, słońce).

CZEGO NIE RYSUJESZ
Szczegółów: oczu, ust, palców, fałd, liści, cegieł, wzoru tkaniny. Nie cieniujesz, nie \
kreskujesz, nie obrysowujesz każdej plamy koloru. Nie rysujesz ramy obrazu. Jedna forma dostaje \
jedną kreskę, najwyżej dwie.

DOKŁADNOŚĆ
Punkty leżą dokładnie na konturze albo osi formy, w pikselach obrazu, który dostajesz (wymiary w \
danych: OBRAZ), od lewego górnego rogu: x w prawo, y w dół. Na łuku stawiaj punkty gęściej, na \
prostej wystarczą dwa. Dla każdej kreski podaj w "co" nazwę tego, po czym biegnie (2–5 słów).

ODPOWIEDŹ: "szkic": lista kresek, każda: "co", "points" (lista {"x", "y"}), "ostra", "zamknieta"."""

_POINT = _object(x={"type": "number"}, y={"type": "number"})
SCHEMA = _object(
    szkic=_list(
        _object(
            co=_str(),
            points=_list(_POINT),
            ostra={"type": "boolean"},
            zamknieta={"type": "boolean"},
        )
    )
)


def question(img: Image.Image) -> dict[str, Any]:
    """The sketch of the picture (its field alone, as the sheet shows it)."""
    small = img.copy()
    small.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
    w, h = small.size
    text = f"OBRAZ: {w} × {h} px (współrzędne w tych pikselach)"
    return request(
        model=SONNET,
        system=SYSTEM,
        content=[image_block(small), {"type": "text", "text": text}],
        schema=SCHEMA,
        max_tokens=6000,
        effort="low",
    )


def _coord(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")  # left out by ``_stroke``


def strokes(data: dict[str, Any] | None, size: tuple[int, int]) -> list[Stroke] | None:
    """The step's answer as strokes in fractions of the picture it drew (of
    whatever size it was sent at: ``size`` is the picture's proportions),
    or None when it drew too little to be a sketch."""
    if not data:
        return None
    small = Image.new("L", size)
    small.thumbnail((SIDE, SIDE))
    w, h = small.size
    found = []
    for raw in _dicts(data.get("szkic")):
        spots = [(_coord(p.get("x")), _coord(p.get("y"))) for p in _dicts(raw.get("points"))]
        pixels = any(abs(x) > 1.5 or abs(y) > 1.5 for x, y in spots)
        sx, sy = (w, h) if pixels else (1, 1)
        stroke = _stroke(
            {
                "points": [{"x": x / sx, "y": y / sy} for x, y in spots],
                "sharp": raw.get("ostra") is True,
                "closed": raw.get("zamknieta") is True,
            }
        )
        if stroke is not None:
            found.append(stroke)
    return found[:MAX_STROKES] if len(found) >= MIN_STROKES else None
