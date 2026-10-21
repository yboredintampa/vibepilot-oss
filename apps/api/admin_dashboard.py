from fastapi import (
    APIRouter,
    Request,
    Body,
    HTTPException,
    Depends,
    status,
    Form,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    FileResponse,
    RedirectResponse,
)
from typing import Optional, Dict, Any, List
import json
import os
import datetime
import secrets

from vp_security import require_env, constant_time_equals, rate_limit, client_ip, is_internal_request

import poster

router = APIRouter()

# -----------------------------
# Session-based admin auth
# -----------------------------

SESSION_COOKIE_NAME = "vp_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days

# In-memory session store: token -> expiry ISO string
ADMIN_SESSIONS: Dict[str, str] = {}


def _get_admin_credentials() -> tuple[str, str]:
    """
    Admin username/password come from env vars. There are NO defaults:
    the app refuses to start without them (see vp_security).
    """
    correct_username = require_env("VP_ADMIN_USER")
    correct_password = require_env("VP_ADMIN_PASS")
    return correct_username, correct_password


def _create_admin_session(username: str) -> str:
    """
    Create a random session token for the logged-in admin.
    Stored in memory with an expiry timestamp.
    """
    token = secrets.token_hex(32)
    expires_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(
        seconds=SESSION_TTL_SECONDS
    )
    ADMIN_SESSIONS[token] = expires_at.isoformat() + "Z"
    return token


def _validate_admin_session(token: Optional[str]) -> bool:
    """
    Check if the session token exists and hasn't expired.
    Expired sessions are cleaned up on access.
    """
    if not token:
        return False

    exp_iso = ADMIN_SESSIONS.get(token)
    if not exp_iso:
        return False

    try:
        exp = datetime.datetime.fromisoformat(exp_iso.replace("Z", ""))
    except Exception:
        # If parsing fails, treat as invalid
        ADMIN_SESSIONS.pop(token, None)
        return False

    if exp < datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None):
        ADMIN_SESSIONS.pop(token, None)
        return False

    return True


def require_admin_session(request: Request):
    """
    Dependency used by all protected admin JSON endpoints.
    Accepts a valid admin session cookie, or the internal service token
    (Authorization: Bearer $VP_INTERNAL_API_TOKEN) for cron/scripts.
    """
    if is_internal_request(request):
        return True
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if _validate_admin_session(token):
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


# -----------------------------
# Paths & constants
# -----------------------------
QUEUE_DIR = os.getenv("POST_QUEUE_DIR", "/app/post_queue")
DELETED_DIR = os.path.join(QUEUE_DIR, "_deleted")
LOG_DIR = os.getenv("VP_LOG_DIR", "/app/logs")
IMAGES_DIR = os.getenv("GENERATED_IMAGES_DIR", "/app/generated_images")
SCHEDULER_CONFIG_PATH = os.getenv("SCHEDULER_CONFIG_PATH", "/app/scheduler_config.json")
STATIC_HTML_PATH = os.getenv("VP_ADMIN_HTML_PATH", "/app/static/admin_dashboard.html")

# Insights + privacy proofs
DELETED_INSIGHTS_PATH = os.path.join(LOG_DIR, "deleted_insights.json")
PRIVACY_PROOFS_LOG = os.path.join(LOG_DIR, "privacy_proofs.log")
SUPPORT_PUSH_LOG = os.path.join(LOG_DIR, "support_push.log")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DELETED_DIR, exist_ok=True)

CATEGORY_COLORS: Dict[str, str] = {
    "realistic": "#38bdf8",      # blue-ish
    "meme": "#facc15",           # yellow
    "persuasive": "#22c55e",     # green
    "comedic": "#f97316",        # orange
    "educational": "#a855f7",    # purple
    "confrontational": "#ef4444",
}

STATUS_COLORS: Dict[str, str] = {
    "pending_review": "#facc15",
    "approved": "#22c55e",
    "deleted": "#b91c1c",
    "posted": "#22c55e",
}

DEFAULT_SCHEDULER_CONFIG: Dict[str, Any] = {
    "post_times": ["08:00", "13:00", "18:00"],
    "preview_generation_time": "18:00",
    "blog_posts_per_week": 3,
    "brand_voice": 70,
}

