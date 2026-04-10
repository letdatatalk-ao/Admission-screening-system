import streamlit as st
import pandas as pd
import time
from utils.api_client import (
    get_applicants, get_sessions, get_applicant_detail, 
    update_applicant_metrics, update_publication, delete_publication,
    add_publication, EXTERNAL_API_BASE_URL
)

st.set_page_config(page_title="Review Tool", layout="wide")
st.title("Complete Candidate Validation")

if "token" not in st.session_state:
    st.error("Please login first.")
    st.stop()

# --- Session Management ---
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
        
        # Session state pour gerer l'edition des publications
        if 'editing_pub_id' not in st.session_state:
            st.session_state.editing_pub_id = None
        if 'show_add_form' not in st.session_state:
            st.session_state.show_add_form = False
        
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
            
            # Bouton pour ajouter une publication (HORS DU FORMULAIRE)
            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("Add New Publication", type="secondary", key="add_pub_btn"):
                    st.session_state.show_add_form = not st.session_state.show_add_form
                    st.session_state.editing_pub_id = None
                    st.rerun()
            
            # Formulaire d'ajout (HORS DU FORMULAIRE PRINCIPAL)
            if st.session_state.show_add_form:
                st.markdown("---")
                st.subheader("Add Publication")
                with st.form("add_publication_form"):
                    new_title = st.text_input("Title", key="new_title")
                    new_year = st.number_input("Year", min_value=1900, max_value=2026, value=2024, key="new_year")
                    new_pub_type = st.selectbox("Type", ["journal", "conference"], key="new_pub_type")
                    new_venue = st.text_input("Journal/Conference Name", key="new_venue")
                    new_authors = st.text_input("Authors", key="new_authors")
                    new_author_pos = st.number_input("Author Position", min_value=1, value=1, key="new_author_pos")
                    new_total_authors = st.number_input("Total Authors", min_value=1, value=1, key="new_total_authors")
                    new_contrib_score = st.slider("Contribution Score", 0.0, 1.0, 0.5, key="new_contrib_score")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("Save Publication"):
                            new_pub = {
                                "title": new_title,
                                "year": new_year,
                                "pub_type": new_pub_type,
                                "venue": new_venue,
                                "authors_raw": new_authors,
                                "author_position": new_author_pos,
                                "total_authors": new_total_authors,
                                "contribution_score": new_contrib_score
                            }
                            success = add_publication(applicant_id, new_pub, st.session_state.token)
                            if success:
                                st.success("Publication added!")
                                st.session_state.show_add_form = False
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Failed to add publication")
                    with col2:
                        if st.form_submit_button("Cancel"):
                            st.session_state.show_add_form = False
                            st.rerun()
                st.markdown("---")
            
            # AFFICHAGE DES PUBLICATIONS (HORS FORMULAIRE) - AVEC BOUTONS HORS FORMULAIRE
            st.markdown("### Existing Publications")
            pubs = app_data.get('publications', [])
            
            if pubs:
                for idx, pub in enumerate(pubs):
                    pub_id = pub.get('id')
                    
                    # Mode edition
                    if st.session_state.editing_pub_id == pub_id:
                        with st.container(border=True):
                            st.markdown(f"**Editing: {pub.get('title', 'Untitled')[:50]}...**")
                            
                            edit_title = st.text_input("Title", value=pub.get('title', ''), key=f"edit_title_{pub_id}")
                            edit_year = st.number_input("Year", min_value=1900, max_value=2026, value=pub.get('year', 2024), key=f"edit_year_{pub_id}")
                            edit_pub_type = st.selectbox("Type", ["journal", "conference"], 
                                                         index=0 if pub.get('pub_type') == 'journal' else 1,
                                                         key=f"edit_type_{pub_id}")
                            edit_venue = st.text_input("Journal/Conference Name", value=pub.get('venue_name', ''), key=f"edit_venue_{pub_id}")
                            edit_authors = st.text_input("Authors", value=pub.get('authors_raw', ''), key=f"edit_authors_{pub_id}")
                            edit_author_pos = st.number_input("Author Position", min_value=1, 
                                                               value=pub.get('author_position', 1),
                                                               key=f"edit_author_pos_{pub_id}")
                            edit_total_authors = st.number_input("Total Authors", min_value=1, 
                                                                 value=pub.get('total_authors', 1),
                                                                 key=f"edit_total_authors_{pub_id}")
                            edit_contrib_score = st.slider("Contribution Score", 0.0, 1.0, 
                                                            value=pub.get('contribution_score', 0.5),
                                                            key=f"edit_contrib_{pub_id}")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("Save Changes", key=f"save_edit_{pub_id}"):
                                    edited_pub = {
                                        "title": edit_title,
                                        "year": edit_year,
                                        "pub_type": edit_pub_type,
                                        "venue": edit_venue,
                                        "authors_raw": edit_authors,
                                        "author_position": edit_author_pos,
                                        "total_authors": edit_total_authors,
                                        "contribution_score": edit_contrib_score
                                    }
                                    success = update_publication(pub_id, edited_pub, st.session_state.token)
                                    if success:
                                        st.success("Publication updated!")
                                        st.session_state.editing_pub_id = None
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("Failed to update")
                            with col2:
                                if st.button("Cancel", key=f"cancel_edit_{pub_id}"):
                                    st.session_state.editing_pub_id = None
                                    st.rerun()
                    else:
                        # Affichage normal - UTILISATION DE st.columns POUR LES BOUTONS (PAS DE FORMULAIRE)
                        with st.container(border=True):
                            # Premiere ligne: titre et metadonnees
                            st.markdown(f"**{pub.get('title', 'Untitled')}**")
                            st.caption(f"Type: {pub.get('pub_type', 'unknown').capitalize()} | Venue: {pub.get('venue_name', 'No venue')} | Year: {pub.get('year', 'N/A')}")
                            st.caption(f"Authors: {pub.get('authors_raw', 'Unknown')} | Position: {pub.get('author_position', '?')}/{pub.get('total_authors', '?')}")
                            if pub.get('contribution_score'):
                                st.progress(pub.get('contribution_score', 0), text=f"Contribution: {pub.get('contribution_score', 0)*100:.0f}%")
                            
                            # Deuxieme ligne: boutons d'action
                            col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 6])
                            with col_btn1:
                                if st.button("Edit", key=f"edit_{pub_id}"):
                                    st.session_state.editing_pub_id = pub_id
                                    st.rerun()
                            with col_btn2:
                                if st.button("Delete", key=f"del_{pub_id}", type="secondary"):
                                    success = delete_publication(pub_id, st.session_state.token)
                                    if success:
                                        st.success("Publication deleted!")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("Failed to delete")
            else:
                st.info("No publications extracted. Use 'Add New Publication' to add manually.")
            
            # Formulaire principal (sans les publications)
            with st.form("full_review_form"):
                tab_id, tab_bsc, tab_msc, tab_sys = st.tabs(["Identity", "Bachelor", "Master", "System"])
                
                with tab_id:
                    full_name = st.text_input("Full Name", value=app_data.get('full_name', ''))
                    email = st.text_input("Email", value=app_data.get('email', ''))
                    nationality = st.text_input("Nationality", value=app_data.get('nationality', ''))

                with tab_bsc:
                    bsc_uni_name = st.text_input("BSc University", value=metrics.get('bsc_uni_name', ''))
                    bsc_qs_rank = st.number_input("BSc QS Rank", value=int(metrics.get('bsc_qs_rank') or 0))
                    col1, col2, col3 = st.columns(3)
                    bsc_gpa_raw = col1.number_input("BSc GPA Raw", value=float(metrics.get('bsc_gpa_raw') or 0.0))
                    bsc_gpa_scale = col2.number_input("BSc GPA Scale", value=float(metrics.get('bsc_gpa_scale') or 4.0))
                    bsc_gpa_normalised = col3.number_input("BSc GPA Normalised", value=float(metrics.get('bsc_gpa_normalised') or 0.0), step=0.01)

                with tab_msc:
                    msc_absent = st.checkbox("MSc Degree Absent", value=metrics.get('msc_absent', False))
                    msc_uni_name = None
                    msc_qs_rank = None
                    msc_gpa_raw = None
                    msc_gpa_scale = None
                    msc_gpa_normalised = None
                    if not msc_absent:
                        msc_uni_name = st.text_input("MSc University", value=metrics.get('msc_uni_name', ''))
                        msc_qs_rank = st.number_input("MSc QS Rank", value=int(metrics.get('msc_qs_rank') or 0))
                        col1, col2, col3 = st.columns(3)
                        msc_gpa_raw = col1.number_input("MSc GPA Raw", value=float(metrics.get('msc_gpa_raw') or 0.0))
                        msc_gpa_scale = col2.number_input("MSc GPA Scale", value=float(metrics.get('msc_gpa_scale') or 4.0))
                        msc_gpa_normalised = col3.number_input("MSc GPA Normalised", value=float(metrics.get('msc_gpa_normalised') or 0.0), step=0.01)

                with tab_sys:
                    st.write(f"LLM used: {metrics.get('llm_used', True)}")
                    st.write(f"Confidence score: {metrics.get('global_confidence', 0.0)}")
                    if metrics.get('extraction_source_detail'):
                        st.json(metrics.get('extraction_source_detail', {}))

                st.divider()
                needs_human_review = st.checkbox("Keep 'Review Required' flag", value=app_data.get('needs_human_review', False))
                reason = st.text_area("Adjustment Reason (Audit log)", placeholder="Required for any changes...")

                # Bouton de soumission principal
                submitted = st.form_submit_button("Save All Changes and Validate", type="primary")
                
                if submitted:
                    if reason:
                        payload = {
                            "full_name": full_name,
                            "email": email,
                            "nationality": nationality,
                            "needs_human_review": needs_human_review,
                            "review_reason": reason,
                            "bsc_uni_name": bsc_uni_name,
                            "bsc_qs_rank": bsc_qs_rank,
                            "bsc_gpa_raw": bsc_gpa_raw,
                            "bsc_gpa_scale": bsc_gpa_scale,
                            "bsc_gpa_normalised": bsc_gpa_normalised,
                            "msc_absent": msc_absent,
                            "msc_uni_name": msc_uni_name,
                            "msc_qs_rank": msc_qs_rank,
                            "msc_gpa_raw": msc_gpa_raw,
                            "msc_gpa_scale": msc_gpa_scale,
                            "msc_gpa_normalised": msc_gpa_normalised
                        }
                        success = update_applicant_metrics(applicant_id, payload, st.session_state.token)
                        if success:
                            st.success("Candidate records updated successfully")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Failed to update server records.")
                    else:
                        st.warning("Please provide a reason for the changes.")