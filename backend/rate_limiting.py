"""
Admin-controlled per-day rate limits for AI features.

Layered on top of the in-memory per-minute middleware (middleware/rate_limiter.py)
which guards against burst abuse. This module enforces per-day quotas that admins
can edit live from the Admin Dashboard.

Storage:
  mongodb.db.app_settings — singleton doc `_id="rate_limits"` holding the
      per-role per-feature daily quotas (admin-editable).
  mongodb.db.rate_limit_counters — one doc per (user_id, feature, day) tracking
      today's usage. Counters older than the current day are stale and ignored.

Enforcement:
  Each AI endpoint declares Depends(rate_limit("qa")). The dep reads the user's
  role, looks up the limit, atomically increments today's counter, and raises
  HTTP 429 (with retry_after_seconds) if the count exceeds the limit. A limit
  of -1 means unlimited.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import Depends, HTTPException, status
from pymongo import ReturnDocument

from database import mongodb

logger = logging.getLogger(__name__)


# Features admins can throttle. Keep the keys short — they end up in counter
# docs and in the admin UI as column headers.
#
# IMPORTANT: students and teachers track DIFFERENT feature sets. A student
# generating a quiz consumes "quiz"; a teacher generating assignment material
# consumes one of "short_answer" / "long_answer" / "mcq" / "fill_in_blank" /
# "question_paper" depending on which AI tab they used. This is because the
# teacher's New Assignment flow has five distinct generation modes that warrant
# independent quota control by admins.
FEATURES_BY_ROLE: Dict[str, list] = {
    "student": ["qa", "summary", "quiz", "audio", "video"],
    "teacher": ["short_answer", "long_answer", "mcq", "fill_in_blank", "question_paper"],
}

# Union of every feature key the system tracks. Used as a whitelist by
# set_rate_limits() and as the legacy "any-known-feature" set for places
# that don't yet know the caller's role.
FEATURES = sorted({f for feats in FEATURES_BY_ROLE.values() for f in feats})


# Defaults are intentionally generous so turning the system on doesn't
# immediately block anyone. Admins can tighten them via the dashboard.
# -1 = unlimited, 0 = feature disabled for that role.
# Note: admins are NOT in this matrix — they're always unmetered (see the
# early-return in _check_and_increment). Rate-limiting an admin would make
# it impossible to demo/test features without exhausting quotas.
DEFAULT_LIMITS: Dict[str, Dict[str, int]] = {
    "student": {
        "qa": 100, "summary": 20, "quiz": 20, "audio": 10, "video": 5,
    },
    "teacher": {
        "short_answer":   50,   # /api/quiz with question_type=short-answer
        "long_answer":    30,   # /api/quiz with question_type=long-answer
        "mcq":            50,   # /api/quiz with question_type=mcq or true-false
        "fill_in_blank":  50,   # /api/quiz with question_type=fill-in-blank
        "question_paper": 10,   # /api/teacher/question-paper bundled call
    },
}


# Maps the question_type sent by the frontend (uses hyphens) to the rate-limit
# feature bucket. true-false shares the mcq bucket because they're conceptually
# the same generation task (a 2-option vs 4-option choice question).
_TEACHER_QUIZ_BUCKET = {
    "short-answer":   "short_answer",
    "long-answer":    "long_answer",
    "mcq":            "mcq",
    "true-false":     "mcq",
    "fill-in-blank":  "fill_in_blank",
}


def map_quiz_feature(role: str, question_type: Optional[str], is_question_paper: bool = False) -> str:
    """Translate a generation request into the rate-limit feature key.

    Students always consume the single "quiz" bucket regardless of which
    question type they generate. Teachers consume role-specific buckets
    (short_answer / long_answer / mcq / fill_in_blank / question_paper).
    """
    if role == "teacher":
        if is_question_paper:
            return "question_paper"
        qt = (question_type or "mcq").strip().lower()
        return _TEACHER_QUIZ_BUCKET.get(qt, "mcq")
    return "quiz"


def features_for_role(role: str) -> list:
    """Return the ordered list of feature keys the given role can consume."""
    return list(FEATURES_BY_ROLE.get(role, []))


# ─────────────────────────────────────────────────────────────────────────────
# Settings (admin-editable)
# ─────────────────────────────────────────────────────────────────────────────

_SETTINGS_DOC_ID = "rate_limits"


async def get_rate_limits() -> Dict[str, Dict[str, int]]:
    """Return the current per-role per-feature daily limits.

    Merges the persisted admin overrides on top of DEFAULT_LIMITS so any
    role/feature the admin hasn't touched still has a sane value.
    """
    doc = await mongodb.db.app_settings.find_one({"_id": _SETTINGS_DOC_ID})
    merged = {role: dict(limits) for role, limits in DEFAULT_LIMITS.items()}
    if doc and isinstance(doc.get("roles"), dict):
        for role, limits in doc["roles"].items():
            if role not in merged:
                merged[role] = {}
            if isinstance(limits, dict):
                for feat, val in limits.items():
                    try:
                        merged[role][feat] = int(val)
                    except (TypeError, ValueError):
                        continue
    return merged


async def set_rate_limits(new_limits: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, int]]:
    """Upsert the admin-editable limits. Coerces values to int and ignores
    unknown roles/features so a malformed admin POST can't corrupt the doc."""
    clean: Dict[str, Dict[str, int]] = {}
    for role in DEFAULT_LIMITS.keys():
        if role not in new_limits or not isinstance(new_limits[role], dict):
            continue
        clean[role] = {}
        for feat in FEATURES:
            if feat in new_limits[role]:
                try:
                    clean[role][feat] = int(new_limits[role][feat])
                except (TypeError, ValueError):
                    continue
    await mongodb.db.app_settings.update_one(
        {"_id": _SETTINGS_DOC_ID},
        {"$set": {"roles": clean, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
    return await get_rate_limits()


# ─────────────────────────────────────────────────────────────────────────────
# Counter helpers
# ─────────────────────────────────────────────────────────────────────────────

def _today_key() -> str:
    """Server-local date stamp. Quotas reset at server midnight."""
    return datetime.now().strftime("%Y-%m-%d")


def _seconds_until_midnight() -> int:
    """Seconds remaining until server local midnight — what we return as
    Retry-After when a user is over quota."""
    now = datetime.now()
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((next_midnight - now).total_seconds()))


def _resolve_role(user: Dict) -> str:
    role = (user.get("role") or "").strip().lower()
    if role in ("admin", "teacher", "student"):
        return role
    return "admin" if user.get("is_admin") else "student"


async def get_today_usage(user_id: str) -> Dict[str, int]:
    """Return {feature: count} for the given user today. Used by the admin
    'today's usage' view."""
    today = _today_key()
    out = {f: 0 for f in FEATURES}
    cursor = mongodb.db.rate_limit_counters.find(
        {"user_id": user_id, "day": today},
        {"feature": 1, "count": 1},
    )
    async for doc in cursor:
        f = doc.get("feature")
        if f in out:
            out[f] = int(doc.get("count") or 0)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Check + increment (the hot path)
# ─────────────────────────────────────────────────────────────────────────────

async def _check_and_increment(user: Dict, feature: str) -> None:
    """Atomically increment today's counter for (user, feature) and raise
    HTTP 429 if the new count exceeds the configured limit.

    -1 = unlimited (skip the increment entirely so we don't bloat the
    counters collection for admins).
    """
    if feature not in FEATURES:
        # Misconfigured call-site — log and let the request through rather
        # than 500-ing a real user.
        logger.warning(f"rate_limit: unknown feature {feature!r}, skipping")
        return

    role = _resolve_role(user)
    # Admins are NEVER rate-limited — they need to be able to demo/test
    # features and shouldn't lock themselves out by tightening student quotas.
    if role == "admin":
        return

    limits = await get_rate_limits()
    role_limits = limits.get(role) or DEFAULT_LIMITS.get(role) or {}
    limit = int(role_limits.get(feature, 0))

    if limit < 0:
        return  # unlimited

    if limit == 0:
        # Explicitly disabled for this role
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": f"The '{feature}' feature is disabled for {role}s.",
                "feature": feature,
                "role": role,
                "limit": 0,
                "used": 0,
                "retry_after_seconds": _seconds_until_midnight(),
            },
            headers={"Retry-After": str(_seconds_until_midnight())},
        )

    user_id = str(user.get("id") or user.get("_id") or user.get("email") or "")
    today = _today_key()

    # Read current count first so a blocked client doesn't keep inflating
    # the counter on every rejected retry. There's a small race between
    # this read and the increment below — at school scale that means a
    # user might rarely sneak through one extra call, which is fine.
    existing = await mongodb.db.rate_limit_counters.find_one(
        {"user_id": user_id, "feature": feature, "day": today}
    )
    current_count = int((existing or {}).get("count") or 0)

    if current_count >= limit:
        retry = _seconds_until_midnight()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": (
                    f"You've reached today's {feature} quota ({limit}). "
                    f"Quota resets at midnight."
                ),
                "feature": feature,
                "role": role,
                "limit": limit,
                "used": current_count,
                "retry_after_seconds": retry,
            },
            headers={"Retry-After": str(retry)},
        )

    await mongodb.db.rate_limit_counters.find_one_and_update(
        {"user_id": user_id, "feature": feature, "day": today},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {
                "user_id": user_id,
                "feature": feature,
                "day": today,
                "role": role,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


def rate_limit(feature: str):
    """FastAPI dependency factory. Usage:

        @app.post("/api/ask")
        async def ask(req: ..., user: Dict = Depends(rate_limit("qa"))):
            ...

    The dependency returns the current user (same shape as get_current_user)
    so the endpoint can use it without declaring a separate Depends.
    """
    # Imported lazily to avoid a circular import with main.py
    from main import get_current_user

    async def _dep(current_user: Dict = Depends(get_current_user)) -> Dict:
        await _check_and_increment(current_user, feature)
        return current_user

    return _dep
