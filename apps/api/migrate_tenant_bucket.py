import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

url = os.getenv("DATABASE_URL")
sql = """
alter table tenants
  add column if not exists asset_bucket text;
"""

with psycopg2.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()

print("tenants.asset_bucket added (if missing)")
