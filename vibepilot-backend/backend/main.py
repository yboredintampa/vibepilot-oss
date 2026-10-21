# backend/main.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Fail closed: refuse to start without required secrets (see .env.example).
from .security import validate_startup_env, require_admin  # noqa: E402

validate_startup_env()

from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from .command_center import command_center_json  # noqa: E402
from .command_center import router as command_center_router  # noqa: E402
from .routes import admin_ai, content, dashboard, qr_routes  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
ENABLE_DOCS = os.getenv("VP_ENABLE_DOCS", "false").lower() == "true"

app = FastAPI(
    title="VibePilot Backend",
    version="0.1.0",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)

# CORS: explicit allow-list only (comma-separated CORS_ORIGINS).
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

# Serve static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Include routers
app.include_router(qr_routes.router)
app.include_router(admin_ai.router)
app.include_router(command_center_router)
app.include_router(content.router, prefix="/api/v1")
app.include_router(dashboard.router)


# Root route (fallback to command center)
@app.get("/")
async def root():
    return HTMLResponse("<meta http-equiv=\"refresh\" content=\"0; url=/command-center\" />")


# Command center HTML (admin only)
@app.get("/command-center", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def command_center_html(request: Request):
    from .database import SessionLocal

    db = SessionLocal()
    try:
        data = await command_center_json(db=db)
    finally:
        db.close()
    return templates.TemplateResponse(request, "command_center.html", {"request": request, **data})


# Command center JSON feed (for HTMX auto-refresh, admin only)
@app.get("/command-center-json", dependencies=[Depends(require_admin)])
async def json_feed():
    from .database import SessionLocal

    db = SessionLocal()
    try:
        return await command_center_json(db=db)
    finally:
        db.close()


# Health check
@app.get("/health")
async def health():
    return {"status": "OK", "message": "VibePilot Backend is alive"}
