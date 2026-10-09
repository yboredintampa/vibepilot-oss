"""
Central security helpers for the VibePilot API.

* `require_env` / `validate_startup_env` make the service refuse to start
  when a required secret is missing, empty, too short, or a well-known
  placeholder. There are intentionally NO insecure fallbacks.
* `require_admin` is a FastAPI dependency that accepts either a valid admin
  session cookie (browser dashboard) or `Authorization: Bearer
  $VP_INTERNAL_API_TOKEN` (cron jobs / scripts / service-to-service).
* `rate_limit` is a tiny in-memory limiter for login and other
  abuse-prone endpoints (per process; use Redis for multi-instance setups).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, Request, status

# Values that must never be accepted as real secrets.
INSECURE_VALUES = {
    "",
    "admin",
    "password",
    "changeme",
    "change_me",
    "change-me",
    "secret",
    "dev",
    "test",
    "your-password",
    "vibepilot",
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


# name -> minimum length
SECRET_MIN_LENGTH: Dict[str, int] = {
    "JWT_SECRET": 32,
    "VP_ADMIN_PASS": 12,
    "VP_INTERNAL_API_TOKEN": 32,
    "DB_PASSWORD": 12,
    "POSTGRES_PASSWORD": 12,
}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or insecure."""


def _check(name: str, value: Optional[str], min_length: int) -> Optional[str]:
    if value is None or value.strip() == "":
        return f"{name} is not set"
    if value.strip().lower() in INSECURE_VALUES or _is_known_leaked(value):
        return f"{name} uses a known insecure placeholder value"
    if len(value) < min_length:
        return f"{name} must be at least {min_length} characters"
    return None


def require_env(name: str, min_length: Optional[int] = None) -> str:
    """Return the env var or raise ConfigError (never falls back to a default)."""
    value = os.getenv(name)
    problem = _check(name, value, min_length or SECRET_MIN_LENGTH.get(name, 1))
    if problem:
        raise ConfigError(problem + " (see .env.example)")
    return value  # type: ignore[return-value]


def validate_startup_env(names: Iterable[str]) -> None:
    """Validate several env vars at once and fail with a combined message."""
    problems: List[str] = []
    for name in names:
        problem = _check(name, os.getenv(name), SECRET_MIN_LENGTH.get(name, 1))
        if problem:
            problems.append(problem)
    if problems:
        raise ConfigError(
            "Refusing to start: insecure or missing configuration:\n  - "
            + "\n  - ".join(problems)
            + "\nSee .env.example and DEPLOYMENT.md."
        )


def database_password_present() -> None:
    """Require a DB password either directly or inside DATABASE_URL."""
    url = os.getenv("DATABASE_URL", "")
    if url:
        from urllib.parse import urlparse

        pw = urlparse(url).password or ""
        problem = _check("DATABASE_URL password", pw, SECRET_MIN_LENGTH["DB_PASSWORD"])
        if problem:
            raise ConfigError("Refusing to start: " + problem)
        return
    require_env("DB_PASSWORD")


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def is_internal_request(request: Request) -> bool:
    token = _bearer_token(request)
    expected = os.getenv("VP_INTERNAL_API_TOKEN") or ""
    return bool(token and expected and constant_time_equals(token, expected))


def require_admin(request: Request) -> bool:
    """FastAPI dependency: admin session cookie OR internal bearer token."""
    if is_internal_request(request):
        return True
    # Lazy import avoids a circular import with admin_dashboard.
    from admin_dashboard import SESSION_COOKIE_NAME, _validate_admin_session

    if _validate_admin_session(request.cookies.get(SESSION_COOKIE_NAME)):
        return True
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
_buckets: Dict[str, Tuple[int, float]] = {}
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        count, reset_at = _buckets.get(key, (0, now + window_seconds))
        if reset_at <= now:
            count, reset_at = 0, now + window_seconds
        count += 1
        _buckets[key] = (count, reset_at)
        if len(_buckets) > 10_000:
            for k, (_, r) in list(_buckets.items()):
                if r <= now:
                    _buckets.pop(k, None)
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests")