# Categories for manual "Generate Next" rotation
FORCE_RUN_CATEGORIES: List[str] = [
    "realistic",
    "meme",
    "educational",
    "comedic",
    "confrontational",
    "persuasive",
]

# Simple state file inside the container; if it disappears, we just restart at index 0
FORCE_RUN_STATE_PATH = os.getenv("VP_FORCE_RUN_STATE_PATH", "/app/force_run_state.json")


def get_next_force_run_category() -> str:
    """
    Deterministic round-robin category picker for the admin 'Generate Next' button.
    Cycles through FORCE_RUN_CATEGORIES in order, then wraps.
    """
    idx = 0
    try:
        if os.path.exists(FORCE_RUN_STATE_PATH):
            with open(FORCE_RUN_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                idx = int(data.get("index", 0))
    except Exception:
        idx = 0

    category = FORCE_RUN_CATEGORIES[idx % len(FORCE_RUN_CATEGORIES)]

    # advance and persist index
    try:
        with open(FORCE_RUN_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"index": (idx + 1) % len(FORCE_RUN_CATEGORIES)}, f)
    except Exception:
        pass

    return category


# -----------------------------
# Helpers
# -----------------------------
def sanitize_category(cat: str) -> str:
    """Normalize category; avoid bogus values like '--category'."""
    if not cat:
        return "realistic"
    cat = cat.strip().lower()
    if not cat or cat.startswith("--"):
        return "realistic"
    return cat


def pretty_category(cat: str) -> str:
    cat = sanitize_category(cat)
    return {
        "realistic": "REALISTIC",
        "meme": "MEME",
        "persuasive": "PERSUASIVE",
        "educational": "EDUCATIONAL",
        "comedic": "COMEDIC",
        "confrontational": "CONFRONTATIONAL",
    }.get(cat, cat.upper())


