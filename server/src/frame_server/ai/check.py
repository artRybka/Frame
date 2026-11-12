"""The composition checked over its own marks drawn on the picture.

A model that analyses a work's composition points at things by eye: a
loop a little beside a face, a horizon a few pixels off, a triangle that
was meant more than seen. So the take it drew (``ai.composition``) is drawn
on the picture (``ai.sketch``), with the places it named as the ones it
rests on, and shown to Haiku with what each point was meant to lie on and
what the server measured: it says of every mark and place whether it hits,
moves what missed, leaves out what is not there and mends a sentence about
what it left out. It no longer judges the analysis itself (Opus did, at
many times the cost; Mateusz 2026-11-04, after a blind trial). A take whose
check fails stays as it was.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .client import HAIKU, request
from .daily import (
    TAKE,
    TEXT_CHARS,
    Key,
    Mark,
    Spot,
    View,
    _dicts,
    _key,
    _list,
    _mark,
    _object,
    _str,
    _text,
    _view,
    image_block,
    takes,
)
from .sketch import draw, draw_keys, measures

if TYPE_CHECKING:
    from PIL import Image

#: The pictures go out this big: one clean and one with the take drawn,
#: smaller than the analysis's, still enough to see where a mark lies.
CHECK_SIDE = 1568
VERDICTS = ("ok", "move", "drop")

SYSTEM = """Sprawdzasz, czy ślady narysowane na obrazie trafiają tam, gdzie mówi ich opis. Nie \
oceniasz pomysłu na kompozycję, tylko celność i uczciwość śladów.

Dostajesz: obraz bez śladów, ten sam obraz z narysowanymi śladami (różowe linie, numer śladu w \
białym kółku przy jego początku; żółte kółka z numerem P1, P2… to punkty kluczowe), a potem listę \
śladów: kształt, tytuł, punkty w pikselach (x w prawo, y w dół od lewego górnego rogu) i przy \
każdym punkcie nazwa miejsca, na którym miał leżeć ("na"), a po "po" to, po czym cały ślad \
biegnie albo co obejmuje, listę punktów kluczowych (tak samo: piksele i nazwa miejsca) oraz \
pomiary serwera. "loop" to owal wpisany w ramkę, której lewy górny i prawy dolny róg podają jego \
dwa punkty. "echo" to małe kółka w podanych miejscach, połączone przerywaną linią: miejsca, w \
których wraca ten sam kolor albo forma.

Dla każdego śladu po kolei:
1. Znajdź na obrazie bez śladów każde nazwane miejsce. Czy punkt leży na nim? Chybienie to więcej \
niż szerokość tej formy albo ok. 3% boku obrazu.
2. Werdykt:
   - "ok": wszystkie punkty trafiają (drobne różnice zostaw).
   - "move": któryś punkt chybia, a miejsce istnieje; podaj WSZYSTKIE punkty śladu, poprawione \
tam, gdzie chybiały, resztę bez zmian.
   - "drop": nazwanego miejsca nie ma, linia biegnie przez puste pole, "rytm" to przypadkowe \
przedmioty lub mniej niż trzy formy, spirala przez puste niebo, "echo" łączy miejsca o różnych \
kolorach albo drobiazgi, których nie widać od razu, albo ślad dubluje inny ślad.
   Pętla ("loop") ma obejmować samą rzecz nazwaną w "po": gdy ramka jest od niej wyraźnie większa \
(z którejś strony zostaje zapas większy niż jedna piąta wymiaru rzeczy albo ramka bierze \
sąsiednią formę), to "move" z rogami ramki ciasno wokół rzeczy.
3. "why": najwyżej 12 słów.

Punkty kluczowe: każdy sprawdzasz jak ślad. "ok", gdy leży na nazwanym miejscu; "move" z \
poprawionym punktem, gdy miejsce istnieje obok; "drop", gdy go nie ma.
Tekst: gdy usuwasz ślad, a tekst o nim mówi, zwróć poprawiony tekst ("text") bez tego \
twierdzenia, zmieniając jak najmniej słów; inaczej "text": "".

Odpowiedź JSON: {"marks": [{"n": 1, "verdict": "ok"|"move"|"drop", "points": [{"x": …, "y": …}, \
…] (przy "move" wszystkie punkty śladu, inaczej pusta lista), "why": "..."}], "points": [{"n": 1, \
"verdict": "ok"|"move"|"drop", "point": {"x": …, "y": …} (przy "move" poprawiony, inaczej ten \
sam), "why": "..."}], "text": "..."}"""

_POINT = _object(x={"type": "number"}, y={"type": "number"})
_VERDICT = {"type": "string", "enum": list(VERDICTS)}
SCHEMA = _object(
    marks=_list(_object(n={"type": "integer"}, verdict=_VERDICT, points=_list(_POINT), why=_str())),
    points=_list(_object(n={"type": "integer"}, verdict=_VERDICT, point=_POINT, why=_str())),
    text=_str(),
)


@dataclass
class Checked:
    """The take and its key points as the check left them, and what it changed."""

    view: View
    keys: list[Key]
    changes: list[str] = field(default_factory=list)


def _box(mark: Mark) -> list[Spot]:
    """A loop as the check sees it: the two corners of the box it is drawn in."""
    centre, corner = mark.points[0], mark.points[1]
    rx, ry = abs(corner.x - centre.x), abs(corner.y - centre.y)
    return [Spot(x=centre.x - rx, y=centre.y - ry), Spot(x=centre.x + rx, y=centre.y + ry)]


def question(
    img: Image.Image,
    view: View,
    keys: list[Key],
    na: dict[str, list[str]],
    po: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The check of a take: the clean picture, the take and its key points
    drawn on it, and both as data with what each point was meant to lie on
    and what the server measured."""
    w, h = img.size
    lines = [f"OBRAZ: {w} × {h} px (oba obrazy)", f"Tekst: {view.text}", "Ślady:"]
    for n, m in enumerate(view.marks, start=1):
        spots = _box(m) if m.shape == "loop" else m.points
        points = " ".join(f"({p.x * w:.0f}, {p.y * h:.0f})" for p in spots)
        named = "; ".join(na.get(m.title, []))
        along = f" – po: {along}" if (along := (po or {}).get(m.title, "")) else ""
        lines.append(
            f"{n}. {m.shape} „{m.title}” – {m.text} – punkty: {points} – na: {named}{along}"
        )
    lines.append("Punkty kluczowe:")
    for n, k in enumerate(keys, start=1):
        kind = "główny" if k.main else "ważny"
        lines.append(f"P{n}. ({k.x * w:.0f}, {k.y * h:.0f}) – na: {k.title} – {kind}")
    lines += ["Pomiary serwera:", *measures(view, (w, h))]
    content = [
        {"type": "text", "text": "OBRAZ BEZ ŚLADÓW"},
        image_block(img),
        {"type": "text", "text": "TEN SAM OBRAZ ZE ŚLADAMI"},
        image_block(draw_keys(draw(img, view), keys)),
        {"type": "text", "text": "\n".join(lines)},
    ]
    return request(
        model=HAIKU, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=8000,
        effort="medium",
    )  # fmt: skip


