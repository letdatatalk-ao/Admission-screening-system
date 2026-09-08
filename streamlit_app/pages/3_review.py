import streamlit as st
import time
from utils.api_client import (
    get_applicants,
    get_sessions,
    get_applicant_detail,
    update_applicant_metrics,
    update_publication,
    delete_publication,
    add_publication,
    EXTERNAL_API_BASE_URL,
)
from utils.styles import apply_theme, institution_header, sidebar_nav, require_auth, ku_favicon_path

st.set_page_config(page_title="Review & Validate — KU Screening", page_icon=ku_favicon_path(), layout="wide", initial_sidebar_state="expanded")
apply_theme()
sidebar_nav(current_page="pages/3_review.py")
require_auth()

st.title("Review and Validate")
institution_header("Human-in-the-Loop Correction")

# ── Session and candidate selection ───────────────────────────────────────────
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions.")
    st.stop()

session_dict = {s["name"]: s["id"] for s in sessions}
session_name = st.sidebar.selectbox("Admission Session", list(session_dict.keys()))
current_session_id = session_dict[session_name]

_, applicants = get_applicants(current_session_id, st.session_state.token)
processed = [a for a in applicants if a["status"] == "processed"]

if not processed:
    st.info("No candidates have been processed by the AI pipeline yet.")
    st.stop()

# Candidate picker — flagged candidates sorted first and marked in the
# label itself, so the queue is visible while browsing, not just on the
# one auto-selected on page load.
review_flagged = [a for a in processed if a.get("needs_human_review")]

only_flagged = st.sidebar.checkbox(
    "Needs review only",
    value=False,
    help="Show only candidates the pipeline flagged for human review",
)
candidate_pool = review_flagged if only_flagged else processed
candidate_pool = sorted(candidate_pool, key=lambda a: not a.get("needs_human_review"))

if not candidate_pool:
    st.sidebar.success("No candidates need review.")
    st.stop()


def _label(a: dict) -> str:
    marker = "[Needs review] " if a.get("needs_human_review") else ""
    return f"{marker}{a['full_name']} ({a['application_ref']})"


app_map = {_label(a): a["id"] for a in candidate_pool}
app_keys = list(app_map.keys())

selected_name = st.sidebar.selectbox("Candidate", app_keys, index=0)
applicant_id = app_map[selected_name]

if review_flagged:
    st.sidebar.info(f"{len(review_flagged)} candidate(s) need review")

app_data = get_applicant_detail(applicant_id, st.session_state.token)

if not app_data:
    st.error("Could not load candidate data from the API.")
    st.stop()

metrics = app_data.get("metrics") or {}

# ── Session state ─────────────────────────────────────────────────────────────
if "editing_pub_id" not in st.session_state:
    st.session_state.editing_pub_id = None
if "show_add_form" not in st.session_state:
    st.session_state.show_add_form = False

col_left, col_right = st.columns([1, 1.25])

