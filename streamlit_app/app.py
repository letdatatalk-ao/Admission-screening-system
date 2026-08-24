import streamlit as st
from utils.api_client import login_user
from utils.styles import apply_theme, sidebar_nav

st.set_page_config(
    page_title="KU Admission Screening",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()
sidebar_nav(current_page="")

# ── Branded header (main area) ─────────────────────────────────────────────────
st.markdown("""
<style>
.main .block-container { max-width: 520px !important; padding-top: 4rem !important; margin: 0 auto; }
.module-btn button {
    text-align: left !important;
    background: #ffffff !important;
    border: 1px solid #dce3ed !important;
    border-radius: 6px !important;
    color: #1a2744 !important;
    font-weight: 600 !important;
    padding: 0.55rem 1rem !important;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.module-btn button:hover {
    border-color: #c8a028 !important;
    box-shadow: 0 0 0 2px rgba(200,160,40,0.18) !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="text-align:center;margin-bottom:2.5rem;">
    <div style="font-size:0.78rem;letter-spacing:0.18em;text-transform:uppercase;
                color:#8a9ab5;font-weight:500;margin-bottom:0.5rem;">
        Khalifa University
    </div>
    <div style="font-size:1.8rem;font-weight:700;color:#1a2744;line-height:1.2;">
        Admissions Screening
    </div>
    <div style="font-size:0.88rem;color:#6b7a99;margin-top:0.35rem;">
        AI-Assisted Postgraduate Evaluation System
    </div>
    <div style="width:34px;height:2px;background:#c8a028;margin:1.1rem auto 0;"></div>
</div>
""", unsafe_allow_html=True)

# ── Auth state ─────────────────────────────────────────────────────────────────
if "token" not in st.session_state:
    with st.container(border=True):
        st.markdown("#### Sign In")
        st.markdown(
            '<p style="font-size:0.82rem;color:#6b7a99;margin-top:-0.6rem;margin-bottom:1rem;">'
            "Authorised university personnel only.</p>",
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            email = st.text_input("Email address", placeholder="admin@ku.ac.ae")
            password = st.text_input("Password", type="password")
            st.markdown("<div style='height:0.2rem;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("Sign In", type="primary", use_container_width=True)

        if submit:
            if not email or not password:
                st.error("Please enter both email address and password.")
            else:
                status, res = login_user(email, password)
                if status == 200:
                    st.session_state.token = res["access_token"]
                    st.rerun()
                else:
                    st.error(f"Authentication failed — {res.get('detail', 'Invalid credentials.')}")

    st.markdown("""
    <p style="text-align:center;font-size:0.75rem;color:#aab5c8;margin-top:2rem;">
        Restricted system — access is logged and audited.
    </p>
    """, unsafe_allow_html=True)

else:
    st.markdown("#### Welcome")
    st.success("You are authenticated. Select a module from the sidebar or the list below.")
    st.markdown("---")

    modules = [
        ("Document Upload",     "Batch ingest CV and transcript pairs",     "pages/1_upload.py"),
        ("Applicant Dashboard", "Monitor processing pipeline status",       "pages/2_dashboard.py"),
        ("Review & Validate",   "Correct and validate AI extractions",      "pages/3_review.py"),
        ("Ranking Engine",      "Compute weighted candidate shortlist",     "pages/4_ranking.py"),
        ("Compare",             "Side-by-side candidate comparison",        "pages/5_compare.py"),
        ("Audit Trail",         "Tamper-evident action history",            "pages/6_audit.py"),
    ]

    for name, desc, path in modules:
        col_btn, col_desc = st.columns([2, 3])
        with col_btn:
            st.markdown('<div class="module-btn">', unsafe_allow_html=True)
            if st.button(name, key=f"nav_{name}", use_container_width=True):
                st.switch_page(path)
            st.markdown("</div>", unsafe_allow_html=True)
        with col_desc:
            st.markdown(
                f'<p style="font-size:0.875rem;color:#6b7a99;margin:0.6rem 0 0 0.25rem;">{desc}</p>',
                unsafe_allow_html=True,
            )
        st.markdown("<div style='height:0.15rem'></div>", unsafe_allow_html=True)
