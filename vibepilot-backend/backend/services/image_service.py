# backend/services/image_service.py
import os
import random
import time
import base64
import re
import urllib.request
from typing import List, Tuple, Dict, Any
import replicate


class ImageGenerator:
    def __init__(self):
        self.api_key = os.getenv("REPLICATE_API_TOKEN")
        if not self.api_key:
            raise ValueError("REPLICATE_API_TOKEN not found")
        
        # Use your existing model from .env
        self.model = os.getenv("REPLICATE_OWNER_MODEL", "black-forest-labs/flux-schnell")
        self.negative = os.getenv("REPLICATE_NEGATIVE", "")
    
    def choose_style(self) -> Dict[str, Any]:
        """Randomized, authentic-looking style mix (from your existing code)"""
        # Weights roughly: warm film 40%, glossy 25%, matte 25%, b&w 10%
        styles = [
            ("warm_film", 0.40, {"width": self._pick([1024, 1280, 1536]), "height": self._pick([1024, 1280, 1536])}),
            ("glossy",    0.25, {"width": self._pick([1024, 1280, 1536, 2048]), "height": self._pick([1024, 1280, 1536, 2048])}),
            ("matte",     0.25, {"width": self._pick([1024, 1280, 1536]), "height": self._pick([1024, 1280, 1536])}),
            ("bw_film",   0.10, {"width": self._pick([1024, 1280]), "height": self._pick([1024, 1280])}),
        ]
        r = random.random()
        acc = 0.0
        for name, w, dims in styles:
            acc += w
            if r <= acc:
                return {"name": name, **dims}
        # fallback
        return {"name": "warm_film", "width": 1024, "height": 1024}
    
    def _pick(self, lst):
        return random.choice(lst)
    
    def generate_pool_images(self, description: str, count: int = 2, aspect_ratio: str = "16:9") -> List[str]:
        """Generate high-quality pool service images with FLUX"""
        print(f"[IMAGE] Generating {count} images with FLUX")
        print(f"[IMAGE] Model: {self.model}")
        print(f"[IMAGE] Description: {description}")
        
        images = []
        
        # Determine dimensions from aspect ratio
        aspect_dims = {
            "16:9": (1536, 864),   # Instagram landscape
            "1:1": (1024, 1024),   # Instagram square
            "4:5": (1024, 1280),   # Instagram portrait
        }
        width, height = aspect_dims.get(aspect_ratio, (1536, 864))
        
        for i in range(count):
            try:
                # Enhanced prompt with quality modifiers
                enhanced_prompt = f"""{description}

Style: photorealistic, professional photography, high resolution, sharp focus, natural lighting, clean composition, 4K quality, Instagram-worthy"""
                
                print(f"[IMAGE] Generating image {i+1}/{count}")
                print(f"[IMAGE] Dimensions: {width}x{height}")
                
                # Call FLUX (using your existing pattern)
                output = replicate.run(
                    self.model,
                    input={
                        "prompt": enhanced_prompt,
                        "width": width,
                        "height": height,
                        "num_outputs": 1
                    },
                    use_file_output=False
                )
                
                # Handle output (list or string)
                if isinstance(output, (list, tuple)) and output:
                    uri = output[0]
                elif isinstance(output, str):
                    uri = output
                else:
                    print(f"[IMAGE] Unexpected output type: {type(output)}")
                    continue
                
                # Handle data URI or HTTP URL
                if isinstance(uri, str):
                    if uri.startswith("data:image/"):
                        # Base64 encoded - we'll return the data URI directly
                        print(f"[IMAGE] Generated data URI for image {i+1}")
                        images.append(uri)
                    else:
                        # HTTP URL from Replicate
                        print(f"[IMAGE] Generated URL for image {i+1}: {uri}")
                        images.append(uri)
                
            except Exception as e:
                print(f"[IMAGE] Error generating image {i+1}: {e}")
        
        if not images:
            print("[IMAGE] All generations failed")
        else:
            print(f"[IMAGE] Successfully generated {len(images)}/{count} images")
        
        return images
    
    def generate_before_after(self, problem_description: str, trade: str = "pool_service") -> Tuple[str, str]:
        """Generate problem + solution image pair"""
        print(f"[IMAGE] Generating before/after for: {problem_description}")
        
        # Problem image
        problem_prompt = f"{problem_description}, photorealistic, before service, showing issue"
        problem_images = self.generate_pool_images(problem_prompt, count=1, aspect_ratio="1:1")
        problem_img = problem_images[0] if problem_images else None
        
        # Solution mapping
        solution_mapping = {
            "green": "crystal clear blue water",
            "algae": "pristine clean pool, no algae",
            "clogged": "clean filter, like new",
            "corroded": "brand new equipment, shiny",
            "dirty": "sparkling clean",
        }
        
        solution_desc = "clean, well-maintained pool"
        for keyword, solution in solution_mapping.items():
            if keyword in problem_description.lower():
                solution_desc = solution
                break
        
        solution_prompt = f"{solution_desc}, photorealistic, after service, perfect results"
        solution_images = self.generate_pool_images(solution_prompt, count=1, aspect_ratio="1:1")
        solution_img = solution_images[0] if solution_images else None
        
        return (problem_img, solution_img)
