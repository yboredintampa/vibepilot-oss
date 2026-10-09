"""Test configuration: strong throwaway secrets + temp dirs, set before import."""
import os
import secrets
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

_TMP = Path(os.environ.get("PYTEST_TMPDIR", "/tmp")) / f"vp-api-tests-{os.getpid()}"
for sub in ("q", "img", "logs"):
    (_TMP / sub).mkdir(parents=True, exist_ok=True)

TEST_ENV = {
    "VP_ADMIN_USER": "test-admin",
    "VP_ADMIN_PASS": secrets.token_hex(16),
    "VP_INTERNAL_API_TOKEN": secrets.token_hex(24),
    "JWT_SECRET": secrets.token_hex(24),
    "DB_PASSWORD": secrets.token_hex(16),
    "POST_QUEUE_DIR": str(_TMP / "q"),
    "GENERATED_IMAGES_DIR": str(_TMP / "img"),
    "VP_LOG_DIR": str(_TMP / "logs"),
    "VP_FORCE_RUN_STATE_PATH": str(_TMP / "force_run_state.json"),
    "SCHEDULER_CONFIG_PATH": str(API_DIR / "scheduler_config.json"),
    "VP_ADMIN_HTML_PATH": str(API_DIR.parent / "static" / "admin_dashboard.html"),
}
os.environ.update(TEST_ENV)
for name in ("VP_ENABLE_DOCS", "VP_ENABLE_DEMO_LOGIN", "DATABASE_URL", "DB_URL"):
    os.environ.pop(name, None)
