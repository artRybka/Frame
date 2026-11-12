"""The picture in some twenty strokes of a pen: a step of the composition's
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

On his phone the owner found the dozen strokes of the first pen a little
too few and too loose (Mateusz 2026-11-12 09:47: "Rysowane ołówkiem
'kontury' mogłyby być trochę dokładniejsze, może być ich też trochę
więcej. Gdzieniegdzie mogą też 'szkicować'/kreskować ciemniejsze partie").
So this pen (:data:`ROUND` 2) draws 14 to 22, with more points where a
contour bends, and thinks a little longer over where they lie. The
hatching of the dark parts is not asked of it: it is measured from the
picture (``imaging.sheet.hatching``), so every sheet has it at once. The
sketches drawn before are drawn again at night (``ai.redraw``).

On the next sheets he found the drawing sometimes chaotic (Mateusz
2026-11-12 14:50: "szczegółowość rysunku pozostawia sporo do życzenia. Może
być oczywiście schematyczna, ale teraz nieraz jest chaotyczna. Najlepiej
gdyby rysunek był dokładny tam gdzie dzieło tego wymaga (temat, postać,
istotny fragment) a pominięty lub bardzo ogólny w reszcie dzieła"). On his
phone Turner's ship in a storm was three blobs under long curves swept
across the sky and the sea that lay on nothing, and the rowing boat was not
there at all. Two things were wrong: the pen was asked for "co gdzie jest"
over the whole picture, evenly, and its points lie a little beside what it
means. So this pen (:data:`ROUND` 3) first says what the picture's subject
is and draws that exactly, in most of its strokes, and gives the rest a few
long lines or none (at most :data:`MAX_GENERAL` are kept); it is told what
the analysis points at; it sees the picture larger; and each of its strokes
is then laid on the picture's own edge, a stroke that lies on none left out
(``imaging.trace``).

A sheet without them is the stains alone: the step may fail.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from PIL import Image

from ..imaging import trace
from .client import SONNET, request
from .daily import MAX_STROKES, Stroke, _dicts, _list, _object, _str, _stroke, image_block

#: The picture goes out this big: a small form (a boat, a head, a hand) is
#: drawn only when it is seen.
SIDE = 1568
#: Fewer strokes than this say nothing of a picture.
MIN_STROKES = 4
#: The most strokes kept of what is not the picture's subject.
MAX_GENERAL = 5
#: The most of the analysis's marks named to the pen.
MAX_ABOUT = 8
#: Which pen drew a page's sketch (kept in the page under :data:`PEN_KEY`;
#: 1, the first one, when it says nothing).
ROUND = 3
PEN_KEY = "pen_round"
#: A page whose sketch a pen before this one drew gets it drawn again at
#: night (``ai.redraw``), which costs: the owner said yes to that for the
#: pages of the first pen (Mateusz 2026-11-12 10:38, "Tak, nocą w
#: pakiecie") and for those the second pen had drawn by then (15:23, the
#: same answer), so every page before this pen is drawn again. A pen after
#: this one asks him anew before it raises this.
REDRAWN = 3

SYSTEM = """Rysujesz piórkiem schematyczny szkic jednego obrazu, taki, jaki malarz robi na kartce \
przed analizą kompozycji. Po szkicu ma być od razu widać, co jest tematem obrazu i gdzie leży. \
To synteza, nie rysunek konturowy całego obrazu: temat rysujesz dokładnie, resztę ledwie \
zaznaczasz albo pomijasz. Barwne plamy akwareli pod szkicem powstają osobno, kreskowanie ciemnych \
partii też. Ty dajesz samą kreskę.

