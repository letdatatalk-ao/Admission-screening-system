import streamlit as st
import pandas as pd
import time
from utils.api_client import (
    get_sessions, 
    create_ranking_config, 
    trigger_ranking_computation, 
    get_latest_ranking_results
)

st.set_page_config(page_title="Ranking Engine - KU", layout="wide")

st.title(" Ranking & Scoring Engine")
st.write("Adjust weights to prioritize criteria and generate the shortlist.")

if "token" not in st.session_state:
    st.error("Please login first.")
    st.stop()

sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_options = {s['name']: s['id'] for s in sessions}
selected_session_name = st.selectbox("Select Admission Session", options=list(session_options.keys()))
session_id = session_options[selected_session_name]

st.divider()

st.subheader("Weight Configuration")
st.info("The sum of weights should be 100%")

col1, col2 = st.columns(2)

with col1:
    w_bsc = st.slider("Bachelor GPA Weight (%)", 0, 100, 30, 5)
    w_msc = st.slider("Master GPA Weight (%)", 0, 100, 20, 5)

with col2:
    w_journals = st.slider("Journal Publications Weight (%)", 0, 100, 30, 5)
    w_confs = st.slider("Conferences Weight (%)", 0, 100, 20, 5)

total_w = w_bsc + w_msc + w_journals + w_confs
if total_w != 100:
    st.warning(f" Current total: {total_w}%. Adjust to 100% for consistency.")
else:
    st.success(" Weights are balanced (100%).")

if st.button(" Compute Official Ranking", type="primary"):
    config_name = f"Profile_{time.strftime('%H%M%S')}"
    weights = {
        "w_bsc": float(w_bsc), 
        "w_msc": float(w_msc), 
        "w_journals": float(w_journals), 
        "w_conferences": float(w_confs)
    }
    
    with st.spinner("Step 1: Saving weight configuration..."):
        config = create_ranking_config(session_id, config_name, weights, st.session_state.token)
    
    if config:
        config_id = config['id']
        with st.spinner("Step 2: Computing scores for all candidates..."):
            status, res = trigger_ranking_computation(session_id, config_id, st.session_state.token)
            
            if status == 200:
                st.success("✅ Ranking successfully computed!")
                st.balloons()
                time.sleep(1)
                st.rerun()
            else:
                st.error("Error during computation. Check backend logs.")
    else:
        st.error("Failed to create Ranking Configuration.")

st.divider()
st.subheader(" Latest Ranking Results")

ranking_data = get_latest_ranking_results(session_id, st.session_state.token)

if ranking_data and ranking_data.get('scores_snapshot'):
    df = pd.DataFrame(ranking_data['scores_snapshot'])
    df = df.sort_values("rank")
    
    st.dataframe(
        df[["rank", "applicant_name", "final_score", "bsc_academic", "msc_academic", "needs_review"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "rank": "Rank #",
            "applicant_name": "Candidate",
            "final_score": st.column_config.NumberColumn("Final Score", format="%.2f"),
            "bsc_academic": st.column_config.NumberColumn("BSc Score", format="%.2f"),
            "msc_academic": st.column_config.NumberColumn("MSc Score", format="%.2f"),
            "needs_review": " Needs Review",
        }
    )
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        " Download Official Shortlist (CSV)", 
        data=csv, 
        file_name=f"ranking_{selected_session_name}.csv",
        mime="text/csv"
    )
    
    with st.expander(" Statistics"):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Candidates", len(df))
        col2.metric("Average Score", f"{df['final_score'].mean():.1f}")
        col3.metric("Needs Review", df['needs_review'].sum() if 'needs_review' in df.columns else 0)
        col4.metric("Score Range", f"{df['final_score'].min():.0f} - {df['final_score'].max():.0f}")
else:
    st.info("No ranking computed yet for this session. Use the button above.")