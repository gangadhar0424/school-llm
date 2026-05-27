"""
Theme system — 5 formal palettes + CSS generator.

Usage:
    from utils.themes import apply_theme, render_theme_selector, get_theme_name

    apply_theme(st.session_state.get("theme", "midnight"))

Each theme defines:
  - Surface colors (bg, surface, surface-2, etc.)
  - Text colors (auto-contrast: light text on dark bg, dark text on light bg)
  - One single accent color (no rainbow mixing within a theme)
  - Semantic status colors (success/warning/danger) — kept consistent across themes
"""
from typing import Dict, List

import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# THEME PALETTES — each is a self-contained, formal color scheme.
# Conventions:
#   bg, surface, surface_2, surface_3 → backgrounds (darkest → lightest variations)
#   text, text_muted, text_strong     → typography colors
#   border, border_soft               → divider colors
#   accent, accent_2, accent_soft     → SINGLE accent family (no mixing!)
#   hero_grad_*                       → 3-stop gradient for hero banners
#   is_light                          → True for light themes (Ivory, Sand)
# ─────────────────────────────────────────────────────────────────────────────
THEMES: Dict[str, Dict] = {
    "midnight": {
        "label": "Midnight Pro",
        "emoji": "🌙",
        "description": "Deep slate with indigo accent — the classic professional dark theme",
        "preview": ["#0F172A", "#1E293B", "#6366F1", "#A5B4FC"],
        "is_light": False,
        "vars": {
            "bg":          "#0F172A",
            "surface":     "#1E293B",
            "surface_2":   "#172033",
            "surface_3":   "#243047",
            "text":        "#E2E8F0",
            "text_muted":  "#94A3B8",
            "text_strong": "#FFFFFF",
            "border":      "#334155",
            "border_soft": "#1E293B",
            "accent":      "#6366F1",
            "accent_2":    "#4F46E5",
            "accent_soft": "#A5B4FC",
            "accent_text": "#FFFFFF",
            "accent_glow": "#6366F144",
            "accent_chip_bg": "#6366F122",
            "hero_grad_1": "#1E1B4B",
            "hero_grad_2": "#0F172A",
            "hero_grad_3": "#1E293B",
            "card_grad_1": "#1E293B",
            "card_grad_2": "#172033",
            "sidebar_grad_1": "#0B1220",
            "sidebar_grad_2": "#0F172A",
            "sidebar_bg_1": "#0B1220",
            "sidebar_bg_2": "#0F172A",
            "sidebar_text": "#E2E8F0",
            "sidebar_text_muted": "#94A3B8",
            "sidebar_border": "#1E293B",
        },
    },
    "cobalt": {
        "label": "Cobalt",
        "emoji": "🔵",
        "description": "Clean white with black text and cobalt blue accent — professional",
        "preview": ["#F4F2EE", "#FFFFFF", "#0A66C2", "#000000"],
        "is_light": True,
        "vars": {
            "bg":          "#F4F2EE",
            "surface":     "#FFFFFF",
            "surface_2":   "#F4F2EE",
            "surface_3":   "#EBE7E1",
            "text":        "#000000",
            "text_muted":  "#666666",
            "text_strong": "#000000",
            "border":      "#E0DFDC",
            "border_soft": "#EBE7E1",
            "accent":      "#0A66C2",
            "accent_2":    "#004182",
            "accent_soft": "#0A66C2",
            "accent_text": "#FFFFFF",
            "accent_glow": "#0A66C233",
            "accent_chip_bg": "#0A66C214",
            "hero_grad_1": "#FFFFFF",
            "hero_grad_2": "#F4F2EE",
            "hero_grad_3": "#EBE7E1",
            "card_grad_1": "#FFFFFF",
            "card_grad_2": "#FAFAFA",
            "sidebar_grad_1": "#F4F2EE",
            "sidebar_grad_2": "#EBE7E1",
            "sidebar_bg_1": "#0B1220",
            "sidebar_bg_2": "#0F172A",
            "sidebar_text": "#E2E8F0",
            "sidebar_text_muted": "#94A3B8",
            "sidebar_border": "#1E293B",
        },
    },
    "onyx": {
        "label": "Onyx",
        "emoji": "⚫",
        "description": "Pure black with white text and white-highlight buttons — minimal & sharp",
        "preview": ["#000000", "#0A0A0A", "#FFFFFF", "#888888"],
        "is_light": False,
        "vars": {
            "bg":          "#000000",
            "surface":     "#0A0A0A",
            "surface_2":   "#050505",
            "surface_3":   "#171717",
            "text":        "#EDEDED",
            "text_muted":  "#888888",
            "text_strong": "#FFFFFF",
            "border":      "#2A2A2A",
            "border_soft": "#1A1A1A",
            "accent":      "#FFFFFF",
            "accent_2":    "#EAEAEA",
            "accent_soft": "#A1A1A1",
            "accent_text": "#000000",
            "accent_glow": "#FFFFFF22",
            "accent_chip_bg": "#FFFFFF10",
            "hero_grad_1": "#0A0A0A",
            "hero_grad_2": "#000000",
            "hero_grad_3": "#0A0A0A",
            "card_grad_1": "#0A0A0A",
            "card_grad_2": "#050505",
            "sidebar_grad_1": "#000000",
            "sidebar_grad_2": "#050505",
            "sidebar_bg_1": "#1F1F1F",
            "sidebar_bg_2": "#0F0F0F",
            "sidebar_text": "#E5E5E5",
            "sidebar_text_muted": "#A1A1A1",
            "sidebar_border": "#2A2A2A",
        },
    },
    "sand": {
        "label": "Sand",
        "emoji": "🌅",
        "description": "Warm cream paper-like background with amber accent",
        "preview": ["#FFF8F0", "#FFFFFF", "#B45309", "#FCD34D"],
        "is_light": True,
        "vars": {
            "bg":          "#FFF8F0",
            "surface":     "#FFFFFF",
            "surface_2":   "#FFF4E6",
            "surface_3":   "#FEF3C7",
            "text":        "#1C1917",
            "text_muted":  "#78716C",
            "text_strong": "#0C0A09",
            "border":      "#FCE7CC",
            "border_soft": "#FEF3C7",
            "accent":      "#C96112",
            "accent_2":    "#C26C0B",
            "accent_soft": "#92400E",
            "accent_text": "#FFFFFF",
            "accent_glow": "#B4530944",
            "accent_chip_bg": "#FEF3C7",
            "hero_grad_1": "#FEF3C7",
            "hero_grad_2": "#FFF8F0",
            "hero_grad_3": "#FFFFFF",
            "card_grad_1": "#FFFFFF",
            "card_grad_2": "#FFF8F0",
            "sidebar_grad_1": "#FFFBF5",
            "sidebar_grad_2": "#FFF4E6",
            "sidebar_bg_1": "#FFF4E6",
            "sidebar_bg_2": "#FEF3C7",
            "sidebar_text": "#1C1917",
            "sidebar_text_muted": "#78716C",
            "sidebar_border": "#FCE7CC",
        },
    },
}


