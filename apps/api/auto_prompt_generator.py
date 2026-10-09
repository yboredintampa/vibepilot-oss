import os
import time
import logging
from datetime import datetime

from phi3_wrapper import generate_caption, generate_image_prompt
from image_prompt_manager import generate_image
from utils import (
    get_blacklist,
    violates_guardrails,
    already_posted_recently,
    save_post_to_file,
    log_failure
)
from telegram_alerts import send_telegram_message
from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)

# Constants
MAX_RETRIES = 10
RETRY_DELAY = 2

# Category Scheduling
def get_scheduled_category():
    schedule = {
        (0, 8): "realistic",        # Monday AM
        (0, 13): "meme",            # Monday PM
        (0, 18): "educational",     # Monday evening
        (1, 8): "comedic",          # Tuesday AM
        (1, 13): "persuasive",      # Tuesday PM
        (1, 18): "confrontational", # Tuesday evening
        (2, 8): "realistic",        # Wednesday AM
        (2, 13): "educational",     # Wednesday PM
        (2, 18): "meme",            # Wednesday evening
        (3, 8): "comedic",          # Thursday AM
        (3, 13): "confrontational", # Thursday PM
        (3, 18): "persuasive",      # Thursday evening
        (4, 8): "realistic",        # Friday AM
        (4, 13): "meme",            # Friday PM
        (4, 18): "educational",     # Friday evening
        (5, 8): "comedic",          # Saturday AM
        (5, 13): "persuasive",      # Saturday PM
        (5, 18): "confrontational", # Saturday evening
        (6, 8): "realistic",        # Sunday AM
        (6, 13): "educational",     # Sunday PM
        (6, 18): "meme",            # Sunday evening
    }
    weekday = datetime.now().weekday()
    hour = datetime.now().hour
    return schedule.get((weekday, hour), "realistic")

# Main logic
category = get_scheduled_category()
blacklist = get_blacklist()
timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

for attempt in range(1, MAX_RETRIES + 1):
    logging.info(f"🧠 Generating post attempt {attempt}/{MAX_RETRIES} for category: {category}")

    caption = generate_caption(category)
    if not caption:
        log_failure("caption_generation_failed", category=category)
        time.sleep(RETRY_DELAY)
        continue

    logging.info("🧠 Caption generated.")

    if violates_guardrails(caption, category):
        log_failure("violates_guardrails", caption=caption, category=category)
        time.sleep(RETRY_DELAY)
        continue

    if any(bad_word.lower() in caption.lower() for bad_word in blacklist):
        log_failure("blacklist_violation", caption=caption, category=category)
        time.sleep(RETRY_DELAY)
        continue

    if already_posted_recently(caption):
        log_failure("already_posted_recently", caption=caption, category=category)
        time.sleep(RETRY_DELAY)
        continue

    image_prompt = generate_image_prompt(category, caption)
    if not image_prompt:
        log_failure("image_prompt_failed", caption=caption, category=category)
        time.sleep(RETRY_DELAY)
        continue

    image_path = generate_image(category, image_prompt)
    if image_path:
        save_post_to_file(caption, image_path, category, timestamp)
        send_telegram_message(f"✅ Auto post saved for category: *{category}*\n\n📝 {caption}")
        logging.info("✅ Post saved and sent to Telegram.")
        break
    else:
        log_failure("image_generation_failed", caption=caption, category=category)
        logging.warning("❌ Image generation failed.")
        time.sleep(RETRY_DELAY)

else:
    save_post_to_file(caption, None, category, timestamp)
    send_telegram_message(f"⚠️ Fallback: *text-only* post saved for category: *{category}*\n\n📝 {caption}")
    logging.info("⚠️ All attempts failed. Fallback to text-only post.")
