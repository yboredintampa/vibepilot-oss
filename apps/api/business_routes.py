from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator

from vp_security import require_admin

# Admin-only until per-business ownership checks exist.
router = APIRouter(prefix="/api/v1", tags=["business"], dependencies=[Depends(require_admin)])

CategoryName = Literal[
    "authoritative",
    "blog",
    "comedic",
    "confrontational",
    "educational",
    "meme",
    "persuasive",
    "realistic",
]

DOW = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---------------------------
# Pydantic models
# ---------------------------

class BrandTone(BaseModel):
    spice: float = Field(0.5, ge=0.0, le=1.0)
    formality: float = Field(0.5, ge=0.0, le=1.0)
    humor: float = Field(0.5, ge=0.0, le=1.0)


class BusinessSettings(BaseModel):
    business_id: str
    name: Optional[str] = None
    logo_url: Optional[str] = None
    niche: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    climate: Optional[str] = Field(
        default=None, description="e.g. warm, cold, mixed"
    )
    brand_tone: BrandTone = Field(default_factory=BrandTone)
    default_posting_schedule_id: Optional[str] = "default"
    created_at: datetime
    updated_at: datetime


class UpdateBusinessSettings(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    niche: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    climate: Optional[str] = None
    brand_tone: Optional[BrandTone] = None
    default_posting_schedule_id: Optional[str] = None


class CategoryWeightsBody(BaseModel):
    weights: Dict[CategoryName, float]
    auto_normalize: bool = True

    @validator("weights")
    def non_negative(cls, v: Dict[CategoryName, float]):
        for k, w in v.items():
            if w < 0:
                raise ValueError(f"Weight for {k} cannot be negative")
        if not v:
            raise ValueError("At least one category weight is required")
        return v


class CategoryWeightsResponse(BaseModel):
    business_id: str
    weights: Dict[CategoryName, float]
    normalized: bool
    updated_at: datetime


class BoostRule(BaseModel):
    name: str
    days: List[DOW]
    category: CategoryName
    weight_multiplier: float = Field(1.0, gt=0.0)


class Schedule(BaseModel):
    business_id: str
    timezone: str = "UTC"
    daily_post_targets: Dict[DOW, int]
    blog_schedule: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of {day_of_week: DOW, time: 'HH:MM'} items"
    )
    boost_rules: List[BoostRule] = Field(default_factory=list)
    updated_at: datetime

    @validator("daily_post_targets")
    def validate_daily_post_targets(cls, v: Dict[DOW, int]):
        for day, count in v.items():
            if count < 0:
                raise ValueError(f"daily_post_targets[{day}] cannot be negative")
        return v


class PostItem(BaseModel):
    id: str
    business_id: str
    platform: str
    category: CategoryName
    caption: str
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    status: Literal["scheduled", "published", "failed"]
    external_post_id: Optional[str] = None


class PostListResponse(BaseModel):
    items: List[PostItem]
    limit: int
    offset: int
    total: int


class TodayReviewResponse(BaseModel):
    business_id: str
    since: datetime
    until: datetime
    posts: List[PostItem]


class FeedbackFlags(BaseModel):
    off_brand: Optional[bool] = False
    wrong_category: Optional[bool] = False
    bad_image: Optional[bool] = False
    repetitive: Optional[bool] = False


class FeedbackBody(BaseModel):
    business_id: str
    rating: Optional[int] = Field(
        default=None, ge=1, le=5, description="1–5, optional"
    )
    thumb: Optional[Literal["up", "down"]] = None
    flags: Optional[FeedbackFlags] = None
    notes: Optional[str] = None


class FeedbackItem(BaseModel):
    id: str
    post_id: str
    business_id: str
    rating: Optional[int]
    thumb: Optional[Literal["up", "down"]]
    flags: FeedbackFlags
    notes: Optional[str]
    created_at: datetime


class FeedbackResponse(BaseModel):
    ok: bool
    feedback: FeedbackItem


