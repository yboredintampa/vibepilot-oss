#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, io, sys, time, logging, argparse, mimetypes, hashlib
from dataclasses import dataclass
from typing import Optional, Tuple
from pathlib import Path

import requests
from PIL import Image

# Local helpers you already have / just added
from dotenv import load_dotenv
from replicate_client import run_image as replicate_run_image
from facebook_poster import post_image_file, post_image_url, post_text

from metrics import log_row
from notify import tg_send


# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ----------------------------
# Dataclasses
# ----------------------------
@dataclass
class ImageDownload:
    path: Path
    mime: str
    size_kb: int


# ----------------------------
# Utils
# ----------------------------
def env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(name)
    return val if val not in (None, "") else default

def is_truthy(x: Optional[str]) -> bool:
    return str(x).strip() in ("1", "true", "True", "yes", "on")

def to_str_url(maybe_url):
    """
    Replicate may return a string or a FileOutput-like object.
    This normalizes it to a plain string URL if possible.
    """
    if maybe_url is None:
        return None
    if isinstance(maybe_url, str):
        return maybe_url
    # replicate.helpers.FileOutput behaves like a sequence/str sometimes
    try:
        s = str(maybe_url)
        if s.startswith("http"):
            return s
    except Exception:
        pass
    return None

def ensure_tmp_dir() -> Path:
    p = Path("/tmp")
    p.mkdir(parents=True, exist_ok=True)
    return p

# ----------------------------
# Image pipeline
# ----------------------------
def download_web_image_to_jpeg(url: str) -> ImageDownload:
    """
    Fetch image bytes (e.g., webp from Replicate Delivery), convert to JPEG,
    write to /tmp/vp_<pid>.jpg, return path + meta for upload to FB.
    """
    logging.info("Downloading image: %s", url)
    r = requests.get(url, timeout=60)
    r.raise_for_status()

    img_bytes = io.BytesIO(r.content)
    img = Image.open(img_bytes).convert("RGB")

    tmpdir = ensure_tmp_dir()
    out_path = tmpdir / f"vp_{os.getpid()}.jpg"

    img.save(out_path, format="JPEG", quality=95, optimize=True)
    size_kb = int(out_path.stat().st_size / 1024)
    logging.info("Saved JPEG: %s", out_path)

    # Guess mime from extension (Pillow save is JPEG)
    mime = "image/jpeg"
    return ImageDownload(path=out_path, mime=mime, size_kb=size_kb)

# ----------------------------
# Caption / Prompt (simple for now; you can swap in your generator)
# ----------------------------
def build_caption(category: str) -> str:
    # Minimal, deterministic caption for stability; replace with your generator when ready
    # Keep it short and ad-safe; emojis are fine.
    base = {
        "realistic": "Pool day in Sunnyvale 🌴",
        "educational": "Crystal-clear pools start with balanced chemistry. 💧",
        "persuasive": "Book a pro cleaning. Your weekend will thank you. ✅",
        "comedic": "PSA: Leaves are not pool décor. 😂",
        "meme": "Florida sun: 1, Algae: 0. 😎",
        "blog": "Today’s tip: why filter pressure matters more than you think.",
        "confrontational": "We fix what ‘budget cleans’ leave behind. Period.",
    }
    return base.get(category, "Pool day in Sunnyvale 🌴")

def build_image_prompt(category: str) -> str:
    # Keep the prompt clean, broad, brand-safe
    # You can branch by category if you like; here we keep a single aesthetic
    return "clean, bright pool service photo, Sunnyvale backyard, wide angle, daytime"

