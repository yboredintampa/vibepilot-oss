# /opt/vibepilot/apps/api/meme_overlay.py

import textwrap
from pathlib import Path
from typing import Dict, Any

from PIL import Image, ImageDraw, ImageFont

# === Per-category style config ============================================

CATEGORY_STYLES: Dict[str, Dict[str, Any]] = {
    # "educational" meme: clean, readable, slightly smaller text
    "educational": {
        "font_paths": [
            "/opt/vibepilot/assets/fonts/Poppins-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "font_size_factor": 18,   # width // factor
        "max_chars_per_line": 44,
        "fill": (255, 255, 255),
        "stroke_fill": (0, 40, 80),
        "bg_fill": (0, 0, 0, 190),
    },

    # "tip" meme: big, punchy headline style
    "tip": {
        "font_paths": [
            "/opt/vibepilot/assets/fonts/BebasNeue-Regular.ttf",
            "/opt/vibepilot/assets/fonts/Anton-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "font_size_factor": 14,
        "max_chars_per_line": 26,
        "fill": (255, 255, 255),
        "stroke_fill": (0, 0, 0),
        "bg_fill": (0, 0, 0, 170),
    },

    # Generic "meme" / jokes: a little more playful, medium line length
    "meme": {
        "font_paths": [
            "/opt/vibepilot/assets/fonts/PermanentMarker-Regular.ttf",
            "/opt/vibepilot/assets/fonts/Anton-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "font_size_factor": 16,
        "max_chars_per_line": 30,
        "fill": (255, 255, 255),
        "stroke_fill": (0, 0, 0),
        "bg_fill": (0, 0, 0, 180),
    },

    # Promo / CTA heavy posts
    "promo": {
        "font_paths": [
            "/opt/vibepilot/assets/fonts/Anton-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "font_size_factor": 15,
        "max_chars_per_line": 32,
        "fill": (255, 255, 0),
        "stroke_fill": (0, 0, 0),
        "bg_fill": (0, 0, 0, 210),
    },

    # Fallback/default
    "default": {
        "font_paths": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "font_size_factor": 18,
        "max_chars_per_line": 34,
        "fill": (255, 255, 255),
        "stroke_fill": (0, 0, 0),
        "bg_fill": (0, 0, 0, 190),
    },
}


def _pick_style(category: str) -> Dict[str, Any]:
    c = (category or "").lower()
    for key in CATEGORY_STYLES.keys():
        if key == "default":
            continue
        if key in c:
            return CATEGORY_STYLES[key]
    return CATEGORY_STYLES["default"]


def _load_font(font_paths, font_size: int) -> ImageFont.FreeTypeFont:
    for p in font_paths:
        path = Path(p)
        if path.exists():
            return ImageFont.truetype(str(path), font_size)
    # last-resort fallback
    return ImageFont.load_default()


def add_text_overlay(
    image_path: str,
    output_path: str | None,
    text: str,
    category: str = "",
    top_margin_ratio: float = 0.07,
    bottom_margin_ratio: float = 0.07,
) -> str:
    """
    Adds text overlay with a style chosen by `category`.

    - Different font + char wrapping per category (educational, tip, meme, promo).
    - Clean rectangle background for readability.
    - White text with dark stroke by default.
    """

    style = _pick_style(category)
    img = Image.open(image_path).convert("RGB")
    width, height = img.size

    font_size_factor = style.get("font_size_factor", 18)
    base_font_size = max(20, width // font_size_factor)
    font_paths = style.get("font_paths", [])
    fill = style.get("fill", (255, 255, 255))
    stroke_fill = style.get("stroke_fill", (0, 0, 0))
    bg_fill = style.get("bg_fill", (0, 0, 0, 190))
    max_chars_per_line = style.get("max_chars_per_line", 34)

    font = _load_font(font_paths, base_font_size)
    draw = ImageDraw.Draw(img)

    # Wrap text into lines
    wrapped_lines: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(paragraph, width=max_chars_per_line))

    line_height = int(base_font_size * 1.3)
    text_block_height = int(line_height * len(wrapped_lines))

    top_y = int(height * (1.0 - bottom_margin_ratio) - text_block_height)

    padding_x = int(width * 0.035)
    padding_y = int(height * 0.015)

    rect_top = max(int(height * top_margin_ratio), top_y - padding_y)
    rect_bottom = min(
        height - int(height * bottom_margin_ratio),
        top_y + text_block_height + padding_y,
    )
    rect_left = padding_x
    rect_right = width - padding_x

    # Background rectangle behind the text
    draw.rounded_rectangle(
        [rect_left, rect_top, rect_right, rect_bottom],
        radius=18,
        fill=bg_fill,
    )

    # Draw lines centered
    current_y = rect_top + padding_y
    for line in wrapped_lines:
        if not line:
            current_y += line_height * 0.5
            continue
        # ImageDraw.textsize() was removed in Pillow 10; textbbox() is the supported API.
        left, _, right, _ = draw.textbbox((0, 0), line, font=font, stroke_width=3)
        w = right - left
        x = (width - w) // 2

        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill,
            stroke_width=3,
            stroke_fill=stroke_fill,
        )
        current_y += line_height

    if not output_path:
        output_path = image_path

    img.save(output_path, format="JPEG", quality=95)
    return output_path
