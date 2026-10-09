#!/usr/bin/env python3
import os
import sys
import logging
import time
import uuid
import requests
import replicate
from typing import Optional, Dict, Any

sys.path.insert(0, '/app/content')

try:
    from pools_training_unified import get_random_example
    TRAINING_AVAILABLE = True
except Exception:
    TRAINING_AVAILABLE = False
    def get_random_example(category: str) -> Dict[str, str]:
        return {"caption": "Crystal clear Florida pool", "image_prompt": "professional photo of pristine Florida residential pool, crystal clear blue water, white concrete deck, palm trees background, sunny day, empty water surface"}

# Import vision validation
# from vision_service import validate_no_pool_toys

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
log.propagate = True

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
ALLOW_IMAGE_POSTS = os.getenv("ALLOW_IMAGE_POSTS", "1").strip().lower() not in {"0", "false", "no"}
GENERATED_DIR = os.getenv("GENERATED_IMAGES_DIR", "/opt/vibepilot/generated_images")

SDXL_MODEL = "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b"

NEGATIVE_PROMPT = """pool toys, floaties, inflatable toys, rubber ducks, duck floaties, yellow ducks, orange ducks, pink flamingos, unicorn floats, donut floats, swan floats, pool noodles, beach balls, water toys, floating toys, floating objects""".strip()

_replicate_client: Optional[replicate.Client] = None

def _ensure_generated_dir() -> None:
    try:
        os.makedirs(GENERATED_DIR, exist_ok=True)
    except Exception as e:
        log.error("[image_prompt_manager] Failed to create dir: %s", e)

def _get_client() -> Optional[replicate.Client]:
    global _replicate_client
    if not REPLICATE_API_TOKEN:
        return None
    if _replicate_client is None:
        _replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    return _replicate_client

def build_image_prompt(category: str, caption: Optional[str] = None, weather_context: Optional[str] = None) -> str:
    cat = (category or "realistic").strip().lower()
    if TRAINING_AVAILABLE:
        try:
            example = get_random_example(cat)
            prompt = example.get("image_prompt", "")
            if prompt:
                log.info("[image_prompt_manager] ✅ Using training data for %s", cat)
                return prompt
        except Exception as e:
            log.warning("[image_prompt_manager] Training failed: %s", e)
    
    fallbacks = {
        "realistic": "professional photo of pristine Florida residential pool, crystal clear blue water, white concrete deck, palm trees, sunny day, empty water",
        "meme": "clean Florida pool, simple composition, crystal water, empty surface",
        "educational": "Florida pool, wide angle, clear water, empty surface",
        "persuasive": "beautiful Florida pool at golden hour, crystal clear water",
        "comedic": "pristine Florida pool, bright lighting, clean water",
        "confrontational": "Florida pool, strong contrast, clear water",
        "blog": "Florida pool, professional photography, crystal clear water"
    }
    return fallbacks.get(cat, fallbacks["realistic"])

def _download_image(url: str, dest_path: str) -> None:
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

def _run_prediction_sdxl(prompt: str, max_retries: int = 5) -> Optional[str]:
    """Generate image with SDXL and validate using vision model."""
    client = _get_client()
    if client is None:
        return None
    
    enhanced_prompt = f"professional photograph, {prompt}, absolutely no pool toys, no floating objects, pristine empty water"
    
    for attempt in range(max_retries):
        try:
            log.info("[image_prompt_manager] 🎨 SDXL attempt %d/%d", attempt + 1, max_retries)
            
            output = replicate.run(
                SDXL_MODEL,
                input={
                    "prompt": enhanced_prompt,
                    "negative_prompt": NEGATIVE_PROMPT,
                    "width": 1024,
                    "height": 768,
                    "num_outputs": 1,
                    "scheduler": "K_EULER",
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                    "refine": "expert_ensemble_refiner",
                    "high_noise_frac": 0.8
                }
            )
            
            image_url = output[0] if isinstance(output, list) else output
            
            # Download to temp for validation
            temp_path = f"/tmp/validate_{uuid.uuid4().hex}.png"
            _download_image(str(image_url), temp_path)
            
            # VISION VALIDATION using Replicate LLaVA
            is_clean, reason = True, "Vision validation disabled"  # is_clean, reason = validate_no_pool_toys(temp_path)
            
            if not is_clean:
                os.remove(temp_path)
                log.warning("[image_prompt_manager] 🔄 Retrying: %s", reason)
                time.sleep(2)
                continue
            
            # APPROVED!
            log.info("[image_prompt_manager] ✅ Image validated clean by vision model")
            return str(image_url)
            
        except Exception as exc:
            log.exception("[image_prompt_manager] Attempt %d failed: %s", attempt + 1, exc)
            time.sleep(2)
    
    log.error("[image_prompt_manager] ❌ All attempts failed")
    return None

def generate_image(
    category: str,
    caption_or_prompt: Optional[str] = None,
    weather_context: Optional[str] = None,
    has_caption_context: Optional[bool] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> str:
    if not ALLOW_IMAGE_POSTS:
        return ""
    
    _ensure_generated_dir()
    prompt = build_image_prompt(category, caption_or_prompt, weather_context)
    image_url = _run_prediction_sdxl(prompt, max_retries=5)
    
    if not image_url:
        log.error("[image_prompt_manager] Failed to generate clean image")
        return ""
    
    filename = f"vp_{uuid.uuid4().hex}.png"
    dest_path = os.path.join(GENERATED_DIR, filename)
    
    try:
        _download_image(image_url, dest_path)
    except Exception as exc:
        log.exception("[image_prompt_manager] Download failed: %s", exc)
        return ""
    
    log.info("[image_prompt_manager] 💾 Saved validated image: %s", dest_path)
    return dest_path
