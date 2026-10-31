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

## Protection against prompt injection

Text from outside (customer profiles, weather, photo descriptions, deleted posts)
can try to trick the language model. `apps/api/llm_safety.py` (copied to
`vibepilot-backend/backend/llm_safety.py`) enforces these rules in code, not by
asking the model nicely:

- Secrets (API keys, tokens, passwords from the environment) are never put in
  prompts; a prompt that contains one is refused.
- Outside content is wrapped in `<untrusted_content>` blocks with hidden text
  removed, and the system prompt says it is data, not instructions.
- Model output is cleaned before it is stored or posted: images and links to
  domains not in `VP_OUTPUT_LINK_ALLOWLIST` are removed, HTML and scripts are
  neutralised, and output that leaks a secret or part of the system prompt is
  discarded.
- Only an allowlist of tasks, tones, trades and categories is permitted.
- Posting to Facebook needs an approved post (or `VP_ALLOW_DIRECT_POST=true`).

See [DEPLOYMENT.md](DEPLOYMENT.md) for secure deployment instructions.
