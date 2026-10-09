# -*- coding: utf-8 -*-
import glob, os, re, pathlib
from datetime import datetime
from telegram_alerts import send_telegram

LOG_DIR = pathlib.Path("./logs")
def newest_log():
    files = sorted(LOG_DIR.glob("run_*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def extract(line, key):
    m = re.search(rf"{key}=([^\s<]+)", line or "")
    return m.group(1) if m else None

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    p = newest_log()
    if not p:
        send_telegram(f"🟡 Vibepilot health {now} — no logs yet.")
        return
    txt = p.read_text(encoding="utf-8", errors="ignore")
    ok = "OK:</b> True" in txt or "OK: True" in txt
    # Try to pull Reason line (works for both md/html we write)
    reason_line = ""
    for line in txt.splitlines():
        if "Reason:" in line:
            reason_line = line
            break
    fb_id = extract(reason_line, "fb_id")
    permalink = extract(reason_line, "permalink")
    status = "🟢 OK" if ok else "🔴 ISSUE"
    msg = f"{status} Vibepilot health {now}\nLast fb_id={fb_id or '-'}\n{permalink or ''}".strip()
    send_telegram(msg)

if __name__ == "__main__":
    main()
