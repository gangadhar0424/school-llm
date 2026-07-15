"""Super-admin API surface.

All endpoints under ``/api/super-admin`` are gated by ``is_superuser``.
Source of truth: the ERP returns ``is_superuser=True`` on its /me/ response
for the platform owner (the row that sits above any school in the ERP
hierarchy). The role mapper in ``auth_backend._map_eskoolia_role`` turns
that into ``role="super_admin"``. Local-mode dev gets the same shape via
``LOCAL_SUPER_ADMIN_EMAILS`` (see ``auth_backend._resolve_local_role``).

The super admin owns:
- Cross-school analytics (overview, per-school totals).
- Per-school user drill-in (list users, view per-user feature usage).
- Per-school rate limits (and the platform default).

The school admin no longer has any rate-limit endpoints — those moved here.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_backend import AuthError, auth_backend
from auth_context import UserCtx
from database import analytics_db, mongodb, schools_db, activity_db
from rate_limiting import (
    DEFAULT_LIMITS as RL_DEFAULTS,
    FEATURES as RL_FEATURES,
    FEATURES_BY_ROLE as RL_FEATURES_BY_ROLE,
    clear_school_rate_limits,
    get_rate_limits,
    get_school_overrides,
    get_school_usage_window,
    get_today_tokens_by_role,
    get_today_usage,
    get_user_usage_window,
    set_rate_limits,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/super-admin", tags=["super-admin"])


# ─── Dependency ──────────────────────────────────────────────────────────
#
# Defined locally (not imported from main.py) to avoid any circular-import
# risk and to keep the super-admin slice self-contained. Mirrors the
# generic `get_current_user_ctx` shape from main.py.
_security = HTTPBearer()


async def _verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> UserCtx:
    try:
        ctx = await auth_backend.verify_token(credentials.credentials)
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not ctx.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    return ctx


async def require_super_admin(ctx: UserCtx = Depends(_verify_token)) -> UserCtx:
    """Gate: super-admin only. Source of truth is `is_superuser` (ERP /me/
    or local-mode allowlist); role string is a redundancy check."""
    if not (ctx.is_superuser or ctx.role == "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges required",
        )
    return ctx


SuperAdminDep = Depends(require_super_admin)


# ─── Helpers ─────────────────────────────────────────────────────────────


_AI_ACTIVITY_TYPES = [
    "qa", "summary", "quiz", "audio", "video",
    "short_answer", "long_answer", "mcq",
    "fill_in_blank", "true_false", "question_paper",
]


def _serialize_user(u: Dict[str, Any]) -> Dict[str, Any]:
    """Public shape — never leak hashed_password or other internals."""
    return {
        "id": str(u.get("_id") or u.get("id") or ""),
        "email": u.get("email"),
        "username": u.get("username"),
        "full_name": u.get("full_name"),
        "role": u.get("role"),
        "erp_title": u.get("erp_title"),
        "school_id": u.get("school_id"),
        "school_name": u.get("school_name"),
        "school_plan": u.get("plan") or u.get("school_plan"),
        "class_section": u.get("class_section"),
        "is_active": u.get("is_active", True),
        "last_login_at": u.get("last_login_at"),
    }


# ─── Identity ────────────────────────────────────────────────────────────


@router.get("/me")
async def super_admin_me(ctx: UserCtx = SuperAdminDep):
    """Identity payload for the super-admin layout."""
    return {
        "id": ctx.user_id,
        "email": ctx.email,
        "full_name": ctx.full_name,
        "role": ctx.role,
        "erp_title": ctx.erp_title or "Super Admin",
        "auth_source": ctx.auth_source,
    }


# ─── Overview / dashboard ────────────────────────────────────────────────


_PERIOD_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}


@router.get("/analytics")
async def super_admin_analytics(
    period: str = "7d",
    ctx: UserCtx = SuperAdminDep,
):
    """Platform-wide analytics — same shape as `/api/admin/analytics` but
    NOT scoped to any school. Drives the rich super-admin dashboard
    (KPIs + activity-over-time chart + feature-usage bars)."""
    days = _PERIOD_DAYS.get(period, 7)
    metrics = await analytics_db.get_metrics(school_id=None)
    usage_over_time = await analytics_db.get_usage_over_time(
        days=days, school_id=None
    )
    feature_usage = await analytics_db.get_feature_usage(school_id=None)
    return {
        "metrics": metrics,
        "usage_over_time": usage_over_time,
        "feature_usage": feature_usage,
        "period": period,
        "days": days,
    }


@router.get("/overview")
async def super_admin_overview(ctx: UserCtx = SuperAdminDep):
    """Cross-school totals: school count, user counts by role, AI activity
    rollups for the last 7 and 30 days, and basic growth deltas."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    two_weeks_ago = now - timedelta(days=14)

    schools_count = await mongodb.db.schools.count_documents({})
    total_users = await mongodb.db.users.count_documents({})
    role_counts: Dict[str, int] = {}
    for role in ("admin", "teacher", "student"):
        role_counts[role] = await mongodb.db.users.count_documents({"role": role})

    # AI activity rollups via user_activity (mirrors SchoolAdminDB pattern).
    async def _count_activity_since(since: datetime) -> int:
        try:
            return await mongodb.db.user_activity.count_documents({
                "activity_type": {"$in": _AI_ACTIVITY_TYPES},
                "timestamp": {"$gte": since},
            })
        except Exception:
            return 0

    ai_7d = await _count_activity_since(week_ago)
    ai_30d = await _count_activity_since(month_ago)
    ai_prev_7d = await _count_activity_since(two_weeks_ago) - ai_7d

    # Active users (7d): distinct emails seen in any activity.
    try:
        active_7d_cursor = mongodb.db.user_activity.aggregate([
            {"$match": {"timestamp": {"$gte": week_ago}}},
            {"$group": {"_id": "$user_email"}},
            {"$count": "n"},
        ])
        active_7d_rows = await active_7d_cursor.to_list(length=1)
        active_users_7d = int(active_7d_rows[0]["n"]) if active_7d_rows else 0
    except Exception:
        active_users_7d = 0

    return {
        "schools_count": schools_count,
        "users_total": total_users,
        "users_by_role": role_counts,
        "ai_calls_7d": ai_7d,
        "ai_calls_30d": ai_30d,
        "ai_calls_7d_delta": ai_7d - ai_prev_7d,
        "active_users_7d": active_users_7d,
        "generated_at": now,
    }


