"""
Admin Dashboard — Analytics, Users, Roles & Permissions, Activity Logs, Audit Export.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import threading
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from utils.session_utils import init_session_state, require_admin, logout, is_teacher, is_student
from utils.api_client import APIClient
from utils.themes import apply_theme, render_theme_selector

st.set_page_config(
    page_title="Admin Dashboard — School LLM",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
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

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D0D1F 0%, #0A0A18 100%);
    border-right: 1px solid #2A2A4A;
}

.stApp { background: #0E1117; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 1rem !important; }

/* Cards */
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

/* Metric cards */
.stat-card {
    background: linear-gradient(135deg, #1A1A2E, #16213E);
    border: 1px solid #2E2E5E;
    border-radius: 14px;
    padding: 20px 16px;
    text-align: center;
    height: 100%;
}
.stat-card .num { font-size: 2rem; font-weight: 800; margin-bottom: 4px; }
.stat-card .lbl { font-size: 0.82rem; color: #888; }
.stat-purple .num { color: #A89CFF; }
.stat-green  .num { color: #00E870; }
.stat-blue   .num { color: #40C4FF; }
.stat-orange .num { color: #FFB347; }

/* Hero */
.admin-hero {
    background: linear-gradient(135deg, #1A0A30 0%, #0D1B3E 60%, #0A1628 100%);
    border: 1px solid #6C63FF44;
    border-radius: 18px;
    padding: 26px 32px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
}
.admin-hero::before {
    content: "";
    position: absolute;
    top: -50px; right: -50px;
    width: 240px; height: 240px;
    background: radial-gradient(circle, #6C63FF1A, transparent 70%);
    border-radius: 50%;
}

/* Badges */
.badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
}
.badge-purple { background: #6C63FF22; color: #A89CFF; border: 1px solid #6C63FF55; }
.badge-green  { background: #00C85322; color: #00E870; border: 1px solid #00C85355; }
.badge-red    { background: #FF444422; color: #FF8080; border: 1px solid #FF444455; }
.badge-orange { background: #FF7A0022; color: #FFB347; border: 1px solid #FF7A0055; }

/* Tabs */
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

/* User row */
.user-row {
    background: #12122A;
    border: 1px solid #2A2A4A;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 8px;
}

/* Buttons */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6C63FF, #8B5CF6);
    border: none;
    border-radius: 10px;
    font-weight: 600;
}

/* Sidebar user card */
.sidebar-admin {
    background: linear-gradient(135deg, #2A0A40, #1A1A2E);
    border: 1px solid #6C63FF44;
    border-radius: 14px;
    padding: 16px;
    text-align: center;
    margin-bottom: 16px;
}
</style>
""", unsafe_allow_html=True)

init_session_state()
# Bounce teachers/students to their own dashboards before the admin gate fires.
if is_teacher():
    st.switch_page("pages/4_Teacher_Dashboard.py")
if is_student():
    st.switch_page("pages/2_Student_Dashboard.py")
require_admin()

# Apply the user's chosen color theme
apply_theme()

api = APIClient(st.session_state.get("token"))


# ─────────────────────────────────────────────────────────────────────────────
# SESSION-CACHED FETCH HELPER
# -----------------------------------------------------------------------------
# Streamlit re-runs the WHOLE page (every `with tab_x:` block) on every widget
# interaction — including interactions inside @st.dialog modals. Without
# caching, opening the Evaluation dialog would re-fetch the analytics / users
# / logs / pdfs from the backend on every keystroke and flash a "Loading…"
# spinner on top of the dialog. Memoize each tab's fetch in session_state —
# entries never expire on their own; the user controls when to refresh via
# the Refresh buttons (which bust the cache and rerun).
# ─────────────────────────────────────────────────────────────────────────────
import time as _time


def _cached_fetch(cache_key: str, fetch_fn, spinner_label: str = "Loading…"):
    """Return cached data for `cache_key` if present, else fetch + cache.
    Cache only invalidates when busted explicitly (Refresh button). Spinner
    only shows on a real fetch — never on a cache hit."""
    cache = st.session_state.setdefault("_admin_fetch_cache", {})
    entry = cache.get(cache_key)
    if entry is not None:
        return entry["data"]
    with st.spinner(spinner_label):
        data = fetch_fn()
    cache[cache_key] = {"data": data, "ts": _time.time()}
    return data


def _bust_cache(*cache_keys: str) -> None:
    """Invalidate one or more cached fetches so the next call re-fetches."""
    cache = st.session_state.get("_admin_fetch_cache") or {}
    for k in cache_keys:
        cache.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION FORMATTING HELPERS (used by Answer Evaluation dialog)
# ─────────────────────────────────────────────────────────────────────────────
def _format_questions_text(questions: list, show_options: bool = True, show_answer: bool = True) -> str:
    """Flatten a list of generated questions into a plain-text block for copying.
    Phase 4: includes `Class:` and `Subject:` lines so the parser can preserve
    them and the evaluator can apply class-aware grading."""
    lines: list[str] = []
    for i, q in enumerate(questions, start=1):
        lines.append(f"Q{i}. {q.get('question', '').strip()}")
        opts = q.get("options", {}) or {}
        if show_options and opts:
            for key in ("A", "B", "C", "D"):
                val = opts.get(key)
                if val and val != "Not applicable":
                    lines.append(f"   {key}) {val}")
        if show_answer:
            correct = str(q.get("correct_answer", "")).strip()
            if correct:
                lines.append(f"   Answer: {correct}")
            keywords = q.get("keywords") or []
            if keywords:
                lines.append(f"   Keywords: {', '.join(keywords)}")
            explanation = str(q.get("explanation", "")).strip()
            if explanation:
                lines.append(f"   Explanation: {explanation}")
            # Class + subject metadata (Phase 4)
            tc = q.get("target_class")
            if tc is not None:
                lines.append(f"   Class: {tc}")
            subj = q.get("subject")
            if subj:
                lines.append(f"   Subject: {subj}")
        lines.append("")
    return "\n".join(lines).strip()


def _render_question_preview(questions: list, mode: str):
    """Preview: show only the question text. Options, answers, keywords, and
    explanations stay in the copyable-text block above."""
    for i, q in enumerate(questions, start=1):
        st.markdown(f"**Q{i}.** {q.get('question', '')}")
        if mode == "mcq":
            opts = q.get("options", {}) or {}
            for key in ("A", "B", "C", "D"):
                val = opts.get(key)
                if val and val != "Not applicable":
                    st.markdown(f"&nbsp;&nbsp;**{key})** {val}", unsafe_allow_html=True)
        st.markdown("")


def _generate_and_store(key_prefix: str, pdf_id: str, pdf_label: str,
                        num_questions: int, difficulty: str,
                        question_type: str, topic: str,
                        target_class: int = None,
                        subject: str = None) -> None:
    """Call the quiz API and store results keyed by key_prefix in session_state.
    Phase 4: target_class + subject are forwarded so the prompt is tuned and
    every question is tagged."""
    try:
        result = api.generate_quiz(
            pdf_identifier=pdf_id,
            num_questions=num_questions,
            difficulty=difficulty,
            question_type=question_type,
            search_query=topic or None,
            target_class=target_class,
            subject=subject,
        )
        st.session_state[f"{key_prefix}_questions"] = result.get("questions", []) or []
        st.session_state[f"{key_prefix}_meta"] = {
            "pdf": pdf_label,
            "difficulty": difficulty,
            "topic": topic,
            "type": question_type,
            "target_class": target_class,
            "subject": subject,
        }
    except Exception as e:
        st.error(f"Generation failed: {e}")



