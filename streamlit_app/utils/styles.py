"""
Shared styling for all Khalifa University Screening Portal pages.

Design system: "Classical" (navy hybrid) — Cormorant Garamond over Lora,
a warm near-white ground, hairline dividers carrying structure, and colour
applied as stroke/text rather than fill. The navigation rail keeps KU navy
for brand continuity; everything else is the neutral Classical palette.
Source: Claude Design project "Frontend Enhancement Planning",
Screening Redesign.dc.html (option 1b).
"""
import base64
import functools
import os
import streamlit as st

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")


@functools.lru_cache(maxsize=4)
def _logo_data_uri(filename: str) -> str:
    """Base64-encode a local asset once per process so it can sit inline in
    the raw HTML brand blocks (consistent with how the rest of this module
    builds the sidebar/title plate) instead of needing a separate st.image
    call that breaks the flex layout."""
    path = os.path.join(_ASSETS_DIR, filename)
    with open(path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def ku_logo_data_uri(on_navy: bool = False) -> str:
    """Khalifa University logo as a data: URI.
    on_navy=True returns the light-recoloured variant for the navy sidebar;
    on_navy=False returns the original black-wordmark version for light
    backgrounds (sign-in title plate, etc.).
    Source: Wikimedia Commons, CC BY-SA 4.0, originally published by ku.ac.ae.
    """
    return _logo_data_uri("ku_logo_on_navy.png" if on_navy else "ku_logo.png")

_KU_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Lora:wght@400;600&display=swap');

:root {
    --color-bg: #f3f2f2;
    --color-surface: #eae9e9;
    --color-text: #201f1d;
    --color-accent: #b68235;
    --color-accent-700: #7d5411;
    --color-accent-400: #e1ad66;
    --color-divider: rgba(32,31,29,0.14);
    --font-heading: "Cormorant Garamond", Georgia, serif;
    --font-body: "Lora", Georgia, serif;
    --navy: #1a2744;
    --navy-border: rgba(255,255,255,0.14);
    --navy-text: #d3d8e4;
}

/* ── Hide default Streamlit chrome ────────────────────── */
/* display:none, not visibility:hidden — Streamlit's own toolbar buttons
   (Deploy, etc.) set visibility:visible on themselves, which overrides an
   inherited visibility:hidden on the header and leaves them clickable.
   [data-testid="stHeader"] (not just the bare `header` element selector)
   with !important — Streamlit's own rule sets display:flex on that exact
   attribute selector, which otherwise outranks a plain element selector. */
#MainMenu { display: none; }
footer    { display: none; }
header, [data-testid="stHeader"] { display: none !important; }

/* ── Page background ──────────────────────────────────── */
/* html/body default to Streamlit's own dark theme background and show
   through as black margins wherever .stApp doesn't cover 100% of the
   viewport (e.g. window wider/taller than the rendered content). */
html, body { background: var(--color-bg) !important; }
.stApp { background: var(--color-bg); font-family: var(--font-body); }
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background: var(--color-bg); }
.stApp, .stApp p, .stApp label, .stApp span, .stApp div { color: var(--color-text); }

/* ── Sidebar — KU navy rail ───────────────────────────── */
[data-testid="stSidebar"] {
    background: var(--navy);
    border-right: 1px solid var(--navy-border);
    min-width: 240px;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] li,
[data-testid="stSidebar"] a,
[data-testid="stSidebar"] .stMarkdown { color: var(--navy-text) !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #ffffff !important; font-family: var(--font-heading) !important; }
[data-testid="stSidebar"] .stSelectbox label { color: rgba(211,216,228,.6) !important; font-size: 0.7rem !important; }
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] {
    background: rgba(255,255,255,.05);
    border: 1px solid var(--navy-border);
}
[data-testid="stSidebar"] [data-baseweb="select"] div { color: var(--navy-text) !important; }
[data-testid="stSidebarNav"] { display: none !important; }