DEFAULT_THEME = "cobalt"


def get_theme_name() -> str:
    """Return the currently active theme name from session state."""
    name = st.session_state.get("theme") or DEFAULT_THEME
    return name if name in THEMES else DEFAULT_THEME


def list_themes() -> List[Dict]:
    """Return ordered list of theme metadata for UI rendering."""
    return [
        {
            "name": k,
            "label": v["label"],
            "emoji": v["emoji"],
            "description": v["description"],
            "preview": v["preview"],
            "is_light": v["is_light"],
        }
        for k, v in THEMES.items()
    ]


def get_theme_css(theme_name: str = None) -> str:
    """Generate the full CSS string for a theme — CSS variables at :root
    plus component overrides that adapt to those variables. Inject this at
    the top of every page via `st.markdown(css, unsafe_allow_html=True)`."""
    theme_name = theme_name if theme_name in THEMES else DEFAULT_THEME
    t = THEMES[theme_name]
    v = t["vars"]
    is_light = t["is_light"]

    # Status colors (semantic — same hues across themes, but light variants
    # use darker shades to maintain contrast on light backgrounds).
    if is_light:
        status = {
            "success":        "#047857",
            "success_bg":     "#D1FAE5",
            "success_border": "#A7F3D0",
            "warning":        "#B45309",
            "warning_bg":     "#FEF3C7",
            "warning_border": "#FCD34D",
            "danger":         "#B91C1C",
            "danger_bg":      "#FEE2E2",
            "danger_border":  "#FCA5A5",
            "info":           "#0369A1",
            "info_bg":        "#DBEAFE",
            "info_border":    "#93C5FD",
        }
    else:
        status = {
            "success":        "#00E870",
            "success_bg":     "#00C85322",
            "success_border": "#00C85355",
            "warning":        "#FFB347",
            "warning_bg":     "#FF7A0022",
            "warning_border": "#FF7A0055",
            "danger":         "#FF8080",
            "danger_bg":      "#FF444422",
            "danger_border":  "#FF444455",
            "info":           "#40C4FF",
            "info_bg":        "#40C4FF22",
            "info_border":    "#40C4FF55",
        }

    css_vars = "\n".join([f"    --{k.replace('_', '-')}: {val};" for k, val in v.items()])
    css_vars += "\n" + "\n".join([f"    --{k.replace('_', '-')}: {val};" for k, val in status.items()])

    # Sidebar palette — each theme defines its own via sidebar_bg_*,
    # sidebar_text, sidebar_text_muted, sidebar_border. This gives every
    # theme a coherent sidebar identity (Midnight=indigo, Cobalt=slate,
    # Onyx=blackish-gray, Sand=amber-orange).
    sb_grad_1 = v.get("sidebar_bg_1", "#0B1220")
    sb_grad_2 = v.get("sidebar_bg_2", "#0F172A")
    sb_text = v.get("sidebar_text", "#E2E8F0")
    sb_text_muted = v.get("sidebar_text_muted", "#94A3B8")
    sb_text_strong = v.get("sidebar_text_strong", "#FFFFFF")
    sb_border = v.get("sidebar_border", sb_grad_2)
    sb_border_strong = sb_border
    sb_surface, sb_surface_2, sb_surface_3 = sb_grad_1, sb_grad_2, sb_border
    sb_accent_soft, sb_accent_glow = sb_text, "#00000033"
    sb_hero_1, sb_hero_2 = sb_grad_2, sb_grad_1
    sb_button_bg, sb_button_border = sb_grad_2, sb_border

    # Build the full CSS. Uses the variables defined above for everything.
    return f"""
<style>
:root {{
{css_vars}
    --shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08);
}}

/* ── Streamlit base overrides ──────────────────────────────────────────── */
#MainMenu {{ visibility: hidden; }}
footer    {{ visibility: hidden; }}
header    {{ visibility: hidden; }}
/* Streamlit's thin gradient strip at the very top of every page —
   visible as a faint horizontal line even when the header above it is
   hidden. We can't display:none the whole header because the sidebar
   collapse button lives inside it; just kill the decoration. */
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {{
    display: none !important;
    height: 0 !important;
}}
/* Collapse the header's reserved height (visibility:hidden keeps it).
   The collapse button itself is positioned with z-index 999999 elsewhere
   so it stays visible even when the header has zero height. */
header[data-testid="stHeader"] {{
    height: 0 !important;
    background: transparent !important;
    border-bottom: none !important;
    box-shadow: none !important;
}}

/* Keep the sidebar collapse button visible */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
button[kind="headerNoPadding"] {{
    visibility: visible !important;
    display: flex !important;
    z-index: 999999 !important;
}}

.stApp {{ background: var(--bg); color: var(--text); }}
.block-container {{ padding-top: 1.5rem !important; padding-bottom: 1rem !important; }}

/* All headings, paragraphs, captions */
h1, h2, h3, h4, h5, h6 {{ color: var(--text-strong) !important; }}
p, span, div, label, li {{ color: var(--text); }}
small, .small, .caption, [data-testid="stCaptionContainer"] {{ color: var(--text-muted) !important; }}

/* ── Sidebar (INVERTED contrast vs body) ────────────────────────────────── */
/* Sidebar uses opposite contrast from the body theme so navigation feels
   like a separate surface. Light body → dark sidebar. Dark body → light
   sidebar. CSS variables are re-scoped inside the sidebar so every inline
   var(--text), var(--accent-soft), etc. reads the sidebar-local values. */
[data-testid="stSidebar"] {{
    --bg:          {sb_grad_1};
    --surface:     {sb_surface};
    --surface-2:   {sb_surface_2};
    --surface-3:   {sb_surface_3};
    --text:        {sb_text};
    --text-muted:  {sb_text_muted};
    --text-strong: {sb_text_strong};
    --border:      {sb_border};
    --border-soft: {sb_border};
    --accent-soft: {sb_accent_soft};
    --accent-glow: {sb_accent_glow};
    --accent-chip-bg: {sb_accent_glow};
    --hero-grad-1: {sb_hero_1};
    --hero-grad-2: {sb_hero_2};
    --hero-grad-3: {sb_grad_1};
    /* Cards rendered inside the sidebar (user profile, etc) must use the
       sidebar palette — without this they pick up the global --card-grad-*
       (which on light body themes is white), producing white cards with
       light text from the sidebar's --text override. */
    --card-grad-1: {sb_surface_3};
    --card-grad-2: {sb_surface_3};

    background: linear-gradient(180deg, {sb_grad_1} 0%, {sb_grad_2} 100%) !important;
    border-right: 1px solid {sb_border} !important;
}}
[data-testid="stSidebar"] *,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] li {{ color: {sb_text} !important; }}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] h4 {{ color: {sb_text_strong} !important; }}
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: {sb_text_muted} !important; }}

/* Badges inside the sidebar keep their SEMANTIC colors — without these
   overrides the universal sidebar text rule wins and the badge text
   fades into the badge background. */
[data-testid="stSidebar"] .badge-purple {{
    background: var(--accent-chip-bg) !important;
    color: var(--accent-soft) !important;
    border: 1px solid var(--accent-glow) !important;
}}
[data-testid="stSidebar"] .badge-green {{
    background: var(--success-bg) !important;
    color: var(--success) !important;
    border: 1px solid var(--success-border) !important;
}}
[data-testid="stSidebar"] .badge-orange {{
    background: var(--warning-bg) !important;
    color: var(--warning) !important;
    border: 1px solid var(--warning-border) !important;
}}
[data-testid="stSidebar"] .badge-blue {{
    background: var(--info-bg) !important;
    color: var(--info) !important;
    border: 1px solid var(--info-border) !important;
}}
[data-testid="stSidebar"] .badge-red {{
    background: var(--danger-bg) !important;
    color: var(--danger) !important;
    border: 1px solid var(--danger-border) !important;
}}
[data-testid="stSidebar"] .badge-grey {{
    background: {sb_surface_3} !important;
    color: {sb_text_muted} !important;
    border: 1px solid {sb_border} !important;
}}

/* Sidebar buttons — themed to sidebar surface, never bleed through */
[data-testid="stSidebar"] .stButton > button {{
    background-color: {sb_button_bg} !important;
    color: {sb_text} !important;
    border: 1px solid {sb_button_border} !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, {sb_accent_soft}, {sb_border_strong}) !important;
    color: {sb_text_strong} !important;
    border: none !important;
}}

/* Arrow INSIDE the sidebar (when sidebar is open) — uses sidebar fg
   so it's light on dark sidebar AND dark on light sidebar. */
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
[data-testid="stSidebar"] button[kind="headerNoPadding"] {{
    color: {sb_text} !important;
}}
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebar"] button[kind="headerNoPadding"] svg,
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] svg *,
[data-testid="stSidebar"] button[kind="headerNoPadding"] svg * {{
    fill: {sb_text} !important;
    stroke: {sb_text} !important;
    color: {sb_text} !important;
}}

/* Arrow OUTSIDE the sidebar (when sidebar is COLLAPSED) — sits on body bg.
   Pure white on dark themes / pure black on light themes. Streamlit 1.57
   renders this with several different testids across versions, so we cover
   all known variants plus add a subtle bg so the button is clearly
   discoverable even on near-white pages. */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarToggle"],
[data-testid="stSidebarCollapsedNavLogo"],
button[kind="header"],
button[kind="headerNoPadding"],
[aria-label="Open sidebar"],
[aria-label="open sidebar"] {{
    visibility: visible !important;
    display: flex !important;
    opacity: 1 !important;
    z-index: 999999 !important;
    color: {"#000000" if is_light else "#FFFFFF"} !important;
    background-color: {"rgba(0,0,0,0.06)" if is_light else "rgba(255,255,255,0.08)"} !important;
    border: 1px solid {"rgba(0,0,0,0.12)" if is_light else "rgba(255,255,255,0.18)"} !important;
    border-radius: 8px !important;
    padding: 4px !important;
}}
[data-testid="collapsedControl"] svg,
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="stSidebarToggle"] svg,
button[kind="header"] svg,
button[kind="headerNoPadding"] svg,
[aria-label="Open sidebar"] svg,
[data-testid="collapsedControl"] svg *,
[data-testid="stSidebarCollapsedControl"] svg *,
[data-testid="stSidebarToggle"] svg *,
button[kind="header"] svg *,
button[kind="headerNoPadding"] svg * {{
    fill: {"#000000" if is_light else "#FFFFFF"} !important;
    stroke: {"#000000" if is_light else "#FFFFFF"} !important;
    color: {"#000000" if is_light else "#FFFFFF"} !important;
    visibility: visible !important;
    opacity: 1 !important;
}}

/* ── Cards ─────────────────────────────────────────────────────────────── */
.card {{
    background: linear-gradient(135deg, var(--card-grad-1) 0%, var(--card-grad-2) 100%);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 14px;
    color: var(--text);
}}
.card-accent {{
    background: linear-gradient(135deg, var(--hero-grad-1) 0%, var(--card-grad-2) 100%);
    border: 1px solid var(--accent-glow);
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 14px;
    color: var(--text);
}}

/* ── Hero banner ───────────────────────────────────────────────────────── */
.hero, .admin-hero {{
    background: linear-gradient(135deg, var(--hero-grad-1) 0%, var(--hero-grad-2) 60%, var(--hero-grad-3) 100%);
    border: 1px solid var(--accent-glow);
    border-radius: 18px;
    padding: 26px 32px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
}}
.hero::before, .admin-hero::before {{
    content: "";
    position: absolute;
    top: -50px; right: -50px;
    width: 240px; height: 240px;
    background: radial-gradient(circle, var(--accent-chip-bg), transparent 70%);
    border-radius: 50%;
}}

/* ── Badges ────────────────────────────────────────────────────────────── */
.badge {{
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
.badge-purple {{ background: var(--accent-chip-bg); color: var(--accent-soft); border: 1px solid var(--accent-glow); }}
.badge-green  {{ background: var(--success-bg);     color: var(--success);     border: 1px solid var(--success-border); }}
.badge-orange {{ background: var(--warning-bg);     color: var(--warning);     border: 1px solid var(--warning-border); }}
.badge-red    {{ background: var(--danger-bg);      color: var(--danger);      border: 1px solid var(--danger-border); }}
.badge-blue   {{ background: var(--info-bg);        color: var(--info);        border: 1px solid var(--info-border); }}

/* ── Pill rows ─────────────────────────────────────────────────────────── */
.pill-row {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }}
.pill {{
    background: var(--surface-3);
    border: 1px solid var(--border);
    border-radius: 24px;
    padding: 6px 16px;
    font-size: 0.82rem;
    color: var(--text);
}}

/* ── Active PDF bar ────────────────────────────────────────────────────── */
.pdf-bar {{
    background: linear-gradient(90deg, var(--hero-grad-1), var(--surface-2));
    border-left: 4px solid var(--accent);
    border-radius: 0 10px 10px 0;
    padding: 10px 16px;
    margin-bottom: 16px;
    font-size: 0.9rem;
    color: var(--text);
}}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background: var(--surface-2);
    border-radius: 12px;
    padding: 4px;
    gap: 2px;
    border: 1px solid var(--border-soft);
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 0.88rem;
    color: var(--text-muted);
    background: transparent;
    border: none;
}}
[data-testid="stTabs"] [aria-selected="true"] {{
    background: linear-gradient(135deg, var(--accent), var(--accent-2)) !important;
    color: var(--accent-text) !important;
}}
[data-testid="stTabs"] [aria-selected="true"] *,
[data-testid="stTabs"] [aria-selected="true"] p,
[data-testid="stTabs"] [aria-selected="true"] span,
[data-testid="stTabs"] [aria-selected="true"] div {{
    color: var(--accent-text) !important;
    background: transparent !important;
}}

/* ── Buttons ───────────────────────────────────────────────────────────── */
/* Secondary (default) buttons */
.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button,
button[data-testid^="stBaseButton-secondary"],
button[data-testid="baseButton-secondary"] {{
    color: var(--text) !important;
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px;
    transition: opacity 0.2s, transform 0.05s;
}}
.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {{ opacity: 0.9; }}

/* Primary buttons — multiple selectors to cover Streamlit DOM variants */
.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"],
button[kind="primary"],
button[data-testid^="stBaseButton-primary"],
button[data-testid="baseButton-primary"],
button[data-testid^="stBaseButton-primaryFormSubmit"] {{
    background: linear-gradient(135deg, var(--accent), var(--accent-2)) !important;
    background-color: var(--accent) !important;
    color: var(--accent-text) !important;
    border: none !important;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
button[kind="primary"]:hover,
button[data-testid^="stBaseButton-primary"]:hover {{ opacity: 0.88; }}
button[kind="primary"] *,
button[kind="primary"] p,
button[kind="primary"] span,
button[kind="primary"] div,
button[kind="primary"] svg,
button[data-testid^="stBaseButton-primary"] *,
button[data-testid^="stBaseButton-primary"] p,
button[data-testid^="stBaseButton-primary"] span,
button[data-testid^="stBaseButton-primary"] div,
button[data-testid^="stBaseButton-primary"] svg {{
    color: var(--accent-text) !important;
    fill: var(--accent-text) !important;
}}

/* ── Text inputs ───────────────────────────────────────────────────────── */
/* Target both the BaseWeb wrapper (where the bg color actually lives) and
   the inner <input>. Without the wrapper rule, Streamlit's BaseWeb default
   (dark on light themes, light on dark themes) leaks through. */
.stTextInput [data-baseweb="input"],
.stTextInput [data-baseweb="base-input"],
.stTextArea [data-baseweb="textarea"],
.stTextArea [data-baseweb="base-textarea"],
.stNumberInput [data-baseweb="input"],
.stPasswordInput [data-baseweb="input"] {{
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}}
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {{
    background-color: var(--surface) !important;
    color: var(--text) !important;
    -webkit-text-fill-color: var(--text) !important;
    caret-color: var(--text) !important;
}}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {{ color: var(--text-muted) !important; opacity: 0.7; }}

/* "Press Enter to submit form" helper / character-count hints */
[data-testid="InputInstructions"],
[data-testid="stWidgetInstructions"],
.stTextInput + small,
[data-baseweb="form-control-message"] {{
    color: var(--text-muted) !important;
    background-color: transparent !important;
}}

/* ── Selectbox / multiselect closed state ──────────────────────────────── */
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div {{
    background-color: var(--surface) !important;
    color: var(--text) !important;
    border-color: var(--border) !important;
}}
.stSelectbox [data-baseweb="select"] *,
.stMultiSelect [data-baseweb="select"] * {{ color: var(--text) !important; }}

/* ── Dropdown / popover menus (the panel that opens on click) ──────────── */
/* These render at the document root, NOT inside .stApp, so we use global
   attribute selectors. Without these the menu shows BaseWeb's default
   black background with near-invisible text on light themes. */
[data-baseweb="popover"],
[data-baseweb="menu"],
ul[role="listbox"],
[data-baseweb="popover"] [role="listbox"] {{
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
}}
[data-baseweb="popover"] *,
[data-baseweb="menu"] *,
ul[role="listbox"] *,
li[role="option"] {{ color: var(--text) !important; background-color: transparent !important; }}
li[role="option"]:hover,
li[role="option"][aria-selected="true"] {{
    background-color: var(--surface-3) !important;
    color: var(--text-strong) !important;
}}

/* File uploader drop zone */
[data-testid="stFileUploaderDropzone"], [data-testid="stFileUploader"] section {{
    background-color: var(--surface) !important;
    color: var(--text) !important;
    border-color: var(--border) !important;
}}
[data-testid="stFileUploader"] * {{ color: var(--text) !important; }}

/* Uploaded file chip — NUCLEAR OVERRIDE.
   Streamlit 1.57 renders the chip via BaseWeb's FileUploaderTile, which
   carries its own dark background via emotion / styled-components.
   Selectively targeting testids is unreliable across Streamlit versions,
   so we instead cover EVERY descendant of stFileUploader except the
   drop-zone <section> and any <button>. The drop zone keeps its own
   styling further down. */
[data-testid="stFileUploader"] *:not(section):not(button):not(svg):not(path) {{
    background-color: var(--surface-2) !important;
    background-image: none !important;
    color: var(--text) !important;
}}
/* The chip itself (any direct child of the uploader that isn't the
   dropzone) gets the surface color + a border to look like a real chip. */
[data-testid="stFileUploader"] > div > div:not([data-testid="stFileUploaderDropzone"]):not(section),
[data-testid="stFileUploader"] > div > section ~ div,
[data-testid="stFileUploader"] [data-baseweb] {{
    background-color: var(--surface-2) !important;
    background-image: none !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}}
/* Drop zone keeps its own surface (lighter than the chip background) */
[data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploaderDropzone"] * {{
    background-color: var(--surface) !important;
    color: var(--text) !important;
    border-color: var(--border) !important;
}}
/* File-size <small> reads muted */
[data-testid="stFileUploader"] small {{ color: var(--text-muted) !important; }}
/* Chip close (×) button */
[data-testid="stFileUploader"] button {{
    background-color: transparent !important;
    color: var(--text-muted) !important;
    border: none !important;
}}
[data-testid="stFileUploader"] button svg,
[data-testid="stFileUploader"] button path {{
    fill: var(--text-muted) !important;
    stroke: var(--text-muted) !important;
    color: var(--text-muted) !important;
}}

/* ── Expander (st.expander — used for assignment dropdowns etc) ────────── */
[data-testid="stExpander"],
.streamlit-expander,
[data-testid="stExpander"] > details {{
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    overflow: hidden;
}}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] details > summary,
.streamlit-expanderHeader {{
    background-color: var(--surface-2) !important;
    color: var(--text) !important;
    padding: 10px 14px !important;
    font-weight: 600;
    border-bottom: 1px solid var(--border-soft) !important;
}}
[data-testid="stExpander"] summary *,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary div,
.streamlit-expanderHeader * {{
    color: var(--text) !important;
    background-color: transparent !important;
}}
[data-testid="stExpander"] summary svg,
[data-testid="stExpander"] summary[aria-expanded] svg {{
    fill: var(--text) !important;
    color: var(--text) !important;
}}
[data-testid="stExpanderDetails"],
[data-testid="stExpander"] > details > div,
.streamlit-expanderContent {{
    background-color: var(--surface) !important;
    color: var(--text) !important;
}}

/* ── Dialog / Modal (st.dialog — onboarding wizard, change password, etc) ─
   Streamlit's modal uses a hardcoded dark surface that produces dark-on-dark
   text on light themes (Cobalt) — the onboarding wizard is unreadable
   without these overrides. We target both the testid wrapper and BaseWeb's
   modal primitive to catch every Streamlit version. */
[data-testid="stDialog"],
[data-testid="stDialogContent"],
[data-baseweb="modal"],
[data-baseweb="dialog"],
div[role="dialog"][aria-modal="true"],
div[role="dialog"][aria-modal="true"] > div {{
    background-color: var(--surface) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 14px !important;
}}
[data-testid="stDialog"] *,
[data-testid="stDialogContent"] *,
[data-baseweb="modal"] *,
[data-baseweb="dialog"] *,
div[role="dialog"][aria-modal="true"] * {{
    color: var(--text) !important;
    background-color: transparent !important;
}}
/* Headings inside the dialog get text-strong; small text gets muted. */
[data-testid="stDialog"] h1,
[data-testid="stDialog"] h2,
[data-testid="stDialog"] h3,
[data-testid="stDialog"] h4,
[data-baseweb="modal"] h1,
[data-baseweb="modal"] h2,
[data-baseweb="modal"] h3,
[data-baseweb="modal"] h4 {{ color: var(--text-strong) !important; }}
[data-testid="stDialog"] small,
[data-testid="stDialog"] [data-testid="stCaptionContainer"],
[data-baseweb="modal"] small,
[data-baseweb="modal"] [data-testid="stCaptionContainer"] {{
    color: var(--text-muted) !important;
}}
/* The dim overlay behind the modal — slightly translucent dark in dark
   themes, slightly translucent black in light themes. */
[data-baseweb="modal-backdrop"],
div[role="dialog"][aria-modal="true"]::backdrop {{
    background-color: rgba(0,0,0,0.45) !important;
}}

/* ── Toast notifications (st.toast) ────────────────────────────────────── */
/* IMPORTANT: only style the toast PILL itself, NOT the container. The
   container (`stToastContainer`) is a fixed-position wrapper that holds
   all toasts; giving it a background turns it into a full-width strip
   across the page instead of a compact notification in the corner. */
[data-testid="stToastContainer"] {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}}
[data-testid="stToast"],
[data-baseweb="toast"],
[data-baseweb="notification"],
[data-baseweb="snackbar"] {{
    background-color: var(--surface-2) !important;
    background-image: none !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.12) !important;
}}
[data-testid="stToast"] *,
[data-baseweb="toast"] *,
[data-baseweb="notification"] *,
[data-baseweb="snackbar"] * {{
    color: var(--text) !important;
    background-color: transparent !important;
}}

/* ── Tooltips (the box that pops up on hover over `help=` controls) ─────── */
/* Streamlit's BaseWeb tooltip otherwise renders as a black box with white
   text — distracting on light themes and reads as "color overridden". */
[data-baseweb="tooltip"],
[role="tooltip"],
[data-testid="stTooltipContent"] {{
    background-color: var(--surface-3) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.12) !important;
    padding: 6px 10px !important;
    font-size: 0.82rem !important;
}}
[data-baseweb="tooltip"] *,
[role="tooltip"] *,
[data-testid="stTooltipContent"] * {{
    color: var(--text) !important;
    background-color: transparent !important;
}}

/* ── Chat messages ─────────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {{
    background: var(--surface-2);
    border: 1px solid var(--border-soft);
    border-radius: 12px;
    margin-bottom: 8px;
}}

/* ── Sidebar user card ─────────────────────────────────────────────────── */
.sidebar-user, .sidebar-admin {{
    background: linear-gradient(135deg, var(--hero-grad-1), var(--surface));
    border: 1px solid var(--accent-glow);
    border-radius: 14px;
    padding: 16px;
    text-align: center;
    margin-bottom: 16px;
}}

/* ── Metric / stat cards ───────────────────────────────────────────────── */
.metric-box, .stat-card {{
    background: linear-gradient(135deg, var(--card-grad-1), var(--card-grad-2));
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px 16px;
    text-align: center;
    height: 100%;
}}
.metric-box .num, .stat-card .num {{
    font-size: 2rem;
    font-weight: 800;
    color: var(--accent-soft);
    margin-bottom: 4px;
}}
.metric-box .lbl, .stat-card .lbl {{ font-size: 0.82rem; color: var(--text-muted); }}
.stat-purple .num {{ color: var(--accent-soft); }}
.stat-green  .num {{ color: var(--success); }}
.stat-blue   .num {{ color: var(--info); }}
.stat-orange .num {{ color: var(--warning); }}

/* ── Score bar ─────────────────────────────────────────────────────────── */
.score-bar-bg {{
    background: var(--surface-2);
    border-radius: 8px;
    height: 10px;
    width: 100%;
    margin-top: 6px;
    overflow: hidden;
}}
.score-bar-fill {{
    height: 100%;
    border-radius: 8px;
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
}}

/* ── Theme picker (sidebar) ────────────────────────────────────────────── */
.theme-swatch {{
    width: 100%;
    height: 36px;
    border-radius: 8px;
    border: 2px solid var(--border);
    cursor: pointer;
    margin-bottom: 4px;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    overflow: hidden;
}}
.theme-swatch:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
.theme-swatch.active {{ border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow); }}
.theme-swatch-stripe {{ flex: 1; height: 100%; }}
</style>
"""