# ─────────────────────────────────────────────────────────────────────────────
# ANSWER EVALUATION MODAL — hybrid keyword + semantic scoring
# ─────────────────────────────────────────────────────────────────────────────
def _render_eval_result(res: dict, fallback_expected: str = "") -> None:
    """Render a single evaluation result panel (score + breakdown + feedback)."""
    if not res:
        return
    if res.get("error"):
        st.error(f"Evaluation error: {res['error']}")
        return

    score = float(res.get("score_out_of_10") or 0)
    method = res.get("method", "?")
    kw = res.get("keyword_score") or {}
    sem = res.get("semantic_score") or {}
    band_label = res.get("grading_band_label") or ""
    mismatch = res.get("class_mismatch_warning")

    if mismatch:
        st.warning(f"⚠️ {mismatch}")

    score_color = "#00E870" if score >= 7 else ("#FFB347" if score >= 4 else "#FF8080")
    band_caption = f" · {band_label}" if band_label else ""
    st.markdown(
        f"""
        <div style="text-align:center; padding:12px; background:#12122A;
                    border:1px solid #2A2A4A; border-radius:12px; margin-bottom:12px;">
            <div style="font-size:0.74rem; color:#888; text-transform:uppercase;
                        letter-spacing:1px;">Score · method: {method}{band_caption}</div>
            <div style="font-size:2.0rem; font-weight:800; color:{score_color}; margin:4px 0;">
                {score:.1f} / 10
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(min(1.0, max(0.0, score / 10.0)))

    c_kw, c_sem = st.columns(2)
    with c_kw:
        st.markdown("**Keyword score**")
        st.markdown(
            f"{kw.get('matched_count', 0)} / {kw.get('total', 0)} "
            f"({(kw.get('ratio', 0) * 100):.0f}%) → "
            f"**{kw.get('score_out_of_10', 0):.1f}/10**"
        )
        if kw.get("matched"):
            chips = " ".join(
                f'<span style="background:#0D2010; border:1px solid #00C85355;'
                f' border-radius:10px; padding:2px 8px; margin:2px 3px 0 0;'
                f' font-size:0.78rem; color:#00E870; display:inline-block;">{m}</span>'
                for m in kw["matched"]
            )
            st.markdown(f"<div style='margin-top:4px;'>{chips}</div>", unsafe_allow_html=True)
        if kw.get("missed"):
            chips = " ".join(
                f'<span style="background:#1A0A0A; border:1px solid #FF444455;'
                f' border-radius:10px; padding:2px 8px; margin:2px 3px 0 0;'
                f' font-size:0.78rem; color:#FF8080; display:inline-block;">{m}</span>'
                for m in kw["missed"]
            )
            st.markdown(
                f"<div style='margin-top:4px;'><span style='color:#888;font-size:0.78rem;'>"
                f"Missed:</span> {chips}</div>",
                unsafe_allow_html=True,
            )
    with c_sem:
        st.markdown("**Semantic score**")
        st.markdown(f"**{sem.get('semantic_score_out_of_10', 0):.1f}/10**")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### ✅ Correct points")
        cps = res.get("correct_points") or []
        if cps:
            for p in cps:
                st.markdown(f"- {p}")
        else:
            st.caption("_(none reported)_")

        st.markdown("##### 💡 Improvements")
        ims = res.get("improvements") or []
        if ims:
            for p in ims:
                st.markdown(f"- {p}")
        else:
            st.caption("_(none reported)_")
    with c2:
        st.markdown("##### ❌ Mistakes")
        mks = res.get("mistakes") or []
        if mks:
            for p in mks:
                st.markdown(f"- {p}")
        else:
            st.caption("_(none reported)_")

        st.markdown("##### 📖 Correct answer")
        ca = res.get("correct_answer") or fallback_expected or ""
        st.markdown(ca or "_(not provided)_")


def _render_per_question_card(qi: int, block: dict) -> None:
    """Render one question card: rubric + upload + answer textarea + per-question result."""
    q_text = block.get("question", "") or f"Question {qi+1}"
    expected = block.get("expected_answer", "") or ""
    keywords = block.get("keywords") or []

    widget_key = f"ev_student_answer_{qi}"
    pending_key = f"_ev_pending_extract_{qi}"
    file_key_state = f"ev_extract_key_{qi}"
    uploader_key = f"ev_file_uploader_{qi}"
    extract_btn_key = f"ev_extract_btn_{qi}"

    # Inject any pending OCR text BEFORE the textarea widget renders
    pe = st.session_state.pop(pending_key, None)
    if pe is not None:
        st.session_state[widget_key] = pe

    with st.container(border=True):
        st.markdown(f"**Q{qi+1}.** {q_text}")
        with st.expander("Rubric (expected answer + keywords)", expanded=False):
            st.markdown(f"**Expected:** {expected or '_(none)_'}")
            st.markdown(
                "**Keywords:** "
                + (", ".join(keywords) if keywords else "_(none)_")
            )

        uf = st.file_uploader(
            f"Upload Q{qi+1} answer (PDF / JPG / PNG, optional)",
            type=["pdf", "jpg", "jpeg", "png", "webp", "bmp"],
            key=uploader_key,
        )
        if uf is not None:
            fk = f"{uf.name}_{uf.size}"
            need_extract = st.session_state.get(file_key_state) != fk
            cu1, cu2 = st.columns([3, 1])
            with cu1:
                st.caption(f"Selected: **{uf.name}** ({uf.size // 1024} KB)")
            with cu2:
                trigger = st.button(
                    "Extract" if need_extract else "Re-extract",
                    width="stretch", key=extract_btn_key,
                )
            if trigger:
                with st.spinner("Extracting…"):
                    try:
                        res = api.extract_text_from_upload(uf.getvalue(), uf.name)
                        ext = res.get("text", "")
                        if not ext:
                            st.warning(res.get("warning") or "No text extracted.")
                        else:
                            st.session_state[pending_key] = ext
                            st.session_state[file_key_state] = fk
                            st.toast(
                                f"Q{qi+1}: extracted {res.get('char_count', 0)} chars",
                                icon="✅",
                            )
                            st.rerun()
                    except Exception as e:
                        st.error(f"Extraction failed: {e}")

        st.text_area(
            f"Student answer for Q{qi+1}",
            height=130,
            placeholder="Type, paste, or extract from a file above.",
            key=widget_key,
        )

        per_result = (st.session_state.get("ev_batch_results") or {}).get(qi)
        if per_result:
            st.markdown("---")
            _render_eval_result(per_result, fallback_expected=expected)


@st.dialog("📝 Answer Evaluation", width="large")
def _answer_evaluation_dialog():
    st.caption(
        "Evaluate one or many student answers against expected answers + keywords. "
        "Paste a formatted question block to batch-evaluate every parsed question, "
        "or use Manual entry for a single ad-hoc check."
    )

    # ── Phase 4 + Phase 6: student class + subject feed the grading rubric ──
    sc_col, ss_col = st.columns([1, 2])
    with sc_col:
        student_class = st.selectbox(
            "Student's class",
            list(range(1, 11)), index=4,  # default class 5
            key="ev_student_class",
            help="Used to pick the grading band (Primary / Upper Primary / Middle / Secondary).",
        )
    with ss_col:
        ev_subject = st.selectbox(
            "Subject (optional)",
            ["", "Math", "Science", "English", "Social", "Computer"],
            index=0, key="ev_subject",
            help="Layers subject-specific instructions onto the rubric.",
        )
    ev_subject_value = ev_subject or None

    # Show which grading band will apply, plus the subject overlay (Phase 2 + 6)
    # Cached — without this, every keystroke in the dialog re-fetches and the
    # popup flashes a spinner / goes blank (same bug pattern as analytics).
    with st.expander("📐 Grading rubric that will be applied", expanded=False):
        try:
            stds = _cached_fetch(
                "grading_standards",
                lambda: api.get_grading_standards(),
                spinner_label="Loading grading standards…",
            )
            bands = stds.get("bands", []) or []
            cl = int(student_class)
            active_band = None
            for b in bands:
                if int(b.get("class_min", 1)) <= cl <= int(b.get("class_max", 10)):
                    active_band = b
                    break
            if active_band:
                st.markdown(f"**Active band:** {active_band.get('label', '?')}")
                st.caption(
                    f"Vocab tolerance: {active_band.get('vocab_tolerance')} · "
                    f"Partial credit: {active_band.get('partial_credit_generosity')} · "
                    f"Keyword pass ratio: {active_band.get('keyword_pass_ratio')}"
                )
                for instr in active_band.get("rubric_instructions", []):
                    st.markdown(f"- {instr}")
            if ev_subject_value:
                subj_extra = (stds.get("subjects") or {}).get(ev_subject_value, {})
                xs = subj_extra.get("extra_instructions") or []
                if xs:
                    st.markdown(f"**Subject overlay ({ev_subject_value}):**")
                    for instr in xs:
                        st.markdown(f"- {instr}")
        except Exception as e:
            st.caption(f"_(could not load grading standards: {e})_")

    src_tab_paste, src_tab_manual = st.tabs(
        ["📋 Paste questions (batch)", "✍️ Manual entry (single)"]
    )

    parsed_blocks: list = st.session_state.get("ev_parsed_blocks", [])

    # ──────────────────────────────────────────────────────────────────
    # PASTE / BATCH TAB
    # ──────────────────────────────────────────────────────────────────
    with src_tab_paste:
        copyable_text = st.text_area(
            "Paste the formatted question block",
            value=st.session_state.get("ev_copyable_text", ""),
            height=160,
            placeholder=(
                "Q1. What are the main components of the atmosphere?\n"
                "    Answer: Troposphere, Stratosphere, Mesosphere\n"
                "    Keywords: components, atmosphere, layers\n"
                "    Explanation: ...\n\n"
                "Q2. ..."
            ),
            key="ev_copyable_input",
        )
        c_parse, c_clear = st.columns([1, 1])
        with c_parse:
            if st.button("Parse questions", width="stretch", key="ev_parse_btn"):
                try:
                    res = api.parse_questions(copyable_text)
                    parsed_blocks = res.get("blocks", [])
                    st.session_state["ev_parsed_blocks"] = parsed_blocks
                    st.session_state["ev_copyable_text"] = copyable_text
                    # Reset prior answers / results when re-parsing
                    st.session_state["ev_batch_results"] = {}
                    if not parsed_blocks:
                        st.warning("No questions detected. Check the format or use Manual entry.")
                except Exception as e:
                    st.error(f"Parse failed: {e}")
        with c_clear:
            if st.button("Clear parsed", width="stretch", key="ev_clear_btn"):
                # Clean up all per-question session_state slots
                for qi in range(len(parsed_blocks)):
                    for k in (
                        f"ev_student_answer_{qi}",
                        f"_ev_pending_extract_{qi}",
                        f"ev_extract_key_{qi}",
                        f"ev_file_uploader_{qi}",
                        f"ev_extract_btn_{qi}",
                    ):
                        st.session_state.pop(k, None)
                st.session_state["ev_parsed_blocks"] = []
                st.session_state["ev_copyable_text"] = ""
                st.session_state["ev_batch_results"] = {}
                st.rerun()

        if parsed_blocks:
            st.markdown(
                f"##### Parsed **{len(parsed_blocks)}** question(s) — "
                f"fill in each student answer below"
            )

            # Aggregate score banner if we already have results
            results_map = st.session_state.get("ev_batch_results") or {}
            valid_scores = [
                float(r.get("score_out_of_10") or 0)
                for r in results_map.values()
                if r and not r.get("error")
            ]
            if valid_scores:
                avg = sum(valid_scores) / len(valid_scores)
                avg_color = "#00E870" if avg >= 7 else ("#FFB347" if avg >= 4 else "#FF8080")
                st.markdown(
                    f"""
                    <div style="background:#12122A; border:1px solid #2A2A4A;
                                border-radius:12px; padding:12px; margin-bottom:12px;
                                display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <div style="font-size:0.74rem; color:#888;
                                        text-transform:uppercase; letter-spacing:1px;">
                                Average across {len(valid_scores)} answered question(s)
                            </div>
                            <div style="font-size:1.6rem; font-weight:800; color:{avg_color};">
                                {avg:.1f} / 10
                            </div>
                        </div>
                        <div style="font-size:0.85rem; color:#888;">
                            Total: {sum(valid_scores):.1f} / {len(valid_scores) * 10}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Render every parsed question with its own answer field + result
            for qi, block in enumerate(parsed_blocks):
                _render_per_question_card(qi, block)

            st.markdown("---")
            if st.button(
                "🔎 Evaluate All Answered Questions",
                type="primary",
                width="stretch",
                key="ev_batch_run",
            ):
                results_map: dict = {}
                evaluated = 0
                progress = st.progress(0.0, text="Starting…")
                total = len(parsed_blocks)
                for qi, block in enumerate(parsed_blocks):
                    ans = (st.session_state.get(f"ev_student_answer_{qi}") or "").strip()
                    if not ans:
                        progress.progress((qi + 1) / total, text=f"Q{qi+1}: skipped (no answer)")
                        continue
                    progress.progress((qi + 0.1) / total, text=f"Evaluating Q{qi+1}…")
                    try:
                        r = api.evaluate_answer(
                            student_answer=ans,
                            question=block.get("question", "") or "",
                            expected_answer=block.get("expected_answer", "") or "",
                            keywords=block.get("keywords") or [],
                            student_class=int(student_class),
                            target_class=block.get("target_class"),
                            subject=block.get("subject") or ev_subject_value,
                        )
                        results_map[qi] = r
                        evaluated += 1
                    except Exception as e:
                        results_map[qi] = {"error": str(e)}
                    progress.progress((qi + 1) / total, text=f"Q{qi+1}: done")
                st.session_state["ev_batch_results"] = results_map
                if evaluated == 0:
                    st.warning("No student answers were filled in. Add at least one answer.")
                else:
                    st.success(f"Evaluated {evaluated} of {total} question(s).")
                    st.rerun()

    # ──────────────────────────────────────────────────────────────────
    # MANUAL ENTRY TAB — single ad-hoc evaluation
    # ──────────────────────────────────────────────────────────────────
    with src_tab_manual:
        manual_q = st.text_area(
            "Question",
            value=st.session_state.get("ev_manual_q", ""),
            height=70, key="ev_manual_q_input",
        )
        manual_a = st.text_area(
            "Expected answer",
            value=st.session_state.get("ev_manual_a", ""),
            height=100, key="ev_manual_a_input",
        )
        manual_kws = st.text_input(
            "Keywords (comma-separated)",
            value=st.session_state.get("ev_manual_kws", ""),
            placeholder="atmosphere, troposphere, stratosphere",
            key="ev_manual_kws_input",
        )

        m_final_q = (manual_q or "").strip()
        m_final_a = (manual_a or "").strip()
        m_kws_str = (manual_kws or "").strip()
        m_keywords = [k.strip() for k in m_kws_str.split(",") if k.strip()] if m_kws_str else []

        st.markdown("##### Student answer")

        pe_manual = st.session_state.pop("_ev_pending_extract_manual", None)
        if pe_manual is not None:
            st.session_state["ev_student_answer_manual"] = pe_manual

        m_uf = st.file_uploader(
            "Upload (optional)",
            type=["pdf", "jpg", "jpeg", "png", "webp", "bmp"],
            key="ev_file_uploader_manual",
        )
        if m_uf is not None:
            fk = f"{m_uf.name}_{m_uf.size}"
            if st.button("Extract text", width="stretch", key="ev_extract_btn_manual"):
                with st.spinner("Extracting…"):
                    try:
                        r = api.extract_text_from_upload(m_uf.getvalue(), m_uf.name)
                        ext = r.get("text", "")
                        if not ext:
                            st.warning(r.get("warning") or "No text extracted.")
                        else:
                            st.session_state["_ev_pending_extract_manual"] = ext
                            st.session_state["ev_extract_key_manual"] = fk
                            st.rerun()
                    except Exception as e:
                        st.error(f"Extraction failed: {e}")

        m_student = st.text_area(
            "Student answer (editable)",
            height=180,
            key="ev_student_answer_manual",
        )

        if st.button(
            "🔎 Evaluate Answer",
            type="primary",
            width="stretch",
            key="ev_run_btn_manual",
        ):
            if not m_student.strip():
                st.warning("Please paste the student's answer first.")
            elif not m_keywords and not (m_final_q and m_final_a):
                st.warning("Provide either keywords or a question + expected answer.")
            else:
                with st.spinner("Evaluating…"):
                    try:
                        result = api.evaluate_answer(
                            student_answer=m_student,
                            question=m_final_q,
                            expected_answer=m_final_a,
                            keywords=m_keywords,
                            student_class=int(student_class),
                            subject=ev_subject_value,
                        )
                        st.session_state["ev_manual_result"] = result
                    except Exception as e:
                        st.error(f"Evaluation failed: {e}")
                        st.session_state.pop("ev_manual_result", None)

        manual_res = st.session_state.get("ev_manual_result")
        if manual_res:
            st.markdown("---")
            _render_eval_result(manual_res, fallback_expected=m_final_a)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    name  = st.session_state.get("full_name") or st.session_state.get("username", "Admin")
    email = st.session_state.get("user_email", "")

    st.markdown(f"""
    <div class="sidebar-admin">
        <div style="font-size:2.2rem; margin-bottom:6px;">🛡️</div>
        <div style="font-size:1rem; font-weight:700; color:var(--text);">{name}</div>
        <div style="font-size:0.78rem; color:#888; margin-top:3px;">{email}</div>
        <div style="margin-top:10px;">
            <span class="badge badge-purple">Administrator</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<p style="font-size:0.82rem; color:#555; margin:0 0 10px 0; text-align:center;">Use the tabs on the right →</p>', unsafe_allow_html=True)

    st.markdown('<hr style="border-color:#2A2A4A; margin:8px 0 16px 0;">', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.82rem; font-weight:700; color:var(--accent-soft); margin:0 0 8px 0;">UPLOAD PDF</p>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload a PDF",
        type=["pdf"],
        label_visibility="collapsed",
        key="admin_pdf_upload",
    )
    if uploaded_file is not None:
        file_key = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.get("admin_last_upload_key") != file_key:
            with st.spinner("Uploading…"):
                try:
                    api.upload_pdf(uploaded_file.getvalue(), uploaded_file.name)
                    st.session_state["admin_last_upload_key"] = file_key
                    st.success(f"Uploaded: {uploaded_file.name}")
                except Exception as e:
                    st.error(f"Upload failed: {e}")
    st.caption("200 MB max · PDF only")

    st.markdown('<hr style="border-color:#2A2A4A; margin:16px 0;">', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.82rem; font-weight:700; color:var(--accent-soft); margin:0 0 8px 0;">QUICK ACTIONS</p>', unsafe_allow_html=True)

    if st.button("📊 Refresh All Data", width="stretch"):
        # Bust every cached fetch so all tabs re-pull fresh data on next render
        st.session_state["_admin_fetch_cache"] = {}
        st.rerun()

    # ── Theme selector ──────────────────────────────────────────────────
    st.markdown('<hr style="border-color:var(--border-soft); margin:16px 0;">', unsafe_allow_html=True)
    render_theme_selector(api_client=api)

    st.markdown('<hr style="border-color:var(--border-soft); margin:16px 0;">', unsafe_allow_html=True)
    if st.button("🚪 Logout", width="stretch"):
        logout()
        st.switch_page("pages/1_Login.py")


# ─────────────────────────────────────────────────────────────────────────────
# HERO
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="admin-hero">
    <div style="font-size:0.82rem; color:var(--accent-soft); font-weight:600; letter-spacing:1px; text-transform:uppercase;">Control Center</div>
    <h2 style="margin:4px 0 6px 0; font-size:1.7rem; color:var(--text);">Admin Dashboard 🛡️</h2>
    <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:8px;">
        <span style="background:var(--surface-3); border:1px solid var(--border); border-radius:20px; padding:5px 14px; font-size:0.8rem; color:var(--text);">📊 Analytics</span>
        <span style="background:var(--surface-3); border:1px solid var(--border); border-radius:20px; padding:5px 14px; font-size:0.8rem; color:var(--text);">👥 User Management</span>
        <span style="background:var(--surface-3); border:1px solid var(--border); border-radius:20px; padding:5px 14px; font-size:0.8rem; color:var(--text);">🔐 Roles & Permissions</span>
        <span style="background:var(--surface-3); border:1px solid var(--border); border-radius:20px; padding:5px 14px; font-size:0.8rem; color:var(--text);">📋 Audit Logs</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# NAV BAR — Evaluate Answer launcher
# ─────────────────────────────────────────────────────────────────────────────
nav_left, nav_eval = st.columns([4, 1])
with nav_eval:
    if st.button("📝  Evaluate Answer", type="primary", width="stretch", key="open_eval"):
        _answer_evaluation_dialog()

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
(
    tab_analytics, tab_users, tab_roles, tab_rate_limits, tab_logs,
    tab_pdfs, tab_eval, tab_export,
) = st.tabs([
    "📊 Analytics", "👥 Users", "🔐 Roles & Permissions", "⏱️ Rate Limits",
    "📋 Activity", "📄 All PDFs", "🧪 AI Evaluation", "📥 Export",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_analytics:
    col_ra, col_ts, _ = st.columns([1, 2, 4])
    with col_ra:
        if st.button("🔄 Refresh", width="stretch", key="ref_analytics"):
            _bust_cache("analytics")
            st.rerun()
    cache_entry = (st.session_state.get("_admin_fetch_cache") or {}).get("analytics")
    if cache_entry:
        with col_ts:
            age = int(_time.time() - cache_entry["ts"])
            st.caption(f"Last updated {age}s ago · click Refresh to update")

    try:
        analytics = _cached_fetch("analytics", api.get_analytics,
                                   spinner_label="Loading analytics…")
    except RuntimeError as e:
        st.error(str(e))
        analytics = {}

    metrics       = analytics.get("metrics", {})
    usage_time    = analytics.get("usage_over_time", [])
    feature_usage = analytics.get("feature_usage", {})

    total_users  = metrics.get("total_users", 0)
    active_users = metrics.get("active_users", 0)
    total_pdfs   = metrics.get("total_pdfs", 0)
    ai_calls     = metrics.get("total_ai_calls", 0)

    st.markdown(f"""
    <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:20px;">
        <div class="stat-card stat-purple">
            <div class="num">{total_users}</div>
            <div class="lbl">👥 Total Users</div>
        </div>
        <div class="stat-card stat-green">
            <div class="num">{active_users}</div>
            <div class="lbl">✅ Active Users</div>
        </div>
        <div class="stat-card stat-blue">
            <div class="num">{total_pdfs}</div>
            <div class="lbl">📄 Uploaded PDFs</div>
        </div>
        <div class="stat-card stat-orange">
            <div class="num">{ai_calls}</div>
            <div class="lbl">🤖 AI API Calls</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown("""
        <div style="background:#12122A; border:1px solid #2A2A4A; border-radius:12px; padding:16px 18px; margin-bottom:6px;">
            <div style="color:var(--accent-soft); font-weight:700; font-size:0.85rem; margin-bottom:12px;">📈 ACTIVITY — LAST 7 DAYS</div>
        </div>
        """, unsafe_allow_html=True)
        if usage_time:
            df_time = (
                pd.DataFrame(usage_time)
                .rename(columns={"date": "Date", "count": "Actions"})
                .set_index("Date")
            )
            st.line_chart(df_time["Actions"], width="stretch")
        else:
            st.markdown("""
            <div style="background:#12122A; border:1px solid #2A2A4A; border-radius:10px;
                        padding:32px; text-align:center; color:#555; font-size:0.88rem;">
                No activity data yet
            </div>
            """, unsafe_allow_html=True)

    with col_chart2:
        st.markdown("""
        <div style="background:#12122A; border:1px solid #2A2A4A; border-radius:12px; padding:16px 18px; margin-bottom:6px;">
            <div style="color:var(--accent-soft); font-weight:700; font-size:0.85rem; margin-bottom:12px;">🔧 FEATURE USAGE BREAKDOWN</div>
        </div>
        """, unsafe_allow_html=True)
        if feature_usage:
            rows = [
                {"Feature": k.replace("_", " ").title(), "Count": v}
                for k, v in feature_usage.items() if v > 0
            ]
            if rows:
                df_feat = pd.DataFrame(rows).set_index("Feature")
                st.bar_chart(df_feat["Count"], width="stretch")
            else:
                st.markdown('<div style="background:#12122A; border:1px solid #2A2A4A; border-radius:10px; padding:32px; text-align:center; color:#555; font-size:0.88rem;">No feature usage yet</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="background:#12122A; border:1px solid #2A2A4A; border-radius:10px; padding:32px; text-align:center; color:#555; font-size:0.88rem;">No feature data yet</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — USERS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_users:
    col_ref, col_search = st.columns([1, 4])
    with col_ref:
        if st.button("🔄 Refresh", key="ref_users"):
            _bust_cache("users")
            st.rerun()
    with col_search:
        user_search = st.text_input(
            "Search", placeholder="🔍  Filter by email or username…",
            label_visibility="collapsed",
        )

    try:
        users = _cached_fetch(
            "users",
            lambda: api.get_all_users().get("users", []),
            spinner_label="Loading users…",
        )
    except RuntimeError as e:
        st.error(str(e))
        users = []

    if user_search:
        q     = user_search.lower()
        users = [u for u in users if q in u.get("email","").lower() or q in u.get("username","").lower()]

    if not users:
        st.markdown("""
        <div class="card" style="text-align:center; padding:28px;">
            <div style="font-size:2.4rem;">👥</div>
            <div style="color:var(--accent-soft); font-weight:600; margin-top:8px;">No Users Found</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Optional role filter
        role_filter = st.selectbox(
            "Filter by role",
            ["All", "student", "teacher", "admin"],
            index=0, key="user_role_filter",
            label_visibility="collapsed",
        )
        if role_filter != "All":
            users = [
                u for u in users
                if (u.get("role") or ("admin" if u.get("is_admin") else "student")) == role_filter
            ]

        st.markdown(f'<p style="color:#666; font-size:0.82rem; margin-bottom:10px;">{len(users)} user(s)</p>', unsafe_allow_html=True)

        ALL_CS = [f"{c}{s}" for c in range(1, 11) for s in ("A", "B", "C")]
        ALL_SUBJ = ["Math", "Science", "English", "Social", "Computer"]

        for user in users:
            is_active = user.get("is_active", True)
            # Resolve role: prefer the explicit `role` field; fall back to is_admin
            role = user.get("role") or ("admin" if user.get("is_admin") else "student")
            if role == "admin":
                role_badge = '<span class="badge badge-purple">Admin</span>'
            elif role == "teacher":
                role_badge = '<span class="badge badge-orange">Teacher</span>'
            else:
                role_badge = '<span class="badge badge-green">Student</span>'
            status_badge = '<span class="badge badge-green">Active</span>' if is_active else '<span class="badge badge-red">Inactive</span>'
            last_login = user.get("last_login", "Never")
            if last_login and last_login != "Never":
                last_login = str(last_login)[:16].replace("T", " ")

            # Class / assignment summary
            if role == "student":
                cs = user.get("class_section") or (
                    f"{user.get('class_level')}{user.get('section')}"
                    if user.get('class_level') and user.get('section') else "—"
                )
                hierarchy_line = f"📚 Class <strong>{cs}</strong>"
            elif role == "teacher":
                subs = ", ".join(user.get("subjects_taught") or []) or "—"
                cls = ", ".join(user.get("assigned_classes") or []) or "—"
                hierarchy_line = f"📖 {subs} &nbsp;·&nbsp; 🏫 {cls}"
            else:
                hierarchy_line = "🛡️ Full system access"

            c1, c2, c3 = st.columns([4, 3, 1])
            with c1:
                st.markdown(f"""
                <div style="padding:4px 0;">
                    <strong style="color:var(--text);">{user.get('username','')}</strong>
                    <span style="color:#666; font-size:0.85rem;"> · {user.get('email','')}</span><br>
                    <div style="margin-top:5px;">{role_badge} &nbsp; {status_badge}</div>
                    <div style="margin-top:5px; font-size:0.82rem; color:var(--accent-soft);">{hierarchy_line}</div>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div style="font-size:0.78rem; color:#888; padding:4px 0;">
                    Last login: {last_login}<br>
                    Logins: {user.get('login_count', 0)} · Joined {str(user.get('created_at',''))[:10]}
                </div>
                """, unsafe_allow_html=True)
            with c3:
                if is_active:
                    if st.button("Deactivate", key=f"deact_{user['id']}", type="secondary", width="stretch"):
                        try:
                            api.update_user_status(user["id"], False)
                            _bust_cache("users")
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))
                else:
                    if st.button("Activate", key=f"act_{user['id']}", type="primary", width="stretch"):
                        try:
                            api.update_user_status(user["id"], True)
                            _bust_cache("users")
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))

            # Inline editor for class / teacher assignment
            if role in ("student", "teacher"):
                with st.expander(
                    f"✏️ Edit {'class' if role=='student' else 'teacher assignments'}",
                    expanded=False,
                ):
                    if role == "student":
                        ec1, ec2, ec3 = st.columns([1, 1, 1])
                        with ec1:
                            new_cls = st.selectbox(
                                "Class", list(range(1, 11)),
                                index=(int(user.get("class_level") or 1) - 1),
                                key=f"cls_{user['id']}",
                            )
                        with ec2:
                            new_sec = st.selectbox(
                                "Section", ["A", "B", "C"],
                                index=["A","B","C"].index(user.get("section") or "A"),
                                key=f"sec_{user['id']}",
                            )
                        with ec3:
                            if st.button("Save class", key=f"save_cls_{user['id']}", width="stretch"):
                                try:
                                    api.admin_update_user_class(user["id"], new_cls, new_sec)
                                    _bust_cache("users")
                                    st.toast(f"Updated to {new_cls}{new_sec}", icon="✅")
                                    st.rerun()
                                except RuntimeError as e:
                                    st.error(str(e))
                    else:  # teacher
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            new_subs = st.multiselect(
                                "Subjects", ALL_SUBJ,
                                default=user.get("subjects_taught") or [],
                                key=f"sub_{user['id']}",
                            )
                        with ec2:
                            new_cls = st.multiselect(
                                "Assigned classes", ALL_CS,
                                default=user.get("assigned_classes") or [],
                                key=f"acls_{user['id']}",
                            )
                        if st.button("Save teacher assignments", key=f"save_t_{user['id']}", width="stretch"):
                            if not new_subs or not new_cls:
                                st.error("Pick at least one subject and one class.")
                            else:
                                try:
                                    api.admin_assign_teacher(user["id"], new_subs, new_cls)
                                    _bust_cache("users")
                                    st.toast("Teacher assignments updated", icon="✅")
                                    st.rerun()
                                except RuntimeError as e:
                                    st.error(str(e))

            st.markdown('<hr style="border-color:#1E1E3A; margin:6px 0;">', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ROLES & PERMISSIONS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_roles:
    st.markdown("### 🔐 Roles & Permissions Matrix")
    st.caption(
        "Role hierarchy and feature access across the platform. "
        "These permissions are enforced server-side via JWT-based role checks."
    )

    # ── Permissions Matrix (toggleable) ──
    st.markdown("#### 📋 Permissions Matrix")
    st.caption(
        "Toggle a permission to immediately grant or revoke access. "
        "Changes are enforced server-side on the next API call."
    )

    # Each entry: (feature_key, label, applies_to_admin, applies_to_teacher, applies_to_student)
    PERMISSION_FEATURES = [
        ("view_analytics",        "📊 View System Analytics",          True,  False, False),
        ("manage_users",          "👥 Manage All Users",                True,  False, False),
        ("toggle_user_status",    "🔧 Activate / Deactivate Users",     True,  False, False),
        ("assign_class_section",  "📚 Assign Class & Section",          True,  False, False),
        ("assign_teacher_subjects", "📖 Assign Teacher Subjects",       True,  False, False),
        ("view_audit_logs",       "📋 View Audit Logs",                 True,  False, False),
        ("export_data",           "📥 Export Data (CSV)",               True,  False, False),
        ("create_assignments",    "📝 Create Assignments",              False, True,  False),
        ("edit_assignments",      "✏️ Edit / Delete Own Assignments",   False, True,  False),
        ("override_grading",      "⚖️ Override AI Grading",             False, True,  False),
        ("view_submissions",      "👀 View Student Submissions",        False, True,  False),
        ("upload_pdfs",           "📤 Upload PDFs",                     True,  True,  True),
        ("use_ai_tools",          "🤖 Use AI Study Tools (Q&A, Quiz)",  True,  True,  True),
        ("submit_assignments",    "📨 Submit Assignments",              False, False, True),
        ("view_own_grades",       "📊 View Own Grades & Feedback",      False, False, True),
        ("change_password",       "🔑 Change Own Password",             True,  True,  True),
    ]

    # Load current permission state from backend (cached)
    try:
        perms_resp = _cached_fetch(
            "permissions",
            lambda: api.admin_get_permissions(),
            spinner_label="Loading permissions…",
        )
        current_perms = perms_resp.get("permissions", {}) or {}
    except Exception as e:
        st.error(f"Could not load permissions: {e}")
        current_perms = {}

    def _is_enabled(role: str, feature: str, default: bool = False) -> bool:
        """Return whether the toggle should be ON. If backend has an explicit
        value, use it; otherwise fall back to the default for that role/feature."""
        role_perms = current_perms.get(role) or {}
        if feature in role_perms:
            return bool(role_perms[feature])
        return default

    def _on_toggle(role: str, feature: str, widget_key: str):
        """Callback fired when a permission toggle changes — pushes to backend."""
        new_val = bool(st.session_state.get(widget_key, True))
        try:
            api.admin_set_permission(role, feature, new_val)
            _bust_cache("permissions")
            st.toast(
                f"{'✅ Granted' if new_val else '🚫 Revoked'} '{feature}' for {role}s",
                icon="✅" if new_val else "🚫",
            )
        except Exception as exc:
            st.toast(f"Failed: {exc}", icon="❌")
            # Revert the toggle in session state on failure
            st.session_state[widget_key] = not new_val

    # Header row
    h_cols = st.columns([3, 1, 1, 1])
    h_cols[0].markdown("**Feature / Permission**")
    h_cols[1].markdown("**🛡️ Admin**")
    h_cols[2].markdown("**👨‍🏫 Teacher**")
    h_cols[3].markdown("**👨‍🎓 Student**")
    st.markdown("<hr style='border-color:#2A2A4A; margin:4px 0 8px 0;'>", unsafe_allow_html=True)

    # Permission rows with toggles. Every cell is now a toggle:
    #   - "default ON" cells (the role's intended features) start ON unless the
    #     admin has explicitly turned them off
    #   - "default OFF" cells (cross-role grants) start OFF unless the admin
    #     explicitly turns them on
    for feature_key, label, default_admin, default_teacher, default_student in PERMISSION_FEATURES:
        row_cols = st.columns([3, 1, 1, 1])
        row_cols[0].markdown(label)

        for idx, (role, default_on) in enumerate(
            [("admin", default_admin), ("teacher", default_teacher), ("student", default_student)],
            start=1,
        ):
            with row_cols[idx]:
                widget_key = f"perm_{role}_{feature_key}"
                st.toggle(
                    " ",
                    value=_is_enabled(role, feature_key, default=default_on),
                    key=widget_key,
                    label_visibility="collapsed",
                    on_change=_on_toggle,
                    args=(role, feature_key, widget_key),
                )

    st.markdown("---")

    # ── User Role Distribution ──
    st.markdown("#### 📊 Role Distribution")
    try:
        users_for_roles = _cached_fetch(
            "users",
            lambda: api.get_all_users().get("users", []),
            spinner_label="Loading role distribution…",
        )
    except RuntimeError:
        users_for_roles = []

    role_counts = {"admin": 0, "teacher": 0, "student": 0}
    for u in users_for_roles:
        r = u.get("role") or ("admin" if u.get("is_admin") else "student")
        if r in role_counts:
            role_counts[r] += 1

    rd_cols = st.columns(3)
    with rd_cols[0]:
        st.markdown(f"""
        <div class="stat-card stat-purple">
            <div class="num">{role_counts['admin']}</div>
            <div class="lbl">🛡️ Administrators</div>
        </div>
        """, unsafe_allow_html=True)
    with rd_cols[1]:
        st.markdown(f"""
        <div class="stat-card stat-orange">
            <div class="num">{role_counts['teacher']}</div>
            <div class="lbl">👨‍🏫 Teachers</div>
        </div>
        """, unsafe_allow_html=True)
    with rd_cols[2]:
        st.markdown(f"""
        <div class="stat-card stat-green">
            <div class="num">{role_counts['student']}</div>
            <div class="lbl">👨‍🎓 Students</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Security Notes ──
    with st.expander("🔒 Security & Enforcement Details", expanded=False):
        st.markdown("""
        - **Authentication:** JWT Bearer tokens (HS256, 30-min expiry)
        - **Password Hashing:** bcrypt with auto-generated salt
        - **Authorization:** Role checks enforced via FastAPI dependency injection
            - `get_admin_user()` — admin-only endpoints
            - `get_teacher_user()` — teacher-only endpoints
            - `get_student_user()` — student-only endpoints
        - **Class Ownership:** Teachers can only access students/submissions for their assigned classes
        - **Submission Privacy:** Students can only view their own submissions
        - **Audit Logging:** All sensitive actions are logged with timestamp and user email
        """)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — RATE LIMITS (admin-controlled per-day AI quotas)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_rate_limits:
    st.markdown("### ⏱️ AI Feature Rate Limits")
    st.caption(
        "Daily quotas per AI feature. Counters reset at server midnight. "
        "**-1 = unlimited**, **0 = disabled**. Students/teachers who exceed "
        "their quota get HTTP 429 until midnight. Admins are never rate-limited."
    )

    _FEATURE_LABELS = {
        "qa": "💬 Q&A Chat",
        "summary": "📝 Summary Generation",
        "quiz": "❓ Quiz Generation",
        "audio": "🔊 Audio Generation",
        "video": "🎬 Video Generation",
    }

    try:
        rl_resp = _cached_fetch(
            "rate_limits",
            lambda: api.admin_get_rate_limits(),
            spinner_label="Loading rate limits…",
        )
    except Exception as e:
        st.error(f"Failed to load rate limits: {e}")
        rl_resp = {"limits": {}, "features": [], "roles": []}

    features = rl_resp.get("features") or []
    current = rl_resp.get("limits") or {}
    # Backend may still include admin in the roles list for legacy reasons —
    # we explicitly drop it from the UI since admins are unmetered server-side.
    EDITABLE_ROLES = [r for r in (rl_resp.get("roles") or []) if r in ("student", "teacher")]

    if not features or not EDITABLE_ROLES:
        st.warning("Backend returned no features/roles — restart the backend to pick up the rate-limit endpoints.")
    else:
        # Two side-by-side sections: Student (left) | Teacher (right). Each
        # section is a self-contained list of feature → number_input rows.
        def _render_role_section(role: str, header: str):
            st.markdown(f"#### {header}")
            for feat in features:
                row = st.columns([3, 2])
                row[0].markdown(_FEATURE_LABELS.get(feat, feat))
                default = int((current.get(role) or {}).get(feat, 0))
                row[1].number_input(
                    f"{role}-{feat}",
                    min_value=-1,
                    max_value=100000,
                    value=default,
                    step=1,
                    label_visibility="collapsed",
                    key=f"rl__{role}__{feat}",
                )

        section_cols = st.columns(2, gap="large")
        with section_cols[0]:
            _render_role_section("student", "🎓 Student Module")
        with section_cols[1]:
            _render_role_section("teacher", "👩‍🏫 Teacher Module")

        st.markdown("---")
        col_save, col_reset, _ = st.columns([1, 1, 4])
        with col_save:
            if st.button("💾 Save Changes", type="primary", width="stretch", key="rl_save"):
                new_limits = {
                    role: {feat: int(st.session_state.get(f"rl__{role}__{feat}", 0)) for feat in features}
                    for role in EDITABLE_ROLES
                }
                try:
                    api.admin_update_rate_limits(new_limits)
                    _bust_cache("rate_limits")
                    st.success("Rate limits saved. Changes apply to the next API call.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save: {e}")
        with col_reset:
            if st.button("↺ Reset to Defaults", width="stretch", key="rl_reset"):
                defaults = rl_resp.get("defaults") or {}
                # Filter defaults to the editable roles too — keeps the request
                # symmetric with what the Save button sends.
                clean_defaults = {r: defaults.get(r, {}) for r in EDITABLE_ROLES}
                try:
                    api.admin_update_rate_limits(clean_defaults)
                    _bust_cache("rate_limits")
                    st.success("Rate limits restored to defaults.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to reset: {e}")

        st.caption(
            "Note: a separate per-minute anti-burst middleware (60 req/min general, "
            "20 req/min for AI) still applies as a safety net."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — ACTIVITY LOGS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_logs:
    st.markdown('<div class="card-accent">', unsafe_allow_html=True)
    col_ef, col_lf, col_rf = st.columns([3, 1, 1])
    with col_ef:
        filter_email = st.text_input(
            "Filter by email", placeholder="🔍  Filter by user email (blank = all users)…",
            label_visibility="collapsed",
            key="log_filter_email",
        )
    with col_lf:
        log_limit = st.number_input(
            "Max records", min_value=10, max_value=500, value=100, step=10,
            key="log_limit",
        )
    with col_rf:
        if st.button("🔄 Refresh", width="stretch", key="ref_logs"):
            # Bust every logs cache key (different filters cache separately)
            cache = st.session_state.get("_admin_fetch_cache") or {}
            for k in [k for k in cache if k.startswith("logs|")]:
                cache.pop(k, None)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # Cache key includes filter params so changing the filter or limit
    # triggers a fresh fetch automatically (without forcing a manual refresh).
    logs_key = f"logs|{filter_email.strip()}|{int(log_limit)}"
    try:
        activities = _cached_fetch(
            logs_key,
            lambda: api.get_activity_logs(
                user_email=filter_email.strip() or None,
                limit=int(log_limit),
            ).get("activities", []),
            spinner_label="Fetching logs…",
        )
        if not activities:
            st.info("No activity logs found for the given filter.")
        else:
            rows = [{
                "Timestamp": str(a.get("timestamp",""))[:19].replace("T"," "),
                "User":      a.get("user_email",""),
                "Action":    a.get("activity_type",""),
                "Details":   str(a.get("details",""))[:80],
            } for a in activities]
            df = pd.DataFrame(rows)
            st.dataframe(df, width="stretch", hide_index=True)
            st.caption(f"{len(activities)} records loaded")
    except RuntimeError as e:
        st.error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — ALL PDFs
# ═══════════════════════════════════════════════════════════════════════════════
with tab_pdfs:
    col_rp, _ = st.columns([1, 5])
    with col_rp:
        if st.button("🔄 Refresh", width="stretch", key="ref_pdfs"):
            _bust_cache("pdfs")
            st.rerun()

    try:
        all_pdfs = _cached_fetch(
            "pdfs",
            lambda: api.get_all_uploaded_pdfs(limit=200).get("pdfs", []),
            spinner_label="Loading PDFs…",
        )
        if not all_pdfs:
            st.info("No PDFs have been uploaded yet.")
        else:
            rows = [{
                "Filename":    pdf.get("filename",""),
                "Uploader":    pdf.get("uploader_email",""),
                "Size (KB)":   round(pdf.get("file_size", 0) / 1024, 1),
                "Upload Date": str(pdf.get("upload_date",""))[:19].replace("T"," "),
                "PDF ID":      pdf.get("pdf_identifier",""),
            } for pdf in all_pdfs]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            total_size = sum(p.get("file_size", 0) for p in all_pdfs) / (1024 * 1024)
            st.markdown(f"""
            <div style="display:flex; gap:20px; margin-top:10px;">
                <span style="color:var(--accent-soft);"><strong>{len(all_pdfs)}</strong> total PDFs</span>
                <span style="color:#888;">Total size: <strong>{total_size:.1f} MB</strong></span>
            </div>
            """, unsafe_allow_html=True)
    except RuntimeError as e:
        st.error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — AI EVALUATION
# Reference-based scoring of AI answers against the curated golden set.
# Uses Claude Haiku as the judge model on production deployments.
# ═══════════════════════════════════════════════════════════════════════════════
with tab_eval:
    st.markdown("#### 🧪 AI Answer Evaluation")
    st.markdown(
        '<p style="color:var(--text-muted); font-size:0.88rem; margin-bottom:16px;">'
        'Score REAL student Q&A traffic. Pulls the most recent (question, AI answer) turns from '
        'the chat sessions and rates each one on <b>faithfulness</b> (does the answer stay grounded '
        'in the PDF chunks the AI retrieved?) and <b>answer relevance</b> (does it actually address '
        'the question?). No expected-answer needed — this measures real-world quality on what '
        'students are actually asking.</p>',
        unsafe_allow_html=True,
    )

    # ── Trigger panel ────────────────────────────────────────────────────────
    with st.container(border=True):
        col_run1, col_run2 = st.columns([3, 2])
        with col_run1:
            eval_label = st.text_input(
                "Label (optional)",
                key="eval_run_label",
                placeholder="e.g. After RAG tightening",
            )
        with col_run2:
            eval_limit_input = st.number_input(
                "Items to evaluate",
                min_value=1, max_value=200, value=20, step=1,
                key="eval_run_limit",
                help="How many records to score from each source.",
            )

        st.markdown(
            '<p style="color:var(--text-muted); font-size:0.85rem; '
            'margin:4px 0 6px 0;">▶ <b>Pick which side to evaluate.</b> '
            '<b>Student</b> runs three sub-evaluations in one go (Q&A, '
            'Summaries, Quizzes). <b>Teacher</b> evaluates the questions '
            'inside recent assignments.</p>',
            unsafe_allow_html=True,
        )
        b_student, b_teacher = st.columns(2)
        with b_student:
            run_student_clicked = st.button(
                "▶ 🎓 Student Evaluation",
                type="primary", width="stretch", key="run_eval_student_btn",
                help="Runs Q&A + Summaries + Quizzes evals sequentially — three runs in one click",
            )
        with b_teacher:
            run_teacher_clicked = st.button(
                "▶ 👩‍🏫 Teacher Evaluation",
                type="primary", width="stretch", key="run_eval_teacher_btn",
                help="Scores the questions inside recent teacher assignments",
            )

        run_eval_clicked = bool(run_student_clicked or run_teacher_clicked)
        eval_mode = (
            "student_bundle" if run_student_clicked else
            "teacher_question" if run_teacher_clicked else
            None
        )

        if run_eval_clicked:
            # Run the eval in a worker thread so the main thread can keep
            # rendering a progress bar. On Ollama with a small model each
            # item takes 20-60 seconds, so a static spinner feels frozen.
            # The bar asymptotes toward 90% over the expected duration and
            # snaps to 100% when the backend finally responds.
            _eval_result = {"done": False, "data": None, "error": None}

            def _run_eval_api():
                try:
                    _label = eval_label.strip() or None
                    _lim = int(eval_limit_input)
                    if eval_mode == "student_bundle":
                        _eval_result["data"] = api.admin_eval_run_student_bundle(label=_label, limit=_lim)
                    elif eval_mode == "teacher_question":
                        _eval_result["data"] = api.admin_eval_run_on_teacher_questions(label=_label, limit=_lim)
                    else:
                        _eval_result["error"] = RuntimeError("No evaluation mode selected")
                except Exception as exc:
                    _eval_result["error"] = exc
                finally:
                    _eval_result["done"] = True

            _ctx = get_script_run_ctx()
            _worker = threading.Thread(target=_run_eval_api, daemon=True)
            add_script_run_ctx(_worker, _ctx)
            _worker.start()

            eval_progress_placeholder = st.empty()
            # Crude time estimate so the bar advances at roughly the right
            # rate: assume ~30s per item on Ollama. The bar caps at 90% until
            # the actual response arrives, then snaps to 100%.
            _estimated_seconds = max(60, int(eval_limit_input) * 30)
            _step_seconds = 0.5
            _max_steps = int(_estimated_seconds / _step_seconds)

            # Per-mode progress label so the bar reflects what's actually
            # running (not the old golden-set wording).
            _mode_labels = {
                "student_bundle": "🧪 Scoring student content (Q&A → Summaries → Quizzes)…",
                "teacher_question": "🧪 Scoring teacher assignment questions…",
            }
            _pb_text = _mode_labels.get(eval_mode, "🧪 Scoring…")

            pb = eval_progress_placeholder.progress(0.0, text=_pb_text)
            _step = 0
            while not _eval_result["done"]:
                _time.sleep(_step_seconds)
                _step += 1
                target = 0.90 * (1 - (1 - min(_step / _max_steps, 1.0)) ** 2)
                pb.progress(target, text=_pb_text)

            _worker.join(timeout=3)
            pb.progress(1.0, text=_pb_text)
            _time.sleep(0.3)
            eval_progress_placeholder.empty()

            err = _eval_result["error"]
            if err is not None:
                st.error(f"Evaluation failed: {err}")
            else:
                summary = _eval_result["data"] or {}
                # Student-bundle returns a different shape (3 sub-runs);
                # render a per-sub-run breakdown so the admin sees what
                # was scored vs what was skipped (no data yet).
                if eval_mode == "student_bundle":
                    sub_runs = summary.get("bundle") or []
                    skipped = summary.get("skipped") or []
                    st.success(
                        f"✅ Student bundle complete — "
                        f"{summary.get('n_sub_runs', 0)} sub-evaluation(s) finished. "
                        f"Average overall across all parts: "
                        f"**{summary.get('avg_overall', 0):.2%}**"
                    )
                    for sr in sub_runs:
                        st.caption(
                            f"  • {sr.get('part','—')}: "
                            f"{sr.get('n_items', 0)} items · "
                            f"{sr.get('avg_overall', 0):.2%} overall"
                        )
                    for sk in skipped:
                        st.caption(
                            f"  • {sk.get('part','—')}: skipped — {sk.get('reason','')}"
                        )
                else:
                    st.success(
                        f"✅ Run complete — {summary.get('n_items', 0)} items scored. "
                        f"Average overall score: **{summary.get('avg_overall', 0):.2%}**"
                    )

    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)

    # ── Recent runs list ─────────────────────────────────────────────────────
    st.markdown("##### Recent runs")
    try:
        runs_resp = api.admin_eval_list_runs(limit=20)
        runs = runs_resp.get("runs", [])
    except Exception as e:
        runs = []
        st.error(f"Could not load runs: {e}")

    if not runs:
        st.info("No evaluation runs yet. Have students ask questions in the Workspace, then click **▶ Evaluate recent Q&A** to score what they got back.")
    else:
        # Summary metrics across the latest run. The metric set shown depends
        # on the eval_type (QA, summary, quiz, teacher_question).
        latest = runs[0]
        latest_type = latest.get("eval_type") or "reference_free"
        if latest_type == "reference_free":
            m1, m2, m3 = st.columns(3)
            with m1: st.metric("Overall (latest)", f"{latest.get('avg_overall', 0):.2%}")
            with m2: st.metric("Faithfulness", f"{latest.get('avg_faithfulness', 0):.2%}")
            with m3: st.metric("Answer relevance", f"{latest.get('avg_answer_relevance', 0):.2%}")
        elif latest_type in ("quiz", "teacher_question"):
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.metric("Overall (latest)", f"{latest.get('avg_overall', 0):.2%}")
            with m2: st.metric("Validity", f"{latest.get('avg_validity', 0):.2%}")
            with m3: st.metric("Correctness", f"{latest.get('avg_correctness', 0):.2%}")
            with m4: st.metric("Faithfulness", f"{latest.get('avg_faithfulness', 0):.2%}")
        else:  # "summary" or "reference"
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.metric("Overall (latest)", f"{latest.get('avg_overall', 0):.2%}")
            with m2: st.metric("Semantic match", f"{latest.get('avg_semantic_match', 0):.2%}")
            with m3: st.metric("Completeness", f"{latest.get('avg_completeness', 0):.2%}")
            with m4: st.metric("Faithfulness", f"{latest.get('avg_faithfulness', 0):.2%}")

        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

        # Runs table — columns adapt to the eval_type of each row.
        _TYPE_BADGE = {
            "reference_free": "🗨️ Real Q&A",
            "summary":        "📋 Summary",
            "quiz":           "📝 Student Quiz",
            "teacher_question": "👩‍🏫 Teacher Q",
        }
        import pandas as _pd
        # Build every row with the SAME set of columns so pandas doesn't
        # render missing keys as the string "None". Non-applicable metrics
        # for a given row's type show "—" instead.
        run_rows = []
        for r in runs:
            etype = r.get("eval_type") or "reference_free"
            row = {
                "When": (r.get("created_at") or "")[:19].replace("T", " "),
                "Label": r.get("label") or "—",
                "Type": _TYPE_BADGE.get(etype, etype),
                "Items": r.get("n_items", 0),
                "Errors": r.get("n_errors", 0),
                "Overall": f"{r.get('avg_overall', 0):.2%}",
                "Faithful": f"{r.get('avg_faithfulness', 0):.2%}",
                "Answer rel.": "—",
                "Validity": "—",
                "Correct": "—",
                "Semantic": "—",
                "Complete": "—",
            }
            if etype == "reference_free":
                row["Answer rel."] = f"{r.get('avg_answer_relevance', 0):.2%}"
            elif etype in ("quiz", "teacher_question"):
                row["Validity"] = f"{r.get('avg_validity', 0):.2%}"
                row["Correct"] = f"{r.get('avg_correctness', 0):.2%}"
            else:  # summary
                row["Semantic"] = f"{r.get('avg_semantic_match', 0):.2%}"
                row["Complete"] = f"{r.get('avg_completeness', 0):.2%}"
            row["Gen model"] = r.get("generation_model") or "—"
            row["Judge model"] = r.get("judge_model") or "—"
            run_rows.append(row)
        st.dataframe(_pd.DataFrame(run_rows), width="stretch", hide_index=True)

        # ── Drill-down: pick a run + view its items ──────────────────────────
        st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
        st.markdown("##### Drill into a run")
        run_options = {f"{r.get('label','—')} — {(r.get('created_at') or '')[:19].replace('T',' ')}": r["id"] for r in runs}
        picked_label = st.selectbox(
            "Pick a run to inspect",
            options=list(run_options.keys()),
            key="eval_drill_pick",
        )
        if picked_label:
            picked_id = run_options[picked_label]
            try:
                detail = api.admin_eval_get_run(picked_id)
                items = detail.get("items", [])
            except Exception as e:
                items = []
                st.error(f"Could not load run details: {e}")

            if not items:
                st.info("No items to display for this run.")
            else:
                run_is_ref_free = any(
                    (it.get("scores") or {}).get("answer_relevance", 0) > 0
                    for it in items
                )
                item_rows = []
                for it in items:
                    sc = it.get("scores") or {}
                    row = {
                        "Question": (it.get("question") or "")[:80],
                        "AI answer": (it.get("ai_answer") or "")[:80],
                        "Overall": f"{sc.get('overall', 0):.2f}",
                        "Faith": f"{sc.get('faithfulness', 0):.2f}",
                    }
                    if run_is_ref_free:
                        row["Ans. rel."] = f"{sc.get('answer_relevance', 0):.2f}"
                        row["Student"] = it.get("user_email") or "—"
                    else:
                        row["Expected"] = (it.get("expected_answer") or "")[:80]
                        row["Sem"] = f"{sc.get('semantic_match', 0):.2f}"
                        row["Comp"] = f"{sc.get('completeness', 0):.2f}"
                        row["Class"] = it.get("class_level") or "—"
                        row["Subject"] = it.get("subject") or "—"
                    item_rows.append(row)
                st.dataframe(_pd.DataFrame(item_rows), width="stretch", hide_index=True)

                # Lowest-scoring items get a callout so admins can review the
                # rationale and decide if it's a prompt issue or a data issue.
                low = sorted(
                    items,
                    key=lambda x: (x.get("scores") or {}).get("overall", 0.0),
                )[:3]
                if low:
                    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
                    st.markdown("##### Worst three answers in this run")
                    for it in low:
                        sc = it.get("scores") or {}
                        with st.expander(
                            f"💢 {sc.get('overall', 0):.2f} — {(it.get('question') or '')[:80]}",
                            expanded=False,
                        ):
                            if run_is_ref_free:
                                if it.get("user_email"):
                                    st.caption(f"Asked by: {it['user_email']}")
                                st.markdown(f"**AI said:** {it.get('ai_answer','')}")
                                st.caption(
                                    f"Faithfulness {sc.get('faithfulness', 0):.2f} · "
                                    f"Answer relevance {sc.get('answer_relevance', 0):.2f}"
                                )
                            else:
                                st.markdown(f"**Expected:** {it.get('expected_answer','')}")
                                st.markdown(f"**AI said:** {it.get('ai_answer','')}")
                                st.caption(
                                    f"Semantic {sc.get('semantic_match', 0):.2f} · "
                                    f"Complete {sc.get('completeness', 0):.2f} · "
                                    f"Faithful {sc.get('faithfulness', 0):.2f}"
                                )
                            if sc.get("rationale"):
                                st.markdown(f"**Judge rationale:** _{sc['rationale']}_")
                            if sc.get("error"):
                                st.warning(f"Eval error: {sc['error']}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 7 — EXPORT LOGS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_export:
    st.markdown('<div class="card-accent">', unsafe_allow_html=True)
    st.markdown("#### 📥 Export Audit Logs as CSV")
    st.markdown('<p style="color:#888; font-size:0.88rem; margin-bottom:16px;">Download a filtered CSV of all platform activity for compliance and analysis.</p>', unsafe_allow_html=True)

    with st.form("export_form"):
        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            export_email = st.text_input("User Email (optional)", placeholder="Leave blank for all users")
        with ec2:
            start_d = st.date_input("From Date", value=datetime.now(timezone.utc).date() - timedelta(days=30))
        with ec3:
            end_d = st.date_input("To Date", value=datetime.now(timezone.utc).date())
        export_submitted = st.form_submit_button("📥 Generate CSV Export", width="stretch", type="primary")
    st.markdown('</div>', unsafe_allow_html=True)

    if export_submitted:
        with st.spinner("Preparing CSV…"):
            try:
                csv_bytes = api.export_logs_csv(
                    user_email=export_email.strip() or None,
                    start_date=str(start_d),
                    end_date=str(end_d),
                )
                fname = f"audit_logs_{start_d}_{end_d}.csv"
                st.markdown(f"""
                <div style="background:#0A1A0A; border:1px solid #00C85355; border-radius:10px;
                            padding:12px 18px; margin-bottom:14px;">
                    <span style="color:#00E870; font-weight:600;">✅ Export ready:</span>
                    <span style="color:var(--text-muted); font-size:0.88rem;"> {fname}</span>
                </div>
                """, unsafe_allow_html=True)
                st.download_button(
                    label="⬇️ Download audit_logs.csv",
                    data=csv_bytes,
                    file_name=fname,
                    mime="text/csv",
                    width="stretch",
                    type="primary",
                )
            except RuntimeError as e:
                st.error(str(e))
