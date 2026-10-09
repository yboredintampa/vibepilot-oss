# Deploying VibePilot

This guide covers a single-host Docker deployment. Adjust paths to your setup;
examples assume the repo is checked out at `/opt/vibepilot` and the env file
lives at `/etc/vibepilot/.env` (any location works via `VP_ENV_FILE`).

## 1. Prerequisites

- Linux host with Docker Engine + Docker Compose v2
- A domain name and a TLS-terminating reverse proxy (Caddy, nginx, Traefik)
- Accounts/keys for the integrations you use (Replicate, Meta Graph API,
  Storj S3 gateway, Telegram, SMTP)

## 2. Configure secrets

```bash
sudo mkdir -p /etc/vibepilot
sudo cp .env.example /etc/vibepilot/.env
sudo chmod 600 /etc/vibepilot/.env
sudoedit /etc/vibepilot/.env
```

Required (the API **refuses to start** without strong values):

| Variable | Notes |
| --- | --- |
| `VP_ADMIN_USER`, `VP_ADMIN_PASS` | Admin dashboard login (password ≥ 12 chars) |
| `VP_INTERNAL_API_TOKEN` | ≥ 32 chars; used by cron scripts as a Bearer token |
| `JWT_SECRET` | ≥ 32 chars; signs user sessions |
| `DB_PASSWORD` / `DATABASE_URL` | Database credentials (password ≥ 12 chars) |

For the reviews service (`vibepilot-backend`): `QR_SIGNING_SECRET` (≥ 32),
`VP_BACKEND_ADMIN_TOKEN` (≥ 32), `VP_ADMIN_USER`, `VP_ADMIN_PASS`,
`DATABASE_URL`, and `VP_PUBLIC_BASE_URL`.

Generate secrets with `openssl rand -hex 32`. Never reuse example values.

## 3. Start the stack

```bash
cd /opt/vibepilot
VP_ENV_FILE=/etc/vibepilot/.env docker compose --env-file /etc/vibepilot/.env up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8000/health
```

`compose.yml` binds the API to `127.0.0.1:8000` only. The `db` service applies
`database/schema/*.sql` on first start. Runtime data lives in `./data/`
(git-ignored).

## 4. Reverse proxy (TLS)

Example Caddyfile:

```
vibepilot.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Keep `VP_COOKIE_SECURE=true` in production so session cookies are only sent
over HTTPS. Only set `TRUST_PROXY_HEADERS=true` when the app is reachable
*exclusively* through your proxy.

## 5. Scheduled jobs

Install the example crontab (review paths first):

```bash
crontab deploy/crontab.example
```

Cron calls `/app/run_post.sh` inside the container, which authenticates to the
admin-only `/scheduler/force_run` endpoint with
`Authorization: Bearer $VP_INTERNAL_API_TOKEN` (already present in the
container's environment).

## 6. Reviews service (optional)

```bash
cd vibepilot-backend
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Expose only the public routes you need (`/qr/review/*`, `/qr/submit-review`,
`/qr/showcase/*`, `/health`) through your proxy; all other routes require
admin authentication. To let the main API learn from top-rated content, set
`VP_BACKEND_URL` and `VP_BACKEND_ADMIN_TOKEN` in the API's env.

## 7. Backups

`scripts/backup_to_storj.sh` dumps PostgreSQL and non-secret config to
`VP_BACKUP_BUCKET` with `s3cmd`. Env files are only included when
`VP_BACKUP_GPG_RECIPIENT` is set (they are GPG-encrypted first). The bucket
**must be private**.

## 8. Hardening checklist

- [ ] All required secrets set, unique, and stored only in the env file (mode 600)
- [ ] `VP_ENABLE_DOCS` and `VP_ENABLE_DEMO_LOGIN` unset/false
- [ ] API reachable only via the TLS reverse proxy
- [ ] `CORS_ORIGINS` limited to your front-end origins
- [ ] Storage buckets private; backups encrypted
- [ ] Firewall allows only 80/443 (and SSH) inbound
- [ ] Rotate tokens periodically and after any suspected exposure
- [ ] Rate limiting is in-memory per process — use a shared store (e.g. Redis)
      or proxy-level limits if you run multiple workers/instances
