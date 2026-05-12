"""
Student Dashboard — PDF management, Q&A, Quiz, Summary, Audio, Video, Chat History.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Dict, List

import time as _time
import streamlit as st
import streamlit.components.v1 as components
from utils.session_utils import (
    init_session_state, require_login, is_admin, is_teacher,
    is_student, logout, class_section,
)
from utils.api_client import APIClient

st.set_page_config(
    page_title="Student Dashboard — School LLM",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* Keep the sidebar collapse/expand button visible even when header is hidden */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
button[kind="headerNoPadding"] {
    visibility: visible !important;
    display: flex !important;
    z-index: 999999 !important;
}

/* Sidebar styling */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D0D1F 0%, #0A0A18 100%);
    border-right: 1px solid #2A2A4A;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    padding-top: 0.5rem;
}

/* Main background */
.stApp { background: #0E1117; }

/* Hide default page padding top */
.block-container { padding-top: 1.5rem !important; padding-bottom: 1rem !important; }

/* ── Cards ── */
.card {
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    border: 1px solid #2E2E5E;
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 14px;
}
.card-accent {
    background: linear-gradient(135deg, #1E1040 0%, #16213E 100%);
    border: 1px solid #6C63FF55;
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 14px;
}

/* ── Hero banner ── */
.hero {
    background: linear-gradient(135deg, #1A1040 0%, #0D1B3E 50%, #0A1628 100%);
    border: 1px solid #6C63FF44;
    border-radius: 18px;
    padding: 28px 32px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: "";
    position: absolute;
    top: -40px; right: -40px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, #6C63FF22, transparent 70%);
    border-radius: 50%;
}

/* ── Pill badges ── */
.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.3px;
}
.badge-purple { background: #6C63FF22; color: #A89CFF; border: 1px solid #6C63FF55; }
.badge-green  { background: #00C85322; color: #00E870; border: 1px solid #00C85355; }
.badge-orange { background: #FF7A0022; color: #FFB347; border: 1px solid #FF7A0055; }
.badge-red    { background: #FF444422; color: #FF8080; border: 1px solid #FF444455; }

/* ── Feature pills row ── */
.pill-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 10px;
}
.pill {
    background: #1E1E3A;
    border: 1px solid #3A3A6A;
    border-radius: 24px;
    padding: 6px 16px;
    font-size: 0.82rem;
    color: #C0C0E0;
}

/* ── Active PDF bar ── */
.pdf-bar {
    background: linear-gradient(90deg, #1A1040, #12122A);
    border-left: 4px solid #6C63FF;
    border-radius: 0 10px 10px 0;
    padding: 10px 16px;
    margin-bottom: 16px;
    font-size: 0.9rem;
    color: #C8C8F0;
}

/* ── Tab styling ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: #12122A;
    border-radius: 12px;
    padding: 4px;
    gap: 2px;
    border: 1px solid #2A2A4A;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 0.88rem;
    color: #888;
    background: transparent;
    border: none;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: linear-gradient(135deg, #6C63FF, #8B5CF6) !important;
    color: white !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: #12122A;
    border: 1px solid #2A2A4A;
    border-radius: 12px;
    margin-bottom: 8px;
}

/* ── Buttons ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6C63FF, #8B5CF6);
    border: none;
    border-radius: 10px;
    font-weight: 600;
    letter-spacing: 0.3px;
    transition: opacity 0.2s;
}
.stButton > button[kind="primary"]:hover { opacity: 0.88; }

/* ── Sidebar user card ── */
.sidebar-user {
    background: linear-gradient(135deg, #1E1040, #1A1A2E);
    border: 1px solid #6C63FF44;
    border-radius: 14px;
    padding: 16px;
    text-align: center;
    margin-bottom: 16px;
}

/* ── Metric boxes ── */
.metric-box {
    background: linear-gradient(135deg, #1A1A2E, #16213E);
    border: 1px solid #2E2E5E;
    border-radius: 12px;
    padding: 18px 14px;
    text-align: center;
}
.metric-box .num { font-size: 1.8rem; font-weight: 700; color: #A89CFF; }
.metric-box .lbl { font-size: 0.8rem; color: #888; margin-top: 2px; }

/* score bar */
.score-bar-bg {
    background: #1A1A2E;
    border-radius: 8px;
    height: 10px;
    width: 100%;
    margin-top: 6px;
    overflow: hidden;
}
.score-bar-fill {
    height: 100%;
    border-radius: 8px;
    background: linear-gradient(90deg, #6C63FF, #E040FB);
}
</style>
""", unsafe_allow_html=True)

init_session_state()
require_login()

# Role-based routing — only students should land here.
if is_admin():
    st.switch_page("pages/3_Admin_Dashboard.py")
if is_teacher():
    st.switch_page("pages/4_Teacher_Dashboard.py")

