"""
Super-admin-controlled per-day **token budgets** for AI features.

Modeled after how Claude / ChatGPT plans charge: every role gets a single
daily token pool. Any AI feature the user invokes spends from the same
pool. When the pool is exhausted, further AI calls return HTTP 429 until
midnight rolls the budget over.

Storage:
  mongodb.db.app_settings
      _id="rate_limits:default"        platform default {roles: {role: int_tokens}}
      _id=f"rate_limits:{school_id}"   per-school override (same shape)
  mongodb.db.rate_limit_counters
      One doc per (user_id, day): {
          user_id, day, tokens_used, role, school_id,
          by_feature: {qa: 123, summary: 456, ...},
      }
      Counters older than today are stale and ignored.

Enforcement:
  Each AI endpoint declares ``Depends(rate_limit("qa"))``. The dep runs a
  **pre-check**: if the caller has already exhausted today's pool, raise
  429 immediately. It does NOT increment — the increment happens in the
  LLM client wrapper, which has the actual token count from the response.

Recording:
  ``record_tokens(user, feature, tokens)`` is called by ``ai/llm_client.py``
  AFTER each successful LLM round-trip. It atomically ``$inc``s
  ``tokens_used`` and ``by_feature.<feature>``. A contextvar set by the
  dep tells the LLM client which (user, feature) to bill.

Sentinels (unchanged from the previous count-based model):
  -1 = unlimited (recording still happens for analytics, but the pre-check is skipped)
   0 = role is disabled — every AI call returns 429
"""
from __future__ import annotations

import contextvars
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from pymongo import ReturnDocument

from database import mongodb

logger = logging.getLogger(__name__)


# Features we record `by_feature` against. Used by the analytics drill-in
# to show per-feature token spend within a single user's daily bucket.
# Not used as a billing dimension — the budget is per role, not per feature.
FEATURES = sorted([
    "qa", "summary", "quiz", "audio", "video",
    "short_answer", "long_answer", "mcq", "fill_in_blank", "question_paper",
])

# Per-role role-feature lists, kept for the analytics drill-in only (the
# token pool is single-bucket per role).
FEATURES_BY_ROLE: Dict[str, list] = {
    "student": ["qa", "summary", "quiz", "audio", "video"],
    "teacher": ["short_answer", "long_answer", "mcq", "fill_in_blank", "question_paper"],
}


# Default daily token pools, split input vs output. Sized roughly 5:1
# (input:output) to match how usage actually flows — every call ships
# a large prompt (questions + PDF chunks) but gets back a much shorter
# response. The 5:1 ratio keeps both pools meaningful: neither
# consistently bottlenecks before the other.
#
# Super admin tightens from the UI. -1 = unlimited, 0 = role disabled.
# Either pool exhausting individually triggers a 429.
DEFAULT_LIMITS: Dict[str, Dict[str, int]] = {
    "student": {"input": 500_000, "output": 100_000},
    "teacher": {"input": 2_000_000, "output": 400_000},
}

_KINDS = ("input", "output")


_TEACHER_QUIZ_BUCKET = {
    "short-answer":   "short_answer",
    "long-answer":    "long_answer",
    "mcq":            "mcq",
    "true-false":     "mcq",
    "fill-in-blank":  "fill_in_blank",
}


def map_quiz_feature(role: str, question_type: Optional[str], is_question_paper: bool = False) -> str:
    """Translate a generation request into the analytics feature key.

    The token budget is per-role (not per-feature) so this no longer affects
    billing; it only labels the analytics bucket so the per-user drill-in
    can break the day's tokens down by feature.
    """
    if role == "teacher":
        if is_question_paper:
            return "question_paper"
        qt = (question_type or "mcq").strip().lower()
        return _TEACHER_QUIZ_BUCKET.get(qt, "mcq")
    return "quiz"


def features_for_role(role: str) -> list:
    """Return the analytics-feature list for the given role (drill-in UI)."""
    return list(FEATURES_BY_ROLE.get(role, []))


# ─────────────────────────────────────────────────────────────────────────────
# Settings (super-admin-editable, per-school)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_DOC_ID = "rate_limits:default"


def _school_doc_id(school_id: Optional[int]) -> str:
    return f"rate_limits:{school_id}"


