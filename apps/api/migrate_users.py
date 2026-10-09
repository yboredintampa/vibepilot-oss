import os, psycopg2

# load .env if present so we can reuse DATABASE_URL
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

url = os.getenv("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL not set. Put it in .env or export it before running.")

sql = """
create extension if not exists pgcrypto;

create table if not exists users(
  id uuid primary key default gen_random_uuid()
);

alter table users add column if not exists email_sha256 text unique;
alter table users add column if not exists wallet_pubkey text unique;
alter table users add column if not exists last_login_at timestamptz default now();

create table if not exists login_tokens(
  id uuid primary key default gen_random_uuid(),
  email_sha256 text not null,
  jti uuid not null unique,
  created_at timestamptz not null default now(),
  used_at timestamptz
);
create index if not exists idx_login_tokens_email on login_tokens(email_sha256);

do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_name='users' and column_name='email'
  ) then
    update users
      set email_sha256 = encode(digest(lower(trim(email)),'sha256'),'hex')
    where email_sha256 is null and email is not null;
  end if;
end$$;
"""

with psycopg2.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()

print("Migration done.")
