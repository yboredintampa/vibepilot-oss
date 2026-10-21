from fastapi import APIRouter, Depends
from datetime import datetime, timezone
import os
from .database import get_db
from .security import require_admin
from sqlalchemy import text

# Business metrics are admin-only.
router = APIRouter(dependencies=[Depends(require_admin)])

@router.get("/command-center/json")  # Fixed path!
async def command_center_json(db = Depends(get_db)):
    # Get real data from PostgreSQL
    try:
        total_users = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        active_subs = db.execute(text("SELECT COUNT(*) FROM users WHERE active = true")).scalar() or 0
        total_posts = db.execute(text("SELECT COUNT(*) FROM posts")).scalar() or 0
    except Exception:
        total_users = 0
        active_subs = 0
        total_posts = 0
    
    stripe_total = float(os.getenv("STRIPE_LIFETIME_GROSS", "0"))
    health_fund = round(0.085 * stripe_total, 2)
    life_fund = round(0.015 * stripe_total, 2)
    farm_fund = round(0.20 * stripe_total, 2)
    acres = int(farm_fund / 5000)
    
    remaining = 300000 - total_users
    days_estimate = f"~{int(remaining / max(1, total_users/30))} days" if total_users > 0 else "Awaiting first user"
    
    return {
        "total_users": total_users,
        "active_subscribers": active_subs,
        "total_posts": total_posts,
        "stripe_lifetime_gross_usd": stripe_total,
        "health_fund_usd": health_fund,
        "life_fund_usd": life_fund,
        "farm_fund_usd": farm_fund,
        "acres_purchasable": acres,
        "countdown_to_300k": remaining,
        "estimated_days_to_300k": days_estimate,
        "current_time_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    }
