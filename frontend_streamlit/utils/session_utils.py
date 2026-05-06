"""
Session state management utilities for School LLM Streamlit app.
"""
import streamlit as st
from typing import Optional


def init_session_state():
    """Initialize all session state keys with safe defaults."""
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
    """Store credentials after a successful login."""
    st.session_state["token"] = token
    st.session_state["is_admin"] = user_info.get("is_admin", False)
    st.session_state["user_email"] = user_info.get("email", "")
    st.session_state["username"] = user_info.get("username", "")
    st.session_state["full_name"] = user_info.get("full_name", "")
    # Resolve role from explicit field or fall back to is_admin
    role = (user_info.get("role") or "").strip().lower()
    if role not in ("admin", "teacher", "student"):
        role = "admin" if user_info.get("is_admin") else "student"
    st.session_state["user_role"] = role
    # Class hierarchy (set by /api/auth/me)
    st.session_state["class_level"] = user_info.get("class_level")
    st.session_state["section"] = user_info.get("section")
    st.session_state["subjects_taught"] = user_info.get("subjects_taught") or []
    st.session_state["assigned_classes"] = user_info.get("assigned_classes") or []


def logout():
    """Clear all session state."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session_state()


def require_login():
    """Call at the top of any protected page to block unauthenticated access."""
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
