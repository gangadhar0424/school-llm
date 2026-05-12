"""
Rate Limiting Middleware for School LLM API
Limits requests per user/IP to prevent abuse.
"""
import time
import logging
from collections import defaultdict, deque
from typing import Dict, Deque
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

# Rate limit configuration
RATE_LIMIT_REQUESTS = 60     # max requests
RATE_LIMIT_WINDOW = 60       # per 60 seconds
AI_RATE_LIMIT_REQUESTS = 20  # stricter limit for AI endpoints
AI_RATE_LIMIT_WINDOW = 60

# AI-heavy endpoints that get stricter limits
AI_ENDPOINTS = {
    "/api/ask", "/api/ask-multi", "/api/quiz",
    "/api/summarize", "/api/audio", "/api/video"
}


class RateLimiter:
    """Token-bucket style per-key rate limiter using a sliding window."""

    def __init__(self):
        # key -> deque of timestamps
        self._windows: Dict[str, Deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        window = self._windows[key]

        # Remove timestamps outside the window
        cutoff = now - window_seconds
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= max_requests:
            return False

        window.append(now)
        return True

    def get_remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        now = time.time()
        window = self._windows[key]
        cutoff = now - window_seconds
        count = sum(1 for ts in window if ts >= cutoff)
        return max(0, max_requests - count)


# Global instance
_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces per-user and per-IP rate limits."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks and static endpoints
        path = request.url.path
        if path in ("/", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # Determine rate limit key: prefer JWT email, fall back to IP
        key = self._get_key(request)
        is_ai = path in AI_ENDPOINTS

        max_req = AI_RATE_LIMIT_REQUESTS if is_ai else RATE_LIMIT_REQUESTS
        window = AI_RATE_LIMIT_WINDOW if is_ai else RATE_LIMIT_WINDOW

        if not _limiter.is_allowed(key, max_req, window):
            logger.warning("Rate limit exceeded for key=%s path=%s", key, path)
            # Important: return a Response directly. Raising HTTPException
            # from inside BaseHTTPMiddleware.dispatch() doesn't propagate
            # cleanly (Starlette wraps it in a TaskGroup → leaks as 500).
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": (
                        f"You're sending requests too fast. Limit is {max_req} "
                        f"per {window} seconds for this feature. "
                        f"Please wait {window}s and try again."
                    ),
                },
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(window),
                },
            )

        response = await call_next(request)
        remaining = _limiter.get_remaining(key, max_req, window)
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(window)
        return response

    def _get_key(self, request: Request) -> str:
        # Try to extract email from JWT for per-user limiting
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                from auth import verify_token
                token_data = verify_token(auth[7:])
                if token_data and token_data.email:
                    return f"user:{token_data.email}"
            except Exception:
                pass

        # Fall back to client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"
