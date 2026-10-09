# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability):
open the repository's **Security** tab and click **Report a vulnerability**.

Please include:

- a description of the issue and its impact,
- steps to reproduce (proof-of-concept if possible),
- affected component (`apps/api`, `vibepilot-backend`, front-end, scripts).

We aim to acknowledge reports within a few days and will coordinate a fix and
disclosure timeline with you. Please give us a reasonable time to fix the issue
before any public disclosure.

## Supported versions

Only the latest commit on the default branch is supported with security fixes.

## Operator guidance

- Never commit `.env` files, API keys, tokens or database passwords. Copy
  `.env.example` to `.env` and fill in your own values.
- Generate secrets with `openssl rand -hex 32`. The services refuse to start
  with missing, short, or placeholder secrets.
- Do not commit generated content (`generated_images/`, `post_queue/`), logs, or
  any customer data/PII. Anonymize data in bug reports.
- Keep object-storage buckets private and rotate API keys regularly.
- Run behind a TLS-terminating reverse proxy; keep `VP_COOKIE_SECURE=true`.

See [DEPLOYMENT.md](DEPLOYMENT.md) for secure deployment instructions.
