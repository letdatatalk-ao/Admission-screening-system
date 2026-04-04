import streamlit as st
import pandas as pd
from utils.api_client import get_sessions, get_applicants

st.set_page_config(page_title="Applicants Dashboard", layout="wide")
st.title("Applicants Dashboard")

if "token" not in st.session_state:
    st.error("Authentication required. Please login on the Home page.")
    st.stop()

# ── 1. Sélection de la Session ──────────────────────────────────────────────
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No evaluation sessions available.")
    st.stop()

session_dict = {s['name']: s['id'] for s in sessions}
selected_session = st.selectbox("Current Session", list(session_dict.keys()))
session_id = session_dict[selected_session]

# ── 2. Récupération des données ──────────────────────────────────────────────
status_code, applicants = get_applicants(session_id, st.session_state.token)

if status_code != 200:
    st.error("Error: Could not retrieve data from the backend.")
    st.stop()

if not applicants:
    st.info("No candidates processed yet for this session.")
    st.stop()

df = pd.DataFrame(applicants)

# ── 3. KPIs ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Applicants", len(df))
c2.metric("Processed",   int((df['status'] == 'processed').sum()))
c3.metric("Pending",     int((df['status'] == 'pending').sum()))
c4.metric("Review Required", int(df['needs_human_review'].sum()))
if 'global_confidence' in df and not df['global_confidence'].isna().all():
    c5.metric("Avg AI Confidence", f"{df['global_confidence'].mean() * 100:.1f}%")
else:
    c5.metric("Avg AI Confidence", "N/A")

st.divider()

# ── 4. Filtres ────────────────────────────────────────────────────────────────
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    status_filter = st.multiselect(
        "Filter by status",
        options=df['status'].unique().tolist(),
        default=df['status'].unique().tolist()
    )
with col_f2:
    review_only = st.checkbox("Show only candidates requiring review")
with col_f3:
    hide_msc_absent = st.checkbox("Hide candidates without MSc")

df_filtered = df[df['status'].isin(status_filter)].copy()
if review_only:
    df_filtered = df_filtered[df_filtered['needs_human_review'] == True]
if hide_msc_absent and 'msc_absent' in df_filtered.columns:
    df_filtered = df_filtered[df_filtered['msc_absent'] == False]

# ── 5. Mapping complet des colonnes ──────────────────────────────────────────
display_map = {
    # Classement
    "last_rank":             "Rank",
    "last_composite_score":  "Final Score",
    # Identité
    "full_name":             "Full Name",
    "nationality":           "Nationality",
    # BSc
    "bsc_uni_name":          "BSc University",
    "bsc_qs_rank":           "BSc QS Rank",
    "bsc_gpa_raw":           "BSc GPA (raw)",
    "bsc_gpa_scale":         "BSc Scale",
    "bsc_gpa_normalised":    "BSc GPA (norm)",
    # MSc
    "msc_absent":            "MSc Absent",
    "msc_uni_name":          "MSc University",
    "msc_qs_rank":           "MSc QS Rank",
    "msc_gpa_raw":           "MSc GPA (raw)",
    "msc_gpa_scale":         "MSc Scale",
    "msc_gpa_normalised":    "MSc GPA (norm)",
    # Publications & Méta
    "pub_count":             "Publications",
    "global_confidence":     "AI Confidence",
    "llm_used":              "LLM Used",
    "model_used":            "Model",
    "status":                "Status",
    "needs_human_review":    "Review?",
}

existing_cols = [c for c in display_map if c in df_filtered.columns]
df_display = df_filtered[existing_cols].rename(columns=display_map)

# Formater la confiance en %
if "AI Confidence" in df_display.columns:
    df_display["AI Confidence"] = df_display["AI Confidence"].apply(
        lambda x: f"{x * 100:.1f}%" if pd.notna(x) else "N/A"
    )

# ── 6. Tableau principal ──────────────────────────────────────────────────────
st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Rank":           st.column_config.NumberColumn(format="%d"),
        "Final Score":    st.column_config.NumberColumn(format="%.2f"),
        "BSc QS Rank":    st.column_config.NumberColumn(format="#%d"),
        "BSc GPA (raw)":  st.column_config.NumberColumn(format="%.2f"),
        "BSc Scale":      st.column_config.NumberColumn(format="%.1f"),
        "BSc GPA (norm)": st.column_config.ProgressColumn(
            min_value=0, max_value=1, format="%.3f"
        ),
        "MSc QS Rank":    st.column_config.NumberColumn(format="#%d"),
        "MSc GPA (raw)":  st.column_config.NumberColumn(format="%.2f"),
        "MSc Scale":      st.column_config.NumberColumn(format="%.1f"),
        "MSc GPA (norm)": st.column_config.ProgressColumn(
            min_value=0, max_value=1, format="%.3f"
        ),
        "Publications":   st.column_config.NumberColumn(format="%d"),
        "MSc Absent":     st.column_config.CheckboxColumn(),
        "LLM Used":       st.column_config.CheckboxColumn(),
        "Review?":        st.column_config.CheckboxColumn(),
    }
)

st.caption(f"{len(df_display)} candidate(s) shown")

# ── 7. Export CSV ─────────────────────────────────────────────────────────────
col_r, col_e = st.columns([1, 1])
with col_r:
    if st.button("🔄 Refresh Dashboard"):
        st.rerun()
with col_e:
    csv = df_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Export CSV",
        data=csv,
        file_name=f"dashboard_{selected_session}.csv",
        mime="text/csv"
    )