api = APIClient(st.session_state.get("token"))


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    name  = st.session_state.get("full_name") or st.session_state.get("username", "Student")
    email = st.session_state.get("user_email", "")

    st.markdown(f"""
    <div class="sidebar-user">
        <div style="font-size:2.2rem; margin-bottom:6px;">🎓</div>
        <div style="font-size:1rem; font-weight:700; color:#E8E8F0;">{name}</div>
        <div style="font-size:0.78rem; color:#888; margin-top:3px;">{email}</div>
        <div style="margin-top:10px;">
            <span class="badge badge-purple">Student</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # PDF list fetched here so it's available globally. Sidebar runs on every
    # rerun, so we must cache aggressively to avoid hammering MongoDB.
    if not st.session_state.get("pdf_list"):
        cache = st.session_state.setdefault("_api_cache", {})
        entry = cache.get("my_pdfs")
        if entry and (_time.time() - entry["ts"]) < 300:
            st.session_state["pdf_list"] = entry["data"]
        else:
            try:
                pdfs = api.get_my_pdfs().get("pdfs", [])
                st.session_state["pdf_list"] = pdfs
                cache["my_pdfs"] = {"data": pdfs, "ts": _time.time()}
            except Exception:
                st.session_state["pdf_list"] = []

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    if st.button("🚪 Logout", use_container_width=True):
        logout()
        st.switch_page("pages/1_Login.py")


# ─────────────────────────────────────────────────────────────────────────────
# CURRENT PDF (used by Q&A / Quiz / Summary / Audio / Video subtabs)
# ─────────────────────────────────────────────────────────────────────────────
current_pdf_id   = st.session_state.get("selected_pdf_id")
current_pdf_name = st.session_state.get("selected_pdf_name", "")

greeting_name = st.session_state.get("full_name") or st.session_state.get("username", "Student")


# ─────────────────────────────────────────────────────────────────────────────
# GENERIC API CACHE — Streamlit re-runs the whole script on every click.
# Without caching, every button press → multiple MongoDB Atlas round-trips
# (~200ms each) → 5-10s UI lag. Session-state cache eliminates this entirely.
# ─────────────────────────────────────────────────────────────────────────────
# Default TTL per cache key (seconds). 5 minutes is fine because we explicitly
# bust caches when data changes (upload, delete, submit, etc.).
_DEFAULT_CACHE_TTL = 300


def _api_cache_get(key: str, ttl: int = _DEFAULT_CACHE_TTL):
    cache = st.session_state.setdefault("_api_cache", {})
    entry = cache.get(key)
    if entry and (_time.time() - entry["ts"]) < ttl:
        return entry["data"]
    return None


def _api_cache_set(key: str, data) -> None:
    cache = st.session_state.setdefault("_api_cache", {})
    cache[key] = {"data": data, "ts": _time.time()}


def _api_cache_bust(*keys: str) -> None:
    """Drop one or more cache keys. Use after mutations."""
    cache = st.session_state.get("_api_cache") or {}
    for k in keys:
        cache.pop(k, None)


def _api_cache_clear_all() -> None:
    st.session_state.pop("_api_cache", None)


def _cached_api(key: str, fn, ttl: int = _DEFAULT_CACHE_TTL, fallback=None):
    """Call `fn()` if no fresh cache entry; otherwise return cached value."""
    cached = _api_cache_get(key, ttl=ttl)
    if cached is not None:
        return cached
    try:
        data = fn()
    except Exception:
        return fallback if fallback is not None else {}
    _api_cache_set(key, data)
    return data


def _get_dashboard_data() -> Dict:
    """Return cached student progress data (5-min TTL)."""
    return _cached_api(
        "dashboard_progress",
        api.get_student_progress,
        ttl=300,
        fallback={
            "features_used": [],
            "total_features": 8,
            "streak_days": 0,
            "recent_pdfs": [],
            "last_used_pdf": None,
            "pending_assignments": 0,
            "onboarding_completed": True,
        },
    )


def _bust_dashboard_cache() -> None:
    """Compatibility shim — busts every cache that depends on PDFs/progress."""
    _api_cache_bust("dashboard_progress", "my_pdfs", "student_assignments")


dashboard_data = _get_dashboard_data()


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTENT HEADER — visible across every tab
# ─────────────────────────────────────────────────────────────────────────────
def _render_persistent_header():
    cs = class_section() or "—"
    streak = int(dashboard_data.get("streak_days", 0))
    pending = int(dashboard_data.get("pending_assignments", 0))

    streak_chip = f"🔥 {streak}-day streak" if streak > 0 else "🌱 Build a streak"
    pending_chip = f"📥 {pending} pending" if pending else "✅ All caught up"

    pdf_chip = ""
    if current_pdf_id:
        pdf_chip = (
            f"<span class='pill' style='background:#1A1040; border-color:#6C63FF;'>"
            f"📄 {current_pdf_name}</span>"
        )

    st.markdown(
        f'<div class="hero" style="padding:18px 24px; margin-bottom:14px;">'
        f'<div style="display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;">'
        f'<div>'
        f'<div style="font-size:0.78rem; color:#A89CFF; font-weight:600; letter-spacing:1px; text-transform:uppercase;">Student Hub</div>'
        f'<h3 style="margin:2px 0 4px 0; font-size:1.35rem; color:#E8E8F0;">Hey, {greeting_name}! 👋'
        f'<span style="color:#888; font-size:0.85rem; font-weight:500;">· Class {cs}</span>'
        f'</h3>'
        f'<div class="pill-row" style="margin-top:6px;">'
        f'<span class="pill">{streak_chip}</span>'
        f'<span class="pill">{pending_chip}</span>'
        f'{pdf_chip}'
        f'</div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


_render_persistent_header()


# ─────────────────────────────────────────────────────────────────────────────
# ONBOARDING WIZARD — first-time student welcome flow
# ─────────────────────────────────────────────────────────────────────────────
@st.dialog("🔑 Change Password")
def _change_password_dialog():
    """Modal for changing the user's password."""
    old_pw = st.text_input("Current Password", type="password", key="_cp_old")
    new_pw = st.text_input("New Password",     type="password", key="_cp_new",
                           help="Minimum 8 characters")
    confirm_pw = st.text_input("Confirm New Password", type="password", key="_cp_confirm")

    cb1, cb2 = st.columns([1, 1])
    with cb1:
        if st.button("Cancel", use_container_width=True, key="_cp_cancel"):
            st.rerun()
    with cb2:
        if st.button("Update Password", use_container_width=True, type="primary",
                     key="_cp_update"):
            if not old_pw or not new_pw:
                st.error("Fill both password fields.")
            elif len(new_pw) < 8:
                st.error("New password must be at least 8 characters.")
            elif new_pw != confirm_pw:
                st.error("New password and confirmation do not match.")
            else:
                try:
                    api.change_password(old_pw, new_pw)
                    st.success("✅ Password updated successfully!")
                    st.toast("Password updated", icon="🔑")
                except RuntimeError as e:
                    st.error(str(e))


@st.dialog("👋 Welcome to School LLM!", width="large")
def _onboarding_wizard():
    """3-step welcome flow shown only on the user's first session."""
    step = int(st.session_state.get("_onboarding_step", 1))
    total_steps = 3

    # Progress dots
    dots = "".join([
        f"<span style='display:inline-block; width:10px; height:10px; border-radius:50%; "
        f"margin-right:6px; background:{'#6C63FF' if i <= step else '#2A2A4A'};'></span>"
        for i in range(1, total_steps + 1)
    ])
    st.markdown(
        f"<div style='text-align:center; margin-bottom:14px;'>{dots}</div>"
        f"<div style='text-align:center; color:#888; font-size:0.85rem;'>Step {step} of {total_steps}</div>",
        unsafe_allow_html=True,
    )

    if step == 1:
        st.markdown("### 📤 Upload your first PDF")
        st.caption(
            "Drop in a textbook, lecture notes, or any study material. "
            "We'll process it so you can ask questions, generate quizzes, and more."
        )
        wizard_pdf = st.file_uploader(
            "PDF file", type=["pdf"], key="_onb_uploader",
            label_visibility="collapsed",
        )
        col_skip, col_next = st.columns([1, 1])
        with col_skip:
            if st.button("Skip for now", use_container_width=True, key="_onb_skip_1"):
                st.session_state["_onboarding_step"] = 3
                st.rerun()
        with col_next:
            if wizard_pdf and st.button("⬆️ Upload & continue",
                                          use_container_width=True, type="primary",
                                          key="_onb_upload"):
                with st.spinner("Processing PDF…"):
                    try:
                        result = api.upload_pdf(wizard_pdf.read(), wizard_pdf.name)
                        st.session_state["pdf_list"] = api.get_my_pdfs().get("pdfs", [])
                        # Auto-select the uploaded PDF
                        new_pdfs = st.session_state["pdf_list"]
                        if new_pdfs:
                            first = new_pdfs[0]
                            st.session_state["selected_pdf_id"] = first["pdf_identifier"]
                            st.session_state["selected_pdf_name"] = first["filename"]
                        st.success(f"✅ {result.get('filename', wizard_pdf.name)}")
                        _bust_dashboard_cache()
                        st.session_state["_onboarding_step"] = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Upload failed: {e}")

    elif step == 2:
        st.markdown("### 🧠 Try your first AI feature")
        st.caption("Pick what you'd like to do with your PDF — you can always come back to try the others.")
        f1, f2, f3 = st.columns(3)
        with f1:
            if st.button("💬 Ask a Question", use_container_width=True, key="_onb_qa"):
                st.session_state["_workspace_subtab"] = "qa"
                st.session_state["_onboarding_step"] = 3
                st.rerun()
        with f2:
            if st.button("📝 Generate a Quiz", use_container_width=True, key="_onb_quiz"):
                st.session_state["_workspace_subtab"] = "quiz"
                st.session_state["_onboarding_step"] = 3
                st.rerun()
        with f3:
            if st.button("📋 Summarize It", use_container_width=True, key="_onb_summary"):
                st.session_state["_workspace_subtab"] = "summary"
                st.session_state["_onboarding_step"] = 3
                st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Skip — I'll explore on my own", use_container_width=True, key="_onb_skip_2"):
            st.session_state["_onboarding_step"] = 3
            st.rerun()

    else:  # step 3 — finalize
        st.markdown("### 🎉 You're all set!")
        st.markdown(
            "Here's what's available on your dashboard:\n\n"
            "- 🏠 **Home** — Quick actions, your PDFs, progress tracker\n"
            "- 📚 **Workspace** — All AI tools (Q&A, Quiz, Summary, Audio, Video) in one place\n"
            "- 📋 **Assignments** — Take and review your teacher's assignments\n"
            "- 🕐 **History** — Past conversations and downloads"
        )
        if st.button("🚀 Get started", use_container_width=True, type="primary", key="_onb_finish"):
            try:
                api.complete_onboarding()
            except Exception:
                pass  # non-fatal — wizard won't reappear once flag is set on next login
            st.session_state["_onboarding_dismissed"] = True
            st.session_state.pop("_onboarding_step", None)
            _bust_dashboard_cache()
            st.toast("Welcome aboard! 🎓", icon="🎉")
            st.rerun()


# Show wizard only if backend says onboarding incomplete AND user hasn't
# dismissed it in this session
if (
    not dashboard_data.get("onboarding_completed", True)
    and not st.session_state.get("_onboarding_dismissed", False)
):
    if "_onboarding_step" not in st.session_state:
        st.session_state["_onboarding_step"] = 1
    _onboarding_wizard()


# ─────────────────────────────────────────────────────────────────────────────
# TABS — simplified to 4 outer tabs; Workspace consolidates 6 AI features
# ─────────────────────────────────────────────────────────────────────────────
tab_home, tab_workspace, tab_assignments_student, tab_history = st.tabs(
    ["🏠 Home", "📚 Workspace", "📋 Assignments", "🕐 History"]
)

# Declare Workspace sub-tabs INSIDE the Workspace tab context so they render
# as subtabs in the DOM. The existing `with tab_qa:`, `with tab_multi:`, etc.
# blocks below this section continue to work unchanged.
with tab_workspace:
    if not current_pdf_id:
        st.markdown("""
        <div style="border:1px dashed #6C63FF55; border-radius:14px;
                    background:#1A1020; padding:38px 24px; text-align:center;
                    margin:20px 0;">
            <div style="font-size:2.4rem; margin-bottom:8px;">📂</div>
            <div style="color:#A89CFF; font-weight:600; font-size:1.05rem;">No PDF selected</div>
            <div style="color:#888; font-size:0.88rem; margin-top:6px;">
                Go to <strong style="color:#A89CFF;">🏠 Home</strong> and use the
                <strong style="color:#A89CFF;">📤 Upload PDF</strong> Quick Action,
                or pick an existing PDF from the sidebar.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="pdf-bar" style="margin-bottom:12px;">
            📖 Working on: <strong style="color:#A89CFF;">{current_pdf_name}</strong>
            &nbsp;<span class="badge badge-green" style="font-size:0.7rem;">READY</span>
        </div>
        """, unsafe_allow_html=True)

    tab_qa, tab_multi, tab_quiz, tab_summary, tab_audio, tab_video = st.tabs(
        ["💬 Q&A", "🔀 Multi-Doc", "📝 Quiz", "📋 Summary", "🔊 Audio", "🎬 Video"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-SWITCH TABS — bridge from Home Quick Actions to target tab.
# Streamlit doesn't expose a tab-switch API, so we inject JS via
# components.html (which runs in an iframe and can access parent DOM).
# `st.markdown` would NOT work here — it strips <script> tags.
# ─────────────────────────────────────────────────────────────────────────────
_pending_switch = st.session_state.pop("_pending_tab_switch", None)
_pending_subtab = st.session_state.get("_workspace_subtab")

if _pending_switch:
    outer_tab_label = {
        "workspace":   "📚 Workspace",
        "assignments": "📋 Assignments",
        "home":        "🏠 Home",
        "history":     "🕐 History",
    }.get(_pending_switch, "🏠 Home")

    inner_tab_label = {
        "qa":      "💬 Q&A",
        "multi":   "🔀 Multi-Doc",
        "quiz":    "📝 Quiz",
        "summary": "📋 Summary",
        "audio":   "🔊 Audio",
        "video":   "🎬 Video",
    }.get(_pending_subtab) if _pending_switch == "workspace" else None

    # Clear the workspace subtab marker so it doesn't keep firing
    if _pending_switch == "workspace":
        st.session_state.pop("_workspace_subtab", None)

    # Build a one-shot JS that:
    # 1. Polls the parent document until the outer tab button appears
    # 2. Clicks it, then waits and clicks the matching inner subtab (if any)
    # Fire-and-forget: click the target tab once, then click the inner subtab
    # once. Use small fixed delays — no polling — to avoid CPU usage and
    # double-reruns. height=0 keeps the iframe invisible.
    components.html(f"""
    <script>
    (function() {{
        const outerLabel = {outer_tab_label!r};
        const innerLabel = {(inner_tab_label or "")!r};
        const doc = window.parent.document;

        function findAndClick(label) {{
            const tabs = doc.querySelectorAll('button[data-baseweb="tab"]');
            for (const t of tabs) {{
                if ((t.innerText || "").trim() === label) {{
                    t.click();
                    return true;
                }}
            }}
            return false;
        }}

        // Click outer tab after the DOM is ready
        setTimeout(() => findAndClick(outerLabel), 60);

        // Click inner subtab a tick later so the subtab DOM has rendered
        if (innerLabel) {{
            setTimeout(() => findAndClick(innerLabel), 220);
        }}
    }})();
    </script>
    """, height=0, width=0)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 0 — HOME (Quick Actions + Progress Tracker + PDF Card Grid)
# ═══════════════════════════════════════════════════════════════════════════════
def _route_to_workspace(subtab: str, pdf_id: str = None, pdf_name: str = None):
    """Helper: select a PDF and remember which Workspace subtab to show."""
    if pdf_id:
        st.session_state["selected_pdf_id"] = pdf_id
    if pdf_name:
        st.session_state["selected_pdf_name"] = pdf_name
    st.session_state["_workspace_subtab"] = subtab
    st.session_state["_pending_tab_switch"] = "workspace"
    st.toast(f"Opened {subtab.replace('_', ' ').title()} in Workspace ↗", icon="🚀")
    st.rerun()


# Track which features the student has used (returned by backend)
_FEATURE_LABELS = {
    "upload":    ("📤", "Upload"),
    "qa":        ("💬", "Q&A"),
    "quiz":      ("📝", "Quiz"),
    "summary":   ("📋", "Summary"),
    "audio":     ("🔊", "Audio"),
    "video":     ("🎬", "Video"),
    "multi_doc": ("🔀", "Multi-Doc"),
    "submit":    ("📨", "Submit"),
}


with tab_home:
    recent_pdfs = dashboard_data.get("recent_pdfs") or []
    last_pdf = dashboard_data.get("last_used_pdf")

    # ── 1. QUICK ACTIONS BAR ─────────────────────────────────────────────────
    st.markdown("#### 🎯 Quick Actions")
    st.caption("One-click access to the most common things you'll do.")

    qa1, qa2 = st.columns(2)
    last_pdf_id = (last_pdf or {}).get("pdf_identifier") if last_pdf else None
    last_pdf_name = (last_pdf or {}).get("filename") if last_pdf else None

    with qa1:
        if st.button("📤  Upload PDF", use_container_width=True, key="qa_upload",
                     type="primary",
                     help="Upload a new PDF to your library"):
            # Toggle the inline upload panel below
            st.session_state["_show_upload_panel"] = not st.session_state.get(
                "_show_upload_panel", False
            )
            st.rerun()
    with qa2:
        if st.button("🔑  Change Password", use_container_width=True, key="qa_change_pw",
                     help="Update your account password"):
            _change_password_dialog()

    # ── INLINE UPLOAD PANEL — toggled by the Upload PDF Quick Action ─────────
    if st.session_state.get("_show_upload_panel", False):
        # Use a Streamlit container with border instead of opening a raw <div>
        # (st.markdown's <div> doesn't span across separate markdown calls,
        # which previously caused stranded </div> tags to render as text).
        with st.container(border=True):
            st.markdown(
                '<div style="color:#A89CFF; font-weight:600;">📤 Upload a new PDF</div>',
                unsafe_allow_html=True,
            )
            up_col, btn_col = st.columns([3, 1])
            with up_col:
                home_uploaders = st.file_uploader(
                    "PDF files", type=["pdf"], key="home_pdf_uploader",
                    label_visibility="collapsed",
                    accept_multiple_files=True,
                    help="Select one or more PDFs to upload",
                )
            with btn_col:
                if st.button("✖️ Close", use_container_width=True, key="home_upload_close"):
                    st.session_state["_show_upload_panel"] = False
                    st.rerun()
            if home_uploaders:
                files_to_upload = home_uploaders if isinstance(home_uploaders, list) else [home_uploaders]
                btn_label = (
                    "⬆️ Upload Now" if len(files_to_upload) == 1
                    else f"⬆️ Upload {len(files_to_upload)} PDFs"
                )
                if st.button(btn_label, use_container_width=True, type="primary",
                             key="home_upload_now"):
                    successes = 0
                    failures = []
                    progress = st.progress(0.0, text="Starting…")
                    for idx, f in enumerate(files_to_upload):
                        progress.progress(
                            idx / len(files_to_upload),
                            text=f"Uploading {f.name} ({idx + 1}/{len(files_to_upload)})…",
                        )
                        try:
                            result = api.upload_pdf(f.read(), f.name)
                            successes += 1
                            st.toast(
                                f"✅ {result.get('filename', f.name)} "
                                f"· {result.get('total_pages','?')} pages",
                                icon="📄",
                            )
                        except RuntimeError as e:
                            failures.append(f"{f.name}: {e}")
                    progress.progress(1.0, text="Done!")

                    # Refresh PDF list + dashboard
                    st.session_state["pdf_list"] = api.get_my_pdfs().get("pdfs", [])
                    new_pdfs = st.session_state["pdf_list"]
                    if new_pdfs and not st.session_state.get("selected_pdf_id"):
                        first = new_pdfs[0]
                        st.session_state["selected_pdf_id"] = first["pdf_identifier"]
                        st.session_state["selected_pdf_name"] = first["filename"]
                    _bust_dashboard_cache()

                    if successes:
                        st.success(f"✅ Uploaded {successes} of {len(files_to_upload)} PDF(s).")
                    if failures:
                        for fail in failures:
                            st.error(fail)

                    if successes and not failures:
                        # Only auto-collapse on full success
                        st.session_state["_show_upload_panel"] = False
                    st.rerun()

    st.markdown("---")

    # ── 2. ACTIVE PDF SELECTOR + MULTI-DOC SELECTOR ─────────────────────────
    home_pdf_list = st.session_state.get("pdf_list", []) or []

    if home_pdf_list:
        st.markdown("#### 📂 Your PDFs")
        sel_col, del_col = st.columns([4, 1])
        pdf_names_home = [p["filename"] for p in home_pdf_list]

        # Default the selectbox to the currently selected PDF if any
        current_name = st.session_state.get("selected_pdf_name", "")
        try:
            default_idx = pdf_names_home.index(current_name) if current_name in pdf_names_home else 0
        except ValueError:
            default_idx = 0

        with sel_col:
            picked_name = st.selectbox(
                "Active PDF",
                options=pdf_names_home,
                index=default_idx,
                key="home_active_pdf_select",
                help="The PDF used by Workspace tools (Q&A, Quiz, Summary, Audio, Video).",
            )
        picked_pdf = next((p for p in home_pdf_list if p["filename"] == picked_name), None)
        if picked_pdf:
            st.session_state["selected_pdf_id"] = picked_pdf["pdf_identifier"]
            st.session_state["selected_pdf_name"] = picked_pdf["filename"]

        with del_col:
            st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
            if st.button("🗑️ Delete", use_container_width=True, key="home_del_pdf",
                         help=f"Delete '{picked_name}'"):
                if picked_pdf:
                    try:
                        api.delete_pdf(picked_pdf["id"])
                        st.session_state["pdf_list"] = api.get_my_pdfs().get("pdfs", [])
                        st.session_state["selected_pdf_id"] = None
                        st.session_state["selected_pdf_name"] = ""
                        _bust_dashboard_cache()
                        st.toast(f"Deleted {picked_name}", icon="🗑️")
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))

        # Multi-Doc selector — always visible (with a hint when <2 PDFs)
        st.markdown(
            '<p style="font-size:0.85rem; font-weight:600; color:#A89CFF; '
            'margin:14px 0 4px 0;">🔀 Multi-Doc Query</p>',
            unsafe_allow_html=True,
        )
        if len(home_pdf_list) < 2:
            st.caption(
                "Upload at least 2 PDFs to use Multi-Doc Query "
                "(query several documents together in Workspace → Multi-Doc)."
            )
            st.multiselect(
                "PDFs to query together",
                options=pdf_names_home,
                default=[],
                key="home_multi_pdfs_disabled",
                placeholder="Need 2+ PDFs to enable Multi-Doc Query",
                label_visibility="collapsed",
                disabled=True,
            )
        else:
            multi_names_home = st.multiselect(
                "PDFs to query together",
                options=pdf_names_home,
                default=[
                    p["filename"] for p in home_pdf_list
                    if p["pdf_identifier"] in (st.session_state.get("selected_pdf_ids") or [])
                ],
                key="home_multi_pdfs",
                placeholder="Pick 2+ PDFs to query together in Workspace → Multi-Doc",
                label_visibility="collapsed",
            )
            st.session_state["selected_pdf_ids"] = [
                p["pdf_identifier"] for p in home_pdf_list if p["filename"] in multi_names_home
            ]

        st.markdown("---")

    # ── 3. PDF CARD GRID ─────────────────────────────────────────────────────
    st.markdown("#### 📚 Your Documents")

    if not recent_pdfs:
        st.markdown("""
        <div style="border:1px dashed #6C63FF55; border-radius:14px; background:#1A1020;
                    padding:38px 24px; text-align:center;">
            <div style="font-size:2.4rem; margin-bottom:8px;">📂</div>
            <div style="color:#A89CFF; font-weight:600;">No PDFs yet</div>
            <div style="color:#888; font-size:0.88rem; margin-top:6px;">
                Click the <strong style="color:#A89CFF;">📤 Upload PDF</strong> Quick Action above to add your first PDF.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Render in rows of 3 cards each
        for row_start in range(0, len(recent_pdfs), 3):
            row_pdfs = recent_pdfs[row_start:row_start + 3]
            row_cols = st.columns(3)
            for col, pdf in zip(row_cols, row_pdfs):
                with col:
                    pid = pdf.get("pdf_identifier") or pdf.get("id")
                    pname = pdf.get("filename", "Untitled")
                    pdisplay = pname if len(pname) <= 28 else pname[:27] + "…"
                    last_action = pdf.get("last_action")
                    last_at = pdf.get("last_action_at") or pdf.get("upload_date") or ""
                    last_at_short = str(last_at)[:10] if last_at else ""
                    last_action_pretty = (
                        _FEATURE_LABELS.get(last_action, ("📄", last_action.title() if last_action else "—"))
                        if last_action else ("📄", "—")
                    )

                    st.markdown(f"""
                    <div class="card" style="height:100%; min-height:170px;">
                        <div style="font-size:1.6rem;">📘</div>
                        <div style="font-weight:700; color:#E8E8F0; margin-top:6px;
                                    overflow:hidden; text-overflow:ellipsis;
                                    white-space:nowrap;" title="{pname}">{pdisplay}</div>
                        <div style="color:#888; font-size:0.78rem; margin-top:4px;">
                            ⏱️ {last_at_short or 'just uploaded'}
                        </div>
                        <div style="color:#A89CFF; font-size:0.78rem; margin-top:2px;">
                            Last: {last_action_pretty[0]} {last_action_pretty[1]}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    bc1, bc2, bc3, bc4 = st.columns(4)
                    with bc1:
                        if st.button("💬", use_container_width=True,
                                     key=f"pdf_qa_{pid}", help="Open Q&A on this PDF"):
                            _route_to_workspace("qa", pid, pname)
                    with bc2:
                        if st.button("📝", use_container_width=True,
                                     key=f"pdf_quiz_{pid}", help="Generate Quiz"):
                            _route_to_workspace("quiz", pid, pname)
                    with bc3:
                        if st.button("📋", use_container_width=True,
                                     key=f"pdf_sum_{pid}", help="Summarize"):
                            _route_to_workspace("summary", pid, pname)
                    with bc4:
                        if st.button("→", use_container_width=True,
                                     key=f"pdf_open_{pid}", help="Open in Workspace",
                                     type="primary"):
                            _route_to_workspace("qa", pid, pname)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — ASSIGNMENTS  (take or review submissions; NO AI features here)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_assignments_student:
    st.caption(
        "📚 Your assignments. Tap one to attempt it. "
        "**AI features are strictly disabled inside the assignment view** — "
        "answer in your own words."
    )

    a_resp = _cached_api("student_assignments", api.student_list_assignments, ttl=120)
    assignments = (a_resp or {}).get("assignments", []) or []

    if not assignments:
        st.info("No assignments are available for your class yet.")
    else:
        for a in assignments:
            aid = a.get("id")
            sub = a.get("my_submission")
            with st.expander(
                f"{'✅' if sub else '⏳'}  {a.get('title','(untitled)')}  "
                f"·  {len(a.get('questions') or [])} Q  ·  Due: "
                f"{str(a.get('due_date',''))[:16].replace('T',' ') or '—'}",
                expanded=False,
            ):
                if a.get("description"):
                    st.markdown(a["description"])

                if sub:
                    # Already submitted — show graded result
                    st.success(
                        f"You scored **{sub.get('percent', 0)}%** "
                        f"({sub.get('total_score', 0)} / {sub.get('total_max', 0)})"
                    )
                    if st.button("View detailed feedback", key=f"s_view_{aid}"):
                        try:
                            full = api.student_get_submission(sub.get("id"))
                            st.session_state[f"s_sub_view_{aid}"] = full
                        except Exception as e:
                            st.error(str(e))

                    detail = st.session_state.get(f"s_sub_view_{aid}")
                    if detail:
                        for ans in (detail.get("submission") or {}).get("answers", []):
                            qi = ans.get("question_index", 0)
                            qtxt = (detail.get("assignment") or {}).get("questions", [])
                            qtxt = qtxt[qi].get("question") if qi < len(qtxt) else f"Q{qi+1}"
                            ovr = ans.get("teacher_override") or {}
                            effective = ovr.get("score") if ovr else ans.get("ai_score")
                            with st.container(border=True):
                                st.markdown(f"**Q{qi+1}. {qtxt}**")
                                st.markdown(f"_Your answer:_ {ans.get('student_answer') or '_(empty)_'}")
                                st.caption(
                                    f"Score: {effective:.1f}/10 · Marks: {ans.get('marks', 10)} · "
                                    f"Scaled: {ans.get('scaled_score', 0)}"
                                )
                                if ovr:
                                    st.info(f"⚖️ Teacher override: **{ovr.get('score')}/10** "
                                            f"— {ovr.get('comment') or '_(no comment)_'}")
                                fb = ans.get("feedback") or {}
                                if fb.get("correct_points"):
                                    st.markdown("✅ **Correct points**")
                                    for p in fb["correct_points"]:
                                        st.markdown(f"- {p}")
                                if fb.get("mistakes"):
                                    st.markdown("❌ **Mistakes**")
                                    for p in fb["mistakes"]:
                                        st.markdown(f"- {p}")
                                if fb.get("improvements"):
                                    st.markdown("💡 **Improvements**")
                                    for p in fb["improvements"]:
                                        st.markdown(f"- {p}")

                else:
                    # Not yet submitted — show questions for taking
                    try:
                        a_full = api.student_get_assignment(aid)
                        questions = (a_full.get("assignment") or {}).get("questions") or []
                    except Exception as e:
                        st.error(str(e))
                        questions = []

                    if questions:
                        st.caption(
                            "✏️ For each question you can **type** your answer, "
                            "or **upload** a PDF / image (JPG / PNG) of your "
                            "handwritten answer — text is **automatically extracted** "
                            "and you can edit it before submitting."
                        )

                        # NOTE: not wrapped in st.form because per-question
                        # 'Extract text' buttons need to act independently.
                        for qi, q in enumerate(questions):
                            with st.container(border=True):
                                st.markdown(f"**Q{qi+1}.** {q.get('question','')}")
                                st.caption(f"Marks: {q.get('marks', 10)}")

                                # Inject any pending OCR text BEFORE the textarea
                                # widget is created on this rerun.
                                pending_key = f"_s_pending_extract_{aid}_{qi}"
                                widget_key = f"s_ans_{aid}_{qi}"
                                pe = st.session_state.pop(pending_key, None)
                                if pe is not None:
                                    st.session_state[widget_key] = pe

                                up = st.file_uploader(
                                    f"📎 Upload your answer for Q{qi+1} (optional)",
                                    type=["pdf", "jpg", "jpeg", "png", "webp", "bmp"],
                                    key=f"s_uploader_{aid}_{qi}",
                                )
                                if up is not None:
                                    fk = f"{up.name}_{up.size}"
                                    already_extracted = st.session_state.get(f"s_extract_key_{aid}_{qi}") == fk

                                    # Auto-extract text when a new file is uploaded
                                    if not already_extracted:
                                        with st.spinner(f"Extracting text from {up.name}…"):
                                            try:
                                                r = api.extract_text_from_upload(
                                                    up.getvalue(), up.name,
                                                )
                                                extracted = r.get("text", "")
                                                if not extracted:
                                                    st.warning(
                                                        r.get("warning")
                                                        or "No text could be extracted from the uploaded file."
                                                    )
                                                else:
                                                    st.session_state[pending_key] = extracted
                                                    st.session_state[f"s_extract_key_{aid}_{qi}"] = fk
                                                    st.toast(
                                                        f"Extracted {r.get('char_count', 0)} chars",
                                                        icon="✅",
                                                    )
                                                    st.rerun()
                                            except Exception as e:
                                                st.error(f"Extraction failed: {e}")

                                    # Show file info and optional re-extract button
                                    eu1, eu2 = st.columns([3, 1])
                                    with eu1:
                                        st.caption(
                                            f"✅ Extracted: **{up.name}** ({up.size // 1024} KB)"
                                        )
                                    with eu2:
                                        if st.button(
                                            "Re-extract",
                                            use_container_width=True,
                                            key=f"s_extract_{aid}_{qi}",
                                        ):
                                            # Clear the extraction key to force re-extraction
                                            st.session_state.pop(f"s_extract_key_{aid}_{qi}", None)
                                            st.rerun()

                                st.text_area(
                                    f"Your answer to Q{qi+1}",
                                    key=widget_key, height=140,
                                    placeholder=(
                                        "Type here, or upload a PDF / image of your "
                                        "handwritten answer above — text will be extracted automatically."
                                    ),
                                )

                        if st.button(
                            "📤 Submit assignment", use_container_width=True,
                            type="primary", key=f"s_submit_{aid}",
                        ):
                            answers = [
                                {
                                    "question_index": qi,
                                    "student_answer": st.session_state.get(
                                        f"s_ans_{aid}_{qi}", ""
                                    ),
                                }
                                for qi in range(len(questions))
                            ]
                            answered = [a for a in answers if (a["student_answer"] or "").strip()]
                            if not answered:
                                st.warning("Write or upload at least one answer before submitting.")
                            else:
                                with st.spinner("Submitting & grading…"):
                                    try:
                                        r = api.student_submit_assignment(aid, answers)
                                        st.success(r.get("message") or "Submitted.")
                                        _bust_dashboard_cache()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Q&A (ChatGPT-style with persistent sessions)
# ═══════════════════════════════════════════════════════════════════════════════
def _render_chat_sessions_panel(mode: str, current_pdf_ids):
    """Render the session list sidebar for a Q&A mode ('single' or 'multi').
    Manages active_session_id_{mode} in session state."""
    state_key = f"active_session_id_{mode}"
    sessions_key = f"sessions_cache_{mode}"

    # Cached: list_chat_sessions runs on every script rerun, but the session
    # list rarely changes. 2-min TTL keeps the UI snappy.
    cache_key = f"chat_sessions_{mode}"
    response = _cached_api(cache_key, lambda: api.list_chat_sessions(mode=mode), ttl=120)
    sessions = (response or {}).get("sessions", [])
    if not sessions and sessions_key in st.session_state:
        sessions = st.session_state.get(sessions_key, [])
    st.session_state[sessions_key] = sessions

    if st.button("New chat", key=f"new_session_{mode}", use_container_width=True, type="primary"):
        try:
            new_sess = api.create_chat_session(
                pdf_ids=current_pdf_ids or [],
                mode=mode,
                name="New chat",
            )
            st.session_state[state_key] = new_sess["id"]
            _api_cache_bust(cache_key)  # session list changed
            st.rerun()
        except Exception as e:
            st.error(f"Could not create session: {e}")

    st.markdown(
        "<div style='margin:14px 0 6px 2px; color:#666; font-size:0.72rem; "
        "text-transform:uppercase; letter-spacing:0.6px; font-weight:600;'>"
        "Recent</div>",
        unsafe_allow_html=True,
    )

    if not sessions:
        st.markdown(
            "<div style='color:#444; font-size:0.82rem; padding:6px 2px;'>"
            "No conversations yet.</div>",
            unsafe_allow_html=True,
        )
        return st.session_state.get(state_key)

    active_id = st.session_state.get(state_key)
    for sess in sessions[:30]:
        sid = sess["id"]
        name = (sess.get("name") or "New chat").strip()
        display = name if len(name) <= 28 else name[:27] + "…"
        updated = (sess.get("updated_at") or "")[:10]

        c1, c2 = st.columns([6, 1], gap="small")
        with c1:
            if st.button(
                display,
                key=f"sess_pick_{mode}_{sid}",
                use_container_width=True,
                help=f"Updated {updated}" if updated else None,
            ):
                st.session_state[state_key] = sid
                st.rerun()
        with c2:
            if st.button("×", key=f"sess_del_{mode}_{sid}", help="Delete"):
                try:
                    api.delete_chat_session(sid)
                    if st.session_state.get(state_key) == sid:
                        st.session_state[state_key] = None
                    _api_cache_bust(f"chat_sessions_{mode}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")

    return st.session_state.get(state_key)


with tab_qa:
    if not current_pdf_id:
        st.markdown("""
        <div style="border:1px solid #2A2A4A; border-radius:12px; background:#12122A;
                    padding:40px 24px; text-align:center;">
            <div style="color:#A89CFF; font-size:1.05rem; font-weight:600;">Start a Conversation</div>
            <div style="color:#666; font-size:0.85rem; margin-top:8px;">
                Upload and select a PDF from the sidebar to ask questions.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        col_sessions, col_chat = st.columns([1, 3], gap="medium")

        with col_sessions:
            active_session_id = _render_chat_sessions_panel("single", [current_pdf_id])

        with col_chat:
            if not active_session_id:
                st.markdown("""
                <div style="border:1px solid #2A2A4A; border-radius:12px; background:#12122A;
                            padding:40px 24px; text-align:center;">
                    <div style="color:#A89CFF; font-size:1.05rem; font-weight:600;">No conversation selected</div>
                    <div style="color:#666; font-size:0.85rem; margin-top:8px;">
                        Click <b>New chat</b> on the left to start a conversation.
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                try:
                    session = api.get_chat_session(active_session_id)
                    session_name = session.get("name") or "New chat"
                    messages = session.get("messages", [])
                except Exception as e:
                    st.error(f"Could not load session: {e}")
                    session_name = "New chat"
                    messages = []

                st.markdown(f"""
                <div style="border-bottom:1px solid #2A2A4A; padding:4px 2px 14px 2px; margin-bottom:14px;">
                    <div style="color:#E8E8F0; font-size:1.1rem; font-weight:600;">{session_name}</div>
                    <div style="color:#666; font-size:0.78rem; margin-top:2px;">{len(messages)} messages</div>
                </div>
                """, unsafe_allow_html=True)

                if not messages:
                    st.markdown("""
                    <div style="color:#555; font-size:0.88rem; padding:32px 4px; text-align:center;">
                        Ask anything about your document. The AI remembers everything you discuss in this chat.
                    </div>
                    """, unsafe_allow_html=True)

                # 1. Render existing (persisted) messages
                for msg in messages:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])
                        if msg.get("sources") and msg["role"] == "assistant":
                            with st.expander("Sources", expanded=False):
                                for src in msg["sources"][:3]:
                                    st.caption(f"› {src}")

                # 2. If a question was just submitted, render it + stream answer
                #    ABOVE the input box (input always stays at the bottom).
                pending_key = f"_qa_pending_{active_session_id}"
                pending_question = st.session_state.pop(pending_key, None)

                if pending_question:
                    with st.chat_message("user"):
                        st.markdown(pending_question)

                    with st.chat_message("assistant"):
                        thinking_ph = st.empty()
                        thinking_ph.markdown(
                            "<span style='color:#888;'>💭 _Thinking…_</span>",
                            unsafe_allow_html=True,
                        )
                        try:
                            result = api.ask_question(
                                current_pdf_id,
                                pending_question,
                                session_id=active_session_id,
                            )
                            answer = result.get("answer", "")
                            sources = result.get("sources", [])
                            thinking_ph.empty()

                            def _word_stream(text: str):
                                import time as _t
                                for word in text.split(" "):
                                    yield word + " "
                                    _t.sleep(0.015)
                            st.write_stream(_word_stream(answer))

                            if sources:
                                with st.expander("Sources", expanded=False):
                                    for src in sources[:3]:
                                        st.caption(f"› {src}")
                        except RuntimeError as e:
                            thinking_ph.empty()
                            st.error(str(e))
                        except Exception as e:
                            thinking_ph.empty()
                            st.error(f"Failed: {e}")

                # 3. Input ALWAYS at the bottom (ChatGPT layout). Submit → store
                #    in session_state and rerun so the question/answer render
                #    above the input on the next pass.
                user_question = st.chat_input(
                    "Ask anything about your PDF…",
                    key=f"qa_input_{active_session_id}",
                )
                if user_question:
                    st.session_state[pending_key] = user_question
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — MULTI-DOC Q&A
# ═══════════════════════════════════════════════════════════════════════════════
with tab_multi:
    selected_ids = st.session_state.get("selected_pdf_ids", [])
    if not selected_ids:
        st.markdown("""
        <div style="border:1px solid #2A2A4A; border-radius:12px; background:#12122A;
                    padding:40px 24px; text-align:center;">
            <div style="color:#A89CFF; font-size:1.05rem; font-weight:600;">Multi-Document Search</div>
            <div style="color:#666; font-size:0.85rem; margin-top:8px;">
                Select multiple PDFs from the sidebar under <b>Multi-Doc Query</b>.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="color:#666; font-size:0.82rem; margin-bottom:12px; padding-left:2px;">
            Querying across <b style="color:#A89CFF;">{len(selected_ids)}</b> documents
        </div>
        """, unsafe_allow_html=True)

        col_sessions_m, col_chat_m = st.columns([1, 3], gap="medium")

        with col_sessions_m:
            active_multi_id = _render_chat_sessions_panel("multi", selected_ids)

        with col_chat_m:
            if not active_multi_id:
                st.markdown("""
                <div style="border:1px solid #2A2A4A; border-radius:12px; background:#12122A;
                            padding:40px 24px; text-align:center;">
                    <div style="color:#A89CFF; font-size:1.05rem; font-weight:600;">No conversation selected</div>
                    <div style="color:#666; font-size:0.85rem; margin-top:8px;">
                        Click <b>New chat</b> on the left to start a multi-doc conversation.
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                try:
                    session = api.get_chat_session(active_multi_id)
                    session_name = session.get("name") or "New chat"
                    messages = session.get("messages", [])
                except Exception as e:
                    st.error(f"Could not load session: {e}")
                    session_name = "New chat"
                    messages = []

                st.markdown(f"""
                <div style="border-bottom:1px solid #2A2A4A; padding:4px 2px 14px 2px; margin-bottom:14px;">
                    <div style="color:#E8E8F0; font-size:1.1rem; font-weight:600;">{session_name}</div>
                    <div style="color:#666; font-size:0.78rem; margin-top:2px;">{len(messages)} messages · {len(selected_ids)} documents</div>
                </div>
                """, unsafe_allow_html=True)

                if not messages:
                    st.markdown("""
                    <div style="color:#555; font-size:0.88rem; padding:32px 4px; text-align:center;">
                        Ask anything across your selected documents.
                    </div>
                    """, unsafe_allow_html=True)

                # 1. Render persisted messages
                for msg in messages:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])
                        if msg.get("sources") and msg["role"] == "assistant":
                            with st.expander("Sources", expanded=False):
                                for src in msg["sources"][:4]:
                                    st.caption(f"› {src}")

                # 2. Render the just-submitted question + streamed answer ABOVE the input
                multi_pending_key = f"_multi_pending_{active_multi_id}"
                multi_pending_question = st.session_state.pop(multi_pending_key, None)

                if multi_pending_question:
                    with st.chat_message("user"):
                        st.markdown(multi_pending_question)

                    with st.chat_message("assistant"):
                        thinking_ph_m = st.empty()
                        thinking_ph_m.markdown(
                            "<span style='color:#888;'>💭 _Searching across documents…_</span>",
                            unsafe_allow_html=True,
                        )
                        try:
                            result = api.ask_question_multi(
                                selected_ids, multi_pending_question, session_id=active_multi_id
                            )
                            answer = result.get("answer", "")
                            sources = result.get("sources", [])
                            thinking_ph_m.empty()

                            def _word_stream_m(text: str):
                                import time as _t
                                for word in text.split(" "):
                                    yield word + " "
                                    _t.sleep(0.015)
                            st.write_stream(_word_stream_m(answer))

                            if sources:
                                with st.expander("Sources", expanded=False):
                                    for src in sources[:4]:
                                        st.caption(f"› {src}")
                        except RuntimeError as e:
                            thinking_ph_m.empty()
                            st.error(str(e))
                        except Exception as e:
                            thinking_ph_m.empty()
                            st.error(f"Failed: {e}")

                # 3. Input ALWAYS at the bottom
                multi_q = st.chat_input(
                    "Ask across all selected documents…",
                    key=f"multi_qa_input_{active_multi_id}",
                )
                if multi_q:
                    st.session_state[multi_pending_key] = multi_q
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — QUIZ
# ═══════════════════════════════════════════════════════════════════════════════
with tab_quiz:
    if not current_pdf_id:
        st.markdown("""
        <div class="card" style="text-align:center; padding:32px;">
            <div style="font-size:3rem; margin-bottom:10px;">📝</div>
            <div style="color:#A89CFF; font-size:1.1rem; font-weight:600;">Quiz Generator</div>
            <div style="color:#666; font-size:0.88rem; margin-top:6px;">Select a PDF from the sidebar to generate a quiz</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="card-accent">', unsafe_allow_html=True)
        st.markdown("#### ⚙️ Quiz Settings")
        col1, col2, col3 = st.columns(3)
        with col1:
            q_count = st.slider("Questions", min_value=1, max_value=15, value=5)
        with col2:
            difficulty = st.selectbox("Difficulty", ["basic", "medium", "hard"],
                                      format_func=lambda x: {"basic":"🟢 Basic","medium":"🟡 Medium","hard":"🔴 Hard"}[x])
        with col3:
            q_type = st.selectbox(
                "Question Type",
                ["mcq", "true-false", "fill-in-blank", "short-answer"],
                format_func=lambda x: {
                    "mcq": "🔵 Multiple Choice",
                    "true-false": "⚖️ True / False",
                    "fill-in-blank": "✏️ Fill in the Blank",
                    "short-answer": "📝 Short Answer",
                }[x],
            )
        topic_filter = st.text_input(
            "🎯 Topic Filter (optional)",
            placeholder="e.g., photosynthesis, Newton's laws, chapter 3…",
        )
        button_labels = {
            "mcq": "🎲 Generate Multiple Choice Quiz",
            "true-false": "⚖️ Generate True / False Quiz",
            "fill-in-blank": "✏️ Generate Fill-in-the-Blank Quiz",
            "short-answer": "📝 Generate Short Answer Quiz",
        }
        if st.button(button_labels.get(q_type, "🎲 Generate Quiz"), type="primary", use_container_width=True):
            with st.spinner("✨ Generating your quiz…"):
                try:
                    result = api.generate_quiz(
                        pdf_identifier=current_pdf_id,
                        num_questions=q_count,
                        difficulty=difficulty,
                        question_type=q_type,
                        search_query=topic_filter or None,
                    )
                    st.session_state["quiz_questions"] = result.get("questions", [])
                    st.session_state["quiz_answers"]   = {}
                    st.session_state["quiz_submitted"] = False
                except RuntimeError as e:
                    msg = str(e)
                    if "temporarily unavailable" in msg.lower():
                        st.warning(
                            "⚠️ **Quiz temporarily unavailable** — the AI service is "
                            "currently down. Please try **📋 Summary** or **💬 Q&A** "
                            "from the Workspace tabs instead. Quiz will work again "
                            "as soon as the service is back online.",
                            icon="🔧",
                        )
                    else:
                        st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)

        questions = st.session_state.get("quiz_questions", [])
        if questions:
            st.divider()
            diff_color = {"basic": "badge-green", "medium": "badge-orange", "hard": "badge-red"}.get(difficulty, "badge-purple")
            st.markdown(f"""
            <div style="margin-bottom:14px;">
                <span style="font-size:1.1rem; font-weight:700; color:#E8E8F0;">{len(questions)} Questions</span>
                &nbsp;<span class="badge {diff_color}">{difficulty.title()}</span>
                &nbsp;<span class="badge badge-purple">{q_type.replace('-',' ').title()}</span>
            </div>
            """, unsafe_allow_html=True)

            with st.form("quiz_form"):
                for i, q in enumerate(questions):
                    st.markdown(f"""
                    <div style="background:#12122A; border:1px solid #2A2A4A; border-radius:10px;
                                padding:14px 18px; margin-bottom:10px;">
                        <div style="font-size:0.82rem; color:#6C63FF; font-weight:600; margin-bottom:6px;">QUESTION {i+1}</div>
                        <div style="color:#E8E8F0; font-size:0.96rem; font-weight:500;">{q.get('question', '')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    qtype = q.get("question_type", "mcq")

                    if qtype == "mcq":
                        opts    = q.get("options", {})
                        choices = [f"{k}) {v}" for k, v in opts.items() if v and v != "Not applicable"]
                        if choices:
                            ans = st.radio(f"q_{i}", choices, index=None,
                                           label_visibility="collapsed", key=f"quiz_q_{i}")
                            if ans:
                                st.session_state["quiz_answers"][i] = ans[0]
                    elif qtype == "true-false":
                        ans = st.radio(f"q_{i}", ["True", "False"], index=None,
                                       label_visibility="collapsed", key=f"quiz_q_{i}", horizontal=True)
                        if ans:
                            st.session_state["quiz_answers"][i] = ans
                    else:
                        ans = st.text_input(
                            f"Answer {i+1}", label_visibility="collapsed",
                            placeholder="Type your answer here…", key=f"quiz_q_{i}",
                        )
                        if ans:
                            st.session_state["quiz_answers"][i] = ans

                submitted = st.form_submit_button("✅ Submit & Check Answers", use_container_width=True, type="primary")

            if submitted or st.session_state.get("quiz_submitted"):
                st.session_state["quiz_submitted"] = True
                score = 0
                results_data = []
                for i, q in enumerate(questions):
                    qtype    = q.get("question_type", "mcq")
                    correct  = q.get("correct_answer", "")
                    user_ans = st.session_state["quiz_answers"].get(i, "")
                    if qtype == "mcq":
                        is_correct = bool(user_ans) and user_ans.upper() == correct.upper()
                    elif qtype == "true-false":
                        is_correct = bool(user_ans) and user_ans.lower() == correct.lower()
                    else:
                        is_correct = bool(user_ans) and user_ans.strip().lower() == correct.strip().lower()
                    if is_correct:
                        score += 1
                    results_data.append((i, q, qtype, correct, user_ans, is_correct))

                pct = int(score / len(questions) * 100) if questions else 0
                grade_color = "#00E870" if pct >= 80 else ("#FFB347" if pct >= 60 else "#FF8080")
                grade_msg   = "🎉 Excellent!" if pct >= 80 else ("👍 Good job!" if pct >= 60 else "📖 Keep studying!")

                st.markdown(f"""
                <div style="background:linear-gradient(135deg, #1A1040, #0D1B2E); border:1px solid #6C63FF55;
                            border-radius:14px; padding:20px 24px; margin:16px 0; text-align:center;">
                    <div style="font-size:2.5rem; font-weight:800; color:{grade_color};">{score}/{len(questions)}</div>
                    <div style="font-size:1rem; color:#aaa; margin:4px 0;">{grade_msg} · {pct}%</div>
                    <div class="score-bar-bg" style="margin: 10px auto; max-width:300px;">
                        <div class="score-bar-fill" style="width:{pct}%;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("#### Detailed Results")
                for i, q, qtype, correct, user_ans, is_correct in results_data:
                    icon = "✅" if is_correct else "❌"
                    with st.expander(f"{icon} Q{i+1}: {q.get('question','')[:65]}…", expanded=not is_correct):
                        if qtype == "mcq":
                            for k, v in q.get("options", {}).items():
                                if v and v != "Not applicable":
                                    if k == correct:
                                        st.markdown(f"🟢 **{k})** {v} ← correct")
                                    elif k == user_ans and k != correct:
                                        st.markdown(f"🔴 **{k})** {v} ← your answer")
                                    else:
                                        st.markdown(f"⚪ {k}) {v}")
                        else:
                            st.markdown(f"**Your answer:** {user_ans or '_not answered_'}")
                            st.markdown(f"**Correct answer:** `{correct}`")
                        if q.get("explanation"):
                            st.info(f"💡 {q['explanation']}")

                if st.button("🔄 Try Another Quiz", type="primary"):
                    st.session_state["quiz_questions"] = []
                    st.session_state["quiz_answers"]   = {}
                    st.session_state["quiz_submitted"] = False
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_summary:
    if not current_pdf_id:
        st.markdown("""
        <div class="card" style="text-align:center; padding:32px;">
            <div style="font-size:3rem; margin-bottom:10px;">📋</div>
            <div style="color:#A89CFF; font-size:1.1rem; font-weight:600;">Document Summarizer</div>
            <div style="color:#666; font-size:0.88rem; margin-top:6px;">Select a PDF to generate summaries</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        col_left, col_right = st.columns([3, 2])
        with col_left:
            st.markdown('<div class="card-accent">', unsafe_allow_html=True)
            st.markdown("#### ⚙️ Summary Settings")
            topic_input = st.text_input(
                "🎯 Topic or Instruction (optional)",
                placeholder="e.g., Summarize chapter 2 · Focus on formulas · Key takeaways only…",
            )
            summary_type = st.radio(
                "Type", ["Short", "Detailed", "Both"], horizontal=True,
                help="Short = 2-3 paragraphs · Detailed = comprehensive · Both = side by side",
            )
            type_map = {"Short": "short", "Detailed": "detailed", "Both": "both"}
            if st.button("📋 Generate Summary", type="primary", use_container_width=True):
                with st.spinner("✨ Summarizing…"):
                    try:
                        result = api.generate_summary(
                            pdf_identifier=current_pdf_id,
                            summary_type=type_map[summary_type],
                            topic=topic_input.strip() or None,
                        )
                        st.session_state["last_summary"] = result
                    except RuntimeError as e:
                        st.error(str(e))
            st.markdown('</div>', unsafe_allow_html=True)

        with col_right:
            st.markdown("""
            <div class="card" style="text-align:center; padding:24px 16px;">
                <div style="font-size:2.4rem;">🤖</div>
                <div style="color:#A89CFF; font-weight:600; margin-top:8px;">AI Summarizer</div>
                <div style="color:#555; font-size:0.82rem; margin-top:6px; line-height:1.5;">
                    Powered by local LLM<br>RAG-enhanced context<br>Topic-aware summaries
                </div>
            </div>
            """, unsafe_allow_html=True)

        summary_result = st.session_state.get("last_summary")
        if summary_result:
            st.divider()
            if "short_summary" in summary_result and "detailed_summary" in summary_result:
                cs, cd = st.columns(2)
                with cs:
                    st.markdown("""
                    <div style="background:#12122A; border:1px solid #6C63FF44; border-radius:10px;
                                padding:14px; margin-bottom:6px;">
                        <div style="color:#A89CFF; font-weight:700; font-size:0.85rem; margin-bottom:8px;">📌 SHORT SUMMARY</div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.markdown(summary_result["short_summary"])
                with cd:
                    st.markdown("""
                    <div style="background:#12122A; border:1px solid #6C63FF44; border-radius:10px;
                                padding:14px; margin-bottom:6px;">
                        <div style="color:#A89CFF; font-weight:700; font-size:0.85rem; margin-bottom:8px;">📄 DETAILED SUMMARY</div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.markdown(summary_result["detailed_summary"])
            elif "summary" in summary_result:
                st.markdown(f"#### 📄 {summary_result.get('type', 'Summary').title()}")
                st.markdown(summary_result["summary"])

            if st.button("🔊 Convert to Audio", key="sum_to_audio"):
                text = summary_result.get("short_summary") or summary_result.get("summary") or ""
                if text:
                    with st.spinner("Generating audio…"):
                        try:
                            ar = api.generate_audio(text, current_pdf_id)
                            st.session_state["last_audio_filename"] = ar.get("filename")
                            st.session_state["last_audio_text"]     = text
                            st.success("✅ Audio ready! Switch to the Audio tab.")
                        except RuntimeError as e:
                            st.error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — AUDIO
# ═══════════════════════════════════════════════════════════════════════════════
with tab_audio:
    if not current_pdf_id:
        st.markdown("""
        <div style="border:1px solid #2A2A4A; border-radius:12px; background:#12122A;
                    padding:40px 24px; text-align:center;">
            <div style="color:#A89CFF; font-size:1.05rem; font-weight:600;">Audio</div>
            <div style="color:#666; font-size:0.85rem; margin-top:8px;">
                Select a PDF from the sidebar to enable voice chat and text-to-speech.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        voice_subtab, narr_subtab = st.tabs(["💬 Voice Chat", "📢 Summary Narration"])

        # ═══════════════════════════════════════════════════════════════════════
        # VOICE CHAT — talk to the PDF
        # ═══════════════════════════════════════════════════════════════════════
        with voice_subtab:
            try:
                from streamlit_mic_recorder import speech_to_text
                stt_available = True
            except ImportError:
                stt_available = False

            if not stt_available:
                st.warning(
                    "**streamlit-mic-recorder** is not installed. "
                    "Stop Streamlit, install it into your venv, then restart."
                )
                st.code("venv\\Scripts\\pip install streamlit-mic-recorder", language="text")
            else:
                _pdf_list = st.session_state.get("pdf_list", []) or []
                current_pdf_name = next(
                    (p.get("filename", "this PDF") for p in _pdf_list
                     if p.get("pdf_identifier") == current_pdf_id),
                    "this PDF",
                )
                st.markdown(f"""
                <div style="background:linear-gradient(135deg, #1A1040 0%, #0D1B3E 100%);
                            border:1px solid #6C63FF44; border-radius:12px;
                            padding:12px 16px; margin-bottom:14px;">
                    <div style="color:#E8E8F0; font-size:0.95rem; font-weight:600;">🎙️ Voice Chat</div>
                    <div style="color:#888; font-size:0.78rem; margin-top:2px;">
                        Grounded on <b>{current_pdf_name}</b> · remembers the last few exchanges
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if "voice_chat_history" not in st.session_state:
                    st.session_state["voice_chat_history"] = []

                # Render history: show the user's query text, assistant replies as audio only
                import requests as _req
                for msg in st.session_state["voice_chat_history"]:
                    with st.chat_message(msg["role"]):
                        if msg["role"] == "user":
                            st.markdown(msg["content"])
                        else:
                            fn = msg.get("audio_filename")
                            if fn:
                                try:
                                    audio_bytes = _req.get(api.get_audio_url(fn), timeout=30).content
                                    st.audio(audio_bytes, format="audio/wav",
                                             autoplay=bool(msg.get("_autoplay")))
                                except Exception as ae:
                                    st.caption(f"Audio unavailable: {ae}")
                            else:
                                st.caption("Audio unavailable.")

                # Mic + new-chat row
                col_mic, col_new = st.columns([3, 1])
                with col_mic:
                    spoken_text = speech_to_text(
                        language="en",
                        start_prompt="🎙️ Tap to Talk",
                        stop_prompt="⏹️ Stop",
                        just_once=True,
                        use_container_width=True,
                        key="voice_chat_stt",
                    )
                with col_new:
                    if st.button("🆕 New", use_container_width=True,
                                 help="Clear voice chat history"):
                        st.session_state["voice_chat_history"] = []
                        st.rerun()


                if spoken_text and spoken_text.strip():
                    # disable autoplay on previous replies so only the newest plays
                    for m in st.session_state["voice_chat_history"]:
                        m["_autoplay"] = False

                    st.session_state["voice_chat_history"].append({
                        "role": "user",
                        "content": spoken_text.strip(),
                    })

                    history_for_ai = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state["voice_chat_history"][:-1]
                        if m["role"] in ("user", "assistant")
                    ]

                    with st.spinner("🤔 Thinking…"):
                        try:
                            result = api.ask_question(
                                current_pdf_id, spoken_text.strip(),
                                history_for_ai[-6:],
                            )
                            answer = result.get("answer", "No answer returned.")

                            # Generate TTS (unique filename per utterance: no pdf_identifier)
                            audio_fn = None
                            try:
                                audio_res = api.generate_audio(answer)
                                audio_fn = audio_res.get("filename")
                            except Exception as ae:
                                st.warning(f"TTS failed, text answer below: {ae}")

                            st.session_state["voice_chat_history"].append({
                                "role": "assistant",
                                "content": answer,
                                "audio_filename": audio_fn,
                                "_autoplay": True,
                            })
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"Voice chat failed: {e}")

        # ═══════════════════════════════════════════════════════════════════════
        # SUMMARY NARRATION — existing text-to-speech feature
        # ═══════════════════════════════════════════════════════════════════════
        with narr_subtab:
            col_a1, col_a2 = st.columns([3, 2])
            with col_a1:
                st.markdown('<div class="card-accent">', unsafe_allow_html=True)
                st.markdown("#### 🎙️ Convert Text to Speech")
                audio_text = st.text_area(
                    "Text",
                    value=st.session_state.get("last_audio_text", ""),
                    placeholder="Enter text here, or generate a summary first and click 'Convert to Audio'…",
                    height=140,
                    label_visibility="collapsed",
                )
                if st.button("🎙️ Generate Audio", type="primary", use_container_width=True):
                    if not audio_text.strip():
                        st.error("Please enter some text.")
                    else:
                        with st.spinner("🎵 Generating audio…"):
                            try:
                                result = api.generate_audio(audio_text, current_pdf_id)
                                st.session_state["last_audio_filename"] = result.get("filename")
                                st.session_state["last_audio_text"]     = audio_text
                                st.success(f"✅ Done! Duration ≈ {result.get('duration_estimate', 0):.1f}s")
                            except RuntimeError as e:
                                st.error(str(e))
                st.markdown('</div>', unsafe_allow_html=True)

            with col_a2:
                audio_file = st.session_state.get("last_audio_filename")
                if audio_file:
                    st.markdown("""
                    <div style="background:#0D2010; border:1px solid #00C85355; border-radius:12px;
                                padding:16px; text-align:center; margin-bottom:14px;">
                        <div style="font-size:2rem;">🎵</div>
                        <div style="color:#00E870; font-weight:600; margin-top:6px;">Audio Ready</div>
                    </div>
                    """, unsafe_allow_html=True)
                    try:
                        import requests as req
                        audio_url   = api.get_audio_url(audio_file)
                        audio_bytes = req.get(audio_url, timeout=30).content
                        st.audio(audio_bytes, format="audio/wav")
                        st.download_button(
                            "⬇️ Download Audio", data=audio_bytes,
                            file_name=audio_file, mime="audio/wav",
                            use_container_width=True,
                        )
                    except Exception as e:
                        st.warning(f"Preview unavailable: {e}")
                else:
                    st.markdown("""
                    <div style="background:#12122A; border:1px solid #2A2A4A; border-radius:12px;
                                padding:24px; text-align:center; color:#555; font-size:0.88rem;">
                        Generate audio and it will appear here
                    </div>
                    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — VIDEO
# ═══════════════════════════════════════════════════════════════════════════════
with tab_video:
    if not current_pdf_id:
        st.markdown("""
        <div style="border:1px solid #2A2A4A; border-radius:12px; background:#12122A;
                    padding:40px 24px; text-align:center;">
            <div style="color:#A89CFF; font-size:1.05rem; font-weight:600;">Animated Video Generator</div>
            <div style="color:#666; font-size:0.85rem; margin-top:8px;">
                Select a PDF from the sidebar to generate a narrated educational video from it.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        col_v1, col_v2 = st.columns([3, 2])
        with col_v1:
            st.markdown('<div class="card-accent">', unsafe_allow_html=True)
            st.markdown("#### 🎬 Animated Video Generator")
            st.caption("Generates a narrated slideshow-style MP4 (60-90 seconds) from your PDF.")
            video_query = st.text_area(
                "What should this video cover?",
                value=st.session_state.get("last_video_query", ""),
                placeholder="e.g., Explain the water cycle, Summarize chapter 2, What are the main causes of climate change?",
                height=110,
            )

            video_style_label = st.radio(
                "Animation style",
                ["Animated slides", "Manim animations"],
                index=0,
                horizontal=True,
                help=(
                    "Animated slides: fast (~3-5 min), build-up reveal + Ken-Burns zoom + fades.\n"
                    "Manim animations: slower (~6-12 min), real motion graphics with text fade-in and "
                    "drawn underlines. Falls back to slides if Manim fails."
                ),
            )
            video_style = "slides" if video_style_label == "Animated slides" else "manim"

            st.caption(
                "Leave the query empty to generate from the full PDF overview. "
                "Rendering time: ~3-5 min for slides, ~6-12 min for Manim."
            )

            if st.button("🎬 Generate Video", type="primary", use_container_width=True):
                spin_msg = (
                    "🎞️ Rendering Manim animations… (script → scenes → audio → Manim → mux)"
                    if video_style == "manim"
                    else "🎞️ Rendering animated slides… (script → scenes → frames → audio → compose)"
                )
                with st.spinner(spin_msg):
                    try:
                        result = api.generate_video(
                            pdf_identifier=current_pdf_id,
                            query=video_query.strip() or None,
                            style=video_style,
                        )
                        st.session_state["last_video_result"] = result
                        st.session_state["last_video_query"]  = video_query
                        actual_style = result.get("style", video_style)
                        if result.get("cached"):
                            st.success(f"✅ Loaded a previously-rendered {actual_style} video from cache.")
                        else:
                            note = ""
                            if video_style == "manim" and actual_style == "slides":
                                note = " (Manim render failed, fell back to slides)"
                            st.success(
                                f"✅ Video ready — {result.get('scenes_count', '?')} scenes, "
                                f"{result.get('duration_estimate', 0):.1f}s long, "
                                f"style: {actual_style}{note}."
                            )
                    except RuntimeError as e:
                        st.error(str(e))
            st.markdown('</div>', unsafe_allow_html=True)

        with col_v2:
            st.markdown("""
            <div class="card" style="padding:20px;">
                <div style="color:#A89CFF; font-weight:600;">How it works</div>
                <div style="color:#888; font-size:0.82rem; margin-top:8px; line-height:1.6;">
                    1. AI writes a 60-90s narration script<br>
                    2. Script splits into 4-6 scenes<br>
                    3. Each scene becomes an animated slide<br>
                    4. Local TTS narrates each slide<br>
                    5. MoviePy renders everything to MP4
                </div>
            </div>
            """, unsafe_allow_html=True)

        result = st.session_state.get("last_video_result")
        if result and result.get("filename"):
            st.divider()
            st.markdown(f"#### 🎬 {result.get('filename')}")
            try:
                st.video(api.get_video_url(result["filename"]))
            except Exception as e:
                st.error(f"Could not load video: {e}")

            if result.get("scenes"):
                with st.expander("📑 Scene breakdown", expanded=False):
                    for i, sc in enumerate(result["scenes"], start=1):
                        st.markdown(f"**Scene {i}: {sc.get('title','')}**")
                        for b in sc.get("bullets", []):
                            st.markdown(f"- {b}")

            if result.get("script"):
                with st.expander("📜 Full narration script", expanded=False):
                    st.text_area("script", value=result["script"], height=220,
                                 disabled=True, label_visibility="collapsed")
                    st.download_button(
                        "⬇️ Download Script (.txt)", data=result["script"],
                        file_name="video_script.txt", use_container_width=True,
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 7 — CHAT HISTORY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_history:
    col_hf, col_hc = st.columns([3, 1])
    with col_hf:
        filter_pdf = st.checkbox("Show only current PDF's history", value=True)
    with col_hc:
        if st.button("🗑️ Clear", key="clear_hist"):
            with st.spinner("Clearing…"):
                try:
                    api.clear_chat_history(current_pdf_id if filter_pdf else None)
                    st.success("Cleared.")
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))

    with st.spinner("Loading…"):
        try:
            doc_id       = current_pdf_id if (filter_pdf and current_pdf_id) else None
            history_data = api.get_chat_history(document_id=doc_id, limit=50)
            history      = history_data.get("history", [])
        except RuntimeError as e:
            st.error(str(e))
            history = []

    if not history:
        st.markdown("""
        <div class="card" style="text-align:center; padding:28px;">
            <div style="font-size:2.4rem;">🕐</div>
            <div style="color:#A89CFF; font-weight:600; margin-top:8px;">No History Yet</div>
            <div style="color:#666; font-size:0.88rem; margin-top:6px;">Your Q&amp;A sessions will appear here</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f'<p style="color:#666; font-size:0.82rem;">{len(history)} past exchanges</p>', unsafe_allow_html=True)
        for item in reversed(history):
            ts   = str(item.get("timestamp", ""))[:19].replace("T", " ")
            conf = item.get("confidence", "")
            conf_badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "")
            with st.expander(f"🕐 {ts}  ·  {item.get('question', '')[:55]}…"):
                st.markdown(f"""
                <div style="background:#1A1A2E; border-radius:8px; padding:10px 14px; margin-bottom:8px;">
                    <span style="font-size:0.78rem; color:#6C63FF; font-weight:700;">QUESTION</span><br>
                    <span style="color:#E8E8F0;">{item.get('question', '')}</span>
                </div>
                <div style="background:#12122A; border-radius:8px; padding:10px 14px;">
                    <span style="font-size:0.78rem; color:#00C853; font-weight:700;">ANSWER</span><br>
                    <span style="color:#C8C8D8;">{item.get('answer', '')}</span>
                </div>
                """, unsafe_allow_html=True)
                if item.get("sources"):
                    st.caption("📖 " + " · ".join(str(s)[:60] for s in item["sources"][:2]))
                if conf_badge:
                    st.caption(f"Confidence: {conf_badge} {conf}")
