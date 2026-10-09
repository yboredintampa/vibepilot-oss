import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.update({
    # Points at a closed port: DB-backed endpoints degrade gracefully in tests.
    "DATABASE_URL": "postgresql://test:test@127.0.0.1:1/test",
    "QR_SIGNING_SECRET": secrets.token_hex(24),
    "VP_BACKEND_ADMIN_TOKEN": secrets.token_hex(24),
    "VP_ADMIN_USER": "test-admin",
    "VP_ADMIN_PASS": secrets.token_hex(12),
    "VP_ANALYTICS_PATH": f"/tmp/vp-backend-tests-{os.getpid()}.json",
})
