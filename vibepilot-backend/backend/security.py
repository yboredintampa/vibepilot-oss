# backend/security.py
"""Security helpers for the VibePilot backend.

* Required secrets are read from the environment and validated at startup
  (the app refuses to start if they are missing or obviously insecure).
* Admin endpoints require either ``Authorization: Bearer <VP_BACKEND_ADMIN_TOKEN>``
  or HTTP Basic credentials matching ``VP_ADMIN_USER`` / ``VP_ADMIN_PASS``.
* A tiny in-memory rate limiter protects public endpoints. It is per-process;
  use a shared store (e.g. Redis) if you run multiple workers.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request, status

INSECURE_VALUES = {
    "", "changeme", "change-me", "change_me", "password", "admin", "secret",
    "test", "dev", "replace-me",
}

# SHA-256 digests of placeholder/dev secrets that were used in earlier
# versions of this project. Stored hashed so the old values never appear in
# the source tree; any value matching one of these is rejected.
KNOWN_LEAKED_SECRET_SHA256 = {
    "376912d192756c41838ba598bd38fd2d7b611c7e1afd0143478e3ccda2792982",
    "5733dcb8b9e6095b751888b6a6e1f11da6163105811a8e7820973f92c691b888",
    "4da3376323046a3bb6759f0a3f4ae7100a0567950c53ee42d2e19201baaa6dfc",
    "6d98700b402977b07fb1164e08c28bce0379bcaf6d98c98f88edb5d8b689d227",
}


def _is_known_leaked(value: str) -> bool:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest() in KNOWN_LEAKED_SECRET_SHA256


SECRET_MIN_LENGTH = {
    "QR_SIGNING_SECRET": 32,
    "VP_BACKEND_ADMIN_TOKEN": 32,
    "VP_ADMIN_PASS": 12,
}


class ConfigError(RuntimeError):
    pass


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.lower() in INSECURE_VALUES or _is_known_leaked(value):
        raise ConfigError(f"Required environment variable {name} is not set (or uses an insecure placeholder).")
    min_len = SECRET_MIN_LENGTH.get(name)
    if min_len and len(value) < min_len:
        raise ConfigError(f"Environment variable {name} must be at least {min_len} characters.")
    return value


def validate_startup_env() -> None:
    """Fail closed if any required secret is missing."""
    missing = []
    for name in ("DATABASE_URL", "QR_SIGNING_SECRET", "VP_BACKEND_ADMIN_TOKEN", "VP_ADMIN_USER", "VP_ADMIN_PASS"):
        try:
            require_env(name)
        except ConfigError as exc:
            missing.append(str(exc))
    if missing:
        raise ConfigError("Refusing to start:\n  " + "\n  ".join(missing))


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_admin(request: Request) -> str:
    """FastAPI dependency: allow only authenticated administrators."""
    header = request.headers.get("authorization", "")
    scheme, _, credentials = header.partition(" ")
    scheme = scheme.lower()
    if scheme == "bearer" and credentials:
        if constant_time_equals(credentials.strip(), require_env("VP_BACKEND_ADMIN_TOKEN")):
            return "token"
    elif scheme == "basic" and credentials:
        try:
            decoded = base64.b64decode(credentials.strip()).decode("utf-8")
            user, _, password = decoded.partition(":")
        except Exception:
            user, password = "", ""
        user_ok = constant_time_equals(user, require_env("VP_ADMIN_USER"))
        pass_ok = constant_time_equals(password, require_env("VP_ADMIN_PASS"))
        if user_ok and pass_ok:
            return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": 'Basic realm="vibepilot-admin"'},
    )


def client_ip(request: Request) -> str:
    # Only trust X-Forwarded-For when explicitly running behind a trusted proxy.
    if os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def rate_limit(key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        bucket = _buckets[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests")
        bucket.append(now)


def public_base_url() -> str:
    """Public URL of this deployment (used in QR codes / emails)."""
    return os.getenv("VP_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
