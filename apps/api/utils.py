import os
import re
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Base paths (relative to current working dir by default)
LOG_DIR = os.getenv("VIBE_LOG_DIR", "logs")
POSTS_DIR = os.getenv("VIBE_POSTS_DIR", "posts")
BLACKLIST_PATH = os.getenv("VIBE_BLACKLIST_PATH", "blacklist.txt")

# How many days back we treat as "recent" for repost prevention
REPOST_WINDOW_DAYS = int(os.getenv("REPOST_WINDOW_DAYS", "7"))

# Make sure directories exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(POSTS_DIR, exist_ok=True)

# Category-level guardrail keywords
GUARDRAIL_KEYWORDS: Dict[str, List[str]] = {
    # Spicier stuff gets extra guardrails
    "meme": [
        "politics",
        "racist",
        "slur",
        "violence",
        "nudity",
        "sex",
        "nsfw",
    ],
    "educational": ["nsfw", "sex", "drugs", "conspiracy"],
    "confrontational": ["hate speech", "bigotry", "racist", "slur"],
    "realistic": [],
    "comedic": [],
    "persuasive": [],
    "authoritative": [],
    "blog": [],
    # Global catch-all (applied on top of category-specific)
    "default": [
        "suicide",
        "self-harm",
        "kill myself",
        "murder",
        "extremist",
    ],
}


# -------------------------------------------------------------------
# Blacklist helpers
# -------------------------------------------------------------------
def get_blacklist() -> List[str]:
    """
    Load a simple line-based blacklist from disk.

    Each non-empty line is a lowercase substring we don't want
    in generated captions (e.g. competitor names, off-brand topics).
    """
    if os.path.exists(BLACKLIST_PATH):
        with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    return []


def _contains_any(text: str, terms: List[str]) -> bool:
    text = text.lower()
    for t in terms:
        t = t.strip().lower()
        if t and t in text:
            return True
    return False


# -------------------------------------------------------------------
# Guardrails
# -------------------------------------------------------------------
def violates_guardrails(caption: str, category: str) -> bool:
    """
    Return True if the caption violates either:
      - The dynamic blacklist (blacklist.txt)
      - Category-specific guardrail keywords
      - Global default guardrails
    """
    if not caption:
        return False

    text = caption.lower()
    cat_key = (category or "").lower().strip()

    # 1) Dynamic blacklist (owner-configurable)
    blacklist_terms = get_blacklist()
    if _contains_any(text, blacklist_terms):
        return True

    # 2) Category-specific guardrails
    category_terms = GUARDRAIL_KEYWORDS.get(cat_key, [])
    if _contains_any(text, category_terms):
        return True

    # 3) Global defaults
    default_terms = GUARDRAIL_KEYWORDS.get("default", [])
    if _contains_any(text, default_terms):
        return True

    return False


# -------------------------------------------------------------------
# Repost prevention
# -------------------------------------------------------------------
def already_posted_recently(caption: str, days: Optional[int] = None) -> bool:
    """
    Check if an identical caption (by SHA-256 hash) was posted
    within the last `days` days (defaults to REPOST_WINDOW_DAYS).

    We scan JSON files in POSTS_DIR and compare caption_hash + timestamp.
    """
    if not caption:
        return False

    if days is None:
        days = REPOST_WINDOW_DAYS

    caption_hash = hashlib.sha256(caption.encode("utf-8")).hexdigest()
    cutoff = datetime.now() - timedelta(days=days)

    if not os.path.isdir(POSTS_DIR):
        return False

    for fname in os.listdir(POSTS_DIR):
        if not fname.endswith(".json"):
            continue

        fpath = os.path.join(POSTS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        if data.get("caption_hash") != caption_hash:
            continue

        ts_str = data.get("timestamp")
        if not ts_str:
            continue

        # Be forgiving on timestamp formats
        dt_obj: Optional[datetime] = None
        for fmt in ("%Y-%m-%dT%H-%M-%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H%M%S"):
            try:
                dt_obj = datetime.strptime(ts_str, fmt)
                break
            except Exception:
                continue

        if not dt_obj:
            continue

        if dt_obj >= cutoff:
            return True

    return False


# -------------------------------------------------------------------
# Save successful post
# -------------------------------------------------------------------
def save_post_to_file(
    caption: str,
    image_path: Optional[str],
    category: str,
    timestamp: str,
) -> None:
    """
    Persist a successful post to disk for:
      - Repost prevention
      - Simple history / debugging
    """
    post_data: Dict[str, Any] = {
        "timestamp": timestamp,
        "caption": caption,
        "caption_hash": hashlib.sha256(caption.encode("utf-8")).hexdigest(),
        "category": category,
        "image_path": image_path or None,
    }

    safe_category = (category or "uncategorized").replace(" ", "_")
    fname = f"{timestamp}_{safe_category}.json"
    fpath = os.path.join(POSTS_DIR, fname)

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(post_data, f, indent=2)


# -------------------------------------------------------------------
# Failure logging
# -------------------------------------------------------------------
def log_failure(
    reason: str,
    caption: Optional[str] = None,
    category: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append a structured JSON line to logs/failures.log so you can
    debug why a given generation path bailed out (guardrail, blacklist,
    repost prevention, model error, etc.).
    """
    entry: Dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H-%M-%S"),
        "reason": reason,
        "category": category,
        "caption": caption,
    }
    if extra:
        entry["extra"] = extra

    fname = os.path.join(LOG_DIR, "failures.log")
    with open(fname, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")