def _merge_role_pool(
    merged: Dict[str, Dict[str, int]], doc: Optional[dict]
) -> None:
    """Overlay a single settings doc on top of `merged` in place.

    Accepts both the new {input, output} shape and the legacy flat int
    shape (treated as the input pool, output left at default) so a
    half-migrated cluster doesn't break.
    """
    if not doc or not isinstance(doc.get("roles"), dict):
        return
    for role, val in doc["roles"].items():
        if role not in merged:
            merged[role] = {"input": 0, "output": 0}
        if isinstance(val, dict):
            for k in _KINDS:
                if k in val:
                    try:
                        merged[role][k] = int(val[k])
                    except (TypeError, ValueError):
                        continue
        else:
            # Legacy flat-int shape — treat as input pool only.
            try:
                merged[role]["input"] = int(val)
            except (TypeError, ValueError):
                continue


async def get_rate_limits(
    school_id: Optional[int] = None,
) -> Dict[str, Dict[str, int]]:
    """Return the effective per-role daily token budget (input + output).

    If ``school_id`` is provided, the school override (if any) is merged
    on top of the platform default. Shape:
        {"student": {"input": 200000, "output": 50000}, ...}
    """
    merged = {role: dict(pool) for role, pool in DEFAULT_LIMITS.items()}
    default_doc = await mongodb.db.app_settings.find_one({"_id": _DEFAULT_DOC_ID})
    _merge_role_pool(merged, default_doc)
    if school_id is not None:
        school_doc = await mongodb.db.app_settings.find_one(
            {"_id": _school_doc_id(school_id)}
        )
        _merge_role_pool(merged, school_doc)
    return merged


async def get_school_overrides(school_id: int) -> Dict[str, Dict[str, int]]:
    """Return ONLY the school's override doc (not merged with the default).
    Empty dict if the school has no override."""
    doc = await mongodb.db.app_settings.find_one(
        {"_id": _school_doc_id(school_id)}
    )
    if not doc or not isinstance(doc.get("roles"), dict):
        return {}
    out: Dict[str, Dict[str, int]] = {}
    for role, val in doc["roles"].items():
        if isinstance(val, dict):
            pool: Dict[str, int] = {}
            for k in _KINDS:
                if k in val:
                    try:
                        pool[k] = int(val[k])
                    except (TypeError, ValueError):
                        continue
            if pool:
                out[role] = pool
        else:
            # Legacy flat-int shape.
            try:
                out[role] = {"input": int(val)}
            except (TypeError, ValueError):
                continue
    return out


def _clean_new_limits(
    new_limits: Dict[str, Any],
) -> Dict[str, Dict[str, int]]:
    """Coerce the inbound payload into the canonical
    ``{role: {input: int, output: int}}`` shape. Unknown roles are
    dropped; missing kinds default to 0 so the doc is always complete."""
    clean: Dict[str, Dict[str, int]] = {}
    for role in DEFAULT_LIMITS.keys():
        if role not in new_limits:
            continue
        raw = new_limits[role]
        pool: Dict[str, int] = {}
        if isinstance(raw, dict):
            for k in _KINDS:
                if k in raw:
                    try:
                        pool[k] = int(raw[k])
                    except (TypeError, ValueError):
                        continue
        else:
            # Caller sent a single int — apply to the input pool only.
            try:
                pool["input"] = int(raw)
            except (TypeError, ValueError):
                pass
        if pool:
            clean[role] = pool
    return clean


