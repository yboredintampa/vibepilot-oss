import os
import logging
from typing import Optional, Dict, Any

import requests

try:
    from . import llm_safety as safety
except ImportError:  # running as top-level modules (Docker: uvicorn main:app)
    import llm_safety as safety

logger = logging.getLogger(__name__)

PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("META_PAGE_ID")

GRAPH_BASE = "https://graph.facebook.com/v21.0"


class FacebookPostError(Exception):
    """Raised when the Facebook Graph API returns an error."""


def _ensure_env():
    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        raise FacebookPostError(
            "Missing META_PAGE_ACCESS_TOKEN or META_PAGE_ID in environment."
        )


def _post_text(caption: str) -> Dict[str, Any]:
    url = f"{GRAPH_BASE}/{PAGE_ID}/feed"
    data = {
        "message": caption,
        "access_token": PAGE_ACCESS_TOKEN,
    }
    resp = requests.post(url, data=data, timeout=30)
    try:
        payload = resp.json()
    except ValueError:
        resp.raise_for_status()
        return {"ok": True, "raw": resp.text}

    if not resp.ok or "error" in payload:
        logger.error("Facebook text post error: %s", payload)
        raise FacebookPostError(str(payload))

    logger.info("Facebook text post success: %s", payload)
    return {"ok": True, "response": payload}


def _post_photo(caption: str, image_path: str) -> Dict[str, Any]:
    url = f"{GRAPH_BASE}/{PAGE_ID}/photos"
    data = {
        "caption": caption,
        "access_token": PAGE_ACCESS_TOKEN,
    }

    if not os.path.exists(image_path):
        raise FacebookPostError(f"Image path does not exist: {image_path}")

    with open(image_path, "rb") as f:
        files = {"source": f}
        resp = requests.post(url, data=data, files=files, timeout=60)

    try:
        payload = resp.json()
    except ValueError:
        resp.raise_for_status()
        return {"ok": True, "raw": resp.text}

    if not resp.ok or "error" in payload:
        logger.error("Facebook photo post error: %s", payload)
        raise FacebookPostError(str(payload))

    logger.info("Facebook photo post success: %s", payload)
    return {"ok": True, "response": payload}


def post_to_facebook(
    caption: str, image_path: Optional[str] = None, *, approved: bool = False
) -> Dict[str, Any]:
    """
    Public entry point used by:
      - poster.py
      - admin_dashboard /admin/item/{post_id}/post_now

    caption: text to post
    image_path: optional absolute path inside the container (e.g. /app/generated_images/xxx.png)

    approved: must be True. Outbound action; the caller confirms a human approved the item
    (or the operator opted in to direct posting). Otherwise safety.ApprovalRequired is raised.

    Returns a dict with at least {"ok": True/False, ...}
    """
    safety.require_action("post_to_facebook", approved=approved)
    _ensure_env()

    caption = (caption or "").strip()
    if not caption:
        raise FacebookPostError("Caption is empty.")

    logger.info("post_to_facebook called with image_path=%r", image_path)

    if image_path:
        return _post_photo(caption, image_path)
    else:
        return _post_text(caption)