def apply_theme(theme_name: str = None) -> None:
    """Inject the theme CSS into the current Streamlit page. Call this at
    the TOP of each page before any other st.markdown styling."""
    name = theme_name if (theme_name and theme_name in THEMES) else get_theme_name()
    st.session_state["theme"] = name
    st.markdown(get_theme_css(name), unsafe_allow_html=True)


def render_theme_selector(api_client=None, on_change_rerun: bool = True) -> None:
    """Render the theme picker in the sidebar. Saves the choice to backend
    if `api_client` is provided. Pass `on_change_rerun=False` to avoid
    automatic page refresh (useful for testing)."""
    current = get_theme_name()

    st.markdown(
        '<p style="font-size:0.85rem; font-weight:700; color:var(--accent-soft); '
        'margin:0 0 8px 0; text-transform:uppercase; letter-spacing:0.5px;">'
        '🎨 Theme</p>',
        unsafe_allow_html=True,
    )

    options = list_themes()
    # Find current index for the radio
    try:
        default_idx = next(i for i, t in enumerate(options) if t["name"] == current)
    except StopIteration:
        default_idx = 0

    picked = st.radio(
        "Theme",
        options=[t["name"] for t in options],
        index=default_idx,
        format_func=lambda n: f"{THEMES[n]['emoji']} {THEMES[n]['label']}",
        key="_theme_selector_radio",
        label_visibility="collapsed",
    )

    # Color preview strip below the radio
    preview = THEMES[picked]["preview"]
    swatches_html = "".join(
        f'<div style="flex:1; background:{c};"></div>' for c in preview
    )
    st.markdown(
        f'<div style="display:flex; height:14px; border-radius:6px; overflow:hidden; '
        f'border:1px solid var(--border); margin-top:4px;">{swatches_html}</div>'
        f'<div style="font-size:0.72rem; color:var(--text-muted); margin-top:6px;">'
        f'{THEMES[picked]["description"]}</div>',
        unsafe_allow_html=True,
    )

    # If user changed theme: persist it
    if picked != current:
        st.session_state["theme"] = picked
        if api_client is not None:
            try:
                api_client.update_theme(picked)
            except Exception:
                # Non-fatal — session state still updated, will persist this session
                pass
        if on_change_rerun:
            st.rerun()
