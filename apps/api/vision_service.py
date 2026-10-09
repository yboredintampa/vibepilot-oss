#!/usr/bin/env python3
"""
Unified vision service for VibePilot using Replicate.
1. Validate AI images (reject pool toys)
2. Caption user-uploaded worksite photos
"""
import os
import logging
import replicate
from typing import Tuple

log = logging.getLogger(__name__)

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

# LLaVA vision model on Replicate
VISION_MODEL = "yorickvp/llava-v1.6-34b:41ecfbfb261e6c1adf3ad896c9066ca98346996d7c4045c5bc944a79d430f174"


def _call_vision_model(image_path: str, prompt: str) -> str:
    """Call Replicate vision model with local image."""
    if not REPLICATE_API_TOKEN:
        raise ValueError("REPLICATE_API_TOKEN not set")
    
    try:
        # LLaVA expects file path or URL
        output = replicate.run(
            VISION_MODEL,
            input={
                "image": open(image_path, 'rb'),
                "prompt": prompt,
                "max_tokens": 300
            }
        )
        
        # Concatenate output
        response = "".join(output) if hasattr(output, '__iter__') else str(output)
        return response.strip()
        
    except Exception as e:
        log.exception("[vision] Replicate call failed: %s", e)
        raise


def validate_no_pool_toys(image_path: str) -> Tuple[bool, str]:
    """
    Check if AI-generated pool image contains toys/floaties.
    
    Returns:
        (is_clean, reason)
    """
    try:
        prompt = """Look at this swimming pool image. Does it contain ANY pool toys, floaties, rubber ducks, inflatable toys, beach balls, pool noodles, or any floating objects in the water? Answer with YES or NO, then briefly explain what you see."""
        
        response = _call_vision_model(image_path, prompt)
        
        # Check if response indicates toys
        has_toys = response.upper().startswith("YES")
        
        if has_toys:
            log.warning("[vision] 🦆 TOYS DETECTED: %s", response)
            return False, response
        else:
            log.info("[vision] ✅ CLEAN: %s", response)
            return True, response
            
    except Exception as e:
        log.exception("[vision] Validation failed: %s", e)
        return True, f"Validation error: {e}"  # Allow on error


def caption_worksite_photo(image_path: str, business_name: str = "Sunny Side Pool Co.", tone: str = "professional") -> str:
    """
    Generate professional caption for user-uploaded worksite photo.
    """
    try:
        prompt = f"""You are writing a social media caption for {business_name}, a pool service company.

Describe this pool equipment or maintenance work in 2-3 short sentences. Focus on:
- What equipment is shown (pump, filter, heater, valves, plumbing)
- What maintenance/repair work is being done
- Technical details that show expertise

Write a {tone} caption under 200 characters. No hashtags. Just the caption text."""
        
        caption = _call_vision_model(image_path, prompt)
        
        # Clean up the response
        caption = caption.strip().strip('"').strip("'")
        
        log.info("[vision] 📸 Generated caption: %s", caption[:100])
        return caption
        
    except Exception as e:
        log.exception("[vision] Caption generation failed: %s", e)
        return f"Professional pool service by {business_name}. Keeping your equipment running perfectly."


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python vision_service.py validate <image_path>")
        print("  python vision_service.py caption <image_path> [business_name]")
        sys.exit(1)
    
    mode = sys.argv[1]
    image_path = sys.argv[2]
    
    if mode == "validate":
        is_clean, reason = validate_no_pool_toys(image_path)
        print(f"Clean: {is_clean}")
        print(f"Reason: {reason}")
    
    elif mode == "caption":
        business = sys.argv[3] if len(sys.argv) > 3 else "Sunny Side Pool Co."
        caption = caption_worksite_photo(image_path, business)
        print(caption)
    
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