/* ── Sidebar nav rail items ────────────────────────────── */
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    text-align: left !important;
    background: transparent !important;
    border: none !important;
    border-left: 2px solid transparent !important;
    border-radius: 0 !important;
    color: var(--navy-text) !important;
    font-family: var(--font-body) !important;
    font-weight: 400 !important;
    font-size: 0.8125rem !important;
    padding: 0.32rem 0.75rem !important;
    margin: 0 !important;
    transition: color 0.15s, border-color 0.15s;
}
[data-testid="stSidebar"] .stButton > button:hover {
    color: var(--color-accent-400) !important;
}
/* Active nav item */
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: transparent !important;
    color: var(--color-accent-400) !important;
    font-weight: 600 !important;
    border-left: 2px solid var(--color-accent-400) !important;
}
/* Sign-out button */
[data-testid="stSidebar"] .signout-wrapper .stButton > button {
    color: rgba(211,216,228,.55) !important;
    font-size: 0.75rem !important;
    border-top: 1px solid var(--navy-border) !important;
    border-left: none !important;
    border-radius: 0 !important;
    margin-top: 0.5rem !important;
    padding-top: 0.6rem !important;
}
[data-testid="stSidebar"] .signout-wrapper .stButton > button:hover {
    color: #ffaaaa !important;
}

/* ── Typography — Cormorant display, Lora body ────────── */
h1 {
    font-family: var(--font-heading) !important;
    color: var(--color-text) !important;
    font-size: 2.15rem !important;
    font-weight: 400 !important;
    letter-spacing: -0.01em;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid var(--color-divider);
    margin-bottom: 1.2rem !important;
}
h2, h3 { font-family: var(--font-heading) !important; color: var(--color-text) !important; font-weight: 600 !important; }
h4, h5 { font-family: var(--font-heading) !important; color: var(--color-text) !important; font-weight: 600 !important; }
h6 {
    font-family: var(--font-body) !important;
    font-size: 0.65rem !important;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: rgba(32,31,29,0.62) !important;
    font-weight: 500 !important;
}
p, label, .stMarkdown { color: var(--color-text); font-family: var(--font-body); }
.kicker {
    font-size: 0.6rem; letter-spacing: 0.2em; text-transform: uppercase;
    font-family: var(--font-body); color: var(--color-accent-700);
}
.num { font-variant-numeric: tabular-nums lining-nums; }

/* ── Metric "figure ledger" — hairline columns, no cards ── */
[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
    border-bottom: 1px solid var(--color-divider);
}
[data-testid="metric-container"], [data-testid="stMetric"] {
    background: transparent !important;
    border: none !important;
    border-left: 1px solid var(--color-divider) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 0.7rem 0 0.6rem 1rem !important;
}
[data-testid="stMetricValue"] {
    color: var(--color-text) !important;
    font-family: var(--font-heading) !important;
    font-size: 2.1rem !important;
    font-weight: 400 !important;
    line-height: 1.05 !important;
}
[data-testid="stMetricLabel"] {
    color: rgba(32,31,29,0.5) !important;
    font-size: 0.62rem !important;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-weight: 500;
    font-family: var(--font-body) !important;
}

/* ── Buttons — stroke, not fill ────────────────────────── */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
    font-family: var(--font-heading) !important;
    font-weight: 600 !important;
    border-radius: 4px !important;
    transition: background 0.15s ease, border-color 0.15s ease;
}
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primaryFormSubmit"] {
    background: transparent !important;
    color: var(--color-accent-700) !important;
    border: 1px solid var(--color-accent) !important;
    letter-spacing: 0.02em;
    padding: 0.4rem 1.3rem;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primaryFormSubmit"]:hover {
    background: rgba(182,130,53,0.12) !important;
    color: var(--color-accent-700) !important;
    border-color: var(--color-accent) !important;
}
.stButton > button[kind="primary"]:disabled,
.stFormSubmitButton > button[kind="primaryFormSubmit"]:disabled {
    opacity: 0.4 !important; border-color: var(--color-divider) !important; color: rgba(32,31,29,.4) !important;
}

