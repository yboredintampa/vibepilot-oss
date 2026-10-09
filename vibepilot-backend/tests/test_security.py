import base64
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def admin():
    return {"Authorization": f"Bearer {os.environ['VP_BACKEND_ADMIN_TOKEN']}"}


def test_refuses_to_start_without_secrets():
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")}
    r = subprocess.run([sys.executable, "-c", "import backend.main"], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "Refusing to start" in r.stderr


@pytest.mark.parametrize("method,path", [
    ("get", "/admin/ai-learning-data"),
    ("get", "/admin/learning-stats"),
    ("get", "/dashboard/"),
    ("get", "/dashboard/settings"),
    ("post", "/api/v1/content/generate"),
    ("get", "/command-center"),
    ("get", "/command-center/json"),
    ("get", "/command-center-json"),
    ("get", "/qr/generate/u1"),
    ("get", "/qr/printable/u1"),
    ("get", "/qr/stats/u1"),
    ("get", "/qr/sticker-sheet/u1"),
    ("get", "/qr/customer-reputation?email=a@example.com"),
    ("post", "/qr/rate-customer"),
    ("get", "/qr/customer-aggregate/a@example.com"),
])
def test_admin_endpoints_require_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_bearer_and_basic_auth(client, admin):
    assert client.get("/admin/ai-learning-data", headers=admin).status_code == 200
    basic = base64.b64encode(f"test-admin:{os.environ['VP_ADMIN_PASS']}".encode()).decode()
    assert client.get("/dashboard/", headers={"Authorization": f"Basic {basic}"}).status_code == 200
    wrong = base64.b64encode(b"test-admin:wrong").decode()
    assert client.get("/dashboard/", headers={"Authorization": f"Basic {wrong}"}).status_code == 401


def test_qr_token_signing_and_tamper_detection(client, admin):
    data = client.get("/qr/generate/u1", headers=admin).json()
    token = data["token"]
    assert client.get(f"/qr/review/{token}").status_code == 200
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert client.post("/qr/submit-review", json={"token": tampered, "rating": 5}).status_code == 400
    assert client.post("/qr/submit-review", json={"token": token, "rating": 9}).status_code == 422
    assert client.post("/qr/submit-review", json={"token": token, "rating": 5}).status_code == 200


def test_invalid_ids_rejected(client, admin):
    assert client.get("/qr/generate/<script>", headers=admin).status_code == 400


def test_public_endpoints(client):
    assert client.get("/health").status_code == 200
    assert client.get("/qr/showcase/u1").status_code == 200
    assert client.get("/docs").status_code == 404
