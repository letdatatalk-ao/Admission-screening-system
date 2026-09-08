import time
import streamlit as st
import pandas as pd
from utils.api_client import get_sessions, get_applicants, get_applicant_detail, create_session
from utils.styles import apply_theme, institution_header, sidebar_nav, require_auth, ku_favicon_path

st.set_page_config(page_title="Applicant Dashboard — KU Screening", page_icon=ku_favicon_path(), layout="wide", initial_sidebar_state="expanded")
apply_theme()

# Extra dashboard-specific styles — Classical: hairline rows, no cards/shadows,
# state read as text (italic) rather than colour-coded chips.
st.markdown("""
<style>
.pipeline-row {
    border-bottom:1px solid var(--color-divider);
    padding:0.68rem 0.25rem;
    display:flex;align-items:center;gap:0.9rem;
}
.pmark { display:inline-block;width:9px;height:9px;flex:none; }
.pmark-processing { border-radius:50%;border:1.5px solid var(--color-accent);background:var(--color-accent); }
.pmark-pending    { border-radius:50%;border:1.5px solid rgba(32,31,29,.45); }
.pmark-error      { border:1.5px solid var(--color-text);transform:rotate(45deg); }
/* Extraction card */
.ext-section {
    border-left:1px solid var(--color-divider);
    padding:0.2rem 0 0.2rem 0.9rem;margin-bottom:0.6rem;
}
.ext-label { font-size:0.62rem;letter-spacing:.14em;text-transform:uppercase;color:rgba(32,31,29,.48);font-family:'Lora',serif; }
.ext-value { font-family:'Cormorant Garamond',serif;font-size:1.15rem;color:var(--color-text);font-weight:600;margin-top:0.1rem; }
.ext-sub   { font-size:0.8rem;color:rgba(32,31,29,.68);font-family:'Lora',serif; }
.conf-bar-wrap { background:var(--color-divider);border-radius:0;height:2px;overflow:hidden; }
.conf-bar-fill { height:2px;border-radius:0; }
/* Publication row */
.pub-row {
    border-bottom:1px solid var(--color-divider);
    padding:0.7rem 0.1rem;
}
</style>
""", unsafe_allow_html=True)

sidebar_nav(current_page="pages/2_dashboard.py")
require_auth()

st.title("Applicant Dashboard")
institution_header("Pipeline Monitor & Extraction Results")

# ── Session selection / creation ───────────────────────────────────────────────
sessions = get_sessions(st.session_state.token)

if not sessions:
    st.warning("No evaluation sessions exist yet.")
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

session_dict = {s["name"]: s["id"] for s in sessions}
col_s, col_r = st.columns([4, 1])
with col_s:
    selected_session = st.selectbox("Admission Session", list(session_dict.keys()), label_visibility="collapsed")
with col_r:
    if st.button("Refresh now", type="secondary", use_container_width=True):
        st.rerun()

session_id = session_dict[selected_session]

# ── Fetch applicants ───────────────────────────────────────────────────────────
status_code, applicants = get_applicants(session_id, st.session_state.token)

if status_code != 200:
    st.error("Unable to reach the backend API. Check the connection.")
    st.stop()

if not applicants:
    st.info("No candidates uploaded yet. Go to Document Upload to add CV and transcript pairs.")
    st.stop()

df = pd.DataFrame(applicants)

# Counts
total      = len(df)
n_proc     = int((df["status"] == "processed").sum())
n_running  = int((df["status"] == "processing").sum())
n_pending  = int((df["status"] == "pending").sum())
n_error    = int((df["status"] == "error").sum())
# "failed" = retries exhausted (terminal) — distinct from "error" (still
# retryable, retry_count < 5). Previously not counted anywhere on this
# dashboard, so candidates that permanently failed extraction were invisible.
n_failed   = int((df["status"] == "failed").sum())
n_review   = int(df["needs_human_review"].sum()) if "needs_human_review" in df.columns else 0
n_active   = n_running + n_pending

