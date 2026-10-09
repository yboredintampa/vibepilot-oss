import os
import requests
from dotenv import load_dotenv
load_dotenv()

ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("FB_PAGE_ID")

def post_to_facebook(caption: str, image_path: str = None):
    try:
        if not ACCESS_TOKEN or not PAGE_ID:
            raise Exception("Facebook token or page ID missing.")

        if image_path:
            with open(image_path, 'rb') as img:
                files = {'source': img}
                url = f"https://graph.facebook.com/{PAGE_ID}/photos"
                payload = {'caption': caption, 'access_token': ACCESS_TOKEN}
                r = requests.post(url, data=payload, files=files)
        else:
            url = f"https://graph.facebook.com/{PAGE_ID}/feed"
            payload = {'message': caption, 'access_token': ACCESS_TOKEN}
            r = requests.post(url, data=payload)

        return r.json()
    except Exception as e:
        return {"error": str(e)}
