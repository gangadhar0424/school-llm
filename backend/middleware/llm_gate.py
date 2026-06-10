"""LLM feature-gate dependency.

A FastAPI ``Depends`` that:

1. Resolves the caller's :class:`UserCtx` from the bearer token via the
   active auth backend (``local`` or ``eskoolia``).
2. Allows the request only if ``ctx.llm_enabled`` (the ``School.llm_enabled``
   flag on the ERP side). Platform super admins bypass the gate.
3. Returns ``402 Payment Required`` otherwise — semantically "feature not
   purchased / not enabled for this school".

Apply on every endpoint that consumes AI features (PDF upload, chat, quiz,
summary, audio, video, assignments, submissions). Do **not** apply on:

* ``/``                — health
* ``/api/auth/login``  — unauthenticated by definition
* ``/api/auth/me``     — used by the frontend to *discover* llm_enabled
* ``/api/auth/logout`` — always allowed

Usage::

    from middleware.llm_gate import require_llm_enabled
    from auth_context import UserCtx

    @app.post("/api/chat")
    async def chat(..., ctx: UserCtx = Depends(require_llm_enabled)):
        ...

This module deliberately depends only on ``auth_backend`` and
``auth_context``, NOT on ``main``, so it can be imported from anywhere
without circular-import risk.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_backend import AuthError, auth_backend
from auth_context import UserCtx

_security = HTTPBearer()


async def require_llm_enabled(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> UserCtx:
    """FastAPI dependency: authenticate the caller and require LLM access.

    Raises:
        401 — token missing/invalid/expired.
        402 — token is valid but the caller's school hasn't been enabled
              for the LLM by the platform super admin.
        403 — account exists but is inactive.
        503 — identity provider unreachable.
    """
    token = credentials.credentials
    try:
        ctx = await auth_backend.verify_token(token)
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"} if e.status_code == 401 else None,
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

    # Platform super admin always passes — useful for preview/debugging
    # before any school has been enabled.
    if ctx.is_superuser:
        return ctx

    if not ctx.llm_enabled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "AI features are not enabled for your school. "
                "Please contact your administrator."
            ),
        )

    return ctx