# ─── Schools list ────────────────────────────────────────────────────────


@router.get("/schools")
async def super_admin_schools(ctx: UserCtx = SuperAdminDep):
    """All schools that have logged into the app at least once, sorted by
    most-recently-seen first, with 7d AI activity and user counts."""
    rows = await schools_db.list_schools()

    # Enrich each school with its 7d AI usage + override flag. Previously this
    # ran 2 awaited queries PER school strictly sequentially (a classic N+1:
    # 2N round trips back-to-back). We now fan the per-school work out
    # concurrently with asyncio.gather, so total latency is ~one round trip
    # instead of scaling linearly with the number of schools.
    async def _enrich(s: Dict[str, Any]) -> Dict[str, Any]:
        sid = s.get("school_id")
        try:
            sid_int = int(sid)
        except (TypeError, ValueError):
            sid_int = None
        ai_usage_7d = 0
        has_override = False
        if sid_int is not None:
            window, overrides = await asyncio.gather(
                get_school_usage_window(sid_int, days=7),
                get_school_overrides(sid_int),
            )
            ai_usage_7d = sum(window.values())
            has_override = bool(overrides)
        return {
            **s,
            "ai_calls_7d": ai_usage_7d,
            "has_rate_limit_override": has_override,
        }

    out = await asyncio.gather(*[_enrich(s) for s in rows]) if rows else []
    return {"schools": list(out)}