async def set_rate_limits(
    new_limits: Dict[str, Any],
    school_id: Optional[int] = None,
) -> Dict[str, Dict[str, int]]:
    """Upsert role-pool token budgets. ``school_id=None`` writes the
    platform default; otherwise writes a per-school override."""
    clean = _clean_new_limits(new_limits)
    doc_id = _DEFAULT_DOC_ID if school_id is None else _school_doc_id(school_id)
    await mongodb.db.app_settings.update_one(
        {"_id": doc_id},
        {"$set": {"roles": clean, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
    return await get_rate_limits(school_id=school_id)


async def clear_school_rate_limits(school_id: int) -> None:
    """Drop the per-school override doc so the school falls back to default."""
    await mongodb.db.app_settings.delete_one(
        {"_id": _school_doc_id(school_id)}
    )


# ─────────────────────────────────────────────────────────────────────────────
# Counter helpers
# ─────────────────────────────────────────────────────────────────────────────

def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _seconds_until_midnight() -> int:
    now = datetime.now()
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((next_midnight - now).total_seconds()))


def _resolve_role(user: Dict) -> str:
    role = (user.get("role") or "").strip().lower()
    if role in ("super_admin", "admin", "teacher", "student"):
        return role
    if user.get("is_superuser"):
        return "super_admin"
    return "admin" if user.get("is_admin") else "student"


def _resolve_school_id(user: Dict) -> Optional[int]:
    sid = user.get("school_id")
    if sid is None:
        return None
    try:
        return int(sid)
    except (TypeError, ValueError):
        return None


def _user_id(user: Dict) -> str:
    return str(user.get("id") or user.get("_id") or user.get("email") or "")


async def _get_today_counter(user_id: str) -> Dict[str, Any]:
    """Return the day's counter doc for this user, or an empty stub."""
    today = _today_key()
    doc = await mongodb.db.rate_limit_counters.find_one(
        {"user_id": user_id, "day": today}
    )
    return doc or {}


def _feature_total(v: Any) -> int:
    """Sum input+output for a single by_feature entry. Handles three shapes:
       - {"input": int, "output": int}  (current)
       - int                            (legacy total)
       - missing                        (0)
    """
    if isinstance(v, dict):
        try:
            return int(v.get("input") or 0) + int(v.get("output") or 0)
        except (TypeError, ValueError):
            return 0
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


async def get_today_usage(user_id: str) -> Dict[str, int]:
    """Per-feature token spend (input+output combined) for this user today.

    Returns ``{feature: total_tokens}`` zero-filled across all known features.
    The total daily spend is ``sum(out.values())``.
    """
    doc = await _get_today_counter(user_id)
    by_feature = (doc.get("by_feature") or {}) if isinstance(doc, dict) else {}
    out = {f: 0 for f in FEATURES}
    for f, v in by_feature.items():
        if f in out:
            out[f] = _feature_total(v)
    return out


async def get_today_tokens(user_id: str) -> Dict[str, int]:
    """Total input/output tokens spent by this user today.
    Returns ``{"input": int, "output": int}`` (both default to 0).

    Falls back to the legacy ``tokens_used`` field as the input count when
    a counter doc predates the input/output split, so users mid-migration
    don't get a sudden budget reset.
    """
    doc = await _get_today_counter(user_id)
    try:
        legacy_total = int(doc.get("tokens_used") or 0)
    except (TypeError, ValueError):
        legacy_total = 0
    try:
        in_tokens = int(doc.get("input_tokens") or 0)
    except (TypeError, ValueError):
        in_tokens = 0
    try:
        out_tokens = int(doc.get("output_tokens") or 0)
    except (TypeError, ValueError):
        out_tokens = 0
    if in_tokens == 0 and out_tokens == 0 and legacy_total > 0:
        in_tokens = legacy_total  # legacy doc: treat as input pool
    return {"input": in_tokens, "output": out_tokens}


async def get_user_usage_window(user_id: str, days: int = 30) -> Dict[str, int]:
    """{feature: tokens (input+output)} for one user across the last N days."""
    out = {f: 0 for f in FEATURES}
    if days <= 0:
        return out
    cutoff = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    cursor = mongodb.db.rate_limit_counters.find(
        {"user_id": user_id, "day": {"$gte": cutoff}},
        {"by_feature": 1},
    )
    async for doc in cursor:
        by_feature = doc.get("by_feature") or {}
        for f, v in by_feature.items():
            if f in out:
                out[f] += _feature_total(v)
    return out


async def get_school_usage_window(
    school_id: int, days: int = 7
) -> Dict[str, int]:
    """{feature: tokens (input+output)} across all users in a school over N days."""
    out = {f: 0 for f in FEATURES}
    if days <= 0:
        return out
    cutoff = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    cursor = mongodb.db.rate_limit_counters.find(
        {"school_id": school_id, "day": {"$gte": cutoff}},
        {"by_feature": 1},
    )
    try:
        async for doc in cursor:
            by_feature = doc.get("by_feature") or {}
            for f, v in by_feature.items():
                if f in out:
                    out[f] += _feature_total(v)
    except Exception as e:  # noqa: BLE001
        logger.error("get_school_usage_window aggregation failed: %s", e)
    return out


async def get_today_tokens_by_role() -> Dict[str, Dict[str, int]]:
    """``{role: {"input": int, "output": int}}`` — today's input vs output
    spend totaled across all users in that role. For the super-admin UI's
    "X used today" hint next to each role's cap."""
    today = _today_key()
    pipeline = [
        {"$match": {"day": today}},
        {
            "$group": {
                "_id": "$role",
                "input": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
                "output": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
                # Legacy: pre-split docs only have `tokens_used`. Add it
                # to input so dashboards don't look empty during the
                # migration window.
                "legacy_total": {"$sum": {"$ifNull": ["$tokens_used", 0]}},
            }
        },
    ]
    out: Dict[str, Dict[str, int]] = {
        "student": {"input": 0, "output": 0},
        "teacher": {"input": 0, "output": 0},
        "admin": {"input": 0, "output": 0},
    }
    try:
        cursor = mongodb.db.rate_limit_counters.aggregate(pipeline)
        async for row in cursor:
            role = row.get("_id") or "unknown"
            if role not in out:
                out[role] = {"input": 0, "output": 0}
            try:
                in_tok = int(row.get("input") or 0)
                out_tok = int(row.get("output") or 0)
                legacy = int(row.get("legacy_total") or 0)
                if in_tok == 0 and out_tok == 0 and legacy > 0:
                    in_tok = legacy
                out[role]["input"] = in_tok
                out[role]["output"] = out_tok
            except (TypeError, ValueError):
                continue
    except Exception as e:  # noqa: BLE001
        logger.error("get_today_tokens_by_role aggregation failed: %s", e)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Check (pre-call) + Record (post-call)
# ─────────────────────────────────────────────────────────────────────────────
#
# The flow is:
#   1. AI endpoint declares Depends(rate_limit("qa")). The dep:
#        - resolves role + school_id + limit
#        - if role is disabled (limit=0), raises 429 immediately
#        - if today's spend already >= limit, raises 429 immediately
#        - otherwise, sets _BILLING_CTX so the LLM client can later record
#   2. Endpoint body runs, calls the LLM via llm_client.chat(...)
#   3. The LLM client extracts input_tokens + output_tokens from the
#      response and calls record_tokens(...) using _BILLING_CTX.
#
# Recording always runs (even for unmetered roles) so per-user analytics
# stays accurate. Only the pre-check distinguishes metered vs unmetered.

_BILLING_CTX: contextvars.ContextVar[Optional[Dict[str, Any]]] = (
    contextvars.ContextVar("_BILLING_CTX", default=None)
)


def set_billing_context(
    user: Dict, feature: str
) -> contextvars.Token:
    """Stash (user, feature, role, school_id) for the current request's
    async context. The LLM client will read this when it records tokens.

    Returns the Token so callers can reset() on cleanup if they want.
    """
    return _BILLING_CTX.set({
        "user_id": _user_id(user),
        "feature": feature,
        "role": _resolve_role(user),
        "school_id": _resolve_school_id(user),
    })


def get_billing_context() -> Optional[Dict[str, Any]]:
    """Return the billing context set by the current request's rate_limit
    dependency, or None if no AI dep is in scope."""
    return _BILLING_CTX.get()


def _disabled_payload(role: str, kind: str) -> Dict[str, Any]:
    secs = _seconds_until_midnight()
    return {
        "message": f"AI features are disabled for {role}s.",
        "role": role,
        "kind": kind,
        "limit": 0,
        "used": 0,
        "remaining": 0,
        "retry_after_seconds": secs,
    }


def _exhausted_payload(role: str, kind: str, limit: int, used: int) -> Dict[str, Any]:
    secs = _seconds_until_midnight()
    return {
        "message": (
            f"You've reached today's {kind} token budget "
            f"({limit:,} tokens). Budget resets at midnight."
        ),
        "role": role,
        "kind": kind,
        "limit": limit,
        "used": used,
        "remaining": 0,
        "retry_after_seconds": secs,
    }


async def check_token_budget(user: Dict, feature: str) -> None:
    """Pre-check: raise 429 if either today's input OR output budget is
    exhausted.

    Admins and super admins are never blocked. For everyone else, each
    pool is checked independently:
      - pool < 0 → unlimited for that pool
      - pool == 0 → role disabled, 429
      - tokens_used[kind] >= pool → 429
    Either way, set the billing context so the LLM client can record.
    """
    role = _resolve_role(user)
    set_billing_context(user, feature)

    if role in ("admin", "super_admin"):
        return

    school_id = _resolve_school_id(user)
    limits = await get_rate_limits(school_id=school_id)
    pool = limits.get(role) or DEFAULT_LIMITS.get(role) or {}
    used = await get_today_tokens(_user_id(user))

    for kind in _KINDS:
        limit = int(pool.get(kind, 0))
        if limit < 0:
            continue  # unlimited for this kind
        if limit == 0:
            secs = _seconds_until_midnight()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=_disabled_payload(role, kind),
                headers={"Retry-After": str(secs)},
            )
        if used.get(kind, 0) >= limit:
            secs = _seconds_until_midnight()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=_exhausted_payload(role, kind, limit, used.get(kind, 0)),
                headers={"Retry-After": str(secs)},
            )


