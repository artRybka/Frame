"""The picture drawn with a pen: a step of the composition's analysis.

The sheet the analysis is drawn on (``imaging.sheet``) is the picture's
masses as stains and, over them, a drawing of a pen that says what is
where. Which lines those are cannot be measured: the strongest contours,
the outlines of the masses and the picture's long straight lines were each
tried and each gave strokes that mean nothing (2026-11-11), and the dense
pencil sketch before them looked to the owner "jak kiepski komiks". So a
model that sees what the picture shows draws them.

The first pens were Sonnet's dozen, then twenty strokes over the whole
picture. On his phone the owner found them too few and too loose (Mateusz
2026-11-12 09:47), then sometimes chaotic (14:50: "Najlepiej gdyby rysunek
był dokładny tam gdzie dzieło tego wymaga (temat, postać, istotny
fragment) a pominięty lub bardzo ogólny w reszcie dzieła"), then, laid on
the picture's edges, still too general (15:50: "Chciałbym żeby był
bardziej szczegółowy. Dokładny. Rysował dzieło, a nie kilka zaznaczeń i
obłych brył"). A drawing traced from the picture's own contours instead
(1.145.62) was worse: "zbyt chaotyczny, gęsty i bez sensu. On chyba działa
na zasadzie kontrastu? To zła droga. Lepszy był rysunek modelu, ale musi
być dokładniejszy" (17:32), and was withdrawn.

So this pen (:data:`ROUND` 4) is the model's drawing made exact, tried on
real pictures before it was built (Ducreux's yawning self-portrait,
Turner's ships bearing up for anchorage, David's Madame Pastoret):

- Who draws matters, and what it is shown. On the same pictures Sonnet
  gave a dozen rounded lumps whatever it was asked. Fable's lines lie on
  the contours. Opus draws well but reads a place off a large picture
  loosely: on Turner it put the ship a fifth of the picture too high, in
  the sky, at any effort. Shown the picture once more with a grid of
  coordinates over it (:data:`GRID`), it puts everything where it is
  (Turner, Pastoret, Ducreux, van Gogh's Bedroom), and draws a little
  less than Fable (the Bedroom's bed, chairs, table and window, not its
  mirror and towel) for about a third less money: Mateusz 2026-11-12
  18:30, "efekt jest super, tylko troszkę drogo. Opus nie da rady?";
  18:59, "Czy Opus na większym wysiłku albo z lepszym promptem nie da
  rady? To praca warta późniejszej oszczędności."
- It sees the picture as large as a model reads one, names the subject,
  and marks up to :data:`MAX_BOXES` places that need a closer look (a
  head, each hand, a ship, a boat). It draws the subject outside them, form
  by form, and of the rest a few long lines or none.
- Each of those places is then cut from the original, enlarged and drawn
  alone (:func:`close_question`): a model puts a line as exactly as the
  picture it reads is large, so a face drawn from the whole picture is
  three dashes and from its enlargement a face. Opus draws these: a place
  that fills its picture is not misplaced. The whole sketch costs 0.2 to
  0.35 USD (with Fable drawing the whole 0.3 to 0.4, all by Fable 0.5 to
  0.9).
- A stroke along a form's outline is drawn with the whole nib, one inside
  a form (features, fingers, folds) and those of a close-up with less
  (``Stroke.weight``), as a hand presses less on what is small.
- The line is where the model put it. Moving strokes onto the picture's
  edges (the third pen) cut them short wherever the picture is soft (a dark
  coat on a dark ground) and made them tremble where it is rough.

A sheet without them is the stains alone: the step may fail.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .client import FABLE, OPUS, request
from .daily import (
    MAX_STROKE_POINTS,
    MAX_STROKES,
    MODEL_EDGE,
    Box,
    Stroke,
    _dicts,
    _list,
    _object,
    _str,
    _stroke,
    image_block,
    model_size,
)
from .sketch import _font

#: Who draws the whole and says where to look closer, who draws the
#: close-ups, and who draws when one of them will not (a refusal, an answer
#: that cannot be read).
MODEL = OPUS
CLOSE_MODEL = OPUS
SPARE = FABLE
#: Who puts a line where the thing is with no help. The others get the
#: whole picture a second time with a grid of coordinates over it, a line
#: every :data:`GRID` pixels with its number. (More effort did not put
#: Opus's drawing in its place, and with the grid drew no better on the
#: trials for a quarter more money.)
SURE = (FABLE,)
GRID = 200
EFFORT = "medium"
#: The original is read at most this long: what the close-ups are cut from.
SOURCE = 4096
#: The most places drawn again enlarged, how much is cut around each (of
#: its longer side), the least a place's side (of the picture's longer
#: one), and how much of the picture a place may take: more is no closer.
MAX_BOXES = 4
PAD = 0.1
LEAST_SIDE = 1 / 14
MOST_AREA = 0.6
#: A cut is enlarged at most this much: beyond it there is nothing more
#: to see.
ZOOM = 4.0
#: A drawing is a long answer: up to a minute, sometimes more (the
#: client's own patience is two).
PATIENCE = 300.0
#: The whole picture beside a close-up, to say where it is.
WHERE_SIDE = 640
#: Fewer strokes than this say nothing of a picture.
MIN_STROKES = 4
#: The most strokes kept of what is not the picture's subject.
MAX_GENERAL = 5
#: The most of the analysis's marks named to the pen.
MAX_ABOUT = 8
#: How much of the nib a stroke inside a form is drawn with, and one of a
#: close-up (the smallest place and one as long as the picture).
LIGHT = 0.62
CLOSE = (0.55, 0.9)
#: A stroke that keeps this near the picture's sides for most of its way
#: draws the picture's own border.
BORDER = 0.012
#: A piece of a stroke left outside a close-up is drawn when it is this
#: long (of the picture's sides).
PIECE = 0.012
#: Which pen drew a page's sketch (kept in the page under :data:`PEN_KEY`;
#: 1, the first one, when it says nothing).
ROUND = 4
PEN_KEY = "pen_round"
#: A page whose sketch a pen before this one drew gets it drawn again at
#: night (``ai.redraw``), which costs: the owner said yes to that for the
#: pages of the first pen (Mateusz 2026-11-12 10:38, "Tak, nocą w
#: pakiecie") and for those the second pen had drawn by then (15:23, the
#: same answer). The fourth pen costs ten times the third: its pages are
#: drawn again only once he says so (raise this to 4 then).
REDRAWN = 3
#: The close-ups' answers in the pen's answer, in the order of its boxes.
CLOSE_KEY = "zblizenia"

_HOW = """JAK TO BĘDZIE NARYSOWANE
Każda kreska to linia przez podane punkty, pociągnięta stalówką jednym ruchem; aplikacja prowadzi \
ją gładko przez każdy punkt. "ostra": true zostawia proste odcinki i ostre narożniki \
(architektura, meble, maszty, reje). "zamknieta": true łączy ostatni punkt z pierwszym.