@router.get("/schools/{school_id}")
async def super_admin_school_detail(
    school_id: int,
    ctx: UserCtx = SuperAdminDep,
):
    """Per-school summary: identity, counts by role, 7d/30d activity."""
    school = await schools_db.get_school(school_id)
    if not school:
        # The school might exist in users but not the registry — synthesize
        # a row from the users collection so the page still loads.
        sample = await mongodb.db.users.find_one({"school_id": school_id})
        if not sample:
            raise HTTPException(status_code=404, detail="School not found")
        school = {
            "school_id": school_id,
            "name": sample.get("school_name") or f"School #{school_id}",
            "plan": sample.get("school_plan"),
            "first_seen_at": None,
            "last_seen_at": None,
        }

    base = {"school_id": school_id}
    # Fan these independent reads out concurrently instead of 5 sequential
    # round trips.
    teacher_count, student_count, admin_count, usage_7d, usage_30d = await asyncio.gather(
        mongodb.db.users.count_documents({**base, "role": "teacher"}),
        mongodb.db.users.count_documents({**base, "role": "student"}),
        mongodb.db.users.count_documents({**base, "role": "admin"}),
        get_school_usage_window(school_id, days=7),
        get_school_usage_window(school_id, days=30),
    )

    return {
        "school": school,
        "school_plan": school.get("plan"),
        "counts": {
            "admin": admin_count,
            "teacher": teacher_count,
            "student": student_count,
            "total": admin_count + teacher_count + student_count,
        },
        "ai_usage_7d": usage_7d,
        "ai_usage_30d": usage_30d,
    }


# ─── School users ───────────────────────────────────────────────────────


@router.get("/schools/{school_id}/analytics")
async def super_admin_school_analytics(
    school_id: int,
    period: str = "7d",
    ctx: UserCtx = SuperAdminDep,
):
    """School-scoped analytics — same shape as `/api/admin/analytics`,
    but the super admin can pass any school_id (school admins can only
    see their own school via the /admin route)."""
    days = _PERIOD_DAYS.get(period, 7)
    metrics = await analytics_db.get_metrics(school_id=school_id)
    usage_over_time = await analytics_db.get_usage_over_time(
        days=days, school_id=school_id
    )
    feature_usage = await analytics_db.get_feature_usage(school_id=school_id)
    return {
        "metrics": metrics,
        "usage_over_time": usage_over_time,
        "feature_usage": feature_usage,
        "period": period,
        "days": days,
        "school_id": school_id,
    }


