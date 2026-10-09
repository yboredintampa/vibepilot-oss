# backend/routes/admin_ai.py
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional

from backend.security import require_admin
from backend.services.analytics_service import AnalyticsService

# Admin-only: this data is used for AI training and must never be public.
router = APIRouter(prefix="/admin", tags=["admin-ai"], dependencies=[Depends(require_admin)])
analytics_service = AnalyticsService()


@router.get("/ai-learning-data")
async def get_ai_learning_data(
    user_id: Optional[str] = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Feed high-performing posts to AI for learning
    Returns top captions with engagement metrics
    """
    try:
        top_posts = analytics_service.get_top_performing_posts(user_id, limit)
        
        # Format for AI training
        training_data = [{
            "caption": post.get("review_text", ""),  # In production, fetch actual caption
            "rating": post["rating"],
            "job_id": post["job_id"],
            "performance_score": post["rating"] / 5.0,  # Normalized 0-1
            "timestamp": post["timestamp"]
        } for post in top_posts]
        
        return JSONResponse({
            "success": True,
            "count": len(training_data),
            "data": training_data,
            "message": "Top-performing content for AI training"
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/learning-stats")
async def get_learning_stats():
    """
    Show AI learning dashboard stats
    """
    try:
        # Mock stats for now - in production, track actual learning metrics
        return JSONResponse({
            "total_training_examples": 907,
            "high_performing_examples": 127,
            "learning_enabled": True,
            "last_update": "2026-01-03T20:30:00Z",
            "avg_post_rating": 4.2,
            "top_categories": ["pools", "hvac", "electrical"]
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")