DOKŁADNOŚĆ JEST NAJWAŻNIEJSZA
Punkty podajesz w pikselach obrazu, który dostajesz (wymiary w danych: OBRAZ), od lewego górnego \
rogu: x w prawo, y w dół, w polu "p" jako tekst "x,y x,y x,y" (liczby całkowite, punkty \
oddzielone spacją). Każdy punkt leży na samej krawędzi formy, po której kreska biegnie: tam, \
gdzie forma styka się z tłem albo z inną formą. Na łuku stawiaj punkty gęsto (co 30–60 pikseli, \
na ciasnym zakręcie gęściej), tak żeby łamana przez nie nigdzie nie odchodziła od konturu; na \
prostej wystarczą dwa. Kreska zaczyna się i kończy tam, gdzie forma. Jedna kreska to jeden \
kontur: nie prowadź jej przez kilka form ani w poprzek formy. Tej samej krawędzi nie rysuj dwa \
razy. Nie cieniuj i nie kreskuj. Dla każdej kreski podaj w "co" nazwę tego, po czym biegnie (2–4 \
słowa), a w "lekka": false dla obrysu formy (tam, gdzie styka się z tłem albo z inną formą) i \
true dla kreski wewnątrz formy (rysy twarzy, palce, fałdy, podziały, liny): ta będzie cieńsza. \
Nie rysuj brzegu ani ramy samego obrazu."""

SYSTEM = (
    """Rysujesz piórkiem szkic jednego obrazu, taki, jaki dobry rysownik robi z natury na \
