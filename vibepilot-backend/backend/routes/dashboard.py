# backend/routes/dashboard.py
import os

from fastapi import APIRouter, Request, HTTPException, Depends

from backend.security import require_admin
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Dict, List

# Every dashboard page requires admin authentication until real per-user auth exists.
router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_admin)])

# Templates
templates = Jinja2Templates(directory="backend/templates")


# Mock user data (will replace with DB later)
def get_current_user(request: Request) -> Dict:
    """
    Get current user from session/auth
    For now, return mock user data
    Later: Replace with real auth
    """
    return {
        "id": "user_001",
        "business_name": os.getenv("BUSINESS_NAME", "Sunny Side Bakery"),
        "trade": "bakery",
        "posting_schedule": {"8am": True, "1pm": True, "6pm": True},
        "cta_strategy": "aggressive",
        "ctas_per_week": 7,
    }


def get_user_posts(user_id: str) -> List[Dict]:
    """
    Get user's posts from database
    For now, return mock data
    """
    today = datetime.now()

    return [
        {
            "id": "post_001",
            "scheduled_time": today.replace(hour=8, minute=0).isoformat(),
            "status": "scheduled",
            "caption": "Fresh sourdough comes out of the oven at 7am every day.",
            "image_url": "/static/placeholder.svg",
            "tone": "educational",
            "has_cta": False,
            "likes": 0,
            "comments": 0,
        },
        {
            "id": "post_002",
            "scheduled_time": today.replace(hour=13, minute=0).isoformat(),
            "status": "scheduled",
            "caption": "Before: plain dough. After: golden croissants!",
            "image_url": "/static/placeholder.svg",
            "tone": "professional",
            "has_cta": False,
            "likes": 0,
            "comments": 0,
        },
        {
            "id": "post_003",
            "scheduled_time": today.replace(hour=18, minute=0).isoformat(),
            "status": "scheduled",
            "caption": "Holiday pie preorders are open - reserve yours today!",
            "image_url": "/static/placeholder.svg",
            "tone": "promotional",
            "has_cta": True,
            "likes": 0,
            "comments": 0,
        },
    ]

def get_user_analytics(user_id: str) -> Dict:
    """
    Get user's analytics from database
    For now, return mock data
    """
    return {
        "this_week": {
            "posts": 21,
            "likes": 847,
            "comments": 93,
            "shares": 12,
            "saves": 34,
            "dms": 12,
            "bookings": 4,
            "revenue": 1680.00,
        },
        "last_week": {
            "posts": 21,
            "likes": 712,
            "comments": 78,
            "shares": 9,
            "saves": 28,
            "dms": 9,
            "bookings": 3,
            "revenue": 1260.00,
        },
        "top_post": {
            "id": "post_top_001",
            "caption": "Croissant lamination behind the scenes!",
            "likes": 94,
            "comments": 12,
            "bookings": 2,
            "revenue": 840.00,
        },
        "reputation": {
            "score": 4.9,
            "total_reviews": 127,
            "rank": 3,
            "location": "Springfield",
        }
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Main user dashboard - overview page"""
    
    user = get_current_user(request)
    posts = get_user_posts(user["id"])
    analytics = get_user_analytics(user["id"])
    
    # Get today's posts
    today = datetime.now().date()
    todays_posts = [
        p for p in posts 
        if datetime.fromisoformat(p["scheduled_time"]).date() == today
    ]
    
    # Calculate growth
    this_week = analytics["this_week"]
    last_week = analytics["last_week"]
    
    engagement_growth = (
        ((this_week["likes"] + this_week["comments"]) - 
         (last_week["likes"] + last_week["comments"])) / 
        (last_week["likes"] + last_week["comments"]) * 100
        if (last_week["likes"] + last_week["comments"]) > 0 else 0
    )
    
    revenue_growth = (
        (this_week["revenue"] - last_week["revenue"]) / 
        last_week["revenue"] * 100
        if last_week["revenue"] > 0 else 0
    )
    
    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "user": user,
        "todays_posts": todays_posts,
        "analytics": analytics,
        "engagement_growth": round(engagement_growth, 1),
        "revenue_growth": round(revenue_growth, 1),
    })


@router.get("/posts", response_class=HTMLResponse)
async def dashboard_posts(request: Request):
    """Content queue page"""
    user = get_current_user(request)
    posts = get_user_posts(user["id"])
    
    return templates.TemplateResponse(request, "dashboard_posts.html", {
        "request": request,
        "user": user,
        "posts": posts,
    })


@router.get("/analytics", response_class=HTMLResponse)
async def dashboard_analytics(request: Request):
    """Analytics page"""
    user = get_current_user(request)
    analytics = get_user_analytics(user["id"])
    
    return templates.TemplateResponse(request, "dashboard_analytics.html", {
        "request": request,
        "user": user,
        "analytics": analytics,
    })


@router.get("/settings", response_class=HTMLResponse)
async def dashboard_settings(request: Request):
    """Settings page"""
    user = get_current_user(request)
    
    from backend.services.cta_optimizer import CTAOptimizer
    optimizer = CTAOptimizer()
    
    # Calculate posting frequency
    posts_per_day = sum(1 for v in user["posting_schedule"].values() if v)
    posts_per_week = posts_per_day * 7
    
    # Get CTA recommendations
    strategies = optimizer.get_all_strategies(posts_per_week)
    
    return templates.TemplateResponse(request, "dashboard_settings.html", {
        "request": request,
        "user": user,
        "posts_per_week": posts_per_week,
        "strategies": strategies,
    })