# ----------------------------
# Core run
# ----------------------------
def run_once(category: str) -> dict:
    """
    Returns a dict with keys:
      - dry_run (bool)
      - image_url (str or None)
      - caption (str)
      - post_id/media_id on success
    """
    t0 = time.time()
    dry_run = is_truthy(env("DRY_RUN", "0"))
    model = env("REPLICATE_OWNER_MODEL", "black-forest-labs/flux-schnell")

    caption = build_caption(category)
    prompt = build_image_prompt(category)

    # Generate image via Replicate
    image_url = to_str_url(replicate_run_image(model, prompt))

    if dry_run:
        logging.info("[DRY_RUN] Would post image+caption now")
        # Metrics + alert (dry run)
        log_row(
            category=category,
            dry_run=True,
            caption=caption,
            image_mode="url" if image_url else "none",
            image_mime="",
            jpeg_size_kb=0,
            replicate_model=model,
            prediction_id="",
            duration_ms=int((time.time() - t0) * 1000),
            fb_status="ok",
            http_code=200,
            error_code=0,
            error_subcode=0,
            post_id="",
            media_id="",
        )
        return {"dry_run": True, "image_url": image_url, "caption": caption}

    # Not a dry run → try FILE upload first (JPEG)
    try:
        jpeg_info = None
        if image_url:
            jpeg_info = download_web_image_to_jpeg(image_url)

        if jpeg_info:
            try:
                resp = post_image_file(str(jpeg_info.path), caption)
                # Expect {'id': media_id, 'post_id': post_id}
                post_id = resp.get("post_id") or ""
                media_id = resp.get("id") or ""
                log_row(
                    category=category,
                    dry_run=False,
                    caption=caption,
                    image_mode="file",
                    image_mime=jpeg_info.mime,
                    jpeg_size_kb=jpeg_info.size_kb,
                    replicate_model=model,
                    prediction_id="",
                    duration_ms=int((time.time() - t0) * 1000),
                    fb_status="ok",
                    http_code=200,
                    error_code=0,
                    error_subcode=0,
                    post_id=post_id,
                    media_id=media_id,
                )
                tg_send(f"✅ Posted <b>{category}</b>\nPost: {post_id}")
                return {"id": media_id, "post_id": post_id, "caption": caption}
            except requests.HTTPError as e:
                # Bubble FB error body to logs (facebook_poster already prints body)
                logging.warning("File upload failed (%s). Trying URL upload.", str(e))
                last_status = getattr(e.response, "status_code", 0)
                last_body = getattr(e.response, "text", "")
        else:
            last_status, last_body = 0, "no image_url or JPEG conversion failed"

        # Fallback 2: URL upload directly (works only for fully public, jpg/png endpoints)
        if image_url:
            try:
                resp = post_image_url(image_url, caption)
                post_id = resp.get("post_id") or ""
                media_id = resp.get("id") or ""
                log_row(
                    category=category,
                    dry_run=False,
                    caption=caption,
                    image_mode="url",
                    image_mime="",  # FB fetches it
                    jpeg_size_kb=0,
                    replicate_model=model,
                    prediction_id="",
                    duration_ms=int((time.time() - t0) * 1000),
                    fb_status="ok",
                    http_code=200,
                    error_code=0,
                    error_subcode=0,
                    post_id=post_id,
                    media_id=media_id,
                )
                tg_send(f"✅ Posted (URL) <b>{category}</b>\nPost: {post_id}")
                return {"id": media_id, "post_id": post_id, "caption": caption}
            except requests.HTTPError as e2:
                logging.warning("URL upload failed too (%s). Falling back to text.", str(e2))
                last_status = getattr(e2.response, "status_code", 0)
                last_body = getattr(e2.response, "text", "")
        else:
            last_status, last_body = 0, "no image_url"

        # Final fallback: text-only post
        try:
            resp = post_text(caption)
            post_id = resp.get("id") or ""
            log_row(
                category=category,
                dry_run=False,
                caption=caption,
                image_mode="none",
                image_mime="",
                jpeg_size_kb=0,
                replicate_model=model,
                prediction_id="",
                duration_ms=int((time.time() - t0) * 1000),
                fb_status="ok",
                http_code=200,
                error_code=0,
                error_subcode=0,
                post_id=post_id,
                media_id="",
            )
            tg_send(f"✅ Posted (TEXT) <b>{category}</b>\nPost: {post_id}")
            return {"post_id": post_id, "caption": caption}
        except requests.HTTPError as e3:
            # Total failure → record the failure with details
            status = getattr(e3.response, "status_code", 0)
            body = getattr(e3.response, "text", "")
            log_row(
                category=category,
                dry_run=False,
                caption=caption,
                image_mode="none",
                image_mime="",
                jpeg_size_kb=0,
                replicate_model=model,
                prediction_id="",
                duration_ms=int((time.time() - t0) * 1000),
                fb_status="error",
                http_code=status or last_status,
                error_code=0,
                error_subcode=0,
                post_id="",
                media_id="",
            )
            tg_send(f"❌ Post FAILED: <b>{category}</b>\nHTTP {status}\n{body[:500]}")
            raise

    except Exception as e:
        # Any unexpected error (network, PIL, etc.)
        log_row(
            category=category,
            dry_run=False,
            caption=caption,
            image_mode="none",
            image_mime="",
            jpeg_size_kb=0,
            replicate_model=model,
            prediction_id="",
            duration_ms=int((time.time() - t0) * 1000),
            fb_status="error",
            http_code=0,
            error_code=0,
            error_subcode=0,
            post_id="",
            media_id="",
        )
        tg_send(f"❌ Post CRASHED: <b>{category}</b>\n{str(e)[:500]}")
        raise


# ----------------------------
# CLI
# ----------------------------
def main():
    load_dotenv("/etc/vibepilot/.env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True, help="Category name (e.g., realistic, educational, meme, blog, comedic, persuasive, confrontational)")
    args = parser.parse_args()

    res = run_once(args.category)
    # Print a small JSON-ish dict so cron logs are readable
    print(res)


if __name__ == "__main__":
    main()