kartce przed analizą kompozycji: oszczędny, ale rysujący DZIEŁO. Po szkicu ma być widać, co obraz \
przedstawia, a nie kilka zaznaczeń i obłych brył. Temat rysujesz szczegółowo i dokładnie, resztę \
obrazu ledwie zaznaczasz albo pomijasz. Akwarela pod szkicem i kreskowanie cieni powstają osobno.

1. ZDECYDUJ, CO JEST TEMATEM
Temat to to, na co obraz każe patrzeć: postać albo grupa, zwierzę, statek, budowla, drzewo, \
przedmioty martwej natury; w pejzażu bez bohatera motyw, który go niesie. Jeśli w danych jest \
ANALIZA WSKAZUJE, to są miejsca, o których mówi analiza: należą do tematu. Nazwij temat w "temat".

2. WSKAŻ FRAGMENTY DO POWIĘKSZENIA ("fragmenty": 2–4 prostokąty, x, y, w, h w pikselach)
To, co w temacie złożone albo małe i ważne, zostanie powiększone i narysowane osobno, dokładniej, \
niż da się z całego obrazu: głowa z twarzą, każda dłoń, mała postać albo grupa, statek z żaglami \
i takielunkiem, łódź z ludźmi, zwierzę, przedmiot, który niesie sens. Z całego obrazu takie formy \
wychodzą obłe i zgrubne, więc każda z nich musi trafić do prostokąta. Gdy temat składa się z \
kilku obiektów (okręt i łódź, dwie postacie), każdy obejmij własnym prostokątem. Gdy cały temat \
zajmuje małą część obrazu, obejmij go jednym prostokątem, a jego najważniejszą część osobnym, \
mniejszym. Prostokąt obejmuje formę z niewielkim zapasem i ma bok nie krótszy niż 1/12 dłuższego \
boku obrazu. Wewnątrz tych prostokątów NIE rysujesz nic: kontur, który do prostokąta dochodzi, \
urywasz na jego brzegu.

3. NARYSUJ TEMAT POZA FRAGMENTAMI: SZCZEGÓŁOWO ("temat": true)
Rysuj tak, jak rysuje się studium, forma po formie, każdą po jej prawdziwym konturze, tyloma \
kreskami, ilu forma wymaga (zwykle 15–45):
- Postać: szyja i kołnierz, barki, każda ręka od barku po nadgarstek, brzegi ubioru (klapy, \
mankiet, pas, rąbek) i te fałdy, które pokazują ruch ciała i budowę stroju; nogi i stopy. \
Granica światła i cienia, gdy buduje formę.
- Statek, budowla, mebel, drzewo, zwierzę, przedmioty martwej natury: bryła po obrysie i te \
wewnętrzne podziały, które ją budują (burta, maszty, reje, dach, otwory, gzymsy, krawędź stołu).
Nie zastępuj formy owalem ani kółkiem: zamknięty kształt obiega formę po jej brzegu. Długi kontur \
prowadź jedną kreską (do 40 punktów), nie sklejaj go z kawałków. Nie rysuj zygzakiem i nie \
powtarzaj równoległych kresek jedna przy drugiej: z fałd wybierz te dwie, trzy, które mówią \
najwięcej.

4. RESZTA OBRAZU: OGÓLNIE ALBO WCALE (0–5 kresek, "temat": false)
Tylko wielkie podziały: horyzont, brzeg wody, linia ściany i podłogi, brzeg wielkiej ciemnej albo \
jasnej partii. Każda długa, po widocznej krawędzi. W spokojnych partiach (niebo, gładka ściana, \
tło portretu) nie rysujesz nic.

"""
    + _HOW
    + """

KOLEJNOŚĆ: najpierw kreski tematu, od najważniejszej, potem reszta.
ODPOWIEDŹ: "temat"; "fragmenty": lista {"co", "x", "y", "w", "h"}; "szkic": lista kresek, każda: \
"co", "temat", "lekka", "p", "ostra", "zamknieta"."""
)

CLOSE_SYSTEM = (
    """Dostajesz powiększony FRAGMENT obrazu (nazwa w danych) oraz, dla orientacji, cały obraz \