async def record_tokens(
    user_id: str,
    feature: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    *,
    role: Optional[str] = None,
    school_id: Optional[int] = None,
) -> None:
    """Atomically charge input + output tokens to the user's daily budget.

    Called by the LLM client AFTER a successful response. Falls through
    silently on storage errors — we'd rather under-bill once than crash
    a returning AI response. ``by_feature.<feat>`` keeps the per-feature
    breakdown for the analytics drill-in (counts total tokens per feature).
    """
    if not user_id:
        return
    in_t = max(0, int(input_tokens or 0))
    out_t = max(0, int(output_tokens or 0))
    if in_t == 0 and out_t == 0:
        return
    today = _today_key()
    try:
        await mongodb.db.rate_limit_counters.find_one_and_update(
            {"user_id": user_id, "day": today},
            {
                "$inc": {
                    "input_tokens": in_t,
                    "output_tokens": out_t,
                    f"by_feature.{feature}.input": in_t,
                    f"by_feature.{feature}.output": out_t,
                },
                "$setOnInsert": {
                    "user_id": user_id,
                    "day": today,
                    "role": role,
                    "school_id": school_id,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(
            "record_tokens failed for user=%s in=%s out=%s: %s",
            user_id, in_t, out_t, e,
        )


async def record_tokens_from_context(
    input_tokens: int = 0, output_tokens: int = 0
) -> None:
    """Pull user/feature from the request's billing context and call
    ``record_tokens``. Called by the LLM client wrapper."""
    ctx = get_billing_context()
    if ctx is None:
        return
    await record_tokens(
        user_id=ctx["user_id"],
        feature=ctx["feature"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        role=ctx.get("role"),
        school_id=ctx.get("school_id"),
    )


def rate_limit(feature: str):
    """FastAPI dependency factory. Usage unchanged:

        @app.post("/api/ask")
        async def ask(req: ..., user: Dict = Depends(rate_limit("qa"))):
            ...

    The dep returns the current user dict so the endpoint can read user
    fields without an extra ``Depends``. Today's spend is checked here;
    tokens are billed later by the LLM client wrapper.
    """
    # Lazy import — main.py imports rate_limiting at module load.
    from main import get_current_user

    async def _dep(current_user: Dict = Depends(get_current_user)) -> Dict:
        await check_token_budget(current_user, feature)
        return current_user

    return _dep


# ─────────────────────────────────────────────────────────────────────────────
# Legacy compatibility shims
# ─────────────────────────────────────────────────────────────────────────────
# The previous (count-based) module exported these names. Kept as thin
# wrappers so any code we haven't refactored yet won't crash.

async def _check_and_increment(user: Dict, feature: str) -> None:
    """Legacy: behaves like a pre-check only now. The post-call token
    accounting happens in the LLM client wrapper."""
    await check_token_budget(user, feature)


async def get_today_usage_by_role() -> Dict[str, Dict[str, int]]:
    """Legacy shape preserved: ``{role: {feature: tokens_today}}``.
    Tokens here are input+output combined."""
    today = _today_key()
    out: Dict[str, Dict[str, int]] = {
        "admin": {f: 0 for f in FEATURES},
        "teacher": {f: 0 for f in FEATURES},
        "student": {f: 0 for f in FEATURES},
    }
    try:
        cursor = mongodb.db.rate_limit_counters.find(
            {"day": today}, {"role": 1, "by_feature": 1}
        )
        async for doc in cursor:
            role = doc.get("role") or "unknown"
            if role not in out:
                out[role] = {f: 0 for f in FEATURES}
            for f, v in (doc.get("by_feature") or {}).items():
                if f in out[role]:
                    out[role][f] += _feature_total(v)
    except Exception as e:  # noqa: BLE001
        logger.error("get_today_usage_by_role failed: %s", e)
    return out
