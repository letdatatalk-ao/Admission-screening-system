import streamlit as st
import pandas as pd
from utils.api_client import get_sessions, get_applicants

st.set_page_config(page_title="Applicants Dashboard", layout="wide")

st.title("Applicants Dashboard")

if "token" not in st.session_state:
    st.error("Authentication required. Please login on the Home page.")
    st.stop()

# 1. Selection de la Session
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No evaluation sessions available.")
    st.stop()

session_dict = {s['name']: s['id'] for s in sessions}
selected_session = st.selectbox("Current Session", list(session_dict.keys()))
session_id = session_dict[selected_session]

# 2. Recuperation des donnees
status_code, applicants = get_applicants(session_id, st.session_state.token)

if status_code == 200:
    if not applicants:
        st.info("No candidates processed yet for this session.")
    else:
        df = pd.DataFrame(applicants)

        # --- Section Statistiques (KPIs) ---
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Applicants", len(df))
        c2.metric("Processed", len(df[df['status'] == 'processed']))
        
        # Securite pour la moyenne de confiance
        if 'global_confidence' in df and not df['global_confidence'].isna().all():
            avg_conf = df['global_confidence'].mean()
            c3.metric("AI Confidence Avg", f"{avg_conf*100:.1f}%")
        else:
            c3.metric("AI Confidence Avg", "N/A")
            
        c4.metric("Review Required", len(df[df['needs_human_review'] == True]))

        st.divider()

        # --- Configuration des colonnes pour affichage complet ---
        display_map = {
            "last_rank": "Rank",
            "last_composite_score": "Final Score",
            "full_name": "Full Name",
            "nationality": "Nation",
            "bsc_uni_name": "BSc University",
            "bsc_gpa_normalised": "BSc GPA",
            "msc_uni_name": "MSc University",
            "msc_gpa_normalised": "MSc GPA",
            "pub_count": "Publications",
            "status": "AI Status",
            "needs_human_review": "Review?"
        }

        # Filtrage des colonnes existantes pour eviter les erreurs d'index
        existing_cols = [c for c in display_map.keys() if c in df.columns]
        df_display = df[existing_cols].rename(columns=display_map)

        # Filtre interactif
        if st.checkbox("Show only candidates requiring review"):
            df_display = df_display[df_display["Review?"] == True]

        # Affichage du tableau de donnees
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn(format="%d"),
                "Final Score": st.column_config.NumberColumn(format="%.2f"),
                "BSc GPA": st.column_config.NumberColumn(format="%.2f"),
                "MSc GPA": st.column_config.NumberColumn(format="%.2f"),
                "Publications": st.column_config.NumberColumn(format="%d"),
                "Review?": st.column_config.CheckboxColumn()
            }
        )

        if st.button("Refresh Dashboard"):
            st.rerun()
else:
    st.error("Error: Could not retrieve data from the backend.")