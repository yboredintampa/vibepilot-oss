import os, ssl, pg8000, uuid
from urllib.parse import urlparse, unquote

dsn = os.environ["DATABASE_URL"]
u = urlparse(dsn)
conn = pg8000.connect(
    host=u.hostname, port=int(u.port or 5432), database=u.path[1:],
    user=unquote(u.username or ""), password=unquote(u.password or ""),
    ssl_context=ssl.create_default_context()
)

tenant_id = str(uuid.uuid4())
user_id   = str(uuid.uuid4())
agent_id  = str(uuid.uuid4())

with conn, conn.cursor() as cur:
    cur.execute("insert into tenants (id, slug, name, plan) values (%s,%s,%s,%s)",
                (tenant_id, 'demo', 'Demo Co', 'free'))
    cur.execute("insert into users (id, tenant_id, email, name, role) values (%s,%s,%s,%s,%s)",
                (user_id, tenant_id, 'founder@example.com', 'Demo Founder', 'admin'))
    cur.execute("insert into agents (id, tenant_id, name, system_prompt, model, active) values (%s,%s,%s,%s,%s,%s)",
                (agent_id, tenant_id, 'Default Agent', 'Be concise and helpful.', 'phi3', True))
print('Seeded tenant:', tenant_id)
