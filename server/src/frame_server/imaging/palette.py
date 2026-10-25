"""Panel palettes.

Every palette colour has two values:

* ``device``    – the RGB value written into the image file so the panel's
                  firmware selects that ink (the "theoretical" colour),
* ``perceived`` – what that ink actually looks like on the panel, measured
                  by photographing or colorimetering a test chart.

Dithering decisions are made against ``perceived`` colours and the result is
written with ``device`` colours. Getting ``perceived`` right is what fixes the
"too dark / muddy" look: see docs/IMAGE_PIPELINE.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .color import FloatArray, linear_to_oklab, u8_to_linear

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class PaletteColor:
    name: str
    device: RGB
    perceived: RGB


@dataclass(frozen=True)
class Palette:
    name: str
    colors: tuple[PaletteColor, ...]
    source: str = ""

    def __len__(self) -> int:
        return len(self.colors)

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.colors]

    def index(self, name: str) -> int:
        return self.names.index(name)

    def device_u8(self) -> np.ndarray:
        return np.array([c.device for c in self.colors], dtype=np.uint8)

    def perceived_u8(self) -> np.ndarray:
        return np.array([c.perceived for c in self.colors], dtype=np.uint8)

    def perceived_linear(self) -> FloatArray:
        return u8_to_linear(self.perceived_u8())

    def perceived_oklab(self) -> FloatArray:
        return linear_to_oklab(self.perceived_linear())

    def white_index(self) -> int:
        """The paper white. Not simply the lightest ink: on Spectra 6 the
        yellow ink is lighter than the white one."""
        if "white" in self.names:
            return self.index("white")
        lab = self.perceived_oklab()
        return int(np.argmax(lab[:, 0] - 2.0 * np.hypot(lab[:, 1], lab[:, 2])))

    def black_index(self) -> int:
        if "black" in self.names:
            return self.index("black")
        return int(np.argmin(self.perceived_oklab()[:, 0]))

    def neutral_range(self) -> tuple[float, float]:
        """OKLab lightness of the panel's black and white."""
        lab = self.perceived_oklab()
        return float(lab[self.black_index(), 0]), float(lab[self.white_index(), 0])

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source": self.source,
            "colors": [
                {"name": c.name, "device": list(c.device), "perceived": list(c.perceived)}
                for c in self.colors
            ],
        }

    @classmethod
    def from_json(cls, data: dict) -> Palette:
        return cls(
            name=data["name"],
            source=data.get("source", ""),
            colors=tuple(
                PaletteColor(
                    name=c["name"],
                    device=tuple(c["device"]),
                    perceived=tuple(c["perceived"]),
                )
                for c in data["colors"]
            ),
        )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> Palette:
        return cls.from_json(json.loads(path.read_text()))

    def subset(self, names: list[str] | None) -> Palette:
        """Restrict to some inks, e.g. ["black", "white"] for drawings."""
        if not names:
            return self
        unknown = set(names) - set(self.names)
        if unknown:
            raise ValueError(f"unknown inks {sorted(unknown)}; palette has {self.names}")
        return Palette(
            name=f"{self.name}[{','.join(names)}]",
            source=self.source,
            colors=tuple(c for c in self.colors if c.name in names),
        )

    def nominal(self) -> Palette:
        """The inks as ideal colours (perceived = device): the picture's own
        colours, before any correction for the panel."""
        return Palette(
            name=f"{self.name}-nominal",
            source="nominal RGB values",
            colors=tuple(PaletteColor(c.name, c.device, c.device) for c in self.colors),
        )

    def with_perceived(self, perceived: dict[str, RGB], *, name: str, source: str) -> Palette:
        return Palette(
            name=name,
            source=source,
            colors=tuple(
                PaletteColor(c.name, c.device, perceived.get(c.name, c.perceived))
                for c in self.colors
            ),
        )


# Measurements of smaller E Ink Spectra 6 panels published with
# aitjcize/epaper-image-convert (MIT). Still the reference that calibration
# normalises white against, so the scale of every palette stays comparable.
SPECTRA6 = Palette(
    name="spectra6-reference",
    source="aitjcize/epaper-image-convert Spectra 6 measured palette",
    colors=(
        PaletteColor("black", (0, 0, 0), (2, 2, 2)),
        PaletteColor("white", (255, 255, 255), (190, 190, 190)),
        PaletteColor("yellow", (255, 255, 0), (205, 202, 0)),
        PaletteColor("red", (255, 0, 0), (135, 19, 0)),
        PaletteColor("blue", (0, 0, 255), (5, 64, 158)),
        PaletteColor("green", (0, 255, 0), (39, 102, 60)),
    ),
)

# Treats the inks as if they were ideal RGB primaries: what naive converters
# (and apparently the stock pipeline) assume. Useful for A/B comparisons.
SPECTRA6_THEORETICAL = Palette(
    name="spectra6-theoretical",
    source="nominal RGB values",
    colors=tuple(PaletteColor(c.name, c.device, c.device) for c in SPECTRA6.colors),
)

# The EM32DX itself, measured from a photo of the `palette` chart under a
# daylight lamp (experiment E5, firmware S-RSEDWWC-1130.7). Its black is bluish
# and its yellow darker than the reference panel's. The default palette.
EM32DX = Palette(
    name="em32dx",
    source="EM32DX palette chart photographed under a daylight lamp, 2026-10-25",
    colors=(
        PaletteColor("black", (0, 0, 0), (18, 14, 30)),
        PaletteColor("white", (255, 255, 255), (190, 190, 190)),
        PaletteColor("yellow", (255, 255, 0), (199, 172, 0)),
        PaletteColor("red", (255, 0, 0), (135, 0, 3)),
        PaletteColor("blue", (0, 0, 255), (25, 91, 174)),
        PaletteColor("green", (0, 255, 0), (49, 103, 75)),
    ),
)

BUILTIN = {p.name: p for p in (EM32DX, SPECTRA6, SPECTRA6_THEORETICAL)}


def get_palette(name_or_path: str | Path | None) -> Palette:
    if not name_or_path:
        return EM32DX
    if str(name_or_path) in BUILTIN:
        return BUILTIN[str(name_or_path)]
    return Palette.load(Path(name_or_path))