def _coord(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def checked(
    view: View, keys: list[Key], data: dict[str, Any] | None, size: tuple[int, int]
) -> Checked:
    """The take after the check's verdicts (its points in the pixels of the
    pictures it got): marks and places that missed moved, those that are
    not there left out, the text mended. As it was when the check is
    unusable or would leave no mark."""
    if not data:
        return Checked(view, keys)
    given = [p for c in _dicts(data.get("marks")) for p in _dicts(c.get("points"))]
    given += [c["point"] for c in _dicts(data.get("points")) if isinstance(c.get("point"), dict)]
    numbers = [abs(n) for p in given for n in (_coord(p.get("x")), _coord(p.get("y"))) if n]
    # In pixels, as asked; an answer all within the unit square gave fractions.
    w, h = size if numbers and max(numbers) > 1.5 else (1, 1)

    def spot(raw: Any) -> dict[str, float] | None:
        if not isinstance(raw, dict):
            return None
        x, y = _coord(raw.get("x")), _coord(raw.get("y"))
        return None if x is None or y is None else {"x": x / w, "y": y / h}

    def verdicts(key: str) -> dict[int, dict[str, Any]]:
        found: dict[int, dict[str, Any]] = {}
        for c in _dicts(data.get(key)):
            n = c.get("n")
            if isinstance(n, int) and c.get("verdict") in VERDICTS:
                found.setdefault(n, c)
        return found

    changes: list[str] = []
    marks = []
    for n, mark in enumerate(view.marks, start=1):
        c = verdicts("marks").get(n, {})
        why = _text(c.get("why"), 120)
        note = f": {why}" if why else ""
        if c.get("verdict") == "drop":
            changes.append(f"usunięty ślad {n} „{mark.title}”{note}")
            continue
        if c.get("verdict") == "move":
            points = [p for p in map(spot, c.get("points") or []) if p is not None]
            if mark.shape == "loop" and len(points) >= 2:  # its box, as it was shown
                a, b = points[0], points[1]
                points = [
                    {"x": (a["x"] + b["x"]) / 2, "y": (a["y"] + b["y"]) / 2},
                    {"x": max(a["x"], b["x"]), "y": max(a["y"], b["y"])},
                ]
            raw = {"shape": mark.shape, "title": mark.title, "text": mark.text, "points": points}
            moved = _mark(raw)
            if moved is not None and moved.points != mark.points:
                changes.append(f"przesunięty ślad {n} „{mark.title}”{note}")
                mark = moved
        marks.append(mark)
    if not marks:  # nothing left to show: the take as it was
        return Checked(view, keys)
    kept = []
    for n, key in enumerate(keys, start=1):
        c = verdicts("points").get(n, {})
        if c.get("verdict") == "drop":
            changes.append(f"usunięty punkt P{n} „{key.title}”")
            continue
        if c.get("verdict") == "move" and (to := spot(c.get("point"))) is not None:
            moved_key = _key({**key.model_dump(), **to})
            if moved_key is not None:
                key = moved_key
        kept.append(key)
    text = _text(data.get("text"), TEXT_CHARS)
    if text and text != view.text:
        changes.append("poprawiony tekst")
    update = {"marks": marks, "text": text or view.text}
    return Checked(view.model_copy(update=update), kept, changes)


def page_views(data: dict[str, Any]) -> list[View]:
    """The takes of a page (or of a model's answer), as the app shows them."""
    composition = data.get("composition")
    raw = _dicts(composition.get("views")) if isinstance(composition, dict) else []
    return takes([v for v in map(_view, raw) if v is not None])


def answer_views(data: dict[str, Any]) -> list[View]:
    """The take of a model's answer (the analysis or its check), whatever
    title it gave it: the one :func:`takes` picks, else its first usable
    view, named :data:`TAKE`. (Only the
    exact title used to count, so "Analiza kompozycji: Trouville" lost a
    paid answer.)"""
    composition = data.get("composition")
    raw = composition.get("views") if isinstance(composition, dict) else data.get("views")
    views = [v for v in map(_view, _dicts(raw)) if v is not None]
    found = takes(views) or views[:1]
    return [found[0].model_copy(update={"title": TAKE})] if found else []
