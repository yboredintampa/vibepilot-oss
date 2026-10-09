import os, sys, ssl
from urllib.parse import urlparse, unquote
import pg8000

def parse_dsn(dsn: str):
    u = urlparse(dsn)
    return {
        "user":     unquote(u.username or ""),
        "password": unquote(u.password or ""),
        "host":     u.hostname or "localhost",
        "port":     int(u.port or 5432),
        "database": (u.path or "/")[1:]
    }

def read_sql_utf8_sig(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()

def execute_sql(conn, sql_text: str):
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt + ";")
    conn.commit()

def main():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    path = sys.argv[1] if len(sys.argv) > 1 else "schema.sql"
    sql_text = read_sql_utf8_sig(path)

    cfg = parse_dsn(dsn)
    ctx = ssl.create_default_context()
    conn = pg8000.connect(
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        ssl_context=ctx,
    )

    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        conn.commit()

        execute_sql(conn, sql_text)
        print("Schema applied.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
