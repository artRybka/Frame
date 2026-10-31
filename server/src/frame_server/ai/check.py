"""The composition checked over its own marks drawn on the picture.

A model that writes a page about a work points at things by eye: a loop a
little beside a face, a horizon a few pixels off, a triangle that was
meant more than seen, a golden section the picture does not have. So the
takes it drew (``ai.daily``) are drawn on the picture (``ai.sketch``) and
shown to Opus again with what the server measured of them: it moves what
missed, leaves out what cannot be defended and mends the text that claimed
it. One more question, far shorter than the page; a page whose check fails
keeps its takes as they were.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..library.models import Note
from .client import OPUS, Answer, request
from .daily import (
    _POINT,
    CHECKED,
    GRIDS,
    SHAPES,
    View,
    _composition,
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
from .daily import (
    KIND as DAILY,
)
from .jobs import NoteJob, Usage, text_hash
from .rhythm import wants_rhythm
from .sketch import draw, measures
from .study import KIND as STUDY

if TYPE_CHECKING:
    from ..library import ImageCache, Item

KIND = "check"
PROMPT_VERSION = "check-1"
#: The pages checked.
PAGES = (DAILY, STUDY)
#: How long the list of pages wanting a check is kept between looks.
PAGES_SECONDS = 30.0
#: Four pictures of 1568 px and the takes; corrected takes with thinking.
TYPICAL = Usage(input_tokens=8000, cache_read_input_tokens=1200, output_tokens=3000)

#: The pictures go out this big: one clean and one per take, so smaller
#: than the page's, still enough to see where a mark lies.
CHECK_SIDE = 1568
MAX_CHANGES = 20

SYSTEM = """Sprawdzasz analizę kompozycji dzieła, którą inny autor narysował ołówkiem na \
obrazie do aplikacji domowej ramki. Dostajesz obraz bez śladów, a potem każde ujęcie na tym \
samym obrazie z narysowanymi śladami: różowe linie, strzałki, kółka, trójkąty i ramki, kropki \
rytmu, numer śladu w białym kółku przy jego początku; niebieskie linie to siatka ujęcia \
(złoty podział lub trójpodział), gdy ją ma. Dalej ujęcia jako dane, ze współrzędnymi \
w pikselach obrazu (wymiary są w danych: OBRAZ, od lewego górnego rogu, x w prawo, y w dół), \
i pomiary serwera.

Dla każdego śladu sprawdź na obrazie:
- czy leży dokładnie na rzeczy, którą nazywa jego podpis: kółko obejmuje tę rzecz (nie obok, \
nie połowę), linia biegnie po horyzoncie, krawędzi lub osi, wierzchołki trójkąta leżą na \
prawdziwych punktach form, punkty rytmu na kolejnych powtórzeniach i nigdzie indziej, \
strzałka przechodzi przez rzeczy w kolejności, o której mówi tekst;
- czy to, co twierdzi, jest zasadne: trójkąt, przekątna, oś symetrii, owal czy krzywa S \
naprawdę porządkują obraz, a nie są do niego dorysowane (trójkąt może być duży i otwarty, \
z podstawą na krawędzi obrazu, byle jego boki wyznaczały prawdziwe formy); rytm to co \
najmniej trzy powtórzenia; siatka zostaje, gdy kluczowy element leży na jej linii lub blisko \
niej (pomiary podają odległości w ułamkach boku: do ok. 0,02 to „na linii”, do ok. 0,05 \
„blisko linii”, dalej siatka nie pasuje), a tekst mówi o tym tak, jak jest.

Popraw: przesuń punkty tego, co chybia, celując dokładnie; usuń ślad, którego nie da się \
obronić; ustaw "grid" na "none", gdy nic na siatce ani blisko niej nie leży; popraw "text" \
ujęcia i podpisy, gdy twierdzą coś, czego obraz nie potwierdza (np. złoty podział, którego \
nie ma). Ujęcie bez żadnego zasadnego śladu pomiń. Nie dodawaj nowych ujęć; nowy ślad tylko \
wtedy, gdy tekst \
ujęcia mówi o rzeczy, której nie zaznaczono. Co poprawne, zostaw bez zmian: te same \
współrzędne, te same słowa.

Kształty i ich punkty: "arrow" (2–12 punktów wzdłuż drogi wzroku, grot na końcu), "line" \
(2–12 punktów: horyzont, przekątna, oś, krawędź), "loop" (kółko: środek rzeczy i jeden róg \
prostokąta, w który się wpisuje), "triangle" (3 wierzchołki), "rect" (dwa przeciwległe rogi), \
"underline" (falka pod rzeczą: początek i koniec), "rhythm" (3–12 punktów, po jednym na \
każdym powtórzeniu, po kolei). Forma jak w oryginale, naturalną polszczyzną: "title" ujęcia \
1–3 słowa, "text" dwa-trzy zdania, podpis śladu ("title") 1–3 słowa, dopisek ("text") \
najwyżej 45 znaków; kolejność śladów to kolejność czytania.