z zaznaczonym miejscem fragmentu. Rysujesz piórkiem studium tego fragmentu: szczegółowo i \
dokładnie, forma po formie, każdą po jej prawdziwym konturze, tak żeby było widać, co to jest. \
To część szkicu całego obrazu do analizy kompozycji, więc bez cieniowania i bez drobiazgów \
faktury (pojedynczych włosów, splotu tkaniny, cegieł).

CO RYSUJESZ (zwykle 15–40 kresek)
Wszystko, co buduje formę we fragmencie: obrysy, wewnętrzne podziały, rysy twarzy (brwi, oczy \
jako linie powiek, nos, usta, podbródek, ucho), palce, fałdy, liny i reje, burty, wiosła, małe \
sylwetki z głową, tułowiem i ręką. Nie zastępuj formy owalem: zamknięty kształt obiega ją po \
brzegu. Kontur, który wychodzi poza fragment, doprowadź do samego brzegu fragmentu: dalej jest \
już narysowany. Rysuj tylko to, co należy do nazwanego fragmentu i tematu obrazu, tła nie rysuj. \
Nie powtarzaj równoległych kresek jedna przy drugiej.

"""
    + _HOW
    + """

Współrzędne podajesz w pikselach FRAGMENTU (pierwszy obraz).
ODPOWIEDŹ: "szkic": lista kresek, każda: "co", "lekka", "p", "ostra", "zamknieta"."""
)

GRID_SYSTEM = (
    SYSTEM
    + f"""

