import os
import psycopg2

# load .env so DATABASE_URL exists in this process
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

raw_url = os.getenv("DATABASE_URL")
if not raw_url:
    raise SystemExit("DATABASE_URL not set in environment or .env")

# psycopg2 is picky about scheme
if raw_url.startswith("postgres://"):
    url = "postgresql://" + raw_url[len("postgres://"):]
else:
    url = raw_url

sql = """
create extension if not exists pgcrypto;

create table if not exists content_posts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  created_at timestamptz not null default now(),
  channel text not null default 'facebook',

  headline text,
  body text,
  cta text,
  image_prompt text
);

create index if not exists idx_content_posts_tenant
  on content_posts(tenant_id);
"""

with psycopg2.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()

print("content_posts migration done.")
