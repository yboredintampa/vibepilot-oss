#!/usr/bin/env python
"""
Initialize VibePilot database:

- Resolve DB URL from env (DATABASE_URL or DB_URL or DB_* pieces)
- Wait for Postgres to be reachable
- Create core tables if they do not exist:
    - tenants
    - posting_schedules
    - facebook_integrations
"""

import os
import socket
import time
from typing import Tuple

from sqlalchemy import create_engine, text


def _log(msg: str) -> None:
    print(f"[init_db] {msg}", flush=True)


def get_db_config() -> Tuple[str, str, int]:
    """
    Returns (db_url, host, port)

    Priority:
      1. DATABASE_URL
      2. DB_URL
      3. Build from DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
    """
    # Try explicit URLs first
    db_url = os.getenv("DATABASE_URL") or os.getenv("DB_URL")

    host = os.getenv("DB_HOST", "vp-postgres")
    port_str = os.getenv("DB_PORT", "5432")
    try:
        port = int(port_str)
    except ValueError:
        port = 5432

    if not db_url:
        name = os.getenv("DB_NAME", "vibepilot")
        user = os.getenv("DB_USER", "vibepilot")
        password = os.getenv("DB_PASSWORD", "")

        if not password:
            raise RuntimeError(
                "No DATABASE_URL/DB_URL and DB_PASSWORD is empty. "
                "Set either DATABASE_URL or DB_* env vars."
            )

        db_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"

    return db_url, host, port


def wait_for_db(host: str, port: int, attempts: int = 20, delay: float = 1.0) -> None:
    """
    Simple TCP wait loop so we don't race Postgres startup.
    """
    _log(f"Waiting for database at {host}:{port} ...")
    for attempt in range(1, attempts + 1):
        _log(f"Attempt {attempt}/{attempts}: opening socket...")
        try:
            with socket.create_connection((host, port), timeout=2):
                _log("Database TCP connection successful ✅")
                return
        except OSError:
            time.sleep(delay)

    raise RuntimeError(f"Could not connect to database at {host}:{port} after {attempts} attempts")


def create_core_tables(db_url: str) -> None:
    """
    Create the core VibePilot tables if they don't already exist.
    Uses SQLAlchemy only for connection management + executing raw SQL.
    """
    _log("Connecting with SQLAlchemy engine to create tables...")
    engine = create_engine(db_url, future=True)

    tenants_sql = """
    CREATE TABLE IF NOT EXISTS tenants (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        contact_email TEXT,
        timezone TEXT NOT NULL DEFAULT 'America/New_York',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_active BOOLEAN NOT NULL DEFAULT TRUE
    );
    """

    posting_schedules_sql = """
    CREATE TABLE IF NOT EXISTS posting_schedules (
        id BIGSERIAL PRIMARY KEY,
        tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        platform TEXT NOT NULL DEFAULT 'facebook',
        timezone TEXT NOT NULL DEFAULT 'America/New_York',
        config JSONB NOT NULL DEFAULT '{}'::jsonb,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    facebook_integrations_sql = """
    CREATE TABLE IF NOT EXISTS facebook_integrations (
        id BIGSERIAL PRIMARY KEY,
        tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        page_id TEXT NOT NULL,
        page_name TEXT,
        access_token TEXT NOT NULL,
        token_expires_at TIMESTAMPTZ,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    # Helpful partial unique indexes so we don't accidentally
    # create duplicate "active" records for the same tenant.
    indexes_sql = [
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_tenants_name_active
        ON tenants (LOWER(name))
        WHERE is_active;
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_posting_schedules_tenant_name_active
        ON posting_schedules (tenant_id, LOWER(name))
        WHERE is_active;
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_fb_integrations_tenant_page_active
        ON facebook_integrations (tenant_id, page_id)
        WHERE is_active;
        """
    ]

    with engine.begin() as conn:
        _log("Creating tenants table (if missing)...")
        conn.execute(text(tenants_sql))

        _log("Creating posting_schedules table (if missing)...")
        conn.execute(text(posting_schedules_sql))

        _log("Creating facebook_integrations table (if missing)...")
        conn.execute(text(facebook_integrations_sql))

        _log("Creating indexes (if missing)...")
        for stmt in indexes_sql:
            conn.execute(text(stmt))

    _log("Core tables + indexes are in place ✅")


def main() -> None:
    db_url, host, port = get_db_config()
    safe_url = db_url
    if "://" in safe_url and "@" in safe_url:
        # redact password in logs
        prefix, rest = safe_url.split("://", 1)
        if "@" in rest and ":" in rest.split("@", 1)[0]:
            creds, tail = rest.split("@", 1)
            user_part = creds.split(":", 1)[0]
            safe_url = f"{prefix}://{user_part}:*****@{tail}"

    _log(f"Using database config: {safe_url}")
    wait_for_db(host, port)
    create_core_tables(db_url)
    _log("Done. Database is ready for the app. ✅")


if __name__ == "__main__":
    main()
