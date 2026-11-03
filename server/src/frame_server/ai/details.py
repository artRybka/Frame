"""The page's details checked over their own cuts.

The model draws a detail's box by eye on the whole picture, and now and
then misses: Hopper's "Automat" (2026-11-03) had its "Twarz pod
kapeluszem" some 200 pixels too high, a cut of the wall above the hat.
So each box is cut from the picture the model saw and shown to Opus again
with the whole picture, its title and its text: a box that shows what it
is about stays, one that misses is drawn again. One short question more;
a page whose check fails keeps its boxes as they were.

Pages written before the check get it when the owner asks ("Popraw
detale", the held header "Detale"; Mateusz 2026-11-03: "Na żądanie,
przytrzymaniem"): :class:`MendJob`, ahead of the background.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from PIL import Image

from ..library.images import display_copy
from ..library.models import Note
from .client import OPUS, Answer, request
from .daily import (
    BOXES,
    BOXES_VERSION,
    DETAILS_CHECKED,
    SEEN,
    Essay,
    Seen,
    _dicts,
    _list,
    _object,
    _str,
    _text,
    image_block,
    mend_boxes,
    picture,
    sent_size,
)
from .daily import KIND as DAILY
from .jobs import NoteJob, Usage, text_hash
from .study import KIND as STUDY

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from .config import AiConfigStore

log = logging.getLogger(__name__)

#: Marks a page whose details were checked; what the check moved.
CHECKED = DETAILS_CHECKED
#: A cut shown at most this big.
CUT_SIDE = 768

SYSTEM = """Sprawdzasz „Detale” dzieła w aplikacji domowej ramki: fragmenty, które inny \
autor zaznaczył ramkami na obrazie, żeby aplikacja wycięła je w pełnej rozdzielczości. \
Dostajesz cały obraz, a potem każdy wycinek osobno: jego tytuł, opis, ramkę w pikselach \
całego obrazu (x, y lewego górnego rogu, szerokość w, wysokość h; od lewego górnego rogu, \
x w prawo, y w dół) i to, co ta ramka naprawdę wycina.

Dla każdego wycinka: czy pokazuje to, o czym mówią tytuł i opis, w całości, blisko i \
mniej więcej w środku? Twarz cała, z oczami i ustami, nie samo czoło ani kapelusz; dłoń \
z tym, co trzyma; napis do przeczytania.
- Tak: "ok": true i ta sama ramka.
- Nie: "ok": false i nowa ramka. Najpierw znajdź tę rzecz na całym obrazie, potem podaj \
ramkę ciasno wokół niej, w pikselach całego obrazu: bok 10–35% szerokości obrazu, \
proporcje od 3:4 do 4:3, w granicach obrazu.
Tytułu i opisu nie zmieniasz. "n" to numer wycinka."""

SCHEMA = _object(
    details=_list(
        _object(
            n={"type": "integer"},
            ok={"type": "boolean"},
            x={"type": "number"},
            y={"type": "number"},
            w={"type": "number"},
            h={"type": "number"},
            why=_str("gdy nie: co ramka wycina zamiast tego, krótko"),
        )
    )
)


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _px(d: dict[str, Any], size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    x, y, w, h = (_num(d.get(k)) or 0.0 for k in ("x", "y", "w", "h"))
    return round(x * width), round(y * height), round(w * width), round(h * height)


def question(details: list[dict[str, Any]], img: Image.Image) -> dict[str, Any]:
    """The whole picture, then each detail's box as data and as its cut."""
    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"CAŁY OBRAZ: {img.size[0]} × {img.size[1]} px"},
        image_block(img),
    ]
    for n, d in enumerate(details, start=1):
        x, y, w, h = _px(d, img.size)
        cut = img.crop((x, y, x + w, y + h))
        cut.thumbnail((CUT_SIDE, CUT_SIDE), Image.Resampling.LANCZOS)
        about = _text(d.get("title"), 60)
        text = _text(d.get("text"), 300)
        content += [
            {
                "type": "text",
                "text": f"WYCINEK {n} „{about}”: {text}\nRamka: x={x} y={y} w={w} h={h}",
            },
            image_block(cut),
        ]
    return request(
        model=OPUS, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=8000, effort="medium"
    )


def mended(
    details: list[dict[str, Any]], answer: dict[str, Any] | None, size: tuple[int, int]
) -> tuple[list[dict[str, Any]], list[str]] | None:
    """``details`` (fractions) with the boxes the check drew anew, and the
    titles it moved; None when the answer is unusable."""
    if answer is None:
        return None
    width, height = size
    out = [dict(d) for d in details]
    moved: list[str] = []
    for found in _dicts(answer.get("details")):
        n = found.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(out) or found.get("ok") is not False:
            continue
        box = [_num(found.get(k)) for k in ("x", "y", "w", "h")]
        if None in box or (box[2] or 0) <= 0 or (box[3] or 0) <= 0:
            continue
        x, y, w, h = (v or 0.0 for v in box)
        out[n - 1].update(x=x / width, y=y / height, w=w / width, h=h / height)
        moved.append(_text(out[n - 1].get("title"), 60))
    return out, moved