SIATKA WSPÓŁRZĘDNYCH
Drugi obraz to ten sam obraz z naniesioną siatką co {GRID} pikseli, opisaną liczbami (x u góry, \
pośrodku i u dołu, y po lewej, pośrodku i po prawej). Służy tylko do odczytu położeń: zanim \
postawisz punkt, znajdź na siatce kratkę, w której leży to miejsce, i podaj współrzędne zgodne z \
jej opisem. Sprawdź tak zwłaszcza rogi każdego prostokąta z "fragmenty" oraz początek i koniec \
każdej kreski. Rysujesz to, co widać na pierwszym obrazie; siatki nie rysujesz."""
)

_NUMBER = {"type": "number"}
_LINE = {
    "co": _str(),
    "lekka": {"type": "boolean"},
    "p": _str(),
    "ostra": {"type": "boolean"},
    "zamknieta": {"type": "boolean"},
}
SCHEMA = _object(
    temat=_str(),
    fragmenty=_list(_object(co=_str(), x=_NUMBER, y=_NUMBER, w=_NUMBER, h=_NUMBER)),
    szkic=_list(_object(temat={"type": "boolean"}, **_LINE)),
)
CLOSE_SCHEMA = _object(szkic=_list(_object(**_LINE)))

Ask = Callable[[dict[str, Any]], dict[str, Any] | None]
#: A line as it is put together: its points (fractions of the picture),
#: whether it keeps its corners, whether it closes, how much of the nib.
_Line = tuple[list[tuple[float, float]], bool, bool, float]
_UNASKED: Any = object()


def read_size(width: int, height: int, most: float = ZOOM) -> tuple[int, int]:
    """The size a picture goes to the model at: as large as it reads one
    whole, a small picture enlarged at most ``most`` times."""
    scale = min(most, 2 * MODEL_EDGE / max(width, height, 1))
    return model_size(max(round(width * scale), 1), max(round(height * scale), 1))


def _read(img: Image.Image) -> Image.Image:
    size = read_size(*img.size)
    return img if size == img.size else img.resize(size, Image.Resampling.LANCZOS)


def gridded(img: Image.Image, step: int = GRID) -> Image.Image:
    """The picture with a grid of coordinates over it: a line every
    ``step`` pixels, each with its number at both ends and in the middle,
    for one who reads a place off a picture loosely."""
    w, h = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    canvas = ImageDraw.Draw(layer)
    font = _font(26)
    for x in range(step, w, step):
        canvas.line([(x, 0), (x, h)], fill=(0, 0, 0, 150), width=4)
        canvas.line([(x, 0), (x, h)], fill=(255, 255, 0, 230), width=2)
    for y in range(step, h, step):
        canvas.line([(0, y), (w, y)], fill=(0, 0, 0, 150), width=4)
        canvas.line([(0, y), (w, y)], fill=(255, 255, 0, 230), width=2)

    def label(x: float, y: float, text: str) -> None:
        box = canvas.textbbox((x, y), text, font=font)
        canvas.rectangle((box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2), fill=(0, 0, 0, 210))
        canvas.text((x, y), text, fill=(255, 255, 0, 255), font=font)

    for x in range(step, w, step):
        for y in (4, h // 2 + 5, h - 36):
            label(x + 5, y, str(x))
    for y in range(step, h, step):
        for x in (4, w // 2 + 5, w - 80):
            label(x, y + 4, str(y))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def question(
    img: Image.Image, about: Sequence[str] = (), model: str | None = None
) -> dict[str, Any]:
    """The pen's first question: the picture whole (its field alone, as
    the sheet shows it), for its subject, the places to look at closer and
    the drawing outside them; ``about``: what the analysis's marks are of,
    so the pen knows what the page will speak of."""
    who = model or MODEL
    sure = who in SURE
    seen = _read(img)
    text = f"OBRAZ: {seen.size[0]} × {seen.size[1]} px (współrzędne w tych pikselach)"
    named = [t for t in dict.fromkeys(a.strip() for a in about) if t][:MAX_ABOUT]
    if named:
        text += "\nANALIZA WSKAZUJE: " + "; ".join(named)
    pictures = [image_block(seen)] if sure else [image_block(seen), image_block(gridded(seen))]
    params = request(
        model=who,
        system=SYSTEM if sure else GRID_SYSTEM,
        content=[*pictures, {"type": "text", "text": text}],
        schema=SCHEMA,
        max_tokens=16000,
        effort=EFFORT,
    )
    params["timeout"] = PATIENCE
    return params


def _number(value: Any) -> float | None:
    try:
        found = float(value)
    except (TypeError, ValueError):
        return None
    return found if np.isfinite(found) else None


def boxes(data: dict[str, Any] | None, size: tuple[int, int]) -> list[tuple[str, Box]]:
    """The places the pen asked to see closer, named, as parts of the
    picture (``size``: the picture's): none smaller than a close-up is
    worth, none that is most of the picture."""
    if not data:
        return []
    w, h = read_size(*size)
    least = LEAST_SIDE * max(w, h)
    found: list[tuple[str, Box]] = []
    for raw in _dicts(data.get("fragmenty")):
        x, y = _number(raw.get("x")), _number(raw.get("y"))
        bw, bh = _number(raw.get("w")), _number(raw.get("h"))
        if x is None or y is None or bw is None or bh is None or bw <= 0 or bh <= 0:
            continue
        # (a place too small is widened about its middle, within the picture)
        cx, cy = x + bw / 2, y + bh / 2
        bw, bh = min(max(bw, least), float(w)), min(max(bh, least), float(h))
        x0 = min(max(cx - bw / 2, 0.0), w - bw)
        y0 = min(max(cy - bh / 2, 0.0), h - bh)
        x1, y1 = x0 + bw, y0 + bh
        if (x1 - x0) * (y1 - y0) > MOST_AREA * w * h:
            continue
        box = Box(x=x0 / w, y=y0 / h, w=(x1 - x0) / w, h=(y1 - y0) / h)
        found.append((str(raw.get("co") or "").strip()[:80], box))
        if len(found) == MAX_BOXES:
            break
    return found


def _cut(size: tuple[int, int], box: Box) -> tuple[int, int, int, int]:
    """The pixels of the picture a close-up of ``box`` is cut from: the
    place and a little around it."""
    w, h = size
    pad = PAD * max(box.w * w, box.h * h)
    x0, y0 = max(round(box.x * w - pad), 0), max(round(box.y * h - pad), 0)
    x1 = min(round((box.x + box.w) * w + pad), w)
    y1 = min(round((box.y + box.h) * h + pad), h)
    return x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)


def close_question(
    img: Image.Image, box: Box, name: str, subject: str = "", model: str | None = None
) -> dict[str, Any]:
    """The pen's question about one place: the place cut from the picture
    and enlarged, and the whole picture with the place marked."""
    cut = _cut(img.size, box)
    near = _read(img.crop(cut))
    where = img.copy()
    where.thumbnail((WHERE_SIDE, WHERE_SIDE), Image.Resampling.LANCZOS)
    k = where.size[0] / img.size[0]
    ImageDraw.Draw(where).rectangle(
        [cut[0] * k, cut[1] * k, cut[2] * k, cut[3] * k], outline=(255, 0, 0), width=3
    )
    text = f"FRAGMENT: {name or 'część tematu'}"
    if subject:
        text += f" (temat obrazu: {subject})"
    text += (
        f"\nOBRAZ: {near.size[0]} × {near.size[1]} px "
        "(współrzędne w pikselach fragmentu, pierwszego obrazu)"
    )
    params = request(
        model=model or CLOSE_MODEL,
        system=CLOSE_SYSTEM,
        content=[image_block(near), image_block(where), {"type": "text", "text": text}],
        schema=CLOSE_SCHEMA,
        max_tokens=16000,
        effort=EFFORT,
    )
    params["timeout"] = PATIENCE
    return params


def draw(
    img: Image.Image,
    about: Sequence[str],
    ask: Ask,
    together: Callable[[list[dict[str, Any]]], list[dict[str, Any] | None]] | None = None,
    plan: dict[str, Any] | None = _UNASKED,
) -> dict[str, Any] | None:
    """The pen's whole answer about the picture (:func:`strokes` makes the
    drawing of it): its first answer (``plan`` when it was asked already)
    and, under :data:`CLOSE_KEY`, what it drew of each place it asked to
    see closer. ``ask`` answers one question, ``together`` several that do
    not wait for one another; a question left unanswered is asked once more
    of :data:`SPARE`. None when even the first has no answer."""
    if plan is _UNASKED:
        plan = ask(question(img, about))
    if plan is None:
        plan = ask(question(img, about, SPARE))
    if plan is None:
        return None
    subject = str(plan.get("temat") or "")
    asked = [close_question(img, box, name, subject) for name, box in boxes(plan, img.size)]
    closes = (together(asked) if together else [ask(q) for q in asked]) if asked else []
    for at, (answer, q) in enumerate(zip(closes, asked, strict=True)):
        if answer is None and q["model"] != SPARE:
            closes[at] = ask({**q, "model": SPARE})
    return {**plan, CLOSE_KEY: closes}


def _points(raw: dict[str, Any], size: tuple[int, int]) -> list[tuple[float, float]]:
    """A stroke's points as fractions of the picture it was drawn on."""
    spots: list[tuple[float, float]] = []
    for pair in str(raw.get("p") or "").replace(";", " ").split():
        x, _, y = pair.partition(",")
        px, py = _number(x), _number(y)
        if px is not None and py is not None:
            spots.append((px / size[0], py / size[1]))
    return spots


