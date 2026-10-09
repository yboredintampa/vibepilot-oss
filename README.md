# VibePilot

VibePilot is a self-hosted social-media autopilot for local service businesses.
It generates on-brand captions and images with AI, puts them in an approval
queue, and publishes approved posts to a Facebook Page on a schedule. A
companion service collects **cryptographically verified customer reviews** via
QR codes.

The repository ships with a fictional demo business, **Sunny Side Pool Co.**
(a pool-service company), and a pool-care training corpus in `content/`.
Swap in your own business via environment variables and training files.

## Features

- **AI content generation** – captions (LLM via Replicate) and companion images
  in several styles: realistic, educational, meme, persuasive, comedic, blog.
- **Approval queue & admin dashboard** – review, translate, approve, delete or
  post immediately from `/admin`.
- **Scheduler** – per-account posting times and category rotation
  (`apps/api/scheduler_config.json`), driven by cron.
- **Facebook publishing** via the Meta Graph API.
- **Blog generation** – long-form articles with a hero image.
- **Context-aware posts** – optional weather/season context (Open-Meteo).
- **Duplicate protection** – caption/prompt dedupe store.
- **Multi-tenant basics** – tenants, users, brand profiles, category weights.
- **Telegram notifications** and an optional Telegram command bot.
- **Verified reviews (vibepilot-backend)** – HMAC-signed QR tokens, review
  landing page, printable sticker sheets, analytics, CTA optimizer.

## Repository layout

| Path | What it is |
| --- | --- |
| `apps/api/` | Main FastAPI service (`main.py` is the production entrypoint; `api.py` is a lighter multi-tenant API) |
| `apps/static/` | Admin dashboard HTML served at `/admin` |
| `apps/api/web/`, `vibepilot-ui/` | React + Vite front-ends |
| `vibepilot-backend/` | QR verified-reviews service (FastAPI) |
| `packages/ui/` | Shared dashboard component |
| `content/` | Training/example captions for the demo business |
| `database/schema/` | PostgreSQL schema (auto-applied by the compose `db` service) |
| `bin/`, `scripts/`, `deploy/` | Host cron helpers, backup script, example crontab |
| `tenants/` | Per-tenant env examples (real `*.env` files are git-ignored) |

## Tech stack

Python 3.12 · FastAPI · Uvicorn · PostgreSQL 16 (psycopg / psycopg2) · PyJWT ·
Replicate · Meta Graph API · boto3 (Storj S3 gateway) · Pillow · qrcode ·
ReportLab · React 19 + Vite + TypeScript · Docker Compose.

## Quick start (Docker)

```bash
cp .env.example .env
# Fill in at least: VP_ADMIN_USER, VP_ADMIN_PASS, VP_INTERNAL_API_TOKEN,
# JWT_SECRET, DB_PASSWORD, DATABASE_URL (or DB_*), REPLICATE_API_TOKEN.
# Generate secrets with: openssl rand -hex 32
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

Open `http://127.0.0.1:8000/admin` and sign in with `VP_ADMIN_USER` /
`VP_ADMIN_PASS`. For local HTTP (no TLS) set `VP_COOKIE_SECURE=false`.

## Local development

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r apps/api/requirements.txt
cp .env.example .env   # and fill it in
cd apps/api && uvicorn main:app --reload

# Tests
pip install pytest httpx
(cd apps/api && pytest tests)
pip install -r vibepilot-backend/requirements.txt
(cd vibepilot-backend && pytest tests)

# Front-ends
(cd vibepilot-ui && npm install && npm run build)
(cd apps/api/web && npm install && npm run build)
```

The QR reviews service runs separately:

```bash
cd vibepilot-backend
uvicorn backend.main:app --port 8001
```

## Configuration

Every setting is an environment variable documented in
[`.env.example`](.env.example). There are **no built-in default secrets**:
both services refuse to start if a required secret is missing, too short, or
a known placeholder.

## Security notes

- All admin, scheduler, command-center, dashboard, analytics and AI-training
  endpoints require authentication (admin session cookie, or
  `Authorization: Bearer $VP_INTERNAL_API_TOKEN` for cron/scripts; the
  reviews service uses `VP_BACKEND_ADMIN_TOKEN` or HTTP Basic admin creds).
- API docs (`/docs`, `/openapi.json`) are disabled unless `VP_ENABLE_DOCS=true`.
- The demo login endpoint is disabled unless `VP_ENABLE_DEMO_LOGIN=true`.
- Login and public review endpoints are rate-limited (in-memory, per process).
- QR review tokens are signed with HMAC-SHA256 using `QR_SIGNING_SECRET`.
- Keep your Storj/S3 bucket **private**; never commit `.env` files.

See [SECURITY.md](SECURITY.md) and [DEPLOYMENT.md](DEPLOYMENT.md).

## Contributing

Issues and pull requests are welcome.

1. Fork the repo and create a feature branch.
2. Keep secrets out of commits (`.env` is git-ignored; use `.env.example`).
3. Run the Python tests and front-end builds before opening a PR.
4. Describe the change and how you tested it.

Please report security issues privately — see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Todd Bullock
