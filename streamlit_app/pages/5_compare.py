import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.api_client import get_applicants, get_sessions, get_applicant_detail

st.set_page_config(page_title="Compare Candidates", layout="wide")
st.title("⚖️ Visual Comparison Tool")

if "token" not in st.session_state:
    st.error("Please login first.")
    st.stop()

sessions = get_sessions(st.session_state.token)
session_id = st.sidebar.selectbox("Session", {s['name']: s['id'] for s in sessions}.values())

_, applicants = get_applicants(session_id, st.session_state.token)
processed = [a for a in applicants if a['status'] == 'processed']

selected = st.multiselect("Select up to 3 candidates", 
                          options=[a['id'] for a in processed],
                          format_func=lambda x: next(a['full_name'] for a in processed if a['id'] == x),
                          max_selections=3)

if selected:
    fig = go.Figure()
    for app_id in selected:
        data = get_applicant_detail(app_id, st.session_state.token)
        m = data['metrics']
        # Normalisation pour le graph (0-100)
        scores = [
            to_f(m.get('bsc_gpa_normalised')) * 25, 
            to_f(m.get('msc_gpa_normalised')) * 25,
            min(len(data.get('publications', [])) * 30, 100),
            to_f(m.get('global_confidence')) * 100
        ]
        categories = ['BSc GPA', 'MSc GPA', 'Research', 'AI Confidence']
        
        fig.add_trace(go.Scatterpolar(r=scores, theta=categories, fill='toself', name=data['full_name']))

    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=True)
    st.plotly_chart(fig, use_container_width=True)