def _border(points: list[tuple[float, float]]) -> bool:
    """Whether the stroke draws the picture's own border: most of its way
    it keeps to one of the picture's sides (a horizon from side to side
    only touches them)."""
    p = np.array(points)
    sides = np.stack(
        [p[:, 0] < BORDER, p[:, 0] > 1 - BORDER, p[:, 1] < BORDER, p[:, 1] > 1 - BORDER]
    )
    along = (sides[:, :-1] & sides[:, 1:]).any(axis=0)
    length = np.hypot(*np.diff(p, axis=0).T)
    return bool(length.sum() > 0 and length[along].sum() > 0.6 * length.sum())


def _lines(data: Any, size: tuple[int, int], nib: float = 1.0) -> tuple[list[_Line], list[_Line]]:
    """An answer's strokes, those of the subject and the others, on the
    picture it drew (``size``: as it was sent)."""
    subject: list[_Line] = []
    rest: list[_Line] = []
    for raw in _dicts(data.get("szkic") if isinstance(data, dict) else None):
        spots = _points(raw, size)
        if len(spots) < 2 or _border(spots):
            continue
        weight = nib * (LIGHT if raw.get("lekka") is True else 1.0)
        line = (spots, raw.get("ostra") is True, raw.get("zamknieta") is True, weight)
        (rest if raw.get("temat") is False else subject).append(line)
    return subject, rest