NAJPIERW ZDECYDUJ, CO JEST TEMATEM
Temat to to, na co obraz każe patrzeć: postać albo grupa postaci, zwierzę, statek, budowla, \
drzewo, przedmioty martwej natury. W pejzażu bez bohatera to motyw, który go niesie (samotne \
drzewo, most, skała, łódź, droga). Jeśli w danych jest ANALIZA WSKAZUJE, to są miejsca, o których \
mówi analiza kompozycji tego obrazu: należą do tematu albo są istotnym fragmentem, który też \
rysujesz dokładnie. Nazwij temat w "temat" (2–6 słów).

JAK TO BĘDZIE NARYSOWANE
Każda kreska to łamana przez podane punkty, pociągnięta stalówką jednym ruchem. Aplikacja \
wygładza ją w miękką linię przez kolejne punkty. Gdy podasz "ostra": true, zostawia proste \
odcinki i ostre narożniki (architektura, meble, ramy, maszty). Gdy podasz "zamknieta": true, \
łączy ostatni punkt z pierwszym (głowa, owoc, żagiel, okno, plama o zwartym kształcie). \
Serwer dosunie potem każdą kreskę do krawędzi obrazu, która biegnie tuż obok niej, i odrzuci \
kreskę, która nie leży na żadnej krawędzi. Kreska, która tylko „mniej więcej” oddaje kierunek, \
przepadnie albo przyklei się do czegoś przypadkowego.

TEMAT: DOKŁADNIE (10–18 kresek, "temat": true)
- Sylwetka w częściach, każda po swoim prawdziwym konturze: głowa jako zamknięty owal po brzegu \
głowy, linia ramion i pleców, ręka, która niesie gest, bok sukni albo płaszcza, noga. U \
zwierzęcia grzbiet, łeb, nogi. U statku kadłub, każdy maszt, główne żagle jako zamknięte \
kształty. U budowli bryła, dach, wieża, główny otwór. W martwej naturze każdy ważny przedmiot i \
krawędź stołu.
- To, co w temacie dzieli formę i bez czego się jej nie odczyta: granica światła i cienia na \
postaci, brzeg dużej plamy stroju, oparcie krzesła, burta łodzi.
- Mała, ale ważna forma (łódź na fali, twarz, dłoń z przedmiotem, ptak) dostaje swoje kreski tak \
samo jak duża. Nie zastępuj jej kółkiem.
- Kreska ma tu 4–16 punktów: punkt na każdym wyraźnym ugięciu konturu. Zamknięty kształt ma co \
najmniej 6 punktów i obiega formę po jej brzegu, nie jest kółkiem w jej środku. Cienka forma \
(maszt, wiosło, laska, pień) to jedna kreska wzdłuż niej.

RESZTA OBRAZU: OGÓLNIE ALBO WCALE (0–5 kresek, "temat": false)
- Tylko wielkie podziały: horyzont, brzeg wody, linia ściany i podłogi, brzeg wielkiej ciemnej \
albo jasnej partii (ławicy chmur, masywu drzew, zbocza), jeden grzbiet fali, krawędź drogi.
- Każda taka kreska jest długa i prosta w rysunku: 2–6 punktów, po wyraźnej, widocznej krawędzi.
- W spokojnych partiach (niebo, gładka ściana, woda, tło portretu) nie rysujesz nic. Nie \
wypełniasz pustego miejsca kreską po to, żeby coś tam było. Tło portretu zostaje puste.
- Drugiego planu nie rysujesz w szczegółach: dalekich postaci, pojedynczych chmur, fal, drzew, \
okien.

CZEGO NIE RYSUJESZ
Drobiazgów: oczu, ust, palców, fałd, liści, cegieł, wzoru tkaniny, olinowania. Nie cieniujesz i \
nie kreskujesz. Nie rysujesz ramy obrazu. Nie prowadzisz kreski przez kilka form naraz ani w \
poprzek formy: jedna kreska to jeden kontur. Tej samej krawędzi nie rysujesz dwa razy.

