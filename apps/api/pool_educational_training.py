import logging
import os
import random
from typing import List, Dict

log = logging.getLogger(__name__)

TRAINING_PATH = "/app/content/pools_educational_training.txt"

_cached_examples: List[Dict[str, str]] = []
_cached_mtime: float = 0.0


def _load_examples() -> List[Dict[str, str]]:
    """
    Load and cache educational training examples from
    /app/content/pools_educational_training.txt.

    Each non-empty, non-comment line is:
        caption | image_prompt
    """
    global _cached_examples, _cached_mtime

    try:
        st = os.stat(TRAINING_PATH)
    except FileNotFoundError:
        log.warning(
            "[pool_educational_training] Training file missing: %s",
            TRAINING_PATH,
        )
        _cached_examples = []
        _cached_mtime = 0.0
        return _cached_examples

    # Reload if the file changed or cache is empty
    if st.st_mtime != _cached_mtime or not _cached_examples:
        examples: List[Dict[str, str]] = []

        try:
            with open(TRAINING_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if "|" in line:
                        caption, image_prompt = [
                            part.strip() for part in line.split("|", 1)
                        ]
                    else:
                        caption, image_prompt = line, ""

                    if caption:
                        examples.append(
                            {
                                "caption": caption,
                                "image_prompt": image_prompt,
                            }
                        )
        except Exception as e:
            log.warning(
                "[pool_educational_training] Failed to read %s: %s",
                TRAINING_PATH,
                e,
            )
            examples = []

        _cached_examples = examples
        _cached_mtime = st.st_mtime

        log.info(
            "[pool_educational_training] Loaded %d examples from %s",
            len(examples),
            TRAINING_PATH,
        )

    return _cached_examples


def get_random_educational_example() -> Dict[str, str]:
    """
    Return a random educational example dict:
        { "caption": str, "image_prompt": str }

    If none available, returns empty strings.
    """
    examples = _load_examples()
    if not examples:
        log.warning(
            "[pool_educational_training] No examples available, "
            "returning empty fallback."
        )
        return {"caption": "", "image_prompt": ""}

    ex = random.choice(examples)
    log.info(
        "[pool_educational_training] Selected educational example: "
        "caption=%r, image_prompt=%r",
        ex.get("caption"),
        ex.get("image_prompt"),
    )
    return ex
