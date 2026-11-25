"""The card the panel shows before its first picture."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .layout import PANEL_HEIGHT, PANEL_WIDTH

W, H = PANEL_WIDTH, PANEL_HEIGHT


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def welcome_card(orientation_hint: str = "") -> Image.Image:
    """Placeholder content: pure black text on white."""
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"  # no anti-aliasing: text stays pure black ink
    draw.text((W // 2, H // 2 - 40), "Frame", fill=(0, 0, 0), font=_font(160), anchor="mm")
    draw.text(
        (W // 2, H // 2 + 110),
        orientation_hint or "Waiting for the first picture",
        fill=(0, 0, 0),
        font=_font(48),
        anchor="mm",
    )
    return img
