#!/usr/bin/env python3
# telegram_dashboard_bot.py
from __future__ import annotations

import os
import asyncio
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest

# ---------- ENV ----------
HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env", override=True)

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
ALLOWED_USERS = {u.strip().lstrip("@") for u in (os.getenv("TELEGRAM_ALLOWED_USERNAMES") or "").split(",") if u.strip()}

PROJECT_DIR = Path(os.getenv("PROJECT_DIR", str(HERE))).resolve()
FB_TASKS = [t.strip() for t in (os.getenv("FB_TASKS") or "FB_Agent_0800,FB_Agent_1300,FB_Agent_1800").split(",") if t.strip()]
BLOG_TASK = (os.getenv("BLOG_TASK") or "Blog_Poster_MWF_0830").strip()

RUN_FB_BAT = PROJECT_DIR / "run_fb_agent.bat"
RUN_BLOG_BAT = PROJECT_DIR / "run_blog.bat"
FB_LOG = PROJECT_DIR / "logs" / "fb_agent.log"
BLOG_LOG = PROJECT_DIR / "logs" / "blog_agent.log"
IMAGES_DIR = PROJECT_DIR / "posts" / "images"

if not BOT_TOKEN:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN in .env")

# ---------- HELPERS ----------
def _auth_ok(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    uname = (update.effective_user.username or "").lower()
    return uname in {u.lower() for u in ALLOWED_USERS}

async def _auth_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if _auth_ok(update):
        return True
    await update.effective_chat.send_message("🚫 Not authorized.")
    return False

def run_cmd(cmd: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def query_task(name: str) -> str:
    code, out, err = run_cmd(["schtasks", "/query", "/tn", name, "/v", "/fo", "list"], timeout=20)
    if code != 0:
        return f"{name}: ERROR – {err or out}"
    lines = [l for l in out.splitlines() if any(k in l for k in ["Status:", "Next Run Time:", "Last Run Time:", "Last Result:"])]
    return f"{name}:\n" + ("\n".join(lines) if lines else out[:500])

def tail(path: Path, n: int = 80) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(data[-n:]) if data else "(empty)"
    except FileNotFoundError:
        return "(log file not found)"

def newest_image() -> Optional[Path]:
    if not IMAGES_DIR.exists():
        return None
    imgs = sorted(IMAGES_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return imgs[0] if imgs else None

async def run_bat(path: Path, timeout: int = 180) -> str:
    if not path.exists():
        return f"BAT not found: {path}"
    try:
        p = await asyncio.create_subprocess_exec(
            "cmd", "/c", str(path),
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(p.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            p.kill()
            return "Started, but still running after timeout. Check logs."
        out = (stdout or b"").decode("utf-8", errors="ignore").strip()
        err = (stderr or b"").decode("utf-8", errors="ignore").strip()
        if err and not out:
            return f"stderr:\n{err[:1500]}"
        return out[-1500:] if out else (err[:1500] if err else "Done.")
    except Exception as e:
        return f"Error: {e}"

# ---------- HANDLERS ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update, context):
        return
    kb = [
        [InlineKeyboardButton("Post Now", callback_data="post_now"),
         InlineKeyboardButton("Blog Now", callback_data="blog_now")],
        [InlineKeyboardButton("Status", callback_data="status"),
         InlineKeyboardButton("Last Image", callback_data="image")],
        [InlineKeyboardButton("Logs", callback_data="logs_fb"),
         InlineKeyboardButton("Blog Logs", callback_data="logs_blog")],
    ]
    await update.effective_chat.send_message("NoDaddy • Telegram Dashboard\nChoose an action:", reply_markup=InlineKeyboardMarkup(kb))

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update, context):
        return
    parts = [query_task(t) for t in FB_TASKS]
    if BLOG_TASK:
        parts.append(query_task(BLOG_TASK))
    await update.effective_chat.send_message(("\n\n".join(parts))[:4000])

async def post_now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update, context):
        return
    await update.effective_chat.send_message("▶️ Running Facebook agent…")
    out = await run_bat(RUN_FB_BAT)
    await update.effective_chat.send_message(f"Done. Output:\n{out}")
    img = newest_image()
    if img:
        try:
            await update.effective_chat.send_photo(photo=img.read_bytes(), caption=f"Latest image: {img.name}")
        except Exception:
            pass

async def blog_now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update, context):
        return
    await update.effective_chat.send_message("▶️ Running Blog poster…")
    out = await run_bat(RUN_BLOG_BAT)
    await update.effective_chat.send_message(f"Done. Output:\n{out}")

# ---- PLAIN-TEXT LOGS (as requested) ----
async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update, context):
        return
    txt = tail(FB_LOG, 80)
    await update.effective_chat.send_message(f"fb_agent.log (tail):\n{txt}", disable_web_page_preview=True)

async def logs_blog_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update, context):
        return
    txt = tail(BLOG_LOG, 80)
    await update.effective_chat.send_message(f"blog_agent.log (tail):\n{txt}", disable_web_page_preview=True)

async def image_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update, context):
        return
    img = newest_image()
    if not img:
        await update.effective_chat.send_message("No images found yet.")
        return
    try:
        await update.effective_chat.send_photo(photo=img.read_bytes(), caption=f"Latest image: {img.name}")
    except Exception as e:
        await update.effective_chat.send_message(f"Couldn't send image: {e}")

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update, context):
        return
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    await q.answer()
    if data == "post_now":
        await post_now_cmd(update, context)
    elif data == "blog_now":
        await blog_now_cmd(update, context)
    elif data == "status":
        await status_cmd(update, context)
    elif data == "image":
        await image_cmd(update, context)
    elif data == "logs_fb":
        await logs_cmd(update, context)
    elif data == "logs_blog":
        await logs_blog_cmd(update, context)

# ---------- ERROR HANDLER ----------
async def on_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        raise context.error
    except BadRequest as e:
        print("BadRequest:", e)
    except Exception as e:
        print("Unhandled error:", e)

# ---------- MAIN ----------
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("post_now", post_now_cmd))
    app.add_handler(CommandHandler("blog_now", blog_now_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("logs_blog", logs_blog_cmd))
    app.add_handler(CommandHandler("image", image_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_error_handler(on_error)
    print("Telegram dashboard bot running… Press Ctrl+C to stop.")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()


