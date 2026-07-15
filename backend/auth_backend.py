"""Auth backend abstraction.

Selects between two identity providers at startup based on
``settings.AUTH_PROVIDER``:

* ``"local"``     — existing flow: Mongo user store + bcrypt password verify
                    + locally-signed JWT. Default; keeps the standalone
                    product working unchanged.
* ``"eskoolia"``  — eSkoolia ERP is the identity provider. ``login()``
                    forwards credentials to the ERP's
                    ``POST /api/v1/auth/login/`` endpoint, and tokens are
                    validated by calling ``GET /api/v1/auth/me/``. No
                    signing secret is shared with the ERP.

Both backends return the same ``UserCtx`` shape, so route handlers don't
need to care which one is active.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Protocol, Tuple

import httpx

from auth_context import UserCtx
from config import settings

logger = logging.getLogger(__name__)


# ─── Errors ───────────────────────────────────────────────────────────────


class AuthError(Exception):
    """Raised by an auth backend on invalid credentials or unrecoverable
    upstream failure. Route handlers translate this into a 401/503."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


# ─── Protocol ─────────────────────────────────────────────────────────────


class AuthBackend(Protocol):
    """Common interface that auth-aware route handlers depend on."""

    name: str

    async def login(self, email: str, password: str, requested_role: Optional[str] = None) -> Tuple[str, UserCtx]:
        """Exchange credentials for an access token + a populated UserCtx.

        ``requested_role`` is honored by the local backend (which enforces the
        three-tier role gate at login). The eskoolia backend ignores it —
        the ERP is authoritative on the user's role.
        """
        ...

    async def verify_token(self, token: str) -> Optional[UserCtx]:
        """Return a UserCtx for a valid token, or ``None`` if invalid."""
        ...

    async def logout(self, token: str) -> None:
        """Best-effort: invalidate the token at the source. May be a no-op."""
        ...


# ─── Local backend ────────────────────────────────────────────────────────


class LocalAuthBackend:
    """Existing behavior: Mongo + bcrypt + self-signed JWT.

    This wraps the helpers in ``auth.py`` and ``database.py`` so existing
    route handlers keep working unchanged when ``AUTH_PROVIDER=local``.
    """

    name = "local"

    async def login(
        self,
        email: str,
        password: str,
        requested_role: Optional[str] = None,
    ) -> Tuple[str, UserCtx]:
        # Imported lazily to avoid pulling Mongo deps into the eskoolia path.
        from auth import create_access_token, verify_password
        from database import user_db

        user = await user_db.get_user_by_email(email)
        if not user:
            raise AuthError("Invalid email or password")
        if not verify_password(password, user.get("hashed_password", "")):
            raise AuthError("Invalid email or password")
        if not user.get("is_active", True):
            raise AuthError("Account is inactive", status_code=403)

        actual_role = _resolve_local_role(user)

        # Normalize legacy "user" -> "student" so older clients work.
        rr = (requested_role or "").strip().lower()
        if rr == "user":
            rr = "student"
        # Super admins log in via the same /login form. Frontend submits
        # whichever role tab they happened to be on; ignore that hint so a
        # super admin's email always resolves to its real role regardless.
        if actual_role == "super_admin":
            rr = ""
        if rr and rr != actual_role:
            pretty = {
                "super_admin": "Super Admin",
                "admin": "Admin",
                "teacher": "Teacher",
                "student": "Student",
            }.get(actual_role, actual_role.title())
            raise AuthError(
                f"This account is a {pretty} account. Please select the {pretty} role.",
                status_code=403,
            )

        token = create_access_token(data={"sub": user["email"], "role": actual_role})
        return token, _ctx_from_local_user(user, actual_role)

    async def verify_token(self, token: str) -> Optional[UserCtx]:
        from auth import verify_token as _verify
        from database import user_db
        from token_store import is_jti_revoked

        td = _verify(token)
        if td is None or td.email is None:
            return None
        # Reject tokens that have been explicitly revoked (logout).
        if await is_jti_revoked(td.jti):
            return None
        user = await user_db.get_user_by_email(td.email)
        if user is None:
            return None
        actual_role = _resolve_local_role(user)
        return _ctx_from_local_user(user, actual_role)

    async def logout(self, token: str) -> None:
        # Add this token's id to the server-side denylist so it can't be
        # reused even though the JWT itself is still well-formed.
        from auth import verify_token as _verify
        from token_store import revoke_jti

        td = _verify(token)
        if td is not None and td.jti:
            await revoke_jti(td.jti, td.exp)
        return None


