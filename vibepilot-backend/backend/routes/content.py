# backend/routes/content.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, validator
from typing import List, Optional

from backend.security import require_admin

# Content generation calls paid AI APIs, so every route requires admin auth.
router = APIRouter(prefix="/content", tags=["content"], dependencies=[Depends(require_admin)])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_TRADES = {"pool_service", "hvac", "electrical", "plumbing", "landscaping", "bakery", "general"}


# Request/Response Models
class CaptionRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    tone: str = "professional"
    trade: str = "pool_service"
    cta_probability: float = 0.30  # 30% default

    @validator('tone')
    def validate_tone(cls, v):
        valid_tones = ["professional", "friendly", "educational", "promotional", "technical"]
        if v not in valid_tones:
            raise ValueError(f"Invalid tone. Must be one of: {valid_tones}")
        return v

    @validator('image_url')
    def validate_image_url(cls, v):
        if v is not None and (not v.startswith("https://") or len(v) > 2048):
            raise ValueError("image_url must be an https:// URL")
        return v

    @validator('image_base64')
    def validate_image_base64(cls, v):
        if v is not None and len(v) > MAX_UPLOAD_BYTES * 4 // 3 + 100:
            raise ValueError("image_base64 too large")
        return v

    @validator('trade')
    def validate_trade(cls, v):
        if v not in ALLOWED_TRADES:
            raise ValueError(f"Invalid trade. Must be one of: {sorted(ALLOWED_TRADES)}")
        return v

    @validator('cta_probability')
    def validate_cta_probability(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("cta_probability must be between 0.0 and 1.0")
        return v


class CaptionResponse(BaseModel):
    vision_description: str
    captions: List[str]
    generated_images: List[str]
    all_valid: bool

    @validator('captions')
    def validate_captions(cls, v):
        for caption in v:
            if len(caption) > 120:
                raise ValueError(f"Caption exceeds 120 chars: {len(caption)}")
            if not caption.rstrip().endswith(('!', '?', '.')):
                raise ValueError(f"Caption must end with punctuation: '{caption}'")
            if '#' in caption:
                raise ValueError(f"Caption contains hashtag: '{caption}'")
        return v


@router.post("/generate", response_model=CaptionResponse)
async def generate_content(request: CaptionRequest):
    """Generate social media content from image"""
    try:
        from backend.services.vision_service import VisionCaptioner
        from backend.services.caption_service import CaptionGenerator
        from backend.services.image_service import ImageGenerator

        vision = VisionCaptioner()
        caption_gen = CaptionGenerator()
        image_gen = ImageGenerator()

        # Get image description
        if request.image_url:
            vision_desc = vision.describe_image(request.image_url)
        elif request.image_base64:
            vision_desc = vision.describe_from_base64(request.image_base64)
        else:
            raise HTTPException(status_code=400, detail="Must provide image_url or image_base64")

        # Refine for trade
        trade_desc = vision.refine_for_trade(vision_desc, request.trade)

        # Generate captions with CTA probability
        captions = caption_gen.generate_variants(
            vision_description=trade_desc,
            tone=request.tone,
            trade=request.trade,
            count=5,
            cta_probability=request.cta_probability
        )

        # Generate companion images
        generated_images = image_gen.generate_pool_images(
            description=trade_desc,
            count=2
        )

        return CaptionResponse(
            vision_description=trade_desc,
            captions=captions,
            generated_images=generated_images,
            all_valid=True
        )

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Content generation failed")


@router.post("/generate-from-upload", response_model=CaptionResponse)
async def generate_from_upload(
    file: UploadFile = File(...),
    tone: str = "professional",
    trade: str = "pool_service",
    cta_probability: float = 0.30
):
    """Generate content from direct file upload"""
    if tone not in ["professional", "friendly", "educational", "promotional", "technical"]:
        raise HTTPException(status_code=400, detail="Invalid tone")
    if trade not in ALLOWED_TRADES:
        raise HTTPException(status_code=400, detail="Invalid trade")
    if not 0.0 <= cta_probability <= 1.0:
        raise HTTPException(status_code=400, detail="cta_probability must be between 0.0 and 1.0")
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported image type")
    try:
        from backend.services.vision_service import VisionCaptioner
        from backend.services.caption_service import CaptionGenerator
        from backend.services.image_service import ImageGenerator

        # Read uploaded file
        contents = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(contents) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large")

        # Convert to base64
        import base64
        image_base64 = base64.b64encode(contents).decode('utf-8')
        image_data_uri = f"data:{file.content_type};base64,{image_base64}"

        # Initialize services
        vision = VisionCaptioner()
        caption_gen = CaptionGenerator()
        image_gen = ImageGenerator()

        # Get image description
        vision_desc = vision.describe_from_base64(image_data_uri)

        # Refine for trade
        trade_desc = vision.refine_for_trade(vision_desc, trade)

        # Generate captions with CTA probability
        captions = caption_gen.generate_variants(
            vision_description=trade_desc,
            tone=tone,
            trade=trade,
            count=5,
            cta_probability=cta_probability
        )

        # Generate companion images
        generated_images = image_gen.generate_pool_images(
            description=trade_desc,
            count=2
        )

        return CaptionResponse(
            vision_description=trade_desc,
            captions=captions,
            generated_images=generated_images,
            all_valid=True
        )

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Content generation failed")


@router.get("/health")
async def health_check():
    return {"status": "healthy", "services": {"vision": "ready", "captions": "ready", "images": "ready"}}
