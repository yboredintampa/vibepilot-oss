# brand.py
import os
import psycopg2
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

from auth import require_user  # <- our helper that reads vp_session and returns user info

router = APIRouter(prefix="/brand", tags=["brand"])


def get_db_conn():
    """
    Open a new DB connection using DATABASE_URL from env.
    Caller is responsible for closing.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in environment")
    return psycopg2.connect(url)


class BrandSetupRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=120)
    city: str = Field(..., max_length=80)
    state: str = Field(..., max_length=40)
    industry: str = Field(..., max_length=80)
    voice: str = Field(..., max_length=500)


@router.post("/setup")
def setup_brand(
    payload: BrandSetupRequest,
    user=Depends(require_user),
):
    """
    Create/update the brand profile for the current tenant.
    If a brand row for this tenant exists, update it.
    Otherwise insert it.
    """
    tenant_id = user["tenant_id"]

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # Make sure brand_profiles exists
                cur.execute(
                    """
                    create table if not exists brand_profiles(
                        id uuid primary key default gen_random_uuid(),
                        tenant_id uuid not null unique,
                        business_name text not null,
                        city text,
                        state text,
                        industry text,
                        voice text,
                        updated_at timestamptz not null default now()
                    );
                    """
                )

                # upsert the brand profile
                cur.execute(
                    """
                    insert into brand_profiles (
                        tenant_id, business_name, city, state, industry, voice
                    )
                    values (%s, %s, %s, %s, %s, %s)
                    on conflict (tenant_id)
                    do update set
                        business_name = excluded.business_name,
                        city = excluded.city,
                        state = excluded.state,
                        industry = excluded.industry,
                        voice = excluded.voice,
                        updated_at = now()
                    returning id, tenant_id, business_name, city, state, industry, voice, updated_at;
                    """,
                    (
                        tenant_id,
                        payload.business_name,
                        payload.city,
                        payload.state,
                        payload.industry,
                        payload.voice,
                    ),
                )
                row = cur.fetchone()

        return {
            "ok": True,
            "brand": {
                "id": row[0],
                "tenant_id": row[1],
                "business_name": row[2],
                "city": row[3],
                "state": row[4],
                "industry": row[5],
                "voice": row[6],
                "updated_at": row[7].isoformat() if isinstance(row[7], datetime) else row[7],
            },
        }
    finally:
        conn.close()


@router.get("/me")
def get_my_brand(user=Depends(require_user)):
    """
    Fetch the brand profile for the current tenant.
    """
    tenant_id = user["tenant_id"]

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, tenant_id, business_name, city, state, industry, voice, updated_at
                    from brand_profiles
                    where tenant_id = %s
                    """,
                    (tenant_id,),
                )
                row = cur.fetchone()

        if not row:
            return {"ok": True, "brand": None}

        return {
            "ok": True,
            "brand": {
                "id": row[0],
                "tenant_id": row[1],
                "business_name": row[2],
                "city": row[3],
                "state": row[4],
                "industry": row[5],
                "voice": row[6],
                "updated_at": row[7].isoformat() if isinstance(row[7], datetime) else row[7],
            },
        }
    finally:
        conn.close()
