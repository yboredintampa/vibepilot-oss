# -*- coding: utf-8 -*-
# Small helpers for the poster runner so we don't touch your existing utils.py
import os, json, time, pathlib, logging
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv, find_dotenv
    # Load .env from:
    # 1) current working dir
    # 2) this file's folder
    # 3) walk-up search (find_dotenv)
    cwd_env = pathlib.Path(".") / ".env"
    here_env = pathlib.Path(__file__).with_name(".env")
    loaded = False
    for p in (cwd_env, here_env):
        if p.exists():
            load_dotenv(p, override=True)
            loaded = True
            break
    if not loaded:
        found = find_dotenv(usecwd=True)
        if found:
            load_dotenv(found, override=True)
except Exception:
    pass

def env(key, default=None, cast=str):
    v = os.getenv(key, default)
    if v is None:
        return None
    if cast is bool:
        return str(v).strip().lower() in {"1","true","yes","on"}
    if cast is int:
        try:
            return int(v)
        except Exception:
            return default
    return v

ROOT = pathlib.Path(os.getcwd())
LOG_DIR = pathlib.Path(env("LOG_DIR","./logs")).resolve()
LOG_DIR.mkdir(parents=True, exist_ok=True)
RECENT_POSTS_JSON = LOG_DIR / "recent_posts.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def _now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _hash_text(t: str) -> str:
    import hashlib
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]

def _load_recent():
    if RECENT_POSTS_JSON.exists():
        try:
            return json.loads(RECENT_POSTS_JSON.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _save_recent(items):
    RECENT_POSTS_JSON.write_text(json.dumps(items, indent=2), encoding="utf-8")

def was_recently_posted(caption: str) -> bool:
    window_days = env("REPEAT_WINDOW_DAYS","14",int)
    h = _hash_text(caption)
    items = _load_recent()
    cutoff = (datetime.now() - timedelta(days=window_days)).timestamp()
    items = [i for i in items if i.get("ts",0) >= cutoff]
    _save_recent(items)
    return any(i.get("hash")==h for i in items)

def mark_posted(caption: str, meta: dict):
    items = _load_recent()
    items.append({"hash": _hash_text(caption), "ts": time.time(), "meta": meta})
    _save_recent(items)

def write_run_log(caption, image_url=None, category="default", ok=True, reason=None):
    ts = _now_iso().replace(":", "-").replace(" ", "_")
    base = LOG_DIR / f"run_{ts}"
    cap_html = caption.replace("\n", "<br>")
    md = base.with_suffix(".md")
    md.write_text(
        f"# Vibepilot Run {_now_iso()}\n\n- OK: {ok}\n- Category: {category}\n- Caption:\n\n{caption}\n\n- Image: {image_url or 'text-only'}\n- Reason: {reason or '-'}\n",
        encoding="utf-8"
    )
    html = base.with_suffix(".html")
    html.write_text(
        f"""<html><body><h1>Vibepilot Run {_now_iso()}</h1>
<p><b>OK:</b> {ok}</p>
<p><b>Category:</b> {category}</p>
<p><b>Caption:</b><br>{cap_html}</p>
<p><b>Image:</b> {image_url or 'text-only'}</p>
<p><b>Reason:</b> {reason or '-'}</p>
</body></html>""",
        encoding="utf-8"
    )
