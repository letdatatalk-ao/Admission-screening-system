import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.api_client import get_applicants, get_sessions, get_applicant_detail

# Helper function pour convertir en float
def to_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

st.set_page_config(page_title="Compare Candidates", layout="wide")
st.title("Candidate Comparison Tool")

if "token" not in st.session_state:
    st.error("Please login first.")
    st.stop()

# Sélection de la session
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_dict = {s['name']: s['id'] for s in sessions}
selected_session_name = st.sidebar.selectbox("Select Session", options=list(session_dict.keys()))
session_id = session_dict[selected_session_name]

# Récupération des candidats
status, applicants = get_applicants(session_id, st.session_state.token)
if status != 200 or not applicants:
    st.info("No applicants found in this session.")
    st.stop()

processed = [a for a in applicants if a.get('status') == 'processed']
if not processed:
    st.info("No processed candidates available for comparison.")
    st.stop()

# Sélection des candidats à comparer
selected = st.multiselect(
    "Select up to 3 candidates to compare", 
    options=[a['id'] for a in processed],
    format_func=lambda x: next((a['full_name'] for a in processed if a['id'] == x), x),
    max_selections=3
)

if not selected:
    st.info("Select at least one candidate to display comparison.")
    st.stop()

# Création du graphique radar
fig = go.Figure()

for app_id in selected:
    app_data = get_applicant_detail(app_id, st.session_state.token)
    if not app_data:
        continue
    
    metrics = app_data.get('metrics', {})
    publications = app_data.get('publications', [])
    
    # Calcul des scores normalisés (0-100)
    bsc_gpa = to_float(metrics.get('bsc_gpa_normalised')) * 25
    msc_gpa = to_float(metrics.get('msc_gpa_normalised')) * 25
    research_score = min(len(publications) * 30, 100)
    confidence = to_float(metrics.get('global_confidence')) * 100
    
    scores = [bsc_gpa, msc_gpa, research_score, confidence]
    categories = ['BSc GPA', 'MSc GPA', 'Publications', 'Extraction Confidence']
    
    fig.add_trace(go.Scatterpolar(
        r=scores, 
        theta=categories, 
        fill='toself', 
        name=app_data.get('full_name', 'Unknown')
    ))

fig.update_layout(
    polar=dict(
        radialaxis=dict(visible=True, range=[0, 100])
    ),
    showlegend=True,
    title="Candidate Performance Radar Chart"
)

st.plotly_chart(fig, use_container_width=True)

# Tableau comparatif
st.subheader("Detailed Comparison")

comparison_data = []
for app_id in selected:
    app_data = get_applicant_detail(app_id, st.session_state.token)
    if not app_data:
        continue
    
    metrics = app_data.get('metrics', {})
    publications = app_data.get('publications', [])
    
    comparison_data.append({
        "Candidate": app_data.get('full_name', 'Unknown'),
        "Status": app_data.get('status', 'unknown'),
        "BSc University": metrics.get('bsc_uni_name', 'N/A'),
        "BSc GPA": metrics.get('bsc_gpa_normalised', 'N/A'),
        "MSc University": metrics.get('msc_uni_name', 'N/A'),
        "MSc GPA": metrics.get('msc_gpa_normalised', 'N/A'),
        "Publications": len(publications),
        "Confidence": f"{to_float(metrics.get('global_confidence')) * 100:.1f}%"
    })

if comparison_data:
    df = pd.DataFrame(comparison_data)
    st.dataframe(df, use_container_width=True, hide_index=True)