class FeedbackSummaryCategory(BaseModel):
    posts: int
    avg_rating: Optional[float]
    thumbs_up: int
    thumbs_down: int
    flags: FeedbackFlags


class FeedbackSummaryResponse(BaseModel):
    business_id: str
    from_: datetime = Field(alias="from")
    to: datetime
    by_category: Dict[CategoryName, FeedbackSummaryCategory]


class CategoryPlanSlot(BaseModel):
    slot: int
    category: CategoryName


class CategoryPlanResponse(BaseModel):
    business_id: str
    date: date
    planned_categories: List[CategoryPlanSlot]


# ---------------------------
# In-memory stores (for now)
# ---------------------------

business_store: Dict[str, BusinessSettings] = {}
weights_store: Dict[str, CategoryWeightsResponse] = {}
schedule_store: Dict[str, Schedule] = {}
posts_store: Dict[str, PostItem] = {}
feedback_store: Dict[str, FeedbackItem] = {}


def _ensure_business(business_id: str) -> BusinessSettings:
    if business_id not in business_store:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        business_store[business_id] = BusinessSettings(
            business_id=business_id,
            name=None,
            logo_url=None,
            niche=None,
            city=None,
            region=None,
            country=None,
            climate=None,
            created_at=now,
            updated_at=now,
        )
    return business_store[business_id]


# ---------------------------
# Settings endpoints
# ---------------------------

@router.get(
    "/businesses/{business_id}/settings",
    response_model=BusinessSettings,
)
def get_business_settings(business_id: str):
    return _ensure_business(business_id)


@router.patch(
    "/businesses/{business_id}/settings",
    response_model=Dict[str, object],
)
def update_business_settings(
    business_id: str, payload: UpdateBusinessSettings
):
    settings = _ensure_business(business_id)
    data = payload.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(settings, k, v)
    settings.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    business_store[business_id] = settings
    return {"ok": True, "settings": settings}


# ---------------------------
# Category weight endpoints
# ---------------------------

def _normalize_weights(raw: Dict[CategoryName, float]) -> Dict[CategoryName, float]:
    total = sum(raw.values())
    if total == 0:
        # edge case: give everything 1 / N
        n = len(raw)
        return {k: 1.0 / n for k in raw.keys()}
    return {k: w / total for k, w in raw.items()}


@router.get(
    "/businesses/{business_id}/category-weights",
    response_model=CategoryWeightsResponse,
)
def get_category_weights(business_id: str):
    _ensure_business(business_id)
    if business_id not in weights_store:
        # default mix if nothing set yet
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        default_weights: Dict[CategoryName, float] = {
            "authoritative": 0.05,
            "blog": 0.02,
            "comedic": 0.03,
            "confrontational": 0.05,
            "educational": 0.40,
            "meme": 0.05,
            "persuasive": 0.05,
            "realistic": 0.35,
        }
        normalized = _normalize_weights(default_weights)
        weights_store[business_id] = CategoryWeightsResponse(
            business_id=business_id,
            weights=normalized,
            normalized=True,
            updated_at=now,
        )
    return weights_store[business_id]


