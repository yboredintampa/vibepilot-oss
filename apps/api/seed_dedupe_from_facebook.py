import os
import requests
from dotenv import load_dotenv

from utils import DedupeDB

load_dotenv()
PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN")
GRAPH_V = os.getenv("FB_GRAPH_VERSION", "v23.0")
BASE = f"https://graph.facebook.com/{GRAPH_V}"

def main():
    if not PAGE_ID or not PAGE_TOKEN:
        print("Missing page env")
        return
    d = DedupeDB()
    url = f"{BASE}/{PAGE_ID}/published_posts"
    params = {"fields": "id,message", "limit": 100, "access_token": PAGE_TOKEN}
    added = 0
    while True:
        r = requests.get(url, params=params, timeout=40)
        js = r.json()
        for item in js.get("data", []):
            msg = (item.get("message") or "").strip()
            if msg:
                if not d.seen("caption", msg):
                    d.add("caption", msg)
                    added += 1
        nxt = js.get("paging", {}).get("next")
        if not nxt:
            break
        url = nxt
        params = {}
    print(f"Seeded {added} captions into posts/dedupe.sqlite")

if __name__ == "__main__":
    main()
