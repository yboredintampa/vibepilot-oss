# backend/routes/qr_routes.py
import html
import json
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.security import client_ip, rate_limit, require_admin

from backend.services.qr_service import QRReputationService
from backend.services.analytics_service import AnalyticsService
from backend.services.pdf_service import PDFService
from fastapi.responses import Response
from backend.services.email_service import EmailService


router = APIRouter(prefix="/qr", tags=["qr-reputation"])
qr_service = QRReputationService()
analytics_service = AnalyticsService()
pdf_service = PDFService()
email_service = EmailService()

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")

# Display name used on public pages until per-user business profiles are stored in the DB.
DEMO_BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Sunny Side Bakery")


def _check_id(value: str, field: str = "user_id") -> str:
    if not _ID_RE.match(value or ""):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


def _check_email(value: str) -> str:
    if not _EMAIL_RE.match(value or "") or len(value) > 320:
        raise HTTPException(status_code=400, detail="Invalid email")
    return value.lower()


class ReviewSubmission(BaseModel):
    token: str = Field(..., max_length=400)
    rating: int = Field(..., ge=1, le=5)  # 1-5 stars
    review_text: Optional[str] = Field(None, max_length=2000)
    customer_name: Optional[str] = Field(None, max_length=120)
    customer_email: Optional[str] = Field(None, max_length=320)


