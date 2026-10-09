import os
import random

CONTENT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_random_realistic_example():
    """Load a random example from pools_realistic_training.txt"""
    try:
        with open(os.path.join(CONTENT_DIR, "pools_realistic_training.txt"), "r") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
        if not lines:
            return {
                "caption": "Crystal clear Florida backyard pool with sparkling blue water",
                "image_prompt": "photo-realistic florida backyard swimming pool, crystal clear blue water, sunlit concrete deck, palm trees in background, well-maintained residential property, natural daylight, clean composition, no objects in water"
            }
        
        example = random.choice(lines)
        
        # If training file has caption|image_prompt format
        if "|" in example:
            parts = example.split("|", 1)
            return {
                "caption": parts[0].strip(),
                "image_prompt": parts[1].strip() if len(parts) > 1 else parts[0].strip()
            }
        
        # Otherwise just use the line as image prompt
        return {
            "caption": example,
            "image_prompt": example
        }
        
    except Exception as e:
        print(f"Error loading training data: {e}")
        return {
            "caption": "Crystal clear Florida backyard pool with sparkling blue water",
            "image_prompt": "photo-realistic florida backyard swimming pool, crystal clear blue water, sunlit concrete deck, palm trees in background, well-maintained residential property, natural daylight, clean composition, no objects in water"
        }
