import streamlit as st
import pandas as pd
from utils.api_client import upload_paired_documents, get_sessions
import uuid

st.set_page_config(page_title="Mass Upload - KU Screening", layout="wide")

st.title("🚀 Smart Mass Document Upload")
st.info("💡 **Instructions:** Drop all your files together. The system matches '[ID] CV' with '[ID] T'. If a file is missing, you can upload it specifically for that candidate below.")

if "token" not in st.session_state:
    st.error("Please login first on the Home page.")
    st.stop()

# --- 1. GESTION DE LA MÉMOIRE (SESSION STATE) ---
# On utilise un dictionnaire pour stocker les fichiers par ID : { "ID": {"cv": file, "tr": file} }
if 'upload_registry' not in st.session_state:
    st.session_state.upload_registry = {}

def add_file_to_registry(uploaded_file):
    if uploaded_file is None: return
    fname = uploaded_file.name.upper()
    try:
        # On extrait l'ID (premier mot avant l'espace)
        fid = uploaded_file.name.split(' ')[0].strip()
    except:
        return

    if fid not in st.session_state.upload_registry:
        st.session_state.upload_registry[fid] = {"cv": None, "tr": None}
    
    if "CV" in fname:
        st.session_state.upload_registry[fid]["cv"] = uploaded_file
    elif " T" in fname or "TRANSCRIPT" in fname:
        st.session_state.upload_registry[fid]["tr"] = uploaded_file

# --- 2. SÉLECTION DE LA SESSION ---
sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active evaluation sessions found. Create one first in Swagger.")
    st.stop()

session_options = {s['name']: s['id'] for s in sessions}
selected_session = st.selectbox("Target Session", options=list(session_options.keys()))
session_id = session_options[selected_session]

# --- 3. ZONE D'UPLOAD MASSIF ---
st.subheader("📁 1. Bulk Upload (Drop everything here)")
bulk_files = st.file_uploader("Drag and drop all CVs and Transcripts", accept_multiple_files=True, type=['pdf', 'docx'])

if bulk_files:
    for f in bulk_files:
        add_file_to_registry(f)

# --- 4. ANALYSE ET AFFICHAGE DES PAIRES ---
st.divider()
st.subheader("🔍 2. Pairing Analysis & Fixes")

matched_list = []
incomplete_list = []

# On analyse le registre
for fid in sorted(st.session_state.upload_registry.keys()):
    docs = st.session_state.upload_registry[fid]
    if docs["cv"] and docs["tr"]:
        matched_list.append({
            "ID": fid,
            "CV File": docs["cv"].name,
            "Transcript File": docs["tr"].name,
            "cv_obj": docs["cv"],
            "tr_obj": docs["tr"]
        })
    else:
        incomplete_list.append(fid)

# --- AFFICHAGE DES COMPLETS ---
if matched_list:
    st.success(f"✅ {len(matched_list)} complete pairs ready.")
    st.table(pd.DataFrame(matched_list)[["ID", "CV File", "Transcript File"]])
else:
    st.info("No complete pairs yet.")

# --- AFFICHAGE DES INCOMPLETS (AVEC BOUTONS DE FIX) ---
if incomplete_list:
    st.warning(f"⚠️ {len(incomplete_list)} candidates have missing files.")
    
    for fid in incomplete_list:
        docs = st.session_state.upload_registry[fid]
        col_id, col_status, col_fix = st.columns([1, 2, 3])
        
        with col_id:
            st.markdown(f"**ID: {fid}**")
        
        with col_status:
            if not docs["cv"]: st.error("❌ Missing CV")
            if not docs["tr"]: st.error("❌ Missing Transcript")
            
        with col_fix:
            label = "Upload CV" if not docs["cv"] else "Upload Transcript"
            # Un uploader spécifique pour ce candidat
            fix_file = st.file_uploader(f"Fix {fid} ({label})", type=['pdf', 'docx'], key=f"fix_{fid}_{label}")
            if fix_file:
                add_file_to_registry(fix_file)
                st.rerun()

# --- 5. ACTION FINALE ---
st.divider()
col_btn, col_clear = st.columns([1, 1])

with col_btn:
    if st.button(f"🚀 Start Processing {len(matched_list)} Candidates", type="primary", disabled=len(matched_list) == 0):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        for i, pair in enumerate(matched_list):
            status_text.text(f"Uploading {pair['ID']}...")
            status_code, response = upload_paired_documents(
                session_id, pair['cv_obj'], pair['tr_obj'], st.session_state.token
            )
            results.append({"ID": pair['ID'], "Status": "✅ Success" if status_code == 200 else "❌ Failed"})
            progress_bar.progress((i + 1) / len(matched_list))
        
        status_text.success("🏁 Batch processing complete!")
        st.balloons()
        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
        # Optionnel : vider le registre après succès
        # st.session_state.upload_registry = {}

with col_clear:
    if st.button("🗑️ Clear All Files"):
        st.session_state.upload_registry = {}
        st.rerun()