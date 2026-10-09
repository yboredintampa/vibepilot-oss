import os, psycopg2

# load .env so we get DATABASE_URL
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

url = os.getenv("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL not set. Put it in .env or export it before running.")

with psycopg2.connect(url) as conn:
    with conn.cursor() as cur:
        # 1. make sure pgcrypto exists
        cur.execute("create extension if not exists pgcrypto;")

        # 2. make sure tenants table exists with at least the columns we know you have
        # We'll create a minimal compatible shape if it somehow doesn't exist.
        # (If it already exists, this whole CREATE TABLE ... will just fail harmlessly in the DO block.)
        cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name='tenants'
            ) THEN
                CREATE TABLE tenants(
                    id uuid primary key default gen_random_uuid(),
                    slug text unique not null,
                    name text not null,
                    plan text default 'free',
                    created_at timestamptz not null default now()
                );
            END IF;
        END$$;
        """)

        # 3. Upsert / fix the 'admin' tenant row.
        # We provide slug, name, plan so 'name' won't be NULL.
        cur.execute("""
        INSERT INTO tenants(slug, name, plan)
        VALUES ('admin', 'Admin Tenant', 'free')
        ON CONFLICT (slug) DO UPDATE
        SET
            name = EXCLUDED.name,
            plan = EXCLUDED.plan;
        """)

        # 4. Get that tenant's UUID
        cur.execute("SELECT id FROM tenants WHERE slug = 'admin';")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Could not get admin tenant id after upsert")
        admin_tenant_id = row[0]  # uuid

        # 5. Ensure users.tenant_id column exists and is uuid
        cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='users'
                  AND column_name='tenant_id'
            ) THEN
                ALTER TABLE users
                ADD COLUMN tenant_id uuid;
            END IF;
        END$$;
        """)

        # 6. Backfill any NULL tenant_id in users
        cur.execute(
            """
            UPDATE users
            SET tenant_id = %s
            WHERE tenant_id IS NULL;
            """,
            (admin_tenant_id,)
        )

        # 7. Set default for tenant_id to that UUID
        cur.execute(f"""
        ALTER TABLE users
        ALTER COLUMN tenant_id SET DEFAULT '{admin_tenant_id}';
        """)

        # 8. Make tenant_id NOT NULL
        cur.execute("""
        ALTER TABLE users
        ALTER COLUMN tenant_id SET NOT NULL;
        """)

        conn.commit()

print("tenant_id patch done. admin tenant =", admin_tenant_id)
