import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_DIR = Path(__file__).resolve().parents[1]


def _import_main_with_env(env):
    base = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")}
    base.update(env)
    return subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=API_DIR, env=base, capture_output=True, text=True,
    )


def test_refuses_to_start_without_secrets():
    r = _import_main_with_env({})
    assert r.returncode != 0
    assert "Refusing to start" in r.stderr


def test_refuses_to_start_with_weak_secrets():
    r = _import_main_with_env({
        "VP_ADMIN_USER": "admin",
        "VP_ADMIN_PASS": "password",
        "VP_INTERNAL_API_TOKEN": "short",
        "JWT_SECRET": "changeme",
        "DB_PASSWORD": "x",
    })
    assert r.returncode != 0
    assert "Refusing to start" in r.stderr


@pytest.fixture(scope="module")
def client():
    import main
    return TestClient(main.app, base_url="https://testserver")


@pytest.mark.parametrize("method,path", [
    ("get", "/scheduler/queue_preview"),
    ("post", "/scheduler/force_run"),
    ("post", "/scheduler/post_next_approved"),
    ("get", "/admin/command"),
    ("get", "/command-center"),
    ("get", "/command-center/json"),
    ("get", "/admin/queue/all"),
    ("get", "/admin/scheduler/config"),
])
def test_admin_endpoints_require_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_docs_disabled_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_internal_token_grants_access(client):
    h = {"Authorization": f"Bearer {os.environ['VP_INTERNAL_API_TOKEN']}"}
    assert client.get("/scheduler/queue_preview", headers=h).status_code == 200
    assert client.get("/scheduler/queue_preview", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_admin_login_session_and_logout(client):
    r = client.post("/admin/login", data={"username": "test-admin", "password": "nope"}, follow_redirects=False)
    assert r.status_code == 401
    r = client.post(
        "/admin/login",
        data={"username": "test-admin", "password": os.environ["VP_ADMIN_PASS"]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert client.get("/admin/queue/all").status_code == 200
    client.get("/admin/logout")
    assert client.get("/admin/queue/all").status_code == 401


def test_vp_security_rejects_known_leaked_values():
    import hashlib
    import vp_security

    assert vp_security._check("X", "a" * 40, 32) is None
    assert vp_security._check("X", "changeme", 1) is not None
    # Every stored digest must be rejected when its preimage is supplied.
    assert all(len(h) == 64 for h in vp_security.KNOWN_LEAKED_SECRET_SHA256)
    sample = "not-a-leaked-value-" + "x" * 20
    assert hashlib.sha256(sample.encode()).hexdigest() not in vp_security.KNOWN_LEAKED_SECRET_SHA256
