import re
import streamlit as st
import pandas as pd
from pathlib import Path
from utils.api_client import upload_paired_documents, get_sessions, create_session
from utils.styles import apply_theme, institution_header, sidebar_nav, require_auth

st.set_page_config(page_title="Document Upload — KU Screening", layout="wide", initial_sidebar_state="expanded")
apply_theme()
sidebar_nav(current_page="pages/1_upload.py")
require_auth()

st.title("Document Upload")
institution_header("Batch Ingest")

# ── Session selection / creation ───────────────────────────────────────────────
sessions = get_sessions(st.session_state.token)

if not sessions:
    st.warning("No evaluation sessions exist yet. Create one below to begin.")
    with st.expander("Create New Admission Session", expanded=True):
        with st.form("create_session_form"):
            col_n, col_y, col_q = st.columns(3)
            s_name    = col_n.text_input("Session Name", placeholder="Fall 2025 Admissions")
            s_year    = col_y.text_input("Academic Year", placeholder="2025-2026")
            s_qs_year = col_q.number_input("QS Rankings Year", value=2025, min_value=2020, max_value=2030)
            if st.form_submit_button("Create Session", type="primary"):
                if not s_name or not s_year:
                    st.error("Session name and academic year are required.")
                else:
                    code, data = create_session(s_name, s_year, int(s_qs_year), st.session_state.token)
                    if code in (200, 201):
                        st.success(f"Session '{s_name}' created.")
                        st.rerun()
                    else:
                        st.error(f"Failed: {data.get('detail', 'Unknown error')}")
    st.stop()

session_options = {s["name"]: s["id"] for s in sessions}
col_sess, col_new = st.columns([3, 1])
with col_sess:
    selected_session = col_sess.selectbox("Admission Session", options=list(session_options.keys()))
with col_new:
    st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
    if st.button("New Session", type="secondary"):
        st.session_state._show_new_session = True

if st.session_state.get("_show_new_session"):
    with st.expander("Create New Admission Session", expanded=True):
        with st.form("create_session_form2"):
            col_n, col_y, col_q = st.columns(3)
            s_name    = col_n.text_input("Session Name", placeholder="Spring 2026 Admissions")
            s_year    = col_y.text_input("Academic Year", placeholder="2026-2027")
            s_qs_year = col_q.number_input("QS Rankings Year", value=2025, min_value=2020, max_value=2030)
            col_s, col_c = st.columns(2)
            if col_s.form_submit_button("Create", type="primary"):
                if not s_name or not s_year:
                    st.error("Name and academic year are required.")
                else:
                    code, data = create_session(s_name, s_year, int(s_qs_year), st.session_state.token)
                    if code in (200, 201):
                        st.success(f"Session '{s_name}' created.")
                        st.session_state._show_new_session = False
                        st.rerun()
                    else:
                        st.error(f"Failed: {data.get('detail', 'Unknown error')}")
            if col_c.form_submit_button("Cancel"):
                st.session_state._show_new_session = False
                st.rerun()

session_id = session_options[selected_session]

# ── Upload registry ────────────────────────────────────────────────────────────
if "upload_registry" not in st.session_state:
    st.session_state.upload_registry = {}


def _extract_applicant_id(filename: str) -> str:
    """Extract the numeric applicant ID prefix from a filename."""
    stem = Path(filename).stem
    m = re.match(r'^(\d+)', stem.replace("_", " ").replace("-", " ").strip())
    return m.group(1) if m else stem


def _classify_file(filename: str) -> str:
    """Classify a file as 'cv' or 'tr' (transcript) based on its name."""
    upper = filename.upper()
    if re.search(r'(^|\s|_)(CV)(\s|_|\.|$)', upper):
        return "cv"
    if re.search(r'(^|\s|_)(T|TRANSCRIPT|TR)(\s|_|\.|$)', upper):
        return "tr"
    if "CURRICULUM" in upper or "RESUME" in upper:
        return "cv"
    if "TRANSCRIPT" in upper or "GRADE" in upper or "RESULT" in upper:
        return "tr"
    return "unknown"


def add_file_to_registry(uploaded_file):
    if uploaded_file is None:
        return
    fid   = _extract_applicant_id(uploaded_file.name)
    ftype = _classify_file(uploaded_file.name)
    if fid not in st.session_state.upload_registry:
        st.session_state.upload_registry[fid] = {"cv": None, "tr": None}
    if ftype in ("cv", "tr"):
        st.session_state.upload_registry[fid][ftype] = uploaded_file


