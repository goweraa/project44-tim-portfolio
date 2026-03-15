"""
TIM Metrics Dashboard
---------------------
Streamlit GUI for the TIM Metrics Assessor.

Run with:
    streamlit run tim_dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from tim_metrics import (
    calculate_metrics, overall_score,
    SLA_TARGET_DAYS, TRACKING_GREEN, TRACKING_YELLOW,
    DATA_QUALITY_GREEN, DATA_QUALITY_YELLOW, ERROR_RATE_YELLOW,
    fmt_interval, fmt_duration,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TIM Metrics Assessor",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0f1117; }
    h1, h2, h3 { color: #e0e0e0; }

    .metric-card {
        background: #1e2130;
        border-radius: 10px;
        padding: 18px 20px;
        text-align: center;
        border-left: 4px solid #4f8ef7;
    }
    .metric-label {
        font-size: 0.78rem;
        color: #9aa0b0;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.1;
    }
    .metric-sub { font-size: 0.75rem; color: #9aa0b0; margin-top: 4px; }

    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-green  { background: #1a3a2a; color: #4caf8a; }
    .badge-yellow { background: #3a2e10; color: #f0b429; }
    .badge-red    { background: #3a1a1a; color: #e05c5c; }
    .badge-grey   { background: #2a2a2a; color: #9aa0b0; }
    .badge-blue   { background: #1a2540; color: #4f8ef7; }
    .badge-purple { background: #2a1a40; color: #b07af7; }
    .badge-teal   { background: #0a2520; color: #4fcfa8; }

    .attention-card {
        background: #1e2130;
        border-left: 4px solid #e05c5c;
        border-radius: 6px;
        padding: 14px 16px;
        margin-bottom: 10px;
    }
    .attention-name  { font-weight: 700; font-size: 0.95rem; color: #e0e0e0; margin-bottom: 6px; }
    .attention-issue { font-size: 0.82rem; color: #c87070; margin: 2px 0; }
    .attention-score { font-size: 0.78rem; color: #9aa0b0; margin-top: 6px; }

    hr { border-color: #2a2d3e; }
    .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def color_for(value, green, yellow, higher_is_better=True):
    if higher_is_better:
        if value >= green:  return "#4caf8a"
        if value >= yellow: return "#f0b429"
        return "#e05c5c"
    else:
        if value <= green:  return "#4caf8a"
        if value <= yellow: return "#f0b429"
        return "#e05c5c"


def badge(text, cls):
    return f'<span class="badge badge-{cls}">{text}</span>'


def score_badge(score):
    cls = "green" if score >= 80 else "yellow" if score >= 60 else "red"
    return badge(f"{score:.0f} / 100", cls)


def status_badge(status):
    cls = {"active": "green", "onboarding": "yellow", "error": "red", "inactive": "grey"}.get(status, "grey")
    return badge(status.upper(), cls)


def provider_badge(ptype):
    cls = {"carrier": "blue", "tms": "purple", "gps": "teal"}.get(ptype, "grey")
    return badge(ptype.upper(), cls)


def pct_badge(value, green, yellow):
    cls = "green" if value >= green else "yellow" if value >= yellow else "red"
    return badge(f"{value:.1f}%", cls)


def sla_badge(m):
    if m["days_to_live"] is not None:
        cls  = "green" if m["sla_met"] else "red"
        mark = "✓" if m["sla_met"] else "✗"
        return badge(f"{m['days_to_live']}d {mark}", cls)
    if m["days_onboarding"] is not None:
        cls = "yellow" if m["days_onboarding"] <= SLA_TARGET_DAYS else "red"
        return badge(f"{m['days_onboarding']}d ⟳", cls)
    return badge("N/A", "grey")


def connection_badge(m):
    direction = m["connection_direction"]
    if direction == "push":
        interval = m.get("push_interval_minutes")
        if interval:
            interval_label = fmt_interval(interval)
            if m["push_on_schedule"]:
                last = fmt_duration(m["minutes_since_push"])
                return badge(f"↑ push/{interval_label} · {last} ago", "green")
            else:
                overdue = fmt_duration(m["push_overdue_by"])
                return badge(f"↑ push/{interval_label} · {overdue} overdue", "red")
        return badge("↑ push", "yellow")
    else:
        h = m["hours_since_sync"]
        if h is None:
            return badge("↓ pull · never", "red")
        cls = "red" if m["sync_stale"] else "green"
        return badge(f"↓ pull · {h:.1f}h ago", cls)


def health_badge(m):
    if m["status"] == "error":
        return badge("ERROR", "red")
    if m["connection_direction"] == "push" and m["push_on_schedule"] is False:
        return badge("PUSH OVERDUE", "red")
    if m["sync_stale"] and m["status"] not in ("onboarding", "inactive"):
        return badge("STALE", "red")
    if m["error_count"] > 0:
        return badge(f"{m['error_count']} errors", "yellow")
    return badge("HEALTHY", "green")


def get_attention_issues(m):
    issues = []
    if m["tracking_pct"] < TRACKING_YELLOW:
        issues.append(f"Low tracking ({m['tracking_pct']:.1f}%)")
    if m["data_quality"] < DATA_QUALITY_YELLOW:
        issues.append(f"Poor data quality ({m['data_quality']:.1f}%)")
    if m["sla_met"] is False:
        issues.append(f"SLA breached ({m['days_to_live']}d > {SLA_TARGET_DAYS}d target)")
    if m["status"] == "error":
        issues.append("Integration in error state")
    if m["connection_direction"] == "push" and m["push_on_schedule"] is False:
        overdue = m["push_overdue_by"]
        interval = m["push_interval_minutes"]
        issues.append(f"Push overdue by {overdue:.0f}min (expected every {interval}min)" if overdue else "Push messages not received")
    elif m["connection_direction"] == "pull" and m["sync_stale"] and m["status"] not in ("onboarding", "inactive"):
        h = m["hours_since_sync"]
        issues.append(f"Stale pull ({h:.0f}h since last sync)" if h else "No sync recorded")
    if m["error_rate"] >= ERROR_RATE_YELLOW:
        issues.append(f"High error rate ({m['error_rate']:.1f}%)")
    return issues


# ── Load & process ────────────────────────────────────────────────────────────

def load_data(file):
    df = pd.read_csv(file)
    rows = []
    for _, row in df.iterrows():
        record = row.to_dict()
        m      = calculate_metrics(record)
        s      = overall_score(m)
        rows.append({"record": record, "metrics": m, "score": s})
    return rows


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📦 TIM Metrics Assessor")
    st.markdown("---")

    uploaded   = st.file_uploader("Upload CSV", type=["csv"])
    sample_path = Path(__file__).parent / "sample_data.csv"
    use_sample  = st.button("Use sample data", use_container_width=True)

    st.markdown("---")
    st.markdown("### Filters")
    status_filter    = st.selectbox("Status",        ["All", "active", "onboarding", "error", "inactive"])
    provider_filter  = st.selectbox("Provider type", ["All", "carrier", "tms", "gps"])
    direction_filter = st.selectbox("Connection",    ["All", "push", "pull"])
    sort_by          = st.selectbox("Sort by",       ["Health Score (worst first)", "Tracking %", "Data Quality", "Name"])

    st.markdown("---")
    st.markdown("### Thresholds")
    st.markdown(
        f"| Metric | 🟢 | 🟡 |\n|---|---|---|\n"
        f"| Tracking % | ≥{TRACKING_GREEN}% | ≥{TRACKING_YELLOW}% |\n"
        f"| Data Quality | ≥{DATA_QUALITY_GREEN}% | ≥{DATA_QUALITY_YELLOW}% |\n"
        f"| SLA (go-live) | ≤{SLA_TARGET_DAYS}d | — |\n"
        f"| Push overdue | on time | >2× interval |"
    )
    st.markdown("---")
    st.caption("Built by Gower Aimable · project44 TIM Portfolio Project")


# ── Data source ───────────────────────────────────────────────────────────────

data_source = uploaded if uploaded else (sample_path if (use_sample or sample_path.exists()) else None)

# ── Main ──────────────────────────────────────────────────────────────────────

st.markdown("# 📦 TIM Metrics Assessor")
st.markdown("Integration health dashboard — carriers, TMS providers, and GPS providers.")
st.markdown("---")

if data_source is None:
    st.info("Upload a CSV or click **Use sample data** to get started.")
    st.stop()

all_rows = load_data(data_source)

# Apply filters
rows = all_rows
if status_filter    != "All": rows = [r for r in rows if r["metrics"]["status"]               == status_filter]
if provider_filter  != "All": rows = [r for r in rows if r["metrics"]["provider_type"]        == provider_filter]
if direction_filter != "All": rows = [r for r in rows if r["metrics"]["connection_direction"] == direction_filter]

sort_map = {
    "Health Score (worst first)": lambda r: r["score"],
    "Tracking %":                 lambda r: r["metrics"]["tracking_pct"],
    "Data Quality":               lambda r: r["metrics"]["data_quality"],
    "Name":                       lambda r: r["record"].get("carrier_name", ""),
}
rows.sort(key=sort_map[sort_by])


# ── Section 1: Network Summary ────────────────────────────────────────────────

n            = len(all_rows)
avg_tracking = sum(r["metrics"]["tracking_pct"] for r in all_rows) / n
avg_quality  = sum(r["metrics"]["data_quality"]  for r in all_rows) / n
avg_score    = sum(r["score"]                    for r in all_rows) / n

sla_vals = [r["metrics"]["sla_met"] for r in all_rows if r["metrics"]["sla_met"] is not None]
sla_rate = (sum(sla_vals) / len(sla_vals) * 100) if sla_vals else 0.0

push_eligible = [r for r in all_rows if r["metrics"]["connection_direction"] == "push"
                 and r["metrics"]["push_on_schedule"] is not None]
push_ok    = sum(1 for r in push_eligible if r["metrics"]["push_on_schedule"])
push_total = len(push_eligible)
push_rate  = (push_ok / push_total * 100) if push_total > 0 else None

carriers = sum(1 for r in all_rows if r["metrics"]["provider_type"] == "carrier")
tms      = sum(1 for r in all_rows if r["metrics"]["provider_type"] == "tms")
gps      = sum(1 for r in all_rows if r["metrics"]["provider_type"] == "gps")
flagged  = sum(1 for r in all_rows if get_attention_issues(r["metrics"]))

st.markdown("## Network Summary")

cols = st.columns(7)

def metric_card(col, label, value, sub, color):
    col.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value" style="color:{color}">{value}</div>'
        f'<div class="metric-sub">{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

metric_card(cols[0], "Integrations",    n,
            f"{carriers} carrier · {tms} TMS · {gps} GPS", "#4f8ef7")
metric_card(cols[1], "Avg Tracking %",  f"{avg_tracking:.1f}%",
            f"target ≥{TRACKING_GREEN}%",
            color_for(avg_tracking, TRACKING_GREEN, TRACKING_YELLOW))
metric_card(cols[2], "Avg Data Quality", f"{avg_quality:.1f}%",
            f"target ≥{DATA_QUALITY_GREEN}%",
            color_for(avg_quality, DATA_QUALITY_GREEN, DATA_QUALITY_YELLOW))
metric_card(cols[3], "SLA Compliance",  f"{sla_rate:.1f}%",
            f"{sum(sla_vals)} of {len(sla_vals)} on time",
            color_for(sla_rate, 90, 70))
if push_rate is not None:
    metric_card(cols[4], "Push On Schedule", f"{push_ok}/{push_total}",
                f"{push_rate:.0f}% of push integrations",
                color_for(push_rate, 90, 70))
else:
    metric_card(cols[4], "Push On Schedule", "N/A", "no push data", "#9aa0b0")
metric_card(cols[5], "Avg Health Score", f"{avg_score:.0f}",
            "out of 100",
            color_for(avg_score, 80, 60))
metric_card(cols[6], "Need Attention",  flagged,
            "integrations with issues",
            "#e05c5c" if flagged > 0 else "#4caf8a")

st.markdown("<br>", unsafe_allow_html=True)


# ── Section 2: Charts ─────────────────────────────────────────────────────────

st.markdown("## Performance Overview")
perf_tab, push_tab, sla_tab, mix_tab = st.tabs(
    ["Tracking & Quality", "Push Interval Health", "SLA Compliance", "Provider Mix"]
)

with perf_tab:
    names    = [r["record"].get("carrier_name", "?") for r in all_rows]
    tracking = [r["metrics"]["tracking_pct"] for r in all_rows]
    quality  = [r["metrics"]["data_quality"]  for r in all_rows]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Tracking %", x=names, y=tracking,
        marker_color=[color_for(v, TRACKING_GREEN, TRACKING_YELLOW) for v in tracking],
        text=[f"{v:.1f}%" for v in tracking], textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Data Quality", x=names, y=quality, opacity=0.75,
        marker_color=[color_for(v, DATA_QUALITY_GREEN, DATA_QUALITY_YELLOW) for v in quality],
        text=[f"{v:.1f}%" for v in quality], textposition="outside",
    ))
    fig.add_hline(y=TRACKING_GREEN, line_dash="dash", line_color="#4caf8a",
                  annotation_text="Tracking target (90%)", annotation_position="top left")
    fig.update_layout(
        barmode="group", height=380,
        plot_bgcolor="#0f1117", paper_bgcolor="#0f1117", font_color="#e0e0e0",
        xaxis=dict(tickangle=-35, gridcolor="#2a2d3e"),
        yaxis=dict(range=[0, 115], gridcolor="#2a2d3e"),
        legend=dict(bgcolor="#1e2130"), margin=dict(t=20, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

with push_tab:
    push_rows = [r for r in all_rows
                 if r["metrics"]["connection_direction"] == "push"
                 and r["metrics"]["push_interval_minutes"] is not None
                 and r["metrics"]["status"] not in ("inactive",)]
    if push_rows:
        p_names    = [r["record"].get("carrier_name", "?") for r in push_rows]
        p_interval = [r["metrics"]["push_interval_minutes"]   for r in push_rows]
        p_actual   = [r["metrics"]["minutes_since_push"] or 0 for r in push_rows]
        p_colors   = ["#4caf8a" if r["metrics"]["push_on_schedule"] else "#e05c5c"
                      for r in push_rows]

        fig2 = go.Figure()
        # Convert to hours for display when any interval >= 60 min
        use_hours = any(v >= 60 for v in p_interval)
        divisor   = 60 if use_hours else 1
        unit      = "hours" if use_hours else "minutes"
        p_interval_display = [v / divisor for v in p_interval]
        p_actual_display   = [v / divisor for v in p_actual]

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            name=f"Expected interval ({unit})", x=p_names, y=p_interval_display,
            marker_color="#4f8ef7", opacity=0.5,
            text=[fmt_interval(v) for v in p_interval], textposition="inside",
        ))
        fig2.add_trace(go.Bar(
            name=f"Actual gap since last push ({unit})", x=p_names, y=p_actual_display,
            marker_color=p_colors,
            text=[fmt_duration(v) for v in p_actual], textposition="outside",
        ))
        fig2.update_layout(
            barmode="overlay", height=380,
            plot_bgcolor="#0f1117", paper_bgcolor="#0f1117", font_color="#e0e0e0",
            xaxis=dict(tickangle=-35, gridcolor="#2a2d3e"),
            yaxis=dict(title=f"Time ({unit})", gridcolor="#2a2d3e"),
            legend=dict(bgcolor="#1e2130"), margin=dict(t=20, b=10),
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("Blue bar = expected push interval. Coloured bar = actual gap since last message. Red = overdue (>2× interval).")
    else:
        st.info("No push integration data available.")

with sla_tab:
    sla_rows = [(r["record"].get("carrier_name", "?"), r["metrics"])
                for r in all_rows if r["metrics"]["days_to_live"] is not None]
    if sla_rows:
        s_names = [n for n, _ in sla_rows]
        s_days  = [m["days_to_live"] for _, m in sla_rows]
        s_colors = ["#4caf8a" if m["sla_met"] else "#e05c5c" for _, m in sla_rows]
        fig3 = go.Figure(go.Bar(
            x=s_names, y=s_days, marker_color=s_colors,
            text=[f"{d}d" for d in s_days], textposition="outside",
        ))
        fig3.add_hline(y=SLA_TARGET_DAYS, line_dash="dash", line_color="#f0b429",
                       annotation_text=f"{SLA_TARGET_DAYS}-day SLA target",
                       annotation_position="top left")
        fig3.update_layout(
            height=360, plot_bgcolor="#0f1117", paper_bgcolor="#0f1117", font_color="#e0e0e0",
            xaxis=dict(tickangle=-35, gridcolor="#2a2d3e"),
            yaxis=dict(title="Days to go-live", gridcolor="#2a2d3e"),
            margin=dict(t=20, b=10),
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No completed onboarding data.")

with mix_tab:
    col_a, col_b = st.columns(2)
    with col_a:
        types  = [r["record"].get("integration_type", "?").upper() for r in all_rows]
        tcnt   = pd.Series(types).value_counts()
        fig4a  = go.Figure(go.Pie(
            labels=tcnt.index, values=tcnt.values, hole=0.45,
            marker_colors=["#4f8ef7", "#f0b429", "#4caf8a", "#e05c5c"],
        ))
        fig4a.update_layout(
            title_text="Protocol (API / EDI / Flat File)",
            plot_bgcolor="#0f1117", paper_bgcolor="#0f1117", font_color="#e0e0e0",
            margin=dict(t=40, b=10), height=320, legend=dict(bgcolor="#1e2130"),
        )
        st.plotly_chart(fig4a, use_container_width=True)
    with col_b:
        ptypes = [r["metrics"]["provider_type"].upper() for r in all_rows]
        pcnt   = pd.Series(ptypes).value_counts()
        fig4b  = go.Figure(go.Pie(
            labels=pcnt.index, values=pcnt.values, hole=0.45,
            marker_colors=["#4f8ef7", "#b07af7", "#4fcfa8"],
        ))
        fig4b.update_layout(
            title_text="Provider Type (Carrier / TMS / GPS)",
            plot_bgcolor="#0f1117", paper_bgcolor="#0f1117", font_color="#e0e0e0",
            margin=dict(t=40, b=10), height=320, legend=dict(bgcolor="#1e2130"),
        )
        st.plotly_chart(fig4b, use_container_width=True)
    st.caption("project44 integration preference: API (push) > API (pull) > Flat File > EDI")


# ── Section 3: Integration Table ──────────────────────────────────────────────

st.markdown(f"## Integration Details  `{len(rows)} shown`")

table_html = """
<table style="width:100%; border-collapse:collapse; font-size:0.83rem;">
<thead>
<tr style="background:#1e2130; color:#9aa0b0; text-align:left;">
  <th style="padding:10px 12px;">Name</th>
  <th style="padding:10px 12px;">Provider</th>
  <th style="padding:10px 12px;">Proto</th>
  <th style="padding:10px 12px; text-align:right;">Tracking %</th>
  <th style="padding:10px 12px; text-align:right;">Data Quality</th>
  <th style="padding:10px 12px; text-align:center;">SLA</th>
  <th style="padding:10px 12px; text-align:center;">Connection</th>
  <th style="padding:10px 12px; text-align:center;">Health</th>
  <th style="padding:10px 12px; text-align:right;">Score</th>