/* ── Secondary buttons ─────────────────────────────────── */
.stButton > button[kind="secondary"],
.stFormSubmitButton > button[kind="secondaryFormSubmit"] {
    border: 1px solid var(--color-divider) !important;
    color: var(--color-text) !important;
    background: transparent !important;
}
.stButton > button[kind="secondary"]:hover,
.stFormSubmitButton > button[kind="secondaryFormSubmit"]:hover {
    border-color: rgba(32,31,29,.4) !important;
    background: rgba(32,31,29,0.045) !important;
}

/* ── Download buttons — ghost link style ───────────────── */
.stDownloadButton > button {
    background: transparent !important;
    border: none !important;
    color: var(--color-accent-700) !important;
    font-weight: 600;
    padding-left: 0 !important;
    text-decoration: underline;
    text-underline-offset: 3px;
}
.stDownloadButton > button:hover { color: var(--color-accent) !important; }

/* ── Form inputs ────────────────────────────────────────── */
/* The *RootElement wrapper (not the <input> itself) carries Streamlit's own
   hardcoded dark theme background — must be overridden separately or fields
   render as dark boxes regardless of the <input>'s own transparent background. */
[data-testid="stTextInputRootElement"],
[data-testid="stTextAreaRootElement"],
[data-testid="stNumberInputRootElement"] {
    background: transparent !important;
    border: 1px solid var(--color-divider) !important;
    border-radius: 4px !important;
    box-shadow: none !important;
}
/* Multiselect chips (e.g. the dashboard's status filter) — Streamlit
   paints these with its red theme colour by default. */
[data-baseweb="tag"] {
    background: var(--color-accent) !important;
    border-radius: 3px !important;
}
[data-baseweb="tag"] span { color: #ffffff !important; }

/* BaseWeb's inner input wrapper carries its own hardcoded dark fill,
   one level inside the RootElement checked above. */
[data-baseweb="base-input"] {
    background: transparent !important;
    box-shadow: none !important;
}
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stNumberInputRootElement"]:focus-within {
    border-color: var(--color-accent) !important;
    box-shadow: 0 0 0 1px var(--color-accent) !important;
}
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    font-family: var(--font-body) !important;
    border: none !important;
    color: var(--color-text) !important;
    background: transparent !important;
}
.stTextInput label, .stTextArea label, .stNumberInput label, .stSelectbox label {
    font-size: 0.72rem !important; color: rgba(32,31,29,.7) !important;
}

/* ── Alerts ─────────────────────────────────────────────── */
div[data-testid="stAlert"] { border-radius: 4px; font-family: var(--font-body); }

/* ── Slider — thin hairline track, ringed thumb ────────── */
/* Mirrors the mockup's own <input type=range>: a flat hairline track with no
   filled/unfilled colour split, just a gold-ringed thumb. */
.stSlider [data-baseweb="slider"] div[role="slider"] {
    background: var(--color-bg) !important;
    border: 1.5px solid var(--color-accent) !important;
    box-shadow: none !important;
}
/* Streamlit paints the track as an inline background-image gradient (its
   theme's red primaryColor) on an unlabelled div — no stable data-testid,
   so it's targeted by its distinctive fixed inline height instead. */
.stSlider [data-baseweb="slider"] div[style*="height: 0.25rem"] {
    background-image: none !important;
    background-color: var(--color-divider) !important;
}
.stSlider [data-testid="stTickBarMin"], .stSlider [data-testid="stTickBarMax"] {
    font-family: var(--font-body); color: rgba(32,31,29,.45);
}
.stSlider label { font-family: var(--font-body) !important; color: var(--color-text) !important; }

/* ── Progress bar ───────────────────────────────────────── */
.stProgress > div > div > div > div { background: var(--color-accent) !important; }
.stProgress > div > div { background: var(--color-divider) !important; }

