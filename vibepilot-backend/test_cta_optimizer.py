# test_cta_optimizer.py
from backend.services.cta_optimizer import CTAOptimizer

optimizer = CTAOptimizer()

# Sunny Side Pool Co. (3x daily = 21/week)
print("=== SUNNY SIDE POOL CO. ===")
print("Posting: 3x daily (8am, 1pm, 6pm) = 21 posts/week\n")

strategies = optimizer.get_all_strategies(posts_per_week=21)

for strategy, data in strategies.items():
    print(f"{strategy.upper()}:")
    print(f"  Recommended: {data['recommended_ctas']} CTAs/week")
    print(f"  CTA Rate: {data['cta_rate']}%")
    print(f"  Rationale: {data['rationale']}")
    print()

# Validate custom setting
print("=== CUSTOM VALIDATION ===")
result = optimizer.validate_cta_settings(posts_per_week=21, ctas_per_week=7)
print(f"7 CTAs/week: {result}")
print()

result = optimizer.validate_cta_settings(posts_per_week=21, ctas_per_week=15)
print(f"15 CTAs/week: {result}")