DOKŁADNOŚĆ
Punkty leżą dokładnie na konturze formy, w pikselach obrazu, który dostajesz (wymiary w danych: \
OBRAZ), od lewego górnego rogu: x w prawo, y w dół. Zanim podasz kreskę, przejdź ją na obrazie \
punkt po punkcie: każdy ma leżeć na samej krawędzi, po której kreska biegnie (tam, gdzie forma \
styka się z tłem albo z inną formą), nie obok niej, a kreska ma się zaczynać i kończyć tam, \
gdzie forma. Na łuku stawiaj punkty gęsto, na prostej wystarczą dwa. Dla każdej kreski podaj w \
"co" nazwę tego, po czym biegnie (2–5 słów).

KOLEJNOŚĆ
Najpierw kreski tematu, od najważniejszej, potem reszta.

ODPOWIEDŹ: "temat": co jest tematem obrazu; "szkic": lista kresek, każda: "co", "temat", \
"points" (lista {"x", "y"}), "ostra", "zamknieta"."""

_POINT = _object(x={"type": "number"}, y={"type": "number"})
SCHEMA = _object(
    temat=_str(),
    szkic=_list(
        _object(
            co=_str(),
            temat={"type": "boolean"},
            points=_list(_POINT),
            ostra={"type": "boolean"},
            zamknieta={"type": "boolean"},
        )
    ),
)


def question(img: Image.Image, about: Sequence[str] = ()) -> dict[str, Any]:
    """The sketch of the picture (its field alone, as the sheet shows it);
    ``about``: what the analysis's marks are of, so the pen knows what the
    page will speak of."""
    small = img.copy()
    small.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
    w, h = small.size
    text = f"OBRAZ: {w} × {h} px (współrzędne w tych pikselach)"
    named = [t for t in dict.fromkeys(a.strip() for a in about) if t][:MAX_ABOUT]
    if named:
        text += "\nANALIZA WSKAZUJE: " + "; ".join(named)
    return request(
        model=SONNET,
        system=SYSTEM,
        content=[image_block(small), {"type": "text", "text": text}],
        schema=SCHEMA,
        max_tokens=12000,
        effort="medium",
    )


def _coord(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")  # left out by ``_stroke``


def strokes(data: dict[str, Any] | None, img: Image.Image) -> list[Stroke] | None:
    """The step's answer as strokes in fractions of the picture it drew
    (``img``: the same picture, of whatever size), each laid on the
    picture's own edge (``imaging.trace``); the subject's first, a few of
    the rest; or None when it drew too little to be a sketch."""
    if not data:
        return None
    small = Image.new("L", img.size)
    small.thumbnail((SIDE, SIDE))
    w, h = small.size
    subject: list[Stroke] = []
    rest: list[Stroke] = []
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
            (rest if raw.get("temat") is False else subject).append(stroke)
    found = [*subject, *(s.model_copy(update={"rest": True}) for s in rest[:MAX_GENERAL])]
    found = found[:MAX_STROKES]
    if len(found) < MIN_STROKES:
        return None
    laid = [
        on.model_copy(update={"rest": drawn.rest})
        for drawn, on in zip(found, map(_laid, _on_edges(img, found)), strict=True)
        if on is not None
    ]
    # A picture too soft to be measured (a fog, a sfumato) keeps the pen's
    # strokes as it drew them: better loose than none.
    return laid if len(laid) >= MIN_STROKES else found


def _on_edges(img: Image.Image, found: list[Stroke]) -> list[trace.Line | None]:
    lines = [([(p.x, p.y) for p in s.points], s.sharp, s.closed) for s in found]
    try:
        return trace.follow(np.asarray(img.convert("RGB")), lines)
    except Exception:  # the measure fails: the strokes as drawn
        return list(lines)


def _laid(line: trace.Line | None) -> Stroke | None:
    if line is None:
        return None
    points, sharp, closed = line
    return _stroke(
        {"points": [{"x": x, "y": y} for x, y in points], "sharp": sharp, "closed": closed}
    )
