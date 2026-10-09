import os
import random
import logging
import time
from typing import Dict, List

# -----------------------------------------------
# Logging
# -----------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [UTC] %(message)s",
)
logging.Formatter.converter = time.gmtime
log = logging.getLogger(__name__)

# -----------------------------------------------
# Where to look for extra training rows
# -----------------------------------------------
BASE_DIR = os.path.dirname(__file__)
# We keep the data file in /opt/vibepilot/content, not next to this module.
# You can override this via POOLS_REALISTIC_TRAINING_FILE if needed.
TRAINING_FILE = os.getenv(
    "POOLS_REALISTIC_TRAINING_FILE",
    "/opt/vibepilot/content/pools_realistic_training.txt",
)

# Seed examples baked into the module so it still works
# even if the .txt file is missing or empty.
SEED_EXAMPLES: List[Dict[str, str]] = [
    {
        "caption": "Freshly brushed Sunnyvale pool with glassy calm water and crisp tile lines.",
        "image_prompt": "ultra realistic residential backyard pool in Sunnyvale, bright Florida sun, water perfectly clear, blue ceramic tile around the steps, neat deck, no people"
    },
    {
        "caption": "Morning light hitting a clean pool before the day heats up.",
        "image_prompt": "realistic sunrise over a suburban Florida pool, soft warm light, light steam coming off the surface, palm shadows, calm water"
    },
    {
        "caption": "Filter running, chemistry dialed in, no foam or film on the surface.",
        "image_prompt": "close-up of clean pool surface with tiny ripples, skimmer in frame, no leaves, no bugs, clear reflection of sky"
    },
    {
        "caption": "Perfect swim-ready pool after a full service visit.",
        "image_prompt": "wide shot of pristine backyard pool in Florida, bright midday sunshine, clear blue water, clean deck, tidy patio furniture"
    },
    {
        "caption": "Tile line spotless, no scale, no slime, just clean water and clean walls.",
        "image_prompt": "realistic side view of pool wall and waterline tile, zero calcium scale, no algae, strong contrast between white grout and blue tile"
    },
    {
        "caption": "Controlled bubbles only where they belong, not foaming across the whole pool.",
        "image_prompt": "close-up of pool return jet making a small column of bubbles, water still looks clear and blue, no heavy foam or scum"
    },
    {
        "caption": "Screened-in lanai keeping the debris out and the peace in.",
        "image_prompt": "Florida screened lanai with a rectangular pool, warm light, a couple of palm fronds outside the screen, deck perfectly clean"
    },
    {
        "caption": "After the storm: leaves gone, clarity back, pool looks calm again.",
        "image_prompt": "realistic Florida backyard pool after cleanup, a few trees in background, deck washed, water clear, sky partly cloudy"
    },
    {
        "caption": "Steps and benches fully visible, no cloudiness hiding the bottom.",
        "image_prompt": "top-down view of shallow end steps in a pool, each step clearly visible through crystal-clear water, sunlight patterns on the floor"
    },
    {
        "caption": "Even lighting, no weird color casts, just a clean blue pool.",
        "image_prompt": "medium wide shot of backyard pool with neutral blue water, white pool walls, no green tint, no odd reflections, simple landscaping"
    },
    {
        "caption": "Tight equipment pad makes this water look easy.",
        "image_prompt": "realistic pool equipment pad with pump and filter, clean pipes, no leaks, tidy layout, soft background blur of the pool itself"
    },
    {
        "caption": "Zero leaves on the surface, zero drama for the homeowner.",
        "image_prompt": "overhead shot of small residential pool, absolutely no debris floating, a few palms nearby, sky reflected in the water"
    },
    {
        "caption": "Shade and sun balanced so the pool looks inviting all day.",
        "image_prompt": "realistic Florida backyard pool with half sun, half shade from a tree or porch, water still bright and clear, inviting ambiance"
    },
    {
        "caption": "The kind of pool that makes you cancel plans and stay home.",
        "image_prompt": "cinematic shot of sparkling residential pool at golden hour, warm highlights, subtle lens flare, cozy seating area nearby"
    },
    {
        "caption": "Clean lines, clean water, clean tile. That’s it.",
        "image_prompt": "minimalist composition of a straight pool edge, waterline tile, and water, strong geometric lines, bright daylight, no clutter"
    },
]

_EXAMPLES: List[Dict[str, str]] = []


def _load_from_file() -> List[Dict[str, str]]:
    """
    Optional: load extra examples from pools_realistic_training.txt

    Expected format per line:
      caption text | image prompt description

    Lines starting with # or blank lines are ignored.
    """
    rows: List[Dict[str, str]] = []

    if not os.path.exists(TRAINING_FILE):
        log.info(
            "[pool_realistic_training] No training file found at %s; using seed examples only",
            TRAINING_FILE,
        )
        return rows

    try:
        with open(TRAINING_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "|" not in line:
                    # Don’t crash on bad rows, just log and skip
                    log.warning(
                        "[pool_realistic_training] Skipping malformed line (missing '|'): %s",
                        line,
                    )
                    continue

                caption, image_prompt = line.split("|", 1)
                caption = caption.strip()
                image_prompt = image_prompt.strip()

                if not caption or not image_prompt:
                    continue

                rows.append(
                    {
                        "caption": caption,
                        "image_prompt": image_prompt,
                    }
                )
    except Exception as exc:
        log.exception(
            "[pool_realistic_training] Error reading %s: %s", TRAINING_FILE, exc
        )

    log.info(
        "[pool_realistic_training] Loaded %d extra realistic examples from %s",
        len(rows),
        TRAINING_FILE,
    )
    return rows


def _init_examples() -> None:
    global _EXAMPLES
    if _EXAMPLES:
        return

    file_rows = _load_from_file()
    # Seed + file-based rows
    _EXAMPLES = list(SEED_EXAMPLES)
    if file_rows:
        _EXAMPLES.extend(file_rows)

    log.info(
        "[pool_realistic_training] Initialized with %d total examples",
        len(_EXAMPLES),
    )


def get_random_realistic_example() -> Dict[str, str]:
    """
    Return a dict with:
      {
        "caption": "...",
        "image_prompt": "..."
      }

    Always returns *something* (falls back to a hard-coded default).
    """
    _init_examples()

    if not _EXAMPLES:
        # ultra-defensive fallback
        return {
            "caption": "Crystal clear Florida backyard pool on a sunny day.",
            "image_prompt": (
                "realistic residential pool in Florida, bright blue water, "
                "clean deck, no debris, palm trees in background"
            ),
        }

    return random.choice(_EXAMPLES)