st.markdown("---")

# ── Step 1: Bulk upload ────────────────────────────────────────────────────────
st.subheader("Step 1 — Upload Documents")
st.caption(
    "Drop all CV and transcript files here. Files are paired by numeric applicant ID prefix. "
    "Naming convention: `507267368 CV.pdf` + `507267368 T.pdf`"
)

bulk_files = st.file_uploader(
    "Drag and drop all documents (PDF, DOCX, or scanned image)",
    accept_multiple_files=True,
    # Must match backend ALLOWED_EXTENSIONS (backend/app/api/v1/upload.py) —
    # the pipeline has an OCR path built for scanned image uploads, but this
    # uploader was rejecting them before they ever reached the backend.
    type=["pdf", "docx", "png", "jpg", "jpeg", "tiff", "tif"],
)
if bulk_files:
    for f in bulk_files:
        add_file_to_registry(f)

# ── Step 2: Pairing analysis ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("Step 2 — Pairing Analysis")

matched_list, incomplete_list, unknown_list = [], [], []

for fid in sorted(st.session_state.upload_registry.keys()):
    docs = st.session_state.upload_registry[fid]
    if docs["cv"] and docs["tr"]:
        matched_list.append({"ID": fid, "CV File": docs["cv"].name,
                              "Transcript File": docs["tr"].name,
                              "cv_obj": docs["cv"], "tr_obj": docs["tr"]})
    elif docs["cv"] or docs["tr"]:
        incomplete_list.append(fid)

if matched_list:
    st.success(f"{len(matched_list)} complete pair(s) ready for processing.")
    st.dataframe(
        pd.DataFrame(matched_list)[["ID", "CV File", "Transcript File"]],
        use_container_width=True,
        hide_index=True,
    )

if incomplete_list:
    st.warning(f"{len(incomplete_list)} candidate(s) are missing one document.")
    for fid in incomplete_list:
        docs = st.session_state.upload_registry[fid]
        col_id, col_status, col_fix = st.columns([1, 2, 3])
        col_id.markdown(f"**{fid}**")
        if not docs["cv"]:
            col_status.error("CV missing")
        if not docs["tr"]:
            col_status.error("Transcript missing")
        label = "Upload CV" if not docs["cv"] else "Upload Transcript"
        fix_file = col_fix.file_uploader(
            f"{fid} — {label}", type=["pdf", "docx", "png", "jpg", "jpeg", "tiff", "tif"], key=f"fix_{fid}"
        )
        if fix_file:
            add_file_to_registry(fix_file)
            st.rerun()

if not matched_list and not incomplete_list:
    st.info("No files uploaded yet. Use the uploader above to add CV and transcript pairs.")

# ── Step 3: Submit ─────────────────────────────────────────────────────────────
st.markdown("---")
col_btn, col_clear = st.columns([2, 1])

with col_btn:
    if st.button(
        f"Process {len(matched_list)} Candidate(s)",
        type="primary",
        disabled=len(matched_list) == 0,
    ):
        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        results, errors = [], 0

        for i, pair in enumerate(matched_list):
            status_placeholder.info(f"Uploading {pair['ID']} ({i + 1} / {len(matched_list)})...")
            code, resp = upload_paired_documents(
                session_id, pair["cv_obj"], pair["tr_obj"], st.session_state.token
            )
            ok = code == 200
            if not ok:
                errors += 1
            results.append({
                "Applicant ID": pair["ID"],
                "Status":       "Queued for AI processing" if ok else f"Failed ({resp.get('detail','')})",
            })
            progress_bar.progress((i + 1) / len(matched_list))

        if errors == 0:
            status_placeholder.success(
                f"All {len(matched_list)} candidate(s) queued. "
                "Navigate to the Dashboard to monitor extraction progress."
            )
        else:
            status_placeholder.warning(f"{errors} upload(s) failed. See details below.")

        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
        st.session_state.upload_registry = {}

with col_clear:
    if st.button("Clear All Files", type="secondary", disabled=len(st.session_state.upload_registry) == 0):
        st.session_state.upload_registry = {}
        st.rerun()
