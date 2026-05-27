"""
Login & Signup — strict role enforcement
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from utils.session_utils import (
    init_session_state, is_logged_in, login, get_role,
)
from utils.api_client import APIClient
from utils.themes import apply_theme


def _route_by_role():
    """After login, send each role to its dashboard."""
    role = get_role()
    if role == "admin":
        st.switch_page("pages/3_Admin_Dashboard.py")
    elif role == "teacher":
        st.switch_page("pages/4_Teacher_Dashboard.py")
    else:
        st.switch_page("pages/2_Student_Dashboard.py")

st.set_page_config(
    page_title="Login — School LLM",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="collapsed",   # no sidebar needed on login
)

init_session_state()

# Apply the theme stored in session_state (set by previous login, defaults to Midnight)
apply_theme()

# Login-page-specific overrides
st.markdown("""
<style>
[data-testid="collapsedControl"] { display: none; }
div[data-testid="stForm"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 28px 32px;
}
</style>
""", unsafe_allow_html=True)

# Already logged in → redirect to the role-appropriate dashboard
if is_logged_in():
    _route_by_role()

# ── Header ────────────────────────────────────────────────────────────────────
_, mid, _ = st.columns([1, 3, 1])
with mid:
    st.markdown("""
    <div style="text-align:center; padding: 30px 0 24px 0;">
        <div style="font-size:48px;">📚</div>
        <h2 style="margin:8px 0 4px 0; color:var(--text-strong);">School LLM</h2>
        <p style="color:var(--text-muted); font-size:0.9rem; margin:0;">AI-powered learning platform</p>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_signup = st.tabs(["  🔑 Login  ", "  📝 Sign Up  "])

    # ── LOGIN ─────────────────────────────────────────────────────────────────
    with tab_login:
        with st.form("login_form"):
            st.markdown("#### Welcome back")
            email    = st.text_input("Email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            role     = st.selectbox(
                "I am a…",
                ["Student", "Teacher", "Admin"],
                help="Must match the role this account was created with.",
            )
            submitted = st.form_submit_button("Login →", width="stretch", type="primary")

        if submitted:
            if not email or not password:
                st.error("Please fill in all fields.")
            else:
                # Map UI label → backend role token (must match
                # auth.RoleType: "admin" | "teacher" | "student")
                api_role = {
                    "Admin":   "admin",
                    "Teacher": "teacher",
                    "Student": "student",
                }[role]
                with st.spinner("Verifying credentials…"):
                    try:
                        client = APIClient()
                        data   = client.login(email, password, api_role)
                        token  = data["access_token"]

                        authed = APIClient(token)
                        user   = authed.get_me()

                        # ── Strict role check ─────────────────────────────
                        # Resolve the user's actual role from the new `role`
                        # field, falling back to the legacy is_admin flag for
                        # accounts created before Phase 1.
                        actual_role = (user.get("role") or "").strip().lower()
                        if not actual_role:
                            actual_role = "admin" if user.get("is_admin") else "student"

                        if actual_role != api_role:
                            pretty = {"admin": "Admin", "teacher": "Teacher", "student": "Student"}.get(actual_role, actual_role.title())
                            st.error(
                                f"⛔ Role mismatch — this is a **{pretty}** account. "
                                f"Please select **{pretty}** and try again."
                            )
                            st.stop()

                        login(token, user)
                        # Apply the user's stored theme so the dashboard
                        # they're about to see uses their preferred colors.
                        st.session_state["theme"] = user.get("theme") or "cobalt"
                        st.success(f"Welcome, {user.get('username', email)}! Redirecting…")
                        _route_by_role()

                    except RuntimeError as e:
                        msg = str(e)
                        if "account" in msg.lower() and "role" in msg.lower():
                            st.error(f"⛔ {msg}")
                        else:
                            st.error(f"Login failed: {msg}")
                    except Exception as e:
                        st.error(f"Cannot reach the server. Is the backend running? ({e})")

    # ── SIGN UP ───────────────────────────────────────────────────────────────
    # ALL_CLASS_SECTIONS = ["1A","1B","1C","2A",...,"10C"]
    ALL_CLASS_SECTIONS = [f"{c}{s}" for c in range(1, 11) for s in ("A", "B", "C")]
    SUBJECT_OPTIONS = ["Math", "Science", "English", "Social", "Computer"]

    with tab_signup:
        # Role selector OUTSIDE the form so the form re-renders with the right
        # role-specific fields when Student / Teacher / Admin is picked.
        s_role = st.selectbox(
            "Register as",
            ["Student", "Teacher", "Admin"],
            key="sr",
            help=(
                "Student → must select your class + section.\n"
                "Teacher → must select subjects + assigned classes.\n"
                "Admin   → full system access; cannot upload/study PDFs."
            ),
        )

        with st.form("signup_form"):
            st.markdown(f"#### Create your account ({s_role})")
            s_email    = st.text_input("Email", placeholder="you@example.com", key="se")
            s_username = st.text_input("Username", placeholder="johndoe", key="su")
            s_fullname = st.text_input("Full Name", placeholder="John Doe (optional)", key="sf")
            s_password = st.text_input("Password", type="password", placeholder="Min 8 characters", key="sp")
            s_confirm  = st.text_input("Confirm Password", type="password", placeholder="Repeat password", key="sc")

            # Role-specific fields
            s_class_level = None
            s_section = None
            s_subjects = []
            s_assigned = []

            if s_role == "Student":
                col_c, col_s = st.columns(2)
                with col_c:
                    s_class_level = st.selectbox(
                        "Class", list(range(1, 11)), key="s_cls",
                        help="Your class level (1 to 10).",
                    )
                with col_s:
                    s_section = st.selectbox(
                        "Section", ["A", "B", "C"], key="s_sec",
                        help="Your section.",
                    )
                st.caption(f"You will be registered to class **{s_class_level}{s_section}**.")
            elif s_role == "Teacher":
                s_subjects = st.multiselect(
                    "Subjects you teach",
                    SUBJECT_OPTIONS, key="t_subs",
                    help="Pick one or more subjects.",
                )
                s_assigned = st.multiselect(
                    "Assigned classes (class + section)",
                    ALL_CLASS_SECTIONS, key="t_cls",
                    help="Select every class+section combo you teach (e.g. 5A, 6A).",
                )

            st.markdown("""
            <div style="background:var(--accent-chip-bg); border-left:3px solid var(--accent);
                        padding:10px 14px; border-radius:4px; margin:8px 0;
                        font-size:0.82rem; color:var(--text-muted);">
                ⚠️ The role you select here is permanent for this account.
            </div>
            """, unsafe_allow_html=True)

            s_submitted = st.form_submit_button("Create Account →", width="stretch", type="primary")

        if s_submitted:
            if not all([s_email, s_username, s_password, s_confirm]):
                st.error("Please fill in all required fields.")
            elif s_password != s_confirm:
                st.error("Passwords do not match.")
            elif len(s_password) < 8:
                st.error("Password must be at least 8 characters.")
            elif s_role == "Student" and (s_class_level is None or not s_section):
                st.error("Students must select a class and section.")
            elif s_role == "Teacher" and (not s_subjects or not s_assigned):
                st.error("Teachers must select at least one subject and one assigned class.")
            else:
                with st.spinner("Creating your account…"):
                    try:
                        api_role = {
                            "Admin": "admin",
                            "Teacher": "teacher",
                            "Student": "student",
                        }[s_role]
                        APIClient().signup(
                            email=s_email, username=s_username,
                            password=s_password, full_name=s_fullname,
                            role=api_role,
                            class_level=int(s_class_level) if s_class_level else None,
                            section=s_section,
                            subjects_taught=s_subjects or None,
                            assigned_classes=s_assigned or None,
                        )
                        st.success("✅ Account created! Switch to the Login tab to sign in.")
                    except RuntimeError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Signup failed: {e}")

    st.markdown("""
    <div style="text-align:center; margin-top:20px;">
        <a href="/" style="color:#555; font-size:0.82rem; text-decoration:none;">
            ← Back to home
        </a>
    </div>
    """, unsafe_allow_html=True)