@router.get("/schools/{school_id}/users")
async def super_admin_school_users(
    school_id: int,
    role: Optional[str] = Query(None, description="Filter by role"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ctx: UserCtx = SuperAdminDep,
):
    """Paginated user list for the given school."""
    query: Dict[str, Any] = {"school_id": school_id}
    if role in ("admin", "teacher", "student"):
        query["role"] = role
    total = await mongodb.db.users.count_documents(query)
    skip = (page - 1) * page_size
    cursor = (
        mongodb.db.users.find(query)
        .sort("full_name", 1)
        .skip(skip)
        .limit(page_size)
    )
    rows = [_serialize_user(u) async for u in cursor]
    return {
        "users": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/schools/{school_id}/users/{user_id}/usage")
async def super_admin_user_usage(
    school_id: int,
    user_id: str,
    ctx: UserCtx = SuperAdminDep,
):
    """Today / 7d / 30d feature usage for a single user inside the school."""
    today_usage = await get_today_usage(user_id)
    last_7d = await get_user_usage_window(user_id, days=7)
    last_30d = await get_user_usage_window(user_id, days=30)
    return {
        "user_id": user_id,
        "school_id": school_id,
        "today": today_usage,
        "last_7d": last_7d,
        "last_30d": last_30d,
    }


# ─── Rate limits (platform default + per-school) ─────────────────────────


@router.get("/rate-limits/default")
async def super_admin_get_default_rate_limits(ctx: UserCtx = SuperAdminDep):
    """Platform default token budgets. Shape:
        limits = {role: tokens_per_day}
        defaults = {role: tokens_per_day}  # built-in fallback
        usage_today = {role: total_tokens_today_across_users}
    -1 = unlimited, 0 = disabled."""
    limits = await get_rate_limits(school_id=None)
    usage_today = await get_today_tokens_by_role()
    return {
        "scope": "default",
        "limits": limits,
        "defaults": RL_DEFAULTS,
        "roles": list(RL_DEFAULTS.keys()),
        "usage_today": usage_today,
    }


@router.put("/rate-limits/default")
async def super_admin_set_default_rate_limits(
    body: Dict[str, Any],
    ctx: UserCtx = SuperAdminDep,
):
    """Replace the platform-wide default token budgets.
    Body: ``{roles: {student: 100000, teacher: 500000}}``."""
    roles_payload = body.get("roles") if isinstance(body, dict) else None
    if not isinstance(roles_payload, dict):
        raise HTTPException(
            status_code=400,
            detail="Body must be {roles: {<role>: <tokens_per_day>, ...}}",
        )
    updated = await set_rate_limits(roles_payload, school_id=None)
    try:
        await activity_db.log_activity(
            user_email=ctx.email,
            activity_type="super_admin_rate_limit_default_change",
            details={"limits": updated},
        )
    except Exception:
        pass
    return {"message": "Default rate limits updated.", "limits": updated}


@router.get("/schools/{school_id}/rate-limits")
async def super_admin_get_school_rate_limits(
    school_id: int,
    ctx: UserCtx = SuperAdminDep,
):
    """Effective token budgets for a school (default merged with the
    school's override), plus the override-only doc so the UI can show
    which roles were explicitly customized."""
    effective = await get_rate_limits(school_id=school_id)
    overrides = await get_school_overrides(school_id)
    school = await schools_db.get_school(school_id)
    return {
        "scope": "school",
        "school_id": school_id,
        "school_name": (school or {}).get("name"),
        "limits": effective,
        "overrides": overrides,
        "has_override": bool(overrides),
        "defaults": RL_DEFAULTS,
        "roles": list(RL_DEFAULTS.keys()),
    }


@router.put("/schools/{school_id}/rate-limits")
async def super_admin_set_school_rate_limits(
    school_id: int,
    body: Dict[str, Any],
    ctx: UserCtx = SuperAdminDep,
):
    """Replace the per-school override.
    Body: ``{roles: {student: 50000, teacher: 250000}}``."""
    roles_payload = body.get("roles") if isinstance(body, dict) else None
    if not isinstance(roles_payload, dict):
        raise HTTPException(
            status_code=400,
            detail="Body must be {roles: {<role>: <tokens_per_day>, ...}}",
        )
    updated = await set_rate_limits(roles_payload, school_id=school_id)
    try:
        await activity_db.log_activity(
            user_email=ctx.email,
            activity_type="super_admin_rate_limit_school_change",
            details={"school_id": school_id, "limits": updated},
        )
    except Exception:
        pass
    return {
        "message": f"Rate limits updated for school {school_id}.",
        "school_id": school_id,
        "limits": updated,
    }


@router.delete("/schools/{school_id}/rate-limits")
async def super_admin_clear_school_rate_limits(
    school_id: int,
    ctx: UserCtx = SuperAdminDep,
):
    """Drop the per-school override so the school falls back to the
    platform default. Idempotent — clearing a non-existent override is OK."""
    await clear_school_rate_limits(school_id)
    try:
        await activity_db.log_activity(
            user_email=ctx.email,
            activity_type="super_admin_rate_limit_school_clear",
            details={"school_id": school_id},
        )
    except Exception:
        pass
    return {
        "message": f"Override cleared for school {school_id}; will follow default.",
        "school_id": school_id,
    }