def _parts(line: _Line, areas: Sequence[Box], inside: bool = False) -> list[_Line]:
    """What of the stroke lies outside every one of ``areas`` (or, with
    ``inside``, within them), piece by piece: a stroke that crosses a
    place's side is cut there."""
    points, sharp, closed, weight = line
    if not areas:
        return [line]
    ring = np.array([*points, points[0]] if closed else points, np.float64)
    along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(ring, axis=0).T))])
    if along[-1] <= 0:
        return []
    steps = np.unique(
        np.concatenate([np.linspace(0, along[-1], int(along[-1] / 0.002) + 2), along])
    )
    fine = np.stack([np.interp(steps, along, ring[:, 0]), np.interp(steps, along, ring[:, 1])], 1)
    within = np.zeros(len(fine), bool)
    for a in areas:
        within |= (
            (fine[:, 0] >= a.x)
            & (fine[:, 0] <= a.x + a.w)
            & (fine[:, 1] >= a.y)
            & (fine[:, 1] <= a.y + a.h)
        )
    keep = within if inside else ~within
    if keep.all():
        return [line]
    given = np.isin(steps, along)
    found: list[_Line] = []
    start: int | None = None
    for at in range(len(fine) + 1):
        on = at < len(fine) and bool(keep[at])
        if on and start is None:
            start = at
        if not on and start is not None:
            if steps[at - 1] - steps[start] >= PIECE:
                chosen = [start, *[i for i in range(start + 1, at - 1) if given[i]], at - 1]
                piece = [(float(fine[i, 0]), float(fine[i, 1])) for i in chosen]
                found.append((piece, sharp, False, weight))
            start = None
    return found


def _nib(box: Box, size: tuple[int, int]) -> float:
    """How much of the nib a close-up's strokes are drawn with: less, the
    smaller the place."""
    long = max(box.w * size[0], box.h * size[1]) / max(size)
    return float(np.clip(0.5 + long, *CLOSE))


def strokes(data: dict[str, Any] | None, img: Image.Image) -> list[Stroke] | None:
    """The pen's answer (:func:`draw`) as strokes in fractions of the
    picture it drew (``img``: the same picture): the subject's first, then
    each place seen closer (the larger first), then a few of the rest. The
    closer look wins: the whole gives way to every place drawn closer, a
    place to the smaller ones in it. None when it drew too little to be a
    sketch."""
    if not data:
        return None
    subject, rest = _lines(data, read_size(*img.size))
    places = boxes(data, img.size)
    answers = data.get(CLOSE_KEY)
    answers = answers if isinstance(answers, list) else []
    closer: list[tuple[Box, list[_Line]]] = []
    for at, (_, box) in enumerate(places):
        cut = _cut(img.size, box)
        cw, ch = cut[2] - cut[0], cut[3] - cut[1]
        near, others = _lines(
            answers[at] if at < len(answers) else None, read_size(cw, ch), _nib(box, img.size)
        )
        if not near and not others:
            continue  # not drawn closer: what the whole has of it stays
        on_whole = [
            (
                [
                    ((cut[0] + x * cw) / img.size[0], (cut[1] + y * ch) / img.size[1])
                    for x, y in points
                ],
                sharp,
                closed,
                weight,
            )
            for points, sharp, closed, weight in [*near, *others]
        ]
        closer.append((box, on_whole))
    closer.sort(key=lambda found: -found[0].w * found[0].h)
    drawn = [found[0] for found in closer]
    lines = [piece for line in subject for piece in _parts(line, drawn)]
    for at, (box, near) in enumerate(closer):
        for line in near:
            for own in _parts(line, [box], inside=True):
                lines += _parts(own, drawn[at + 1 :])
    general = [piece for line in rest for piece in _parts(line, drawn)]
    lines += general[:MAX_GENERAL]
    found = [s for s in map(_laid, lines[:MAX_STROKES]) if s is not None]
    return found if len(found) >= MIN_STROKES else None


def _laid(line: _Line) -> Stroke | None:
    points, sharp, closed, weight = line
    if len(points) > MAX_STROKE_POINTS:  # evenly fewer: the ends stay
        chosen = np.unique(np.linspace(0, len(points) - 1, MAX_STROKE_POINTS).round().astype(int))
        points = [points[i] for i in chosen]
    return _stroke(
        {
            "points": [{"x": round(x, 4), "y": round(y, 4)} for x, y in points],
            "sharp": sharp,
            "closed": closed,
            "weight": round(weight, 2),
        }
    )
