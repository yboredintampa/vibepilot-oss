"""
Main entrypoint for the VibePilot API container.

The Docker image starts uvicorn with `main:app`.
This file defines the FastAPI app, mounts the admin dashboard at /admin,
and exposes small scheduler helper endpoints for the queue + scheduler UI.
"""

import os
import json
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse, HTMLResponse
import datetime
import logging
from typing import Any, Dict, List, Tuple

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse

from vp_security import database_password_present, require_admin, validate_startup_env

# Refuse to start with missing or insecure secrets (no insecure defaults).
validate_startup_env(["VP_ADMIN_USER", "VP_ADMIN_PASS", "VP_INTERNAL_API_TOKEN", "JWT_SECRET"])
database_password_present()

from admin_dashboard import router as admin_router
from command_center import router as command_center_router
import poster
try:
    from . import llm_safety as safety
except ImportError:  # running as top-level modules (Docker: uvicorn main:app)
    import llm_safety as safety

log = logging.getLogger("vibepilot.main")

# ----------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------
app = FastAPI(
    title="VibePilot API",
    version="0.1.0",
    # Interactive API docs are disabled unless explicitly enabled.
    docs_url="/docs" if os.getenv("VP_ENABLE_DOCS") == "true" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if os.getenv("VP_ENABLE_DOCS") == "true" else None,
)


@app.get("/health")
async def health():
    """
    Lightweight health check used by Docker and external monitors.
    Returns 200 OK with a simple JSON payload.
    """
    return {"status": "ok"}


# Mount admin dashboard under /admin
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(
    command_center_router,
    prefix="/command-center",
    tags=["command-center"],
    dependencies=[Depends(require_admin)],
)
# Mount static files (dashboard assets; contain no secrets)
app.mount("/static", StaticFiles(directory="static", check_dir=False), name="static")

# Generated post images (these are published to social media anyway)
GENERATED_IMAGES_DIR = os.getenv("GENERATED_IMAGES_DIR", "/app/generated_images")
app.mount(
    "/generated_images",
    StaticFiles(directory=GENERATED_IMAGES_DIR, check_dir=False),
    name="generated_images",
)


# Serve command center HTML at root path
@app.get("/command-center", dependencies=[Depends(require_admin)])
async def serve_command_center():
    return FileResponse("static/command-center.html")


# ----------------------------------------------------------------------
# Queue helpers
# ----------------------------------------------------------------------
POST_QUEUE_DIR = os.getenv("POST_QUEUE_DIR", "/app/post_queue")


def _iter_queue() -> List[Tuple[str, str, Dict[str, Any]]]:
    """
    Return a list of (filename, path, data) for all queue JSON files.

    - Skips internal folders like _deleted
    - Ignores malformed JSON
    - Sorted by mtime (oldest first)
    """
    items: List[Tuple[str, str, Dict[str, Any]]] = []

    if not os.path.isdir(POST_QUEUE_DIR):
        return items

    for fname in os.listdir(POST_QUEUE_DIR):
        # Skip internal dirs and non-JSON
        if fname.startswith("_") or not fname.endswith(".json"):
            continue

        path = os.path.join(POST_QUEUE_DIR, fname)
        if not os.path.isfile(path):
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            # Corrupt or partial file – skip quietly
            continue

        items.append((fname, path, data))

    # Oldest first
    items.sort(key=lambda tup: os.path.getmtime(tup[1]))
    return items


# ----------------------------------------------------------------------
# Scheduler + queue API
# ----------------------------------------------------------------------
@app.get("/scheduler/queue_preview", dependencies=[Depends(require_admin)])
def scheduler_queue_preview(
    limit: int = Query(50, ge=1, le=500),
    status: str | None = Query(
        None,
        description="Optional status filter: pending_review, approved, posted",
    ),
):
    """
    Return a lightweight preview of items in the queue for the admin UI.

    Only returns a caption preview (not the full caption) and basic metadata,
    so we don't leak anything sensitive if this endpoint is ever exposed.
    """
    status_filter = status.strip().lower() if status else None
    items_raw = _iter_queue()

    preview: List[Dict[str, Any]] = []

    for fname, path, data in items_raw:
        item_status = (data.get("status") or "pending_review").strip().lower()
        if status_filter and item_status != status_filter:
            continue

        caption = data.get("caption") or ""
        created_at = data.get("created_at")
        scheduled_for = data.get("scheduled_for")
        posted_at = data.get("posted_at")

        preview.append(
            {
                "file": fname,
                "id": data.get("id"),
                "category": data.get("category"),
                "status": item_status,
                "created_at": created_at,
                "scheduled_for": scheduled_for,
                "posted_at": posted_at,
                "caption_preview": caption[:160],
                "has_image": bool(data.get("image_path")),
            }
        )

        if len(preview) >= limit:
            break

    return {"ok": True, "items": preview}


