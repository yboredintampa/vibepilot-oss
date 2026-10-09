# backend/services/caption_service.py
import os
import re
import random
from typing import List
import replicate

CAPTION_SYSTEM_PROMPT = """You are a pool service marketing expert.
Generate engaging social media captions for pool service companies.

RULES:
- Maximum 120 characters (strictly enforce)
- End with clear CTA: "DM for quote" or "Book now" or "Call today"
- No hashtags in caption body
- No rambling or filler words
- Focus on customer benefit or pain point

FORBIDDEN:
- Hashtags in caption text
- Emojis
- Generic phrases like "check out this"
- Questions without answers"""

CAPTION_USER_TEMPLATE = """Image description: {vision_caption}
Tone: {tone}
Trade: {trade}

Generate 5 caption variants (max 120 chars each, end with CTA):"""


class CaptionGenerator:
    def __init__(self):
        self.api_key = os.getenv("REPLICATE_API_TOKEN")
        if not self.api_key:
            raise ValueError("REPLICATE_API_TOKEN not found")
    
    def generate_variants(self, vision_description: str, tone: str = "professional", trade: str = "pool_service", count: int = 5, cta_probability: float = 0.30) -> List[str]:
        """Generate caption variants with configurable CTA probability"""
        user_prompt = CAPTION_USER_TEMPLATE.format(vision_caption=vision_description, tone=tone, trade=trade)
        
        output = replicate.run(
            os.getenv("REPLICATE_LLM", "meta/meta-llama-3-8b-instruct"),
            input={
                "prompt": user_prompt,
                "max_tokens": 500,
                "temperature": 0.8
            }
        )
        
        full_text = "".join(output)
        
        # Split by newlines and filter
        lines = full_text.split('\n')
        
        # Filter out meta-commentary and preamble
        captions = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                continue
            # Skip preamble lines
            if any(skip in line.lower() for skip in [
                'here are', 'here\'s', 'caption variants', 
                'variant 1', 'variant 2', 'variant 3', 'variant 4', 'variant 5',
                '**variant', 'version 1', 'version 2'
            ]):
                continue
            captions.append(line)
        
        sanitized = []
        for caption in captions[:count * 2]:  # Get more candidates to ensure we have enough
            clean = self.sanitize_caption(caption, cta_probability=cta_probability)
            if clean and len(clean) > 20:  # Must be at least 20 chars (filter out junk)
                sanitized.append(clean)
            if len(sanitized) >= count:
                break
        
        # Fill with fallbacks if needed
        while len(sanitized) < count:
            sanitized.append(self._fallback_caption(vision_description))
        
        return sanitized[:count]
    
    def sanitize_caption(self, raw_caption: str, max_length: int = 120, cta_probability: float = 0.30) -> str:
        """
        Sanitize caption with configurable CTA probability
        
        Args:
            raw_caption: Raw LLM output
            max_length: Max chars (default 120)
            cta_probability: Chance of adding CTA (0.0-1.0, default 0.30 = 30%)
        """
        caption = re.sub(r'^\d+\.\s*', '', raw_caption).strip()
        caption = re.sub(r'#\w+', '', caption).strip()
        caption = re.sub(r'[^\x00-\x7F]+', '', caption).strip()
        
        if len(caption) > max_length:
            truncated = caption[:max_length]
            last_punct = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
            if last_punct > 0:
                caption = truncated[:last_punct + 1]
            else:
                caption = truncated[:max_length - 15] + "..."
        
        # Variety of CTAs
        ctas = [
            "DM for quote", "DM us", "DM for details",
            "Call today", "Call us", "Call now",
            "Book now", "Book service", "Schedule now", "Schedule service",
            "Visit link", "Link in bio", "Tap link",
            "Get quote", "Free quote"
        ]
        has_cta = any(cta.lower() in caption.lower() for cta in ctas)
        
        # Only consider adding CTA based on probability
        if not has_cta and random.random() < cta_probability:
            if not caption.endswith(('.', '!', '?')):
                # Add a random CTA
                random_cta = random.choice(["DM for quote!", "Call today!", "Book now!"])
                caption = caption.rstrip('.!?') + f". {random_cta}"
                if len(caption) > max_length:
                    caption = caption[:max_length - 15] + f" {random_cta}"
        
        # Ensure it ends with punctuation (even if no CTA added)
        if not caption.endswith(('.', '!', '?')):
            caption = caption + "."
        
        return caption[:max_length]
    
    def _fallback_caption(self, description: str) -> str:
        templates = [
            "Pool maintenance made easy.",
            "Professional service you can trust.",
            "Keep your pool pristine.",
        ]
        return random.choice(templates)
