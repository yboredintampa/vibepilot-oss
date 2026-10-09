import schedule
import time
import subprocess
import os

# Optional: Set working directory to the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run_facebook_post():
    print("📆 Running scheduled Facebook post...")
    subprocess.run(["run_fb_agent.bat"], shell=True)

def run_blog_post():
    print("📆 Running scheduled Blog post...")
    subprocess.run(["run_blog.bat"], shell=True)

# --- Daily Facebook posts at 8 AM, 1 PM, 6 PM ---
schedule.every().day.at("08:00").do(run_facebook_post)
schedule.every().day.at("13:00").do(run_facebook_post)
schedule.every().day.at("18:00").do(run_facebook_post)

# --- Blog posts: M/W/F at 10:00 AM ---
schedule.every().monday.at("10:00").do(run_blog_post)
schedule.every().wednesday.at("10:00").do(run_blog_post)
schedule.every().friday.at("10:00").do(run_blog_post)

print("✅ Scheduler is running. Press Ctrl+C to stop.")
while True:
    schedule.run_pending()
    time.sleep(30)
