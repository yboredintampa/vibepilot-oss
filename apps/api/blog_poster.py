#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Blog runner for Vibepilot / Sunny Side Pool Co..

Design:
- Primary LLM: Replicate (REPLICATE_LLM)
- Fallback LLM: local phi3 (via phi3_wrapper) *only if* Replicate fails or is unavailable.
  This keeps the architecture future-proof for private/on-device deployments.

Flow:
1. Build a strong prompt for a long-form pool blog post.
2. Call Replicate LLM to generate the blog content.
3. If Replicate errors or returns nothing, try phi3_wrapper (if present).
4. Enforce a minimum word count with a few retry attempts (on Replicate).
5. Generate a hero image via image_prompt_manager (image model = Replicate).
6. Write:
     /app/posts/YYYYMMDD_HHMMSS_blog.md           (blog content)
     /app/posts/YYYYMMDD_HHMMSS_blog.prompt.txt   (image prompt used)
     /app/posts/YYYYMMDD_HHMMSS_blog.json         (metadata: paths, word count, etc.)
7. Print a single [OK] line for cron/docker logs.

This script does NOT post directly to socials.
Later, another service can:
- Publish the .md to the business website
- Use the .json to build social posts that link back to the blog URL.
"""

from __future__ import annotations

import os
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

import replicate
from image_prompt_manager import generate_image

# Optional phi3 fallback (if module exists)
try:
    from phi3_wrapper import generate_caption as phi3_generate_caption  # type: ignore
except ImportError:  # pragma: no cover
    phi3_generate_caption = None  # type: ignore

# -------------------------------------------------------------------
# Logging (UTC)
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [UTC] %(message)s",
)
logging.Formatter.converter = time.gmtime  # log timestamps in UTC
log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Environment
# -------------------------------------------------------------------
POSTS_DIR = Path(os.getenv("POSTS_DIR", "/app/posts")).resolve()
CATEGORY = os.getenv("BLOG_CATEGORY", "blog")

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
REPLICATE_LLM = os.getenv("REPLICATE_LLM", "meta/meta-llama-3-8b-instruct")
CAPTION_TEMP = float(os.getenv("CAPTION_TEMP", "0.9"))

# Blog-specific length targets
BLOG_WORD_TARGET = int(os.getenv("BLOG_WORD_TARGET", "800"))
BLOG_MIN_WORDS = int(os.getenv("BLOG_MIN_WORDS", "400"))
BLOG_MAX_RETRIES = int(os.getenv("BLOG_MAX_RETRIES", "3"))


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _word_count(text: str) -> int:
    return len(str(text).strip().split())


def _get_replicate_client() -> replicate.Client:
    if not REPLICATE_API_TOKEN:
        raise RuntimeError("REPLICATE_API_TOKEN is missing")
    return replicate.Client(api_token=REPLICATE_API_TOKEN)


def _normalize_llm_output(output: Any) -> str:
    """
    Replicate text models may return:
      - a string
      - a list of strings
      - a dict with an 'output' key, etc.

    We collapse that to a single string.
    """
    if output is None:
        return ""

    if isinstance(output, str):
        return output

    if isinstance(output, list):
        # Join list elements (e.g. streaming chunks)
        return "".join(str(x) for x in output)

    if isinstance(output, dict):
        # Common pattern: { "output": "..."/[...]}
        inner = output.get("output")
        if isinstance(inner, str):
            return inner
        if isinstance(inner, list):
            return "".join(str(x) for x in inner)

    # Fallback: string-ify
    return str(output)


def _build_blog_prompt(category: str) -> str:
    """
    Build the instruction for the LLM.

    NOTE:
    - This is written with a pool-service business in mind (a pool service business) but structured so later
      you can swap in tenant-specific context (e.g., plumber in Ohio).
    """
    return f"""
You are an expert content writer for a residential pool service company in Sunnyvale, Florida
called "Sunny Side Pool Co.". Write a detailed, helpful, and slightly persuasive
blog post for homeowners.

Requirements:
- Topic style: long-form '{category}' pool-care article.
- Audience: Florida residential pool owners (heat, storms, heavy bather load).
- Tone: confident, clear, no fluff; practical advice with light authority.
- Length: at least {BLOG_MIN_WORDS} words (aim for about {BLOG_WORD_TARGET} words).
- Avoid: emojis, hashtags, obvious sales pitches, or mentioning that you are an AI.
- Include: real-world scenarios (storm clean-up, algae prevention, filter care, etc.),
  subtle reasons why hiring a pro like Sunny Side Pool Co. is safer and more reliable
  than DIY guesswork.

