"""The composition checked over its own marks drawn on the picture.

A model that analyses a work's composition points at things by eye: a
loop a little beside a face, a horizon a few pixels off, a triangle that
was meant more than seen, a golden section the picture does not have. So
the take it drew (``ai.composition``) is drawn on the picture
(``ai.sketch``) and shown to Opus again with what the server measured of
it: it moves what missed, leaves out what cannot be defended and mends the
text that claimed it. One more question, far shorter; a take whose check
fails stays as it was.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .client import OPUS, Answer, request
from .daily import (
    CHECK_ROUND,
    CHECKED,
    ROUND,
    TAKE,
    VIEW,
    View,
    _dicts,
    _list,
    _object,
    _str,
    _text,
    _view,
    image_block,
    picture,
    sent_size,
    takes,
    to_fractions,
)
from .sketch import draw, measures

if TYPE_CHECKING:
    from ..library import ImageCache, Item

#: The pictures go out this big: one clean and one per take, so smaller
#: than the page's, still enough to see where a mark lies.
CHECK_SIDE = 1568
MAX_CHANGES = 20

SYSTEM = """Sprawdzasz „Analizę kompozycji” dzieła, którą inny autor narysował ołówkiem \
na obrazie do aplikacji domowej ramki. Dostajesz obraz bez śladów, potem ten sam obraz \
z narysowanymi śladami: różowe linie, trójkąty, koła, ramki, spirale, kreski rytmu (jedna \
wzdłuż każdej powtarzanej formy), promienie perspektywy zbiegające się w punkcie zbiegu, \
strzałki i ruch (strzałka ze smugami); numer śladu w białym kółku przy jego początku (przy \
spirali obok jej oka); niebieskie linie to siatka, gdy jest. Dalej ujęcie jako dane, ze \
współrzędnymi w pikselach obrazu (wymiary są w danych: OBRAZ, od lewego górnego rogu, x \
w prawo, y w dół), i pomiary serwera.

Najpierw sam spójrz na obraz bez śladów, z daleka, jak historyk sztuki: duże masy i ich \
równowaga, podziały pola, jedna figura, która porządkuje całość (trójkąt, przekątna, krzyż, \
owal, krzywa S, perspektywa zbieżna, klin, pasy), duże wyraźne rytmy, otwarta czy zamknięta.

Potem sprawdź każdy ślad:
- Czy pokazuje coś, co ten obraz naprawdę porządkuje, wyznaczone przez konkretne formy. \
Ślad naciągnięty (wzór przyłożony na siłę, linia przez puste pole, rytm z kilku form, które \
tylko przypadkiem stoją obok siebie, rytm sprzętów czy przedmiotów, np. stołków, krzeseł, \
butelek, spirala przez puste niebo) usuń i popraw tekst. Lepiej mniej i pewnie.
- Czy trafia: linia biegnie przez formy, które ją wyznaczają, a nie obok nich (przesuń ją, \
gdy mija je o więcej niż ich szerokość) i kończy się tam, gdzie one (albo biegnie dalej, gdy \
dalej biegnie forma; punkty poza obrazem są dozwolone, do połowy boku); kreska rytmu idzie \
po osi swojej formy od jej dołu do góry; promień perspektywy po prawdziwej krawędzi do punktu \
zbiegu, w którym spotykają się krawędzie; spirala ma oko na rzeczy, w którą się zwija, a łuki \
(pomiary podają, gdzie leżą kolejne ćwierć obroty) po prawdziwych formach; przesuń jej \
początek, punkt kierunku lub oko (spiralę można obrócić), albo ją usuń.
- Czytelność: dwa ślady nie biegną po tej samej krawędzi ani tuż obok siebie, jedna rzecz ma \
jeden ślad (nie kółko wokół łodzi i linia po jej maszcie), a numery nie lądują na sobie; gdy \
tak jest, zostaw ten, który mówi więcej (albo przesuń drugi na jego własną formę). Łamana, \
która krąży zygzakiem po kilku krawędziach, to zwykle klin: zostaw 3 punkty (koniec boku, \
wierzchołek, koniec drugiego boku). Krawędzie zbiegające się w perspektywie: "rays", gdy \
punkt zbiegu leży w obrazie lub do pół boku poza nim, inaczej dwie osobne "line" po tych \
krawędziach. Strzałka otwartości jest \
długa (co najmniej jedna piąta boku) i idzie przez formę, której nie zajmuje inny ślad; \
krótki zaczep przy krawędzi usuń.
- Gdy brakuje głównego układu, wyraźnego podziału albo dużego rytmu, które widzisz, dodaj go \
i dopisz do tekstu. Układ, który tekst nazywa najmocniejszym (np. klin, piramida, przekątna), \
musi mieć swój ślad, i to pierwszy; porządkując czytelność, nie usuwaj go, tylko to, co go \
dubluje.
- Siatka zostaje, gdy kluczowy element leży na jej linii lub blisko niej (pomiary podają \
odległości w ułamkach boku: do ok. 0,02 to „na linii”, do ok. 0,05 „blisko linii”, dalej \
siatka nie pasuje): wtedy ustaw właściwą ("golden", "thirds", "halves", "3x2", "2x3"); \
inaczej "none" i usuń z tekstu twierdzenie o siatce.
- Tekst: 4–6 zdań, jedno mówi, czy kompozycja jest otwarta czy zamknięta i po czym to widać. \
Popraw zdania, które twierdzą coś, czego obraz nie potwierdza.

