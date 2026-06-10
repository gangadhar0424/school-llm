"""Unified per-request user context.

Source-agnostic wrapper that both auth backends (local Mongo and eSkoolia ERP)
populate. Existing route handlers read user fields from a plain dict, so
``UserCtx.to_legacy_dict()`` produces the exact shape that today's routes
expect — letting the integration land without touching 50+ endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class UserCtx(BaseModel):
    """Per-request authenticated-user context.

    Fields are deliberately shaped to match what the legacy route handlers
    already read from the Mongo user document, so ``to_legacy_dict()`` can
    feed them directly. New code should prefer the typed accessors on this
    class over the legacy dict.
    """

    # Identity ────────────────────────────────────────────────────────────
    user_id: str                              # eSkoolia int as str, or Mongo ObjectId
    email: str
    username: str
    full_name: Optional[str] = None

    # Authorization ───────────────────────────────────────────────────────
    role: str                                 # "admin" | "teacher" | "student"
    role_names: List[str] = []                # raw role names from ERP, optional
    # Most specific human-readable title (e.g. "Class Teacher", "HOD",
    # "Vice Principal"). Derived from role_names[0] for ERP users and
    # from `role.title()` for local users. UI surfaces this on user lists;
    # auth still gates on `role` (the collapsed 3-tier value).
    erp_title: Optional[str] = None
    permission_codes: List[str] = []          # ERP RBAC codes, optional
    is_admin: bool = False
    is_school_admin: bool = False
    is_superuser: bool = False
    is_active: bool = True

    # Tenancy ─────────────────────────────────────────────────────────────
    school_id: Optional[int] = None           # None in local mode
    school_name: Optional[str] = None
    llm_enabled: bool = True                  # always True for local; ERP-driven otherwise

    # Student-specific ────────────────────────────────────────────────────
    class_level: Optional[int] = None
    section: Optional[str] = None
    class_section: Optional[str] = None       # e.g. "5A"

    # Teacher-specific ────────────────────────────────────────────────────
    subjects_taught: List[str] = []
    assigned_classes: List[str] = []

    # User preferences ────────────────────────────────────────────────────
    theme: str = "cobalt"
    onboarding_completed: bool = False
    must_change_password: bool = False        # ERP signals first-login students

    # Audit fields ────────────────────────────────────────────────────────
    created_at: Optional[datetime] = None

    # Auth-source bookkeeping (NOT serialized to clients) ────────────────
    auth_source: str = "local"                # "local" | "eskoolia"
    hashed_password: Optional[str] = None     # local mode only; never sent

    def to_legacy_dict(self) -> dict:
        """Render the same dict shape the existing route handlers expect.

        Existing routes read keys like ``user["email"]``, ``user["role"]``,
        ``user["id"]``, ``user["_id"]``, ``user["assigned_classes"]`` etc.
        This method preserves that contract so we don't have to refactor
        every endpoint in this phase.
        """
        d = {
            "id": self.user_id,
            "_id": self.user_id,
            "email": self.email,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "erp_title": self.erp_title,
            "is_admin": self.is_admin,
            "is_active": self.is_active,
            "school_id": self.school_id,
            "school_name": self.school_name,
            "llm_enabled": self.llm_enabled,
            "class_level": self.class_level,
            "section": self.section,
            "class_section": self.class_section,
            "subjects_taught": list(self.subjects_taught),
            "assigned_classes": list(self.assigned_classes),
            "theme": self.theme,
            "onboarding_completed": self.onboarding_completed,
            "must_change_password": self.must_change_password,
            "created_at": self.created_at,
            "auth_source": self.auth_source,
        }
        if self.hashed_password is not None:
            d["hashed_password"] = self.hashed_password
        return d
