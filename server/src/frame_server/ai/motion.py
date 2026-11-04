"""Movement and dynamics in a composition: a step of its own, by Sonnet.

The analysis (``ai.composition``) no longer says whether a picture is still
or moving, nor draws its movement: a model asked for everything at once
drew a flight's path by guess and called a still life dynamic. Here
Sonnet looks at the analysed picture with its marks, with how much of its
edges the server measured running level, upright and slanting
(``ai.lines.directions``) and its long straight slants, and writes one
sentence (in place of one that already spoke of it, or added) and at most
two "motion" marks for a movement that really happens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from .client import SONNET, request
from .daily import Mark, View, _dicts, _list, _mark, _object, _str, _text, image_block
from .lines import Found
from .sketch import draw

MAX_MOTION = 2
BUILDS = ("statyczna", "dynamiczna", "statyczna z ruchem")

SYSTEM = """Dopisujesz do gotowej „Analizy kompozycji” jednego dzieła część o ruchu i \
dynamice. Analizę, jej tekst i ślady zrobił wcześniej inny model; Ty ich nie zmieniasz. \
Odpowiadasz tylko za ruch: czy kompozycja jest statyczna czy dynamiczna, i czy w obrazie \
dzieje się ruch wart narysowania. Naturalna, poprawna polszczyzna, jak w dobrym polskim \
muzeum, bez superlatywów, dla miłośnika sztuki, który nie jest historykiem sztuki.

Dostajesz: czysty obraz, ten sam obraz ze śladami analizy, ponumerowane zdania tekstu, listę \
śladów i pomiar programu (jaki udział krawędzi w obrazie biegnie poziomo, pionowo i skośnie; \
długie proste skosy). Współrzędne podajesz w pikselach tych obrazów, od lewego górnego rogu.

JAK OCENIASZ
1. Budowa. Statyczna: przewaga pionów i poziomów, symetria, szeroka podstawa, spokój. \
Dynamiczna: skosy, łuki, linie łamane, asymetria, formy w ruchu lub w chwiejnej równowadze. \
Pomiar programu jest wskazówką, nie wyrokiem: faktura pędzla i drobny wzór też dają skosy, \
liczy się to, co widać z daleka. Wiele obrazów łączy obie cechy (spokojna architektura i \
gwałtowny gest): powiedz, co przeważa i po czym to widać.
2. Kierunek. Czy główne kierunki prowadzą do środka (dośrodkowa) czy ku krawędziom \
(odśrodkowa); mów o tym tylko, gdy to wyraźne.
3. Ruch w obrazie. Ślad "motion" rysujesz tylko dla ruchu, który naprawdę się dzieje i który \
widać: lot, huśtanie, upadek, galop, taniec, fala, wiatr szarpiący formy, cios, rzut. Nie dla \
drogi wzroku, nie dla spokojnej czynności (lanie mleka, szycie, czytanie), nie dla \
nieruchomej linii (ta należy do analizy). Najwyżej 2 ślady, zwykle 0 albo 1. Tor biegnie po \
prawdziwych formach (kolano, brzeg sukni, siedzisko, lina), 2–12 punktów, grot na końcu w \
stronę ruchu; każdy punkt nazwij w "na". Nie dubluj śladu analizy, który już biegnie tą samą \
drogą.

