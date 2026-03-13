"""Shared Pillow rendering utilities for Betty visual cards.

All cards are 800x450 (or 800x600 for wellness) with consistent branding.
"""

import logging
import os
import time
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

CARDS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "cards")
os.makedirs(CARDS_DIR, exist_ok=True)

# Try to load a nice font, fall back to default
_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _font_cache:
        # Try common Windows fonts
        font_names = (
            ["arialbd.ttf", "arial.ttf"] if bold
            else ["arial.ttf", "calibri.ttf"]
        )
        for name in font_names:
            try:
                _font_cache[key] = ImageFont.truetype(name, size)
                return _font_cache[key]
            except OSError:
                continue
        _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


# Colour palette
COLORS = {
    "bg_blue": (30, 58, 95),
    "bg_blue_light": (45, 85, 135),
    "bg_orange": (180, 80, 30),
    "bg_red": (160, 40, 40),
    "bg_green": (30, 100, 60),
    "white": (255, 255, 255),
    "white_80": (255, 255, 255, 204),
    "white_60": (255, 255, 255, 153),
    "yellow": (255, 210, 70),
    "green": (100, 220, 130),
    "red": (255, 100, 100),
    "orange": (255, 165, 60),
    "light_grey": (200, 210, 220),
    "dark_overlay": (0, 0, 0, 80),
}

# Facility icons (simple text labels since we can't bundle icon files)
FACILITY_LABELS = {
    "toilets": "WC",
    "water": "H2O",
    "fuel": "FUEL",
    "food": "FOOD",
    "showers": "SHOWER",
    "shade": "SHADE",
}


def create_card(width: int, height: int, bg_color: tuple) -> Image.Image:
    """Create a card canvas with background."""
    img = Image.new("RGBA", (width, height), bg_color + (255,))
    return img


def draw_gradient_overlay(img: Image.Image, start_alpha: int = 0,
                          end_alpha: int = 100) -> None:
    """Draw a vertical gradient overlay for depth."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    for y in range(h):
        alpha = int(start_alpha + (end_alpha - start_alpha) * y / h)
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    img.alpha_composite(overlay)


def draw_header(draw: ImageDraw.Draw, y: int, title: str,
                subtitle: str = "", width: int = 800) -> int:
    """Draw a card header. Returns new y position."""
    font_title = _get_font(28, bold=True)
    font_sub = _get_font(16)

    draw.text((40, y), title, fill=COLORS["white"], font=font_title)
    y += 38
    if subtitle:
        draw.text((40, y), subtitle, fill=COLORS["white_60"], font=font_sub)
        y += 24
    return y + 10


def draw_badge(draw: ImageDraw.Draw, x: int, y: int, text: str,
               bg_color: tuple, text_color: tuple = None) -> int:
    """Draw a rounded badge. Returns badge width."""
    if text_color is None:
        text_color = COLORS["white"]
    font = _get_font(14, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 12, 6
    draw.rounded_rectangle(
        [x, y, x + tw + pad_x * 2, y + th + pad_y * 2],
        radius=12, fill=bg_color,
    )
    draw.text((x + pad_x, y + pad_y), text, fill=text_color, font=font)
    return tw + pad_x * 2


def draw_text_wrapped(draw: ImageDraw.Draw, x: int, y: int, text: str,
                      font: ImageFont.FreeTypeFont, fill: tuple,
                      max_width: int) -> int:
    """Draw word-wrapped text. Returns new y position."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    for line in lines:
        draw.text((x, y), line, fill=fill, font=font)
        bbox = draw.textbbox((0, 0), line, font=font)
        y += bbox[3] - bbox[1] + 6
    return y


def draw_divider(draw: ImageDraw.Draw, y: int, width: int = 800) -> int:
    """Draw a subtle divider line."""
    draw.line([(40, y), (width - 40, y)], fill=(255, 255, 255, 40), width=1)
    return y + 15


def save_card(img: Image.Image, driver_id: str, card_type: str) -> str:
    """Save card image and return the URL path."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{driver_id}_{card_type}_{ts}.png"
    filepath = os.path.join(CARDS_DIR, filename)
    img.save(filepath, "PNG")
    url_path = f"/static/cards/{filename}"
    logger.info("Card saved: %s", filepath)
    return url_path
