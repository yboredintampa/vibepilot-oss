#!/usr/bin/env python3
"""
Publish APPROVED posts from the queue to Facebook
Called by cron: 0 8,13,18 * * *
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add app to path
sys.path.insert(0, '/app')

QUEUE_DIR = os.getenv("POST_QUEUE_DIR", "/app/post_queue")

def get_approved_posts():
    """Get all APPROVED posts from queue"""
    queue_path = Path(QUEUE_DIR)
    approved = []
    
    for json_file in sorted(queue_path.glob("*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)
                if data.get("status") == "approved":
                    approved.append((json_file, data))
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
    
    return approved

def publish_post(post_file, post_data):
    """Publish a single post to Facebook"""
    try:
        import poster
        
        caption = post_data.get("caption", "")
        image_path = post_data.get("image_path", "")
        
        print(f"[{datetime.now()}] Publishing: {caption[:50]}...")
        
        # Post to Facebook
        success = poster.post_to_facebook(caption, image_path)
        
        if success:
            # Mark as posted
            post_data["status"] = "posted"
            post_data["posted_at"] = datetime.now().isoformat()
            
            with open(post_file, 'w') as f:
                json.dump(post_data, f, indent=2)
            
            print(f"✅ Published successfully")
            return True
        else:
            print(f"❌ Failed to publish")
            return False
            
    except Exception as e:
        print(f"❌ Error publishing: {e}")
        return False

def main():
    dry_run = "--dry-run" in sys.argv
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Checking for APPROVED posts...")
    
    approved_posts = get_approved_posts()
    
    if not approved_posts:
        print("No APPROVED posts found")
        return
    
    print(f"Found {len(approved_posts)} APPROVED post(s)")
    
    for post_file, post_data in approved_posts:
        print(f"\n📋 {post_file.name}")
        print(f"   Caption: {post_data.get('caption', '')[:60]}...")
        
        if not dry_run:
            publish_post(post_file, post_data)
        else:
            print("   [Would publish in live mode]")

if __name__ == "__main__":
    main()
