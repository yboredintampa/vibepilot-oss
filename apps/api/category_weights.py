from typing import Dict

from fastapi import APIRouter, Depends

from vp_security import require_admin
from pydantic import BaseModel

router = APIRouter(
    prefix="/category-weights",
    tags=["category-weights"],
    dependencies=[Depends(require_admin)],
)


class CategoryWeights(BaseModel):
    authoritative: int = 0
    blog: int = 0
    comedic: int = 0
    confrontational: int = 0
    educational: int = 0
    meme: int = 0
    persuasive: int = 0
    realistic: int = 0


# In-memory store for now; swap to DB later.
_TENANT_WEIGHTS: Dict[str, CategoryWeights] = {}


def _normalize(weights: CategoryWeights) -> Dict[str, float]:
    data = weights.model_dump()
    total = sum(data.values())
    if total <= 0:
        return {k: 0.0 for k in data}
    return {k: v / total for k, v in data.items()}


DEFAULT_WEIGHTS = {
    "authoritative": 5,
    "blog": 0,
    "comedic": 3,
    "confrontational": 0,
    "educational": 40,
    "meme": 7,
    "persuasive": 5,
    "realistic": 40,
}


@router.get("/tenants/{tenant_id}")
def get_category_weights(tenant_id: str):
    """
    Get weights for a tenant.

    For now, if the tenant has no stored weights and its id contains
    'pure-water-professionals', we seed it with your default mix.
    Otherwise, default to all zeros.
    """
    weights = _TENANT_WEIGHTS.get(tenant_id)

    if weights is None:
        if "pure-water-professionals" in tenant_id:
            weights = CategoryWeights(**DEFAULT_WEIGHTS)
        else:
            weights = CategoryWeights()
        _TENANT_WEIGHTS[tenant_id] = weights

    return {
        "tenant_id": tenant_id,
        "weights": weights,
        "normalized": _normalize(weights),
    }


@router.put("/tenants/{tenant_id}")
def set_category_weights(tenant_id: str, payload: CategoryWeights):
    """
    Upsert weights for a tenant.
    """
    _TENANT_WEIGHTS[tenant_id] = payload
    return {
        "tenant_id": tenant_id,
        "weights": payload,
        "normalized": _normalize(payload),
    }
