# auth.py
import os
import uuid
import hashlib
import time
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel
import jwt  # PyJWT

router = APIRouter(prefix="/auth", tags=["auth"])

from vp_security import require_env, rate_limit, client_ip

# Required; the app refuses to start without a strong secret (>= 32 chars).
JWT_SECRET = require_env("JWT_SECRET")
# Session cookies are Secure by default; set VP_COOKIE_SECURE=false only for local HTTP dev.
COOKIE_SECURE = os.getenv("VP_COOKIE_SECURE", "true").lower() != "false"
# Passwordless demo login is DISABLED unless explicitly enabled (never in production).
DEMO_LOGIN_ENABLED = os.getenv("VP_ENABLE_DEMO_LOGIN", "false").lower() == "true"
JWT_ALGO = "HS256"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def get_db_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(url)


class LoginDemoBody(BaseModel):
    email: str


def require_user(request: Request) -> dict:
    """
    Pull vp_session cookie, decode, return user context.
    Raises 401 if invalid.
    """
    token = request.cookies.get("vp_session")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")

    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")

    # basic sanity
    if "uid" not in claims or "tenant" not in claims:
        raise HTTPException(status_code=401, detail="Session missing required claims")

    return {
        "user_id": claims["uid"],
        "tenant_id": claims["tenant"],
        "email_sha256": claims.get("email_sha256"),
    }


@router.post("/login-demo")
def login_demo(body: LoginDemoBody, response: Response, request: Request):
    """
    Dev login:
    - takes an email
    - creates/looks up tenant "admin"
    - creates/looks up user with hashed email under that tenant
    - returns vp_session cookie
    """
    if not DEMO_LOGIN_ENABLED:
        # Hide the endpoint entirely when disabled.
        raise HTTPException(status_code=404, detail="Not Found")
    rate_limit(f"login-demo:{client_ip(request)}", 10, 15 * 60)

    email = (body.email or "").strip().lower()
    if not email or len(email) > 254 or "@" not in email:
        raise HTTPException(status_code=400, detail="email required")

    # hash email -> stable ID we don't have to store raw email
    email_sha256 = hashlib.sha256(email.encode("utf-8")).hexdigest()

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. ensure tenants table exists
                cur.execute(
                    """
                    create table if not exists tenants(
                        id uuid primary key default gen_random_uuid(),
                        slug text unique not null,
                        name text not null,
                        created_at timestamptz not null default now()
                    );
                    """
                )

                # 2. upsert a single default tenant "admin"
                tenant_id = str(uuid.uuid4())
                cur.execute(
                    """
                    insert into tenants (id, slug, name)
                    values (%s, %s, %s)
                    on conflict (slug)
                    do update set
                        name = excluded.name
                    returning id;
                    """,
                    (tenant_id, "admin", "Admin Tenant"),
                )
                row_tenant = cur.fetchone()
                tenant_id = row_tenant["id"]

                # 3. ensure users table exists
                cur.execute(
                    """
                    create table if not exists users(
                        id uuid primary key default gen_random_uuid(),
                        tenant_id uuid not null,
                        email text,
                        wallet_pubkey text,
                        role text,
                        created_at timestamptz not null default now(),
                        email_sha256 text unique,
                        last_login_at timestamptz default now()
                    );
                    """
                )

                # 4. upsert user under that tenant by email hash
                user_id = str(uuid.uuid4())
                cur.execute(
                    """
                    insert into users (
                        id, tenant_id, email, role, email_sha256, last_login_at
                    )
                    values (%s, %s, %s, %s, %s, now())
                    on conflict (email_sha256)
                    do update set
                        tenant_id = excluded.tenant_id,
                        email     = excluded.email,
                        role      = excluded.role,
                        last_login_at = now()
                    returning id;
                    """,
                    (user_id, tenant_id, email, "admin", email_sha256),
                )
                row_user = cur.fetchone()
                user_id = row_user["id"]

        # 5. issue JWT session cookie
        now_ts = int(time.time())
        exp_ts = now_ts + SESSION_TTL_SECONDS
        claims = {
            "sub": "user",
            "uid": user_id,
            "tenant": tenant_id,
            "email_sha256": email_sha256,
            "iat": now_ts,
            "exp": exp_ts,
        }
        token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGO)

        # set cookie
        response.set_cookie(
            key="vp_session",
            value=token,
            httponly=True,
            samesite="Lax",
            secure=COOKIE_SECURE,
            max_age=SESSION_TTL_SECONDS,
        )

        return {
            "ok": True,
            "email_sha256": email_sha256,
            "user_id": user_id,
            "tenant_id": tenant_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="login_demo failed") from e
    finally:
        conn.close()


@router.get("/whoami")
def whoami(user=Depends(require_user)):
    return {"ok": True, "claims": user}
