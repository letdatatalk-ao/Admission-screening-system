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

st.markdown("""
<style>
.main .block-container { max-width: 1180px !important; padding-top: 2.5rem !important; margin: 0 auto; }
.title-plate {
    padding: 2rem 2.4rem; border-right: 1px solid var(--color-divider);
    display: flex; flex-direction: column; min-height: 560px;
}
.title-plate h1 {
    font-family: 'Cormorant Garamond', serif; font-size: 3.1rem; font-weight: 400;
    line-height: 1.05; letter-spacing: -.02em; margin: 1.1rem 0 0; border: none; padding: 0;
}
.title-rule { width: 60px; height: 1px; background: var(--color-accent); margin: 1.4rem 0 1.2rem; }
.title-lede {
    font-family: 'Lora', serif; font-size: 0.92rem; line-height: 1.7; max-width: 46ch;
    color: rgba(32,31,29,.72); text-align: justify;
}
.title-stats { margin-top: auto; display: flex; gap: 2.6rem; padding-top: 1.6rem; border-top: 1px solid var(--color-divider); }
.title-stats .stat-label { font-size: 0.6rem; letter-spacing: .18em; text-transform: uppercase; color: rgba(32,31,29,.45); }
.title-stats .stat-value { font-family: 'Cormorant Garamond', serif; font-size: 1.05rem; margin-top: 4px; }
.module-row {
    display: flex; align-items: baseline; gap: 14px; padding: 12px 0;
    border-bottom: 1px solid var(--color-divider);
}
.module-row .m-desc { font-family: 'Lora', serif; font-size: 0.82rem; color: rgba(32,31,29,.55); }
</style>
""", unsafe_allow_html=True)

# ── Auth state ─────────────────────────────────────────────────────────────────
if "token" not in st.session_state:
    col_plate, col_form = st.columns([1.15, 1], gap="large")

    with col_plate:
        st.markdown("""
<div class="title-plate">
    <div class="kicker">Khalifa University &middot; Office of Graduate Admissions</div>
    <h1>Postgraduate<br>Admissions<br>Screening</h1>
    <div class="title-rule"></div>
    <p class="title-lede">An AI-assisted evaluation system for PhD and MSc applications. Uploaded
    curricula vitae and transcripts are read, cross-checked against QS, Scopus and CORE, and
    scored against the weights the admissions committee has set for the cycle. Every extracted
    figure remains open to human correction, and every correction is recorded.</p>
    <div class="title-stats">
        <div><div class="stat-label">Current cycle</div><div class="stat-value">Fall 2026</div></div>
        <div><div class="stat-label">Scoring</div><div class="stat-value">Configurable weights</div></div>
        <div><div class="stat-label">Every correction</div><div class="stat-value">Logged &amp; audited</div></div>
    </div>
</div>
""", unsafe_allow_html=True)

    with col_form:
        st.markdown("<div style='padding:2.4rem 1rem 0 0.5rem'>", unsafe_allow_html=True)
        st.markdown("#### Sign In")
        st.markdown(
            '<p style="font-family:\'Lora\',serif;font-size:0.82rem;color:rgba(32,31,29,.6);margin-top:-0.6rem;margin-bottom:1.2rem;">'
            "Authorised university personnel only.</p>",
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            email = st.text_input("University email address", placeholder="name@ku.ac.ae")
            password = st.text_input("Password", type="password")
            st.markdown("<div style='height:0.2rem;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("Sign in", type="primary", use_container_width=True)

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
        <div style="margin-top:2.2rem;padding-top:1rem;border-top:1px solid var(--color-divider);">
            <p style="font-family:'Lora',serif;font-size:0.7rem;line-height:1.7;color:rgba(32,31,29,.5);">
                Restricted system. Sessions, document access and every field correction are written
                to a tamper-evident audit log.
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

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
        col_btn, col_desc = st.columns([1.4, 3])
        with col_btn:
            if st.button(name, key=f"nav_{name}", use_container_width=True, type="secondary"):
                st.switch_page(path)
        with col_desc:
            st.markdown(
                f'<p class="m-desc" style="margin:0.65rem 0 0 0.25rem;">{desc}</p>',
                unsafe_allow_html=True,
            )
