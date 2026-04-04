import streamlit as st
import pandas as pd
import time
from utils.api_client import (
    get_applicants, 
    get_sessions, 
    get_applicant_detail, 
    update_applicant_metrics,
    EXTERNAL_API_BASE_URL
)

# Configuration de la page en mode large
st.set_page_config(page_title="Review Tool - KU Screening", layout="wide")

st.title("🧐 Complete Candidate Validation")

if "token" not in st.session_state:
    st.error("🔒 Please login on the Home page first.")
    st.stop()

# --- 1. BARRE LATÉRALE : SÉLECTION DU CANDIDAT ---
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_options = {s['name']: s['id'] for s in sessions}
sel_session_name = st.sidebar.selectbox("Admission Session", list(session_options.keys()))
session_id = session_options[sel_session_name]

# Récupération des candidats traités (processed) pour la session choisie
_, applicants = get_applicants(session_id, st.session_state.token)
processed_apps = [a for a in applicants if a['status'] == 'processed']

if not processed_apps:
    st.info("No candidates ready for review. Ensure candidates are 'processed' by the AI first.")
else:
    # Liste de sélection dans la sidebar
    app_options = {f"{a['full_name']}": a['id'] for a in processed_apps}
    selected_app_label = st.sidebar.selectbox("Select Candidate to Review", list(app_options.keys()))
    applicant_id = app_options[selected_app_label]
    
    # Récupération des détails complets depuis l'API
    app_data = get_applicant_detail(applicant_id, st.session_state.token)

    if app_data:
        metrics = app_data.get('metrics') or {}
        
        # --- 2. LAYOUT : PDF À GAUCHE, FORMULAIRE À DROITE ---
        col_pdf, col_data = st.columns([1, 1.2])

        with col_pdf:
            st.subheader("📄 Document Viewer")
            doc_type = st.radio("Display document:", ["CV", "Transcript"], horizontal=True)
            
            # On récupère l'ID du document à afficher
            doc_id = app_data['cv_document_id'] if doc_type == "CV" else app_data['transcript_document_id']
            
            if doc_id:
                # Utilisation de l'URL externe pour que le navigateur charge l'Iframe
                file_url = f"{EXTERNAL_API_BASE_URL}/files/{doc_id}"
                st.markdown(
                    f'<iframe src="{file_url}" width="100%" height="850px" style="border: 1px solid #444; border-radius: 5px;"></iframe>', 
                    unsafe_allow_html=True
                )
            else:
                st.warning("Document file ID not found in database.")

        with col_data:
            st.subheader("📝 Metric Validation")
            
            # Ce dictionnaire contiendra toutes les valeurs à envoyer au backend
            updated_payload = {}

            # Formulaire de révision
            with st.form("full_review_form"):
                # CORRECTION : Unpacking des 4 onglets
                tab_bsc, tab_msc, tab_pubs, tab_sys = st.tabs([
                    "🎓 Bachelor", "🎓 Master", "📚 Publications", "⚙️ System"
                ])
                
                with tab_bsc:
                    st.markdown("#### Bachelor Degree Information")
                    updated_payload["bsc_uni_name"] = st.text_input("BSc University Name", value=metrics.get('bsc_uni_name', ''))
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        updated_payload["bsc_gpa_normalised"] = st.number_input(
                            "BSc GPA (Normalised /4.0)", 
                            value=float(metrics.get('bsc_gpa_normalised') or 0.0), 
                            step=0.01
                        )
                    with c2:
                        st.write("") # Espace vertical
                        updated_payload["bsc_gpa_normalised_done"] = st.checkbox(
                            "Validated by Reviewer", 
                            value=metrics.get('bsc_gpa_normalised_done', False)
                        )

                with tab_msc:
                    st.markdown("#### Master Degree Information")
                    updated_payload["msc_absent"] = st.checkbox("No Master's Degree (MSc Absent)", value=metrics.get('msc_absent', False))
                    
                    if not updated_payload["msc_absent"]:
                        updated_payload["msc_uni_name"] = st.text_input("MSc University Name", value=metrics.get('msc_uni_name', ''))
                        updated_payload["msc_gpa_normalised"] = st.number_input(
                            "MSc GPA (Normalised /4.0)", 
                            value=float(metrics.get('msc_gpa_normalised') or 0.0), 
                            step=0.01
                        )
                    else:
                        st.info("Candidate will be ranked based on Bachelor data only.")

                with tab_pubs:
                    st.markdown("#### Research Publications")
                    pubs = app_data.get('publications', [])
                    if pubs:
                        df_pubs = pd.DataFrame(pubs)
                        # On affiche les colonnes clés
                        st.dataframe(df_pubs[['pub_type', 'title', 'year', 'contribution_score']], use_container_width=True)
                    else:
                        st.info("No research publications were extracted for this candidate.")

                with tab_sys:
                    st.markdown("#### AI System Insights")
                    st.write(f"**LLM Extraction Used:** {'✅ Yes' if metrics.get('llm_used') else '❌ No'}")
                    
                    conf_score = float(metrics.get('global_confidence') or 0.0)
                    st.metric("Global Confidence Score", f"{conf_score * 100:.1f}%")
                    
                    st.markdown("**Raw Extraction Details:**")
                    st.json(metrics.get('extraction_source_detail', {}))

                st.divider()
                st.markdown("#### 🛡️ Validation & Audit")
                reason = st.text_area("Reason for manual adjustments", placeholder="Mandatory for the audit trail...")
                
                # Le flag de révision forcée (visible sur le dashboard)
                updated_payload["needs_human_review"] = st.checkbox("Keep 'Review Required' flag active", value=app_data.get('needs_human_review', False))

                # Bouton de soumission
                if st.form_submit_button("💾 Save All Changes & Approve"):
                    # On appelle la fonction de l'api_client
                    success = update_applicant_metrics(applicant_id, updated_payload, st.session_state.token)
                    
                    if success:
                        st.success(f"Successfully updated records for {app_data['full_name']}!")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Failed to update database. Please check the backend logs.")