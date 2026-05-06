"""
School LLM — Landing Page
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from utils.session_utils import init_session_state, is_logged_in, is_admin

st.set_page_config(
    page_title="School LLM",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Hide sidebar nav arrows and default Streamlit menu
st.markdown("""
<style>
[data-testid="collapsedControl"] { display: none; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

init_session_state()

# Auto-redirect if already logged in
if is_logged_in():
    if is_admin():
        st.switch_page("pages/3_Admin_Dashboard.py")
    else:
        st.switch_page("pages/2_Student_Dashboard.py")

# ── Hero ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding: 60px 0 40px 0;">
    <div style="font-size: 64px; margin-bottom: 8px;">📚</div>
    <h1 style="font-size: 2.8rem; font-weight: 700; margin: 0; color: #E8E8F0;">
        School LLM
    </h1>
    <p style="font-size: 1.1rem; color: #888; margin-top: 10px; margin-bottom: 40px;">
        AI-powered learning platform — RAG · Quiz · Summary · Audio
    </p>
</div>
""", unsafe_allow_html=True)

# ── Feature pills ─────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
for col, icon, label in [
    (col1, "💬", "Smart Q&A"),
    (col2, "📝", "Quiz Generator"),
    (col3, "📋", "Summaries"),
    (col4, "🔊", "Audio & Video"),
]:
    with col:
        st.markdown(f"""
        <div style="background:#1A1A2E; border:1px solid #2E2E4E; border-radius:10px;
                    padding:16px 8px; text-align:center;">
            <div style="font-size:28px;">{icon}</div>
            <div style="font-size:0.85rem; color:#aaa; margin-top:6px;">{label}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── CTA buttons ───────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([1, 2, 1])
with c2:
    if st.button("🔑  Login to your account", use_container_width=True, type="primary"):
        st.switch_page("pages/1_Login.py")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    if st.button("📝  Create a new account", use_container_width=True):
        st.switch_page("pages/1_Login.py")

st.markdown("""
<div style="text-align:center; margin-top:50px; color:#555; font-size:0.8rem;">
    Powered by Ollama · ChromaDB · FastAPI · MongoDB
</div>
""", unsafe_allow_html=True)
