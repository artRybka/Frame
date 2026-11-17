"""A photograph's white balance set by hand (Mateusz 2026-11-17 16:27
UTC: "Gdy przy robieniu zdjęcia dzieła nie zostanie wykryta karta koloru
dodaj suwak regulacji balansu bieli").

His works hang under warm lamps, and the phone leaves much of that
warmth in: the white wall beside a small oil had 3.3 times the red of
its blue in linear light, beside others 1.3 to 4. With no colour chart
beside the work (:mod:`.colorchecker`) nothing says what is white there,
so he says it: one number from -1 (cooler) to 1 (warmer), 0 as taken.

The colours move as a lamp's warmth does: red by :data:`WARM`'s first
part, blue by its second, the other way and further (a lamp against
daylight is some 0.6 of red and 1.7 of blue), green staying, and the
whole kept as light as it was. The app draws the same on the phone
(``OwnBalance`` in ``OwnScanResult.swift``): the two must agree."""

from __future__ import annotations

from PIL import Image

#: Full warmth: red and blue so many times two (in linear light).
WARM = (0.72, -1.2)
#: How much of a colour's light is seen as light (Rec. 709).
_SEEN = (0.2126, 0.7152, 0.0722)


def gains(balance: float) -> tuple[float, float, float]:
    """What red, green and blue light are multiplied by at ``balance``
    (-1 cooler … 1 warmer): a grey stays as light as it was."""
    at = max(-1.0, min(1.0, balance))
    raw = (2.0 ** (WARM[0] * at), 1.0, 2.0 ** (WARM[1] * at))
    seen = sum(share * gain for share, gain in zip(_SEEN, raw, strict=True))
    return (raw[0] / seen, raw[1] / seen, raw[2] / seen)


def _linear(coded: float) -> float:
    return coded / 12.92 if coded <= 0.04045 else ((coded + 0.055) / 1.055) ** 2.4


def _coded(light: float) -> float:
    return light * 12.92 if light <= 0.0031308 else 1.055 * light ** (1 / 2.4) - 0.055


def apply(img: Image.Image, balance: float) -> Image.Image:
    """``img`` (RGB) at ``balance``: itself at 0."""
    if abs(balance) < 1e-3:
        return img
    table: list[int] = []
    for gain in gains(balance):
        table += [
            round(255 * _coded(min(1.0, _linear(level / 255) * gain))) for level in range(256)
        ]
    return img.convert("RGB").point(table)
