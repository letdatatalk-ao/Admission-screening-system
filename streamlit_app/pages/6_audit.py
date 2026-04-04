import streamlit as st
import pandas as pd
import json
from utils.api_client import get_sessions, get_audit_logs

# Configuration de la page
st.set_page_config(page_title="Audit Trail - KU Screening", layout="wide")

st.title("🛡️ System Audit & Transparency")
st.write("Complete history of system actions and human interventions.")

if "token" not in st.session_state:
    st.error("🔒 Please login on the Home page first.")
    st.stop()

# --- 1. FILTRES DE RECHERCHE ---
st.sidebar.header("Filter Logs")
sessions = get_sessions(st.session_state.token)

if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_options = {s['name']: s['id'] for s in sessions}
sel_session_name = st.sidebar.selectbox("Session", list(session_options.keys()))
session_id = session_options[sel_session_name]

# --- 2. RÉCUPÉRATION DES LOGS ---
logs = get_audit_logs(session_id, st.session_state.token)

if not logs:
    st.info(f"No audit records found for session: {sel_session_name}")
else:
    df_logs = pd.DataFrame(logs)

    # Nettoyage des colonnes pour l'affichage
    # Conversion du timestamp en format lisible
    df_logs['occurred_at'] = pd.to_datetime(df_logs['occurred_at']).dt.strftime('%Y-%m-%d %H:%M:%S')

    # --- 3. VUE D'ENSEMBLE (KPIs) ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Actions", len(df_logs))
    
    # On compte les corrections humaines
    manual_fixes = len(df_logs[df_logs['action_type'].str.contains('CORRECTION|OVERRIDE', case=False, na=False)])
    c2.metric("Human Corrections", manual_fixes)
    
    # On compte les uploads
    uploads = len(df_logs[df_logs['action_type'].str.contains('UPLOAD', case=False, na=False)])
    c3.metric("Document Batches", uploads)

    st.divider()

    # --- 4. LE JOURNAL D'AUDIT INTERACTIF ---
    st.subheader("📋 Chronological Activity Log")
    
    # Mapping des noms d'actions pour Mr Werghi
    action_labels = {
        "UPLOAD_PAIRED_DOCS": "📥 Batch Upload",
        "MANUAL_CORRECTION": "✏️ Manual Override",
        "COMPUTE_RANKING": "🏆 Ranking Generation",
        "VIEW_DOCUMENT": "👁️ File Access",
        "LOGIN": "🔑 User Login"
    }
    
    # Appliquer le mapping si possible
    df_display = df_logs.copy()
    df_display['action_type'] = df_display['action_type'].map(lambda x: action_labels.get(x, x))

    # Sélecteur de type d'action pour filtrer le tableau
    all_actions = ["All Actions"] + list(df_display['action_type'].unique())
    selected_action = st.selectbox("Filter by action type", all_actions)

    if selected_action != "All Actions":
        df_display = df_display[df_display['action_type'] == selected_action]

    # Affichage du tableau principal
    st.dataframe(
        df_display[['occurred_at', 'action_type', 'user_id', 'entity_type', 'entity_id']],
        use_container_width=True,
        hide_index=True,
        column_config={
            "occurred_at": "Timestamp",
            "action_type": "Action",
            "user_id": "Author (User ID)",
            "entity_type": "Target",
            "entity_id": "Object ID"
        }
    )

    # --- 5. DÉTAILS DE L'ACTION (L'inspecteur de JSON) ---
    st.divider()
    st.subheader("🔍 Deep Inspection")
    st.write("Select a log entry ID below to see exactly what changed (JSON diff).")

    log_id_list = df_logs['id'].tolist()
    selected_log_id = st.selectbox("Select Log ID to inspect", log_id_list)

    if selected_log_id:
        log_detail = df_logs[df_logs['id'] == selected_log_id].iloc[0]
        
        col_old, col_new = st.columns(2)
        with col_old:
            st.markdown("**Previous State:**")
            st.json(log_detail.get('old_state') or {})
        
        with col_new:
            st.markdown("**New State:**")
            st.json(log_detail.get('new_state') or {})

    # --- 6. BOUTON D'EXPORT LÉGAL ---
    st.divider()
    csv_audit = df_logs.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Export Full Audit Trail (CSV)",
        data=csv_audit,
        file_name=f"audit_trail_{sel_session_name}.csv",
        mime="text/csv",
        help="Download this for official university compliance records."
    )