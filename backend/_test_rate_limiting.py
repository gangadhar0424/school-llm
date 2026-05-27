"""
Standalone verification for rate_limiting.py.

Mocks mongodb.db with an in-memory collection so we exercise the real
_check_and_increment + get_rate_limits + set_rate_limits paths without
needing a live backend or Mongo connection.

Run from the backend directory:
    python _test_rate_limiting.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pymongo import ReturnDocument


class InMemoryCollection:
    def __init__(self):
        self.docs = []

    def _match(self, doc, query):
        return all(doc.get(k) == v for k, v in query.items())

    async def find_one(self, query):
        for d in self.docs:
            if self._match(d, query):
                return dict(d)
        return None

    async def find_one_and_update(self, query, update, upsert=False, return_document=None):
        for d in self.docs:
            if self._match(d, query):
                for k, v in (update.get("$inc") or {}).items():
                    d[k] = d.get(k, 0) + v
                return dict(d) if return_document == ReturnDocument.AFTER else None
        if upsert:
            new = dict(query)
            new.update(update.get("$setOnInsert") or {})
            for k, v in (update.get("$inc") or {}).items():
                new[k] = v
            self.docs.append(new)
            return dict(new) if return_document == ReturnDocument.AFTER else None
        return None

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if self._match(d, query):
                for k, v in (update.get("$set") or {}).items():
                    d[k] = v
                return
        if upsert:
            new = dict(query)
            for k, v in (update.get("$set") or {}).items():
                new[k] = v
            self.docs.append(new)

    def find(self, query, projection=None):
        matches = [dict(d) for d in self.docs if self._match(d, query)]

        class _Cursor:
            def __init__(self, items):
                self.items = items
                self.idx = 0
            def __aiter__(self):
                return self
            async def __anext__(self):
                if self.idx >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.idx]
                self.idx += 1
                return item

        return _Cursor(matches)


class InMemoryDB:
    def __init__(self):
        self.rate_limit_counters = InMemoryCollection()
        self.app_settings = InMemoryCollection()


# Patch mongodb BEFORE importing rate_limiting so the module sees our fake db
from database import mongodb
mongodb.db = InMemoryDB()

from rate_limiting import (
    _check_and_increment,
    get_rate_limits,
    set_rate_limits,
    get_today_usage,
    FEATURES,
    DEFAULT_LIMITS,
)
from fastapi import HTTPException


def ok(msg): print(f"  [OK] {msg}")
def fail(msg): print(f"  [FAIL] {msg}"); sys.exit(1)


async def main():
    student = {"id": "s1", "email": "s1@x.com", "role": "student"}
    teacher = {"id": "t1", "email": "t1@x.com", "role": "teacher"}
    admin   = {"id": "a1", "email": "a1@x.com", "role": "admin"}

    print("\n[1] Defaults & schema")
    limits = await get_rate_limits()
    assert "student" in limits and "teacher" in limits, limits
    assert "admin" not in DEFAULT_LIMITS, "admin should NOT be in DEFAULT_LIMITS"
    assert limits["student"]["qa"] == 100, limits["student"]
    assert limits["teacher"]["qa"] == 200, limits["teacher"]
    ok(f"DEFAULT_LIMITS has only {list(DEFAULT_LIMITS)} (admin correctly excluded)")
    ok(f"FEATURES = {FEATURES}")

    print("\n[2] set_rate_limits round-trip + sanitization")
    await set_rate_limits({
        "student": {"qa": 3, "summary": 0, "junk_feature": 99},
        "teacher": {"qa": 5},
        "admin": {"qa": 1},   # should be silently dropped
    })
    limits = await get_rate_limits()
    assert limits["student"]["qa"] == 3, limits
    assert limits["student"]["summary"] == 0, limits
    assert "junk_feature" not in limits["student"], "unknown features must be dropped"
    assert limits["student"]["quiz"] == 20, "untouched fields must keep their default"
    assert "admin" not in limits, "admin row must not be persisted"
    ok("Custom limits saved; unknown features + admin payload dropped")

    print("\n[3] Student under quota (3 calls succeed)")
    for i in range(3):
        await _check_and_increment(student, "qa")
    ok("Calls 1, 2, 3 succeeded")

    print("\n[4] 4th call blocked with HTTP 429 + retry_after")
    try:
        await _check_and_increment(student, "qa")
        fail("Expected HTTPException(429) but call returned normally")
    except HTTPException as e:
        assert e.status_code == 429, e.status_code
        assert e.detail["feature"] == "qa"
        assert e.detail["role"] == "student"
        assert e.detail["limit"] == 3
        assert e.detail["used"] == 3, f"used should be 3 (rejected call not counted), got {e.detail['used']}"
        assert e.detail["retry_after_seconds"] > 0
        ok(f"429 raised: limit={e.detail['limit']} used={e.detail['used']} retry={e.detail['retry_after_seconds']}s")

    print("\n[5] Feature disabled (limit=0) blocks the FIRST call")
    try:
        await _check_and_increment(student, "summary")
        fail("summary=0 should have blocked the first call")
    except HTTPException as e:
        assert e.status_code == 429, e.status_code
        assert e.detail["limit"] == 0
        ok(f"summary=0 blocked: '{e.detail['message']}'")

    print("\n[6] Admin is NEVER rate-limited (no counter writes either)")
    counters_before = len(mongodb.db.rate_limit_counters.docs)
    for i in range(20):
        await _check_and_increment(admin, "qa")
    counters_after = len(mongodb.db.rate_limit_counters.docs)
    assert counters_before == counters_after, "admin calls must not write to rate_limit_counters"
    ok(f"Admin made 20 calls, never blocked, 0 new counter docs")

    print("\n[7] Teacher quota is independent of student")
    for i in range(5):
        await _check_and_increment(teacher, "qa")
    try:
        await _check_and_increment(teacher, "qa")
        fail("Teacher 6th call should be blocked (limit=5)")
    except HTTPException as e:
        assert e.status_code == 429
        ok(f"Teacher blocked at 6th call (limit={e.detail['limit']})")

    print("\n[8] get_today_usage reports counts correctly")
    usage = await get_today_usage("s1")
    assert usage["qa"] == 3, f"student qa counter should be 3, got {usage['qa']}"
    assert usage["summary"] == 0, "summary blocked before increment, should be 0"
    ok(f"Student usage today: {usage}")

    print("\n[9] limit=-1 means unlimited (no counter writes)")
    await set_rate_limits({"student": {"qa": -1}, "teacher": {"qa": 5}})
    counters_before = len(mongodb.db.rate_limit_counters.docs)
    for i in range(50):
        await _check_and_increment(student, "qa")
    counters_after = len(mongodb.db.rate_limit_counters.docs)
    assert counters_before == counters_after, "unlimited (-1) must skip the counter write"
    ok("50 student calls all succeeded with limit=-1, 0 new counter docs")

    print("\n[10] Counter docs are keyed by (user_id, feature, day)")
    docs = mongodb.db.rate_limit_counters.docs
    keys = {(d["user_id"], d["feature"], d["day"]) for d in docs}
    assert len(keys) == len(docs), "counter docs must be unique per (user, feature, day)"
    ok(f"{len(docs)} counter docs, all uniquely keyed")

    print("\n[ALL PASSED] Rate-limit verification complete")


if __name__ == "__main__":
    asyncio.run(main())
