# -*- coding: utf-8 -*-
import os, time, logging, replicate
from vp_helpers import env  # use shim, not repo utils

REPLICATE_API_TOKEN = env("REPLICATE_API_TOKEN")
if not REPLICATE_API_TOKEN:
    raise RuntimeError("REPLICATE_API_TOKEN missing in .env")

client = replicate.Client(api_token=REPLICATE_API_TOKEN)

def run_image(model: str, prompt: str, width=1024, height=1024, retries=3, delay=3) -> str | None:
    for attempt in range(1, retries+1):
        try:
            out = client.run(
                model,
                input={"prompt": prompt, "width": int(width), "height": int(height)}
            )
            if isinstance(out, str) and out.startswith("http"):
                return out
            if isinstance(out, list) and out and str(out[0]).startswith("http"):
                return out[0]
            logging.warning(f"Unexpected image output (attempt {attempt}): {out}")
        except Exception as e:
            logging.warning(f"Image gen attempt {attempt} failed: {e}")
        time.sleep(delay)
    return None
