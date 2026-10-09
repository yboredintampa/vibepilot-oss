#!/usr/bin/env python
"""
translate_post.py — Local Replicate-only translation, zero logging, private.
Uses the text model defined in REPLICATE_LLM (default: meta/meta-llama-3-8b-instruct)
to translate marketing captions.
"""

import os
import json
import replicate
from pathlib import Path
from typing import Dict, Any, Tuple

QUEUE_DIR = Path("/app/post_queue")


def find_queue_item(item_id: str) -> Tuple[Path, Dict[str, Any]]:
    """Find the post JSON file in the queue by its id."""
    if not QUEUE_DIR.exists():
        raise SystemExit(f"Queue dir not found: {QUEUE_DIR}")

    for path in QUEUE_DIR.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        stored_id = data.get("id") or path.stem
        if stored_id == item_id or stored_id.startswith(item_id) or item_id.startswith(stored_id):
            return path, data
    raise SystemExit(f"Queue item {item_id!r} not found in {QUEUE_DIR}")


def translate_caption_local(caption: str, target_lang: str) -> str:
    """Translate caption using Replicate LLM; stay fully local/private."""
    if not caption:
        return caption

    model = os.getenv("REPLICATE_LLM", "meta/meta-llama-3-8b-instruct")
    token = os.getenv("REPLICATE_API_TOKEN")

    if not token:
        print("⚠️ Missing REPLICATE_API_TOKEN — returning original caption.")
        return caption

    prompt = (
        f"Translate the following marketing caption into {target_lang}.\n\n"
        f"Keep tone, emojis, and personality intact. Do not add any notes or brackets.\n\n"
        f"Caption:\n{caption}\n\nTranslation:"
    )

    try:
        output = replicate.run(model, input={"prompt": prompt})
        # Replicate outputs vary — normalize to string
        if isinstance(output, list):
            translated = "".join(str(x) for x in output).strip()
        elif isinstance(output, dict):
            translated = output.get("output") or output.get("text") or caption
        else:
            translated = str(output).strip()
        return translated or caption
    except Exception as e:
        print(f"⚠️ Translation error: {e}")
        return caption


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Translate queued post caption in-place.")
    parser.add_argument("--id", required=True, help="Post ID or filename stem")
    parser.add_argument("--target-lang", required=True, help="Target language code (es, fr, etc.)")
    args = parser.parse_args()

    path, data = find_queue_item(args.id)
    caption = str(data.get("caption") or "")
    if not caption:
        print("No caption found.")
        return

    translated = translate_caption_local(caption, args.target_lang)
    data["caption"] = translated
    data["language"] = args.target_lang

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)
    print(f"✅ Translated {args.id} → {args.target_lang}")


if __name__ == "__main__":
    main()
