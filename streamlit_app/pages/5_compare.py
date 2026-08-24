import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.api_client import get_applicants, get_sessions, get_applicant_detail
from utils.styles import apply_theme, institution_header, sidebar_nav, require_auth


def to_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


st.set_page_config(page_title="Compare Candidates — KU Screening", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")
apply_theme()
sidebar_nav(current_page="pages/5_compare.py")
require_auth()

st.title("Candidate Comparison")
institution_header("Side-by-Side Evaluation")

# ── Session selection ──────────────────────────────────────────────────────────
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_dict = {s["name"]: s["id"] for s in sessions}
selected_session_name = st.sidebar.selectbox("Admission Session", options=list(session_dict.keys()))
session_id = session_dict[selected_session_name]

# ── Fetch candidates ───────────────────────────────────────────────────────────
status, applicants = get_applicants(session_id, st.session_state.token)
if status != 200 or not applicants:
    st.info("No applicants found in this session.")
    st.stop()

processed = [a for a in applicants if a.get("status") == "processed"]
if not processed:
    st.info("No processed candidates available for comparison yet.")
    st.stop()

# ── Candidate selection ────────────────────────────────────────────────────────
selected = st.multiselect(
    "Select up to 3 candidates to compare",
    options=[a["id"] for a in processed],
    format_func=lambda x: next((a["full_name"] for a in processed if a["id"] == x), str(x)),
    max_selections=3,
)

if not selected:
    st.info("Select at least one candidate from the list above to display a comparison.")
    st.stop()

# ── Radar chart ────────────────────────────────────────────────────────────────
fig = go.Figure()

# KU brand palette
palette = ["#1a2744", "#c8a028", "#4a7ab5"]
categories = ["BSc GPA", "MSc GPA", "Publications", "AI Confidence"]

for i, app_id in enumerate(selected):
    app_data = get_applicant_detail(app_id, st.session_state.token)
    if not app_data:
        continue

    metrics = app_data.get("metrics", {})
    publications = app_data.get("publications", [])

    bsc_gpa = to_float(metrics.get("bsc_gpa_normalised")) * 100
    msc_gpa = to_float(metrics.get("msc_gpa_normalised")) * 100
    research_score = min(len(publications) * 30, 100)
    confidence = to_float(metrics.get("global_confidence")) * 100

    scores = [bsc_gpa, msc_gpa, research_score, confidence]
    color = palette[i % len(palette)]

    fig.add_trace(
        go.Scatterpolar(
            r=scores,
            theta=categories,
            fill="toself",
            name=app_data.get("full_name", "Unknown"),
            line=dict(color=color, width=2),
            opacity=0.75,
        )
    )

fig.update_layout(
    polar=dict(
        radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=10)),
        angularaxis=dict(tickfont=dict(size=12, color="#2c3a52")),
        bgcolor="#f9fafc",
    ),
    showlegend=True,
    legend=dict(orientation="h", y=-0.15, font=dict(size=12)),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    margin=dict(t=40, b=60, l=60, r=60),
    font=dict(family="Inter, Segoe UI, system-ui", color="#2c3a52"),
    title=dict(
        text="Performance Radar",
        font=dict(size=14, color="#1a2744", weight="bold"),
        x=0.5,
    ),
)

st.plotly_chart(fig, use_container_width=True)

# ── Comparison table ───────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Detailed Comparison")

comparison_data = []
for app_id in selected:
    app_data = get_applicant_detail(app_id, st.session_state.token)
    if not app_data:
        continue
    metrics = app_data.get("metrics", {})
    publications = app_data.get("publications", [])

    comparison_data.append(
        {
            "Candidate":       app_data.get("full_name", "Unknown"),
            "Status":          app_data.get("status", "unknown"),
            "BSc University":  metrics.get("bsc_uni_name", "N/A"),
            "BSc GPA (norm)":  round(to_float(metrics.get("bsc_gpa_normalised")), 3),
            "MSc University":  metrics.get("msc_uni_name", "N/A"),
            "MSc GPA (norm)":  round(to_float(metrics.get("msc_gpa_normalised")), 3),
            "Publications":    len(publications),
            "AI Confidence":   f"{to_float(metrics.get('global_confidence')) * 100:.1f}%",
        }
    )

if comparison_data:
    df = pd.DataFrame(comparison_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
