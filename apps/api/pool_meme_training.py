"""
pool_meme_training.py

Utility helpers to load and sample from curated pool-service
meme training data.

Format of /app/content/pools_meme_training.txt:

    Caption text | Image prompt text

Example line:

    Truth is, most don't check. If your tech arrives in flip-flops, your pool’s doomed (bather load) | Tech with flip-flops slipping near pump with focus on bather load

Left side  = the meme-style caption hook.
Right side = the image description for the generator.

For now we only wire memes, but this module is written so we
can easily add other category-specific training files later
(educational, confrontational, authoritative, etc.).
"""

import os
import random
import logging

log = logging.getLogger(__name__)

# Path inside the container
TRAINING_PATH = "/app/content/pools_meme_training.txt"

# In-memory cache so we only read once per process
_examples_cache = None


def _load_examples():
    """
    Load meme training examples from pools_meme_training.txt.

    Expected format per line:
        caption text goes here | image prompt / scene description here

    - Lines starting with '#' or blank are ignored.
    - If there's no '|', the whole line is treated as caption and
      image_prompt is set to "" (the image layer can still build a prompt).
    """
    global _examples_cache
    if _examples_cache is not None:
        return _examples_cache

    examples = []

    if not os.path.exists(TRAINING_PATH):
        log.warning(
            "[pool_meme_training] Training file missing: %s",
            TRAINING_PATH,
        )
        _examples_cache = examples
        return examples

    try:
        with open(TRAINING_PATH, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split("|", 1)
                if len(parts) == 2:
                    caption, image_prompt = parts
                else:
                    caption, image_prompt = line, ""

                caption = caption.strip().strip('"')
                image_prompt = image_prompt.strip()

                if not caption:
                    continue

                examples.append(
                    {
                        "caption": caption,
                        "image_prompt": image_prompt,
                    }
                )

        log.info(
            "[pool_meme_training] Loaded %d examples from %s",
            len(examples),
            TRAINING_PATH,
        )
    except Exception as e:
        log.exception(
            "[pool_meme_training] Error loading %s: %s",
            TRAINING_PATH,
            e,
        )
        examples = []

    _examples_cache = examples
    return examples


def get_random_meme_example():
    """
    Return a random meme example as a dict:
        { "caption": str, "image_prompt": str }

    Raises RuntimeError if no examples could be loaded.
    """
    examples = _load_examples()
    if not examples:
        raise RuntimeError("No meme training examples loaded")

    example = random.choice(examples)
    log.info(
        "[pool_meme_training] Selected meme example: caption=%r, image_prompt=%r",
        example["caption"],
        example["image_prompt"],
    )
    return example


def sample_pool_meme_pair():
    """
    Backwards-compat wrapper for older image_prompt_manager code.

    Returns:
        (caption, image_prompt)
    """
    example = get_random_meme_example()
    return example["caption"], example["image_prompt"]
