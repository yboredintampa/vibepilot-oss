#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils_card: render clean tip cards over images (no model text).
- Sanitizes caption (ASCII + basic punctuation, smart quotes -> ASCII)
- Optional keyword enforcement (e.g., "filter pressure gauge")
- Draws a rounded rectangle + title + bullet list or paragraph
"""

from __future__ import annotations
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont
import textwrap, re, os, io

# Fonts: DejaVu is present on Ubuntu; fall back to PIL default if missing.
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG_PATH  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

SAFE_CHARS = re.compile(r"[^A-Za-z0-9\s\-\.,:'%()/\[\]°]+")  # strip weird glyphs
WS_CLEAN   = re.compile(r"\s{2,}")

def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def sanitize(text: str) -> str:
    # normalize quotes/dashes
    repl = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    # remove junk chars
    text = SAFE_CHARS.sub("", text)
    # collapse whitespace
    text = WS_CLEAN.sub(" ", text).strip()
    return text

def force_terms(text: str) -> str:
    # Force “filter pressure gauge” wording if “filter gauge” present
    text = re.sub(r"\bfilter\s+gauge\b", "filter pressure gauge", text, flags=re.I)
    return text

def split_heading_body(caption: str) -> Tuple[str, str]:
    # If caption starts with "Today's tip:" (any case), split there
    m = re.match(r"(?i)\s*today'?s tip:\s*(.*)", caption)
    if m:
        return "TODAY’S TIP:", m.group(1).strip()
    # default
    return "TODAY’S TIP:", caption

def wrap_lines(text: str, width_chars: int = 54) -> list[str]:
    # Detect numbered/bulleted lines and preserve them
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            lines.append("")
            continue
        if re.match(r"^(\d+[\).]|[-*•])\s+", raw):
            # indent wrapped bullets a bit
            wrapped = textwrap.wrap(raw, width=width_chars,
                                    subsequent_indent="   ")
            lines.extend(wrapped)
        else:
            lines.extend(textwrap.wrap(raw, width=width_chars))
    return lines

def draw_card(base_img: Image.Image, caption: str) -> Image.Image:
    img = base_img.convert("RGB")
    W, H = img.size

    # Sanitize + enforce wording
    caption = force_terms(sanitize(caption))

    title, body = split_heading_body(caption)

    # Fonts sized relative to image width
    title_font = _font(FONT_BOLD_PATH, max(28, W // 18))
    body_font  = _font(FONT_REG_PATH,  max(20, W // 28))

    # Layout
    margin = W // 18
    card_pad = W // 28
    radius = max(16, W // 40)

    # Text blocks
    body_lines = wrap_lines(body, width_chars= max(42, W // 20))
    body_text  = "\n".join(body_lines)

    # Measure
    draw = ImageDraw.Draw(img)
    t_w, t_h = draw.multiline_textbbox((0,0), title, font=title_font)[2:]
    b_w, b_h = draw.multiline_textbbox((0,0), body_text, font=body_font, spacing=6)[2:]

    card_w = min(W - 2*margin, max(t_w, b_w) + 2*card_pad)
    card_h = t_h + 12 + b_h + 2*card_pad

    # Card position (bottom-center)
    x0 = (W - card_w) // 2
    y0 = H - card_h - margin

    # Semi-opaque backdrop
    card = Image.new("RGBA", (card_w, card_h), (245, 250, 255, 228))
    # rounded rectangle
    card_draw = ImageDraw.Draw(card)
    card_draw.rounded_rectangle([0,0,card_w-1,card_h-1], radius=radius, fill=(245,250,255,228), outline=(0,0,0,40), width=2)

    # Text colors
    title_color = (0, 74, 173)  # deep blue
    body_color  = (15, 23, 42)  # slate

    # Draw text
    tx = card_pad
    ty = card_pad
    card_draw.text((tx, ty), title, font=title_font, fill=title_color)
    ty += t_h + 12
    card_draw.multiline_text((tx, ty), body_text, font=body_font, fill=body_color, spacing=6)

    # Composite
    img.alpha_composite(card, (x0, y0)) if img.mode == "RGBA" else img.paste(card.convert("RGB"), (x0, y0), card)

    return img

def render_tip_card_on(jpeg_path: str, caption: str, out_path: str) -> str:
    base = Image.open(jpeg_path)
    out  = draw_card(base, caption)
    out.save(out_path, "JPEG", quality=92)
    return out_path
