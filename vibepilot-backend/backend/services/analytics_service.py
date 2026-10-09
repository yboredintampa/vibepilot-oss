# backend/services/analytics_service.py
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class AnalyticsService:
    """
    Track QR analytics (scans, reviews, conversions)
    For MVP: Uses JSON file storage
    Production: Move to database
    """
    
    def __init__(self, storage_path: str = ""):
        storage_path = storage_path or os.getenv("VP_ANALYTICS_PATH", "/tmp/vibepilot_analytics.json")
        self.storage_path = Path(storage_path)
        self._ensure_storage()
    
    def _ensure_storage(self):
        """Create storage file if it doesn't exist"""
        if not self.storage_path.exists():
            self.storage_path.write_text(json.dumps({
                "scans": [],
                "reviews": [],
                "stats": {}
            }))
    
    def _load_data(self) -> Dict:
        """Load analytics data"""
        try:
            return json.loads(self.storage_path.read_text())
        except:
            return {"scans": [], "reviews": [], "stats": {}}
    
    def _save_data(self, data: Dict):
        """Save analytics data"""
        self.storage_path.write_text(json.dumps(data, indent=2))
    
    def log_scan(self, user_id: str, job_id: str, token: str):
        """Log a QR scan"""
        data = self._load_data()
        data["scans"].append({
            "user_id": user_id,
            "job_id": job_id,
            "token_hash": token[:16],
            "timestamp": datetime.now().isoformat(),
            "event": "scan"
        })
        self._save_data(data)
    
    def log_review_submission(self, user_id: str, job_id: str, rating: int, token: str, customer_email: Optional[str] = None):
        """Log a review submission with customer email for reputation tracking"""
        data = self._load_data()
        data["reviews"].append({
            "user_id": user_id,
            "job_id": job_id,
            "token_hash": token[:16],
            "rating": rating,
            "customer_email": customer_email,
            "timestamp": datetime.now().isoformat(),
            "event": "review_submitted"
        })
        self._save_data(data)
    
    def get_user_stats(self, user_id: str) -> Dict:
        """Get analytics for a specific user"""
        data = self._load_data()
        
        user_scans = [s for s in data["scans"] if s["user_id"] == user_id]
        user_reviews = [r for r in data["reviews"] if r["user_id"] == user_id]
        
        total_scans = len(user_scans)
        total_reviews = len(user_reviews)
        conversion_rate = (total_reviews / total_scans * 100) if total_scans > 0 else 0
        
        # Calculate average rating
        avg_rating = 0
        if user_reviews:
            avg_rating = sum(r["rating"] for r in user_reviews) / len(user_reviews)
        
        return {
            "total_scans": total_scans,
            "total_reviews": total_reviews,
            "conversion_rate": round(conversion_rate, 1),
            "average_rating": round(avg_rating, 1) if avg_rating else None,
            "recent_scans": user_scans[-5:],
            "recent_reviews": user_reviews[-5:]
        }
    
    def get_customer_reputation(self, customer_email: str) -> Dict:
        """
        Get reputation score for a customer based on their review history
        This enables two-sided verification - customers build reputation too!
        """
        data = self._load_data()
        
        # Find all reviews from this customer
        customer_reviews = [
            r for r in data["reviews"] 
            if r.get("customer_email") == customer_email
        ]
        
        if not customer_reviews:
            return {
                "email": customer_email,
                "total_reviews": 0,
                "verified_jobs": 0,
                "reputation_score": 0,
                "average_rating": None,
                "status": "new"
            }
        
        total_reviews = len(customer_reviews)
        avg_rating = sum(r["rating"] for r in customer_reviews) / total_reviews
        
        # Calculate reputation score (0-100)
        # Formula: (avg_rating / 5) * 100, boosted by review count
        base_score = (avg_rating / 5) * 100
        review_bonus = min(total_reviews * 2, 20)  # Max 20 bonus points
        reputation_score = min(base_score + review_bonus, 100)
        
        # Determine status
        if reputation_score >= 90:
            status = "excellent"
        elif reputation_score >= 75:
            status = "good"
        elif reputation_score >= 60:
            status = "fair"
        else:
            status = "caution"
        
        return {
            "email": customer_email,
            "total_reviews": total_reviews,
            "verified_jobs": total_reviews,
            "average_rating": round(avg_rating, 1),
            "reputation_score": round(reputation_score, 1),
            "status": status,
            "recent_reviews": customer_reviews[-3:]  # Last 3
        }

    def log_tech_rating(self, tech_id: str, customer_email: str, ratings: dict, note: str = ""):
        """
        Tech rates customer (2-way reputation)
        ratings = {
            "payment_speed": 1-5,
            "communication": 1-5, 
            "property_respect": 1-5,
            "overall": 1-5
        }
        """
        data = self._load_data()
        
        if "tech_ratings" not in data:
            data["tech_ratings"] = []
        
        data["tech_ratings"].append({
            "tech_id": tech_id,
            "customer_email": customer_email,
            "ratings": ratings,
            "note": note,
            "timestamp": datetime.now().isoformat(),
            "event": "tech_rated_customer"
        })
        
        self._save_data(data)
        
        # Return Vibe Points (10 points per rating)
        return {"vibe_points": 10, "total_ratings": len([r for r in data["tech_ratings"] if r["tech_id"] == tech_id])}
    
    def get_customer_aggregate(self, customer_email: str) -> Dict:
        """
        Get aggregate customer ratings from ALL techs (anonymous)
        This is the cross-vertical intelligence - no names/sources
        """
        data = self._load_data()
        
        customer_ratings = [
            r for r in data.get("tech_ratings", [])
            if r["customer_email"] == customer_email
        ]
        
        if not customer_ratings:
            return {
                "email": customer_email,
                "total_ratings": 0,
                "aggregate_score": None,
                "status": "new_customer",
                "categories": {},
                "notes_summary": []
            }
        
        # Calculate averages
        total = len(customer_ratings)
        categories = {
            "payment_speed": sum(r["ratings"]["payment_speed"] for r in customer_ratings) / total,
            "communication": sum(r["ratings"]["communication"] for r in customer_ratings) / total,
            "property_respect": sum(r["ratings"]["property_respect"] for r in customer_ratings) / total,
            "overall": sum(r["ratings"]["overall"] for r in customer_ratings) / total
        }
        
        aggregate = sum(categories.values()) / len(categories)
        
        # Collect notes (no tech names)
        notes = [r["note"] for r in customer_ratings if r["note"]]
        
        # Status
        if aggregate >= 4.5:
            status = "excellent"
        elif aggregate >= 3.5:
            status = "good"
        elif aggregate >= 2.5:
            status = "fair"
        else:
            status = "caution"
        
        return {
            "email": customer_email,
            "total_ratings": total,
            "aggregate_score": round(aggregate, 2),
            "status": status,
            "categories": {k: round(v, 2) for k, v in categories.items()},
            "notes_summary": notes[:5]  # Last 5 notes
        }
    
    def get_top_performing_posts(self, user_id: str = None, limit: int = 20) -> List[Dict]:
        """
        Get top-performing posts for AI learning
        Returns posts with high engagement, reviews, conversions
        """
        data = self._load_data()
        
        # For now, return posts with 4+ star reviews
        # In production, this would query actual post engagement data
        top_reviews = [
            r for r in data.get("reviews", [])
            if r["rating"] >= 4
        ]
        
        if user_id:
            top_reviews = [r for r in top_reviews if r["user_id"] == user_id]
        
        return sorted(top_reviews, key=lambda x: x["rating"], reverse=True)[:limit]
