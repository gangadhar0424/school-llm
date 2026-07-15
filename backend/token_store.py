"""Server-side revocation denylist for locally-issued JWTs.

The local auth path (AUTH_PROVIDER=local) issues self-signed JWTs. Logout was
previously a no-op — a stolen token stayed valid until it expired. This module
adds a small MongoDB-backed denylist of revoked token ids (`jti`) so logout can
actually kill a token immediately.

Storage:
  mongodb.db.revoked_tokens
      { _id: <jti>, expires_at: <datetime> }
  A TTL index on `expires_at` (created in database.create_indexes) auto-purges
  entries once the underlying token would have expired anyway, so the
  collection never grows without bound. Tokens with no expiry are kept for a
  bounded default window.

Both helpers fail safe by their own semantics:
  - is_jti_revoked: on a DB error returns False (do not lock everyone out if
    Mongo blips; the token still had to pass signature + expiry checks).
  - revoke_jti: best-effort; logs on failure.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import mongodb

logger = logging.getLogger(__name__)

# How long to keep a revoked never-expiring token in the denylist. Long enough
# to be safe, bounded so the collection can't grow forever.
_DEFAULT_RETENTION_DAYS = 30


async def revoke_jti(jti: Optional[str], exp: Optional[int] = None) -> None:
    """Add a token id to the denylist. `exp` is the token's expiry epoch (from
    the JWT) so the TTL index can purge the row exactly when the token would
    have lapsed anyway. Best-effort; never raises."""
    if not jti:
        return
    if exp:
        try:
            expires_at = datetime.fromtimestamp(int(exp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            expires_at = datetime.now(timezone.utc) + timedelta(days=_DEFAULT_RETENTION_DAYS)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(days=_DEFAULT_RETENTION_DAYS)
    try:
        await mongodb.db.revoked_tokens.update_one(
            {"_id": jti},
            {"$set": {"expires_at": expires_at}},
            upsert=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not revoke token jti=%s: %s", jti, e)


async def is_jti_revoked(jti: Optional[str]) -> bool:
    """Return True if this token id has been revoked. Fails open (returns
    False) on a storage error so a transient Mongo issue doesn't log out
    every user — the token still passed signature and expiry checks."""
    if not jti:
        return False
    try:
        doc = await mongodb.db.revoked_tokens.find_one({"_id": jti}, {"_id": 1})
        return doc is not None
    except Exception as e:  # noqa: BLE001
        logger.warning("Revocation check failed for jti=%s: %s", jti, e)
        return False
