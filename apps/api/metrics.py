import csv, os, hashlib, time
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CSV_PATH = Path("/var/log/vibepilot/posts.csv")

HEADER = [
    "ts_utc","ts_est","category","dry_run",
    "caption_len","caption_sha1_10",
    "image_mode","image_mime","jpeg_size_kb",
    "replicate_model","prediction_id","duration_ms",
    "fb_status","http_code","error_code","error_subcode",
    "post_id","media_id"
]

def _now():
    utc = datetime.now(timezone.utc)
    est = utc.astimezone(ZoneInfo("America/New_York"))
    return utc.isoformat(), est.isoformat()

def _sha10(s: str) -> str:
    return hashlib.sha1((s or "").encode()).hexdigest()[:10]

def _ensure_header():
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADER)

def log_row(
    *, category, dry_run, caption,
    image_mode, image_mime=None, jpeg_size_kb=None,
    replicate_model=None, prediction_id=None, duration_ms=None,
    fb_status=None, http_code=None, error_code=None, error_subcode=None,
    post_id=None, media_id=None,
):
    _ensure_header()
    ts_utc, ts_est = _now()
    row = [
        ts_utc, ts_est, category, int(bool(dry_run)),
        len(caption or ""), _sha10(caption or ""),
        image_mode, image_mime or "", (jpeg_size_kb or 0),
        replicate_model or "", prediction_id or "", (duration_ms or 0),
        fb_status or "", (http_code or 0), (error_code or 0), (error_subcode or 0),
        post_id or "", media_id or "",
    ]
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
