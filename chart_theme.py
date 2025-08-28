# chart_theme.py
import plotly.graph_objects as go

# Default palette (edit/extend as you like)
DEFAULT_COLORWAY = [
    "#146f91", "#e67e22", "#27ae60", "#8e44ad", "#c0392b",
    "#2c3e50", "#f39c12", "#16a085", "#d35400", "#7f8c8d"
]

def apply_chart_theme(fig: go.Figure, **overrides) -> go.Figure:
    base = {
        "font_family": "Bahnschrift, 'Segoe UI', system-ui, -apple-system, Roboto, Arial, sans-serif",
        "font_size": 12,
        "title_size": 14,
        "axis_title_size": 13,
        "tick_size": 12,
        "legend_size": 12,
        "legend_orientation": "v",
        "legend_x": 1.02,
        "legend_y": 1,
        "legend_xanchor": "left",
        "legend_yanchor": "top",
        "show_legend": True,
        "height": 250,
        "margin_l": 40, "margin_r": 40, "margin_t": 40, "margin_b": 40,
        "plot_bg": "rgba(255,255,255,1)",
        "paper_bg": "rgba(255,255,255,0)",
        "xgrid": "rgba(0,0,0,0.06)",
        "ygrid": "rgba(0,0,0,0.08)",
        "zeroline": False,
        "hover_bg": "rgba(0,0,0,0.85)",
        "hover_font_color": "#fff",
        "hover_font_size": 12,
        "bargap": 0.18,
        "bargroupgap": 0.06,

        # NEW: colors + number labels
        "colorway": DEFAULT_COLORWAY,   # list[str]
        "show_bar_text": False,         # when True, put numbers above bars
        "bar_text_color": "#111",
        "bar_text_size": 11,

        # Axis colors (titles + ticks)
        "xaxis_title_color": "#111",
        "xaxis_tick_color":  "#111",
        "yaxis_title_color": "#111",
        "yaxis_tick_color":  "#111",
        # Optional axis line colors
        "xaxis_line_color":  None,
        "yaxis_line_color":  None,
    }
    base.update(overrides or {})

    fig.update_layout(
        height=base["height"],
        margin=dict(l=base["margin_l"], r=base["margin_r"], t=base["margin_t"], b=base["margin_b"]),
        paper_bgcolor=base["paper_bg"],
        plot_bgcolor=base["plot_bg"],
        font=dict(family=base["font_family"], size=base["font_size"]),
        legend=dict(
            orientation=base["legend_orientation"],
            x=base["legend_x"], y=base["legend_y"],
            xanchor=base["legend_xanchor"], yanchor=base["legend_yanchor"],
            font=dict(size=base["legend_size"])
        ),
        hoverlabel=dict(
            bgcolor=base["hover_bg"],
            font=dict(color=base["hover_font_color"], size=base["hover_font_size"])
        ),
        bargap=base["bargap"],
        bargroupgap=base["bargroupgap"],
        showlegend=base["show_legend"],
        colorway=base["colorway"],   # <- use your palette
    )

    # Axes
    fig.update_xaxes(
        title=dict(text="Month", font=dict(size=base["axis_title_size"], color=base["xaxis_title_color"])),
        tickfont=dict(size=base["tick_size"], color=base["xaxis_tick_color"]),
        showgrid=True, gridcolor=base["xgrid"],
        zeroline=base["zeroline"],
        showline=bool(base["xaxis_line_color"]),
        linecolor=base["xaxis_line_color"] or "rgba(0,0,0,0)"
    )
    fig.update_yaxes(
        title=dict(text="Task Count", font=dict(size=base["axis_title_size"], color=base["yaxis_title_color"])),
        tickfont=dict(size=base["tick_size"], color=base["yaxis_tick_color"]),
        showgrid=True, gridcolor=base["ygrid"],
        zeroline=base["zeroline"],
        showline=bool(base["yaxis_line_color"]),
        linecolor=base["yaxis_line_color"] or "rgba(0,0,0,0)"
    )

    # If labels are requested, set text styling globally
    if base["show_bar_text"]:
        fig.update_traces(
            textposition="outside",
            textfont=dict(color=base["bar_text_color"], size=base["bar_text_size"]),
            cliponaxis=False,  # allow text outside plotting area
        )

    return fig
