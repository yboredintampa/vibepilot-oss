import os, psycopg2
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("DATABASE_URL")
if not url:
    raise SystemExit("no DATABASE_URL in env")

sql = """
create table if not exists brands (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null unique references tenants(id) on delete cascade,
    business_name text not null,
    city text,
    state text,
    industry text,
    voice text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- keep updated_at fresh on UPDATE
create or replace function touch_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_touch_brands on brands;
create trigger trg_touch_brands
before update on brands
for each row execute function touch_updated_at();
"""

with psycopg2.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()

print("brands table ready.")
