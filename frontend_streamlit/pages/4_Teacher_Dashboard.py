"""
Teacher Dashboard — profile, my classes/students, assignment builder
(manual + AI-assisted), and per-assignment submission review with
auto-grading + grade override.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import streamlit as st
from utils.session_utils import (
    init_session_state, require_teacher, logout, class_section,
)
from utils.api_client import APIClient
from utils.themes import apply_theme, render_theme_selector

st.set_page_config(
    page_title="Teacher Dashboard — School LLM",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
button[kind="headerNoPadding"] {
    visibility: visible !important; display: flex !important; z-index: 999999 !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D0D1F 0%, #0A0A18 100%);
    border-right: 1px solid #2A2A4A;
}
.stApp { background: #0E1117; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 1rem !important; }

.card {
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    border: 1px solid #2E2E5E;
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 14px;
}
/* .hero-t was renamed to .hero so themes.py's themed hero rule applies
   uniformly across all three dashboards (Student / Teacher / Admin). */
.badge { display:inline-block; padding:3px 10px; border-radius:14px; font-size:0.74rem; font-weight:600; }
.badge-orange { background:#3A1A0A; color:#FFB347; border:1px solid #FFB34755; }
.badge-green  { background:#0A2A12; color:#00E870; border:1px solid #00C85355; }
.badge-blue   { background:#0A2030; color:#6BC8FF; border:1px solid #6BC8FF55; }
.badge-grey   { background:#1A1A2A; color:#888; border:1px solid #444; }
</style>
""", unsafe_allow_html=True)

init_session_state()
require_teacher()

# Apply the user's chosen color theme
apply_theme()

api = APIClient(st.session_state.get("token"))

ALL_SUBJECTS = ["Math", "Science", "English", "Social", "Computer"]
ALL_CS = [f"{c}{s}" for c in range(1, 11) for s in ("A", "B", "C")]

# Question types — keep keys in sync with backend `quiz.py` `question_type`.
_QUESTION_TYPES = ["mcq", "true-false", "fill-in-blank", "short-answer", "long-answer"]
_TYPE_LABELS = {
    "mcq":            "🎲 MCQ",
    "true-false":     "⚖️ True / False",
    "fill-in-blank":  "✏️ Fill in the Blank",
    "short-answer":   "📝 Short Answer",
    "long-answer":    "📜 Long Answer",
}


# ─────────────────────────────────────────────────────────────────────────────
# Cached fetches — same pattern as admin dashboard, prevents popup blink.
# ─────────────────────────────────────────────────────────────────────────────
def _cache():
    return st.session_state.setdefault("_teacher_cache", {})


def _cached(key: str, fn, spinner: str = "Loading…"):
    c = _cache()
    if key in c:
        return c[key]
    with st.spinner(spinner):
        c[key] = fn()
    return c[key]


def _bust(*keys):
    c = _cache()
    for k in keys:
        c.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — profile + nav hint + logout
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    name = st.session_state.get("full_name") or st.session_state.get("username", "Teacher")
    email = st.session_state.get("user_email", "")
    subjects = st.session_state.get("subjects_taught") or []
    classes = st.session_state.get("assigned_classes") or []

    st.markdown(f"""
    <div class="card" style="text-align:center;">
        <div style="font-size:2.2rem; margin-bottom:6px;">📖</div>
        <div style="font-size:1rem; font-weight:700; color:var(--text);">{name}</div>
        <div style="font-size:0.78rem; color:#888; margin-top:3px;">{email}</div>
        <div style="margin-top:10px;">
            <span class="badge badge-orange">Teacher</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<p style="font-size:0.78rem; color:#888; margin:0 0 4px 0;">Subjects</p>', unsafe_allow_html=True)
    if subjects:
        st.markdown(" ".join(f'<span class="badge badge-blue">{s}</span>' for s in subjects), unsafe_allow_html=True)
    else:
        st.caption("_(none assigned — ask admin)_")

    st.markdown('<p style="font-size:0.78rem; color:#888; margin:12px 0 4px 0;">Classes</p>', unsafe_allow_html=True)
    if classes:
        st.markdown(" ".join(f'<span class="badge badge-green">{c}</span>' for c in classes), unsafe_allow_html=True)
    else:
        st.caption("_(none assigned — ask admin)_")

    st.markdown('<hr style="border-color:#2A2A4A; margin:14px 0;">', unsafe_allow_html=True)
    st.markdown(
        '<p style="font-size:0.82rem; font-weight:700; color:#FFB347; margin:0 0 6px 0;">UPLOAD PDF</p>',
        unsafe_allow_html=True,
    )

    teacher_pdf = st.file_uploader(
        "Upload a PDF",
        type=["pdf"],
        label_visibility="collapsed",
        key="teacher_pdf_upload",
        help="Upload a syllabus / chapter PDF. Use it as a source on the **New Assignment → Use AI** tab.",
    )
    if teacher_pdf is not None:
        file_key = f"{teacher_pdf.name}_{teacher_pdf.size}"
        if st.session_state.get("teacher_last_upload_key") != file_key:
            with st.spinner("Uploading…"):
                try:
                    api.upload_pdf(teacher_pdf.getvalue(), teacher_pdf.name)
                    st.session_state["teacher_last_upload_key"] = file_key
                    st.success(f"Uploaded: {teacher_pdf.name}")
                except Exception as e:
                    st.error(f"Upload failed: {e}")
    st.caption("200 MB max · PDF only")

    # Show this teacher's uploaded PDFs
    try:
        my_pdfs_resp = api.get_my_pdfs(limit=50)
        my_pdfs = my_pdfs_resp.get("pdfs", []) or []
    except Exception:
        my_pdfs = []
    if my_pdfs:
        st.markdown(
            '<p style="font-size:0.78rem; font-weight:700; color:#888; '
            'margin:14px 0 4px 0;">YOUR PDFs</p>',
            unsafe_allow_html=True,
        )
        for p in my_pdfs[:6]:
            st.markdown(
                f"<div style='font-size:0.78rem; color:var(--text-muted); padding:2px 0;'>"
                f"📄 {p.get('filename', '?')[:36]}</div>",
                unsafe_allow_html=True,
            )
        if len(my_pdfs) > 6:
            st.caption(f"…and {len(my_pdfs) - 6} more")

    st.markdown('<hr style="border-color:#2A2A4A; margin:14px 0;">', unsafe_allow_html=True)

    if st.button("🔄 Refresh data", width="stretch", key="t_refresh"):
        st.session_state["_teacher_cache"] = {}
        st.rerun()

    # ── Theme selector ──────────────────────────────────────────────────
    st.markdown('<hr style="border-color:var(--border-soft); margin:14px 0;">', unsafe_allow_html=True)
    render_theme_selector(api_client=api)

    st.markdown('<hr style="border-color:var(--border-soft); margin:14px 0;">', unsafe_allow_html=True)
    if st.button("🚪 Logout", width="stretch", key="t_logout"):
        logout()
        st.switch_page("pages/1_Login.py")


# ─────────────────────────────────────────────────────────────────────────────
# HERO
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="hero">
    <div style="font-size:0.78rem; color:var(--accent); font-weight:700; letter-spacing:1px;
                text-transform:uppercase;">Teacher Workspace</div>
    <h2 style="margin:4px 0 4px 0; font-size:1.7rem; color:var(--text-strong);">
        Welcome back, {name} 👋
    </h2>
    <div style="color:var(--text-muted); font-size:0.92rem;">
        Build assignments, post them to your classes, and review auto-graded submissions.
    </div>
</div>
""", unsafe_allow_html=True)

