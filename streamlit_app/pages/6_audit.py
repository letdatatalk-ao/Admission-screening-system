import streamlit as st
import pandas as pd
from utils.api_client import get_sessions, get_audit_logs
from utils.styles import apply_theme, institution_header, sidebar_nav, require_auth

st.set_page_config(page_title="Audit Trail — KU Screening", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
apply_theme()
sidebar_nav(current_page="pages/6_audit.py")
require_auth()

st.title("System Audit and Transparency")
institution_header("Tamper-Evident Action Log")

# ── Sidebar filters ────────────────────────────────────────────────────────────
st.sidebar.subheader("Filter Logs")
sessions = get_sessions(st.session_state.token)

if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_options = {s["name"]: s["id"] for s in sessions}
sel_session_name = st.sidebar.selectbox("Session", list(session_options.keys()))
session_id = session_options[sel_session_name]

# ── Fetch audit logs ───────────────────────────────────────────────────────────
logs = get_audit_logs(session_id, st.session_state.token)

if not logs:
    st.info(f"No audit records found for session: {sel_session_name}")
    st.stop()

df_logs = pd.DataFrame(logs)
df_logs["occurred_at"] = pd.to_datetime(df_logs["occurred_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")

# ── KPI metrics ────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Total Actions", len(df_logs))

manual_fixes = len(
    df_logs[df_logs["action_type"].str.contains("CORRECTION|OVERRIDE", case=False, na=False)]
)
c2.metric("Human Corrections", manual_fixes)

uploads = len(df_logs[df_logs["action_type"].str.contains("UPLOAD", case=False, na=False)])
c3.metric("Document Batches", uploads)

st.markdown("---")

# ── Action log ─────────────────────────────────────────────────────────────────
st.subheader("Chronological Activity Log")

action_labels = {
    "UPLOAD_PAIRED_DOCS":     "Batch Upload",
    "MANUAL_CORRECTION":      "Manual Override",
    "COMPUTE_RANKING":        "Ranking Generation",
    "VIEW_DOCUMENT":          "File Access",
    "LOGIN":                  "User Login",
    "PUBLICATION_CORRECTION": "Publication Edited",
    "PUBLICATION_DELETED":    "Publication Removed",
    "PUBLICATION_CREATED":    "Publication Added",
}

df_display = df_logs.copy()
df_display["action_type"] = df_display["action_type"].map(lambda x: action_labels.get(x, x))

all_actions = ["All Actions"] + list(df_display["action_type"].unique())
selected_action = st.selectbox("Filter by action type", all_actions)

if selected_action != "All Actions":
    df_display = df_display[df_display["action_type"] == selected_action]

st.dataframe(
    df_display[["occurred_at", "action_type", "user_id", "entity_type", "entity_id"]],
    use_container_width=True,
    hide_index=True,
    column_config={
        "occurred_at":  "Timestamp",
        "action_type":  "Action",
        "user_id":      "User",
        "entity_type":  "Target",
        "entity_id":    "Object ID",
    },
)

# ── Deep inspection ────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Record Inspection")
st.caption("Select a log entry to examine the before/after state of the changed record.")

log_id_list = df_logs["id"].tolist()
selected_log_id = st.selectbox("Log entry ID", log_id_list)

if selected_log_id:
    log_detail = df_logs[df_logs["id"] == selected_log_id].iloc[0]

    col_old, col_new = st.columns(2)
    with col_old:
        st.markdown("**Previous State**")
        st.json(log_detail.get("old_state") or {})
    with col_new:
        st.markdown("**New State**")
        st.json(log_detail.get("new_state") or {})

# ── Export ─────────────────────────────────────────────────────────────────────
st.markdown("---")
csv_audit = df_logs.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Export Full Audit Trail (CSV)",
    data=csv_audit,
    file_name=f"audit_trail_{sel_session_name}.csv",
    mime="text/csv",
    help="Download for official university compliance records.",
)
