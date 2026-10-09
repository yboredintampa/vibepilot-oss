# backend/services/vision_service.py
import os
import base64
from io import BytesIO
from PIL import Image
import replicate


class VisionCaptioner:
    def __init__(self):
        self.api_key = os.getenv("REPLICATE_API_TOKEN")
        if not self.api_key:
            raise ValueError("REPLICATE_API_TOKEN not found")
    
    def describe_image(self, image_url: str) -> str:
        """Generate base description from image URL using BLIP"""
        print(f"[VISION] Calling BLIP with image: {image_url}")
        try:
            output = replicate.run(
                "salesforce/blip:2e1dddc8621f72155f24cf2e0adbde548458d3cab9f00c0139eea840d0ac4746",
                input={
                    "image": image_url,
                    "task": "image_captioning"
                }
            )
            
            description = str(output).strip()
            print(f"[VISION] BLIP returned: {description}")
            return description
            
        except Exception as e:
            print(f"[VISION] BLIP error: {e}")
            return "A swimming pool with equipment visible"
    
    def describe_from_base64(self, image_base64: str) -> str:
        """Generate description from base64 encoded image"""
        print(f"[VISION] Processing base64 image")
        try:
            if "," in image_base64:
                image_base64 = image_base64.split(",")[1]
            
            image_bytes = base64.b64decode(image_base64)
            image = Image.open(BytesIO(image_bytes))
            
            temp_path = "/tmp/temp_vision_upload.jpg"
            image.save(temp_path, format="JPEG")
            
            with open(temp_path, "rb") as f:
                output = replicate.run(
                    "salesforce/blip:2e1dddc8621f72155f24cf2e0adbde548458d3cab9f00c0139eea840d0ac4746",
                    input={
                        "image": f,
                        "task": "image_captioning"
                    }
                )
            
            import os as os_module
            os_module.remove(temp_path)
            
            description = str(output).strip()
            print(f"[VISION] BLIP returned: {description}")
            return description
            
        except Exception as e:
            print(f"[VISION] BLIP error: {e}")
            return "A swimming pool with equipment visible"
    
    def refine_for_trade(self, base_description: str, trade: str = "pool_service") -> str:
        """Enhance description with trade-specific terminology using LLM"""
        print(f"[VISION] Refining description for {trade}: {base_description}")
        
        TRADE_REFINEMENT_PROMPTS = {
            "pool_service": """You are a pool service expert.

Base image description: "{description}"

Refine this description to be specific and useful for pool service marketing:
- Identify specific equipment if visible (filter, pump, heater, salt cell, etc)
- Use industry terminology (DE filter, cartridge, skimmer, plaster, pebble, etc)
- Identify issues or maintenance needs
- Keep under 60 words
- Focus on what pool owners care about

Refined description:""",
        }
        
        prompt_template = TRADE_REFINEMENT_PROMPTS.get(trade, TRADE_REFINEMENT_PROMPTS["pool_service"])
        prompt = prompt_template.format(description=base_description)
        
        try:
            output = replicate.run(
                os.getenv("REPLICATE_LLM", "meta/meta-llama-3-8b-instruct"),
                input={
                    "prompt": prompt,
                    "max_tokens": 150,
                    "temperature": 0.3
                }
            )
            
            refined = "".join(output).strip()
            print(f"[VISION] Refined description: {refined}")
            
            if len(refined) > 200 or not refined:
                return base_description
            
            return refined
            
        except Exception as e:
            print(f"[VISION] LLM refinement error: {e}")
            return base_description
