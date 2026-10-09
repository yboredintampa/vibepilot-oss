#!/usr/bin/env python3
"""Unified training data loader for all VibePilot categories."""

import os
import random
from typing import Dict

CONTENT_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE = {}

def get_random_example(category: str) -> Dict[str, str]:
    """Get random training example for category."""
    category = category.lower().strip()
    
    if category not in _CACHE:
        filename = f"pools_{category}_training.txt"
        filepath = os.path.join(CONTENT_DIR, filename)
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            
            _CACHE[category] = []
            for line in lines:
                if "|" in line:
                    parts = line.split("|", 1)
                    _CACHE[category].append({
                        "caption": parts[0].strip(),
                        "image_prompt": parts[1].strip()
                    })
                else:
                    _CACHE[category].append({
                        "caption": line,
                        "image_prompt": line
                    })
            
            print(f"[TRAINING] Loaded {len(_CACHE[category])} examples for {category}")
        except Exception as e:
            print(f"[TRAINING] Failed to load {category}: {e}")
            _CACHE[category] = []
    
    if _CACHE.get(category):
        return random.choice(_CACHE[category])
    
    # Fallback
    fallbacks = {
        "realistic": {
            "caption": "Crystal clear Florida pool",
            "image_prompt": "professional photo of clean Florida residential pool, crystal clear water, palm trees, natural daylight"
        },
        "meme": {
            "caption": "Pool maintenance done right",
            "image_prompt": "clean Florida pool, simple composition for text overlay, bright lighting"
        },
        "educational": {
            "caption": "Understanding pool chemistry",
            "image_prompt": "Florida pool, wide angle, educational style, clear water"
        },
        "persuasive": {
            "caption": "Professional service you can trust",
            "image_prompt": "beautiful Florida pool at golden hour, inviting atmosphere, resort quality"
        },
        "comedic": {
            "caption": "When your pool is cleaner than your kitchen",
            "image_prompt": "pristine Florida pool, bright cheerful lighting, simple composition"
        },
        "confrontational": {
            "caption": "Stop ignoring your pool maintenance",
            "image_prompt": "Florida pool, strong lighting contrast, documentary style"
        },
        "blog": {
            "caption": "The secret to crystal clear water",
            "image_prompt": "Florida residential pool, professional photography, wide angle"
        }
    }
    
    return fallbacks.get(category, fallbacks["realistic"])

# Backwards compatibility
def get_random_realistic_example():
    return get_random_example("realistic")

if __name__ == "__main__":
    print("Testing training data loader...")
    for cat in ["realistic", "meme", "educational", "persuasive", "comedic", "confrontational", "blog"]:
        example = get_random_example(cat)
        print(f"\n{cat.upper()}:")
        print(f"  Examples loaded: {len(_CACHE.get(cat, []))}")