/* ── Tabs ───────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid var(--color-divider); gap: 0; }
.stTabs [data-baseweb="tab"] {
    font-family: var(--font-heading);
    color: rgba(32,31,29,.55);
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.55rem 1.1rem;
    border-radius: 0;
    border-bottom: 1px solid transparent;
    margin-bottom: -1px;
}
.stTabs [aria-selected="true"] {
    color: var(--color-accent-700) !important;
    border-bottom: 1px solid var(--color-accent) !important;
}

/* ── Divider ────────────────────────────────────────────── */
hr { border: none; border-top: 1px solid var(--color-divider); margin: 1.4rem 0; }

/* ── DataFrames — hairline table, no card box ──────────── */
[data-testid="stDataFrame"] {
    border-radius: 0;
    border: none;
    border-top: 1px solid var(--color-divider);
}
[data-testid="stDataFrame"] * { font-family: var(--font-body) !important; }

/* ── Containers ─────────────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 4px !important;
    border-color: var(--color-divider) !important;
    background: transparent;
}

/* ── Selectbox ──────────────────────────────────────────── */
.stSelectbox [data-baseweb="select"] {
    border: 1px solid var(--color-divider);
    border-radius: 4px;
    background: transparent;
}
/* Same hardcoded-dark-wrapper pattern as the text input's base-input div. */
[data-baseweb="select"] > div {
    background: transparent !important;
}

/* ── Radio / checkbox — same hardcoded-theme-colour pattern ────────────── */
[data-baseweb="radio"] > div:first-child,
[data-baseweb="checkbox"] > div:first-child {
    background: transparent !important;
    border-color: var(--color-divider) !important;
}
[data-baseweb="radio"] input:checked + div,
[data-baseweb="checkbox"] input:checked + div {
    background: var(--color-accent) !important;
    border-color: var(--color-accent) !important;
}

/* ── Status tags — outline pills, not filled chips ─────── */
.tag {
    display: inline-flex; align-items: center; font-size: 0.68rem;
    letter-spacing: 0.02em; padding: 2px 9px; border-radius: 3px;
    font-family: var(--font-body);
}
.tag-outline  { border: 1px solid var(--color-accent); color: var(--color-accent-700); }
.tag-neutral  { border: 1px solid var(--color-divider); color: rgba(32,31,29,.55); }
.tag-accent   { border: 1px solid var(--color-accent); background: rgba(182,130,53,.10); color: var(--color-accent-700); }

/* Legacy badge aliases (kept for any page not yet migrated) */
.badge-processing { border:1px solid var(--color-accent);color:var(--color-accent-700);padding:2px 9px;border-radius:3px;font-size:0.68rem;font-weight:500; }
.badge-processed  { border:1px solid var(--color-divider);color:rgba(32,31,29,.55);padding:2px 9px;border-radius:3px;font-size:0.68rem;font-weight:500; }
.badge-error      { border:1px solid var(--color-accent);background:rgba(182,130,53,.10);color:var(--color-accent-700);padding:2px 9px;border-radius:3px;font-size:0.68rem;font-weight:500; }
.badge-pending    { border:1px solid var(--color-divider);color:rgba(32,31,29,.4);padding:2px 9px;border-radius:3px;font-size:0.68rem;font-weight:500; }
</style>
"""


def apply_theme() -> None:
    """Inject the KU Classical (navy-hybrid) theme CSS. Call once per page after set_page_config."""
    st.markdown(_KU_CSS, unsafe_allow_html=True)


def institution_header(subtitle: str = "") -> None:
    """Render the institution sub-caption line under the page title."""
    parts = ["Khalifa University", "Office of Graduate Admissions"]
    if subtitle:
        parts.append(subtitle)
    label = "&nbsp;&middot;&nbsp;".join(parts)
    st.markdown(
        f'<p class="kicker" style="margin:-0.9rem 0 1.3rem 0;">{label}</p>',
        unsafe_allow_html=True,
    )


def require_auth() -> None:
    """Redirect to login page if the user is not authenticated.
    Shows a visible button as fallback in case the browser redirect is delayed."""
    if "token" not in st.session_state:
        st.markdown("""
