import os, sys, re
import psycopg2

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL not set"); sys.exit(1)

path = sys.argv[1] if len(sys.argv) > 1 else "schema.sql"
with open(path, "r", encoding="utf-8") as f:
    sql = f.read()

# Remove UTF-8 BOM if present and strip single-line comments
sql = sql.lstrip("\ufeff")
lines = []
for line in sql.splitlines():
    # keep lines that aren't pure -- comments
    if re.match(r"^\s*--", line): 
        continue
    lines.append(line)
sql = "\n".join(lines)

with psycopg2.connect(db_url) as conn:
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("create extension if not exists pgcrypto;")
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt + ";")
print("Schema applied.")
