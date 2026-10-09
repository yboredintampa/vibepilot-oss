import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

url = os.getenv("DATABASE_URL")
sql = """
alter table content_posts
  add column if not exists published_at timestamptz default now();
"""

with psycopg2.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()

print("content_posts.published_at added (if missing)")