# ── Left panel: document viewer (auto-select CV for review-flagged) ──────────
with col_left:
    st.subheader("Document Viewer")

    has_cv   = bool(app_data.get("cv_document_id"))
    has_tr   = bool(app_data.get("transcript_document_id"))

    # Auto-select: show CV first; if no CV but has transcript, show transcript
    default_doc = "CV" if has_cv else "Transcript"
    doc_type = st.radio("Display", ["CV", "Transcript"], horizontal=True,
                        index=0 if default_doc == "CV" else 1)

    doc_id = (
        app_data["cv_document_id"]
        if doc_type == "CV"
        else app_data["transcript_document_id"]
    )
    if doc_id:
        # /files/{id} requires evaluator auth, but a plain <iframe src> can't
        # attach an Authorization header — pass the JWT as a query param
        # instead (the backend accepts either; see check_evaluator_header_or_query).
        st.markdown(
            f'<iframe src="{EXTERNAL_API_BASE_URL}/files/{doc_id}?token={st.session_state.token}" '
            'width="100%" height="860px" '
            'style="border:1px solid var(--color-divider);border-radius:4px;"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"No {doc_type} file available for this candidate.")
        if doc_type == "CV" and has_tr:
            st.info("Transcript is available — switch to Transcript above.")
        elif doc_type == "Transcript" and has_cv:
            st.info("CV is available — switch to CV above.")

# ── Right panel: review form ───────────────────────────────────────────────────
with col_right:
    if app_data.get("needs_human_review"):
        st.warning("This candidate is flagged for human review.")

    st.subheader("Review and Correction")

    # Add publication button
    col_add, _ = st.columns([1, 4])
    with col_add:
        if st.button("Add Publication", type="secondary", key="add_pub_btn"):
            st.session_state.show_add_form = not st.session_state.show_add_form
            st.session_state.editing_pub_id = None
            st.rerun()

    # Add publication form
    if st.session_state.show_add_form:
        st.markdown("---")
        st.markdown("#### Add Publication")
        with st.form("add_publication_form"):
            new_title       = st.text_input("Title")
            new_year        = st.number_input("Year", min_value=1900, max_value=2030, value=2024)
            new_pub_type    = st.selectbox("Type", ["journal", "conference", "book_chapter", "preprint"])
            new_venue       = st.text_input("Journal / Conference Name")
            new_doi         = st.text_input("DOI (optional)", placeholder="10.xxxx/xxxxx")
            new_authors     = st.text_input("Authors")
            new_author_pos  = st.number_input("Author Position", min_value=1, value=1)
            new_total_authors = st.number_input("Total Authors", min_value=1, value=1)
            new_contrib_score = st.slider("Contribution Score", 0.0, 1.0, 0.5)

            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.form_submit_button("Save Publication", type="primary"):
                    new_pub = {
                        "title": new_title,
                        "year": new_year,
                        "pub_type": new_pub_type,
                        "venue": new_venue,
                        "doi": new_doi or None,
                        "authors_raw": new_authors,
                        "author_position": new_author_pos,
                        "total_authors": new_total_authors,
                        "contribution_score": new_contrib_score,
                    }
                    success = add_publication(applicant_id, new_pub, st.session_state.token)
                    if success:
                        st.success("Publication added.")
                        st.session_state.show_add_form = False
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Failed to add publication.")
            with col_cancel:
                if st.form_submit_button("Cancel"):
                    st.session_state.show_add_form = False
                    st.rerun()
        st.markdown("---")

    # ── Publication list ───────────────────────────────────────────────────────
    st.markdown("#### Publications")
    pubs = app_data.get("publications", [])

    if pubs:
        for pub in pubs:
            pub_id = pub.get("id")

            if st.session_state.editing_pub_id == pub_id:
                with st.container(border=True):
                    st.markdown(f"**Editing:** {pub.get('title', 'Untitled')[:60]}")

                    edit_title  = st.text_input("Title", value=pub.get("title", ""), key=f"et_{pub_id}")
                    edit_year   = st.number_input("Year", min_value=1900, max_value=2030,
                                                  value=pub.get("year", 2024), key=f"ey_{pub_id}")
                    type_opts   = ["journal", "conference", "book_chapter", "preprint"]
                    cur_type    = pub.get("pub_type", "journal")
                    type_idx    = type_opts.index(cur_type) if cur_type in type_opts else 0
                    edit_pub_type = st.selectbox("Type", type_opts, index=type_idx, key=f"ept_{pub_id}")
                    edit_venue  = st.text_input("Journal / Conference",
                                                value=pub.get("venue_name", ""), key=f"ev_{pub_id}")
                    edit_doi    = st.text_input("DOI", value=pub.get("doi", "") or "", key=f"edoi_{pub_id}")
                    edit_authors = st.text_input("Authors", value=pub.get("authors_raw", ""),
                                                 key=f"ea_{pub_id}")
                    edit_author_pos = st.number_input("Author Position", min_value=1,
                                                       value=pub.get("author_position", 1),
                                                       key=f"eap_{pub_id}")
                    edit_total_authors = st.number_input("Total Authors", min_value=1,
                                                          value=pub.get("total_authors", 1),
                                                          key=f"eta_{pub_id}")
                    edit_contrib = st.slider("Contribution Score", 0.0, 1.0,
                                            value=float(pub.get("contribution_score", 0.5)),
                                            key=f"ec_{pub_id}")

                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("Save Changes", key=f"save_{pub_id}", type="primary"):
                            edited_pub = {
                                "title": edit_title, "year": edit_year,
                                "pub_type": edit_pub_type, "venue": edit_venue,
                                "doi": edit_doi or None,
                                "authors_raw": edit_authors,
                                "author_position": edit_author_pos,
                                "total_authors": edit_total_authors,
                                "contribution_score": edit_contrib,
                            }
                            success = update_publication(pub_id, edited_pub, st.session_state.token)
                            if success:
                                st.success("Updated.")
                                st.session_state.editing_pub_id = None
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Update failed.")
                    with col_cancel:
                        if st.button("Cancel", key=f"cancel_{pub_id}"):
                            st.session_state.editing_pub_id = None
                            st.rerun()
            else:
                with st.container(border=True):
                    # Title row with type badge
                    scopus = pub.get("scopus_pct_at_extraction")
                    core   = pub.get("core_score_at_extraction")
                    doi    = pub.get("doi")
                    pos    = pub.get("author_position") or "?"
                    tot    = pub.get("total_authors") or "?"

                    col_t, col_b = st.columns([6, 1])
                    with col_t:
                        st.markdown(f"**{pub.get('title', 'Untitled')}**")
                    with col_b:
                        st.markdown(
                            f'<span class="tag tag-outline">{pub.get("pub_type","").upper()}</span>',
                            unsafe_allow_html=True,
                        )

                    venue_line = pub.get("venue_name") or "No venue"
                    year_line  = pub.get("year") or "N/A"
                    st.caption(f"{venue_line} · {year_line}")

                    # Rank badges
                    if scopus is not None:
                        q = "Q1" if scopus >= 75 else "Q2" if scopus >= 50 else "Q3" if scopus >= 25 else "Q4"
                        st.markdown(
                            f'<span class="tag tag-accent">{q}</span>'
                            f' <span class="num" style="font-size:0.72rem;color:rgba(32,31,29,.55);">Scopus {scopus:.0f}th pct</span>',
                            unsafe_allow_html=True,
                        )
                    if core is not None:
                        st.caption(f"CORE score: {core}")
                    if doi:
                        st.caption(f"DOI: {doi}")

                    st.caption(
                        f"Authors: {pub.get('authors_raw', 'Unknown')} "
                        f"| Position: {pos}/{tot}"
                    )
                    if pub.get("contribution_score"):
                        st.progress(
                            float(pub["contribution_score"]),
                            text=f"Contribution: {pub['contribution_score'] * 100:.0f}%",
                        )

                    col_edit, col_del, _ = st.columns([1, 1, 6])
                    with col_edit:
                        if st.button("Edit", key=f"edit_{pub_id}", type="secondary"):
                            st.session_state.editing_pub_id = pub_id
                            st.rerun()
                    with col_del:
                        if st.button("Delete", key=f"del_{pub_id}", type="secondary"):
                            success = delete_publication(pub_id, st.session_state.token)
                            if success:
                                st.success("Removed.")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Delete failed.")
    else:
        st.info("No publications extracted. Use 'Add Publication' to enter records manually.")

    # ── Main metrics form ──────────────────────────────────────────────────────
    st.markdown("---")
    with st.form("full_review_form"):
        tab_id, tab_bsc, tab_msc, tab_phd, tab_tests, tab_research, tab_sys = st.tabs(
            ["Identity", "Bachelor", "Master", "PhD", "Tests & Language", "Research", "System"]
        )

        with tab_id:
            full_name   = st.text_input("Full Name",    value=app_data.get("full_name", ""))
            email       = st.text_input("Email",        value=app_data.get("email", ""))
            nationality = st.text_input("Nationality",  value=app_data.get("nationality", ""))
            phone       = st.text_input("Phone",        value=app_data.get("phone", "") or "")
            linkedin    = st.text_input("LinkedIn URL", value=app_data.get("linkedin", "") or "")

        with tab_bsc:
            bsc_uni_name = st.text_input("BSc University", value=metrics.get("bsc_uni_name") or "")
            col_f, col_c, col_y = st.columns(3)
            bsc_field   = col_f.text_input("Field / Discipline", value=metrics.get("bsc_field") or "")
            bsc_country = col_c.text_input("Country", value=metrics.get("bsc_country") or "")
            bsc_year    = col_y.number_input("Graduation Year", value=int(metrics.get("bsc_year") or 0))
            bsc_qs_rank = st.number_input("BSc QS Rank", value=int(metrics.get("bsc_qs_rank") or 0))
            col1, col2, col3 = st.columns(3)
            bsc_gpa_raw        = col1.number_input("Raw GPA",         value=float(metrics.get("bsc_gpa_raw") or 0.0))
            bsc_gpa_scale      = col2.number_input("Scale",           value=float(metrics.get("bsc_gpa_scale") or 4.0))
            bsc_gpa_normalised = col3.number_input("Normalised (0-1)", value=float(metrics.get("bsc_gpa_normalised") or 0.0), min_value=0.0, max_value=1.0, step=0.01)

        with tab_msc:
            msc_absent = st.checkbox("MSc degree absent", value=metrics.get("msc_absent", False))
            msc_uni_name = msc_qs_rank = msc_gpa_raw = msc_gpa_scale = msc_gpa_normalised = None
            msc_field = msc_country = ""; msc_year = 0
            if not msc_absent:
                msc_uni_name = st.text_input("MSc University", value=metrics.get("msc_uni_name") or "")
                col_f, col_c, col_y = st.columns(3)
                msc_field   = col_f.text_input("Field", value=metrics.get("msc_field") or "", key="msc_field")
                msc_country = col_c.text_input("Country", value=metrics.get("msc_country") or "", key="msc_country")
                msc_year    = col_y.number_input("Year", value=int(metrics.get("msc_year") or 0), key="msc_year")
                msc_qs_rank = st.number_input("MSc QS Rank", value=int(metrics.get("msc_qs_rank") or 0))
                col1, col2, col3 = st.columns(3)
                msc_gpa_raw        = col1.number_input("Raw GPA",         value=float(metrics.get("msc_gpa_raw") or 0.0), key="msc_gpa_raw_in")
                msc_gpa_scale      = col2.number_input("Scale",           value=float(metrics.get("msc_gpa_scale") or 4.0), key="msc_scale_in")
                msc_gpa_normalised = col3.number_input("Normalised (0-1)", value=float(metrics.get("msc_gpa_normalised") or 0.0), min_value=0.0, max_value=1.0, step=0.01, key="msc_norm_in")

        with tab_phd:
            phd_uni_name = st.text_input("PhD University (if any)", value=metrics.get("phd_uni_name") or "")
            col_f, col_y = st.columns(2)
            phd_field    = col_f.text_input("PhD Field", value=metrics.get("phd_field") or "")
            phd_year     = col_y.number_input("PhD Year", value=int(metrics.get("phd_year") or 0))
            phd_qs_rank  = st.number_input("PhD University QS Rank", value=int(metrics.get("phd_qs_rank") or 0))
            work_exp_years = st.number_input(
                "Work Experience (years)", value=float(metrics.get("work_exp_years") or 0.0),
                min_value=0.0, step=0.5,
                help="Total years of relevant professional experience"
            )

        with tab_tests:
            st.markdown("**GRE Scores**")
            col_v, col_q, col_a = st.columns(3)
            gre_verbal = col_v.number_input("GRE Verbal (130–170)",  value=int(metrics.get("gre_verbal") or 0), min_value=0, max_value=170)
            gre_quant  = col_q.number_input("GRE Quant (130–170)",   value=int(metrics.get("gre_quant") or 0),  min_value=0, max_value=170)
            gre_awa    = col_a.number_input("GRE AWA (0–6)",         value=float(metrics.get("gre_awa") or 0.0), min_value=0.0, max_value=6.0, step=0.5)
            st.markdown("**Language Proficiency**")
            col_i, col_t = st.columns(2)
            ielts_score = col_i.number_input("IELTS Overall (0–9)",   value=float(metrics.get("ielts_score") or 0.0), min_value=0.0, max_value=9.0, step=0.5)
            toefl_score = col_t.number_input("TOEFL iBT (0–120)",     value=int(metrics.get("toefl_score") or 0), min_value=0, max_value=120)

        with tab_research:
            interests_raw = metrics.get("research_interests") or []
            interests_str = ", ".join(interests_raw) if isinstance(interests_raw, list) else str(interests_raw)
            research_interests_input = st.text_area(
                "Research Interests (comma-separated)",
                value=interests_str,
                help="Will be stored as a list of strings",
            )
            awards_raw = metrics.get("awards") or []
            awards_str = ", ".join(awards_raw) if isinstance(awards_raw, list) else str(awards_raw)
            awards_input = st.text_area(
                "Awards & Honors (comma-separated)",
                value=awards_str,
            )

        with tab_sys:
            st.markdown(f"LLM used: `{metrics.get('llm_used', True)}`")
            st.markdown(f"Confidence score: `{metrics.get('global_confidence', 0.0)}`")
            if metrics.get("extraction_source_detail"):
                st.json(metrics.get("extraction_source_detail", {}))

        st.markdown("---")
        needs_human_review = st.checkbox(
            "Keep 'Review Required' flag",
            value=app_data.get("needs_human_review", False),
        )
        reason = st.text_area(
            "Reason for adjustment (required for audit log)",
            placeholder="Describe what was corrected and why...",
        )

        submitted = st.form_submit_button("Save and Validate", type="primary")

        if submitted:
            if not reason:
                st.warning("An adjustment reason is required before saving.")
            else:
                # Parse list fields
                research_list = [x.strip() for x in research_interests_input.split(",") if x.strip()]
                awards_list   = [x.strip() for x in awards_input.split(",") if x.strip()]

                payload = {
                    "full_name": full_name,
                    "email": email or None,
                    "nationality": nationality,
                    "phone": phone or None,
                    "linkedin": linkedin or None,
                    "needs_human_review": needs_human_review,
                    "review_reason": reason,
                    # BSc
                    "bsc_uni_name": bsc_uni_name,
                    "bsc_qs_rank": bsc_qs_rank or None,
                    "bsc_gpa_raw": bsc_gpa_raw or None,
                    "bsc_gpa_scale": bsc_gpa_scale or None,
                    "bsc_gpa_normalised": bsc_gpa_normalised or None,
                    "bsc_field": bsc_field or None,
                    "bsc_country": bsc_country or None,
                    "bsc_year": bsc_year or None,
                    # MSc
                    "msc_absent": msc_absent,
                    "msc_uni_name": msc_uni_name,
                    "msc_qs_rank": msc_qs_rank or None,
                    "msc_gpa_raw": msc_gpa_raw or None,
                    "msc_gpa_scale": msc_gpa_scale or None,
                    "msc_gpa_normalised": msc_gpa_normalised or None,
                    "msc_field": msc_field or None,
                    "msc_country": msc_country or None,
                    "msc_year": msc_year or None,
                    # PhD
                    "phd_uni_name": phd_uni_name or None,
                    "phd_field": phd_field or None,
                    "phd_year": phd_year or None,
                    "phd_qs_rank": phd_qs_rank or None,
                    "work_exp_years": work_exp_years or None,
                    # Tests
                    "gre_verbal": gre_verbal or None,
                    "gre_quant": gre_quant or None,
                    "gre_awa": gre_awa or None,
                    "ielts_score": ielts_score or None,
                    "toefl_score": toefl_score or None,
                    # Research
                    "research_interests": research_list or None,
                    "awards": awards_list or None,
                }
                success = update_applicant_metrics(applicant_id, payload, st.session_state.token)
                if success:
                    st.success("Candidate record updated and saved.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to update the record. Check the API connection.")
