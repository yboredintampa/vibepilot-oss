# content.py
import os
import uuid
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_user  # gives us { user_id, tenant_id, email_sha256 }

router = APIRouter(prefix="/content", tags=["content"])


# --- DB helpers ------------------------------------------------------------

def get_db_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(url)


def ensure_content_posts_schema(cur):
    """
    Make sure content_posts exists and has:
      id uuid pk
      tenant_id uuid
      body_text text
      created_at timestamptz default now()

    We run this before insert/select so Neon can't be 'surprised'.
    """

    # 1. create table if missing
    cur.execute(
        """
        create table if not exists content_posts(
            id uuid primary key default gen_random_uuid(),
            tenant_id uuid not null,
            body_text text,
            created_at timestamptz not null default now()
        );
        """
    )

    # 2. check columns
    cur.execute(
        """
        select column_name, data_type
        from information_schema.columns
        where table_name = 'content_posts';
        """
    )

    # RealDictCursor returns dict rows, so build a set of column names safely
    rows = cur.fetchall()
    existing_cols = {r["column_name"] for r in rows}

    # 3. add missing columns if needed
    if "body_text" not in existing_cols:
        cur.execute("alter table content_posts add column body_text text;")

    if "created_at" not in existing_cols:
        cur.execute(
            "alter table content_posts add column created_at timestamptz not null default now();"
        )


def fetch_brand_profile(cur, tenant_id: str):
    """
    Return the brand profile row for this tenant_id, or None.
    We ONLY select columns we know are actually in your DB (no created_at),
    because earlier we saw your DB does not have brand_profiles.created_at.
    """
    cur.execute(
        """
        select
            id,
            tenant_id,
            business_name,
            city,
            state,
            industry,
            voice,
            updated_at
        from brand_profiles
        where tenant_id = %s
        order by updated_at desc
        limit 1;
        """,
        (tenant_id,),
    )
    row = cur.fetchone()
    return row


def generate_marketing_blurb(brand_row: dict) -> str:
    """
    First-pass marketing copy generator.
    We'll upgrade this later with actual model calls.
    """
    biz = brand_row.get("business_name") or "our team"
    city = brand_row.get("city") or "your area"
    state = brand_row.get("state") or ""
    voice = brand_row.get("voice") or "friendly_pro"
    industry = brand_row.get("industry") or "local service"

    # voice preset
    if voice == "friendly_pro":
        opener = f"Hey {city}{(', ' + state) if state else ''}! 👋"
        tone = (
            "We're the pros you call when you want it done right but still treated like a neighbor."
        )
        cta = "Message us today for fast, friendly service you can feel good about."
    else:
        opener = f"Attention {city}{(', ' + state) if state else ''}:"
        tone = "Quality service. Honest pricing. Zero hassle."
        cta = "Get your free quote today."

    # industry preset
    if industry == "pool_service":
        problem = "Crystal clear, healthy water without the headache."
        proof = "Weekly cleaning, balancing, and checkups so you can just enjoy the pool."
    else:
        problem = "Done right the first time — no stress, no drama."
        proof = "We show up when we say we will and we leave it looking better than we found it."

    blurb = (
        f"{opener}\n\n"
        f"{biz} keeps your pool sparkling all week long. {problem}\n\n"
        f"{proof}\n\n"
        f"{tone}\n\n"
        f"{cta}"
    )

    return blurb


class PublishBody(BaseModel):
    text: str | None = Field(None, max_length=5000)


# --- Routes ------------------------------------------------------------

@router.post("/preview")
def preview_content(user=Depends(require_user)):
    """
    Generate a marketing post preview for this tenant.
    Does NOT save to DB.
    """
    tenant_id = user["tenant_id"]

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                brand = fetch_brand_profile(cur, tenant_id)
                if not brand:
                    raise HTTPException(
                        status_code=400,
                        detail="No brand profile set for this tenant. Hit /brand/setup first.",
                    )

                text = generate_marketing_blurb(brand)

        return {
            "ok": True,
            "preview": {
                "tenant_id": tenant_id,
                "text": text,
                "generated_at": datetime.utcnow().isoformat() + "Z",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="preview failed")
    finally:
        conn.close()


@router.post("/publish")
def publish_content(
    body: PublishBody = PublishBody(),
    user=Depends(require_user),
):
    """
    Take final post text (or auto-generate it), then save it to content_posts.
    Returns the inserted row.
    """
    tenant_id = user["tenant_id"]

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # make sure table is shaped sanely
                ensure_content_posts_schema(cur)

                final_text = body.text
                if not final_text:
                    brand = fetch_brand_profile(cur, tenant_id)
                    if not brand:
                        raise HTTPException(
                            status_code=400,
                            detail="No brand profile set for this tenant. Hit /brand/setup first.",
                        )
                    final_text = generate_marketing_blurb(brand)

                post_id = str(uuid.uuid4())

                cur.execute(
                    """
                    insert into content_posts (id, tenant_id, body_text)
                    values (%s, %s, %s)
                    returning id, tenant_id, body_text, created_at;
                    """,
                    (post_id, tenant_id, final_text),
                )
                row = cur.fetchone()

        return {"ok": True, "published": row}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="publish failed")
    finally:
        conn.close()


@router.get("/history")
def history(user=Depends(require_user)):
    """
    Return recent published posts for this tenant.
    """
    tenant_id = user["tenant_id"]

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                ensure_content_posts_schema(cur)

                cur.execute(
                    """
                    select id, tenant_id, body_text, created_at
                    from content_posts
                    where tenant_id = %s
                    order by created_at desc
                    limit 20;
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()

        return {"ok": True, "history": rows}

    except Exception as e:
        raise HTTPException(status_code=500, detail="history failed")
    finally:
        conn.close()