def _local_super_admin_emails() -> set[str]:
    raw = (settings.LOCAL_SUPER_ADMIN_EMAILS or "").strip()
    if not raw:
        return set()
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _resolve_local_role(user: dict) -> str:
    email = (user.get("email") or "").strip().lower()
    if email and email in _local_super_admin_emails():
        return "super_admin"
    role = (user.get("role") or "").strip().lower()
    if role in ("super_admin", "admin", "teacher", "student"):
        return role
    return "admin" if user.get("is_admin") else "student"


def _ctx_from_local_user(user: dict, role: str) -> UserCtx:
    """Build a UserCtx from a Mongo user document."""
    role_names_raw = list(user.get("role_names") or [])
    erp_title = (user.get("erp_title") or (role_names_raw[0] if role_names_raw else role.title())) or None
    is_super = role == "super_admin"
    return UserCtx(
        user_id=str(user.get("id") or user.get("_id") or ""),
        email=user.get("email", ""),
        username=user.get("username", ""),
        full_name=user.get("full_name"),
        role=role,
        role_names=role_names_raw,
        erp_title=("Super Admin" if is_super else erp_title),
        is_admin=bool(user.get("is_admin", False)) or role == "admin" or is_super,
        is_superuser=is_super,
        is_active=bool(user.get("is_active", True)),
        school_id=None,
        school_name=None,
        school_plan=None,
        llm_enabled=True,
        class_level=user.get("class_level"),
        section=user.get("section"),
        class_section=user.get("class_section"),
        subjects_taught=list(user.get("subjects_taught") or []),
        assigned_classes=list(user.get("assigned_classes") or []),
        theme=str(user.get("theme") or "cobalt"),
        onboarding_completed=bool(user.get("onboarding_completed", False)),
        created_at=user.get("created_at"),
        auth_source="local",
        hashed_password=user.get("hashed_password"),
    )


# ─── eSkoolia backend ─────────────────────────────────────────────────────


