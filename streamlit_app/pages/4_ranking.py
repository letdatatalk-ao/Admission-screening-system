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

st.title("🏆 Ranking & Scoring Engine")
st.write("Adjust weights to prioritize criteria and generate the shortlist.")

if "token" not in st.session_state:
    st.error("Please login first.")
    st.stop()

# --- 1. SÉLECTION DE LA SESSION ---
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_options = {s['name']: s['id'] for s in sessions}
selected_session_name = st.selectbox("Select Admission Session", options=list(session_options.keys()))
session_id = session_options[selected_session_name]

st.divider()

# --- 2. SLIDERS POUR LES POIDS ---
st.subheader("⚙️ Weight Configuration")
st.info("The sum of weights should ideally be 1.0 (100%)")

col1, col2 = st.columns(2)

with col1:
    w_bsc = st.slider("Bachelor GPA Weight", 0.0, 1.0, 0.30, 0.05)
    w_msc = st.slider("Master GPA Weight", 0.0, 1.0, 0.20, 0.05)

with col2:
    w_journals = st.slider("Journal Publications Weight", 0.0, 1.0, 0.30, 0.05)
    w_confs = st.slider("Conferences Weight", 0.0, 1.0, 0.20, 0.05)

total_w = round(w_bsc + w_msc + w_journals + w_confs, 2)
if total_w != 1.0:
    st.warning(f"Current total: {total_w}. Adjust to 1.0 for better consistency.")
else:
    st.success("✅ Weights are balanced (1.0).")

# --- 3. CALCUL DU CLASSEMENT ---
if st.button("🚀 Compute Official Ranking", type="primary"):
    # A. Création du profil de poids
    config_name = f"Profile_{time.strftime('%H%M%S')}"
    weights = {
        "w_bsc": w_bsc, 
        "w_msc": w_msc, 
        "w_journals": w_journals, 
        "w_conferences": w_confs
    }
    
    with st.spinner("Step 1: Saving weight configuration..."):
        config = create_ranking_config(session_id, config_name, weights, st.session_state.token)
    
    if config:
        config_id = config['id']
        with st.spinner("Step 2: Computing scores for all candidates..."):
            status, res = trigger_ranking_computation(session_id, config_id, st.session_state.token)
            
            if status == 200:
                st.success("Ranking successfully computed!")
                st.balloons()
                time.sleep(1)
                st.rerun() # On rafraichit pour voir les résultats
            else:
                st.error("Error during computation. Check backend logs.")
    else:
        st.error("Failed to create Ranking Configuration.")

# --- 4. AFFICHAGE DES RÉSULTATS ---
st.divider()
st.subheader("📊 Latest Ranking Results")

ranking_data = get_latest_ranking_results(session_id, st.session_state.token)

if ranking_data and ranking_data.get('scores_snapshot'):
    # Le snapshot est stocké en JSONB dans votre base
    df = pd.DataFrame(ranking_data['scores_snapshot'])
    
    # On trie par rang
    df = df.sort_values("rank")
    
    # On affiche un beau tableau
    st.dataframe(
        df[["rank", "applicant_name", "final_score", "bsc_academic", "msc_academic"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "rank": "Rank #",
            "applicant_name": "Candidate",
            "final_score": st.column_config.NumberColumn("Final Score", format="%.2f"),
        }
    )
    
    # Bouton d'export
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Official Shortlist (CSV)", data=csv, file_name=f"ranking_{selected_session_name}.csv")
else:
    st.info("No ranking computed yet for this session. Use the button above.")