Write the post as a single, clean article suitable for a blog page.
"""


def _call_replicate_blog(category: str) -> str:
    client = _get_replicate_client()
    prompt = _build_blog_prompt(category)

    log.info(
        "[blog_poster] Calling Replicate LLM=%s for blog content (target=%s words)...",
        REPLICATE_LLM,
        BLOG_WORD_TARGET,
    )

    output = client.run(
        REPLICATE_LLM,
        input={
            "prompt": prompt,
            "max_tokens": BLOG_WORD_TARGET * 2,  # generous cap
            "temperature": CAPTION_TEMP,
        },
    )

    text = _normalize_llm_output(output)
    return text.strip()


def _call_phi3_fallback(category: str) -> str:
    """
    Optional local fallback via phi3_wrapper, if present.
    If phi3_wrapper is not configured, this returns an empty string.
    """
    if phi3_generate_caption is None:
        log.warning(
            "[blog_poster] phi3_wrapper not available; cannot use fallback."
        )
        return ""

    try:
        log.info("[blog_poster] Using phi3_wrapper fallback for blog content...")
        caption = phi3_generate_caption(category) or ""
        return caption.strip()
    except Exception as exc:  # pragma: no cover
        log.exception("[blog_poster] phi3 fallback failed: %s", exc)
        return ""


def _generate_longform_caption(category: str) -> str:
    """
    Main blog content generator:
    - Tries Replicate up to BLOG_MAX_RETRIES times (length-checked).
    - If Replicate repeatedly fails or produces nothing, uses phi3 fallback (if present).
    """
    last_caption: Optional[str] = None

    # 1) Replicate primary path with retries
    for attempt in range(1, BLOG_MAX_RETRIES + 1):
        try:
            log.info(
                "[blog_poster] Generating blog caption via Replicate "
                "(attempt %s/%s)...",
                attempt,
                BLOG_MAX_RETRIES,
            )
            caption = _call_replicate_blog(category)
        except Exception as exc:
            log.exception(
                "[blog_poster] Replicate error on attempt %s/%s: %s",
                attempt,
                BLOG_MAX_RETRIES,
                exc,
            )
            caption = ""

        if not caption:
            log.warning(
                "[blog_poster] Replicate returned empty caption (attempt %s/%s).",
                attempt,
                BLOG_MAX_RETRIES,
            )
            continue

        last_caption = caption
        wc = _word_count(caption)
        log.info("[blog_poster] Replicate caption word count: %s", wc)

        if wc >= BLOG_MIN_WORDS:
            log.info(
                "[blog_poster] Caption meets minimum length (%s words).",
                BLOG_MIN_WORDS,
            )
            return caption

        log.warning(
            "[blog_poster] Caption too short (%s words, min=%s). Retrying...",
            wc,
            BLOG_MIN_WORDS,
        )

    # 2) Fallback to phi3 if Replicate never produced a satisfactory caption
    log.warning(
        "[blog_poster] Replicate did not produce a satisfactory caption. "
        "Attempting phi3 fallback..."
    )
    fallback_caption = _call_phi3_fallback(category)
    if fallback_caption:
        return fallback_caption

    # 3) Final resort: use the last Replicate caption, even if short/empty
    log.warning(
        "[blog_poster] Using last Replicate caption even though it may be short."
    )
    return last_caption or ""


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def main() -> None:
    _ensure_dir(POSTS_DIR)

    ts = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
    base_name = f"{ts}_{CATEGORY}"

    md_path = POSTS_DIR / f"{base_name}.md"
    pr_path = POSTS_DIR / f"{base_name}.prompt.txt"
    meta_path = POSTS_DIR / f"{base_name}.json"

    # 1) Generate longform blog content
    caption = _generate_longform_caption(CATEGORY)
    if not caption.strip():
        log.error("[blog_poster] Empty caption generated; aborting.")
        return

    # 2) Build a simple image prompt from the blog body
    #    (image_prompt_manager will refine this into a model-specific scene prompt)
    img_prompt = (
        "Hero image for a Florida residential pool-care blog article: "
        "clean, clear pool water, subtle equipment pad in the background, "
        "warm light, safe family-friendly backyard. Match the mood of this article "
        "without including text in the image."
    )

    # 3) Generate hero image using image_prompt_manager
    image_path = ""
    try:
        log.info(
            "[blog_poster] Calling generate_image for category=%s (blog hero)...",
            CATEGORY,
        )
        image_path = generate_image(
            category=CATEGORY,
            caption_or_prompt=img_prompt,
            has_caption_context=True,
        ) or ""
    except Exception as exc:
        log.exception("[blog_poster] Error generating hero image: %s", exc)
        image_path = ""

    # 4) Write files
    md_path.write_text(caption, encoding="utf-8")
    pr_path.write_text(img_prompt, encoding="utf-8")

    meta = {
        "category": CATEGORY,
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "markdown_path": str(md_path),
        "image_prompt_path": str(pr_path),
        "image_path": image_path,
        "word_count": _word_count(caption),
        "llm_primary": "replicate",
        "llm_fallback": "phi3" if phi3_generate_caption is not None else None,
    }
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 5) Greppable line for cron/docker logs
    print(
        f"[OK] blog_poster wrote {md_path}, {pr_path} and {meta_path} "
        f"(image_path={image_path or 'NONE'})"
    )


if __name__ == "__main__":
    main()