@app.post("/scheduler/force_run", dependencies=[Depends(require_admin)])
def scheduler_force_run():
    """
    Generate the next post and drop it into the queue as pending_review.

    This mirrors what `/app/run_post.sh` does:
    - Calls poster.main(), which:
        * Rotates category based on your rotation config
        * Generates caption via Replicate (or fallback)
        * Generates image via Replicate
        * Enqueues the post to /app/post_queue

    It does NOT post to Facebook; that's still controlled separately via
    queue approval + /scheduler/post_next_approved.
    """
    try:
        # poster.main() encapsulates the queue-first behavior.
        poster.main()
        return JSONResponse(
            {
                "ok": True,
                "message": "Force post triggered via poster.main() (queue mode).",
            }
        )
    except Exception as e:
        log.exception("scheduler_force_run failed: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/scheduler/post_next_approved", dependencies=[Depends(require_admin)])
def scheduler_post_next_approved():
    """
    Find the **oldest** item in /app/post_queue with status == 'approved',
    send it to Facebook via poster.post_to_facebook(), and then mark it
    as 'posted' in the queue file.

    This is what cron (and later the per-card "Post now" button) should call
    when you’re in semi-auto mode.

    Security / safety notes:
    - Only operates on local queue files (no external state).
    - Never exposes tokens or secrets in the response.
    - If updating the queue file fails *after* posting to Facebook, we log
      the error but still return HTTP 200 to avoid duplicate posting loops.
    """
    try:
        approved_items: List[Tuple[float, str, str, Dict[str, Any]]] = []

        for fname, path, data in _iter_queue():
            status = (data.get("status") or "pending_review").strip().lower()
            if status != "approved":
                continue

            mtime = os.path.getmtime(path)
            approved_items.append((mtime, fname, path, data))

        if not approved_items:
            return JSONResponse(
                {"ok": False, "error": "no approved posts in queue"},
                status_code=404,
            )

        # Oldest approved first
        approved_items.sort(key=lambda x: x[0])
        _, fname, path, data = approved_items[0]

        caption = data.get("caption") or ""
        image_path = data.get("image_path") or ""

        if image_path and not os.path.exists(image_path):
            return JSONResponse(
                {"ok": False, "error": f"image missing for {fname}"},
                status_code=500,
            )

        # Actually post to Facebook using your helper in poster.py
        safety.require_approval(data)  # outbound action: only for human-approved items
        fb_ok = poster.post_to_facebook(
            caption=caption,
            image_path=image_path if image_path else None,
            approved=True,
        )

        if not fb_ok:
            return JSONResponse(
                {"ok": False, "error": f"Facebook post failed for {fname}"},
                status_code=502,
            )

        # Mark it as posted in the queue file
        data["status"] = "posted"
        data["posted_at"] = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as write_exc:
            # We already posted to FB; log this but don't return an error so
            # the scheduler doesn't hammer the same item repeatedly.
            log.exception("Failed to update queue file %s: %s", fname, write_exc)

        return JSONResponse(
            {
                "ok": True,
                "message": f"Posted {fname} to Facebook and marked as posted",
                "file": fname,
            }
        )

    except Exception as e:
        log.exception("scheduler_post_next_approved failed: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
@app.get("/admin/command", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def command_center_dashboard():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VibePilot Command Center</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a0033 0%, #2d1b4e 50%, #1a0033 100%);
            color: #e0d4f7; min-height: 100vh; padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        header { text-align: center; margin-bottom: 40px; padding: 30px 0; border-bottom: 2px solid rgba(139,92,246,0.3); }
        h1 { font-size: 3em; font-weight: 700; background: linear-gradient(135deg, #a78bfa 0%, #8b5cf6 50%, #7c3aed 100%);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px; }
        .subtitle { color: #c4b5fd; font-size: 1.1em; opacity: 0.8; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 25px; margin-bottom: 40px; }
        .card { background: rgba(139,92,246,0.1); border: 2px solid rgba(139,92,246,0.3); border-radius: 16px;
                padding: 25px; transition: all 0.3s ease; }
        .card:hover { transform: translateY(-5px); border-color: rgba(139,92,246,0.6); box-shadow: 0 12px 48px rgba(139,92,246,0.2); }
        .card-title { font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; color: #c4b5fd; margin-bottom: 15px; opacity: 0.8; }
        .card-value { font-size: 2.5em; font-weight: 700; color: #a78bfa; margin-bottom: 8px; }
        .card-subtitle { font-size: 0.85em; color: #ddd6fe; opacity: 0.7; }
        .countdown-section { background: rgba(139,92,246,0.15); border: 3px solid rgba(139,92,246,0.4); border-radius: 20px;
                             padding: 40px; margin-bottom: 40px; text-align: center; }
        .countdown-value { font-size: 4em; font-weight: 700; background: linear-gradient(135deg, #a78bfa 0%, #8b5cf6 50%, #7c3aed 100%);
                          -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .progress-bar { width: 100%; height: 30px; background: rgba(0,0,0,0.3); border-radius: 15px; overflow: hidden; margin: 20px 0; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #8b5cf6 0%, #a78bfa 100%); transition: width 0.5s ease; }
        .timestamp { text-align: center; color: #c4b5fd; opacity: 0.6; margin-top: 30px; }
        @media (max-width: 768px) { h1 { font-size: 2em; } .card-value { font-size: 2em; } .countdown-value { font-size: 2.5em; } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ VIBEPILOT COMMAND CENTER ⚡</h1>
            <div class="subtitle">Real-time mission metrics • Auto-refresh every 30s</div>
        </header>
        <div class="countdown-section">
            <div class="card-title">🎯 USERS UNTIL HANDOVER</div>
            <div class="countdown-value" id="countdown">300,000</div>
            <div class="progress-bar"><div class="progress-fill" id="progress" style="width: 0%"></div></div>
            <div class="card-subtitle" id="estimate">Awaiting first user</div>
        </div>
        <div class="grid">
            <div class="card"><div class="card-title">👥 Total Users</div><div class="card-value" id="total-users">0</div><div class="card-subtitle">All registered</div></div>
            <div class="card"><div class="card-title">✅ Active Subs</div><div class="card-value" id="active-subs">0</div><div class="card-subtitle">Paying customers</div></div>
            <div class="card"><div class="card-title">💰 Revenue</div><div class="card-value" id="revenue">$0</div><div class="card-subtitle">Lifetime Stripe</div></div>
            <div class="card"><div class="card-title">🏥 Health Fund</div><div class="card-value" id="health-fund">$0</div><div class="card-subtitle">8.5% healthcare</div></div>
            <div class="card"><div class="card-title">🌱 Farm Fund</div><div class="card-value" id="farm-fund">$0</div><div class="card-subtitle" id="acres">0 acres</div></div>
            <div class="card"><div class="card-title">🛡️ Life Fund</div><div class="card-value" id="life-fund">$0</div><div class="card-subtitle">1.5% insurance</div></div>
        </div>
        <div class="timestamp" id="timestamp">Last updated: Never</div>
    </div>
    <script>
        function fmt(n){return new Intl.NumberFormat('en-US').format(n);}
        function fmtUSD(n){return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:0}).format(n);}
        async function load(){
            try{
                const r=await fetch('/command-center/json');
                const d=await r.json();
                document.getElementById('total-users').textContent=fmt(d.total_users);
                document.getElementById('active-subs').textContent=fmt(d.active_subscribers);
                document.getElementById('revenue').textContent=fmtUSD(d.stripe_lifetime_gross_usd);
                document.getElementById('health-fund').textContent=fmtUSD(d.health_fund_usd);
                document.getElementById('farm-fund').textContent=fmtUSD(d.farm_fund_usd);
                document.getElementById('life-fund').textContent=fmtUSD(d.life_fund_usd);
                document.getElementById('countdown').textContent=fmt(d.countdown_to_300k);
                document.getElementById('estimate').textContent=`Est: ${d.estimated_days_to_300k}`;
                document.getElementById('acres').textContent=`${fmt(d.acres_purchasable)} acres`;
                document.getElementById('progress').style.width=`${((300000-d.countdown_to_300k)/300000)*100}%`;
                document.getElementById('timestamp').textContent=`Last: ${new Date().toLocaleString()}`;
            }catch(e){console.error(e);}
        }
        load();
        setInterval(load,30000);
    </script>
</body>
</html>"""
    return html
