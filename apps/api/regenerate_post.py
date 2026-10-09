#!/usr/bin/env python
import argparse
import json
from pathlib import Path
from typing import Dict, Any, Tuple

QUEUE_DIR = Path("/app/post_queue")


def find_queue_item(item_id: str) -> Tuple[Path, Dict[str, Any]]:
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

    raise SystemExit(f"Queue item {item_id!r} not found")


def regen_caption(data: Dict[str, Any]) -> None:
    cap = str(data.get("caption") or "")
    # 🔧 STUB: hook this into your Phi/Replicate pipeline later.
    data["caption"] = f"{cap} [regenerated caption]"
    data.setdefault("metadata", {})["caption_regenerated"] = True


def regen_image(data: Dict[str, Any]) -> None:
    # 🔧 STUB: real version should call your image generator.
    # Here we just clear the image reference and set a flag.
    data["image_url"] = ""
    data["image_path"] = ""
    data.setdefault("metadata", {})["image_regenerated"] = True


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate queued post content.")
    parser.add_argument("--id", required=True, help="Queue item id")
    parser.add_argument(
        "--mode",
        choices=["caption", "image", "both"],
        default="both",
        help="What to regenerate.",
    )
    args = parser.parse_args()

    path, data = find_queue_item(args.id)

    if args.mode in ("caption", "both"):
        regen_caption(data)
    if args.mode in ("image", "both"):
        regen_image(data)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)

    print(f"Regenerated {args.mode} for {args.id}")


if __name__ == "__main__":
    main()
