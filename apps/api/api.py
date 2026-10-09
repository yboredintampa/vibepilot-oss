import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Optional: load env vars if python-dotenv is present
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


from vp_security import database_password_present, require_admin, validate_startup_env  # noqa: E402

# Refuse to start with missing or insecure secrets (no insecure defaults).
validate_startup_env(["VP_ADMIN_USER", "VP_ADMIN_PASS", "VP_INTERNAL_API_TOKEN", "JWT_SECRET"])
database_password_present()

APP_NAME = "VibePilot API"
APP_VERSION = "0.1.0"

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url="/docs" if os.getenv("VP_ENABLE_DOCS") == "true" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if os.getenv("VP_ENABLE_DOCS") == "true" else None,
)

# -------------------------------------------------------------------
# CORS
# -------------------------------------------------------------------
_default_origins = "http://localhost:3000,http://localhost:5173"
origins = os.getenv("CORS_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Routers from the rest of the API
# -------------------------------------------------------------------
from auth import router as auth_router          # noqa: E402
from brand import router as brand_router        # noqa: E402
from content import router as content_router    # noqa: E402

# storage is optional in your stack
_HAS_STORAGE = False
storage_router = None
try:  # noqa: E402
    from storage import router as storage_router  # type: ignore
    _HAS_STORAGE = True
except Exception:
    _HAS_STORAGE = False
    storage_router = None

# Admin dashboard router
from admin_dashboard import router as admin_router  # noqa: E402


# Mount all routers
app.include_router(content_router)
app.include_router(auth_router)
if _HAS_STORAGE and storage_router is not None:
    app.include_router(storage_router)
app.include_router(brand_router)

# Admin UI + JSON endpoints under /admin
app.include_router(admin_router, prefix="/admin", tags=["admin"])
print("[api.py] Admin dashboard router mounted at /admin")  # shows up in container logs


# -------------------------------------------------------------------
# Root + health
# -------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    """
    Redirect bare domain to the admin UI.

    Avoids a bare 'Not Found' JSON response at the site root.
    """
    return RedirectResponse(url="/admin/")


@app.get("/health")
def health():
    return {
        "ok": True,
        "name": APP_NAME,
        "version": APP_VERSION,
    }
# ============================
# Force Scheduler Run Endpoint
# ============================
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import os, json

from poster import run_single_post

from fastapi import Depends  # noqa: E402

router = APIRouter(dependencies=[Depends(require_admin)])

POST_QUEUE_DIR = os.getenv("POST_QUEUE_DIR", "/app/post_queue")

@router.post("/scheduler/force_run")
async def force_run_next_post():
    """
    Detects the next queued post and forces it to run immediately.
    """
    try:
        # Find next pending post
        if not os.path.exists(POST_QUEUE_DIR):
            return JSONResponse({"ok": False, "error": "post_queue folder missing"}, status_code=404)

        pending_files = [
            f for f in sorted(os.listdir(POST_QUEUE_DIR))
            if f.endswith(".json") and not f.startswith("_")
        ]
        if not pending_files:
            return JSONResponse({"ok": False, "error": "no posts found in queue"}, status_code=404)

        next_file = None
        for fname in pending_files:
            path = os.path.join(POST_QUEUE_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status", "pending_review") == "pending_review":
                    next_file = path
                    break
            except Exception:
                continue

        if not next_file:
            return JSONResponse({"ok": False, "error": "no pending_review posts found"}, status_code=404)

        with open(next_file, "r", encoding="utf-8") as f:
            post_data = json.load(f)

        category = post_data.get("category", "realistic")
        result = run_single_post(category)

        # Mark as processed
        post_data["status"] = "approved_and_posted"
        with open(next_file, "w", encoding="utf-8") as f:
            json.dump(post_data, f, ensure_ascii=False, indent=2)

        return JSONResponse({"ok": True, "category": category, "result": str(result)})

    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
