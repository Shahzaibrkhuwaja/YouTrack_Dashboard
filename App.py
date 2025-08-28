# app.py
from __future__ import annotations
import streamlit as st
from config import ACTIVE_PROJECTS, PERIOD_LABELS
from youtrack_queries import get_task_counts_by_type_and_state
from youtrack_queries import yt_issues_url
import plotly.graph_objects as go
from datetime import date
from youtrack_queries import get_monthly_task_counts_by_type
from chart_theme import apply_chart_theme
import calendar
from chart_theme import apply_chart_theme, DEFAULT_COLORWAY

st.set_page_config(page_title="YouTrack Dashboard", layout="wide")


with open("styles.css", "r", encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


#______________________Section 1 STARTS___________________________________________________________________
#  Header
st.markdown('<div class="center-title">YouTrack Dashboard</div>', unsafe_allow_html=True)

#  Controls 
c1, c2, c3 = st.columns([1, 1, 10])
with c1:
    st.markdown('<div class="label">Project</div>', unsafe_allow_html=True)
    project = st.selectbox("Project", ACTIVE_PROJECTS, index=0, label_visibility="collapsed")
with c2:
    st.markdown('<div class="label">Period</div>', unsafe_allow_html=True)
    labels = list(PERIOD_LABELS.values())
    keys = list(PERIOD_LABELS.keys())
    idx = 0
    selected_label = st.selectbox("Period", labels, index=idx, label_visibility="collapsed")
    period_key = keys[labels.index(selected_label)]
with c3:
    st.write("")

st.markdown('<div class="smallnote">*Summary is based on Task Created in Given Period</div>', unsafe_allow_html=True)
st.markdown('<div class="bar"></div>', unsafe_allow_html=True)

# Data
data = get_task_counts_by_type_and_state(period_key)
type_map = data.get("per_project", {}).get(project, {})

# Cards
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
            f"    <a class='chip-link type-label' href='{type_href}' target='_blank' style='flex:1 1 auto'>{typ}:</a>"
            f"    <span class='pill'>{total}</span>"
            f"  </h4>"
            f"  <div class='muted'>{state_lines}</div>"
            f"</div>"
        )
cards.append("</div>")
st.markdown("".join(cards), unsafe_allow_html=True)
st.markdown('<div class="bar"></div>', unsafe_allow_html=True)
#______________________Section 1 ENDS_____________________________________________________________________

#______________________Section 2 STARTS___________________________________________________________________
st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="section-title">Tasks Created per Month (by Type)</div>', unsafe_allow_html=True)

year = date.today().year
current_month = date.today().month
monthly_data = get_monthly_task_counts_by_type(project, year)

if not monthly_data:
    st.markdown('<div class="muted">No data available for this year.</div>', unsafe_allow_html=True)
else:
    months = [f"{year}-{m:02d}" for m in range(1, current_month + 1)]
    month_labels = [calendar.month_abbr[m] for m in range(1, current_month + 1)]
    all_types = sorted({t for m in monthly_data.values() for t in m})

    # 🔴 Custom color map
    TYPE_COLORS = {
        "Bug": "#e74c3c",
        "New Requirement": "#0748B1",
        "Change Request" : "#07B176",
    }
    PALETTE = [
        "#146f91", "#075066", "#9b59b6", "#f39c12",
        "#34495e", "#1abc9c", "#f38942", "#7f8c8d"
    ]
    palette_idx = 0

    fig = go.Figure()
    for t in all_types:
        vals = [monthly_data.get(m, {}).get(t, 0) for m in months]
        labels = [str(v) if v > 0 else "" for v in vals]

        # choose color: fixed if in TYPE_COLORS, otherwise rotate palette
        if t in TYPE_COLORS:
            color = TYPE_COLORS[t]
        else:
            color = PALETTE[palette_idx % len(PALETTE)]
            palette_idx += 1

        fig.add_bar(
            name=t,
            x=month_labels,
            y=vals,
            text=labels,
            textposition="outside",
            marker_color=color,
            hoverinfo="skip",        
            hovertemplate=None
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
        bar_text_size=12,
        height=250,
        margin_t=10,
        margin_b=0,
        legend_orientation="v",
        legend_x=1.02, legend_y=1, legend_xanchor="left", legend_yanchor="top",
    )
    st.markdown('<div class="bar"></div>', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('<div class="bar"></div>', unsafe_allow_html=True)
#______________________Section 2 ENDS_____________________________________________________________________




