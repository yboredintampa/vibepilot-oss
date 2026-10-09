import os, ssl, pg8000
from urllib.parse import urlparse, unquote

dsn = os.environ["DATABASE_URL"]
u = urlparse(dsn)
conn = pg8000.connect(
    host=u.hostname, port=int(u.port or 5432), database=u.path[1:],
    user=unquote(u.username or ""), password=unquote(u.password or ""),
    ssl_context=ssl.create_default_context()
)
with conn, conn.cursor() as cur:
    cur.execute("""
        select table_name
        from information_schema.tables
        where table_schema='public'
        order by table_name;
    """)
    print([r[0] for r in cur.fetchall()])
