# /opt/vibepilot/apps/api/phi3_wrapper.py
# Clean, crash-safe caption + prompt helpers (no external deps)

from __future__ import annotations
import datetime as _dt
from collections import OrderedDict
from typing import Optional

def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat() + "Z"

_ALLOWED = {
    "realistic",
    "meme",
    "educational",
    "blog",
    "comedic",
    "persuasive",
}

def _sanitize_category(category: str) -> str:
    c = (category or "").strip().lower()
    return c if c in _ALLOWED else "realistic"

def generate_caption(category: str, extra_hint: Optional[str] = None) -> str:
    """
    Returns a single caption string. Always provides all referenced blocks so
    callers never hit KeyError (e.g., 'Myth').
    """
    cat = _sanitize_category(category)
    hint = (extra_hint or "").strip()

    # Base blocks with guaranteed keys (avoid KeyError)
    blocks = {
        "Hook": "",
        "Tip": "",
        "Myth": "",
        "Why it matters": "",
        "CTA": "",
    }

    if cat in ("educational", "blog"):
        blocks["Hook"] = "Pool tip time 💡"
        blocks["Tip"] = (
            "Check your filter PSI weekly. If it’s 8–10 PSI above clean-start, "
            "it’s time to backwash or clean the cartridge."
        )
        blocks["Myth"] = "“Higher PSI means better flow.” Nope—higher PSI is back-pressure."
        blocks["Why it matters"] = (
            "Running with high PSI strains the pump, wastes energy, and reduces circulation clarity."
        )
        blocks["CTA"] = "If you’re in Sunnyvale, we’ll handle it—message to schedule a quick tune-up."
    elif cat == "meme":
        blocks["Hook"] = "That moment when the pool robot eats your phone charger…"
        blocks["Tip"] = "Pro move: keep cords clear and empty skimmer baskets before a robot run."
        blocks["Myth"] = "“Robots replace maintenance.” Nah—they complement it."
        blocks["Why it matters"] = "You still need chemistry balance and periodic filter care."
        blocks["CTA"] = "Want a set-and-forget plan? We’ve got you."
    elif cat == "comedic":
        blocks["Hook"] = "Your pool when it hears ‘I’ll shock it later’:"
        blocks["Tip"] = "Don’t wait—test today, adjust today."
        blocks["Myth"] = "“More chlorine fixes everything.” Balance > brute force."
        blocks["Why it matters"] = "Right pH + right CYA = chlorine actually works."
        blocks["CTA"] = "Ping us—fast, friendly, no-pressure help."
    elif cat == "persuasive":
        blocks["Hook"] = "You don’t need a pool guy—until you do."
        blocks["Tip"] = "Weekly eyes-on + logs beat crisis cleanups every time."
        blocks["Myth"] = "“Skimming is most of the work.” Chemistry drives clarity."
        blocks["Why it matters"] = "Prevent algae blooms, protect equipment, keep water silky."
        blocks["CTA"] = "Reply ‘START’ and we’ll put your pool on autopilot."
    else:  # realistic (default)
        blocks["Hook"] = "Crystal water comes from quiet consistency."
        blocks["Tip"] = "Rinse cartridges, verify PSI, brush walls, and log readings."
        blocks["Myth"] = "“If it’s clear, it’s balanced.” Not always."
        blocks["Why it matters"] = "Clear-but-imbalanced water can etch, stain, or irritate skin."
        blocks["CTA"] = "We service Sunnyvale daily—DM for a slot."

    if hint:
        blocks["CTA"] += f" ({hint})"

    ordered = OrderedDict((k, v) for k, v in blocks.items() if v.strip())

    parts = []
    for i, (key, val) in enumerate(ordered.items(), start=1):
        parts.append(f"**{i}. {key}.** {val}")
    parts.append(f"_Posted {_now_iso()}_")
    return "\n\n".join(parts)

def generate_image_prompt(category: str, caption: Optional[str] = None) -> str:
    """
    Simple, category-aware prompt builder to pair with images.
    Always returns a non-empty string.
    """
    cat = _sanitize_category(category)
    base = "Ultra-detailed pool service scene, modern residential backyard, clean water, natural lighting"
    if cat == "meme":
        return "Simple meme template, bold top/bottom text area, high contrast, minimal background"
    if cat in ("educational", "blog"):
        return (
            "Clean infographic about pool filter PSI and backwashing, labeled gauges, "
            "clear arrows, easy-to-read typography"
        )
    if cat == "comedic":
        return "Playful cartoon pool with overworked robot vacuum, expressive eyes, bright colors"
    if cat == "persuasive":
        return "Premium lifestyle photo of a pristine backyard pool at sunset, subtle bokeh, aspirational tone"
    # realistic default
    extra = f". Caption context: {caption.strip()}" if caption else ""
    return base + extra
