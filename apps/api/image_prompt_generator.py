#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
image_prompt_manager.py (VibePilot Edition)
-------------------------------------------
- Category-driven image generation pipeline.
- Routes to FLUX-Schnell (photos) or SDXL-Lightning (infographics).
- Enforces sanity: NO gibberish, NO in-image text, NO watermarks.

Env Vars:
  REPLICATE_API_TOKEN
  IMAGE_WIDTH / IMAGE_HEIGHT (optional, defaults = 1024)
"""

import os
import io
import time
import random
import logging
from typing import Dict, Tuple, List
import requests

try:
    import replicate
except Exception:
    replicate = None

log = logging.getLogger("image_prompt_manager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [UTC] %(message)s")

# -------------------------------------------------------------------
#  CATEGORY STYLE PACKS
# -------------------------------------------------------------------
def _prompt_style_pack() -> Dict[str, Dict[str, str]]:
    return {
        "realistic": {
            "style": (
                "Photorealistic pool service scene, Sunnyvale backyard, real light reflections, "
                "clear water, professional composition, inviting tone, no text, no watermark, no logos"
            ),
            "neg": (
                "text, watermark, logo, gibberish letters, low quality, distorted faces, "
                "unnatural lighting, clutter, cartoon, fake words"
            ),
        },
        "educational": {
            "style": (
                "Infographic style clean layout about pool care, icons and simple shapes, "
                "flat design, white background, minimal, clear symbols, no text, no letters"
            ),
            "neg": (
                "text, watermark, logo, gibberish, complex photo, cluttered design, "
                "busy background, fake words, blurred shapes"
            ),
        },
        "meme": {
            "style": (
                "Funny candid pool photo, expressive face, strong emotion, "
                "leave space for top and bottom captions, no text in image, vivid lighting"
            ),
            "neg": (
                "text, watermark, logo, gibberish, cartoon, illustration, distorted anatomy"
            ),
        },
        "confrontational": {
            "style": (
                "Dramatic before-and-after pool water contrast, moody real lighting, "
                "clean vs dirty halves, professional photo realism, no text"
            ),
            "neg": (
                "text, watermark, logo, gibberish, low-res, deformed water, fake reflections"
            ),
        },
        "comedic": {
            "style": (
                "Playful, humorous poolside shot, warm tone, realistic setting, "
                "human expressions, no text, no cartoon, real photo"
            ),
            "neg": "text, watermark, logo, cartoon, gibberish, low quality",
        },
        "persuasive": {
            "style": (
                "Premium modern backyard pool, serene and elegant, high-end photography, "
                "perfect symmetry, golden hour lighting, no text, no logos"
            ),
            "neg": "text, watermark, logo, clutter, fake lighting, gibberish",
        },
    }

# -------------------------------------------------------------------
#  PROMPT BUILDER
# -------------------------------------------------------------------
def build_image_prompt(category: str, caption: str) -> Tuple[str, str]:
    cat = (category or "realistic").strip().lower()
    pack = _prompt_style_pack().get(cat, _prompt_style_pack()["realistic"])

    context_bits: List[str] = []
    caption_l = caption.lower()
    if "algae" in caption_l:
        context_bits.append("emphasis on clean clear water")
    if "filter" in caption_l or "psi" in caption_l:
        context_bits.append("equipment or pool filter implied")
    if "summer" in caption_l or "heat" in caption_l:
        context_bits.append("bright sunlight, Florida summer vibes")
    if "repair" in caption_l or "service" in caption_l:
        context_bits.append("technician or maintenance scene")

    context = ", ".join(context_bits) if context_bits else "residential pool, clear water"

    # Add strong global safety tags
    safety_tags = (
        "no text, no words, no letters, no gibberish, no logos, no watermark, "
        "clean realistic composition, focus on subject clarity"
    )

    positive = f"{pack['style']}, {context}, {safety_tags}"
    negative = pack["neg"]
    return positive, negative

# -------------------------------------------------------------------
#  REPLICATE CLIENT + UTILITIES
# -------------------------------------------------------------------
def _replicate_client():
    token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("REPLICATE_API_TOKEN is not set")
    return replicate.Client(api_token=token)


def _pick_dims() -> Tuple[int, int]:
    w = int(os.environ.get("IMAGE_WIDTH", "1024"))
    h = int(os.environ.get("IMAGE_HEIGHT", "1024"))
    w = max(512, min(1536, w))
    h = max(512, min(1536, h))
    return w, h


def _download_first_image(output, dest_path: str) -> str:
    urls: List[str] = []
    if isinstance(output, list):
        urls = [u for u in output if isinstance(u, str) and u.startswith("http")]
    elif isinstance(output, dict):
        if "output" in output:
            urls = [u for u in output["output"] if isinstance(u, str) and u.startswith("http")]
        elif "image" in output and isinstance(output["image"], str):
            urls = [output["image"]]
    elif isinstance(output, str) and output.startswith("http"):
        urls = [output]

    if not urls:
        raise RuntimeError(f"Unexpected Replicate output: {output}")

    url = urls[0]
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(r.content)
    return dest_path

# -------------------------------------------------------------------
#  MODEL RUNNERS
# -------------------------------------------------------------------
def _run_flux_schnell(client, prompt, negative, width, height):
    model = "black-forest-labs/flux-schnell"
    return client.run(model, input={
        "prompt": prompt,
        "negative_prompt": negative,
        "width": width,
        "height": height
    })


def _run_sdxl_lightning(client, prompt, negative, width, height):
    model = "stability-ai/sdxl-lightning"
    return client.run(model, input={
        "prompt": prompt,
        "negative_prompt": negative,
        "width": width,
        "height": height
    })

# -------------------------------------------------------------------
#  PUBLIC FUNCTION
# -------------------------------------------------------------------
def generate_image(category: str, caption: str) -> str:
    client = _replicate_client()
    width, height = _pick_dims()
    prompt, negative = build_image_prompt(category, caption)
    tmp_path = f"/tmp/vp_{int(time.time())}_{random.randint(1000,9999)}.png"

    # Route based on category
    if category.lower() == "educational":
        runners = [("sdxl-lightning", _run_sdxl_lightning), ("flux-schnell", _run_flux_schnell)]
    else:
        runners = [("flux-schnell", _run_flux_schnell), ("sdxl-lightning", _run_sdxl_lightning)]

    for name, runner in runners:
        try:
            log.info("[image_prompt_manager] Generating via %s for category=%s", name, category)
            output = runner(client, prompt, negative, width, height)
            path = _download_first_image(output, tmp_path)
            log.info("[image_prompt_manager] Saved generated image: %s", path)
            return path
        except Exception as e:
            log.warning("[image_prompt_manager] Model %s failed: %s", name, e)

    raise RuntimeError("All models failed for category: " + category)


def generate_image_prompt(category: str, caption: str) -> Tuple[str, str]:
    return build_image_prompt(category, caption)


if __name__ == "__main__":
    print(generate_image("educational", "Free chlorine and total chlorine explained."))
