"""
Student Dashboard — PDF management, Q&A, Quiz, Summary, Audio, Video, Chat History.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Dict, List

import streamlit as st
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

    # PDF Upload
    st.markdown('<p style="font-size:0.85rem; font-weight:700; color:#A89CFF; margin:0 0 6px 0;">📤 UPLOAD PDF</p>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("PDF file", type=["pdf"], label_visibility="collapsed")
    if uploaded_file:
        if st.button("⬆️ Upload Now", use_container_width=True, type="primary"):
            with st.spinner("Processing PDF…"):
                try:
                    result = api.upload_pdf(uploaded_file.read(), uploaded_file.name)
                    st.success(f"✅ {result.get('filename', uploaded_file.name)}")
                    st.caption(f"📄 {result.get('total_pages','?')} pages · {result.get('total_chunks','?')} chunks")
                    st.session_state["pdf_list"] = api.get_my_pdfs().get("pdfs", [])
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))

    st.markdown('<hr style="border-color:#2A2A4A; margin:14px 0;">', unsafe_allow_html=True)

    # PDF Selector
    st.markdown('<p style="font-size:0.85rem; font-weight:700; color:#A89CFF; margin:0 0 6px 0;">📂 YOUR PDFS</p>', unsafe_allow_html=True)
    try:
        if not st.session_state.get("pdf_list"):
            st.session_state["pdf_list"] = api.get_my_pdfs().get("pdfs", [])
    except Exception:
        st.session_state["pdf_list"] = []

    pdf_list = st.session_state.get("pdf_list", [])

    if not pdf_list:
        st.markdown('<p style="font-size:0.82rem; color:#555; text-align:center; padding:10px 0;">No PDFs yet — upload one above</p>', unsafe_allow_html=True)
    else:
        pdf_names    = [p["filename"] for p in pdf_list]
        selected_name = st.selectbox("Select PDF", options=pdf_names, label_visibility="collapsed")
        selected_pdf  = next((p for p in pdf_list if p["filename"] == selected_name), None)
        if selected_pdf:
            st.session_state["selected_pdf_id"]   = selected_pdf["pdf_identifier"]
            st.session_state["selected_pdf_name"] = selected_pdf["filename"]

            c1, c2 = st.columns(2)
            with c2:
                if st.button("🗑️ Delete", use_container_width=True, key="del_pdf"):
                    try:
                        api.delete_pdf(selected_pdf["id"])
                        st.session_state["pdf_list"]        = api.get_my_pdfs().get("pdfs", [])
                        st.session_state["selected_pdf_id"] = None
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))

    # Multi-doc selector
    if pdf_list and len(pdf_list) > 1:
        st.markdown('<hr style="border-color:#2A2A4A; margin:14px 0;">', unsafe_allow_html=True)
        st.markdown('<p style="font-size:0.85rem; font-weight:700; color:#A89CFF; margin:0 0 6px 0;">🔀 MULTI-DOC QUERY</p>', unsafe_allow_html=True)
        multi_names = st.multiselect(
            "PDFs", options=pdf_names, default=[],
            label_visibility="collapsed", placeholder="Select PDFs to query together…",
        )
        st.session_state["selected_pdf_ids"] = [
            p["pdf_identifier"] for p in pdf_list if p["filename"] in multi_names
        ]

    st.markdown('<hr style="border-color:#2A2A4A; margin:14px 0;">', unsafe_allow_html=True)

    with st.expander("🔑 Change Password"):
        old_pw = st.text_input("Current Password", type="password", key="cp_old")
        new_pw = st.text_input("New Password",     type="password", key="cp_new")
        if st.button("Update", use_container_width=True):
            if not old_pw or not new_pw:
                st.error("Fill both fields.")
            elif len(new_pw) < 8:
                st.error("Min 8 characters.")
            else:
                try:
                    api.change_password(old_pw, new_pw)
                    st.success("Password updated!")
                except RuntimeError as e:
                    st.error(str(e))

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    if st.button("🚪 Logout", use_container_width=True):
        logout()
        st.switch_page("pages/1_Login.py")


# ─────────────────────────────────────────────────────────────────────────────
# HERO BANNER
# ─────────────────────────────────────────────────────────────────────────────
current_pdf_id   = st.session_state.get("selected_pdf_id")
current_pdf_name = st.session_state.get("selected_pdf_name", "")

greeting_name = st.session_state.get("full_name") or st.session_state.get("username", "Student")

st.markdown(f"""
<div class="hero">
    <div style="display:flex; align-items:center; gap:16px; flex-wrap:wrap;">
        <div>
            <div style="font-size:0.82rem; color:#A89CFF; font-weight:600; letter-spacing:1px; text-transform:uppercase;">Welcome back</div>
            <h2 style="margin:4px 0 6px 0; font-size:1.7rem; color:#E8E8F0;">Hey, {greeting_name}! 👋</h2>
            <div class="pill-row">
                <span class="pill">💬 Smart Q&amp;A</span>
                <span class="pill">📝 Quiz Generator</span>
                <span class="pill">📋 Summaries</span>
                <span class="pill">🔊 Audio</span>
                <span class="pill">🎬 Video Scripts</span>
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if current_pdf_id:
    st.markdown(f"""
    <div class="pdf-bar">
        📖 Active document: <strong style="color:#A89CFF;">{current_pdf_name}</strong>
        &nbsp;&nbsp;<span class="badge badge-green" style="font-size:0.72rem;">READY</span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="background:#1A1020; border:1px dashed #6C63FF55; border-radius:12px;
                padding:14px 20px; text-align:center; margin-bottom:16px; color:#888; font-size:0.9rem;">
        📂 No PDF selected — use the <strong style="color:#A89CFF;">sidebar</strong> to upload or pick a PDF
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_home, tab_assignments_student, tab_qa, tab_multi, tab_quiz, tab_summary, tab_audio, tab_video, tab_history = st.tabs(
    ["🏠 Home", "📚 Assignments",
     "💬 Q&A", "🔀 Multi-Doc", "📝 Quiz", "📋 Summary", "🔊 Audio", "🎬 Video", "🕐 History"]
)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 0 — HOME (profile + AI Features button + assignments preview)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_home:
    cs = class_section()
    name_h = st.session_state.get("full_name") or st.session_state.get("username", "Student")
    email_h = st.session_state.get("user_email", "")

    st.markdown(f"""
    <div class="card">
        <div style="display:flex; align-items:center; gap:18px;">
            <div style="font-size:2.6rem;">🎓</div>
            <div>
                <div style="font-size:1.3rem; font-weight:800; color:#E8E8F0;">{name_h}</div>
                <div style="color:#888; font-size:0.88rem;">{email_h}</div>
                <div style="margin-top:6px; color:#A89CFF; font-weight:600;">
                    Class {cs or '—'}
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick recent assignments preview
    try:
        a_data = api.student_list_assignments()
        my_a = a_data.get("assignments", []) or []
    except Exception as e:
        st.error(f"Could not load assignments: {e}")
        my_a = []

    pending = [a for a in my_a if not a.get("my_submission")]
    submitted = [a for a in my_a if a.get("my_submission")]

    qc1, qc2, qc3 = st.columns(3)
    with qc1:
        st.markdown(f"""
        <div class="card" style="text-align:center;">
            <div style="font-size:1.6rem; font-weight:800; color:#FFB347;">{len(pending)}</div>
            <div style="color:#888; font-size:0.82rem;">📥 Pending assignments</div>
        </div>
        """, unsafe_allow_html=True)
    with qc2:
        st.markdown(f"""
        <div class="card" style="text-align:center;">
            <div style="font-size:1.6rem; font-weight:800; color:#00E870;">{len(submitted)}</div>
            <div style="color:#888; font-size:0.82rem;">✅ Submitted</div>
        </div>
        """, unsafe_allow_html=True)
    with qc3:
        if submitted:
            avg = sum(float((s.get("my_submission") or {}).get("percent") or 0) for s in submitted) / len(submitted)
            color = "#00E870" if avg >= 70 else "#FFB347" if avg >= 40 else "#FF8080"
            st.markdown(f"""
            <div class="card" style="text-align:center;">
                <div style="font-size:1.6rem; font-weight:800; color:{color};">{avg:.0f}%</div>
                <div style="color:#888; font-size:0.82rem;">📊 Average score</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="card" style="text-align:center;">
                <div style="font-size:1.6rem; font-weight:800; color:#666;">—</div>
                <div style="color:#888; font-size:0.82rem;">📊 Average score</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("#### 🤖 AI Features")
    st.caption(
        "Use the **Q&A**, **Multi-Doc**, **Quiz**, **Summary**, **Audio**, **Video**, "
        "or **History** tabs above to explore your uploaded PDFs with AI. "
        "AI features are restricted while you're answering an assignment."
    )

    st.markdown("#### 📚 Recent assignments")
    if not my_a:
        st.info("No assignments yet for your class.")
    else:
        for a in my_a[:5]:
            sub = a.get("my_submission")
            done = sub is not None
            status_html = (
                f'<span class="badge badge-green">✅ {sub.get("percent", 0)}%</span>'
                if done else
                '<span class="badge badge-blue">⏳ Pending</span>'
            )
            due = a.get("due_date") or ""
            due_str = str(due)[:16].replace("T", " ") if due else "—"
            st.markdown(f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <strong>{a.get('title','(untitled)')}</strong> {status_html}
                    </div>
                    <div style="color:#888; font-size:0.82rem;">
                        {len(a.get('questions') or [])} Q · Due: {due_str}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — ASSIGNMENTS  (take or review submissions; NO AI features here)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_assignments_student:
    st.caption(
        "📚 Your assignments. Tap one to attempt it. "
        "**AI features are strictly disabled inside the assignment view** — "
        "answer in your own words."
    )

    try:
        a_resp = api.student_list_assignments()
        assignments = a_resp.get("assignments", []) or []
    except Exception as e:
        st.error(f"Could not load assignments: {e}")
        assignments = []

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
                            "handwritten answer — text is extracted via OCR and "
                            "you can edit it before submitting."
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
                                    need = st.session_state.get(f"s_extract_key_{aid}_{qi}") != fk
                                    eu1, eu2 = st.columns([3, 1])
                                    with eu1:
                                        st.caption(
                                            f"Selected: **{up.name}** ({up.size // 1024} KB)"
                                        )
                                    with eu2:
                                        if st.button(
                                            "Extract text" if need else "Re-extract",
                                            use_container_width=True,
                                            key=f"s_extract_{aid}_{qi}",
                                        ):
                                            with st.spinner("Extracting…"):
                                                try:
                                                    r = api.extract_text_from_upload(
                                                        up.getvalue(), up.name,
                                                    )
                                                    extracted = r.get("text", "")
                                                    if not extracted:
                                                        st.warning(
                                                            r.get("warning")
                                                            or "No text could be extracted."
                                                        )
                                                    else:
                                                        st.session_state[pending_key] = extracted
                                                        st.session_state[
                                                            f"s_extract_key_{aid}_{qi}"
                                                        ] = fk
                                                        st.toast(
                                                            f"Extracted {r.get('char_count', 0)} chars",
                                                            icon="✅",
                                                        )
                                                        st.rerun()
                                                except Exception as e:
                                                    st.error(f"Extraction failed: {e}")

                                st.text_area(
                                    f"Your answer to Q{qi+1}",
                                    key=widget_key, height=140,
                                    placeholder=(
                                        "Type here, or upload a PDF / image of your "
                                        "handwritten answer above and click Extract text."
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

    try:
        sessions = api.list_chat_sessions(mode=mode).get("sessions", [])
    except Exception:
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
                    st.error(str(e))
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
