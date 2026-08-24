import streamlit as st
import pandas as pd
import time
from utils.api_client import (
    get_sessions,
    create_ranking_config,
    trigger_ranking_computation,
    get_latest_ranking_results,
)
from utils.styles import apply_theme, institution_header, sidebar_nav, require_auth

st.set_page_config(page_title="Ranking Engine — KU Screening", page_icon="🏆", layout="wide", initial_sidebar_state="expanded")
apply_theme()
sidebar_nav(current_page="pages/4_ranking.py")
require_auth()

st.title("Ranking and Scoring Engine")
institution_header("Weighted Shortlist Computation")

sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_options = {s["name"]: s["id"] for s in sessions}
selected_session_name = st.selectbox("Admission Session", options=list(session_options.keys()))
session_id = session_options[selected_session_name]

st.markdown("---")

# ── Weight configuration ───────────────────────────────────────────────────────
st.subheader("Weight Configuration")
st.caption(
    "Assign percentage weights to each scoring component. Total must equal **100%**. "
    "Adjust sliders — remaining budget shows in real time."
)

col1, col2, col3 = st.columns(3)
with col1:
    w_bsc      = st.slider("Bachelor Academic (%)",     0, 100, 15, 5,
                           help="BSc GPA (60%) + BSc university QS rank (40%)")
    w_msc      = st.slider("Master Academic (%)",       0, 100, 25, 5,
                           help="MSc GPA (60%) + MSc university QS rank (40%)")
with col2:
    w_journals = st.slider("Journal Publications (%)",  0, 100, 30, 5,
                           help="Scopus percentile × author contribution, diminishing returns")
    w_confs    = st.slider("Conference Publications (%)", 0, 100, 20, 5,
                           help="CORE score × author contribution, diminishing returns")
with col3:
    w_research = st.slider("Research Profile (%)",      0, 100, 10, 5,
                           help="PhD degree (50 pts) + work experience (up to 20 pts) + publication count (up to 30 pts)")

total_w = w_bsc + w_msc + w_journals + w_confs + w_research
remaining = 100 - total_w

if total_w != 100:
    st.warning(
        f"Current total: **{total_w}%** — "
        f"{'over by' if remaining < 0 else 'remaining'} **{abs(remaining)}%**. "
        "Adjust sliders to reach exactly 100%."
    )
else:
    st.success("Weight allocation is balanced at **100%**.")

# ── Weight breakdown visual ────────────────────────────────────────────────────
if total_w > 0:
    segments = [
        ("BSc", w_bsc, "#1a2744"),
        ("MSc", w_msc, "#3b5998"),
        ("Journals", w_journals, "#c8a028"),
        ("Conferences", w_confs, "#7c3aed"),
        ("Research", w_research, "#10b981"),
    ]
    bar_html = '<div style="display:flex;height:18px;border-radius:4px;overflow:hidden;margin:0.5rem 0 1rem;">'
    for label, w, color in segments:
        if w > 0:
            bar_html += (
                f'<div style="width:{w/total_w*100:.1f}%;background:{color};'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-size:0.65rem;color:#fff;font-weight:600;" title="{label}: {w}%">'
                f'{"" if w < 8 else label}</div>'
            )
    bar_html += "</div>"
    st.markdown(bar_html, unsafe_allow_html=True)

st.markdown("---")

config_name = st.text_input("Configuration Name (optional)",
                             value=f"Config_{time.strftime('%Y%m%d_%H%M')}",
                             help="Give this weight set a meaningful name for audit purposes")

if st.button("Compute Official Ranking", type="primary", disabled=(total_w != 100)):
    weights = {
        "w_bsc":          float(w_bsc),
        "w_msc":          float(w_msc),
        "w_journals":     float(w_journals),
        "w_conferences":  float(w_confs),
        "w_research":     float(w_research),
    }

    with st.spinner("Saving weight configuration..."):
        config = create_ranking_config(session_id, config_name or f"Config_{time.strftime('%H%M%S')}",
                                       weights, st.session_state.token)

    if config:
        config_id = config["id"]
        with st.spinner("Computing scores for all candidates..."):
            http_status, res = trigger_ranking_computation(session_id, config_id, st.session_state.token)

        if http_status == 200:
            st.success("Ranking computed successfully.")
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"Computation failed ({http_status}). Check backend logs for details.")
    else:
        st.error("Failed to save ranking configuration.")

# ── Latest results ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Latest Ranking Results")

ranking_data = get_latest_ranking_results(session_id, st.session_state.token)

if ranking_data and ranking_data.get("scores_snapshot"):
    df = pd.DataFrame(ranking_data["scores_snapshot"]).sort_values("rank")

    # Determine which score columns exist
    score_cols    = ["rank", "applicant_name", "final_score"]
    col_cfg       = {
        "rank":           "Rank",
        "applicant_name": "Candidate",
        "final_score":    st.column_config.NumberColumn("Final Score", format="%.2f"),
    }

    for col, label, fmt in [
        ("bsc_academic",   "BSc Score",   "%.2f"),
        ("msc_academic",   "MSc Score",   "%.2f"),
        ("journal_score",  "Journals",    "%.2f"),
        ("conf_score",     "Conferences", "%.2f"),
        ("research_score", "Research",    "%.2f"),
    ]:
        if col in df.columns:
            score_cols.append(col)
            col_cfg[col] = st.column_config.NumberColumn(label, format=fmt)

    if "needs_review" in df.columns:
        score_cols.append("needs_review")
        col_cfg["needs_review"] = "Review?"

    st.dataframe(
        df[[c for c in score_cols if c in df.columns]],
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
    )

    # Score breakdown expander
    with st.expander("Score Breakdown by Component"):
        chart_df = df[["applicant_name"] + [c for c in
            ["bsc_academic", "msc_academic", "journal_score", "conf_score", "research_score"]
            if c in df.columns]].set_index("applicant_name")
        st.bar_chart(chart_df)

    # Summary statistics
    with st.expander("Summary Statistics"):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total", len(df))
        c2.metric("Average Score", f"{df['final_score'].mean():.1f}")
        c3.metric("Highest Score", f"{df['final_score'].max():.1f}")
        c4.metric("Needs Review", int(df["needs_review"].sum()) if "needs_review" in df.columns else 0)
        c5.metric("Score Range",
                  f"{df['final_score'].min():.0f}–{df['final_score'].max():.0f}")

    st.markdown("---")
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Official Shortlist (CSV)",
        data=csv,
        file_name=f"ranking_{selected_session_name}.csv",
        mime="text/csv",
    )
else:
    st.info("No ranking has been computed yet for this session. Configure weights above and click Compute.")