ODPOWIEDŹ
- "budowa": "statyczna", "dynamiczna" albo "statyczna z ruchem" (spokojna budowa, w której \
dzieje się ruch).
- "sentence": jedno zdanie, 90–200 znaków, w tonie tekstu: co przeważa i po czym to widać, \
nazwane formy. Bez liczb z pomiaru programu.
- "replaces": numer zdania tekstu, które już mówi o statyce, dynamice lub ruchu i które Twoje \
zdanie zastępuje; 0, gdy takiego nie ma.
- "where": gdy "replaces" to 0, numer zdania, po którym ma stać Twoje (0 = na koniec).
- "marks": 0–2 ślady {"shape": "motion", "points": [{"x": …, "y": …}, …], "na": [...], \
"title": 1–3 słowa, "text": najwyżej 45 znaków}.
- "why": najwyżej 15 słów."""

_POINT = _object(x={"type": "number"}, y={"type": "number"})
SCHEMA = _object(
    budowa={"type": "string", "enum": list(BUILDS)},
    sentence=_str(),
    replaces={"type": "integer"},
    where={"type": "integer"},
    marks=_list(
        _object(
            shape={"type": "string", "enum": ["motion"]},
            points=_list(_POINT),
            na=_list(_str()),
            title=_str(),
            text=_str(),
        )
    ),
    why=_str(),
)


@dataclass
class Movement:
    """What the step said: its sentence, which sentence it replaces (from
    1; 0 none) or follows (0: at the end), and its marks."""

    build: str
    sentence: str
    replaces: int = 0
    where: int = 0
    marks: list[Mark] = field(default_factory=list)


def question(
    img: Image.Image,
    view: View,
    said: list[str],
    directions: tuple[float, float, float],
    found: Found,
) -> dict[str, Any]:
    """Sonnet's look at the movement: the clean picture, the take drawn on
    it, its sentences and marks, and what the server measured."""
    w, h = img.size
    level, upright, slanting = directions
    lines = [
        f"OBRAZ: {w} × {h} px (oba obrazy)",
        "Tekst analizy (zdania ponumerowane):",
        *(f"{n}. {s}" for n, s in enumerate(said, start=1)),
        "Ślady analizy (na drugim obrazie):",
    ]
    for n, m in enumerate(view.marks, start=1):
        points = " ".join(f"({p.x * w:.0f}, {p.y * h:.0f})" for p in m.points)
        lines.append(f"{n}. {m.shape} „{m.title}” – {m.text} – punkty: {points}")
    lines.append(
        f"Pomiar programu – kierunek krawędzi w obrazie (udział siły): poziome {level:.0%}, "
        f"pionowe {upright:.0%}, skośne i krzywe {slanting:.0%}. Dla porównania: przy "
        "kierunkach zupełnie przypadkowych wychodzi ok. 13% / 13% / 74%; im więcej pionów i "
        "poziomów ponad to, tym spokojniejsza budowa."
    )
    if found.slants:
        lines.append(
            "Długie proste skosy znalezione przez program (piksele): "
            + "; ".join(
                f"({s.x1 * w:.0f}, {s.y1 * h:.0f})–({s.x2 * w:.0f}, {s.y2 * h:.0f}) "
                f"kąt {s.angle:.0f}°"
                for s in found.slants
            )
        )
    content = [
        {"type": "text", "text": "OBRAZ BEZ ŚLADÓW"},
        image_block(img),
        {"type": "text", "text": "TEN SAM OBRAZ ZE ŚLADAMI ANALIZY"},
        image_block(draw(img, view)),
        {"type": "text", "text": "\n".join(lines)},
    ]
    return request(
        model=SONNET, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=8000,
        effort="medium",
    )  # fmt: skip


def _coord(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")  # left out by ``_mark``


def _number(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def movement(data: dict[str, Any] | None, size: tuple[int, int]) -> Movement | None:
    """The step's answer (points in the pixels of the pictures it got), or
    None when it said nothing usable."""
    if not data:
        return None
    sentence = _text(data.get("sentence"), 300)
    if not sentence:
        return None
    w, h = size
    marks = []
    for raw in _dicts(data.get("marks"))[:MAX_MOTION]:
        spots = [(_coord(p.get("x")), _coord(p.get("y"))) for p in _dicts(raw.get("points"))]
        pixels = any(abs(x) > 1.5 or abs(y) > 1.5 for x, y in spots)
        sx, sy = (w, h) if pixels else (1, 1)
        points = [{"x": x / sx, "y": y / sy} for x, y in spots]
        found = _mark({**raw, "shape": "motion", "points": points})
        if found is not None:
            marks.append(found)
    build = data.get("budowa")
    return Movement(
        build=build if isinstance(build, str) and build in BUILDS else "",
        sentence=sentence,
        replaces=_number(data.get("replaces")),
        where=_number(data.get("where")),
        marks=marks,
    )