<div style="text-align:center;padding:4rem 1rem 2rem;">
    <div style="width:40px;height:1px;background:#b68235;margin:0 auto 1.5rem;"></div>
    <p style="font-family:'Lora',serif;font-size:0.95rem;color:rgba(32,31,29,.6);margin-bottom:1.8rem;">
        You are not signed in. Authentication is required to access this module.
    </p>
</div>
""", unsafe_allow_html=True)
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            if st.button("Return to Sign In", type="primary", use_container_width=True, key="_auth_redirect"):
                st.switch_page("app.py")
        st.stop()


# Map page filename → (label, description)
_NAV_PAGES = [
    ("pages/1_upload.py",    "Document Upload",     "Ingest CV and transcript pairs"),
    ("pages/2_dashboard.py", "Applicant Dashboard", "Pipeline status and overview"),
    ("pages/3_review.py",    "Review & Validate",   "Correct AI extractions"),
    ("pages/4_ranking.py",   "Ranking Engine",      "Compute candidate shortlist"),
    ("pages/5_compare.py",   "Compare",             "Side-by-side evaluation"),
    ("pages/6_audit.py",     "Audit Trail",         "Tamper-evident action log"),
]


def sidebar_nav(current_page: str = "") -> None:
    """
    Render the KU-branded sidebar navigation.
    current_page: filename of the active page (e.g. 'pages/2_dashboard.py').
    """
    with st.sidebar:
        # ── Brand header ───────────────────────────────────────────────────
        st.markdown(f"""
<div style="padding:1.5rem 1.25rem 1.1rem;border-bottom:1px solid var(--navy-border);margin-bottom:0.4rem;">
    <img src="{ku_logo_data_uri(on_navy=True)}" alt="Khalifa University" style="height:26px;display:block;margin-bottom:0.7rem;">
    <div style="font-family:'Cormorant Garamond',serif;font-size:1.3rem;font-weight:400;color:#ffffff;line-height:1.2;">
        Admissions Screening
    </div>
    <div style="width:26px;height:1px;background:#e1ad66;margin-top:0.7rem;"></div>
</div>
""", unsafe_allow_html=True)

        # ── Navigation items ───────────────────────────────────────────────
        if "token" in st.session_state:
            st.markdown(
                '<p class="kicker" style="color:rgba(211,216,228,.4);padding:0 0.5rem;margin:0.6rem 0 0.3rem;">Modules</p>',
                unsafe_allow_html=True,
            )
            for path, label, desc in _NAV_PAGES:
                is_active = current_page == path
                if st.button(
                    label,
                    key=f"sidenav_{path}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    st.switch_page(path)

            # ── Sign out ───────────────────────────────────────────────────
            st.markdown("<div class='signout-wrapper'>", unsafe_allow_html=True)
            if st.button("Sign Out", key="sidebar_signout", use_container_width=True):
                del st.session_state.token
                st.switch_page("app.py")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                '<p style="font-family:\'Lora\',serif;font-size:0.8rem;color:rgba(211,216,228,.5);padding:0.5rem 0.25rem;">'
                'Sign in to access the system.</p>',
                unsafe_allow_html=True,
            )
            if st.button("Go to Sign In", key="sidebar_signin", use_container_width=True, type="primary"):
                st.switch_page("app.py")

        # ── Footer ─────────────────────────────────────────────────────────
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.markdown("""
<div style="padding:0.7rem 1.25rem;border-top:1px solid var(--navy-border);">
    <p class="kicker" style="color:rgba(211,216,228,.35);line-height:1.7;letter-spacing:.12em;">
        Restricted &mdash; every action is logged
    </p>
</div>
""", unsafe_allow_html=True)
