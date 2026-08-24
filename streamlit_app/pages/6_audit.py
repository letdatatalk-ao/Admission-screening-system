import streamlit as st
import pandas as pd
from utils.api_client import get_sessions, get_audit_logs
from utils.styles import apply_theme, institution_header, sidebar_nav, require_auth

st.set_page_config(page_title="Audit Trail — KU Screening", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
apply_theme()

st.markdown("""
<style>
.logrow { padding:11px 0; border-bottom:1px solid var(--color-divider); }
.logrow:hover { background:rgba(32,31,29,.03); }
.diff-table { margin:12px 0 4px 0; border:1px solid var(--color-divider); border-radius:4px; overflow:hidden; max-width:620px; }
.diff-head { display:grid; grid-template-columns:1.2fr 1fr 1fr; font-size:9.5px; letter-spacing:.16em;
    text-transform:uppercase; color:rgba(32,31,29,.45); padding:6px 12px; border-bottom:1px solid var(--color-divider); }
.diff-row { display:grid; grid-template-columns:1.2fr 1fr 1fr; font-size:12.5px; padding:6px 12px; }
.diff-row + .diff-row { border-top:1px solid var(--color-divider); }
.diff-before { text-decoration:line-through; color:rgba(32,31,29,.4); }
.diff-after { color:var(--color-accent-700); }
</style>
""", unsafe_allow_html=True)

sidebar_nav(current_page="pages/6_audit.py")
require_auth()

st.title("Register of Actions")
institution_header("Audit & Transparency")

# ── Session + filters ─────────────────────────────────────────────────────────
sessions = get_sessions(st.session_state.token)

if not sessions:
    st.warning("No active sessions found.")
    st.stop()

session_options = {s["name"]: s["id"] for s in sessions}
col_sess, col_filter, col_export = st.columns([2, 1.4, 1])
with col_sess:
    sel_session_name = st.selectbox("Session", list(session_options.keys()))
session_id = session_options[sel_session_name]

# ── Fetch audit logs ───────────────────────────────────────────────────────────
logs = get_audit_logs(session_id, st.session_state.token)

if not logs:
    st.info(f"No audit records found for session: {sel_session_name}")
    st.stop()

df_logs = pd.DataFrame(logs)
df_logs["occurred_dt"] = pd.to_datetime(df_logs["occurred_at"])

action_labels = {
    "UPLOAD_PAIRED_DOCS":     "Batch upload",
    "MANUAL_CORRECTION":      "Manual override",
    "COMPUTE_RANKING":        "Ranking generation",
    "VIEW_DOCUMENT":          "File access",
    "LOGIN":                  "User login",
    "PUBLICATION_CORRECTION": "Publication edited",
    "PUBLICATION_DELETED":    "Publication removed",
    "PUBLICATION_CREATED":    "Publication added",
}
df_logs["action_label"] = df_logs["action_type"].map(lambda x: action_labels.get(x, x))

with col_filter:
    all_actions = ["All actions"] + sorted(df_logs["action_label"].unique().tolist())
    selected_action = st.selectbox("Filter by action type", all_actions, label_visibility="collapsed")

df_view = df_logs if selected_action == "All actions" else df_logs[df_logs["action_label"] == selected_action]

with col_export:
    st.markdown("<div style='height:1.65rem'></div>", unsafe_allow_html=True)
    st.download_button(
        "Export register, CSV",
        data=df_logs.to_csv(index=False).encode("utf-8"),
        file_name=f"audit_trail_{sel_session_name}.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ── KPI ledger ─────────────────────────────────────────────────────────────────
manual_fixes = int(df_logs["action_type"].str.contains("CORRECTION|OVERRIDE", case=False, na=False).sum())
uploads      = int(df_logs["action_type"].str.contains("UPLOAD", case=False, na=False).sum())
rankings     = int((df_logs["action_type"] == "COMPUTE_RANKING").sum())
accesses     = int((df_logs["action_type"] == "VIEW_DOCUMENT").sum())

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total actions", len(df_logs))
k2.metric("Human corrections", manual_fixes)
k3.metric("Ranking runs", rankings)
k4.metric("Document batches", uploads)

st.markdown("---")

# ── Register, grouped by day, inline diff ─────────────────────────────────────
df_view = df_view.sort_values("occurred_dt", ascending=False)
df_view["date"] = df_view["occurred_dt"].dt.strftime("%d %B %Y")

for date, day_df in df_view.groupby("date", sort=False):
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin:18px 0 2px;">'
        f'<h6 style="margin:0;">{date}</h6>'
        f'<div style="flex:1;height:1px;background:var(--color-divider);"></div>'
        f'<span class="num" style="font-size:11px;color:rgba(32,31,29,.45);">{len(day_df)} entries</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    for _, row in day_df.iterrows():
        t = row["occurred_dt"].strftime("%H:%M:%S")
        user = row.get("user_id") or "system"
        target = f'{row.get("entity_type") or ""} · {str(row.get("entity_id") or "")[:8]}'

        diff_html = ""
        old_state = row.get("old_state") or {}
        new_state = row.get("new_state") or {}
        if isinstance(old_state, dict) and isinstance(new_state, dict):
            changed = [
                (k, old_state.get(k), v) for k, v in new_state.items()
                if k != "reason" and old_state.get(k) != v
            ]
            if changed:
                diff_rows = "".join(
                    f'<div class="diff-row"><span class="num">{k}</span>'
                    f'<span class="num diff-before">{"—" if before in (None, "") else before}</span>'
                    f'<span class="num diff-after">{after}</span></div>'
                    for k, before, after in changed[:8]
                )
                diff_html = (
                    '<div class="diff-table"><div class="diff-head">'
                    '<span>Field</span><span>Before</span><span>After</span></div>'
                    f'{diff_rows}</div>'
                )
        note = ""
        reason = new_state.get("reason") if isinstance(new_state, dict) else None
        if reason:
            note = f'<p style="font-size:12px;line-height:1.6;color:rgba(32,31,29,.62);margin:7px 0 0;max-width:70ch;">{reason}</p>'

        st.markdown(
            f'<div class="logrow">'
            f'<div style="display:flex;gap:16px;align-items:baseline;">'
            f'<span class="num" style="width:64px;flex:none;font-size:12.5px;color:rgba(32,31,29,.45);">{t}</span>'
            f'<span style="width:170px;flex:none;font-size:13.5px;">{row["action_label"]}</span>'
            f'<span style="flex:1;font-size:12.5px;color:rgba(32,31,29,.62);">{target}</span>'
            f'<span class="num" style="font-size:12px;color:rgba(32,31,29,.45);">{user}</span>'
            f'</div>{note}{diff_html}</div>',
            unsafe_allow_html=True,
        )

st.markdown("---")
st.markdown(
    f'<p class="num" style="font-size:12px;color:rgba(32,31,29,.45);">'
    f'{len(df_logs)} entries in this session. The register is append-only.</p>',
    unsafe_allow_html=True,
)
