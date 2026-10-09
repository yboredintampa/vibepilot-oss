VibePilot static site
=====================

Structure:
- index.html            -> public landing
- /app                  -> PWA shell
  - index.html          -> dashboard
  - calendar.html       -> simple calendar editor (talks to /calendar API)
  - styles.css          -> deep purple theme
  - app.js              -> PWA logic + API base setter
  - manifest.webmanifest
  - service-worker.js
  (add your own icons under /app/icons and reference them in manifest.webmanifest)

Usage:
1) Upload whole folder to Storj (see instructions below).
2) In /app (Dashboard), set API Base (e.g. https://<your-public-api>/).
3) Check API Health and use Calendar page to load/save.

Storj upload (uplink CLI):
  uplink mb sj://<your-site-bucket>
  uplink cp -r ./ sj://<your-site-bucket>/

Static hosting settings (bucket):
  - Index document: index.html
  - Error document: index.html

API (FastAPI minimal):
  See apps/api in this repository.
