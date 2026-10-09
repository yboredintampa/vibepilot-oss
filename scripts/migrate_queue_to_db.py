#!/usr/bin/env python3
"""Migrate post_queue/*.json files to PostgreSQL"""
import json
import os
import sys
from pathlib import Path
import psycopg2

DB_URL = os.getenv("DATABASE_URL", "").strip()
if not DB_URL:
    sys.exit("DATABASE_URL is not set (see .env.example)")
QUEUE_DIR = Path(os.getenv("POST_QUEUE_DIR", "/opt/vibepilot/post_queue"))
TENANT_ID = 1

def parse_queue_file(filepath):
    try:
        with open(filepath) as f:
            data = json.load(f)
        return {
            'caption': data.get('caption', ''),
            'image_path': data.get('image_path'),
            'image_prompt': data.get('image_prompt'),
            'category': data.get('category'),
            'status': data.get('status', 'pending_review'),
            'platform': data.get('platform', 'facebook'),
            'caption_voice_score': data.get('caption_voice_score'),
            'image_accuracy_score': data.get('image_accuracy_score'),
            'rating': data.get('rating'),
            'used_llm': data.get('used_llm', False),
            'caption_hash': data.get('caption_hash'),
            'legacy_filename': filepath.name
        }
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return None

def migrate():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    json_files = list(QUEUE_DIR.glob("*.json"))
    print(f"Found {len(json_files)} JSON files")
    
    migrated = 0
    for filepath in json_files:
        data = parse_queue_file(filepath)
        if not data:
            continue
        try:
            cur.execute("""
                INSERT INTO posts (
                    tenant_id, caption, image_path, image_prompt, category,
                    status, platform, caption_voice_score, image_accuracy_score,
                    rating, used_llm, caption_hash, legacy_filename
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                TENANT_ID, data['caption'], data['image_path'], data['image_prompt'],
                data['category'], data['status'], data['platform'],
                data['caption_voice_score'], data['image_accuracy_score'],
                data['rating'], data['used_llm'], data['caption_hash'],
                data['legacy_filename']
            ))
            migrated += 1
        except Exception as e:
            print(f"Error: {filepath.name}: {e}")
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Migrated {migrated} posts!")

if __name__ == "__main__":
    migrate()