</tr>
</thead>
<tbody>
"""

for i, row in enumerate(rows):
    rec = row["record"]
    m   = row["metrics"]
    s   = row["score"]
    bg  = "#0f1117" if i % 2 == 0 else "#13161f"
    itype = rec.get("integration_type", "?").upper()
    type_color = {"API": "#4f8ef7", "EDI": "#f0b429", "FLAT FILE": "#4caf8a"}.get(itype, "#9aa0b0")

    table_html += f"""
<tr style="background:{bg}; border-bottom:1px solid #2a2d3e;">
  <td style="padding:10px 12px; color:#e0e0e0; font-weight:500;">{rec.get('carrier_name', '?')}</td>
  <td style="padding:10px 12px;">{provider_badge(m['provider_type'])}</td>
  <td style="padding:10px 12px;"><span style="color:{type_color}; font-size:0.75rem; font-weight:600;">{itype}</span></td>
  <td style="padding:10px 12px; text-align:right;">{pct_badge(m['tracking_pct'], TRACKING_GREEN, TRACKING_YELLOW)}</td>
  <td style="padding:10px 12px; text-align:right;">{pct_badge(m['data_quality'], DATA_QUALITY_GREEN, DATA_QUALITY_YELLOW)}</td>
  <td style="padding:10px 12px; text-align:center;">{sla_badge(m)}</td>
  <td style="padding:10px 12px; text-align:center;">{connection_badge(m)}</td>
  <td style="padding:10px 12px; text-align:center;">{health_badge(m)}</td>
  <td style="padding:10px 12px; text-align:right;">{score_badge(s)}</td>
</tr>
"""

table_html += "</tbody></table>"
st.markdown(table_html, unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)


# ── Section 4: Attention Cards ────────────────────────────────────────────────

attention_rows = sorted(
    [(r["record"].get("carrier_name", "?"), get_attention_issues(r["metrics"]), r["score"])
     for r in all_rows if get_attention_issues(r["metrics"])],
    key=lambda x: x[2]
)

st.markdown("## Integrations Requiring Attention")

if not attention_rows:
    st.success("✓ All integrations within acceptable thresholds.")
else:
    cols = st.columns(min(len(attention_rows), 3))
    for idx, (name, issues, score) in enumerate(attention_rows):
        with cols[idx % 3]:
            issue_html = "".join(f'<div class="attention-issue">• {i}</div>' for i in issues)
            st.markdown(
                f'<div class="attention-card">'
                f'<div class="attention-name">{name}</div>'
                f'{issue_html}'
                f'<div class="attention-score">Health score: {score:.0f} / 100</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.markdown("---")
st.caption(
    f"TIM Metrics Assessor · "
    f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · "
    f"Built by Gower Aimable"
)
