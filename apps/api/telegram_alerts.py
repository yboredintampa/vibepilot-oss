# -*- coding: utf-8 -*-
import requests, logging
from vp_helpers import env

BOT = env("TELEGRAM_BOT_TOKEN")
CHAT = env("TELEGRAM_CHAT_ID")
DRY = env("DRY_RUN","1",bool)

API = f"https://api.telegram.org/bot{BOT}/sendMessage" if BOT else None

def send_telegram(text: str, parse_mode: str | None = None):
    if not BOT or not CHAT:
        logging.warning("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
        return {"ok": False, "skipped": "no-token-or-chat"}
    if DRY:
        logging.info(f"[DRY_RUN][TG] {text[:140]}...")
        return {"ok": True, "dry_run": True}

    data = {
        "chat_id": CHAT,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        data["parse_mode"] = parse_mode

    r = requests.post(API, data=data, timeout=30)
    try:
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.warning(f"Telegram send failed: {e} | {r.text if hasattr(r,'text') else ''}")
        return {"ok": False, "error": str(e)}
