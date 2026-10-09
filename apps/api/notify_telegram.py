import os
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
BOT = os.getenv("TELEGRAM_ALERTS_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_ALERTS_CHAT_ID")

def _enabled() -> bool:
    return bool(BOT and CHAT)

def send_telegram_text(text: str):
    if not _enabled(): 
        return
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    # Keep under Telegram caption length
    text = text.strip()
    try:
        requests.post(url, data={"chat_id": CHAT, "text": text, "disable_web_page_preview": True}, timeout=20)
    except Exception:
        pass

def send_telegram_post_preview(image_path: str, caption: str, permalink_url: Optional[str] = None):
    if not _enabled(): 
        return
    url = f"https://api.telegram.org/bot{BOT}/sendPhoto"
    cap = caption.strip()
    if permalink_url:
        cap = (cap + "\n\n" + permalink_url).strip()
    if len(cap) > 1024:
        cap = cap[:1000].rstrip() + "…"

    p = Path(image_path)
    files = None
    data = {"chat_id": CHAT, "caption": cap}
    try:
        if p.exists():
            files = {"photo": (p.name, open(p, "rb"), "image/jpeg")}
            requests.post(url, data=data, files=files, timeout=30)
        else:
            # fallback text if photo missing
            send_telegram_text(f"{caption}\n\n{permalink_url or ''}".strip())
    except Exception:
        pass
    finally:
        if files and hasattr(files["photo"][1], "close"):
            try:
                files["photo"][1].close()
            except Exception:
                pass

