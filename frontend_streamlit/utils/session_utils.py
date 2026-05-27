"""
Session state management utilities for School LLM Streamlit app.

Auth persistence: the JWT token is stored in `st.session_state` for fast
in-memory access AND mirrored into the URL as a query parameter so a
hard browser reload preserves the login state.

Why URL query params and not cookies:
    extra-streamlit-components' CookieManager.set() does not write the
    cookie synchronously — it enqueues a JS command that only runs when
    the component next renders. If the caller redirects (st.switch_page)
    immediately after login(), the iframe is destroyed before the queued
    set executes, so the cookie is never persisted. URL query params do
    not have this race: they're part of the URL itself, set synchronously,
    and read back instantly on any reload.

Trade-off: the token is visible in the URL. For an internal school app
this is acceptable; JWTs expire, and the alternative (broken reloads)
is far worse.
"""
from typing import Optional

import streamlit as st

# Side-effect import: silences noisy Windows asyncio ConnectionResetError
# spam during connection cleanup. Imported here because session_utils is
# loaded on every Streamlit page entry point.
from utils import asyncio_patch  # noqa: F401


# Short query param name keeps the URL readable.
_QUERY_PARAM_TOKEN = "_t"


def _populate_from_user(user_info: dict) -> None:
    """Copy fields from /api/auth/me into session state. Shared by both
    the fresh-login and URL-restore paths so they stay consistent."""
    st.session_state["is_admin"] = user_info.get("is_admin", False)
    st.session_state["user_email"] = user_info.get("email", "")
    st.session_state["username"] = user_info.get("username", "")
    st.session_state["full_name"] = user_info.get("full_name", "")
    role = (user_info.get("role") or "").strip().lower()
    if role not in ("admin", "teacher", "student"):
        role = "admin" if user_info.get("is_admin") else "student"
    st.session_state["user_role"] = role
    st.session_state["class_level"] = user_info.get("class_level")
    st.session_state["section"] = user_info.get("section")
    st.session_state["subjects_taught"] = user_info.get("subjects_taught") or []
    st.session_state["assigned_classes"] = user_info.get("assigned_classes") or []
    if user_info.get("theme"):
        st.session_state["theme"] = user_info["theme"]


def _get_url_token() -> Optional[str]:
    """Read the JWT from the URL query string. Synchronous — no handshake."""
    try:
        return st.query_params.get(_QUERY_PARAM_TOKEN)
    except Exception:
        return None


def _set_url_token(token: str) -> None:
    """Write the JWT into the URL query string."""
    try:
        st.query_params[_QUERY_PARAM_TOKEN] = token
    except Exception:
        pass


def _clear_url_token() -> None:
    """Remove the JWT from the URL query string."""
    try:
        if _QUERY_PARAM_TOKEN in st.query_params:
            del st.query_params[_QUERY_PARAM_TOKEN]
    except Exception:
        pass


def _restore_from_url() -> None:
    """If session has no token but the URL has one, validate it against
    /api/auth/me and rehydrate session state. Wipes the URL token on
    validation failure so we don't retry a bad token on every rerun."""
    if st.session_state.get("token"):
        return
    url_token = _get_url_token()
    if not url_token:
        return
    try:
        # Local import avoids a circular dependency (api_client imports
        # from this module).
        from utils.api_client import APIClient
        user = APIClient(url_token).get_me()
        st.session_state["token"] = url_token
        _populate_from_user(user)
    except Exception:
        _clear_url_token()


def _sync_url_with_session() -> None:
    """If session has a token but the URL lost it (e.g. after a
    st.switch_page that didn't preserve query params), re-write the URL
    so a hard reload still works."""
    token = st.session_state.get("token")
    if token and not _get_url_token():
        _set_url_token(token)


def init_session_state():
    """Initialize all session state keys with safe defaults, restore auth
    from the URL if needed, and keep URL ↔ session in sync."""
    defaults = {
        "token": None,
        "user_email": None,
        "user_role": None,        # "admin" | "teacher" | "student"
        "is_admin": False,
        "username": None,
        "full_name": None,
        # Class hierarchy (Phase 1)
        "class_level": None,
        "section": None,
        "subjects_taught": [],
        "assigned_classes": [],
        # Student state
        "selected_pdf_id": None,
        "selected_pdf_name": None,
        "selected_pdf_ids": [],
        "pdf_list": [],
        "chat_messages": [],
        "chat_input_key": 0,
        # Quiz state
        "quiz_questions": [],
        "quiz_answers": {},
        "quiz_submitted": False,
        "quiz_score": 0,
        # Summary state
        "last_summary": None,
        # Audio state
        "last_audio_filename": None,
        "last_audio_text": None,
        # Video state
        "last_video_script": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    _restore_from_url()
    _sync_url_with_session()


def is_logged_in() -> bool:
    return bool(st.session_state.get("token"))


def get_role() -> str:
    """Return the active role: 'admin' | 'teacher' | 'student'.
    Falls back to is_admin for legacy sessions."""
    role = (st.session_state.get("user_role") or "").strip().lower()
    if role in ("admin", "teacher", "student"):
        return role
    return "admin" if st.session_state.get("is_admin") else "student"


def is_admin() -> bool:
    return get_role() == "admin"


def is_teacher() -> bool:
    return get_role() == "teacher"


def is_student() -> bool:
    return get_role() == "student"


def get_token() -> Optional[str]:
    return st.session_state.get("token")


def login(token: str, user_info: dict):
    """Store credentials after a successful login + mirror to URL so reloads
    survive. URL writes are synchronous — no race with st.switch_page."""
    st.session_state["token"] = token
    _populate_from_user(user_info)
    _set_url_token(token)


def logout():
    """Clear all session state and the URL token."""
    _clear_url_token()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session_state()


def require_login():
    """Call at the top of any protected page. URL-based persistence is
    synchronous so no retry loop is needed — either the token is in the
    URL when the page loads or it isn't."""
    init_session_state()
    if not is_logged_in():
        st.warning("Please log in to access this page.")
        st.page_link("pages/1_Login.py", label="Go to Login", icon="🔐")
        st.stop()


def require_student():
    """Block non-students from student-only pages."""
    require_login()
    if not is_student():
        st.error("This page is for students only.")
        st.stop()


def require_teacher():
    """Block non-teachers from teacher-only pages."""
    require_login()
    if not is_teacher():
        st.error("This page is for teachers only.")
        st.stop()


def require_admin():
    """Block non-admins from admin-only pages."""
    require_login()
    if not is_admin():
        st.error("Admin access required.")
        st.stop()


def class_section() -> str:
    """Return the active student's class+section like '5A', or empty."""
    cl = st.session_state.get("class_level")
    sec = st.session_state.get("section")
    if cl and sec:
        return f"{cl}{sec}"
    return ""
