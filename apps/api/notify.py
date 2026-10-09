import os, json, requests

def tg_send(msg: str):
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=15,
        )
    except Exception:
        pass
