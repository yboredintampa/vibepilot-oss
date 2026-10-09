import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger("post_queue")


class PostQueue:
    """
    Simple file-based queue for posts.

    - Files live in POST_QUEUE_DIR or /opt/vibepilot/post_queue by default
    - Filenames: YYYYMMDD_HHMMSS.micro0000_<id>.json
    - Status values:
        - "pending_review" (default)
        - "approved"
        - "posted" (for future use when we wire posting-from-queue)
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.environ.get("POST_QUEUE_DIR", "/opt/vibepilot/post_queue")
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    # --- internal helpers -------------------------------------------------

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _filename_for(self, post_id: str, created_at: Optional[datetime] = None) -> str:
        if created_at is None:
            created_at = self._now()
        ts = created_at.strftime("%Y%m%d_%H%M%S.%f0000")
        return os.path.join(self.base_dir, f"{ts}_{post_id}.json")

    def _iter_files(self) -> List[str]:
        files = [
            os.path.join(self.base_dir, f)
            for f in os.listdir(self.base_dir)
            if f.endswith(".json")
        ]
        files.sort()  # oldest -> newest
        return files

    # --- core enqueue API (used by poster.py) -----------------------------

    def enqueue_post(
        self,
        category: str,
        caption: str,
        image_path: str,
        scheduled_for: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new JSON file on disk and return the post dict.
        This is the method poster.py can use to enqueue posts.
        """
        if metadata is None:
            metadata = {}

        post_id = uuid.uuid4().hex
        created_at = self._now()

        post: Dict[str, Any] = {
            "id": post_id,
            "status": "pending_review",
            "category": category,
            "caption": caption,
            "image_path": image_path,
            "created_at": created_at.isoformat(),
            "scheduled_for": scheduled_for,
            "metadata": metadata,
        }

        filename = self._filename_for(post_id, created_at)
        post["file_path"] = filename

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)

        logger.info(
            "[post_queue] Enqueued post id=%s category=%s file=%s",
            post_id,
            category,
            filename,
        )
        return post

    # --- lookup / persistence helpers ------------------------------------

    def _load_from_path(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "file_path" not in data:
                data["file_path"] = path
            return data
        except Exception as exc:
            logger.warning("[post_queue] Failed to load %s: %s", path, exc)
            return None

    def find_by_id(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a queued post by id (searches filenames ending with _<id>.json).
        """
        suffix = f"_{post_id}.json"
        for path in self._iter_files():
            if os.path.basename(path).endswith(suffix):
                post = self._load_from_path(path)
                if post is not None:
                    return post
        return None

    def save(self, post: Dict[str, Any]) -> None:
        """
        Rewrite the JSON for this post to its file_path.
        """
        path = post.get("file_path")
        if not path:
            # try to resolve from id
            existing = self.find_by_id(post["id"])
            if existing and existing.get("file_path"):
                path = existing["file_path"]
            else:
                path = self._filename_for(post["id"])
            post["file_path"] = path

        with open(path, "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)

    # --- listing & status management -------------------------------------

    def list_posts(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Return up to `limit` posts, newest first.
        If status is given, filter to that status.
        """
        posts: List[Dict[str, Any]] = []
        for path in reversed(self._iter_files()):  # newest -> oldest
            data = self._load_from_path(path)
            if not data:
                continue
            if status and data.get("status") != status:
                continue
            posts.append(data)
            if len(posts) >= limit:
                break
        return posts

    def set_status(self, post_id: str, status: str) -> Optional[Dict[str, Any]]:
        """
        Update status for a given post id and persist.
        """
        post = self.find_by_id(post_id)
        if not post:
            return None
        post["status"] = status
        post["updated_at"] = self._now().isoformat()
        self.save(post)
        logger.info("[post_queue] Set status id=%s status=%s", post_id, status)
        return post

    def delete(self, post_id: str) -> bool:
        """
        Delete the JSON file for a given post id.
        """
        post = self.find_by_id(post_id)
        if not post:
            return False
        path = post.get("file_path")
        if path and os.path.exists(path):
            os.remove(path)
            logger.info("[post_queue] Deleted post id=%s file=%s", post_id, path)
            return True
        return False


# -------------------------------------------------------------------------
# Backwards-compatible wrapper for existing imports
# -------------------------------------------------------------------------

def enqueue_post(
    category: str,
    caption: str,
    image_path: str,
    scheduled_for: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Backwards-compatible helper so existing code can still do:

        from post_queue import enqueue_post

    Internally delegates to PostQueue().enqueue_post(...).
    """
    queue = PostQueue()
    return queue.enqueue_post(
        category=category,
        caption=caption,
        image_path=image_path,
        scheduled_for=scheduled_for,
        metadata=metadata,
    )


# -------------------------------------------------------------------------
# CLI interface: list / show / approve / delete
# -------------------------------------------------------------------------

import argparse  # noqa: E402


def _cli_list(queue: PostQueue, args: argparse.Namespace) -> int:
    posts = queue.list_posts(status=args.status, limit=args.limit)
    if not posts:
        print("No posts found.")
        return 0

    for p in posts:
        caption = (p.get("caption") or "").replace("\n", " ")
        if len(caption) > 80:
            caption = caption[:77] + "..."
        print(
            f"{p.get('id')} "
            f"[{p.get('status')}] "
            f"{p.get('category')} "
            f"created={p.get('created_at')} "
            f"-> {caption}"
        )
    return 0


def _cli_show(queue: PostQueue, args: argparse.Namespace) -> int:
    post = queue.find_by_id(args.id)
    if not post:
        print(f"No post found with id={args.id}")
        return 1
    print(json.dumps(post, ensure_ascii=False, indent=2))
    return 0


def _cli_approve(queue: PostQueue, args: argparse.Namespace) -> int:
    post = queue.set_status(args.id, "approved")
    if not post:
        print(f"No post found with id={args.id}")
        return 1
    print(f"Post {args.id} marked as approved.")
    return 0


def _cli_delete(queue: PostQueue, args: argparse.Namespace) -> int:
    ok = queue.delete(args.id)
    if not ok:
        print(f"No post found with id={args.id}")
        return 1
    print(f"Post {args.id} deleted.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage queued posts (file-based queue in /opt/vibepilot/post_queue)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List posts in the queue")
    p_list.add_argument(
        "--status",
        choices=["pending_review", "approved", "posted"],
        default=None,
        help="Optional status filter",
    )
    p_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of posts to show (newest first)",
    )

    # show
    p_show = subparsers.add_parser("show", help="Show full JSON for a single post")
    p_show.add_argument("id", help="Post id (the hex id from the JSON)")

    # approve
    p_approve = subparsers.add_parser(
        "approve", help="Mark a post as approved (ready to schedule/post later)"
    )
    p_approve.add_argument("id", help="Post id")

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a post from the queue")
    p_delete.add_argument("id", help="Post id")

    args = parser.parse_args(argv)
    queue = PostQueue()

    if args.command == "list":
        return _cli_list(queue, args)
    if args.command == "show":
        return _cli_show(queue, args)
    if args.command == "approve":
        return _cli_approve(queue, args)
    if args.command == "delete":
        return _cli_delete(queue, args)

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
