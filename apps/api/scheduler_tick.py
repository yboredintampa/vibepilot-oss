#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler_tick.py

Runs once per minute (via cron) *inside the vp-api container*.

- Reads /app/scheduler_config.json (managed by the admin dashboard)
  - Uses "post_times": ["08:00", "13:00", "18:00"] (HH:MM, server time)
- At each scheduled time, it:
  1) Picks the oldest APPROVED, NOT-YET-POSTED item in /app/post_queue
  2) Posts it to Facebook via facebook_poster.post_to_facebook()
  3) Marks it as "posted" and writes posted_at
  4) Updates a small state file so we only post ONCE per slot per day

This script does NOT generate new content – it only posts approved items.
Fill the queue using:
- the admin "Generate next" button, or
- manual: /app/run_post.sh realistic|meme|educational|...
"""

import os
import json
import datetime
import time
import logging
from typing import Dict, Any, List, Optional

# Paths inside the container
QUEUE_DIR = "/app/post_queue"
LOG_DIR = "/app/logs"
CONFIG_PATH = "/app/scheduler_config.json"
STATE_PATH = "/app/data/scheduler_state.json"

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [UTC] %(message)s",
)
logging.Formatter.converter = time.gmtime  # log timestamps in UTC
log = logging.getLogger("scheduler_tick")


# --------------------------
# Config + state
# --------------------------
def load_config() -> Dict[str, Any]:
    cfg = {
        "post_times": ["08:00", "13:00", "18:00"],  # HH:MM, server time
        "preview_generation_time": "18:00",
        "blog_posts_per_week": 3,
        "brand_voice": 70,
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                disk = json.load(f)
            if isinstance(disk, dict):
                cfg.update(disk)
        except Exception as e:
            log.warning("Failed to read scheduler_config.json: %s", e)
    return cfg


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        return {"last_post_date_by_slot": {}}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"last_post_date_by_slot": {}}
        data.setdefault("last_post_date_by_slot", {})
        return data
    except Exception as e:
        log.warning("Failed to read scheduler state: %s", e)
        return {"last_post_date_by_slot": {}}


def save_state(state: Dict[str, Any]) -> None:
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log.warning("Failed to write scheduler state: %s", e)


# --------------------------
# Queue helpers
# --------------------------
def _list_queue_files() -> List[str]:
    if not os.path.exists(QUEUE_DIR):
        return []
    return sorted(
        [
            f
            for f in os.listdir(QUEUE_DIR)
            if f.endswith(".json") and not f.startswith("_")
        ]
    )


def _load_post(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("Failed to read post file %s: %s", path, e)
        return None


def find_oldest_approved_unposted() -> Optional[str]:
    """
    Return the path to the oldest APPROVED, not-yet-POSTED item in /app/post_queue,
    or None if there is none.
    """
    candidates: List[tuple[datetime.datetime, str]] = []

    for fname in _list_queue_files():
        path = os.path.join(QUEUE_DIR, fname)
        data = _load_post(path)
        if not data:
            continue

        status = (data.get("status") or "").strip().lower()
        if status != "approved":
            continue

        # Skip if already posted
        if (data.get("posted_at") or "").strip():
            continue

        created_str = data.get("created_at") or ""
        try:
            created_dt = datetime.datetime.fromisoformat(
                created_str.replace("Z", "")
            )
        except Exception:
            # If created_at missing or malformed, just treat as newest
            created_dt = datetime.datetime.max

        candidates.append((created_dt, path))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


# --------------------------
# Post to Facebook
# --------------------------
def post_item(path: str) -> bool:
    """
    Post a single queue item to Facebook.
    Returns True on success, False on failure.
    """
    from facebook_poster import post_to_facebook  # import inside to avoid cycles

    data = _load_post(path)
    if not data:
        return False

    caption = data.get("caption") or ""
    image_path = data.get("image_path") or None

    log.info("Posting approved item to Facebook: %s", os.path.basename(path))

    try:
        result = post_to_facebook(caption, image_path)
        data["status"] = "posted"
        data["posted_at"] = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        data.setdefault("scheduler", {})
        data["scheduler"]["result"] = result

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        log.info("Facebook post success: %r", result)
        return True
    except Exception as e:
        log.exception("Error posting to Facebook for %s: %s", path, e)
        return False


# --------------------------
# Main tick logic
# --------------------------
def tick_once() -> None:
    now = datetime.datetime.now()  # container local time (likely UTC)
    today_str = now.strftime("%Y-%m-%d")
    now_hm = now.strftime("%H:%M")

    cfg = load_config()
    state = load_state()
    last_by_slot: Dict[str, str] = state.get("last_post_date_by_slot", {})

    post_times: List[str] = [
        str(t).strip() for t in (cfg.get("post_times") or []) if str(t).strip()
    ]

    if not post_times:
        log.info("[scheduler_tick] No post_times configured; nothing to do.")
        return

    log.info(
        "[scheduler_tick] Tick at %s (local) with post_times=%s",
        now.isoformat(),
        post_times,
    )

    did_anything = False

    for slot in post_times:
        if len(slot) != 5 or ":" not in slot:
            continue

        last_date = last_by_slot.get(slot)
        if now_hm == slot and last_date != today_str:
            log.info(
                "[scheduler_tick] Slot %s is due (last_date=%s, today=%s)",
                slot,
                last_date,
                today_str,
            )

            queue_item_path = find_oldest_approved_unposted()
            if not queue_item_path:
                log.warning(
                    "[scheduler_tick] No approved, unposted items available for slot %s",
                    slot,
                )
                # We still mark the slot as used for today, so we don't spam logs
                last_by_slot[slot] = today_str
                did_anything = True
                continue

            if post_item(queue_item_path):
                last_by_slot[slot] = today_str
                did_anything = True

    state["last_post_date_by_slot"] = last_by_slot
    save_state(state)

    if not did_anything:
        log.info("[scheduler_tick] No due slots at this minute.")


if __name__ == "__main__":
    tick_once()