class EskooliaAuthBackend:
    """ERP-backed identity provider.

    Login: POST {base}/api/v1/auth/login/ with {username, password}.
    Verify: GET  {base}/api/v1/auth/me/  with the access token. The ERP
            validates the JWT signature, so we don't need DJANGO_SECRET_KEY.

    The /me/ response is cached per-token for ESKOOLIA_ME_CACHE_TTL seconds
    to keep load on the ERP bounded; revocation propagates within that window.
    """

    name = "eskoolia"

    def __init__(self) -> None:
        if not settings.ESKOOLIA_BASE_URL:
            logger.warning(
                "AUTH_PROVIDER=eskoolia but ESKOOLIA_BASE_URL is empty; "
                "all auth requests will fail until this is set."
            )
        self._client = httpx.AsyncClient(
            base_url=settings.ESKOOLIA_BASE_URL or "http://invalid.local",
            timeout=settings.ESKOOLIA_HTTP_TIMEOUT,
        )
        # token -> (expires_at_epoch, UserCtx)
        self._me_cache: dict[str, tuple[float, UserCtx]] = {}

    async def login(
        self,
        email: str,
        password: str,
        requested_role: Optional[str] = None,
    ) -> Tuple[str, UserCtx]:
        # The ERP serializer accepts username, email, or phone in `username`.
        payload = {"username": email, "password": password}
        try:
            r = await self._client.post("/api/v1/auth/login/", json=payload)
        except httpx.HTTPError as e:
            logger.error("eSkoolia login network error: %s", e)
            raise AuthError("Identity provider unreachable", status_code=503)

        if r.status_code in (400, 401):
            raise AuthError("Invalid email or password")
        if r.status_code >= 500:
            raise AuthError("Identity provider error", status_code=503)
        r.raise_for_status()

        data = r.json()
        access = data.get("access") or data.get("access_token")
        if not access:
            logger.error("eSkoolia login response missing access token: %s", data)
            raise AuthError("Identity provider returned no token", status_code=502)

        ctx = await self._fetch_me(access)
        self._cache_set(access, ctx)
        return access, ctx

    async def verify_token(self, token: str) -> Optional[UserCtx]:
        cached = self._me_cache.get(token)
        if cached and cached[0] > time.time():
            return cached[1]
        try:
            ctx = await self._fetch_me(token)
        except AuthError as e:
            if e.status_code == 401:
                return None
            raise
        self._cache_set(token, ctx)
        return ctx

    async def logout(self, token: str) -> None:
        # ERP exposes /api/v1/auth/logout/ but it expects the refresh token,
        # which we don't store. Drop the cache entry so it can't be reused
        # from this process; the access token will lapse on its own.
        self._me_cache.pop(token, None)

    # ── helpers ──────────────────────────────────────────────────────────

    async def _fetch_me(self, token: str) -> UserCtx:
        try:
            r = await self._client.get(
                "/api/v1/auth/me/",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as e:
            logger.error("eSkoolia /me/ network error: %s", e)
            raise AuthError("Identity provider unreachable", status_code=503)

        if r.status_code == 401:
            raise AuthError("Invalid or expired token", status_code=401)
        if r.status_code >= 500:
            raise AuthError("Identity provider error", status_code=503)
        r.raise_for_status()
        return _ctx_from_eskoolia_me(r.json())

    def _cache_set(self, token: str, ctx: UserCtx) -> None:
        expires_at = time.time() + max(1, int(settings.ESKOOLIA_ME_CACHE_TTL))
        self._me_cache[token] = (expires_at, ctx)


def _ctx_from_eskoolia_me(me: dict) -> UserCtx:
    """Build a UserCtx from an eSkoolia /api/v1/auth/me/ response."""
    role_names = list(me.get("role_names") or [])
    role = _map_eskoolia_role(me, role_names)
    is_superuser = bool(me.get("is_superuser", False))
    is_school_admin = bool(me.get("is_school_admin", False))

    # The ERP's class_section is the canonical "5A"-style string.
    class_section = me.get("class_section")
    class_level: Optional[int] = None
    section: Optional[str] = None
    if class_section and isinstance(class_section, str):
        # Split "10B" -> ("10", "B"); "5A" -> ("5", "A")
        i = 0
        while i < len(class_section) and class_section[i].isdigit():
            i += 1
        if 0 < i < len(class_section):
            try:
                class_level = int(class_section[:i])
            except ValueError:
                class_level = None
            section = class_section[i:].upper() or None

    # erp_title surfaces the most specific role string the ERP gave us
    # (e.g. "Class Teacher", "HOD", "Vice Principal") so the admin UI can
    # render the real org chart instead of just "Teacher". For the LLM's
    # 3-tier authz we still use `role` — this is display-only.
    erp_title = next((str(n) for n in role_names if n), None)
    if erp_title is None:
        if is_superuser:
            erp_title = "Super Admin"
        elif is_school_admin:
            erp_title = "School Admin"

    def _first_nonempty(*values: object) -> Optional[str]:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    school_plan = _first_nonempty(
        me.get("school_plan"),
        me.get("subscription_plan"),
        me.get("plan"),
        me.get("package_name"),
        me.get("package"),
    )

    return UserCtx(
        user_id=str(me.get("id", "")),
        email=me.get("email", "") or "",
        username=me.get("username", "") or "",
        full_name=(me.get("first_name", "") + " " + me.get("last_name", "")).strip() or None,
        role=role,
        role_names=role_names,
        erp_title=erp_title,
        permission_codes=list(me.get("permission_codes") or []),
        is_admin=(is_superuser or is_school_admin or role == "admin"),
        is_school_admin=is_school_admin,
        is_superuser=is_superuser,
        is_active=True,
        school_id=me.get("school_id"),
        school_name=me.get("school_name"),
        school_plan=school_plan,
        # Super admins (no school) always allowed for preview/debug.
        llm_enabled=bool(me.get("llm_enabled", False)) or is_superuser,
        class_level=class_level,
        section=section,
        class_section=class_section,
        subjects_taught=list(me.get("subjects_taught") or []),
        assigned_classes=list(me.get("assigned_classes") or []),
        theme="cobalt",  # ERP doesn't own LLM theme prefs; default for now
        onboarding_completed=True,  # ERP users skip the LLM-side onboarding
        must_change_password=bool(me.get("must_change_password", False)),
        auth_source="eskoolia",
        hashed_password=None,
    )


def _map_eskoolia_role(me: dict, role_names: list) -> str:
    # Super admin lives above the school hierarchy — its own role string so
    # the LLM can route it to the cross-school dashboard. A school admin
    # (principal etc.) still collapses to "admin".
    if me.get("is_superuser"):
        return "super_admin"
    if me.get("is_school_admin"):
        return "admin"
    lowered = {str(n).lower() for n in role_names}
    if "teacher" in lowered:
        return "teacher"
    if "student" in lowered:
        return "student"
    # Fall back: ERP may have other role names (accountant, librarian, etc.)
    # that should not get LLM access. Map them to "student" so they hit the
    # least-privileged path; routes still enforce role checks.
    return "student"


# ─── Singleton selection ──────────────────────────────────────────────────


def _build_backend() -> AuthBackend:
    provider = (settings.AUTH_PROVIDER or "local").strip().lower()
    if provider == "eskoolia":
        logger.info("Auth backend: eSkoolia (%s)", settings.ESKOOLIA_BASE_URL or "<unset>")
        return EskooliaAuthBackend()
    logger.info("Auth backend: local (Mongo + bcrypt)")
    return LocalAuthBackend()


auth_backend: AuthBackend = _build_backend()
