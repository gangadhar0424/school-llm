"""Request gates — semaphores + per-user dedup for heavy operations.

Why this exists
----------------
On a 2 vCPU app box + CPU-only Ollama on a separate VPS, three or four
concurrent quiz generations are enough to push memory into swap and
make every other user's request feel frozen. We bound concurrency per
operation *kind* and reject excess with a friendly 503 instead of
letting it pile up until the OOM-killer steps in.

Three layers
------------
Layer 1 — process-wide semaphores per operation kind ("ai", "pdf",
          "av"). Tuned for KVM 2 + KVM 4 (Ollama) and 5–10 users.
Layer 2 — per-user-per-feature locks. Prevents a double-clicked button
          from firing the same expensive request twice for the same
          person.
Layer 3 — hard wait-queue depth. If too many tasks are already queued
          for a slot, reject the newest with 503 so the connection
          doesn't sit forever holding a worker.

Per-worker scope
----------------
Each uvicorn worker has its own copy of the gates. With
``UVICORN_WORKERS=2`` the effective AI concurrency is 2 × 2 = 4, which
is still well within what the box can absorb. If you scale workers up,
revisit `MAX_CONCURRENT_*` constants.

Usage
-----
::

    from concurrency import AI_GATE

    @app.post("/api/quiz")
    async def generate_quiz(...):
        async with AI_GATE.acquire(
            user_email=current_user["email"], feature="quiz"
        ):
            return await heavy_quiz_work()

The wrapped exceptions ``ServerBusyError`` and ``AlreadyInFlightError``
are translated by main.py's exception handlers into JSON 503 / 429
responses with a generic, professional message.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional, Set

logger = logging.getLogger(__name__)


class ServerBusyError(Exception):
    """The queue for this operation kind is at capacity."""


class AlreadyInFlightError(Exception):
    """The user already has the same feature in flight."""


@dataclass
class _Gate:
    """A capacity-limited slot wrapping ``asyncio.Semaphore``.

    Fields
    ------
    name : str
        Identifier used in logs.
    max_concurrent : int
        Max simultaneous holders.
    max_waiting : int
        Max queued *waiters*. Beyond this, callers get
        ``ServerBusyError`` immediately instead of joining the queue.
    """

    name: str
    max_concurrent: int
    max_waiting: int
    _sem: asyncio.Semaphore = field(init=False)
    _waiting: int = field(default=0, init=False)
    _user_locks: Set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        self._sem = asyncio.Semaphore(self.max_concurrent)

    # Observability — cheap to read, used by health/admin endpoints later.
    def stats(self) -> dict:
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "max_waiting": self.max_waiting,
            "in_flight": self.max_concurrent - self._sem._value,  # type: ignore[attr-defined]
            "waiting": self._waiting,
            "user_locks": len(self._user_locks),
        }

    @asynccontextmanager
    async def acquire(
        self,
        *,
        user_email: Optional[str] = None,
        feature: Optional[str] = None,
    ):
        """Acquire a slot or raise.

        ``user_email`` + ``feature`` together opt into per-user dedup.
        If either is missing, the dedup layer is skipped (e.g. internal
        warm-up calls without a user context).
        """
        user_key: Optional[str] = None
        if user_email and feature:
            user_key = f"{user_email}::{feature}"
            if user_key in self._user_locks:
                logger.info(
                    "gate=%s dedup hit user=%s feature=%s",
                    self.name, user_email, feature,
                )
                raise AlreadyInFlightError(
                    f"This action is already running. Please wait for it to finish."
                )
            self._user_locks.add(user_key)

        # Hard queue cap — refuse before joining the wait queue if the
        # backlog is already deep AND the semaphore is saturated. This
        # is the difference between "you'll wait 10 seconds" and "the
        # server is genuinely overloaded right now."
        already_saturated = self._sem.locked()
        if already_saturated and self._waiting >= self.max_waiting:
            if user_key:
                self._user_locks.discard(user_key)
            logger.warning(
                "gate=%s rejecting user=%s feature=%s (waiting=%d max=%d)",
                self.name, user_email, feature, self._waiting, self.max_waiting,
            )
            raise ServerBusyError(
                "The server is processing many requests right now. "
                "Please try again in a moment."
            )

        self._waiting += 1
        try:
            await self._sem.acquire()
        finally:
            self._waiting -= 1

        try:
            yield
        finally:
            self._sem.release()
            if user_key:
                self._user_locks.discard(user_key)


# ─── Process-wide gates ─────────────────────────────────────────────────
#
# Tuned for Hostinger KVM 2 (app) + KVM 4 (Ollama) + 5–10 users.
# Change these constants here if the box grows; nothing else needs to
# move.

AI_GATE = _Gate(name="ai", max_concurrent=2, max_waiting=15)
PDF_GATE = _Gate(name="pdf", max_concurrent=2, max_waiting=15)
AV_GATE = _Gate(name="av", max_concurrent=1, max_waiting=15)


def all_gate_stats() -> list:
    """Snapshot for the admin/health page."""
    return [g.stats() for g in (AI_GATE, PDF_GATE, AV_GATE)]
