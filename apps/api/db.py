from __future__ import annotations

import os
from typing import Optional
from contextlib import asynccontextmanager

import psycopg_pool

_pool: Optional[psycopg_pool.AsyncConnectionPool] = None


def _build_dsn_from_parts() -> Optional[str]:
    """
    Build a PostgreSQL DSN from individual DB_* env vars if present.
    """
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([host, name, user, password]):
        return None

    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def _dsn() -> str:
    """
    Resolve the database connection string in a flexible way:

    1. DB_URL (preferred, if set)
    2. DATABASE_URL
    3. Built from DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD

    This way you don't have to keep changing your .env layout.
    """
    # 1) Prefer DB_URL
    db_url = os.getenv("DB_URL")
    if db_url:
        print("[db] Using DB_URL from environment")
        return db_url

    # 2) Fall back to DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        print("[db] Using DATABASE_URL from environment")
        return database_url

    # 3) Build from DB_* parts
    dsn_from_parts = _build_dsn_from_parts()
    if dsn_from_parts:
        print("[db] Using DSN built from DB_HOST/DB_NAME/DB_USER/DB_PASSWORD")
        return dsn_from_parts

    # If we get here, nothing usable was found
    raise RuntimeError(
        "No database configuration found. "
        "Set DB_URL, or DATABASE_URL, or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD."
    )


async def init_pool(min_size: int = 1, max_size: int = 10) -> None:
    """
    Initialize the global async connection pool if it doesn't exist yet.
    """
    global _pool
    if _pool is None:
        conninfo = _dsn()
        print(f"[db] Initializing async connection pool to: {conninfo}")
        _pool = psycopg_pool.AsyncConnectionPool(
            conninfo=conninfo,
            min_size=min_size,
            max_size=max_size,
            open=True,
            timeout=10,
        )


async def close_pool() -> None:
    """
    Close the global connection pool (used on graceful shutdown).
    """
    global _pool
    if _pool is not None:
        print("[db] Closing async connection pool")
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn():
    """
    Async context manager yielding a raw connection from the pool.
    """
    if _pool is None:
        raise RuntimeError("DB pool not initialized; call init_pool() first")

    async with _pool.connection() as conn:
        yield conn


@asynccontextmanager
async def get_cursor():
    """
    Async context manager yielding a cursor from the pool.
    """
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            yield cur
