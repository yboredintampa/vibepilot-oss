#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dedupe all pools_*_training.txt files under /opt/vibepilot/content.

- Works across ALL training files (global "no repeats ever" for caption|prompt pairs).
- Normalizes whitespace around the pipe: "caption | prompt".
- Keeps the first occurrence of each unique pair; discards later duplicates.
- Backs up each file to <name>.bak before rewriting.

Safe to re-run any time after you add new lines.
"""

import sys
from pathlib import Path

TRAINING_DIR = Path("/opt/vibepilot/content")
PATTERN = "pools_*_training.txt"


def normalize_pair(line: str) -> str:
    """
    Normalize a caption | image_prompt line:
    - Strip leading/trailing spaces
    - Compress internal whitespace
    - Force single space around the pipe
    """
    # We only split on the first pipe; captions shouldn't contain another pipe.
    left, right = line.split("|", 1)

    def squash_spaces(s: str) -> str:
        return " ".join(s.strip().split())

    caption = squash_spaces(left)
    prompt = squash_spaces(right)

    return f"{caption} | {prompt}"


def dedupe_file(path: Path, seen_pairs: set[str]) -> None:
    original_lines = path.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []

    for raw in original_lines:
        stripped = raw.strip()

        # Keep blank lines but avoid multiple in a row
        if not stripped:
            if new_lines and new_lines[-1].strip() == "":
                continue
            new_lines.append("")
            continue

        # If it doesn't look like a caption|prompt line, keep as-is
        if "|" not in stripped:
            new_lines.append(raw)
            continue

        try:
            key = normalize_pair(stripped)
        except Exception:
            # If something weird happens, just keep the raw line
            new_lines.append(raw)
            continue

        if key in seen_pairs:
            # Global dedupe: this exact pair already appeared in some file
            continue

        seen_pairs.add(key)
        new_lines.append(key)

    backup = path.with_suffix(path.suffix + ".bak")
    if backup.exists():
        backup.unlink()

    path.rename(backup)
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    removed = len(original_lines) - len(new_lines)
    print(
        f"{path.name}: {len(original_lines)} -> {len(new_lines)} lines "
        f"(removed {removed})  backup={backup.name}"
    )


def main() -> int:
    if not TRAINING_DIR.exists():
        print(f"Training dir not found: {TRAINING_DIR}", file=sys.stderr)
        return 1

    files = sorted(TRAINING_DIR.glob(PATTERN))
    if not files:
        print(f"No files matching {PATTERN} in {TRAINING_DIR}")
        return 0

    print(f"Deduping {len(files)} training file(s) in {TRAINING_DIR}...\n")

    seen_pairs: set[str] = set()
    for path in files:
        dedupe_file(path, seen_pairs)

    print("\nDone. All caption|prompt pairs are now globally deduped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