if not classes or not subjects:
    st.warning(
        "Your account is missing class or subject assignments. Ask the admin to set "
        "**Subjects you teach** and **Assigned classes** for your account before using this dashboard."
    )

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_home, tab_assignments, tab_new, tab_students = st.tabs([
    "🏠 Home", "📋 My Assignments", "➕ New Assignment", "👨‍🎓 My Students",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HOME (profile + recent assignments + quick stats)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_home:
    try:
        a_resp = _cached("assignments", api.teacher_list_assignments,
                         spinner="Loading your assignments…")
        my_assignments = a_resp.get("assignments", []) or []
    except Exception as e:
        st.error(f"Could not load assignments: {e}")
        my_assignments = []

    try:
        s_resp = _cached("students", api.teacher_list_students,
                         spinner="Loading your students…")
        all_students = s_resp.get("students", []) or []
        by_class = s_resp.get("by_class", {}) or {}
    except Exception as e:
        st.error(f"Could not load students: {e}")
        all_students = []
        by_class = {}

    total_subs = sum(int(a.get("submission_count") or 0) for a in my_assignments)
    published = sum(1 for a in my_assignments if a.get("status") == "published")
    drafts = sum(1 for a in my_assignments if a.get("status") == "draft")

    st.markdown(f"""
    <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:18px;">
        <div class="card" style="text-align:center;">
            <div style="font-size:1.6rem; font-weight:800; color:#FFB347;">{len(my_assignments)}</div>
            <div style="color:#888; font-size:0.82rem;">📋 Total assignments</div>
        </div>
        <div class="card" style="text-align:center;">
            <div style="font-size:1.6rem; font-weight:800; color:#00E870;">{published}</div>
            <div style="color:#888; font-size:0.82rem;">✅ Published</div>
        </div>
        <div class="card" style="text-align:center;">
            <div style="font-size:1.6rem; font-weight:800; color:#6BC8FF;">{drafts}</div>
            <div style="color:#888; font-size:0.82rem;">📝 Drafts</div>
        </div>
        <div class="card" style="text-align:center;">
            <div style="font-size:1.6rem; font-weight:800; color:var(--accent-soft);">{len(all_students)}</div>
            <div style="color:#888; font-size:0.82rem;">👨‍🎓 Students in your classes</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### Recent assignments")
    if not my_assignments:
        st.info("No assignments yet. Use the **➕ New Assignment** tab to create one.")
    else:
        for a in my_assignments[:5]:
            status = a.get("status", "draft")
            badge_cls = {"published": "badge-green", "closed": "badge-grey", "draft": "badge-blue"}.get(status, "badge-blue")
            due = a.get("due_date") or ""
            due_str = str(due)[:16].replace("T", " ") if due else "—"
            st.markdown(f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <strong>{a.get('title','(untitled)')}</strong>
                        <span class="badge {badge_cls}" style="margin-left:8px;">{status}</span>
                        <span class="badge badge-blue" style="margin-left:4px;">{a.get('class_section','?')}</span>
                        {f'<span class="badge badge-orange" style="margin-left:4px;">{a.get("subject")}</span>' if a.get('subject') else ''}
                    </div>
                    <div style="color:#888; font-size:0.82rem;">
                        {len(a.get('questions') or [])} Q · Submissions: {a.get('submission_count', 0)} · Due: {due_str}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — MY ASSIGNMENTS (list + per-assignment submissions + override)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_assignments:
    try:
        a_resp = _cached("assignments", api.teacher_list_assignments,
                         spinner="Loading your assignments…")
        my_assignments = a_resp.get("assignments", []) or []
    except Exception as e:
        st.error(f"Could not load assignments: {e}")
        my_assignments = []

    if not my_assignments:
        st.info("No assignments yet.")
    else:
        for a in my_assignments:
            aid = a.get("id")
            status = a.get("status", "draft")
            badge_cls = {"published": "badge-green", "closed": "badge-grey", "draft": "badge-blue"}.get(status, "badge-blue")
            due = a.get("due_date") or ""
            due_str = str(due)[:16].replace("T", " ") if due else "—"

            with st.expander(
                f"{a.get('title','(untitled)')}  ·  {a.get('class_section','?')}  ·  "
                f"{status} · {len(a.get('questions') or [])} Q · "
                f"Subs: {a.get('submission_count', 0)}",
                expanded=False,
            ):
                st.caption(
                    f"Subject: {a.get('subject') or '—'}  ·  Due: {due_str}  ·  "
                    f"Created: {str(a.get('created_at',''))[:16].replace('T',' ')}"
                )
                if a.get("description"):
                    st.markdown(a["description"])

                ec1, ec2, ec3 = st.columns([1, 1, 1])
                with ec1:
                    if status == "draft":
                        if st.button("📤 Publish", key=f"pub_{aid}", width="stretch", type="primary"):
                            try:
                                api.teacher_update_assignment(aid, {"status": "published"})
                                _bust("assignments")
                                st.toast("Published", icon="✅")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                    elif status == "published":
                        if st.button("🔒 Close", key=f"close_{aid}", width="stretch"):
                            try:
                                api.teacher_update_assignment(aid, {"status": "closed"})
                                _bust("assignments")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                with ec2:
                    if st.button("🗑️ Delete", key=f"del_{aid}", width="stretch"):
                        try:
                            api.teacher_delete_assignment(aid)
                            _bust("assignments")
                            st.toast("Deleted", icon="🗑️")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with ec3:
                    pass

                # Questions overview
                st.markdown("**Questions**")
                for qi, q in enumerate(a.get("questions") or [], start=1):
                    with st.container(border=True):
                        st.markdown(f"**Q{qi}.** {q.get('question','')}")
                        st.caption(
                            f"Marks: {q.get('marks', 10)} · "
                            f"Target class: {q.get('target_class') or '—'} · "
                            f"Subject: {q.get('subject') or '—'}"
                        )
                        if q.get("expected_answer"):
                            st.caption(f"_Expected:_ {q['expected_answer']}")
                        if q.get("keywords"):
                            st.caption(f"_Keywords:_ {', '.join(q['keywords'])}")

                # Submissions
                st.markdown("**Submissions**")
                try:
                    full = api.teacher_get_assignment(aid)
                    subs = full.get("submissions", []) or []
                except Exception as e:
                    st.error(f"Could not load submissions: {e}")
                    subs = []

                if not subs:
                    st.caption("_No submissions yet._")
                else:
                    for s in subs:
                        sid = s.get("id")
                        score_color = "#00E870" if (s.get("percent") or 0) >= 70 else (
                            "#FFB347" if (s.get("percent") or 0) >= 40 else "#FF8080"
                        )
                        with st.expander(
                            f"📝 {s.get('student_email','?')}  —  "
                            f"{s.get('total_score',0)} / {s.get('total_max',0)}  "
                            f"({s.get('percent',0)}%)",
                            expanded=False,
                        ):
                            for ai_idx, ans in enumerate(s.get("answers") or []):
                                qi = ans.get("question_index", ai_idx)
                                q_text = (a.get("questions") or [{}])[qi].get("question") if qi < len(a.get("questions") or []) else f"Q{qi+1}"
                                ovr = ans.get("teacher_override") or {}
                                effective = ovr.get("score") if ovr else ans.get("ai_score")
                                with st.container(border=True):
                                    st.markdown(f"**Q{qi+1}. {q_text}**")
                                    st.markdown(f"_Student:_ {ans.get('student_answer') or '_(empty)_'}")
                                    st.caption(
                                        f"AI: {ans.get('ai_score', 0):.1f}/10 ({ans.get('ai_method','?')}) · "
                                        f"Marks: {ans.get('marks', 10)} · "
                                        f"Scaled: {ans.get('scaled_score', 0)}"
                                    )
                                    if ovr:
                                        st.caption(
                                            f"⚖️ Teacher override: **{ovr.get('score')}/10** "
                                            f"({ovr.get('comment') or 'no comment'})"
                                        )

                                    oc1, oc2, oc3 = st.columns([1, 3, 1])
                                    with oc1:
                                        new_score = st.number_input(
                                            "Override (0-10)", 0.0, 10.0,
                                            value=float(effective or 0.0), step=0.5,
                                            key=f"ovr_score_{sid}_{qi}",
                                        )
                                    with oc2:
                                        new_comment = st.text_input(
                                            "Comment (optional)",
                                            value=ovr.get("comment", "") if ovr else "",
                                            key=f"ovr_comment_{sid}_{qi}",
                                        )
                                    with oc3:
                                        st.write("")
                                        if st.button("Save", key=f"ovr_save_{sid}_{qi}",
                                                     width="stretch"):
                                            try:
                                                api.teacher_override_grade(
                                                    sid, qi, float(new_score), new_comment,
                                                )
                                                _bust("assignments")
                                                st.toast("Override saved", icon="⚖️")
                                                st.rerun()
                                            except Exception as e:
                                                st.error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — NEW ASSIGNMENT  (mode-first: pick Manual or Use AI, then build)
# ═══════════════════════════════════════════════════════════════════════════════
def _class_to_target(cs: str) -> int:
    """Extract the numeric class from a class+section string ('5A' -> 5)."""
    m = re.match(r"\s*(\d+)", cs or "")
    return int(m.group(1)) if m else 5


with tab_new:
    # Working list of questions persists across mode changes so the teacher
    # can mix AI-generated + manual questions in the same assignment.
    Q_KEY = "t_new_questions"
    if Q_KEY not in st.session_state:
        st.session_state[Q_KEY] = []
    questions: List[Dict] = st.session_state[Q_KEY]

    mode = st.session_state.get("t_new_mode")  # None | "manual" | "ai"

    # ── Edit-question dialog ─────────────────────────────────────────────────
    # Opens when the teacher clicks ✎ on a question card in the working set.
    # All fields are editable, and MCQ options appear only when type=mcq.
    @st.dialog("Edit question", width="large")
    def _edit_question_dialog(idx: int):
        qs = st.session_state.get(Q_KEY) or []
        if idx < 0 or idx >= len(qs):
            st.error("Question not found.")
            return
        q = qs[idx]

        current_type = q.get("type") or "short-answer"
        try:
            type_idx = _QUESTION_TYPES.index(current_type)
        except ValueError:
            type_idx = _QUESTION_TYPES.index("short-answer")

        new_text = st.text_area(
            "Question", value=q.get("question", ""),
            key=f"_edit_q_text_{idx}", height=100,
        )
        c1, c2 = st.columns([3, 1])
        with c1:
            new_type = st.selectbox(
                "Type",
                options=_QUESTION_TYPES,
                index=type_idx,
                format_func=lambda t: _TYPE_LABELS.get(t, t),
                key=f"_edit_q_type_{idx}",
            )
        with c2:
            new_marks = st.number_input(
                "Marks", 1, 100, int(q.get("marks", 10) or 10),
                key=f"_edit_q_marks_{idx}",
            )

        new_options: List[str] = []
        if new_type == "mcq":
            existing = list(q.get("options") or [])
            existing = (existing + ["", "", "", ""])[:4]
            r1 = st.columns(2)
            with r1[0]:
                new_options.append(st.text_input("Option A", value=existing[0], key=f"_edit_q_opt_{idx}_0"))
            with r1[1]:
                new_options.append(st.text_input("Option B", value=existing[1], key=f"_edit_q_opt_{idx}_1"))
            r2 = st.columns(2)
            with r2[0]:
                new_options.append(st.text_input("Option C", value=existing[2], key=f"_edit_q_opt_{idx}_2"))
            with r2[1]:
                new_options.append(st.text_input("Option D", value=existing[3], key=f"_edit_q_opt_{idx}_3"))

        new_expected = st.text_area(
            "Expected answer", value=q.get("expected_answer", ""),
            key=f"_edit_q_exp_{idx}", height=80,
        )
        new_keywords_str = st.text_input(
            "Keywords (comma-separated)",
            value=", ".join(q.get("keywords") or []),
            key=f"_edit_q_kw_{idx}",
        )

        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("💾 Save changes", type="primary", width="stretch",
                         key=f"_edit_q_save_{idx}"):
                if not new_text.strip():
                    st.error("Question text is required.")
                else:
                    qs[idx] = {
                        **q,
                        "question": new_text.strip(),
                        "type": new_type,
                        "options": [o.strip() for o in new_options if o and o.strip()],
                        "expected_answer": new_expected.strip(),
                        "keywords": [k.strip() for k in new_keywords_str.split(",") if k.strip()],
                        "marks": int(new_marks),
                    }
                    st.session_state[Q_KEY] = qs
                    st.rerun()
        with b2:
            if st.button("Cancel", width="stretch", key=f"_edit_q_cancel_{idx}"):
                st.rerun()

    # ─── STAGE 1: Mode picker ────────────────────────────────────────────
    if not mode:
        st.markdown("### How would you like to build this assignment?")
        st.caption(
            "Choose **Manual entry** to type questions yourself, or **Use AI** to "
            "generate questions from one of your uploaded PDFs. You can also switch "
            "modes later — your work is preserved."
        )
        pc1, pc2 = st.columns(2)
        with pc1:
            st.markdown("""
            <div class="card" style="text-align:center; padding:24px;">
                <div style="font-size:2.4rem;">✏️</div>
                <div style="font-weight:700; color:var(--text); margin-top:6px;">Manual entry</div>
                <div style="font-size:0.82rem; color:#888; margin-top:4px;">
                    Type each question, expected answer, and keywords by hand.
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Start manual →", key="t_pick_manual",
                         width="stretch", type="primary"):
                st.session_state["t_new_mode"] = "manual"
                st.rerun()
        with pc2:
            st.markdown("""
            <div class="card" style="text-align:center; padding:24px;">
                <div style="font-size:2.4rem;">🤖</div>
                <div style="font-weight:700; color:var(--text); margin-top:6px;">Use AI</div>
                <div style="font-size:0.82rem; color:#888; margin-top:4px;">
                    Generate questions from one of your uploaded PDFs.
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Start AI →", key="t_pick_ai",
                         width="stretch", type="primary"):
                st.session_state["t_new_mode"] = "ai"
                st.rerun()

        if questions:
            st.info(
                f"You have {len(questions)} question(s) already added to this draft. "
                "Picking a mode will let you continue building."
            )

    # ─── STAGE 2: Build form ────────────────────────────────────────────
    else:
        # Mode header + change-mode action
        h1, h2 = st.columns([4, 1])
        with h1:
            label = "✏️ Manual entry" if mode == "manual" else "🤖 Use AI"
            st.markdown(f"### {label}")
        with h2:
            if st.button("↺ Change mode", key="t_change_mode", width="stretch"):
                st.session_state.pop("t_new_mode", None)
                st.rerun()

        # ── Common metadata (shown ONCE, used by both modes) ────────────
        mc1, mc2, mc3 = st.columns([2, 1, 1])
        with mc1:
            new_title = st.text_input(
                "Title", key="t_new_title",
                placeholder="e.g. Photosynthesis basics",
            )
        with mc2:
            if classes:
                new_class = st.selectbox("Class", classes, key="t_new_class")
            else:
                new_class = st.selectbox("Class", ALL_CS, key="t_new_class")
                st.caption("⚠️ No assigned classes — admin must assign you first.")
        with mc3:
            subject_options = (subjects or ALL_SUBJECTS)
            new_subject = st.selectbox(
                "Subject", [""] + list(subject_options), key="t_new_subject",
            )
        new_subject_value = new_subject or None

        new_desc = st.text_area(
            "Description / instructions (optional)",
            key="t_new_desc", height=70,
        )

        dd1, dd2 = st.columns(2)
        with dd1:
            new_due_date = st.date_input(
                "Due date",
                value=(datetime.now(timezone.utc) + timedelta(days=7)).date(),
                key="t_new_due",
            )
        with dd2:
            new_due_time = st.time_input(
                "Due time",
                value=datetime.now(timezone.utc).time().replace(microsecond=0),
                key="t_new_due_time",
            )
        new_due_iso = datetime.combine(new_due_date, new_due_time).isoformat()

        # Derive target_class from the class selector ("5A" → 5).
        derived_target_class = _class_to_target(new_class)

        st.markdown("---")

        # ── MODE: Manual ────────────────────────────────────────────────
        if mode == "manual":
            st.markdown("#### Add a question")
            with st.form("t_manual_q"):
                mq_text = st.text_area("Question", key="t_mq_text", height=80)
                mq_top_a, mq_top_b = st.columns([3, 1])
                with mq_top_a:
                    mq_type = st.selectbox(
                        "Question type",
                        options=_QUESTION_TYPES,
                        format_func=lambda t: _TYPE_LABELS.get(t, t),
                        key="t_mq_type",
                    )
                with mq_top_b:
                    mq_marks = st.number_input(
                        "Marks", 1, 100, 10, key="t_mq_marks",
                    )
                # MCQ-only: 4 option inputs revealed when the type matches
                mq_options: List[str] = []
                if mq_type == "mcq":
                    opt_row1 = st.columns(2)
                    with opt_row1[0]:
                        mq_options.append(st.text_input("Option A", key="t_mq_opt_0"))
                    with opt_row1[1]:
                        mq_options.append(st.text_input("Option B", key="t_mq_opt_1"))
                    opt_row2 = st.columns(2)
                    with opt_row2[0]:
                        mq_options.append(st.text_input("Option C", key="t_mq_opt_2"))
                    with opt_row2[1]:
                        mq_options.append(st.text_input("Option D", key="t_mq_opt_3"))
                mq_expected = st.text_area(
                    "Expected answer", key="t_mq_expected", height=80,
                )
                mq_keywords_str = st.text_input(
                    "Keywords (comma-separated)", key="t_mq_keywords",
                    placeholder="atmosphere, oxygen, photosynthesis",
                )
                add_q = st.form_submit_button(
                    "➕ Add this question", width="stretch",
                )
                if add_q:
                    if not mq_text.strip():
                        st.error("Question text is required.")
                    else:
                        questions.append({
                            "question": mq_text.strip(),
                            "type": mq_type,
                            "options": [o.strip() for o in mq_options if o and o.strip()],
                            "expected_answer": mq_expected.strip(),
                            "keywords": [
                                k.strip() for k in mq_keywords_str.split(",")
                                if k.strip()
                            ],
                            "marks": int(mq_marks),
                            "target_class": derived_target_class,
                            "subject": new_subject_value,
                        })
                        st.session_state[Q_KEY] = questions
                        st.toast(f"Added Q{len(questions)}", icon="➕")
                        st.rerun()

        # ── MODE: Use AI ────────────────────────────────────────────────
        else:
            try:
                my_pdfs = api.get_my_pdfs(limit=200).get("pdfs", []) or []
            except Exception as e:
                st.error(f"Could not load your PDFs: {e}")
                my_pdfs = []

            if not my_pdfs:
                st.info(
                    "📄 You haven't uploaded any PDFs yet. Use the **Upload PDF** "
                    "section in the sidebar, then come back here."
                )
            else:
                pdf_options = {
                    p.get("pdf_identifier", p.get("id", "")): p.get("filename", "Unknown")
                    for p in my_pdfs if p.get("pdf_identifier") or p.get("id")
                }
                pdf_ids = list(pdf_options.keys())

                ai_pdf = st.selectbox(
                    "Source PDF", pdf_ids,
                    format_func=lambda i: pdf_options.get(i, i),
                    key="t_ai_pdf",
                )
                st.caption(
                    f"Generated questions will use **target class {derived_target_class}** "
                    f"(from class {new_class})"
                    + (f" and subject **{new_subject_value}**." if new_subject_value
                       else " — pick a Subject above to tune the prompt.")
                )

                ai_tab_q, ai_tab_quiz, ai_tab_fill, ai_tab_paper = st.tabs([
                    "📝 Questions", "🎲 Quizzes", "✏️ Fill in the Blanks", "📄 Question Paper",
                ])

                def _import_to_assignment(generated: List[Dict], q_type: str) -> int:
                    """Append AI-generated questions to the working set, preserving
                    the question type and any MCQ options so the teacher can see
                    and edit them before publishing."""
                    added = 0
                    for g in generated or []:
                        questions.append({
                            "question": g.get("question", "").strip(),
                            "type": q_type,
                            "options": list(g.get("options") or []),
                            "expected_answer": (
                                g.get("correct_answer")
                                or g.get("expected_answer") or ""
                            ).strip(),
                            "keywords": list(g.get("keywords") or []),
                            "marks": 10,
                            "target_class": derived_target_class,
                            "subject": new_subject_value,
                        })
                        added += 1
                    st.session_state[Q_KEY] = questions
                    return added

                def _show_quiz_error(exc: Exception) -> None:
                    """Display either a friendly 'unavailable' banner or the raw error."""
                    msg = str(exc)
                    if "temporarily unavailable" in msg.lower():
                        st.warning(
                            "⚠️ **AI question generation temporarily unavailable** — "
                            "the AI service is currently down. You can still **enter "
                            "questions manually** by switching to the Manual entry "
                            "mode above. AI generation will return automatically "
                            "when the service is back online.",
                            icon="🔧",
                        )
                    else:
                        st.error(msg)

                with ai_tab_q:
                    qc1, qc2, qc3 = st.columns(3)
                    with qc1:
                        q_mode = st.radio(
                            "Type", ["short-answer", "long-answer"],
                            format_func=lambda x: "Short Answer" if x == "short-answer" else "Long Answer",
                            key="t_ai_q_mode", horizontal=True,
                        )
                    with qc2:
                        q_count = st.slider("Questions", 1, 15, 5, key="t_ai_q_count")
                    with qc3:
                        q_diff = st.selectbox(
                            "Difficulty", ["basic", "medium", "hard"],
                            format_func=lambda x: x.title(), key="t_ai_q_diff",
                        )
                    q_topic = st.text_input("Topic (optional)", key="t_ai_q_topic")
                    if st.button("Generate & import", type="primary",
                                 width="stretch", key="t_ai_q_gen"):
                        with st.spinner("Generating…"):
                            try:
                                r = api.generate_quiz(
                                    pdf_identifier=ai_pdf, num_questions=q_count,
                                    difficulty=q_diff, question_type=q_mode,
                                    search_query=q_topic or None,
                                    target_class=derived_target_class,
                                    subject=new_subject_value,
                                )
                                n = _import_to_assignment(r.get("questions") or [], q_mode)
                                st.toast(f"Imported {n} questions", icon="✅")
                                st.rerun()
                            except Exception as e:
                                _show_quiz_error(e)

                with ai_tab_quiz:
                    qc1, qc2 = st.columns(2)
                    with qc1:
                        quiz_count = st.slider("Questions", 1, 20, 5, key="t_ai_quiz_count")
                    with qc2:
                        quiz_diff = st.selectbox(
                            "Difficulty", ["basic", "medium", "hard"],
                            format_func=lambda x: x.title(), key="t_ai_quiz_diff",
                        )
                    quiz_topic = st.text_input("Topic (optional)", key="t_ai_quiz_topic")
                    if st.button("Generate & import (MCQ)", type="primary",
                                 width="stretch", key="t_ai_quiz_gen"):
                        with st.spinner("Generating…"):
                            try:
                                r = api.generate_quiz(
                                    pdf_identifier=ai_pdf, num_questions=quiz_count,
                                    difficulty=quiz_diff, question_type="mcq",
                                    search_query=quiz_topic or None,
                                    target_class=derived_target_class,
                                    subject=new_subject_value,
                                )
                                n = _import_to_assignment(r.get("questions") or [], "mcq")
                                st.toast(f"Imported {n} MCQs", icon="✅")
                                st.rerun()
                            except Exception as e:
                                _show_quiz_error(e)

                with ai_tab_fill:
                    fc1, fc2 = st.columns(2)
                    with fc1:
                        fill_count = st.slider("Questions", 1, 15, 5, key="t_ai_fill_count")
                    with fc2:
                        fill_diff = st.selectbox(
                            "Difficulty", ["basic", "medium", "hard"],
                            format_func=lambda x: x.title(), key="t_ai_fill_diff",
                        )
                    fill_topic = st.text_input("Topic (optional)", key="t_ai_fill_topic")
                    if st.button("Generate & import (Fill blanks)", type="primary",
                                 width="stretch", key="t_ai_fill_gen"):
                        with st.spinner("Generating…"):
                            try:
                                r = api.generate_quiz(
                                    pdf_identifier=ai_pdf, num_questions=fill_count,
                                    difficulty=fill_diff, question_type="fill-in-blank",
                                    search_query=fill_topic or None,
                                    target_class=derived_target_class,
                                    subject=new_subject_value,
                                )
                                n = _import_to_assignment(r.get("questions") or [], "fill-in-blank")
                                st.toast(f"Imported {n} fill-in-blanks", icon="✅")
                                st.rerun()
                            except Exception as e:
                                _show_quiz_error(e)

                with ai_tab_paper:
                    paper_topic = st.text_input("Topics or chapters", key="t_ai_paper_topic")
                    pc1, pc2, pc3, pc4, pc5 = st.columns(5)
                    with pc1:
                        p_mcq = st.number_input("MCQ", 0, 20, 5, key="t_ai_p_mcq")
                    with pc2:
                        p_sa = st.number_input("Short Ans.", 0, 20, 3, key="t_ai_p_sa")
                    with pc3:
                        p_la = st.number_input("Long Ans.", 0, 20, 2, key="t_ai_p_la")
                    with pc4:
                        p_fib = st.number_input("Fill Blanks", 0, 20, 3, key="t_ai_p_fib")
                    with pc5:
                        p_tf = st.number_input("True/False", 0, 20, 2, key="t_ai_p_tf")
                    paper_diff = st.selectbox(
                        "Difficulty", ["basic", "medium", "hard"],
                        format_func=lambda x: x.title(), key="t_ai_p_diff",
                    )
                    if st.button("Generate question paper & import", type="primary",
                                 width="stretch", key="t_ai_p_gen"):
                        sections = [
                            ("mcq", int(p_mcq)), ("fill-in-blank", int(p_fib)),
                            ("true-false", int(p_tf)), ("short-answer", int(p_sa)),
                            ("long-answer", int(p_la)),
                        ]
                        if sum(c for _, c in sections) == 0:
                            st.warning("Set at least one count > 0.")
                        elif not paper_topic.strip():
                            st.warning("Enter topics/chapters first.")
                        else:
                            with st.spinner("Generating question paper…"):
                                total_added = 0
                                ai_down = False
                                for qtype, count in sections:
                                    if count <= 0:
                                        continue
                                    try:
                                        r = api.generate_quiz(
                                            pdf_identifier=ai_pdf, num_questions=count,
                                            difficulty=paper_diff, question_type=qtype,
                                            search_query=paper_topic.strip(),
                                            target_class=derived_target_class,
                                            subject=new_subject_value,
                                        )
                                        total_added += _import_to_assignment(r.get("questions") or [], qtype)
                                    except Exception as e:
                                        if "temporarily unavailable" in str(e).lower():
                                            ai_down = True
                                            break
                                        st.warning(f"{qtype}: {e}")
                                if ai_down:
                                    st.warning(
                                        "⚠️ **AI question generation temporarily unavailable** — "
                                        "the AI service is currently down. Switch to **Manual entry** "
                                        "to build the paper yourself, or try again later.",
                                        icon="🔧",
                                    )
                                else:
                                    st.toast(f"Imported {total_added} questions", icon="✅")
                                    st.rerun()

        # ── Working set of questions ────────────────────────────────────
        st.markdown("---")
        st.markdown(f"### Questions in this assignment ({len(questions)})")
        if not questions:
            st.caption(
                "_No questions yet. Add some "
                + ("manually above" if mode == "manual" else "via the AI tabs above")
                + "._"
            )
        else:
            for qi, q in enumerate(questions):
                with st.container(border=True):
                    cc1, cc_edit, cc_del = st.columns([10, 1, 1])
                    with cc1:
                        type_label = _TYPE_LABELS.get(q.get("type"), "❓ Unspecified")
                        st.markdown(
                            f"**Q{qi+1}.** {q.get('question','')}  "
                            f"<span style='background:var(--accent-chip-bg); "
                            f"color:var(--accent); border:1px solid var(--accent-glow); "
                            f"border-radius:12px; padding:2px 10px; font-size:0.74rem; "
                            f"font-weight:600; margin-left:6px;'>{type_label}</span>",
                            unsafe_allow_html=True,
                        )
                        st.caption(
                            f"Marks: {q.get('marks',10)} · "
                            f"Target class: {q.get('target_class') or '—'} · "
                            f"Subject: {q.get('subject') or '—'}"
                        )
                        # MCQ-only: show the four options so the teacher can verify them
                        if q.get("type") == "mcq" and q.get("options"):
                            opts = q["options"]
                            opt_labels = [
                                f"**{chr(65 + i)})** {o}" for i, o in enumerate(opts)
                            ]
                            st.caption("  ·  ".join(opt_labels))
                        if q.get("expected_answer"):
                            st.caption(f"_Expected:_ {q['expected_answer']}")
                        if q.get("keywords"):
                            st.caption(f"_Keywords:_ {', '.join(q['keywords'])}")
                    with cc_edit:
                        if st.button("✎", key=f"t_q_edit_{qi}",
                                     help="Edit this question"):
                            _edit_question_dialog(qi)
                    with cc_del:
                        if st.button("✕", key=f"t_q_del_{qi}",
                                     help="Remove this question"):
                            questions.pop(qi)
                            st.session_state[Q_KEY] = questions
                            st.rerun()

        # ── Save / publish ──────────────────────────────────────────────
        st.markdown("---")
        sc1, sc2, sc3 = st.columns([1, 1, 2])
        with sc1:
            if st.button("💾 Save as draft", width="stretch", key="t_save_draft"):
                if not new_title.strip():
                    st.error("Title required.")
                elif not questions:
                    st.error("Add at least one question.")
                else:
                    try:
                        api.teacher_create_assignment({
                            "title": new_title.strip(),
                            "description": new_desc.strip(),
                            "class_section": new_class,
                            "subject": new_subject_value,
                            "questions": questions,
                            "due_date": new_due_iso,
                            "status": "draft",
                        })
                        st.session_state[Q_KEY] = []
                        st.session_state.pop("t_new_mode", None)
                        _bust("assignments")
                        st.success("Draft saved! See it in My Assignments.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        with sc2:
            if st.button("📤 Publish now", type="primary",
                         width="stretch", key="t_publish_now"):
                if not new_title.strip():
                    st.error("Title required.")
                elif not questions:
                    st.error("Add at least one question.")
                else:
                    try:
                        api.teacher_create_assignment({
                            "title": new_title.strip(),
                            "description": new_desc.strip(),
                            "class_section": new_class,
                            "subject": new_subject_value,
                            "questions": questions,
                            "due_date": new_due_iso,
                            "status": "published",
                        })
                        st.session_state[Q_KEY] = []
                        st.session_state.pop("t_new_mode", None)
                        _bust("assignments")
                        st.success(f"Published to {new_class}!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MY STUDENTS (per-class roster + per-student submission history)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_students:
    try:
        s_resp = _cached("students", api.teacher_list_students,
                         spinner="Loading your students…")
        all_students = s_resp.get("students", []) or []
        by_class = s_resp.get("by_class", {}) or {}
    except Exception as e:
        st.error(f"Could not load students: {e}")
        all_students = []
        by_class = {}

    if not all_students:
        st.info("No students in your assigned classes yet.")
    else:
        for cs, students in sorted(by_class.items()):
            st.markdown(f"### Class {cs}  ·  {len(students)} students")
            for s in students:
                with st.expander(
                    f"👨‍🎓 {s.get('username','?')} · {s.get('email','?')}",
                    expanded=False,
                ):
                    st.caption(
                        f"Class {cs} · "
                        f"Joined {str(s.get('created_at',''))[:10]}"
                    )

                    # Auto-load submissions when expander is opened
                    student_id = s.get('id')
                    cache_key = f"t_sub_history_{student_id}"
                    if cache_key not in st.session_state:
                        try:
                            with st.spinner("Loading submissions..."):
                                sub_resp = api.teacher_student_submissions(student_id)
                                st.session_state[cache_key] = sub_resp.get("submissions", [])
                        except Exception as e:
                            st.error(f"Could not load submissions: {e}")
                            st.session_state[cache_key] = []

                    history = st.session_state.get(cache_key, [])
                    if not history:
                        st.caption("_No submissions for your assignments yet._")
                    else:
                        for h in history:
                            sub_id = h.get("id")
                            with st.container(border=True):
                                # Summary line
                                score_pct = h.get('percent', 0)
                                score_color = "green" if score_pct >= 70 else "orange" if score_pct >= 40 else "red"
                                st.markdown(
                                    f"**{h.get('total_score',0):.1f}/{h.get('total_max',0)}** "
                                    f"(:{score_color}[{score_pct}%]) — "
                                    f"submitted {str(h.get('submitted_at',''))[:16].replace('T',' ')}"
                                )

                                # Auto-load detailed grading or show toggle
                                detail_key = f"t_sub_detail_{sub_id}"
                                if st.checkbox("View detailed grading", key=f"t_detail_toggle_{sub_id}"):
                                    if detail_key not in st.session_state:
                                        try:
                                            with st.spinner("Loading grading details..."):
                                                detail_resp = api.teacher_get_submission(sub_id)
                                                st.session_state[detail_key] = detail_resp
                                        except Exception as e:
                                            st.error(f"Could not load details: {e}")
                                            st.session_state[detail_key] = {}

                                    detail = st.session_state.get(detail_key, {})
                                    if detail:
                                        submission = detail.get("submission", {})
                                        assignment = detail.get("assignment", {})
                                        questions = assignment.get("questions", [])

                                        for ans in submission.get("answers", []):
                                            qi = ans.get("question_index", 0)
                                            qtxt = questions[qi].get("question") if qi < len(questions) else f"Q{qi+1}"
                                            ovr = ans.get("teacher_override") or {}
                                            effective = ovr.get("score") if ovr else ans.get("ai_score", 0)

                                            with st.container(border=True):
                                                st.markdown(f"**Q{qi+1}.** {qtxt}")
                                                st.markdown(f"_Student answer:_ {ans.get('student_answer') or '_(empty)_'}")

                                                # Score info
                                                st.caption(
                                                    f"Score: {effective:.1f}/10 · Marks: {ans.get('marks', 10)} · "
                                                    f"Scaled: {ans.get('scaled_score', 0):.1f}"
                                                )

                                                # Teacher override indicator
                                                if ovr:
                                                    st.info(
                                                        f"**Teacher override:** {ovr.get('score')}/10 "
                                                        f"— {ovr.get('comment') or '_(no comment)_'}"
                                                    )

                                                # Feedback breakdown
                                                fb = ans.get("feedback") or {}
                                                if fb.get("correct_points"):
                                                    st.markdown("**Correct points:**")
                                                    for p in fb["correct_points"]:
                                                        st.markdown(f"- {p}")
                                                if fb.get("mistakes"):
                                                    st.markdown("**Mistakes:**")
                                                    for p in fb["mistakes"]:
                                                        st.markdown(f"- {p}")
                                                if fb.get("improvements"):
                                                    st.markdown("**Suggestions for improvement:**")
                                                    for p in fb["improvements"]:
                                                        st.markdown(f"- {p}")