# ── KPI strip ──────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.metric("Total",       total)
k2.metric("Processed",   n_proc)
k3.metric("Processing",  n_running)
k4.metric("Pending",     n_pending)
k5.metric("Errors",      n_error)
k6.metric("Failed",      n_failed)
k7.metric("Need Review", n_review)

# Global progress bar
if total > 0:
    pct = n_proc / total
    st.markdown(
        f"""<div style="margin:0.6rem 0 1.2rem;display:flex;align-items:center;gap:14px;">
            <div style="flex:1;height:2px;background:var(--color-divider);position:relative;">
                <div style="position:absolute;left:0;top:0;width:{pct*100:.1f}%;height:2px;
                            background:var(--color-accent);"></div>
            </div>
            <div class="num" style="font-size:0.72rem;color:rgba(32,31,29,.55);white-space:nowrap;">
                {n_proc} of {total} extracted &middot; {pct*100:.0f}%
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: LIVE PIPELINE MONITOR
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Live Pipeline Monitor")

active_df = df[df["status"].isin(["pending", "processing", "error"])].copy()

if active_df.empty and n_proc == total:
    st.success(f"All {total} candidate(s) processed successfully.")
elif active_df.empty:
    st.info("No candidates currently in the pipeline.")
else:
    # Auto-refresh banner
    countdown_slot = st.empty()
    countdown_slot.info(
        f"**{n_active} candidate(s) in pipeline** — page will auto-refresh in 5 seconds. "
        f"Processing: {n_running} &nbsp;|&nbsp; Pending: {n_pending} &nbsp;|&nbsp; Errors: {n_error}"
    )

    # Per-candidate status rows — state read as italic text, not colour-coded chips
    for _, row in active_df.iterrows():
        status = row.get("status", "pending")
        name   = row.get("full_name") or row.get("application_ref") or "Unknown"
        ref    = row.get("application_ref", "")

        if status == "processing":
            mark  = '<span class="pmark pmark-processing"></span>'
            label = '<span style="font-style:italic;font-size:0.85rem;">Extracting with AI</span>'
        elif status == "pending":
            mark  = '<span class="pmark pmark-pending"></span>'
            label = '<span style="font-style:italic;font-size:0.85rem;">Queued</span>'
        else:  # error
            mark  = '<span class="pmark pmark-error"></span>'
            err   = str(row.get("last_error", ""))[:80] if "last_error" in row else ""
            label = '<span style="font-style:italic;font-size:0.85rem;">Retrying</span>' + (
                f' <span style="font-size:0.76rem;color:rgba(32,31,29,.5);">— {err}</span>' if err else ""
            )

        retry = int(row.get("retry_count", 0)) if "retry_count" in row.index else 0
        st.markdown(
            f'<div class="pipeline-row">'
            f'{mark}'
            f'<div style="flex:1;min-width:0;">'
            f'  <div style="font-size:0.9rem;">{name}</div>'
            f'  <div class="num" style="font-size:0.7rem;color:rgba(32,31,29,.45);">{ref}</div>'
            f'</div>'
            f'<div style="text-align:right;max-width:60%;">{label}'
            f'  {"&nbsp; <span class=\"num\" style=\"font-size:0.72rem;color:rgba(32,31,29,.45);\">attempt " + str(retry) + " of 5</span>" if retry > 0 else ""}'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    # Auto-refresh after 5 s
    time.sleep(5)
    st.rerun()

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: CANDIDATES TABLE WITH FILTERS
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Candidate List")

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    status_filter = st.multiselect(
        "Status", options=df["status"].unique().tolist(),
        default=df["status"].unique().tolist(),
    )
with col_f2:
    review_only = st.checkbox("Review-flagged only")
with col_f3:
    hide_no_msc = st.checkbox("Hide candidates without MSc")

df_filt = df[df["status"].isin(status_filter)].copy()
if review_only:
    df_filt = df_filt[df_filt["needs_human_review"] == True]
if hide_no_msc and "msc_absent" in df_filt.columns:
    df_filt = df_filt[df_filt["msc_absent"] == False]

display_map = {
    "last_rank":            "Rank",
    "last_composite_score": "Score",
    "full_name":            "Full Name",
    "nationality":          "Nationality",
    "status":               "Status",
    "bsc_uni_name":         "BSc University",
    "bsc_gpa_normalised":   "BSc GPA",
    "msc_absent":           "No MSc",
    "msc_uni_name":         "MSc University",
    "msc_gpa_normalised":   "MSc GPA",
    "pub_count":            "Pubs",
    "global_confidence":    "AI Conf.",
    "model_used":           "Model",
    "needs_human_review":   "Review?",
}
existing = [c for c in display_map if c in df_filt.columns]
df_show  = df_filt[existing].rename(columns=display_map)

st.dataframe(
    df_show,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Rank":    st.column_config.NumberColumn(format="%d"),
        "Score":   st.column_config.NumberColumn(format="%.2f"),
        "BSc GPA": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.3f"),
        "MSc GPA": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.3f"),
        "AI Conf.":st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.0%"),
        "Pubs":    st.column_config.NumberColumn(format="%d"),
    },
)
st.caption(f"{len(df_show)} candidate(s) shown · {n_proc} processed · {n_active} in pipeline")

col_dl, _ = st.columns([1, 3])
with col_dl:
    st.download_button(
        "Export CSV", data=df_show.to_csv(index=False).encode("utf-8"),
        file_name=f"dashboard_{selected_session}.csv", mime="text/csv",
    )

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: EXTRACTION RESULTS INSPECTOR
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Extraction Results Inspector")
st.caption("Select any processed candidate to view the full AI extraction result.")

processed_df = df[df["status"] == "processed"]

if processed_df.empty:
    st.info("No processed candidates yet. The pipeline must complete before extraction results appear here.")
    st.stop()

# Build candidate selector
name_map = {}
for _, row in processed_df.iterrows():
    label = f"{row.get('full_name') or 'Unknown'} — {row.get('application_ref','')}"
    name_map[label] = row["id"]

selected_label = st.selectbox("Candidate", list(name_map.keys()), key="inspector_select")
applicant_id   = name_map[selected_label]

detail = get_applicant_detail(applicant_id, st.session_state.token)

if not detail:
    st.error("Could not load candidate details from the API.")
    st.stop()

metrics = detail.get("metrics") or {}
pubs    = detail.get("publications") or []
conf    = float(metrics.get("global_confidence") or 0)

# ── Confidence banner ──────────────────────────────────────────────────────────
if conf >= 0.80:
    conf_color, conf_label = "var(--color-text)", "High confidence"
elif conf >= 0.60:
    conf_color, conf_label = "var(--color-accent-700)", "Medium confidence"
else:
    conf_color, conf_label = "var(--color-accent-700)", "Low confidence — review recommended"

st.markdown(
    f"""<div style="border-top:1px solid var(--color-divider);border-bottom:1px solid var(--color-divider);
                    padding:0.9rem 0.1rem;margin-bottom:1rem;display:flex;
                    align-items:center;gap:1rem;">
        <div style="flex:1;">
            <div class="ext-label" style="margin-bottom:5px;">AI Extraction Confidence</div>
            <div class="conf-bar-wrap" style="width:100%;">
                <div class="conf-bar-fill" style="width:{conf*100:.1f}%;background:{conf_color};"></div>
            </div>
        </div>
        <div class="num" style="font-family:'Cormorant Garamond',serif;font-size:1.6rem;color:{conf_color};min-width:4rem;text-align:right;">
            {conf*100:.0f}%
        </div>
        <div style="font-size:0.82rem;color:{conf_color};min-width:10rem;font-family:'Lora',serif;">{conf_label}</div>
    </div>""",
    unsafe_allow_html=True,
)

# ── Four-column layout: identity / BSc / MSc / PhD+Research ──────────────────
col_id, col_bsc, col_msc, col_phd = st.columns(4)

# Identity
with col_id:
    st.markdown("**Identity**")
    phone_val   = detail.get("phone") or metrics.get("phone") or "—"
    linkedin_val = detail.get("linkedin") or metrics.get("linkedin") or "—"
    st.markdown(
        f'<div class="ext-section">'
        f'<div class="ext-label">Full Name</div>'
        f'<div class="ext-value">{detail.get("full_name") or "—"}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Email</div>'
        f'<div class="ext-sub">{detail.get("email") or "—"}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Nationality</div>'
        f'<div class="ext-sub">{detail.get("nationality") or "—"}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Phone</div>'
        f'<div class="ext-sub">{phone_val}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">LinkedIn</div>'
        f'<div class="ext-sub" style="word-break:break-all;">{linkedin_val}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Model Used</div>'
        f'<div class="ext-sub">{metrics.get("model_used") or "—"}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if detail.get("needs_human_review"):
        st.warning("Flagged for human review")

# BSc
with col_bsc:
    st.markdown("**Bachelor (BSc)**")
    bsc_norm    = float(metrics.get("bsc_gpa_normalised") or 0)
    bsc_raw     = metrics.get("bsc_gpa_raw")
    bsc_scl     = metrics.get("bsc_gpa_scale")
    bsc_qs      = metrics.get("bsc_qs_rank")
    bsc_field   = metrics.get("bsc_field") or "—"
    bsc_country = metrics.get("bsc_country") or "—"
    bsc_year    = metrics.get("bsc_year") or "—"
    gpa_str     = f"{bsc_raw}/{bsc_scl}" if bsc_raw else "—"
    st.markdown(
        f'<div class="ext-section">'
        f'<div class="ext-label">University</div>'
        f'<div class="ext-value">{metrics.get("bsc_uni_name") or "—"}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Field · Country · Year</div>'
        f'<div class="ext-sub">{bsc_field} · {bsc_country} · {bsc_year}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">QS World Rank</div>'
        f'<div class="ext-sub">{"#" + str(bsc_qs) if bsc_qs else "Not ranked"}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">GPA</div>'
        f'<div class="ext-sub">{gpa_str}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Normalised GPA (0–1)</div>'
        f'<div class="conf-bar-wrap" style="margin-top:4px;">'
        f'  <div class="conf-bar-fill" style="width:{bsc_norm*100:.1f}%;background:var(--color-accent);"></div>'
        f'</div>'
        f'<div class="ext-sub" style="text-align:right;">{bsc_norm:.3f}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# MSc
with col_msc:
    st.markdown("**Master (MSc)**")
    if metrics.get("msc_absent"):
        st.markdown(
            '<div class="ext-section"><div class="ext-sub" style="color:rgba(32,31,29,.5);">'
            'No Master degree recorded.</div></div>',
            unsafe_allow_html=True,
        )
    else:
        msc_norm    = float(metrics.get("msc_gpa_normalised") or 0)
        msc_raw     = metrics.get("msc_gpa_raw")
        msc_scl     = metrics.get("msc_gpa_scale")
        msc_qs      = metrics.get("msc_qs_rank")
        msc_field   = metrics.get("msc_field") or "—"
        msc_country = metrics.get("msc_country") or "—"
        msc_year    = metrics.get("msc_year") or "—"
        gpa_str     = f"{msc_raw}/{msc_scl}" if msc_raw else "—"
        st.markdown(
            f'<div class="ext-section">'
            f'<div class="ext-label">University</div>'
            f'<div class="ext-value">{metrics.get("msc_uni_name") or "—"}</div>'
            f'<div class="ext-label" style="margin-top:.5rem;">Field · Country · Year</div>'
            f'<div class="ext-sub">{msc_field} · {msc_country} · {msc_year}</div>'
            f'<div class="ext-label" style="margin-top:.5rem;">QS World Rank</div>'
            f'<div class="ext-sub">{"#" + str(msc_qs) if msc_qs else "Not ranked"}</div>'
            f'<div class="ext-label" style="margin-top:.5rem;">GPA</div>'
            f'<div class="ext-sub">{gpa_str}</div>'
            f'<div class="ext-label" style="margin-top:.5rem;">Normalised GPA (0–1)</div>'
            f'<div class="conf-bar-wrap" style="margin-top:4px;">'
            f'  <div class="conf-bar-fill" style="width:{msc_norm*100:.1f}%;background:var(--color-accent);"></div>'
            f'</div>'
            f'<div class="ext-sub" style="text-align:right;">{msc_norm:.3f}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# PhD + Test scores + Research
with col_phd:
    st.markdown("**PhD & Research Profile**")
    phd_uni  = metrics.get("phd_uni_name") or "—"
    phd_fld  = metrics.get("phd_field") or "—"
    phd_yr   = metrics.get("phd_year") or "—"
    phd_qs   = metrics.get("phd_qs_rank")
    work_yrs = metrics.get("work_exp_years")
    ielts    = metrics.get("ielts_score")
    toefl    = metrics.get("toefl_score")
    gre_v    = metrics.get("gre_verbal")
    gre_q    = metrics.get("gre_quant")
    gre_a    = metrics.get("gre_awa")

    # Research interests
    interests = metrics.get("research_interests") or []
    interests_str = " · ".join(interests[:4]) if interests else "—"
    awards = metrics.get("awards") or []
    awards_str = "; ".join(awards[:3]) if awards else "—"

    gre_str = (f"V{gre_v}/Q{gre_q}/AWA{gre_a}"
               if any(x for x in [gre_v, gre_q, gre_a]) else "—")
    lang_str = " · ".join(filter(None, [
        f"IELTS {ielts}" if ielts else "",
        f"TOEFL {toefl}" if toefl else "",
    ])) or "—"

    st.markdown(
        f'<div class="ext-section">'
        f'<div class="ext-label">PhD University</div>'
        f'<div class="ext-value">{phd_uni}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Field · Year · QS</div>'
        f'<div class="ext-sub">{phd_fld} · {phd_yr}{"  #" + str(phd_qs) if phd_qs else ""}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Work Experience</div>'
        f'<div class="ext-sub">{str(work_yrs) + " yrs" if work_yrs else "—"}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">GRE</div>'
        f'<div class="ext-sub">{gre_str}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Language Tests</div>'
        f'<div class="ext-sub">{lang_str}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Research Interests</div>'
        f'<div class="ext-sub">{interests_str}</div>'
        f'<div class="ext-label" style="margin-top:.5rem;">Awards</div>'
        f'<div class="ext-sub">{awards_str}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Publications ───────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"**Publications &nbsp;·&nbsp; {len(pubs)} record(s)**")

if not pubs:
    st.info("No publications were extracted. Use Review & Validate to add records manually.")
else:
    for pub in pubs:
        pub_type = pub.get("pub_type", "journal").capitalize()
        contrib  = float(pub.get("contribution_score") or 0)
        pos      = pub.get("author_position") or "?"
        tot      = pub.get("total_authors") or "?"
        first    = pos == 1 or pos == "1"

        st.markdown(
            f'<div class="pub-row">'
            f'  <div style="display:flex;justify-content:space-between;align-items:flex-start;">'
            f'    <div style="flex:1;margin-right:1rem;">'
            f'      <div style="font-size:0.92rem;">'
            f'        {pub.get("title") or "Untitled"}'
            f'      </div>'
            f'      <div class="num" style="font-size:0.76rem;color:rgba(32,31,29,.55);margin-top:2px;">'
            f'        {pub.get("venue_name") or "Unknown venue"} &nbsp;·&nbsp; {pub.get("year") or "N/A"}'
            f'      </div>'
            f'    </div>'
            f'    <div style="text-align:right;white-space:nowrap;">'
            f'      <span class="tag tag-outline">{pub_type}</span>'
            f'      {"&nbsp;<span class=\"tag tag-accent\">1st author</span>" if first else ""}'
            f'    </div>'
            f'  </div>'
            f'  <div style="margin-top:8px;display:flex;align-items:center;gap:0.6rem;">'
            f'    <div class="num" style="font-size:0.72rem;color:rgba(32,31,29,.5);">Author {pos}/{tot}</div>'
            f'    <div style="flex:1;background:var(--color-divider);height:2px;">'
            f'      <div style="width:{contrib*100:.0f}%;height:2px;background:var(--color-accent);"></div>'
            f'    </div>'
            f'    <div class="num" style="font-size:0.72rem;color:rgba(32,31,29,.5);">Contribution {contrib*100:.0f}%</div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )
