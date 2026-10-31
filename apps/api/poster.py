import os
import sys
import json
import time
import datetime as dt
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
load_dotenv("/etc/vibepilot/.env")

import random
import dedupe_store
import requests
import replicate

# Training data loader
import random as _random
def load_training_example(category):
    filepath = f"/opt/vibepilot/content/pools_{category}_training.txt"
    try:
        with open(filepath, "r") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        examples = []
        for line in lines:
            if "|" in line:
                parts = line.split("|", 1)
                examples.append({"caption": parts[0].strip(), "image_prompt": parts[1].strip()})
            else:
                examples.append({"caption": line, "image_prompt": line})
        return _random.choice(examples) if examples else {"caption": "Pool service complete", "image_prompt": "pool"}
    except:
        return {"caption": "Pool service complete", "image_prompt": "pool"}

# Import training data loader
try:
    from content.pools_training_unified import load_training_example
except Exception:
    # Fallback if training not available
    def load_training_example(category):
        return {"caption": "Clean pool, clear water.", "image_prompt": "pool"}

# Try relative imports first (inside apps.api), then fall back for older layouts
try:
    from .image_prompt_manager import generate_image
except Exception:
    from image_prompt_manager import generate_image

try:
    from .post_queue import enqueue_post
except Exception:
    from post_queue import enqueue_post

try:
    from .weather_client import describe_weather_for_prompt
except Exception:
    from weather_client import describe_weather_for_prompt

try:
    from . import llm_safety as safety
except ImportError:  # running as top-level modules (Docker: uvicorn main:app)
    import llm_safety as safety


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [UTC] %(message)s",
)
logging.Formatter.converter = time.gmtime
log = logging.getLogger(__name__)

# Environment
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
REPLICATE_LLM = os.getenv("REPLICATE_LLM", "meta/meta-llama-3-8b-instruct")

META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")
META_PAGE_ID = os.getenv("META_PAGE_ID", "")

POST_MODE = os.getenv("POST_MODE", "queue").lower()
DEFAULT_CATEGORY = os.getenv("DEFAULT_CATEGORY", "realistic")

BLOG_WORD_TARGET = int(os.getenv("BLOG_WORD_TARGET", "800"))
MIN_WORDS = int(os.getenv("MIN_WORDS", "40"))

VALID_POST_MODES = {"queue", "direct", "facebook"}

# Category rotation
CATEGORY_ROTATION = os.getenv(
    "CATEGORY_ROTATION",
    "realistic,realistic,educational,persuasive,comedic,confrontational,realistic,meme",
)

ROTATION_STATE_FILE = os.getenv(
    "CATEGORY_ROTATION_STATE_FILE",
    "/app/post_state/category_rotation.json",
)

# Business context
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Sunny Side Pool Co.")
BUSINESS_CITY = os.getenv("BUSINESS_CITY", "Sunnyvale")
BUSINESS_REGION = os.getenv("BUSINESS_REGION", "FL")
BUSINESS_HEMISPHERE = os.getenv("BUSINESS_HEMISPHERE", "north")

WEATHER_CITY = os.getenv("WEATHER_CITY", BUSINESS_CITY)
WEATHER_REGION = os.getenv("WEATHER_REGION", BUSINESS_REGION)

_ENABLE_WEATHER_RAW = os.getenv("ENABLE_WEATHER_CONTEXT", "1").strip()
ENABLE_WEATHER = _ENABLE_WEATHER_RAW not in {"0", "false", "False", ""}


def _ensure_rotation_state_dir() -> None:
    try:
        os.makedirs(os.path.dirname(ROTATION_STATE_FILE), exist_ok=True)
    except Exception:
        pass


def resolve_category(cli_arg: Optional[str]) -> str:
    """Decide which category to use for this run."""
    # Task/topic guard: the category ends up in the LLM prompt, so only the known
    # social-marketing categories are accepted (raises safety.ScopeError otherwise).
    if cli_arg:
        return safety.require_choice(cli_arg, safety.ALLOWED_CATEGORIES, "category")

    seq = [c.strip().lower() for c in CATEGORY_ROTATION.split(",") if c.strip()]
    if not seq:
        return safety.require_choice(DEFAULT_CATEGORY, safety.ALLOWED_CATEGORIES, "category")

    _ensure_rotation_state_dir()
    idx = 0
    try:
        with open(ROTATION_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            idx = int(data.get("idx", 0))
    except Exception:
        idx = 0

    category = seq[idx % len(seq)]

    try:
        with open(ROTATION_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"idx": (idx + 1) % len(seq), "seq": seq}, f)
    except Exception as e:
        log.warning("[poster] Could not persist rotation index: %s", e)

    return safety.require_choice(category, safety.ALLOWED_CATEGORIES, "category")


def _safe_weather_context() -> str:
    """Try to get weather description for prompting. 50% chance to skip."""
    if not ENABLE_WEATHER:
        return ""

    # RANDOMIZATION: Skip weather 50% of the time
    if random.random() > 0.5:
        log.info("[poster] Skipping weather context (randomized)")
        return ""

    try:
        ctx = describe_weather_for_prompt()
        if ctx:
            return str(ctx).strip()
    except TypeError:
        try:
            ctx = describe_weather_for_prompt(
                city=WEATHER_CITY,
                region=WEATHER_REGION,
                hemisphere=BUSINESS_HEMISPHERE,
            )
            if ctx:
                return str(ctx).strip()
        except Exception as exc:
            log.warning("[poster] Weather client failed (with location): %s", exc)
    except Exception as exc:
        log.warning("[poster] Weather client failed: %s", exc)

    return ""


def _get_llm_client() -> replicate.Client:
    if not REPLICATE_API_TOKEN:
        raise RuntimeError("REPLICATE_API_TOKEN is missing")
    return replicate.Client(api_token=REPLICATE_API_TOKEN)


def _normalize_replicate_text(output) -> str:
    """Convert Replicate output to plain string."""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return "".join(str(chunk) for chunk in output)
    if hasattr(output, "__iter__"):
        return "".join(str(chunk) for chunk in output)
    return str(output)


def _strip_preamble(text: str) -> str:
    """Remove common LLM preambles from caption text."""
    if not text:
        return text
    
    text = text.strip()
    
    # Remove entire first line if it contains preamble keywords
    lines = text.split("\n")
    if lines:
        first_line_lower = lines[0].lower()
        preamble_keywords = [
            "here is",
            "here are",
            "caption for",
            "caption:",
            "social media",
            "sunny side pool co."
        ]
        if any(kw in first_line_lower for kw in preamble_keywords):
            # Remove first line entirely
            text = "\n".join(lines[1:]).strip()
    
    # If numbered list (e.g., "1. Caption text"), extract first item only
    if text.startswith("1.") or text.startswith("1)"):
        # Get everything after "1." or "1)" up to next number or newline
        lines = text.split("\n")
        first_item = lines[0]
        # Remove "1." or "1)"
        first_item = first_item.lstrip("1.").lstrip("1)").strip()
        return first_item
    
    return text.strip()


_CAPTION_INSTRUCTIONS = """You write short social media captions for a pool service business.
Use the business details, weather and example captions in the user message only as background
facts and style references.

CRITICAL - AVOID THESE REPETITIVE OPENINGS:
- DO NOT start with "Just finished servicing" or "Just wrapped up"
- DO NOT use "I'm happy to report" or "I'm pleased with"
- DO NOT use "After a morning of servicing"
- DO NOT follow template patterns from previous posts

RULES:
- Under 60 words
- No hashtags, no emojis
- No quotation marks
- Write like a confident local tech, not a marketing bot
- Be specific about pools/water/chemistry where relevant

Return ONLY the caption text, nothing else."""


def _caption_system_prompt() -> str:
    """System prompt: fixed instructions + untrusted-content policy. Never contains secrets."""
    return safety.build_system_prompt(_CAPTION_INSTRUCTIONS)


def _build_caption_prompt(category: str, weather_context: str) -> str:
    """Build the user-side LLM prompt (task context; outside content is in data blocks)."""
    cat = (category or "").lower().strip()

    if "realistic" in cat:
        style_note = (
            "Tone: calm, confident, Florida-local pro. Describe the clean pool "
            "in plain language, no hype, just competence."
        )
    elif "meme" in cat:
        style_note = "Tone: meme-friendly, lightly sarcastic, but keep it understandable."
    elif "educational" in cat:
        style_note = "Tone: clear, teaching-focused, like a friendly pool chemistry nerd."
    elif "persuasive" in cat:
        style_note = "Tone: gently persuasive, make hiring a pro feel obvious."
    elif "confrontational" in cat or "authoritative" in cat:
        style_note = (
            "Tone: direct, no-nonsense, calling out bad pool habits without being cruel."
        )
    elif "comedic" in cat:
        style_note = "Tone: funny and light, but still on-topic about pool care."
    elif "blog" in cat:
        style_note = "Tone: mini-story, a few sentences that could be the intro to a blog."
    else:
        style_note = (
            "Tone: realistic and grounded, like a pro tech sharing a quick update "
            "from a clean Florida pool."
        )

    weather_str = (
        "Current local weather (data block below)."
        if weather_context
        else "Current local weather: not specified."
    )

    # Get training examples
    examples = []
    try:
        for _ in range(3):
            ex = get_weighted_training_example(cat or "realistic")
            if ex and "caption" in ex:
                examples.append(ex["caption"])
    except Exception:
        pass  # Continue without examples

    # Everything below that did not come from this file's own code (business settings,
    # weather feed, example captions that may come from customer reviews) is data.
    business = (
        f"Business name: {BUSINESS_NAME}\n"
        f"Location: {BUSINESS_CITY}, {BUSINESS_REGION}, {BUSINESS_HEMISPHERE} hemisphere."
    )
    sections = [
        f"Post category: {category}.",
        safety.wrap_untrusted(business, source="business_profile", max_chars=400),
        weather_str,
    ]
    if weather_context:
        sections.append(safety.wrap_untrusted(weather_context, source="weather", max_chars=400))
    sections.append(style_note)
    if examples:
        numbered = "\n".join(f"{i}. {ex}" for i, ex in enumerate(examples, 1))
        sections.append(
            "EXAMPLES OF GOOD CAPTIONS (style reference only, NO PREAMBLE, JUST THE CAPTION):\n"
            + safety.wrap_untrusted(numbered, source="example_captions", max_chars=1500)
        )
    sections.append("Write the caption now.")
    return "\n\n".join(sections)


def _fallback_caption(category: str, weather_context: str) -> str:
    """Hardcoded fallback caption if LLM fails."""
    weather_bit = f" Right now it's {weather_context.lower()}." if weather_context else ""
    cat = (category or "").lower().strip()

    if "realistic" in cat or not cat:
        return (
            "Another Sunnyvale pool checked, brushed, and balanced. "
            "Water clear, equipment quiet, and everything ready for your next swim."
            f"{weather_bit}"
        )

    if "educational" in cat:
        return (
            "Quick tip: clear water doesn't always mean safe water. "
            "Keeping sanitizer and pH in range is what protects your family."
        )

    if "meme" in cat or "comedic" in cat:
        return (
            "That moment when your pool goes from swamp to 'invite the neighbors' in one visit."
        )

    if "persuasive" in cat:
        return (
            "If your weekends keep disappearing into pool chores, it might be time "
            "to let a pro handle the chemistry and brushing."
        )

    if "confrontational" in cat or "authoritative" in cat:
        return (
            "If you only touch your pool when it turns green, you're already too late. "
            "Consistent service keeps the problems away before they show up."
        )

    if "blog" in cat:
        return (
            "Some of the cleanest pools we see don't belong to resorts—they're right here "
            "in everyday backyards. It just takes consistent care and smart chemistry."
        )

    return (
        "Pool is brushed, baskets are cleared, and chemistry is balanced. "
        "You just get to enjoy the water."
    )


def _generate_caption(category: str, weather_context: str) -> tuple[str, bool]:
    """Generate caption using Replicate LLM with fallback."""
    safety.require_action("generate_caption")
    try:
        client = _get_llm_client()
    except Exception as exc:
        log.error("[poster] LLM client unavailable, using fallback caption: %s", exc)
        return _fallback_caption(category, weather_context), False

    try:
        system_prompt = _caption_system_prompt()
        prompt = _build_caption_prompt(category, weather_context)
        llm_input = safety.llm_inputs(system_prompt, prompt, temperature=0.8, top_p=0.9)
    except safety.SecretInPromptError as exc:
        log.error("[poster] Prompt blocked, using fallback caption: %s", exc)
        return _fallback_caption(category, weather_context), False

    try:
        log.info("[poster] Calling Replicate LLM (%s) for category=%s", REPLICATE_LLM, category)
        prediction = client.predictions.create(model=REPLICATE_LLM, input=llm_input)

        while prediction.status not in {"succeeded", "failed", "canceled"}:
            time.sleep(1.0)
            prediction.reload()

        if prediction.status != "succeeded":
            log.error(
                "[poster] Replicate LLM failed status=%s error=%s",
                prediction.status,
                prediction.error,
            )
            return _fallback_caption(category, weather_context), False

        caption = _normalize_replicate_text(prediction.output).strip()
        if not caption:
            log.error("[poster] Replicate LLM returned empty caption, using fallback.")
            return _fallback_caption(category, weather_context), False

        # Output filter: block leaks/off-task text, strip links, images and HTML.
        checked = safety.filter_output(
            _strip_preamble(caption), protected_texts=[system_prompt], mode="text"
        )
        if checked.blocked or not checked.text:
            log.error(
                "[poster] LLM output rejected by safety filter (%s); using fallback caption.",
                ",".join(checked.reasons) or "empty",
            )
            return _fallback_caption(category, weather_context), False
        if checked.reasons:
            log.warning("[poster] LLM output cleaned: %s", ",".join(checked.reasons))

        return checked.text, True

    except Exception as exc:
        log.exception("[poster] Replicate LLM call threw, using fallback caption: %s", exc)
        return _fallback_caption(category, weather_context), False


CAPTION_DEDUPE_ATTEMPTS = max(1, int(os.getenv("CAPTION_DEDUPE_ATTEMPTS", "3")))


def _find_similar_caption(caption: str) -> Optional[str]:
    """Return a previously stored caption that this one duplicates, if any."""
    dup, match = dedupe_store.is_duplicate_caption(caption)
    if not dup:
        dup, match = dedupe_store.is_duplicate_opening(caption)
    return match if dup else None


def _generate_unique_caption(category: str, weather_context: str) -> tuple[str, bool, Optional[str]]:
    """
    Generate a caption and reject near-duplicates of earlier captions.

    Each LLM caption is compared with the dedupe store (exact match, fuzzy
    similarity >= 0.92, or a near-identical opening phrase). Duplicates are
    regenerated up to CAPTION_DEDUPE_ATTEMPTS times. If every attempt is a
    duplicate, the last caption is still queued but flagged via the returned
    `duplicate_of` value so the human reviewer can see it.
    """
    caption, used_llm, duplicate_of = "", False, None
    for attempt in range(1, CAPTION_DEDUPE_ATTEMPTS + 1):
        caption, used_llm = _generate_caption(category, weather_context)
        try:
            duplicate_of = _find_similar_caption(caption)
        except Exception as exc:
            log.warning("[poster] Dedupe check failed, skipping it: %s", exc)
            return caption, used_llm, None
        if duplicate_of is None:
            return caption, used_llm, None
        if not used_llm:
            # Fallback captions are fixed text; regenerating would not help.
            break
        log.warning(
            "[poster] Caption too similar to an earlier one (attempt %d/%d); regenerating.",
            attempt,
            CAPTION_DEDUPE_ATTEMPTS,
        )
    log.warning("[poster] Queueing a caption flagged as a possible duplicate for human review.")
    return caption, used_llm, duplicate_of


def _normalized_post_mode() -> str:
    mode = (POST_MODE or "queue").lower()
    if mode not in VALID_POST_MODES:
        log.warning("[poster] Unknown POST_MODE=%r, defaulting to 'queue'", mode)
        return "queue"
    return mode


def post_to_facebook(
    caption: str, image_path: Optional[str] = None, *, approved: bool = False
) -> bool:
    """Post to Facebook Page. Returns True on success.

    Outbound action: refuses (raises safety.ApprovalRequired) unless the caller passes
    approved=True, which must only be done for a queue item a human approved (or when the
    operator explicitly enabled VP_ALLOW_DIRECT_POST).
    """
    safety.require_action("post_to_facebook", approved=approved)
    if not META_PAGE_ACCESS_TOKEN or not META_PAGE_ID:
        log.error(
            "[poster] Cannot post to Facebook: META_PAGE_ACCESS_TOKEN or META_PAGE_ID missing"
        )
        return False

    base_url = "https://graph.facebook.com/v21.0"

    try:
        if image_path and os.path.exists(image_path):
            url = f"{base_url}/{META_PAGE_ID}/photos"
            with open(image_path, "rb") as f:
                files = {"source": f}
                data = {"caption": caption, "access_token": META_PAGE_ACCESS_TOKEN}
                resp = requests.post(url, data=data, files=files, timeout=30)
        else:
            url = f"{base_url}/{META_PAGE_ID}/feed"
            data = {"message": caption, "access_token": META_PAGE_ACCESS_TOKEN}
            resp = requests.post(url, data=data, timeout=30)

        if 200 <= resp.status_code < 300:
            log.info("[poster] Facebook post successful: %s", resp.text)
            return True
        else:
            log.error("[poster] Facebook post failed (%s): %s", resp.status_code, resp.text)
            return False

    except Exception:
        log.exception("[poster] Exception during Facebook post")
        return False


def _run_single_post_internal(requested_category: Optional[str] = None) -> Dict[str, Any]:
    """Core engine: generate caption, image, enqueue post, optionally post to FB."""
    cli_category = requested_category.strip().lower() if requested_category else None
    try:
        category = resolve_category(cli_category)
    except safety.ScopeError as exc:
        log.error("[poster] Rejected off-scope request: %s", exc)
        return {"ok": False, "error": "category not permitted", "requested_category": cli_category}
    post_mode = _normalized_post_mode()

    log.info(
        "[poster] START requested_category=%s resolved_category=%s POST_MODE=%s BUSINESS=%s",
        cli_category or "<none>",
        category,
        post_mode,
        BUSINESS_NAME,
    )

    # Weather
    weather_context = _safe_weather_context()
    if weather_context:
        log.info("[poster] Weather context: %s", weather_context)

    # Caption
    caption, used_llm, duplicate_of = _generate_unique_caption(category, weather_context)
    log.info("[poster] Final caption (used_llm=%s): %s", used_llm, caption)

    # Image
    image_path = ""
    try:
        image_path = generate_image(
            category=category,
            caption_or_prompt=caption,
            weather_context=weather_context,
            has_caption_context=True,
        )
    except Exception as exc:
        log.exception("[poster] Image generation threw; continuing text-only: %s", exc)

    if image_path:
        log.info("[poster] Image generated at %s", image_path)
    else:
        log.info("[poster] No image generated; continuing with text-only.")
    if not image_path or not os.path.exists(image_path):
        log.error("[poster] BLOCKING post creation - no valid image at: %s", image_path)
        return {
            "ok": False,
            "error": "Image generation failed - post not created",
            "requested_category": cli_category,
            "category": category,
            "caption": caption,
            "image_path": "",
        }

    # Enqueue
    file_path = ""
    try:
        result = enqueue_post(
            category=category,
            caption=caption,
            image_path=image_path or "",
            scheduled_for=None,
            metadata={
                "debug_source": "poster.py",
                "weather_summary": weather_context,
                "used_llm": used_llm,
                "possible_duplicate_of": duplicate_of,
                "post_mode": post_mode,
                "requested_category": cli_category,
                "enqueued_at_utc": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(),
            },
        )
        file_path = result.get("file_path") if isinstance(result, dict) else str(result)
        log.info("[poster] Enqueued post: %s", file_path)
        try:
            dedupe_store.save_caption(caption)
            log.info("[poster] Saved caption to dedupe DB")
        except Exception as e:
            log.warning("[poster] Failed to save caption to dedupe DB: %s", e)
    except Exception as exc:
        log.exception("[poster] FAILED to enqueue post: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "requested_category": cli_category,
            "category": category,
            "post_mode": post_mode,
            "caption": caption,
            "image_path": image_path,
            "file_path": file_path,
            "used_llm": used_llm,
            "posted_to_facebook": False,
        }

    # Optional immediate Facebook post
    posted_now = False
    if post_mode in {"direct", "facebook"} and not safety.direct_posting_enabled():
        log.warning(
            "[poster] POST_MODE=%s ignored: posting without human review needs "
            "VP_ALLOW_DIRECT_POST=true. The post stays in the approval queue.",
            post_mode,
        )
    elif post_mode in {"direct", "facebook"}:
        posted_now = post_to_facebook(
            caption=caption, image_path=image_path or None, approved=True
        )
        if posted_now:
            log.info("[poster] Posted to Facebook immediately in POST_MODE=%s", post_mode)
        else:
            log.error("[poster] Facebook posting failed in POST_MODE=%s", post_mode)

    log.info("[poster] DONE category=%s POST_MODE=%s", category, post_mode)

    return {
        "ok": True,
        "requested_category": cli_category,
        "category": category,
        "post_mode": post_mode,
        "caption": caption,
        "image_path": image_path,
        "file_path": file_path,
        "used_llm": used_llm,
        "posted_to_facebook": posted_now,
    }


def run_single_post(category: Optional[str] = None) -> Dict[str, Any]:
    """Public API used by admin dashboard."""
    return _run_single_post_internal(category)


def main() -> None:
    """CLI entrypoint."""
    requested = sys.argv[1].strip().lower() if len(sys.argv) > 1 else None
    result = _run_single_post_internal(requested)
    if not result.get("ok", False):
        sys.exit(1)


if __name__ == "__main__":
    main()

# AI Learning Integration
import requests

def get_weighted_training_example(category: str):
    """
    Load training example with AI learning:
    - Fetch high-performing captions from analytics
    - Weight selection based on performance scores
    - Fall back to random if no analytics available
    """
    try:
        # Try to fetch AI learning data from the (optional) backend service.
        # Configure VP_BACKEND_URL and VP_BACKEND_ADMIN_TOKEN to enable this.
        backend_url = os.getenv("VP_BACKEND_URL", "").rstrip("/")
        backend_token = os.getenv("VP_BACKEND_ADMIN_TOKEN", "")
        if not backend_url or not backend_token:
            raise RuntimeError("AI learning backend not configured")
        response = requests.get(
            f"{backend_url}/admin/ai-learning-data",
            params={"limit": 20},
            headers={"Authorization": f"Bearer {backend_token}"},
            timeout=2,
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('data'):
                # Filter by category if we have category-specific data
                # For now, use all high-performers
                high_performers = data['data']
                
                # Weight by performance score
                weighted_examples = []
                for item in high_performers:
                    caption = item.get('caption', '').strip()
                    if caption and len(caption) > 10:  # Valid caption
                        score = item.get('performance_score', 1.0)
                        # Add multiple times based on score (1.0 = 5 copies, 0.8 = 4 copies, etc.)
                        copies = max(1, int(score * 5))
                        weighted_examples.extend([caption] * copies)
                
                if weighted_examples:
                    import random
                    selected = random.choice(weighted_examples)
                    log.info("[poster] 🤖 Using AI-learned high-performer (score-weighted)")
                    return {"caption": selected, "image_prompt": "high quality pool"}
    except Exception as e:
        log.debug("[poster] AI learning fetch failed (falling back to random): %s", e)
    
    # Fallback to regular training example
    return load_training_example(category)

