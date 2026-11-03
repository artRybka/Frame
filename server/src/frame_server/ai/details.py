"""The page's details checked over their own cuts.

The model draws a detail's box by eye on the whole picture, and now and
then misses: Hopper's "Automat" (2026-11-03) had its "Twarz pod
kapeluszem" some 200 pixels too high, a cut of the wall above the hat.
So each box is cut from the picture the model saw and shown to Opus again
with the whole picture, its title and its text: a box that shows what it
is about stays, one that misses is drawn again. One short question more;
a page whose check fails keeps its boxes as they were.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PIL import Image

from .client import OPUS, Answer, request
from .daily import DETAILS_CHECKED, _dicts, _list, _object, _str, _text, image_block, picture

if TYPE_CHECKING:
    from ..library import ImageCache, Item

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
