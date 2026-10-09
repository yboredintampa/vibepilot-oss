# backend/services/cta_optimizer.py
from typing import Dict, Literal

Strategy = Literal["conservative", "balanced", "aggressive"]


class CTAOptimizer:
    """Smart CTA frequency calculator based on posting schedule"""
    
    def __init__(self):
        self.strategies = {
            "conservative": {
                "min_rate": 0.20,
                "max_rate": 0.25,
                "description": "Build trust and relationships first",
            },
            "balanced": {
                "min_rate": 0.28,
                "max_rate": 0.33,
                "description": "Recommended for most businesses",
            },
            "aggressive": {
                "min_rate": 0.50,
                "max_rate": 0.60,
                "description": "Maximum lead generation",
            }
        }
    
    def calculate_recommended_ctas(
        self, 
        posts_per_week: int, 
        strategy: Strategy = "balanced"
    ) -> Dict:
        """
        Calculate optimal CTA frequency based on posting volume
        
        Args:
            posts_per_week: Total posts planned per week
            strategy: "conservative", "balanced", or "aggressive"
        
        Returns:
            Dictionary with CTA recommendations and rationale
        """
        posts_per_day = posts_per_week / 7
        max_ctas_per_week = min(7, posts_per_week)  # Never more than 1/day
        
        config = self.strategies.get(strategy, self.strategies["balanced"])
        
        # Calculate recommended range
        min_ctas = int(posts_per_week * config["min_rate"])
        max_ctas = int(posts_per_week * config["max_rate"])
        
        # Apply "max 1 per day" constraint
        min_ctas = min(min_ctas, max_ctas_per_week)
        max_ctas = min(max_ctas, max_ctas_per_week)
        
        # Recommended is middle of range
        recommended = (min_ctas + max_ctas) // 2
        
        # Calculate actual rate
        cta_rate = round(recommended / posts_per_week * 100, 1) if posts_per_week > 0 else 0
        
        return {
            "posts_per_week": posts_per_week,
            "posts_per_day": round(posts_per_day, 1),
            "strategy": strategy,
            "strategy_description": config["description"],
            "min_ctas": min_ctas,
            "max_ctas": max_ctas,
            "recommended_ctas": recommended,
            "cta_rate": cta_rate,
            "max_ctas_per_day": 1,
            "rationale": self._generate_rationale(
                posts_per_week, 
                recommended, 
                cta_rate, 
                strategy
            )
        }
    
    def _generate_rationale(
        self, 
        posts_per_week: int, 
        recommended_ctas: int, 
        cta_rate: float, 
        strategy: str
    ) -> str:
        """Generate human-readable explanation"""
        
        if posts_per_week >= 21:
            frequency = "3+ times daily"
        elif posts_per_week >= 14:
            frequency = "2+ times daily"
        elif posts_per_week >= 7:
            frequency = "daily"
        else:
            frequency = f"{posts_per_week}x per week"
        
        return (
            f"Based on {frequency} posting ({posts_per_week} posts/week), "
            f"{strategy} strategy recommends {recommended_ctas} CTAs/week "
            f"(~{cta_rate}% of posts) with max 1 CTA per day."
        )
    
    def get_all_strategies(self, posts_per_week: int) -> Dict[str, Dict]:
        """Get recommendations for all strategies"""
        return {
            strategy: self.calculate_recommended_ctas(posts_per_week, strategy)
            for strategy in ["conservative", "balanced", "aggressive"]
        }
    
    def validate_cta_settings(
        self, 
        posts_per_week: int, 
        ctas_per_week: int
    ) -> Dict:
        """Validate user's custom CTA settings"""
        
        max_allowed = min(7, posts_per_week)
        
        if ctas_per_week > max_allowed:
            return {
                "valid": False,
                "error": f"Maximum {max_allowed} CTAs/week allowed (1 per day rule)",
                "suggestion": max_allowed
            }
        
        if ctas_per_week > posts_per_week:
            return {
                "valid": False,
                "error": "Cannot have more CTAs than total posts",
                "suggestion": posts_per_week
            }
        
        # Calculate what strategy this matches
        rate = ctas_per_week / posts_per_week if posts_per_week > 0 else 0
        
        if rate <= 0.25:
            matched_strategy = "conservative"
        elif rate <= 0.40:
            matched_strategy = "balanced"
        else:
            matched_strategy = "aggressive"
        
        return {
            "valid": True,
            "ctas_per_week": ctas_per_week,
            "cta_rate": round(rate * 100, 1),
            "matched_strategy": matched_strategy,
            "max_ctas_per_day": 1
        }