@router.get("/generate/{user_id}", dependencies=[Depends(require_admin)])
async def generate_qr(user_id: str, job_id: Optional[str] = None):
    """Generate a QR code for a specific user/job (admin only)"""
    _check_id(user_id)
    if job_id is not None:
        _check_id(job_id, "job_id")
    try:
        qr_data = qr_service.generate_qr_code(user_id, job_id)
        return JSONResponse(qr_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not generate QR code")


@router.get("/printable/{user_id}", dependencies=[Depends(require_admin)])
async def generate_printable(user_id: str, business_name: str = "Your Business"):
    """Generate a printable QR code for trucks/invoices (admin only)"""
    _check_id(user_id)
    business_name = business_name[:120]
    try:
        qr_data = qr_service.create_printable_qr(user_id, business_name)
        return JSONResponse(qr_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not generate QR code")


@router.post("/submit-review")
async def submit_review(review: ReviewSubmission, request: Request):
    """Submit a verified review (public; protected by signed token + rate limit)"""
    rate_limit(f"submit-review:{client_ip(request)}", limit=10, window_seconds=3600)
    if review.customer_email:
        review.customer_email = _check_email(review.customer_email)
    # Verify token
    verification = qr_service.verify_token(review.token)
    
    if not verification["valid"]:
        raise HTTPException(status_code=400, detail=verification["error"])
    
    # Log analytics
    analytics_service.log_review_submission(
        verification["user_id"],
        verification["job_id"],
        review.rating,
        review.token,
        review.customer_email
    )
    # Send email notification
    # TODO: Look up the business owner's email from the database.
    user_email = os.getenv("REVIEW_NOTIFICATION_EMAIL", "")
    if user_email:
        email_service.send_review_notification(
            to_email=user_email,
            business_name=DEMO_BUSINESS_NAME,  # TODO: Get from DB
            rating=review.rating,
            review_text=review.review_text,
            customer_name=review.customer_name,
            job_id=verification["job_id"],
        )


    
    # Store review (mock for now, will use DB later)
    review_data = {
        "id": f"review_{datetime.now().timestamp()}",
        "user_id": verification["user_id"],
        "job_id": verification["job_id"],
        "rating": review.rating,
        "review_text": review.review_text,
        "customer_name": review.customer_name,
        "customer_email": review.customer_email,
        "verified": True,
        "timestamp": datetime.now().isoformat(),
        "verification_token": review.token
    }
    
    # TODO: Store in database
    
    return JSONResponse({
        "success": True,
        "message": "Review submitted successfully!",
        "discount_code": "VERIFIED10",  # 10% off next service
        "review_id": review_data["id"]
    })


@router.get("/review/{token}", response_class=HTMLResponse)
async def review_landing_page(token: str, request: Request):
    """Landing page customers see when they scan QR"""
    rate_limit(f"review-page:{client_ip(request)}", limit=60, window_seconds=60)
    # Verify token
    verification = qr_service.verify_token(token)
    
    # Log scan (even if invalid - for analytics)
    if verification["valid"]:
        analytics_service.log_scan(
            verification["user_id"],
            verification["job_id"],
            token
        )
    
    if not verification["valid"]:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><body style="text-align:center;padding:50px;font-family:sans-serif;">
        <h1>❌ Invalid Review Link</h1>
        <p>{html.escape(str(verification['error']))}</p>
        </body></html>
        """)
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Leave a Verified Review</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gradient-to-br from-purple-900 via-gray-900 to-black min-h-screen flex items-center justify-center p-4">
        <div class="max-w-md w-full bg-gray-800 rounded-2xl shadow-2xl p-8 border border-purple-500">
            <div class="text-center mb-6">
                <div class="text-6xl mb-4">⭐</div>
                <h1 class="text-2xl font-bold text-white mb-2">Leave a Verified Review</h1>
                <p class="text-gray-400 text-sm">Get 10% off your next service!</p>
            </div>
            
            <form id="reviewForm" class="space-y-4">
                <!-- Star Rating -->
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Rating</label>
                    <div class="flex gap-2 justify-center" id="starRating">
                        <button type="button" class="star text-4xl text-gray-600 hover:text-yellow-400 transition" data-rating="1">★</button>
                        <button type="button" class="star text-4xl text-gray-600 hover:text-yellow-400 transition" data-rating="2">★</button>
                        <button type="button" class="star text-4xl text-gray-600 hover:text-yellow-400 transition" data-rating="3">★</button>
                        <button type="button" class="star text-4xl text-gray-600 hover:text-yellow-400 transition" data-rating="4">★</button>
                        <button type="button" class="star text-4xl text-gray-600 hover:text-yellow-400 transition" data-rating="5">★</button>
                    </div>
                    <input type="hidden" id="ratingValue" value="0">
                </div>
                
                <!-- Review Text -->
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Your Review (Optional)</label>
                    <textarea id="reviewText" rows="4" class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:border-purple-500 focus:outline-none" placeholder="Tell us about your experience..."></textarea>
                </div>
                
                <!-- Name -->
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Your Name (Optional)</label>
                    <input type="text" id="customerName" class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:border-purple-500 focus:outline-none" placeholder="John Doe">
                </div>
                
                <!-- Email -->
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Email for Discount Code</label>
                    <input type="email" id="customerEmail" required class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:border-purple-500 focus:outline-none" placeholder="your@email.com">
                </div>
                
                <!-- Submit -->
                <button type="submit" class="w-full bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white font-semibold py-3 rounded-lg transition">
                    Submit Review & Get Discount
                </button>
            </form>
            
            <div id="successMessage" class="hidden mt-6 p-4 bg-green-900 bg-opacity-50 border border-green-500 rounded-lg">
                <p class="text-green-200 text-center font-semibold mb-2">✅ Review Submitted!</p>
                <p class="text-green-300 text-center text-sm">Your discount code: <span id="discountCode" class="font-mono font-bold"></span></p>
            </div>
        </div>
        
        <script>
            let selectedRating = 0;
            
            // Star rating interaction
            document.querySelectorAll('.star').forEach(star => {{
                star.addEventListener('click', (e) => {{
                    e.preventDefault();
                    selectedRating = parseInt(star.dataset.rating);
                    document.getElementById('ratingValue').value = selectedRating;
                    
                    // Update star colors
                    document.querySelectorAll('.star').forEach((s, i) => {{
                        if (i < selectedRating) {{
                            s.classList.remove('text-gray-600');
                            s.classList.add('text-yellow-400');
                        }} else {{
                            s.classList.remove('text-yellow-400');
                            s.classList.add('text-gray-600');
                        }}
                    }});
                }});
            }});
            
            // Form submission
            document.getElementById('reviewForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                
                if (selectedRating === 0) {{
                    alert('Please select a rating');
                    return;
                }}
                
                const reviewData = {{
                    token: {html.escape(json.dumps(token), quote=False)},
                    rating: selectedRating,
                    review_text: document.getElementById('reviewText').value,
                    customer_name: document.getElementById('customerName').value,
                    customer_email: document.getElementById('customerEmail').value
                }};
                
                try {{
                    const response = await fetch('/qr/submit-review', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(reviewData)
                    }});
                    
                    const result = await response.json();
                    
                    if (result.success) {{
                        document.getElementById('reviewForm').classList.add('hidden');
                        document.getElementById('successMessage').classList.remove('hidden');
                        document.getElementById('discountCode').textContent = result.discount_code;
                    }}
                }} catch (error) {{
                    alert('Error submitting review. Please try again.');
                }}
            }});
        </script>
    </body>
    </html>
    """)

@router.get("/stats/{user_id}", dependencies=[Depends(require_admin)])
async def get_user_analytics(user_id: str):
    """Get analytics for a user (admin only)"""
    _check_id(user_id)
    try:
        stats = analytics_service.get_user_stats(user_id)
        return JSONResponse(stats)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not load stats")


@router.get("/showcase/{user_id}", response_class=HTMLResponse)
async def review_showcase(user_id: str, request: Request):
    """Public showcase of verified reviews"""
    rate_limit(f"showcase:{client_ip(request)}", limit=60, window_seconds=60)
    _check_id(user_id)
    stats = analytics_service.get_user_stats(user_id)

    # Get user info (mock for now)
    business_name = html.escape(DEMO_BUSINESS_NAME)  # TODO: Get from DB
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en" class="bg-gray-950">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{business_name} - Verified Reviews</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="text-gray-100 min-h-screen">
        <div class="gradient-purple py-12">
            <div class="max-w-4xl mx-auto px-6 text-center">
                <h1 class="text-4xl font-bold mb-4">{business_name}</h1>
                <div class="text-6xl mb-4">⭐ {html.escape(str(stats['average_rating'] or 'N/A'))}</div>
                <p class="text-lg text-purple-100">{stats['total_reviews']} Verified Reviews</p>
                <div class="mt-4 inline-block bg-green-600 px-4 py-2 rounded-lg">
                    <span class="font-semibold">✓ Cryptographically Verified</span>
                </div>
            </div>
        </div>
        
        <div class="max-w-4xl mx-auto px-6 py-12">
            <h2 class="text-2xl font-bold mb-6">Recent Reviews</h2>
            
            <div class="space-y-6">
                {chr(10).join([f'''
                <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
                    <div class="flex items-center gap-4 mb-4">
                        <div class="text-3xl">{'⭐' * int(review['rating'])}</div>
                        <div class="flex-1">
                            <div class="text-sm text-gray-400">{html.escape(str(review['timestamp'])[:10])}</div>
                            <div class="text-xs text-green-400">✓ Verified Job</div>
                        </div>
                    </div>
                    <p class="text-gray-300">Job ID: {html.escape(str(review['job_id']))}</p>
                </div>
                ''' for review in stats['recent_reviews'][:10]])}
            </div>
            
            <div class="mt-12 text-center">
                <div class="inline-block bg-gray-800 rounded-xl p-6 border border-purple-700">
                    <p class="text-sm text-gray-400 mb-2">Powered by</p>
                    <div class="text-2xl font-bold text-purple-400">🟣 VibePilot</div>
                    <p class="text-xs text-gray-500 mt-2">Cryptographically Verified Reviews</p>
                </div>
            </div>
        </div>
        
        <style>
            .gradient-purple {{ background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); }}
        </style>
    </body>
    </html>
    """)

@router.get("/sticker-sheet/{user_id}", dependencies=[Depends(require_admin)])
async def generate_sticker_sheet(user_id: str, business_name: str = "Your Business"):
    """Generate printable 8-up sticker sheet PDF (admin only)"""
    _check_id(user_id)
    business_name = business_name[:120]
    try:
        # Generate QR code
        qr_data = qr_service.create_printable_qr(user_id, business_name)
        
        # Create PDF
        pdf_bytes = pdf_service.create_sticker_sheet(
            qr_data['qr_code_base64'],
            business_name
        )
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=vibepilot-qr-stickers.pdf"
            }
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Could not generate sticker sheet")

@router.get("/customer-reputation", dependencies=[Depends(require_admin)])
async def get_customer_reputation(email: str):
    """Get reputation score for a customer (two-sided verification, admin only)"""
    email = _check_email(email)
    try:
        reputation = analytics_service.get_customer_reputation(email)
        return JSONResponse(reputation)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


class TechRating(BaseModel):
    customer_email: str = Field(..., max_length=320)
    payment_speed: int = Field(..., ge=1, le=5)
    communication: int = Field(..., ge=1, le=5)
    property_respect: int = Field(..., ge=1, le=5)
    overall: int = Field(..., ge=1, le=5)
    note: Optional[str] = Field("", max_length=1000)
    tech_id: str = Field(..., max_length=128)


@router.post("/rate-customer", dependencies=[Depends(require_admin)])
async def tech_rate_customer(rating: TechRating):
    """
    Tech rates customer (2-way reputation system, admin/internal only)
    Private to network, anonymous aggregate
    """
    rating.customer_email = _check_email(rating.customer_email)
    _check_id(rating.tech_id, "tech_id")
    try:
        ratings = {
            "payment_speed": rating.payment_speed,
            "communication": rating.communication,
            "property_respect": rating.property_respect,
            "overall": rating.overall
        }
        
        result = analytics_service.log_tech_rating(
            rating.tech_id,
            rating.customer_email,
            ratings,
            rating.note
        )
        
        # TODO: Mint on-chain hash (Solana integration)
        
        return JSONResponse({
            "success": True,
            "message": "Customer rated successfully",
            "vibe_points": result["vibe_points"],
            "total_ratings": result["total_ratings"],
            "note": "Rating is private to VibePilot network"
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/customer-aggregate/{email}", dependencies=[Depends(require_admin)])
async def get_customer_aggregate_ratings(email: str):
    """
    Get anonymous aggregate customer ratings (cross-vertical intelligence, admin only)
    No tech names/sources - just the truth from the network
    """
    email = _check_email(email)
    try:
        aggregate = analytics_service.get_customer_aggregate(email)
        return JSONResponse(aggregate)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")