def log_json(path: str, payload: dict) -> None:
    payload = dict(payload)
    payload["ts"] = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def list_queue_items() -> List[Dict[str, Any]]:
    """Return last 40 posts from /app/post_queue as JSON-ready dicts."""
    items: List[Dict[str, Any]] = []
    if not os.path.exists(QUEUE_DIR):
        return items

    for fname in sorted(os.listdir(QUEUE_DIR)):
        if fname.startswith("_") or not fname.endswith(".json"):
            continue

        path = os.path.join(QUEUE_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        cat = sanitize_category(str(data.get("category", "")))
        status_val = (data.get("status") or "pending_review").strip().lower()
        caption = data.get("caption") or ""
        img_path = data.get("image_path") or ""
        img_name = os.path.basename(img_path) if img_path else ""
        image_url = f"/generated_images/{img_name}" if img_name else ""
        created_at = data.get("created_at") or ""

        items.append(
            {
                "id": data.get("id") or fname,
                "file_name": fname,
                "category": cat,
                "category_label": pretty_category(cat),
                "category_color": CATEGORY_COLORS.get(cat, "#64748b"),
                "status": status_val,
                "status_color": STATUS_COLORS.get(status_val, "#facc15"),
                "caption": caption,
                "image_url": image_url,
                "created_at": created_at,
            }
        )

    # latest 40, newest first
    return items[-40:][::-1]


def find_post_by_id_or_file(
    item_id: str, file_name: Optional[str]
) -> tuple[Optional[dict], Optional[str], Optional[str]]:
    """Locate a post JSON file by file_name (preferred) or id."""
    # 1) direct file name
    if file_name:
        path = os.path.join(QUEUE_DIR, file_name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f), path, file_name
            except Exception:
                pass

    # 2) search by id field
    if not os.path.exists(QUEUE_DIR):
        return None, None, None

    for fname in os.listdir(QUEUE_DIR):
        if fname.startswith("_") or not fname.endswith(".json"):
            continue
        path = os.path.join(QUEUE_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if str(data.get("id")) == str(item_id):
            return data, path, fname

    return None, None, None


def read_scheduler_config() -> dict:
    cfg = dict(DEFAULT_SCHEDULER_CONFIG)
    if os.path.exists(SCHEDULER_CONFIG_PATH):
        try:
            with open(SCHEDULER_CONFIG_PATH, "r", encoding="utf-8") as f:
                disk = json.load(f)
            if isinstance(disk, dict):
                cfg.update(disk)
        except Exception:
            pass
    return cfg


def write_scheduler_config(update: dict) -> dict:
    cfg = read_scheduler_config()
    for key in [
        "post_times",
        "preview_generation_time",
        "blog_posts_per_week",
        "brand_voice",
    ]:
        if key in update and update[key] is not None:
            cfg[key] = update[key]
    with open(SCHEDULER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def read_deleted_insights() -> dict:
    """
    Load the latest deleted-post insights generated by apps/api/deleted_insights.py.

    That job writes a JSON file at LOG_DIR/deleted_insights.json with a structure like:
    {
      "generated_at": "...",
      "sample_size": 4,
      "used_llm": true,
      "suggestions": "Here are the patterns and recommendations: ...",
      "example_categories": [...]
    }
    """
    if os.path.exists(DELETED_INSIGHTS_PATH):
        try:
            with open(DELETED_INSIGHTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # Friendly default
    return {
        "generated_at": None,
        "sample_size": 0,
        "used_llm": False,
        "suggestions": (
            "No deleted-post analysis available yet. "
            "The nightly insights job has not run, or there are no deleted posts."
        ),
        "example_categories": [],
    }


def read_privacy_proofs_summary() -> dict:
    """
    Aggregate stats from a privacy_proofs.log JSONL file.

    Expected (future) log line shape:
      {
        "event": "shred",
        "shared_publicly": true/false,
        "ts": "ISO8601",
        "meta": {...}  # NEVER includes raw user content or IDs
      }

    This function stays deliberately dumb: it only counts events and
    shared_publicly flags, plus a simple "this month" filter on ts.
    """
    total = 0
    total_shared = 0
    month = 0

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if not os.path.exists(PRIVACY_PROOFS_LOG):
        return {
            "total_events": 0,
            "total_shared_publicly": 0,
            "month_events": 0,
            "message": (
                "No privacy proofs recorded yet. Once your shred pipeline "
                "appends JSON lines here, this panel will show aggregated "
                "“wall of trust” stats only."
            ),
        }

    try:
        with open(PRIVACY_PROOFS_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                if obj.get("event") != "shred":
                    continue

                total += 1
                if obj.get("shared_publicly"):
                    total_shared += 1

                ts = obj.get("ts")
                try:
                    if ts:
                        ts_dt = datetime.datetime.fromisoformat(ts.replace("Z", ""))
                        if ts_dt >= month_start:
                            month += 1
                except Exception:
                    continue
    except Exception:
        # Fall through with zeros, keep default message
        return {
            "total_events": 0,
            "total_shared_publicly": 0,
            "month_events": 0,
            "message": (
                "Failed to read privacy proofs log. This is safe to ignore "
                "until the shred pipeline is wired up."
            ),
        }

    message = (
        f"{total} shred events total. "
        f"{total_shared} users opted to share confirmations. "
        f"{month} events recorded this month."
    )

    return {
        "total_events": total,
        "total_shared_publicly": total_shared,
        "month_events": month,
        "message": message,
    }


# -----------------------------
# Login / Logout HTML
# -----------------------------
@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """
    Simple admin login form. iPhone-friendly, lets Safari/Chrome
    offer to save username/password.
    """
    html = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Vibepilot Admin Login</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <style>
        body {
          margin: 0;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: radial-gradient(circle at top, #4c1d95, #020617 55%);
          color: #e5e7eb;
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .card {
          background: rgba(15, 23, 42, 0.95);
          border-radius: 1.25rem;
          padding: 1.75rem 1.5rem;
          max-width: 380px;
          width: 100%;
          box-shadow: 0 20px 40px rgba(15, 23, 42, 0.7);
          border: 1px solid rgba(129, 140, 248, 0.35);
        }
        .title {
          font-size: 1.25rem;
          font-weight: 700;
          margin-bottom: 0.25rem;
          letter-spacing: 0.04em;
        }
        .subtitle {
          font-size: 0.875rem;
          color: #9ca3af;
          margin-bottom: 1.25rem;
        }
        label {
          display: block;
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: #9ca3af;
          margin-bottom: 0.25rem;
        }
        input[type="text"],
        input[type="password"] {
          width: 100%;
          padding: 0.6rem 0.75rem;
          border-radius: 0.75rem;
          border: 1px solid #4b5563;
          background: rgba(15, 23, 42, 0.85);
          color: #e5e7eb;
          font-size: 0.9rem;
          outline: none;
        }
        input[type="text"]:focus,
        input[type="password"]:focus {
          border-color: #a855f7;
          box-shadow: 0 0 0 1px rgba(168, 85, 247, 0.3);
        }
        .field {
          margin-bottom: 0.75rem;
        }
        .button-row {
          margin-top: 1rem;
        }
        button {
          width: 100%;
          border: none;
          border-radius: 9999px;
          padding: 0.65rem 1rem;
          font-size: 0.95rem;
          font-weight: 600;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          cursor: pointer;
          background: linear-gradient(90deg, #a855f7, #6366f1);
          color: white;
        }
        button:active {
          transform: translateY(1px);
          filter: brightness(0.95);
        }
        .hint {
          margin-top: 0.75rem;
          font-size: 0.75rem;
          color: #6b7280;
        }
      </style>
    </head>
    <body>
      <div class="card">
        <div class="title">Vibepilot Admin</div>
        <div class="subtitle">Sign in to review & schedule content.</div>

        <form method="post" action="/admin/login" autocomplete="on">
          <div class="field">
            <label for="username">Username</label>
            <input
              id="username"
              type="text"
              name="username"
              autocomplete="username"
              autocapitalize="none"
              autocorrect="off"
              required
            />
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input
              id="password"
              type="password"
              name="password"
              autocomplete="current-password"
              required
            />
          </div>
          <div class="button-row">
            <button type="submit">Log in</button>
          </div>
          <div class="hint">
            Tip: let your browser save this login so you’re not retyping on mobile.
          </div>
        </form>
      </div>
    </body>
    </html>
    """.strip()
    return HTMLResponse(content=html)


@router.post("/login", response_class=HTMLResponse)
async def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    # Brute-force protection: 10 attempts / 15 min per client IP.
    rate_limit(f"admin-login:{client_ip(request)}", 10, 15 * 60)
    correct_username, correct_password = _get_admin_credentials()

    user_ok = constant_time_equals(username, correct_username)
    pass_ok = constant_time_equals(password, correct_password)
    if not (user_ok and pass_ok):
        html = """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <title>Vibepilot Admin Login</title>
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        </head>
        <body>
          <script>
            alert("Invalid username or password.");
            window.location.href = "/admin/login";
          </script>
        </body>
        </html>
        """.strip()
        return HTMLResponse(content=html, status_code=401)

    token = _create_admin_session(username)

    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        expires=SESSION_TTL_SECONDS,
        httponly=True,
        secure=os.getenv("VP_COOKIE_SECURE", "true").lower() != "false",  # set VP_COOKIE_SECURE=false only for local http dev
        samesite="lax",
    )
    return response


@router.get("/logout")
async def admin_logout(request: Request):
    """
    Invalidate the server-side session, clear the cookie, back to login.
    """
    ADMIN_SESSIONS.pop(request.cookies.get(SESSION_COOKIE_NAME) or "", None)
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# -----------------------------
# HTML dashboard
# -----------------------------
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """
    Main admin dashboard.

    If there is no valid session cookie, redirect to /admin/login.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not _validate_admin_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        with open(STATIC_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="admin_dashboard.html missing in /app/static",
        )
    return HTMLResponse(content=html)


# -----------------------------
# JSON endpoints (all behind session auth)
# -----------------------------
@router.get("/queue/all", dependencies=[Depends(require_admin_session)])
async def admin_queue_all():
    return {"items": list_queue_items()}


@router.get("/images/{image_name}", dependencies=[Depends(require_admin_session)])
async def admin_image(image_name: str):
    path = os.path.join(IMAGES_DIR, image_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(path)


@router.get("/scheduler/config", dependencies=[Depends(require_admin_session)])
async def admin_get_scheduler_config():
    return read_scheduler_config()


@router.post("/scheduler/config", dependencies=[Depends(require_admin_session)])
async def admin_set_scheduler_config(payload: dict = Body(...)):
    cfg = write_scheduler_config(payload or {})
    return {"ok": True, "config": cfg}


@router.post(
    "/item/{item_id}/translate", dependencies=[Depends(require_admin_session)]
)
async def admin_translate_item(item_id: str, payload: dict = Body(...)):
    """
    Caption translation is not implemented yet (see ROADMAP in README.md).
    Returns 501 instead of pretending to translate, and leaves the post untouched.
    """
    return JSONResponse(
        {
            "ok": False,
            "error": "Caption translation is not implemented yet.",
        },
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
    )


@router.post(
    "/item/{item_id}/delete", dependencies=[Depends(require_admin_session)]
)
async def admin_delete_item(item_id: str, payload: dict = Body(...)):
    """
    Delete a queue item and move it into QUEUE_DIR/_deleted.

    Expected payload (all optional except file_name):
      {
        "file_name": "...json",
        "rating": 2,
        "note": "too stiff",
        "image_score": 40,
        "caption_score": 60,
        "issue_type": "image" | "caption" | "both" | "other"
      }
    """
    file_name = payload.get("file_name")
    rating = payload.get("rating")
    note = payload.get("note") or ""
    image_score = payload.get("image_score")
    caption_score = payload.get("caption_score")
    issue_type = (payload.get("issue_type") or "").strip().lower() or None

    data, path, fname = find_post_by_id_or_file(item_id, file_name)
    if not data or not path:
        return JSONResponse({"ok": False, "error": "post not found"}, status_code=404)

    os.makedirs(DELETED_DIR, exist_ok=True)
    deleted_path = os.path.join(DELETED_DIR, fname)

    # Enrich the JSON itself so insights can read issue metadata
    issue_meta = data.get("issue_meta") or {}
    if image_score is not None:
        issue_meta["image_score"] = image_score
    if caption_score is not None:
        issue_meta["caption_score"] = caption_score
    if issue_type:
        issue_meta["issue_type"] = issue_type
    if rating is not None:
        issue_meta["rating"] = rating
    if note:
        issue_meta["note"] = note
    if issue_meta:
        data["issue_meta"] = issue_meta

    data["status"] = "deleted"

    with open(deleted_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Remove from live queue
    try:
        os.remove(path)
    except Exception:
        pass

    # Log compact feedback for analytics
    log_json(
        os.path.join(LOG_DIR, "admin_delete_feedback.log"),
        {
            "post_id": item_id,
            "file_name": fname,
            "rating": rating,
            "note": note,
            "image_score": image_score,
            "caption_score": caption_score,
            "issue_type": issue_type,
        },
    )
    return {"ok": True}


@router.post(
    "/item/{item_id}/approve", dependencies=[Depends(require_admin_session)]
)
async def admin_approve_item(item_id: str, payload: dict = Body(...)):
    file_name = payload.get("file_name")
    caption = payload.get("caption")
    voice_score = payload.get("voice_score")
    image_score = payload.get("image_score")

    data, path, fname = find_post_by_id_or_file(item_id, file_name)
    if not data or not path:
        return JSONResponse({"ok": False, "error": "post not found"}, status_code=404)

    data["status"] = "approved"
    if caption is not None:
        data["caption"] = caption
    if voice_score is not None or image_score is not None:
        scores = data.get("admin_scores") or {}
        if voice_score is not None:
            scores["voice"] = voice_score
        if image_score is not None:
            scores["image"] = image_score
        data["admin_scores"] = scores

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    log_json(
        os.path.join(LOG_DIR, "admin_approve.log"),
        {
            "post_id": item_id,
            "file_name": fname,
            "voice_score": voice_score,
            "image_score": image_score,
        },
    )

    return {"ok": True}


@router.post(
    "/item/{item_id}/post_now", dependencies=[Depends(require_admin_session)]
)
async def admin_post_now(item_id: str, payload: dict = Body(...)):
    """
    Post this specific item to Facebook immediately.
    Only succeeds if already approved. On success, marks as 'posted'
    and disables the button in the UI; on failure, button stays active.
    """
    file_name = payload.get("file_name")

    data, path, fname = find_post_by_id_or_file(item_id, file_name)
    if not data or not path:
        return JSONResponse({"ok": False, "error": "post not found"}, status_code=404)

    if data.get("status") != "approved":
        return JSONResponse({"ok": False, "error": "not approved yet"}, status_code=400)

    try:
        from .facebook_poster import post_to_facebook

        caption = data.get("caption") or ""
        image_path = data.get("image_path") or None

        result = post_to_facebook(caption, image_path)

        data["status"] = "posted"
        data["posted_at"] = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        log_json(
            os.path.join(LOG_DIR, "admin_postnow.log"),
            {
                "post_id": item_id,
                "file_name": fname,
                "status": "posted",
                "result": result,
            },
        )

        return JSONResponse(
            {"ok": True, "message": "Posted to Facebook", "result": result}
        )

    except Exception as e:
        log_json(
            os.path.join(LOG_DIR, "admin_postnow.log"),
            {
                "post_id": item_id,
                "file_name": fname,
                "error": str(e),
            },
        )
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500,
        )


@router.post("/scheduler/force_run", dependencies=[Depends(require_admin_session)])
async def force_run():
    """
    Manually trigger a single pipeline run from the dashboard.

    This walks through a fixed rotation of categories so you always get a mix:
    realistic → meme → educational → comedic → confrontational → persuasive → ...
    """
    try:
        category = get_next_force_run_category()
        category = sanitize_category(category)

        result = poster.run_single_post(category)

        log_json(
            os.path.join(LOG_DIR, "admin_force.log"),
            {"category": category, "result": result},
        )

        return {"ok": True, "message": f"Generated next ({category})"}
    except Exception as e:
        log_json(
            os.path.join(LOG_DIR, "admin_force.log"),
            {"error": str(e)},
        )
        return {"ok": False, "error": str(e)}


# -----------------------------
# Admin health + insights + privacy proofs
# -----------------------------
@router.get("/health", response_class=JSONResponse)
async def admin_health():
    """
    Lightweight health endpoint for the admin router.
    Does NOT require login; used by internal checks.
    """
    return JSONResponse(
        {"ok": True, "message": "Admin dashboard is online and reachable."}
    )


@router.get(
    "/insights/deleted",
    dependencies=[Depends(require_admin_session)],
)
async def admin_deleted_insights():
    """
    Return the most recent LLM analysis of deleted posts.

    The job that populates this file is run out-of-band (e.g. via cron)
    by calling: python -m apps.api.deleted_insights inside the vp-api container.
    """
    return read_deleted_insights()


@router.get(
    "/privacy/proofs",
    dependencies=[Depends(require_admin_session)],
)
async def admin_privacy_proofs():
    """
    Return aggregated stats from privacy_proofs.log.

    This is intentionally aggregate-only; no per-user breakdown.
    """
    return read_privacy_proofs_summary()


@router.post(
    "/support/push",
    dependencies=[Depends(require_admin_session)],
)
async def admin_support_push(payload: dict = Body(...)):
    """
    Accept an encrypted error/support bundle from a trusted client.

    Expected payload:
      {
        "ciphertext": "base64(AES-GCM blob)",
        "iv": "base64(12-byte IV)",
        "meta": { "source": "admin_dashboard_test", ... }
      }

    This endpoint NEVER attempts to decrypt. It only logs ciphertext + metadata
    so your future support tooling can pick it up, analyze in a separate,
    privacy-respecting pipeline, then shred.
    """
    ciphertext = payload.get("ciphertext")
    iv = payload.get("iv")
    meta = payload.get("meta") or {}

    if not ciphertext:
        raise HTTPException(status_code=400, detail="ciphertext required")

    log_json(
        SUPPORT_PUSH_LOG,
        {
            "ciphertext": ciphertext,
            "iv": iv,
            "meta": meta,
        },
    )

    return {"ok": True, "message": "Encrypted payload logged for support."}
