# app.py
from __future__ import annotations
import streamlit as st
from config import ACTIVE_PROJECTS, PERIOD_LABELS
from youtrack_queries import get_task_counts_by_type_and_state
from youtrack_queries import yt_issues_url
import plotly.graph_objects as go
from datetime import date
from youtrack_queries import get_monthly_task_counts_by_type
import calendar
from chart_theme import apply_chart_theme
from youtrack_queries import get_deployments_on_live
import os
from datetime import datetime




st.set_page_config(page_title="YouTrack Dashboard", layout="wide")


with open("styles.css", "r", encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


#______________________Section 1 STARTS___________________________________________________________________
#  Header
st.markdown('<h1 class="heading--page">YouTrack Dashboard</h1>', unsafe_allow_html=True)

# ---- Defaults from session (persist last submitted) ----
_default_project = st.session_state.get("selected_project", ACTIVE_PROJECTS[0])
_default_period_key = st.session_state.get("selected_period_key", list(PERIOD_LABELS.keys())[0])
_default_period_label = PERIOD_LABELS[_default_period_key]

# ---- Controls----
with st.form("filters_form", clear_on_submit=False):
    c1, c2, c3 = st.columns([1, 1, 5])
    with c1:
        st.markdown('<div class="label">Project</div>', unsafe_allow_html=True)
        project_choice = st.selectbox(
            "Project",
            ACTIVE_PROJECTS,
            index=ACTIVE_PROJECTS.index(_default_project),
            label_visibility="collapsed",
            key="project_select",
        )
    with c2:
        st.markdown('<div class="label">Period</div>', unsafe_allow_html=True)
        labels = list(PERIOD_LABELS.values())
        keys = list(PERIOD_LABELS.keys())
        idx = labels.index(_default_period_label)
        selected_label = st.selectbox(
            "Period",
            labels,
            index=idx,
            label_visibility="collapsed",
            key="period_select",
        )
        period_key_choice = keys[labels.index(selected_label)]
    with c3:
        st.markdown('<div class="spacer-20"></div>', unsafe_allow_html=True)
        submitted = st.form_submit_button("Send")

    if submitted:
        st.session_state.selected_project = project_choice
        st.session_state.selected_period_key = period_key_choice
        st.session_state.filters_submitted = True

# ---- Gate the rest of the dashboard until user clicks Send ----
if not st.session_state.get("filters_submitted", False):
    st.markdown("""
    <div class="empty-hero">
      <div class="box">
        <div class="title">Load the Dashboard</div>
        <div class="sub">Choose a <b>Project</b> and <b>Period</b>, then click <b>Send</b> to fetch data.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Use last submitted filters
project = st.session_state["selected_project"]
period_key = st.session_state["selected_period_key"]

# Now that data will load, show note + separator
st.markdown('<div class="smallnote">*Summary is based on Task Created in Given Period</div>', unsafe_allow_html=True)
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# --- Fancy loader helper for the cards (status chip + shimmer cards) ---
def render_cards_loader(label: str, count: int = 6) -> str:
    head = (
        "<div class='chip chip--status'><div class='dot'></div>"
        f"<div>{label}</div></div>"
    )

    cards_html = []
    for _ in range(count):
        cards_html.append(
            "<div class='skel-card'>"
            "  <div class='h'></div>"
            "  <div class='line'></div>"
            "  <div class='line'></div>"
            "  <div class='line'></div>"
            "</div>"
        )
    return head + "<div class='skel-cards'>" + "".join(cards_html) + "</div>"

# Show loader immediately in a stable placeholder
sec1 = st.empty()
with sec1.container():
    st.markdown(render_cards_loader("Loading summary…"), unsafe_allow_html=True)

# Fetch while loader is visible
data = get_task_counts_by_type_and_state(period_key)
type_map = data.get("per_project", {}).get(project, {}) or {}

# Replace loader with real cards
sec1.empty()
with sec1.container():
    cards = ['<div class="row">']
    if not type_map:
        cards.append('<div class="muted">No tasks found for the selected Project/Period.</div>')
    else:
        for typ, states in sorted(type_map.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
            total = sum(states.values())

            # Per-state clickable lines
            state_lines = "<br>".join(
                f'-) <a class="state-link" href="{yt_issues_url(project, period_key, issue_type=typ, state=s)}" target="_blank">{s}: <span class="state-count">{n}</span></a>'
                for s, n in sorted(states.items(), key=lambda kv: (-kv[1], kv[0]))
            )

            # Type label clickable (links to all tasks of that type for period)
            type_href = yt_issues_url(project, period_key, issue_type=typ)
            cards.append(
                f"<div class='card'>"
                f"  <h4>"
                f"    <a class='chip-link type-label' href='{type_href}' target='_blank'>{typ}:</a>"
                f"    <span class='chip chip--count'>{total}</span>"
                f"  </h4>"
                f"  <div class='muted'>{state_lines}</div>"
                f"</div>"
            )
    cards.append("</div>")
    st.markdown("".join(cards), unsafe_allow_html=True)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
#______________________Section 1 ENDS_____________________________________________________________________




#______________________Section 2 STARTS___________________________________________________________________
st.markdown('<div class="mt-10"></div>', unsafe_allow_html=True)
st.markdown('<h2 class="heading--section">Tasks Created Per Month in Current Year (by Type)</h2>', unsafe_allow_html=True)

#loader
def render_chart_loader(label: str) -> str:
    head = (
        "<div class='chip chip--status'><div class='dot'></div>"
        f"<div>{label}</div></div>"
    )

    # 12 month placeholders (compact)
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    bars = "".join(f"<div class='skel-bar' title='{m}'></div>" for m in months)
    return head + "<div class='skel-chart'>" + bars + "</div>"

sec2 = st.empty()
with sec2.container():
    st.markdown(render_chart_loader("Loading monthly counts…"), unsafe_allow_html=True)

#Fetch while loader is visible
year = date.today().year
current_month = date.today().month
monthly_data = get_monthly_task_counts_by_type(project, year)  # YouTrack API call  :contentReference[oaicite:2]{index=2}

#Replace loader with final chart
sec2.empty()
with sec2.container():
    if not monthly_data:
        st.markdown('<div class="muted">No data available for this year.</div>', unsafe_allow_html=True)
    else:
        months = [f"{year}-{m:02d}" for m in range(1, current_month + 1)]
        month_labels = [calendar.month_abbr[m] for m in range(1, current_month + 1)]
        all_types = sorted({t for m in monthly_data.values() for t in m})

        # Fixed colors for common types + rotating fallback palette
        TYPE_COLORS = {
            "Bug": "#e74c3c",
            "New Requirement": "#0748B1",
            "Change Request": "#07B176",
        }
        PALETTE = ["#146f91", "#075066", "#9b59b6", "#f39c12", "#34495e", "#1abc9c", "#f38942", "#7f8c8d"]
        palette_idx = 0

        fig = go.Figure()
        for t in all_types:
            vals = [monthly_data.get(m, {}).get(t, 0) for m in months]
            labels = [str(v) if v > 0 else "" for v in vals]

            color = TYPE_COLORS.get(t)
            if not color:
                color = PALETTE[palette_idx % len(PALETTE)]
                palette_idx += 1

            fig.add_bar(
                name=t, x=month_labels, y=vals,
                text=labels, textposition="outside",
                marker_color=color, hoverinfo="skip", hovertemplate=None
            )

        fig.update_layout(
            barmode="group",
            xaxis=dict(type="category", categoryorder="array", categoryarray=month_labels),
            showlegend=True,
        )

        fig = apply_chart_theme(
            fig,
            show_bar_text=True,
            bar_text_color="#111",
            bar_text_size=11,
            height=320,
            margin_t=50,
            margin_b=0,
            legend_orientation="v",
            legend_x=1.02, legend_y=1, legend_xanchor="left", legend_yanchor="top",
        )

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
#______________________Section 2 ENDS_____________________________________________________________________



# ______________________ Section 3 STARTS ______________________________________


#loader
def render_section_loader(label: str) -> str:
    head = (
        "<div class='chip chip--status'><div class='dot'></div>"
        f"<div>{label}</div></div>"
    )

    header = "<div class='skel-head'>Preparing table…</div>"
    rows = []
    for _ in range(6):  # 6 preview rows
        cells = "".join("<div class='cell'></div>" for _ in range(7))
        rows.append(f"<div class='skel-row'>{cells}</div>")
    return head + "<div class='skel'>" + header + "".join(rows) + "</div>"

st.markdown('<div class="mt-10"></div>', unsafe_allow_html=True)
st.markdown('<h2 class="heading--section">Deployments</h2>', unsafe_allow_html=True)
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# Stable mount point + immediate custom loader
sec3 = st.empty()
with sec3.container():
    st.markdown(render_section_loader("Loading deployments…"), unsafe_allow_html=True)

#Run while loader is visible
resp = get_deployments_on_live(project, period_key, link_types={"relates","subtask"})
deployments = resp.get("deployments", []) or []

#Replace loader with final UI
sec3.empty()
with sec3.container():
    # Flatten rows and build quick stats
    rows = []
    type_counts = {}
    total_tasks = 0
    for dep in deployments:
        dep_id = dep.get("deployment_id")
        dep_due = dep.get("due_date")
        for li in dep.get("linked", []):
            total_tasks += 1
            t = (li.get("type") or "Unspecified").strip()
            type_counts[t] = type_counts.get(t, 0) + 1
            rows.append({
                "deployment_id": dep_id,
                "task_id": li.get("id"),
                "title": li.get("title") or "",
                "type": t,
                "state": li.get("state") or "",
                "created_on": li.get("created_on") or "",
                "deployed_on": dep_due or "",
            })

    # --- KPI strip (centered) ---
    def _pill(label, value):
        return f"<div class='kpi__pill'><b>{label}:</b> {value}</div>"

    preferred = [
        "Bug", "Change Request", "New Requirement", "Enhancement",
        "System Understanding", "Tech Task", "Exceptional Cases",
        "External Dependency", "End User Mistake",
    ]
    present_types = list(type_counts.keys())
    ordered = [t for t in preferred if t in present_types] + \
              sorted(t for t in present_types if t not in preferred)

    kpis = [
        _pill("Total Deployments", len(deployments)),
        _pill("Deployed Tasks", total_tasks),
    ]
    for t in ordered:
        kpis.append(_pill(t, type_counts.get(t, 0)))

    st.markdown("<div class='kpi'>" + "".join(kpis) + "</div>", unsafe_allow_html=True)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Build YouTrack links
    base = os.getenv("YOUTRACK_URL", "").rstrip("/")
    def issue_link(key: str) -> str:
        return f"{base}/issue/{key}" if (base and key) else "#"

    # Sort rows by deployed_on desc, then task_id
    def _parse_date(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            return datetime.min
    rows_sorted = sorted(rows, key=lambda r: (_parse_date(r["deployed_on"]), r["task_id"] or ""), reverse=True)

    # Render table
    table_html = [
        "<div class='table-wrap'>",
        "<table class='table table--sticky table--compact'>",
        "<thead><tr>",
        "<th>Deployment ID</th><th>Task ID</th><th>Title</th><th>Type</th><th>State</th><th>Created On</th><th>Deployed On</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    for r in rows_sorted:
        dep_href = issue_link(r["deployment_id"])
        task_href = issue_link(r["task_id"])
        table_html.append(
            "<tr>"
            f"<td><a class='state-link' href='{dep_href}' target='_blank'>{r['deployment_id'] or ''}</a></td>"
            f"<td><a class='state-link' href='{task_href}' target='_blank'>{r['task_id'] or ''}</a></td>"
            f"<td>{r['title'] or ''}</td>"
            f"<td>{r['type'] or ''}</td>"
            f"<td>{r['state'] or ''}</td>"
            f"<td>{r['created_on'] or ''}</td>"
            f"<td>{r['deployed_on'] or ''}</td>"
            "</tr>"
        )

    if not rows_sorted:
        table_html.append("<tr><td colspan='7' class='muted'>No deployments found for this Project/Period.</td></tr>")

    table_html.append("</tbody></table>")
    table_html.append("</div>")
    st.markdown("".join(table_html), unsafe_allow_html=True)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
# ______________________ Section 3 ENDS ______________________________________


