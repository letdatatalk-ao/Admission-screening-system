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

st.title("Weighted Shortlist")
institution_header("Ranking & Scoring")

sessions = get_sessions(st.session_state.token)
if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_options = {s["name"]: s["id"] for s in sessions}
selected_session_name = st.selectbox("Admission Session", options=list(session_options.keys()))
session_id = session_options[selected_session_name]

st.markdown("---")

# ── Weight configuration ───────────────────────────────────────────────────────
st.markdown("###### The hundred points")
st.markdown(
    '<p style="font-family:\'Lora\',serif;font-size:0.82rem;line-height:1.6;'
    'color:rgba(32,31,29,.65);max-width:70ch;text-align:justify;margin-top:-0.4rem;">'
    "Each component takes a share of one hundred points. Move a slider and the rest of "
    "the page follows — the allocation rule, the remaining budget, and the shortlist "
    "below. Nothing is written to the audit log until the ranking is committed.</p>",
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns(3)
with col1:
    w_bsc      = st.slider("Bachelor academic",     0, 100, 15, 5,
                           help="BSc GPA (60%) + BSc university QS rank (40%)")
    w_msc      = st.slider("Master academic",       0, 100, 25, 5,
                           help="MSc GPA (60%) + MSc university QS rank (40%); absent MSc scores neutrally")
with col2:
    w_journals = st.slider("Journal publications",  0, 100, 30, 5,
                           help="Scopus percentile × author contribution, diminishing returns")
    w_confs    = st.slider("Conference publications", 0, 100, 20, 5,
                           help="CORE ranking × author contribution, diminishing returns")
with col3:
    w_research = st.slider("Research profile",      0, 100, 10, 5,
                           help="Doctorate held, work experience to 5 years, raw publication output")

total_w = w_bsc + w_msc + w_journals + w_confs + w_research
remaining = 100 - total_w

col_note, col_total = st.columns([3, 1])
with col_note:
    if total_w == 100:
        st.markdown(
            '<div style="padding-top:0.6rem;font-size:0.85rem;">Balanced. '
            '<span style="color:rgba(32,31,29,.5);">The ranking can be committed.</span></div>',
            unsafe_allow_html=True,
        )
    else:
        over = remaining < 0
        st.markdown(
            f'<div style="padding-top:0.6rem;font-size:0.85rem;color:var(--color-accent-700);">'
            f'{"Over budget by " + str(abs(remaining)) + " points." if over else str(remaining) + " points still unallocated."}'
            f'</div>',
            unsafe_allow_html=True,
        )
with col_total:
    st.markdown(
        f'<div style="text-align:right;font-family:\'Cormorant Garamond\',serif;font-size:1.7rem;">'
        f'{total_w} / 100</div>',
        unsafe_allow_html=True,
    )

# ── Weight breakdown visual — hairline segmented bar, opacity not hue ─────────
if total_w > 0:
    segments = [
        ("Bachelor",     w_bsc,      1.0),
        ("Master",       w_msc,      0.85),
        ("Journals",     w_journals, 0.65),
        ("Conferences",  w_confs,    0.45),
        ("Research",     w_research, 0.28),
    ]
    bar_html = '<div style="display:flex;height:4px;margin:6px 0 8px;">'
    labels_html = '<div style="display:flex;">'
    for label, w, opacity in segments:
        if w > 0:
            pct = w / total_w * 100
            bar_html += (
                f'<div style="width:{pct:.2f}%;background:var(--color-accent);opacity:{opacity};" '
                f'title="{label}: {w}%"></div>'
            )
            labels_html += (
                f'<div style="width:{pct:.2f}%;font-size:9.5px;padding-top:5px;color:rgba(32,31,29,.45);'
                f'overflow:hidden;white-space:nowrap;">{label if w >= 10 else ""}</div>'
            )
    bar_html += "</div>"
    labels_html += "</div>"
    st.markdown(bar_html + labels_html, unsafe_allow_html=True)

st.markdown("---")

col_name, col_btns = st.columns([2, 1.2])
with col_name:
    config_name = st.text_input("Configuration name, for the audit record",
                                 value=f"Config_{time.strftime('%Y%m%d_%H%M')}")
with col_btns:
    st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
    compute = st.button("Compute and commit", type="primary", disabled=(total_w != 100), use_container_width=True)

if compute:
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
st.markdown("###### Shortlist under the current weights")

ranking_data = get_latest_ranking_results(session_id, st.session_state.token)

if ranking_data and ranking_data.get("scores_snapshot"):
    df = pd.DataFrame(ranking_data["scores_snapshot"]).sort_values("rank")

    # Determine which score columns exist
    score_cols    = ["rank", "applicant_name", "final_score"]
    col_cfg       = {
        "rank":           "Rank",
        "applicant_name": "Candidate",
        "final_score":    st.column_config.NumberColumn("Composite", format="%.2f"),
    }

    for col, label, fmt in [
        ("bsc_academic",   "Bachelor",    "%.2f"),
        ("msc_academic",   "Master",      "%.2f"),
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
    with st.expander("Score breakdown by component"):
        chart_df = df[["applicant_name"] + [c for c in
            ["bsc_academic", "msc_academic", "journal_score", "conf_score", "research_score"]
            if c in df.columns]].set_index("applicant_name")
        st.bar_chart(chart_df, color="#b68235")

    # Summary statistics — figure ledger, same treatment as the dashboard
    with st.expander("Effect of this configuration"):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total", len(df))
        c2.metric("Average", f"{df['final_score'].mean():.1f}")
        c3.metric("Highest", f"{df['final_score'].max():.1f}")
        c4.metric("Needs Review", int(df["needs_review"].sum()) if "needs_review" in df.columns else 0)
        c5.metric("Spread", f"{df['final_score'].min():.0f}–{df['final_score'].max():.0f}")

    st.markdown("---")
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download shortlist, CSV",
        data=csv,
        file_name=f"ranking_{selected_session_name}.csv",
        mime="text/csv",
    )
else:
    st.info("No ranking has been computed yet for this session. Configure weights above and click Compute.")
