import os, re
from typing import Callable, Tuple

# ---------- helpers ----------
def _bool(key: str, default: bool=False) -> bool:
    v = os.getenv(key, str(int(default))).strip().lower()
    return v in ("1", "true", "yes", "on")

def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)).strip())
    except Exception:
        return default

def _strlist(key: str, default: str="") -> list[str]:
    raw = os.getenv(key, default)
    return [s.strip().lower() for s in raw.split(",") if s.strip()]

def _catkey(prefix: str, category: str) -> str:
    return f"{prefix}_{category.upper()}"

# ---------- global + per-category config ----------
STRICT = _bool("VP_STRICT_TIPS", True)
STRICT_CATS = set([c for c in _strlist("VP_TIP_STRICT_CATEGORIES", "blog,educational")])

# global defaults
G_MIN_WORDS        = _int("VP_TIP_MIN_WORDS", 40)
G_REQUIRE_TEMPLATE = _bool("VP_TIP_REQUIRE_TEMPLATE", True)
G_REQUIRE_STRUCT   = _bool("VP_TIP_REQUIRE_STRUCTURE", True)
G_REQ_KW           = _strlist("VP_TIP_REQUIRED_KW", "")

TEASER_PAT = re.compile(r"\bwhy\s+[^.?!]{0,80}\s+matters\b", re.I)

def _effective_params(category: str) -> tuple[int, bool, bool, list[str]]:
    """Resolve per-category overrides with global fallbacks."""
    mw  = _int(_catkey("VP_TIP_MIN_WORDS", category), G_MIN_WORDS)
    rti = _bool(_catkey("VP_TIP_REQUIRE_TEMPLATE", category), G_REQUIRE_TEMPLATE)
    rst = _bool(_catkey("VP_TIP_REQUIRE_STRUCTURE", category), G_REQUIRE_STRUCT)
    kw  = _strlist(_catkey("VP_TIP_REQUIRED_KW", category), ",".join(G_REQ_KW))
    return mw, rti, rst, kw

# ---------- validators ----------
def is_actionable_tip(
    caption: str,
    *,
    min_words: int,
    require_template: bool,
    require_structure: bool,
    required_kw: list[str],
) -> Tuple[bool, str]:
    text = (caption or "").strip()
    if not text:
        return False, "empty"

    # word count
    if len(re.findall(r"\w+", text)) < min_words:
        return False, "too_few_words"

    # opening template like "Today's tip:"
    if require_template:
        if not re.search(r"^(today[’']?s tip|pro tip|tip of the day)[:\-]\s+\S", text.lower()):
            return False, "missing_tip_intro"

    # structure: bullet/number OR ≥2 sentences
    if require_structure:
        structured = re.search(r"^\s*(?:\d+[\.\)]|[-•])\s+\S", text)
        two_sentences = len(re.findall(r"[.!?]", text)) >= 2
        if not (structured or two_sentences):
            return False, "not_structured"

    # required keywords (any)
    if required_kw:
        low = text.lower()
        if not any(k in low for k in required_kw):
            return False, "missing_keywords"

    # avoid teaser “why X matters” unless it also teaches
    if TEASER_PAT.search(text.lower()) and "how to" not in text.lower():
        return False, "teaser_without_howto"

    return True, "ok"

FALLBACK = (
    "Today’s tip: check your filter gauge weekly. When PSI rises 20–25% above your clean baseline, "
    "it’s time to backwash sand/DE or clean cartridges. 1) Turn off pump. 2) Relieve pressure at the "
    "filter air-bleed. 3) Backwash 2–3 minutes (or hose off cartridges) until water runs clear. "
    "4) Restart pump and note the new PSI in your log. Consistent high PSI = clogged filter or flow issue."
)

def validate_or_regen(
    caption: str,
    category: str,
    regen_fn: Callable[[str], str],
    max_retries: int = 6,
) -> Tuple[str, bool, str, int]:
    """Apply guard only if STRICT and category is configured in VP_TIP_STRICT_CATEGORIES."""
    if not (STRICT and category in STRICT_CATS):
        return caption, True, "ok", 0

    min_words, req_template, req_struct, req_kw = _effective_params(category)
    ok, reason = is_actionable_tip(
        caption,
        min_words=min_words,
        require_template=req_template,
        require_structure=req_struct,
        required_kw=req_kw,
    )

    tries = 0
    while not ok and tries < max_retries:
        tries += 1
        hint = (
            f'Rewrite as an actionable pool-care tip for category "{category}". '
            f'Start with "Today’s tip:" then give specific, numbered steps. '
            f"At least {min_words} words; avoid pure teasers; include practical verbs. "
            + (f"Try to include one of: {', '.join(req_kw)}. " if req_kw else "")
            + ("Use a bullet or a number list, or at least two sentences. " if req_struct else "")
        )
        caption = regen_fn(hint)
        ok, reason = is_actionable_tip(
            caption,
            min_words=min_words,
            require_template=req_template,
            require_structure=req_struct,
            required_kw=req_kw,
        )

    if not ok:
        return FALLBACK, False, reason, tries
    return caption, True, "ok", tries
