"""
Vibepilot Scheduler

- Runs inside the vp-api container.
- Reads /app/scheduler_config.json for account + schedule definitions.
- Decides if any schedule is "due" based on:
    - Account timezone
    - days_of_week
    - times (HH:MM)
    - last_run_key (one run per time slot)

Actions supported per schedule:

1) "run_post_live"
    -> /app/run_post.sh [optional_category]

2) "generate_to_queue"
    -> POST_MODE=queue /app/run_post.sh <category>

3) "post_from_queue"
    -> python /app/queue_poster.py post-next

Usage examples (inside container or via docker exec):

    python /app/scheduler.py init-config       # create a starter config if missing
    python /app/scheduler.py show-config       # pretty-print config
    python /app/scheduler.py tick              # run one scheduler tick

Recommended cron (on host) once you move to scheduler-driven behavior:

    * * * * * /usr/bin/docker exec vp-api sh -lc "python /app/scheduler.py tick"

Then all per-user times live in scheduler_config.json (and later, in a DB/GUI),
NOT in system cron.
"""

import argparse
import json
import logging
import os
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo

CONFIG_PATH = os.environ.get("SCHEDULER_CONFIG_PATH", "/app/scheduler_config.json")

logger = logging.getLogger("scheduler")


def setup_logging() -> None:
    import time

    class UTCFormatter(logging.Formatter):
        converter = time.gmtime

    fmt = "%(asctime)s [%(levelname)s] [UTC] [scheduler] %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(UTCFormatter(fmt))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        logger.warning(
            "Scheduler config not found at %s. Run 'init-config' to create one.",
            CONFIG_PATH,
        )
        return {"accounts": []}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse scheduler config: %s", exc)
            return {"accounts": []}

    if "accounts" not in data or not isinstance(data["accounts"], list):
        logger.error("scheduler_config.json is missing 'accounts' list.")
        return {"accounts": []}

    return data


def save_config(config: Dict[str, Any]) -> None:
    tmp_path = CONFIG_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CONFIG_PATH)


