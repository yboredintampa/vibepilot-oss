"""
Command Center dashboard - metrics and KPIs for VibePilot
"""
from fastapi import APIRouter, Depends

from vp_security import require_admin
from datetime import datetime, timezone
import os

# Defense in depth: also protected where the router is mounted.
router = APIRouter(dependencies=[Depends(require_admin)])

@router.get("/json")
async def command_center_json():
    """
    Returns JSON data for the command center dashboard.
    Shows basic metrics (for now, mostly placeholder data until database is connected)
    """
    
    # For now, return placeholder data since we don't have database access working yet
    # TODO: Connect to database once we figure out the right way to import it
    
    total_users = 0
    active_subs = 0
    
    # Stripe lifetime total (from env var)
    stripe_total = float(os.getenv("STRIPE_LIFETIME_GROSS", "0"))
    
    # Fund allocations (based on charter percentages)
    health_fund = 0.085 * stripe_total  # 8.5% to health
    life_fund = 0.015 * stripe_total     # 1.5% to life insurance
    farm_fund = 0.20 * stripe_total      # 20% to regenerative farms
    
    # Countdown to 300K handover trigger
    remaining = max(0, 300000 - active_subs)
    
    # Estimate days to 300K (assuming 3% monthly growth)
    if remaining == 0:
        days_estimate = "Handover imminent"
    else:
        if active_subs > 0:
            monthly_growth = max(1, active_subs * 0.03)
            months_remaining = remaining / monthly_growth
            days_estimate = f"~{max(1, int(months_remaining * 30))} days"
        else:
            days_estimate = "Awaiting first user"
    
    return {
        "total_users": total_users,
        "active_subscribers": active_subs,
        "stripe_lifetime_gross_usd": stripe_total,
        "health_fund_usd": round(health_fund, 2),
        "life_fund_usd": round(life_fund, 2),
        "farm_fund_usd": round(farm_fund, 2),
        "acres_purchasable": int(farm_fund / 5000) if farm_fund > 0 else 0,
        "countdown_to_300k": remaining,
        "estimated_days_to_300k": days_estimate,
        "tiers": {"starter": 0},  # Placeholder
        "current_time_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "note": "Database connection pending - showing placeholder metrics"
    }