@router.put(
    "/businesses/{business_id}/category-weights",
    response_model=CategoryWeightsResponse,
)
def set_category_weights(business_id: str, payload: CategoryWeightsBody):
    _ensure_business(business_id)
    raw = payload.weights
    if payload.auto_normalize:
        normalized = _normalize_weights(raw)
        normalized_flag = True
    else:
        total = sum(raw.values())
        if abs(total - 1.0) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Weights must sum to 1.0 (+/- 0.01). Got {total:.3f}",
            )
        normalized = raw
        normalized_flag = False
    res = CategoryWeightsResponse(
        business_id=business_id,
        weights=normalized,
        normalized=normalized_flag,
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    weights_store[business_id] = res
    return res


# ---------------------------
# Schedule endpoints
# ---------------------------

@router.get(
    "/businesses/{business_id}/schedule",
    response_model=Schedule,
)
def get_schedule(business_id: str):
    _ensure_business(business_id)
    if business_id not in schedule_store:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        schedule_store[business_id] = Schedule(
            business_id=business_id,
            timezone="America/New_York",
            daily_post_targets={
                "mon": 3,
                "tue": 3,
                "wed": 3,
                "thu": 3,
                "fri": 3,
                "sat": 2,
                "sun": 2,
            },
            blog_schedule=[
                {"day_of_week": "wed", "time": "10:00"},
                {"day_of_week": "sun", "time": "10:00"},
                {"day_of_week": "fri", "time": "10:00"},
            ],
            boost_rules=[],
            updated_at=now,
        )
    return schedule_store[business_id]


class UpdateScheduleBody(BaseModel):
    timezone: Optional[str] = None
    daily_post_targets: Optional[Dict[DOW, int]] = None
    blog_schedule: Optional[List[Dict[str, str]]] = None
    boost_rules: Optional[List[BoostRule]] = None


@router.put(
    "/businesses/{business_id}/schedule",
    response_model=Dict[str, object],
)
def update_schedule(business_id: str, payload: UpdateScheduleBody):
    sched = get_schedule(business_id)
    data = payload.dict(exclude_unset=True)
    if "timezone" in data:
        sched.timezone = data["timezone"]
    if "daily_post_targets" in data:
        sched.daily_post_targets = data["daily_post_targets"]
    if "blog_schedule" in data:
        sched.blog_schedule = data["blog_schedule"]
    if "boost_rules" in data:
        sched.boost_rules = data["boost_rules"]
    sched.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    schedule_store[business_id] = sched
    return {"ok": True, "schedule": sched}


# ---------------------------
# Posts list + today review
# (these expect some other worker to create posts)
# ---------------------------

@router.get(
    "/businesses/{business_id}/posts",
    response_model=PostListResponse,
)
def list_posts(
    business_id: str,
    status: Optional[str] = Query(default=None, regex="^(scheduled|published|failed)$"),
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = Query(default=None),
    limit: int = 50,
    offset: int = 0,
):
    _ensure_business(business_id)
    all_posts = [
        p for p in posts_store.values() if p.business_id == business_id
    ]
    if status:
        all_posts = [p for p in all_posts if p.status == status]
    if from_:
        all_posts = [
            p for p in all_posts
            if p.published_at is not None and p.published_at >= from_
        ]
    if to:
        all_posts = [
            p for p in all_posts
            if p.published_at is not None and p.published_at <= to
        ]
    total = len(all_posts)
    items = all_posts[offset : offset + limit]
    return PostListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/businesses/{business_id}/posts/today-review",
    response_model=TodayReviewResponse,
)
def today_review(
    business_id: str,
    max_items: int = Query(default=3, ge=1, le=20, alias="max"),
    since: Optional[datetime] = None,
):
    _ensure_business(business_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if since is None:
        since = now - timedelta(days=1)
    until = now

    # naive: all published in [since, until], limit N
    published_posts = [
        p
        for p in posts_store.values()
        if p.business_id == business_id
        and p.status == "published"
        and p.published_at is not None
        and since <= p.published_at <= until
    ]
    # sort newest first
    published_posts.sort(key=lambda p: p.published_at or now, reverse=True)
    return TodayReviewResponse(
        business_id=business_id,
        since=since,
        until=until,
        posts=published_posts[:max_items],
    )


# ---------------------------
# Feedback endpoints
# ---------------------------

@router.post(
    "/posts/{post_id}/feedback",
    response_model=FeedbackResponse,
)
def submit_feedback(post_id: str, payload: FeedbackBody):
    if post_id not in posts_store:
        raise HTTPException(status_code=404, detail="Post not found")

    post = posts_store[post_id]
    if post.business_id != payload.business_id:
        raise HTTPException(
            status_code=400,
            detail="business_id does not match post business",
        )

    fb_id = f"fbk_{len(feedback_store) + 1}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    flags = payload.flags or FeedbackFlags()

    fb = FeedbackItem(
        id=fb_id,
        post_id=post_id,
        business_id=payload.business_id,
        rating=payload.rating,
        thumb=payload.thumb,
        flags=flags,
        notes=payload.notes,
        created_at=now,
    )
    feedback_store[fb_id] = fb
    return FeedbackResponse(ok=True, feedback=fb)


@router.get(
    "/businesses/{business_id}/feedback/summary",
    response_model=FeedbackSummaryResponse,
)
def feedback_summary(
    business_id: str,
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = None,
):
    _ensure_business(business_id)
    if to is None:
        to = datetime.now(timezone.utc).replace(tzinfo=None)
    if from_ is None:
        from_ = to - timedelta(days=30)

    # collect feedback for this business and date range
    fb_items = [
        fb
        for fb in feedback_store.values()
        if fb.business_id == business_id
        and from_ <= fb.created_at <= to
    ]

    # join with posts to know category
    by_cat: Dict[CategoryName, List[FeedbackItem]] = {
        "authoritative": [],
        "blog": [],
        "comedic": [],
        "confrontational": [],
        "educational": [],
        "meme": [],
        "persuasive": [],
        "realistic": [],
    }
    for fb in fb_items:
        post = posts_store.get(fb.post_id)
        if not post:
            continue
        by_cat[post.category].append(fb)

    summary: Dict[CategoryName, FeedbackSummaryCategory] = {}
    for cat, items in by_cat.items():
        if not items:
            summary[cat] = FeedbackSummaryCategory(
                posts=0,
                avg_rating=None,
                thumbs_up=0,
                thumbs_down=0,
                flags=FeedbackFlags(),
            )
            continue

        ratings = [i.rating for i in items if i.rating is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else None
        thumbs_up = sum(1 for i in items if i.thumb == "up")
        thumbs_down = sum(1 for i in items if i.thumb == "down")
        flags = FeedbackFlags(
            off_brand=any(i.flags.off_brand for i in items),
            wrong_category=any(i.flags.wrong_category for i in items),
            bad_image=any(i.flags.bad_image for i in items),
            repetitive=any(i.flags.repetitive for i in items),
        )
        summary[cat] = FeedbackSummaryCategory(
            posts=len(items),
            avg_rating=avg_rating,
            thumbs_up=thumbs_up,
            thumbs_down=thumbs_down,
            flags=flags,
        )

    return FeedbackSummaryResponse(
        business_id=business_id,
        **{"from": from_},  # use alias
        to=to,
        by_category=summary,
    )


# ---------------------------
# Category plan endpoint
# ---------------------------

@router.get(
    "/businesses/{business_id}/category-plan",
    response_model=CategoryPlanResponse,
)
def category_plan(
    business_id: str,
    date_: Optional[date] = Query(default=None, alias="date"),
    count: Optional[int] = None,
):
    _ensure_business(business_id)
    sched = get_schedule(business_id)
    weights = get_category_weights(business_id)

    if date_ is None:
        date_ = datetime.now(timezone.utc).replace(tzinfo=None).date()

    dow_idx = date_.weekday()  # 0=Mon
    dow_map: List[DOW] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    dow = dow_map[dow_idx]

    if count is None:
        count = sched.daily_post_targets.get(dow, 0)

    if count <= 0:
        return CategoryPlanResponse(
            business_id=business_id,
            date=date_,
            planned_categories=[],
        )

    # Simple weighted choice: deterministic round-robin from weights
    cats: List[CategoryName] = list(weights.weights.keys())
    vals: List[float] = list(weights.weights.values())
    total = sum(vals)
    probs = [v / total for v in vals]

    planned: List[CategoryPlanSlot] = []
    # naive deterministic plan: just repeat the category with max prob, etc.
    # You can replace this with real RNG or smart planning later.
    for i in range(count):
        # pick category with highest weight for now:
        max_idx = max(range(len(cats)), key=lambda idx: probs[idx])
        planned.append(
            CategoryPlanSlot(slot=i + 1, category=cats[max_idx])
        )

    return CategoryPlanResponse(
        business_id=business_id,
        date=date_,
        planned_categories=planned,
    )