def default_config() -> Dict[str, Any]:
    """
    Starter config that mirrors the demo schedule:
    - Account: "demo" (Sunny Side Pool Co.)
    - Timezone: America/New_York
    - Three times per day: 13:00, 18:00, 23:00
    - Action: run_post_live  -> /app/run_post.sh (uses internal category rotation)
    """
    return {
        "accounts": [
            {
                "id": "demo",
                "name": "Sunny Side Pool Co.",
                "timezone": "America/New_York",
                "schedules": [
                    {
                        "id": "demo_auto_3x",
                        "description": "Demo auto-rotating live posts 3x/day",
                        "enabled": True,
                        "action": "run_post_live",
                        # if category is None, run_post.sh decides category
                        "category": None,
                        # local times in HH:MM (24h) in account timezone
                        "times": ["13:00", "18:00", "23:00"],
                        # days of week: mon, tue, wed, thu, fri, sat, sun
                        "days_of_week": [
                            "mon",
                            "tue",
                            "wed",
                            "thu",
                            "fri",
                            "sat",
                            "sun",
                        ],
                        # internal state: last scheduled slot executed, e.g. "2025-11-22T13:00"
                        "last_run_key": None,
                    }
                ],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Time / schedule logic
# ---------------------------------------------------------------------------

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _normalize_days(days: Optional[List[str]]) -> List[str]:
    if not days:
        return DAY_NAMES[:]
    result: List[str] = []
    for d in days:
        d = str(d).strip().lower()
        if d in DAY_NAMES and d not in result:
            result.append(d)
    return result or DAY_NAMES[:]


def _parse_times(times: List[str]) -> List[Tuple[int, int]]:
    parsed: List[Tuple[int, int]] = []
    for t in times:
        try:
            hh, mm = t.split(":")
            hh_i = int(hh)
            mm_i = int(mm)
            if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
                parsed.append((hh_i, mm_i))
        except Exception:
            continue
    return parsed


def _compute_target_slot_key(
    schedule: Dict[str, Any], tz_str: str, now_utc: datetime
) -> Optional[str]:
    """
    Given a schedule and "now" in UTC, determine if there is a scheduled slot
    that should fire at or before now, and hasn't already been run for this slot.

    Returns:
        - A slot_key string like "YYYY-MM-DDT13:00" if the job is due.
        - None if not due.

    We rely on schedule["last_run_key"] to ensure we don't run the same slot twice.
    """
    tz = ZoneInfo(tz_str)
    now_local = now_utc.astimezone(tz)

    days = _normalize_days(schedule.get("days_of_week"))
    day_name = DAY_NAMES[now_local.weekday()]
    if day_name not in days:
        return None

    times_parsed = _parse_times(schedule.get("times", []))
    if not times_parsed:
        return None

    # Build today's scheduled local datetimes
    slots_local: List[datetime] = []
    for hh, mm in times_parsed:
        slot_local = now_local.replace(
            hour=hh, minute=mm, second=0, microsecond=0
        )
        slots_local.append(slot_local)

    # Consider only slots that are <= now_local
    past_or_now_slots = [s for s in slots_local if s <= now_local]
    if not past_or_now_slots:
        return None

    # Latest slot that is <= now
    target_local = max(past_or_now_slots)
    target_key = target_local.strftime("%Y-%m-%dT%H:%M")

    last_run_key = schedule.get("last_run_key")
    if last_run_key == target_key:
        # already ran this time slot
        return None

    return target_key


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

def _run_subprocess(cmd: List[str], extra_env: Optional[Dict[str, str]] = None) -> int:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    logger.info("Executing command: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=600,
        )
    except Exception as exc:
        logger.error("Subprocess failed to start: %s", exc)
        return 1

    if result.stdout:
        # pipe child logs into scheduler logs for visibility
        for line in result.stdout.splitlines():
            logger.info("[child] %s", line)

    if result.returncode != 0:
        logger.error("Command exited with code %s", result.returncode)
    else:
        logger.info("Command completed successfully.")

    return result.returncode


def execute_schedule(account: Dict[str, Any], schedule: Dict[str, Any]) -> None:
    action = schedule.get("action") or "run_post_live"
    category = schedule.get("category")
    account_id = account.get("id", "unknown")

    logger.info(
        "Executing schedule id=%s for account=%s action=%s category=%s",
        schedule.get("id"),
        account_id,
        action,
        category,
    )

    if action == "run_post_live":
        # Live post using /app/run_post.sh
        # If category is None, run_post.sh will rotate/select on its own.
        if category:
            cmd = ["/app/run_post.sh", str(category)]
        else:
            cmd = ["/app/run_post.sh"]
        _run_subprocess(cmd)

    elif action == "generate_to_queue":
        # Generate into queue, not post immediately.
        # We require a category here; POST_MODE=queue is passed via env.
        if not category:
            logger.error(
                "generate_to_queue schedule id=%s missing 'category'; skipping.",
                schedule.get("id"),
            )
            return
        cmd = ["/app/run_post.sh", str(category)]
        _run_subprocess(cmd, extra_env={"POST_MODE": "queue"})

    elif action == "post_from_queue":
        # Post the next approved item from the queue
        cmd = ["python", "/app/queue_poster.py", "post-next"]
        _run_subprocess(cmd)

    else:
        logger.error(
            "Unknown action '%s' for schedule id=%s; skipping.",
            action,
            schedule.get("id"),
        )


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_init_config() -> int:
    if os.path.exists(CONFIG_PATH):
        logger.info("Config already exists at %s; not overwriting.", CONFIG_PATH)
        print(f"Config already exists at {CONFIG_PATH}")
        return 0

    cfg = default_config()
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    save_config(cfg)
    logger.info("Created starter config at %s", CONFIG_PATH)
    print(f"Created starter config at {CONFIG_PATH}")
    return 0


def cmd_show_config() -> int:
    cfg = load_config()
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    return 0


def cmd_tick() -> int:
    now_utc = datetime.now(timezone.utc)
    cfg = load_config()
    if not cfg.get("accounts"):
        logger.info("No accounts defined in scheduler_config.json; nothing to do.")
        return 0

    cfg_new = deepcopy(cfg)
    any_changes = False

    for account in cfg_new.get("accounts", []):
        acc_id = account.get("id", "unknown")
        tz_str = account.get("timezone", "UTC")
        schedules = account.get("schedules", [])
        if not schedules:
            continue

        for schedule in schedules:
            if not schedule.get("enabled", True):
                continue

            slot_key = _compute_target_slot_key(schedule, tz_str, now_utc)
            if not slot_key:
                # Not due (either wrong day, not reached time yet, or already ran)
                continue

            logger.info(
                "Schedule id=%s for account=%s is due for slot %s",
                schedule.get("id"),
                acc_id,
                slot_key,
            )

            try:
                execute_schedule(account, schedule)
            except Exception as exc:
                logger.exception(
                    "Error executing schedule id=%s for account=%s: %s",
                    schedule.get("id"),
                    acc_id,
                    exc,
                )
                # We still set last_run_key so we don't hammer it every minute
                schedule["last_run_key"] = slot_key
                any_changes = True
                continue

            # Mark this slot as executed
            schedule["last_run_key"] = slot_key
            any_changes = True

    if any_changes:
        save_config(cfg_new)
        logger.info("Scheduler state updated in %s", CONFIG_PATH)

    return 0


def main(argv=None) -> int:
    setup_logging()

    parser = argparse.ArgumentParser(description="Vibepilot scheduler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-config", help="Create a starter scheduler_config.json")
    subparsers.add_parser("show-config", help="Print current scheduler config")
    subparsers.add_parser("tick", help="Run one scheduler tick")

    args = parser.parse_args(argv)

    if args.command == "init-config":
        return cmd_init_config()
    if args.command == "show-config":
        return cmd_show_config()
    if args.command == "tick":
        return cmd_tick()

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