Zwróć wszystkie zachowane ujęcia w tej samej kolejności ("views", współrzędne w pikselach) \
i "changes": krótkie notatki, co zmieniłeś i dlaczego (np. „Geometria, ślad 2: kółko \
przesunięte na twarz”); pusta lista, gdy wszystko było dobrze."""

SCHEMA = _object(
    views=_list(
        _object(
            title=_str(),
            grid={"type": "string", "enum": list(GRIDS)},
            text=_str(),
            marks=_list(
                _object(
                    shape={"type": "string", "enum": list(SHAPES)},
                    points=_list(_POINT),
                    title=_str(),
                    text=_str(),
                )
            ),
        )
    ),
    changes=_list(_str()),
)


def _px(view: View, size: tuple[int, int]) -> list[str]:
    """A take as data, its points in pixels, with what the server measured."""
    lines = [f"Siatka: {view.grid}", f"Tekst: {view.text}", "Ślady:"]
    for n, mark in enumerate(view.marks, start=1):
        points = " ".join(f"({p.x * size[0]:.0f}, {p.y * size[1]:.0f})" for p in mark.points)
        note = f" – dopisek: {mark.text}" if mark.text else ""
        lines.append(f"{n}. {mark.shape} „{mark.title}”{note} – punkty: {points}")
    return [*lines, "Pomiary serwera:", *measures(view, size)]


def wants_check(note: Note | None) -> bool:
    """A written page with takes, never checked, that is not waiting for its
    "Rytm" (``ai.rhythm``) first."""
    if note is None or "teaser" not in note.data or CHECKED in note.data:
        return False
    return bool(page_views(note.data)) and not wants_rhythm(note)


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


def corrected(data: dict[str, Any] | None) -> tuple[list[View], list[str]] | None:
    """The takes a check gave back (its answer in fractions already) and
    what it changed; None when it is unusable."""
    if data is None:
        return None
    kept = takes([v for v in map(_view, _dicts(data.get("views"))) if v is not None])
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
        return {**data, CHECKED: []}
    kept, changes = found
    return {**data, "composition": {"views": [v.model_dump() for v in kept]}, CHECKED: changes}


class CheckJob(NoteJob):
    """The check asked alone of pages written before it (kept for good, so a
    new prompt never reaches them): their takes corrected over their marks
    drawn on the picture, the rest of the page as it was. Once per page."""

    kind = KIND
    model = OPUS
    prompt_version = PROMPT_VERSION
    typical = TYPICAL

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pages: tuple[float, set[str]] = (0.0, set())

    def waiting(self) -> set[str]:
        """The works with a page wanting a check (looked up again every
        :data:`PAGES_SECONDS`: the background asks about every item)."""
        when, ids = self._pages
        if time.monotonic() - when > PAGES_SECONDS:
            ids = {
                item_id
                for kind in PAGES
                for item_id, note in self.library.notes(kind).items()
                if wants_check(note)
            }
            self._pages = (time.monotonic(), ids)
        return ids

    def wanted(self, item: Item) -> bool:
        return item.id in self.waiting()

    def source_hash(self, item: Item) -> str:
        return text_hash(item.title, item.artist, item.date_text)

    def params(self, item: Item) -> dict[str, Any]:
        for kind in PAGES:
            note = self.library.note(item.id, kind)
            if wants_check(note):
                assert note is not None
                return question(page_views(note.data), self.images, item)
        raise ValueError(f"no page of {item.id} wants a check")

    def revise(
        self, item: Item, params: dict[str, Any], answer: Answer, ask: Callable[..., Answer]
    ) -> Answer:
        if answer.data is None:
            return answer
        return replace(answer, data=to_fractions(answer.data, sent_size(params)))

    def apply(self, item: Item, note: Note) -> None:
        """Puts the corrected takes in each of the work's pages wanting them;
        a page whose check is unusable keeps its takes. Either way, once."""
        found = corrected(note.data)
        for kind in PAGES:
            page = self.library.note(item.id, kind)
            if not wants_check(page):
                continue
            assert page is not None
            data = {**page.data, CHECKED: found[1] if found else []}
            if found:
                data["composition"] = _composition(found[0]).model_dump()
            self.library.save_note(page.model_copy(update={"data": data}))
        self._pages = (0.0, set())