def check(
    images: ImageCache, item: Item, data: dict[str, Any], ask: Callable[[dict[str, Any]], Answer]
) -> dict[str, Any]:
    """``data`` (a page's answer in fractions) with its details checked
    over their cuts on the picture the model saw (``ai.daily.picture``);
    as it was when there are none or the check gives nothing usable."""
    details = _dicts(data.get("details"))
    if not details:
        return data
    if not all(_num(d.get(k)) is not None for d in details for k in ("x", "y", "w", "h")):
        return data
    img = picture(images, item)
    found = mended(details, ask(question(details, img)).data, img.size)
    if found is None:
        return data
    fixed, moved = found
    return {**data, "details": fixed, CHECKED: moved}


KIND = "details_check"
PROMPT_VERSION = "details-1"
#: The works whose details the owner asked to be checked, not done yet.
AGAIN_KEY = "details_again"
#: The pages it mends.
PAGES = (DAILY, STUDY)
#: The whole picture and four or five cuts, a short answer.
TYPICAL = Usage(input_tokens=9000, cache_read_input_tokens=0, output_tokens=1500)


def seen(item: Item) -> Seen:
    """The copy a page's boxes are drawn on from now on: the one shown."""
    return Seen(copy_id=item.sharper.item_id if item.sharper else "", url=display_copy(item))


def boxes(page: Note, item: Item) -> Essay:
    """The page's details (and focus) as fractions of the picture the model
    reads, a page from before :data:`BOXES_VERSION` mended as ``essay``
    shows it."""
    essay = Essay.model_validate(page.data)
    return essay if page.data.get(BOXES) == BOXES_VERSION else mend_boxes(essay, item)


def titles(details: list[dict[str, Any]]) -> list[str]:
    return [_text(d.get("title"), 60) for d in details]


class MendJob(NoteJob):
    """The owner's "Popraw detale" on a page written before its details
    were checked: the same check (:func:`check`), its boxes kept in the
    work's pages, the copy they are drawn on noted (``Seen``)."""

    kind = KIND
    model = OPUS
    prompt_version = PROMPT_VERSION
    typical = TYPICAL

    def __init__(self, library: Library, images: ImageCache, config: AiConfigStore) -> None:
        super().__init__(library, images, config)

    def enabled(self) -> bool:
        """With the pages themselves ("Studium dnia" on)."""
        return self.config.enabled(DAILY)

    def asked(self) -> set[str]:
        found = self.library.get_state(AGAIN_KEY, [])
        return {str(i) for i in found} if isinstance(found, list) else set()

    def _pages_of(self, item_id: str) -> list[Note]:
        """The work's written pages with details (its study, its day's page)."""
        found = (self.library.note(item_id, kind) for kind in PAGES)
        return [p for p in found if p is not None and "teaser" in p.data and p.data.get("details")]

    def again(self, item: Item) -> bool:
        """Asks for the work's details to be checked; False when it has no
        written page with details."""
        if not self._pages_of(item.id):
            return False
        self.library.delete_notes(KIND, item.id)
        self.library.set_state(AGAIN_KEY, sorted(self.asked() | {item.id}))
        return True

    def pending(self, item_id: str) -> bool:
        """Asked for and on its way (not when the check came to nothing)."""
        if item_id not in self.asked():
            return False
        note = self.library.note(item_id, KIND)
        return note is None or not any(note.data.get(k) for k in ("refused", "failed"))

    def moved(self, item_id: str) -> list[str] | None:
        """The titles of the details the last check moved; None when it
        gave nothing usable (or there was none)."""
        note = self.library.note(item_id, KIND)
        if note is None or "details" not in note.data:
            return None
        return [str(t) for t in note.data.get(CHECKED) or []]

    def wanted(self, item: Item) -> bool:
        return item.id in self.asked()

    def source_hash(self, item: Item) -> str:
        return text_hash(item.title, item.artist, item.date_text)

    def params(self, item: Item) -> dict[str, Any]:
        pages = self._pages_of(item.id)
        if not pages:
            raise ValueError("no page with details")
        details = [d.model_dump() for d in boxes(pages[0], item).details]
        return question(details, picture(self.images, item))

    def revise(
        self, item: Item, params: dict[str, Any], answer: Answer, ask: Callable[..., Answer]
    ) -> Answer:
        """The boxes in fractions, with the titles they belong to."""
        pages = self._pages_of(item.id)
        details = [d.model_dump() for d in boxes(pages[0], item).details] if pages else []
        size = sent_size(params)
        found = mended(details, answer.data, size) if size and details else None
        if found is None:
            log.warning("details check of %s gave nothing usable", item.id)
            return replace(answer, data={"unusable": True})
        fixed, moved = found
        return replace(answer, data={"details": fixed, CHECKED: moved, "titles": titles(fixed)})

    def apply(self, item: Item, note: Note) -> None:
        """Puts the boxes in each of the work's pages with the same details;
        the work is asked about no more."""
        fixed = _dicts(note.data.get("details"))
        if fixed:
            for page in self._pages_of(item.id):
                essay = boxes(page, item)
                if titles([d.model_dump() for d in essay.details]) != titles(fixed):
                    continue
                data: dict[str, Any] = {
                    **page.data,
                    "details": fixed,
                    BOXES: BOXES_VERSION,
                    SEEN: seen(item).model_dump(),
                    CHECKED: note.data.get(CHECKED) or [],
                }
                if page.data.get(BOXES) != BOXES_VERSION:
                    data["focus"] = essay.focus.model_dump() if essay.focus else None
                self.library.save_note(page.model_copy(update={"data": data}))
        self.library.set_state(AGAIN_KEY, sorted(self.asked() - {item.id}))
