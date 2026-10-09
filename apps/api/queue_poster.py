import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import requests

from post_queue import PostQueue

logger = logging.getLogger("queue_poster")


def setup_logging() -> None:
    """
    Basic logging config in UTC, similar style to your other scripts,
    but using time.gmtime so logging doesn't blow up.
    """
    import time

    class UTCFormatter(logging.Formatter):
        # logging will call converter(record.created) and expects a struct_time
        converter = time.gmtime

    fmt = "%(asctime)s [%(levelname)s] [UTC] %(message)s"

    handler = logging.StreamHandler()
    handler.setFormatter(UTCFormatter(fmt))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


def get_facebook_credentials() -> Dict[str, str]:
    page_token = os.environ.get("META_PAGE_ACCESS_TOKEN")
    page_id = os.environ.get("META_PAGE_ID")

    if not page_token or not page_id:
        raise RuntimeError(
            "META_PAGE_ACCESS_TOKEN and META_PAGE_ID must be set in the environment."
        )

    return {"page_token": page_token, "page_id": page_id}


def post_image_to_facebook(
    caption: str,
    image_path: str,
    creds: Dict[str, str],
) -> Dict[str, Any]:
    """
    Uploads the local image file to the Facebook page as a photo,
    with the given caption.

    Uses the standard Graph API: POST /{page_id}/photos
    """
    page_id = creds["page_id"]
    page_token = creds["page_token"]

    url = f"https://graph.facebook.com/v19.0/{page_id}/photos"

    logger.info("[queue_poster] Posting image + caption to Facebook (page_id=%s)", page_id)

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with open(image_path, "rb") as img_file:
        files = {"source": img_file}
        data = {
            "caption": caption,
            "access_token": page_token,
        }
        resp = requests.post(url, data=data, files=files, timeout=30)

    try:
        resp_json = resp.json()
    except Exception:
        resp.raise_for_status()
        raise

    if not resp.ok:
        logger.error(
            "[queue_poster] Facebook API error status=%s body=%s",
            resp.status_code,
            resp.text,
        )
        raise RuntimeError(f"Facebook API error: {resp_json}")

    logger.info("[queue_poster] Facebook API response: %s", resp_json)
    return resp_json


def pick_next_approved(queue: PostQueue) -> Optional[Dict[str, Any]]:
    """
    Choose the next approved post to publish.

    Strategy:
      - Get up to N approved posts via list_posts(status="approved")
      - Take the OLDEST by created_at (so approvals go out FIFO)

    If none, return None.
    """
    posts: List[Dict[str, Any]] = queue.list_posts(status="approved", limit=100)
    if not posts:
        return None

    def parse_dt(p: Dict[str, Any]) -> float:
        try:
            return datetime.fromisoformat(p["created_at"]).timestamp()
        except Exception:
            return 0.0

    posts_sorted = sorted(posts, key=parse_dt)  # oldest -> newest
    return posts_sorted[0]


def post_next_approved(dry_run: bool = False) -> int:
    """
    Pop the next approved post, send to Facebook, mark as posted.

    If dry_run=True, just log what WOULD be posted.
    """
    queue = PostQueue()

    logger.info("[queue_poster] Looking for next approved post in queue...")
    post = pick_next_approved(queue)
    if not post:
        logger.info("[queue_poster] No approved posts found.")
        print("No approved posts in queue.")
        return 0

    post_id = post.get("id")
    caption = post.get("caption") or ""
    image_path = post.get("image_path") or ""

    logger.info(
        "[queue_poster] Selected post id=%s category=%s image=%s",
        post_id,
        post.get("category"),
        image_path,
    )

    if dry_run:
        print(
            f"[DRY RUN] Would post id={post_id} (category={post.get('category')}) "
            f"image={image_path}\nCaption:\n{caption}"
        )
        return 0

    # Real post to Facebook
    try:
        creds = get_facebook_credentials()
        fb_resp = post_image_to_facebook(caption, image_path, creds)
    except Exception as exc:
        logger.exception("[queue_poster] Failed to post to Facebook: %s", exc)
        print(f"Error posting to Facebook: {exc}")
        return 1

    # Update queue entry as posted
    post["status"] = "posted"
    post["posted_at"] = datetime.now(timezone.utc).isoformat()

    metadata = post.get("metadata") or {}
    metadata["facebook_response"] = fb_resp
    metadata["facebook_post_id"] = fb_resp.get("post_id") or fb_resp.get("id")
    post["metadata"] = metadata

    queue.save(post)

    logger.info(
        "[queue_poster] Marked post id=%s as posted (facebook_post_id=%s)",
        post_id,
        metadata.get("facebook_post_id"),
    )

    print(
        json.dumps(
            {
                "id": post_id,
                "status": post["status"],
                "facebook_post_id": metadata.get("facebook_post_id"),
            },
            ensure_ascii=False,
        )
    )
    return 0


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

import argparse  # noqa: E402


def main(argv=None) -> int:
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Post approved items from the queue to Facebook."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_post_next = subparsers.add_parser(
        "post-next", help="Post the next approved item from the queue."
    )
    p_post_next.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call Facebook; just show what would be posted.",
    )

    args = parser.parse_args(argv)

    if args.command == "post-next":
        return post_next_approved(dry_run=args.dry_run)

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