Popraw: przesuń punkty tego, co chybia, celując dokładnie; usuń ślad, którego nie da się \
obronić. Co poprawne, zostaw bez zmian: te same współrzędne, te same słowa.

Kształty i ich punkty: "line" (2–12 punktów), "triangle" (3 wierzchołki), "loop" (środek \
i jeden róg prostokąta, w który się wpisuje), "rect" (dwa przeciwległe rogi), "rhythm" (pary \
punktów, 3–12 par: dół i góra każdej powtarzanej formy), "rays" (punkt zbiegu, potem 2–8 \
dalekich końców promieni), "motion" (2–12 punktów po torze ruchu, grot na końcu), "arrow" \
(2–12 punktów, grot na końcu), "spiral" (złota spirala: początek najszerszego łuku, punkt na \
nim mniej więcej ćwierć obrotu dalej, który wyznacza kierunek skrętu, i oko). Forma jak \
w oryginale, naturalną polszczyzną: "title" ujęcia „Analiza kompozycji”, podpis śladu \
("title") 1–3 słowa, dopisek ("text") najwyżej 45 znaków; 3–6 śladów, najpierw główny układ.

Zwróć poprawione ujęcie ("views" z jednym ujęciem, współrzędne w pikselach) i "changes": \
krótkie notatki, co zmieniłeś i dlaczego (np. „usunięty rytm drzew: stoją przypadkiem”); \
pusta lista, gdy wszystko było dobrze."""

SCHEMA = _object(views=_list(VIEW), changes=_list(_str()))


def _px(view: View, size: tuple[int, int]) -> list[str]:
    """A take as data, its points in pixels, with what the server measured."""
    lines = [f"Siatka: {view.grid}", f"Tekst: {view.text}", "Ślady:"]
    for n, mark in enumerate(view.marks, start=1):
        points = " ".join(f"({p.x * size[0]:.0f}, {p.y * size[1]:.0f})" for p in mark.points)
        note = f" – dopisek: {mark.text}" if mark.text else ""
        lines.append(f"{n}. {mark.shape} „{mark.title}”{note} – punkty: {points}")
    return [*lines, "Pomiary serwera:", *measures(view, size)]


def question(views: list[View], images: ImageCache, item: Item) -> dict[str, Any]:
    """The check of ``views``: the clean picture, each take drawn on it, and
    the takes as data with what the server measured."""
    img = picture(images, item, CHECK_SIDE)
    size = img.size
    content: list[dict[str, Any]] = [
        {"type": "text", "text": "OBRAZ BEZ ŚLADÓW"},
        image_block(img),
    ]
    data = [
        f"DZIEŁO: {item.artist}, {_text(item.title, 200)}, {item.date_text}",
        f"OBRAZ: {size[0]} × {size[1]} px (wszystkie obrazy mają ten rozmiar)",
    ]
    for n, view in enumerate(views, start=1):
        content += [
            {"type": "text", "text": f"UJĘCIE {n} „{view.title}” Z NARYSOWANYMI ŚLADAMI"},
            image_block(draw(img, view)),
        ]
        data += ["", f"UJĘCIE {n} „{view.title}”", *_px(view, size)]
    content.append({"type": "text", "text": "\n".join(data)})
    params = request(
        model=OPUS, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=16000, effort="medium"
    )
    params["timeout"] = 600.0
    return params


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


def corrected(data: dict[str, Any] | None) -> tuple[list[View], list[str]] | None:
    """The takes a check gave back (its answer in fractions already) and
    what it changed; None when it is unusable."""
    if data is None:
        return None
    kept = answer_views(data)
    if not kept:
        return None
    changes = [_text(c, 200) for c in data.get("changes") or [] if _text(c)][:MAX_CHANGES]
    return kept, changes


def check(
    images: ImageCache, item: Item, data: dict[str, Any], ask: Callable[[dict[str, Any]], Answer]
) -> dict[str, Any]:
    """``data`` (a page's answer in fractions) with its takes as Claude
    corrected them over the marks drawn on the picture, and what it changed
    under :data:`CHECKED`; as it was when there is nothing to check, with an
    empty :data:`CHECKED` when the answer is unusable."""
    views = page_views(data)
    if not views:
        return data
    params = question(views, images, item)
    answer = ask(params)
    found = corrected(to_fractions(answer.data, sent_size(params)) if answer.data else None)
    if found is None:  # asked once all the same
        return {**data, CHECKED: [], CHECK_ROUND: ROUND}
    kept, changes = found
    drawn = [v.model_dump() for v in kept]
    return {**data, "composition": {"views": drawn}, CHECKED: changes, CHECK_ROUND: ROUND}
