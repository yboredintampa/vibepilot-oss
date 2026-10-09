import os
import logging
import random
from typing import Dict, List

log = logging.getLogger(__name__)

# Path to your training data file with:
# "caption | image prompt" per line
PERSUASIVE_TRAINING_FILE = os.getenv(
    "PERSUASIVE_TRAINING_FILE",
    "/opt/vibepilot/content/pools_persuasive_training.txt",
)

# Cached examples so we only read from disk once
_PERSUASIVE_EXAMPLES: List[Dict[str, str]] | None = None


def _load_persuasive_examples() -> List[Dict[str, str]]:
    """
    Load persuasive training examples from the text file.

    Expected format per line:
        Caption text here | Image prompt text here

    Lines starting with '#' or blank lines are ignored.
    """
    global _PERSUASIVE_EXAMPLES
    if _PERSUASIVE_EXAMPLES is not None:
        return _PERSUASIVE_EXAMPLES

    examples: List[Dict[str, str]] = []

    if not os.path.exists(PERSUASIVE_TRAINING_FILE):
        log.warning(
            "[pool_persuasive_training] Training file not found: %s",
            PERSUASIVE_TRAINING_FILE,
        )
        _PERSUASIVE_EXAMPLES = []
        return _PERSUASIVE_EXAMPLES

    try:
        with open(PERSUASIVE_TRAINING_FILE, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                if "|" not in line:
                    # Skip lines that don't follow "caption | image prompt"
                    continue

                caption_part, image_part = line.split("|", 1)

                caption = (
                    caption_part.replace("\uFEFF", "")
                    .lstrip("* ")
                    .strip()
                )
                image_prompt = image_part.strip()

                if not caption or not image_prompt:
                    continue

                examples.append(
                    {
                        "caption": caption,
                        "image_prompt": image_prompt,
                    }
                )

        log.info(
            "[pool_persuasive_training] Loaded %d persuasive examples from %s",
            len(examples),
            PERSUASIVE_TRAINING_FILE,
        )
    except Exception as exc:
        log.exception(
            "[pool_persuasive_training] Error loading persuasive training "
            "file %s: %s",
            PERSUASIVE_TRAINING_FILE,
            exc,
        )
        examples = []

    _PERSUASIVE_EXAMPLES = examples
    return _PERSUASIVE_EXAMPLES


def get_all_persuasive_examples() -> List[Dict[str, str]]:
    """
    Return a copy of all loaded persuasive examples.
    """
    return list(_load_persuasive_examples())


def get_random_persuasive_example() -> Dict[str, str]:
    """
    Return a single random persuasive example as:
        {"caption": "...", "image_prompt": "..."}
    If none are available, returns an empty shell dict.
    """
    examples = _load_persuasive_examples()
    if not examples:
        return {"caption": "", "image_prompt": ""}

    return random.choice(examples)


if __name__ == "__main__":
    # Quick manual test:
    ex = get_random_persuasive_example()
    print("Sample persuasive example:")
    print("Caption     :", ex.get("caption"))
    print("Image prompt:", ex.get("image_prompt"))
