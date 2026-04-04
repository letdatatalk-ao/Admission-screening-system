import streamlit as st
import pandas as pd
import time
from utils.api_client import get_applicants, get_sessions, get_applicant_detail, update_applicant_metrics, EXTERNAL_API_BASE_URL

st.set_page_config(page_title="Review Tool", layout="wide")
st.title("Complete Candidate Validation")

if "token" not in st.session_state:
    st.error("Please login first.")
    st.stop()

# --- Sidebar ---
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions.")
    st.stop()

session_dict = {s['name']: s['id'] for s in sessions}
session_id = st.sidebar.selectbox("Admission Session", list(session_dict.keys()))
current_session_id = session_dict[session_id]

_, applicants = get_applicants(current_session_id, st.session_state.token)
processed = [a for a in applicants if a['status'] == 'processed']

if not processed:
    st.info("No candidates processed by AI yet.")
else:
    app_map = {f"{a['full_name']} ({a['application_ref']})": a['id'] for a in processed}
    selected_name = st.sidebar.selectbox("Select Candidate", list(app_map.keys()))
    applicant_id = app_map[selected_name]
    
    app_data = get_applicant_detail(applicant_id, st.session_state.token)

    if app_data:
        metrics = app_data.get('metrics') or {}
        col_left, col_right = st.columns([1, 1.2])

        with col_left:
            st.subheader("Document Viewer")
            doc_type = st.radio("Display:", ["CV", "Transcript"], horizontal=True)
            doc_id = app_data['cv_document_id'] if doc_type == "CV" else app_data['transcript_document_id']
            if doc_id:
                st.markdown(f'<iframe src="{EXTERNAL_API_BASE_URL}/files/{doc_id}" width="100%" height="850px" style="border:1px solid #444;"></iframe>', unsafe_allow_html=True)
            else:
                st.warning("Document file not available.")

        with col_right:
            st.subheader("Review and Correction")
            payload = {}
            with st.form("full_review_form"):
                tab_id, tab_bsc, tab_msc, tab_pubs, tab_sys = st.tabs(["Identity", "Bachelor", "Master", "Publications", "System"])
                
                with tab_id:
                    payload["full_name"] = st.text_input("Full Name", value=app_data['full_name'])
                    payload["email"] = st.text_input("Email", value=app_data.get('email', ''))
                    payload["nationality"] = st.text_input("Nationality", value=app_data.get('nationality', ''))

                with tab_bsc:
                    payload["bsc_uni_name"] = st.text_input("BSc University", value=metrics.get('bsc_uni_name', ''))
                    payload["bsc_qs_rank"] = st.number_input("BSc QS Rank", value=int(metrics.get('bsc_qs_rank') or 0))
                    c1, c2, c3 = st.columns(3)
                    payload["bsc_gpa_raw"] = c1.number_input("BSc GPA Raw", value=float(metrics.get('bsc_gpa_raw') or 0.0))
                    payload["bsc_gpa_scale"] = c2.number_input("BSc GPA Scale", value=float(metrics.get('bsc_gpa_scale') or 4.0))
                    payload["bsc_gpa_normalised"] = c3.number_input("BSc GPA Normalised", value=float(metrics.get('bsc_gpa_normalised') or 0.0), step=0.01)

                with tab_msc:
                    payload["msc_absent"] = st.checkbox("MSc Degree Absent", value=metrics.get('msc_absent', False))
                    if not payload["msc_absent"]:
                        payload["msc_uni_name"] = st.text_input("MSc University", value=metrics.get('msc_uni_name', ''))
                        payload["msc_qs_rank"] = st.number_input("MSc QS Rank", value=int(metrics.get('msc_qs_rank') or 0))
                        payload["msc_gpa_normalised"] = st.number_input("MSc GPA Normalised (/4.0)", value=float(metrics.get('msc_gpa_normalised') or 0.0), step=0.01)

                with tab_pubs:
                    pubs = app_data.get('publications', [])
                    if pubs:
                        st.dataframe(pd.DataFrame(pubs)[['title', 'year', 'pub_type', 'contribution_score']], use_container_width=True)
                    else:
                        st.info("No publications extracted.")

                with tab_sys:
                    st.write(f"LLM used: {metrics.get('llm_used', True)}")
                    st.write(f"Confidence score: {metrics.get('global_confidence', 0.0)}")
                    st.json(metrics.get('extraction_source_detail', {}))

                st.divider()
                payload["needs_human_review"] = st.checkbox("Keep 'Review Required' flag", value=app_data['needs_human_review'])
                reason = st.text_area("Adjustment Reason (Audit log)", placeholder="Required for any changes...")

                if st.form_submit_button("Save All Changes and Validate"):
                    if update_applicant_metrics(applicant_id, payload, st.session_state.token):
                        st.success("Candidate records updated successfully")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Failed to update server records.")