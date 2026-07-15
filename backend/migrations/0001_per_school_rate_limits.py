"""One-time migration: convert the single rate-limits doc into the new
per-school layout, seed the `schools` registry from existing users, and
backfill `school_id` on existing `rate_limit_counters` rows.

Idempotent — running this twice does nothing on the second run.

Run from the backend directory:
    python -m migrations.0001_per_school_rate_limits
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Make `backend/` importable when invoked as a module.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from database import mongodb  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")


MIGRATION_ID = "per_school_rate_limits_v1"


async def step_rename_default_rate_limits(db) -> int:
    """Migrate the rate-limits settings doc to the input/output token-pool shape.

    Supported source shapes:
      - {"_id": "rate_limits", "roles": {"student": {"qa": 100, ...}, ...}}
            (legacy per-feature counts)
      - {"_id": "rate_limits:default", "roles": {"student": 100000, ...}}
            (intermediate flat token-pool shape)
      - {"_id": "rate_limits:default", "roles": {"student": {"input": ..., "output": ...}}}
            (new shape — already up to date)
    """
    new_defaults = {
        "student": {"input": 500_000, "output": 100_000},
        "teacher": {"input": 2_000_000, "output": 400_000},
    }

    existing = await db.app_settings.find_one({"_id": "rate_limits"})
    target = await db.app_settings.find_one({"_id": "rate_limits:default"})

    if target and _is_split_shape(target):
        logger.info("Step 1: rate_limits:default already in input/output shape.")
        if existing:
            await db.app_settings.delete_one({"_id": "rate_limits"})
        return 0

    # Promote intermediate flat-int shape (single number per role) into the
    # split shape, treating the existing number as the input pool.
    seed = {k: dict(v) for k, v in new_defaults.items()}
    if target and isinstance(target.get("roles"), dict):
        for role, val in target["roles"].items():
            if role in seed and isinstance(val, int):
                seed[role]["input"] = val

    await db.app_settings.update_one(
        {"_id": "rate_limits:default"},
        {"$set": {"roles": seed, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
    await db.app_settings.delete_one({"_id": "rate_limits"})
    logger.info(f"Step 1: installed input/output token defaults {seed}")
    return 1


def _is_split_shape(doc: dict) -> bool:
    """True if every role value is a dict with at least one of input/output keys."""
    roles = doc.get("roles") or {}
    if not roles:
        return False
    for v in roles.values():
        if not isinstance(v, dict):
            return False
        if "input" not in v and "output" not in v:
            return False
    return True


async def step_seed_schools(db) -> int:
    """Seed `schools` collection from distinct users.school_id values."""
    pipeline = [
        {"$match": {"school_id": {"$ne": None}}},
        {"$group": {
            "_id": "$school_id",
            "name": {"$first": "$school_name"},
            "count": {"$sum": 1},
        }},
    ]
    rows = await db.users.aggregate(pipeline).to_list(length=None)
    now = datetime.utcnow()
    seeded = 0
    for r in rows:
        sid = r["_id"]
        try:
            sid_int = int(sid)
        except (TypeError, ValueError):
            continue
        update = {
            "$set": {
                "name": r.get("name") or f"School #{sid_int}",
                "last_seen_at": now,
                "user_count_cached": int(r.get("count") or 0),
            },
            "$setOnInsert": {"first_seen_at": now},
        }
        result = await db.schools.update_one(
            {"_id": sid_int}, update, upsert=True
        )
        if result.upserted_id is not None:
            seeded += 1
    logger.info(f"Step 2: seeded {seeded} school(s) (existing rows updated)")
    return seeded


async def step_backfill_counter_school_id(db) -> int:
    """Attach `school_id` to existing `rate_limit_counters` rows that lack
    it, by looking up each user's school_id from `users`."""
    cursor = db.rate_limit_counters.find(
        {"school_id": {"$exists": False}},
        {"_id": 1, "user_id": 1},
    )
    rows = await cursor.to_list(length=None)
    if not rows:
        logger.info("Step 3: all counters already carry school_id — nothing to backfill.")
        return 0

    # Cache user_id → school_id lookups so a busy user only gets queried once.
    cache: dict = {}
    updated = 0

    for row in rows:
        uid = row.get("user_id")
        if not uid:
            continue
        if uid in cache:
            sid = cache[uid]
        else:
            # users.id is stored as ObjectId in Mongo but the counter doc
            # stringifies it. Try both.
            from bson import ObjectId  # local import
            user = None
            try:
                user = await db.users.find_one({"_id": ObjectId(uid)})
            except Exception:
                user = None
            if user is None:
                user = await db.users.find_one({"email": uid})
            sid = (user or {}).get("school_id")
            cache[uid] = sid

        await db.rate_limit_counters.update_one(
            {"_id": row["_id"]},
            {"$set": {"school_id": sid}},
        )
        updated += 1

    logger.info(f"Step 3: backfilled school_id on {updated} counter row(s)")
    return updated


async def main() -> None:
    await mongodb.connect()
    db = mongodb.db

    marker = await db["_migrations"].find_one({"_id": MIGRATION_ID})
    if marker:
        logger.info(f"Migration {MIGRATION_ID} already applied at {marker.get('applied_at')}.")
        # Even when previously applied, re-run idempotent steps so partially
        # completed migrations heal themselves.
    s1 = await step_rename_default_rate_limits(db)
    s2 = await step_seed_schools(db)
    s3 = await step_backfill_counter_school_id(db)

    await db["_migrations"].update_one(
        {"_id": MIGRATION_ID},
        {"$set": {
            "applied_at": datetime.utcnow(),
            "stats": {"defaults_renamed": s1, "schools_seeded": s2, "counters_backfilled": s3},
        }},
        upsert=True,
    )
    logger.info("Migration complete.")
    await mongodb.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
