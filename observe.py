"""
Observe — Shipment Visibility Platform
Inspired by project44's Observe product.
Run with: python3 -m streamlit run observe.py
"""

import os
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NOW = datetime(2026, 3, 15, 21, 0, 0)
TODAY = date(2026, 3, 15)
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "observe_shipments.csv")

MILESTONE_SEQUENCE = [
    "PICKUP_CONFIRMED",
    "IN_TRANSIT",
    "AT_FACILITY",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
]

MILESTONE_LABELS = {
    "PICKUP_CONFIRMED": "Pickup\nConfirmed",
    "IN_TRANSIT": "In\nTransit",
    "AT_FACILITY": "At\nFacility",
    "OUT_FOR_DELIVERY": "Out for\nDelivery",
    "DELIVERED": "Delivered",
}

STATUS_DISPLAY = {
    "in_transit": "● In Transit",
    "at_risk": "▲ At Risk",
    "exception": "✖ Exception",
    "delivered": "✓ Delivered",
}

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

EXCEPTION_LABELS = {
    "NO_UPDATE": "No tracking update",
    "DATA_GAP": "Milestone data gap",
    "DELAY": "Delivery delay",
    "MISSED_PICKUP": "Missed pickup",
}

EXCEPTION_ACTIONS = {
    "NO_UPDATE": "Contact carrier operations team. Verify EDI/API feed is active.",
    "DATA_GAP": "Review EDI parse logs. Check AT7 segment mapping. Request retransmission.",
    "DELAY": "Notify customer of revised ETA. Update shipment ETA in TMS.",
    "MISSED_PICKUP": "Confirm pickup with carrier dispatcher. Re-tender if needed.",
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Observe — Shipment Visibility",
    page_icon="📦",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .exc-card {
        border: 1px solid #444;
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 10px;
        background: #111827;
    }
    .badge-critical { color: #ff4444; font-weight: 700; }
    .badge-high     { color: #ff8800; font-weight: 700; }
    .badge-medium   { color: #f0c040; font-weight: 700; }
    .badge-low      { color: #4488ff; font-weight: 700; }
    .badge-api  { background:#1a3a5c; color:#7ec8e3; padding:2px 8px; border-radius:4px; font-size:0.8em; }
    .badge-edi  { background:#3a1a1a; color:#e37c7c; padding:2px 8px; border-radius:4px; font-size:0.8em; }
    .badge-flat { background:#2a3a1a; color:#a0e37c; padding:2px 8px; border-radius:4px; font-size:0.8em; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Data loading & computed columns
# ---------------------------------------------------------------------------
@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)

    # Parse date-only columns
    for col in ["pickup_date", "scheduled_delivery", "estimated_delivery"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # Parse datetime columns
    for col in ["actual_delivery", "last_event_time"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # Computed columns
    df["route"] = (
        df["origin_city"] + ", " + df["origin_state"]
        + " → "
        + df["destination_city"] + ", " + df["destination_state"]
    )

    df["milestones_str"] = (
        df["milestones_received"].astype(str)
        + "/"
        + df["milestones_expected"].astype(str)
    )

    df["hours_since_update"] = df["last_event_time"].apply(
        lambda t: (NOW - t).total_seconds() / 3600 if pd.notna(t) else None
    )

    def _update_label(h):
        if h is None:
            return "—"
        if h >= 1:
            return f"{int(h)}h ago"
        return f"{int(h * 60)}m ago"

    df["last_update_label"] = df["hours_since_update"].apply(_update_label)

    def _is_on_time(row):
        if row["status"] != "delivered":
            return False
        if pd.isna(row["actual_delivery"]) or pd.isnull(row["scheduled_delivery"]):
            return False
        return row["actual_delivery"].date() <= row["scheduled_delivery"]

    df["is_on_time"] = df.apply(_is_on_time, axis=1)

    df["status_display"] = df["status"].map(STATUS_DISPLAY).fillna(df["status"])

    def _eta_display(row):
        if row["status"] == "delivered" and pd.notna(row["actual_delivery"]):
            return row["actual_delivery"].strftime("%Y-%m-%d")
        if row["estimated_delivery"] is not None and not pd.isnull(row["estimated_delivery"]) if isinstance(row["estimated_delivery"], float) else row["estimated_delivery"] is not None:
            return str(row["estimated_delivery"])
        return "—"

    df["eta_display"] = df.apply(_eta_display, axis=1)

    # Fill NaN exception columns with empty string
    df["exception_type"] = df["exception_type"].fillna("")
    df["exception_severity"] = df["exception_severity"].fillna("")
    df["notes"] = df["notes"].fillna("")

    return df


# ---------------------------------------------------------------------------
# Milestone helpers
# ---------------------------------------------------------------------------
def _get_milestones(row) -> list:
    """Return list of milestone dicts for a shipment row."""
    last_event = str(row["last_event"]) if pd.notna(row["last_event"]) else ""
    exc_type = str(row["exception_type"])
    pickup_date = row["pickup_date"]

    if pickup_date is not None:
        pickup_dt = datetime.combine(pickup_date, datetime.min.time().replace(hour=8))
    else:
        pickup_dt = NOW - pd.Timedelta(days=2)

    sched_del = row["scheduled_delivery"]
    actual_del = row["actual_delivery"]

    # Estimate end time
    if pd.notna(actual_del):
        end_dt = actual_del
    elif sched_del is not None:
        end_dt = datetime.combine(sched_del, datetime.min.time().replace(hour=17))
    else:
        end_dt = pickup_dt + pd.Timedelta(days=3)

    transit_seconds = (end_dt - pickup_dt).total_seconds()
    if transit_seconds <= 0:
        transit_seconds = 86400

    # Fractions of transit time for estimated milestone timestamps
    fractions = {
        "PICKUP_CONFIRMED": 0.0,
        "IN_TRANSIT": 0.15,
        "AT_FACILITY": 0.50,
        "OUT_FOR_DELIVERY": 0.80,
        "DELIVERED": 1.0,
    }

    # Determine which milestones are complete
    complete_set = {"PICKUP_CONFIRMED"}
    if last_event in ("IN_TRANSIT", "AT_FACILITY", "OUT_FOR_DELIVERY", "DELIVERED"):
        complete_set.add("IN_TRANSIT")
    if last_event in ("AT_FACILITY", "OUT_FOR_DELIVERY", "DELIVERED"):
        complete_set.add("AT_FACILITY")
    if last_event in ("OUT_FOR_DELIVERY", "DELIVERED"):
        complete_set.add("OUT_FOR_DELIVERY")
    if last_event == "DELIVERED":
        complete_set.add("DELIVERED")

    # Index of last complete milestone
    last_complete_idx = -1
    for i, m in enumerate(MILESTONE_SEQUENCE):
        if m in complete_set:
            last_complete_idx = i

    warning_flag = exc_type in ("NO_UPDATE", "DATA_GAP")

    milestones = []
    for i, name in enumerate(MILESTONE_SEQUENCE):
        complete = name in complete_set
        is_last_complete = (i == last_complete_idx)
        warning = warning_flag and is_last_complete

        # Assign timestamps
        if name == "PICKUP_CONFIRMED":
            ts = pickup_dt
        elif name == "DELIVERED" and pd.notna(actual_del):
            ts = actual_del
        elif name == row["last_event"] and pd.notna(row["last_event_time"]):
            ts = row["last_event_time"]
        else:
            frac = fractions[name]
            ts = pickup_dt + pd.Timedelta(seconds=transit_seconds * frac)

        milestones.append({
            "name": name,
            "label": MILESTONE_LABELS[name],
            "complete": complete,
            "warning": warning,
            "ts": ts,
        })

    return milestones


def _render_timeline(row):
    """Render a Plotly horizontal milestone timeline for a shipment row."""
    milestones = _get_milestones(row)

    x_vals = [m["ts"] for m in milestones]
    y_vals = [0] * len(milestones)

    marker_colors = []
    marker_sizes = []
    marker_symbols = []

    for m in milestones:
        if m["warning"]:
            marker_colors.append("#ff4444")
            marker_sizes.append(16)
            marker_symbols.append("circle")
        elif m["complete"]:
            marker_colors.append("#4488cc")
            marker_sizes.append(16)
            marker_symbols.append("circle")
        else:
            marker_colors.append("#888888")
            marker_sizes.append(12)
            marker_symbols.append("circle-open")

    fig = go.Figure()

    # Connector line
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode="lines",
        line=dict(color="#555555", width=2),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Individual milestone markers + labels above
    for i, m in enumerate(milestones):
        ts_obj = m["ts"]
        ts_str = ts_obj.strftime("%Y-%m-%d %H:%M") if hasattr(ts_obj, "strftime") else str(ts_obj)
        fig.add_trace(go.Scatter(
            x=[m["ts"]],
            y=[0],
            mode="markers+text",
            marker=dict(
                color=marker_colors[i],
                size=marker_sizes[i],
                symbol=marker_symbols[i],
                line=dict(color=marker_colors[i], width=2),
            ),
            text=[m["label"].replace("\n", "<br>")],
            textposition="top center",
            textfont=dict(size=10, color="#cccccc"),
            hovertemplate=f"{m['name']}<br>{ts_str}<extra></extra>",
            showlegend=False,
        ))

    # Timestamp annotations below each milestone
    for m in milestones:
        ts_obj = m["ts"]
        ts_str = ts_obj.strftime("%m/%d %H:%M") if hasattr(ts_obj, "strftime") else str(ts_obj)
        fig.add_annotation(
            x=m["ts"],
            y=-0.55,
            text=f"<span style='font-size:9px;color:#888'>{ts_str}</span>",
            showarrow=False,
            yanchor="top",
        )

    exc_note = ""
    if row["exception_type"] in ("NO_UPDATE", "DATA_GAP"):
        exc_note = f"  ⚠ {EXCEPTION_LABELS.get(row['exception_type'], row['exception_type'])}"

    fig.add_annotation(
        text=f"BOL: {row['bol']} | {row['carrier_name']} | {row['route']}{exc_note}",
        xref="paper", yref="paper",
        x=0, y=1.22,
        showarrow=False,
        font=dict(size=11, color="#aaaaaa"),
        align="left",
    )

    fig.update_layout(
        template="plotly_white",
        height=200,
        margin=dict(l=10, r=10, t=50, b=60),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1.2, 1.2]),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df_all = load_data()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.title("Observe")
st.sidebar.caption("Shipment Visibility Platform")
st.sidebar.markdown("---")

all_carriers = sorted(df_all["carrier_name"].unique().tolist())
all_statuses = sorted(df_all["status"].unique().tolist())
all_modes = sorted(df_all["mode"].unique().tolist())
all_integrations = sorted(df_all["integration_type"].unique().tolist())

sel_carriers = st.sidebar.multiselect("Carrier", all_carriers, default=all_carriers)
sel_statuses = st.sidebar.multiselect("Status", all_statuses, default=all_statuses)
sel_modes = st.sidebar.multiselect("Mode", all_modes, default=all_modes)
sel_integrations = st.sidebar.multiselect("Integration Type", all_integrations, default=all_integrations)

if st.sidebar.button("Reset Filters"):
    st.rerun()

# Apply filters
df = df_all[
    df_all["carrier_name"].isin(sel_carriers)
    & df_all["status"].isin(sel_statuses)
    & df_all["mode"].isin(sel_modes)
    & df_all["integration_type"].isin(sel_integrations)
].copy()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Observe — Shipment Visibility")
st.caption(f"Reference date: {NOW.strftime('%Y-%m-%d %H:%M')} | {len(df)} shipments shown")

# ---------------------------------------------------------------------------
# Summary metric bar
# ---------------------------------------------------------------------------
total = len(df)
in_transit_count = len(df[df["status"].isin(["in_transit", "at_risk"])])
delivered_today_count = len(
    df[
        (df["status"] == "delivered")
        & (df["actual_delivery"].dt.date == TODAY)
    ]
)
exceptions_count = len(df[df["exception_type"] != ""])

delivered_df = df[df["status"] == "delivered"]
if len(delivered_df) > 0:
    otd_pct = round(delivered_df["is_on_time"].sum() / len(delivered_df) * 100, 1)
    otd_str = f"{otd_pct}%"
else:
    otd_str = "—"

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Shipments", total)
m2.metric("In Transit / At Risk", in_transit_count)
m3.metric("Delivered Today", delivered_today_count)
m4.metric("Exceptions", exceptions_count)
m5.metric("OTD %", otd_str)

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_shipments, tab_exceptions, tab_scorecards = st.tabs(
    ["Shipments", "Exceptions", "Scorecards"]
)

# ===========================================================================
# TAB 1 — SHIPMENTS
# ===========================================================================
with tab_shipments:

    # Build display dataframe
    display_df = df[[
        "bol", "carrier_name", "route", "mode", "integration_type",
        "pickup_date", "scheduled_delivery", "eta_display",
        "status_display", "last_update_label", "milestones_str", "exception_severity",
    ]].copy()

    display_df.columns = [
        "BOL", "Carrier", "Route", "Mode", "Integration",
        "Pickup", "Sched. Delivery", "ETA / Delivered",
        "Status", "Last Update", "Milestones", "Exception",
    ]

    # Convert date objects to strings for clean display
    display_df["Pickup"] = display_df["Pickup"].apply(
        lambda x: str(x) if x is not None else "—"
    )
    display_df["Sched. Delivery"] = display_df["Sched. Delivery"].apply(
        lambda x: str(x) if x is not None else "—"
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "BOL": st.column_config.TextColumn("BOL", width="medium"),
            "Carrier": st.column_config.TextColumn("Carrier", width="medium"),
            "Route": st.column_config.TextColumn("Route", width="large"),
            "Mode": st.column_config.TextColumn("Mode", width="small"),
            "Integration": st.column_config.TextColumn("Integration", width="small"),
            "Pickup": st.column_config.TextColumn("Pickup", width="small"),
            "Sched. Delivery": st.column_config.TextColumn("Sched. Delivery", width="small"),
            "ETA / Delivered": st.column_config.TextColumn("ETA / Delivered", width="small"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
            "Last Update": st.column_config.TextColumn("Last Update", width="small"),
            "Milestones": st.column_config.TextColumn("Milestones", width="small"),
            "Exception": st.column_config.TextColumn("Exception", width="small"),
        },
    )

    st.markdown("---")
    st.subheader("Milestone Timeline")

    bol_options = df["bol"].tolist()
    if bol_options:
        selected_bol = st.selectbox("View milestone timeline for:", bol_options)
        row_sel = df[df["bol"] == selected_bol].iloc[0]
        with st.expander(
            f"Timeline: {selected_bol} — {row_sel['route']}",
            expanded=True,
        ):
            _render_timeline(row_sel)
    else:
        st.info("No shipments match current filters.")


# ===========================================================================
# TAB 2 — EXCEPTIONS
# ===========================================================================
with tab_exceptions:

    exc_df = df[df["exception_type"] != ""].copy()

    if exc_df.empty:
        st.info("No exceptions in current filtered view.")
    else:
        exc_df["_sev_order"] = exc_df["exception_severity"].map(SEVERITY_ORDER).fillna(99)
        exc_df = exc_df.sort_values("_sev_order")

        crit_count = len(exc_df[exc_df["exception_severity"] == "CRITICAL"])
        high_count = len(exc_df[exc_df["exception_severity"] == "HIGH"])
        med_low_count = len(exc_df[exc_df["exception_severity"].isin(["MEDIUM", "LOW"])])

        ec1, ec2, ec3 = st.columns(3)
        ec1.metric("CRITICAL", crit_count)
        ec2.metric("HIGH", high_count)
        ec3.metric("MEDIUM / LOW", med_low_count)

        st.markdown("---")

        for severity_label in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            group = exc_df[exc_df["exception_severity"] == severity_label]
            if group.empty:
                continue

            st.subheader(f"{severity_label} ({len(group)})")

            for _, row in group.iterrows():
                st.markdown(
                    '<div style="border:1px solid #444; border-radius:6px; '
                    'padding:12px 14px; margin-bottom:10px; background:#111827;">',
                    unsafe_allow_html=True,
                )

                col_sev, col_mid, col_act = st.columns([1, 3, 2])

                with col_sev:
                    sev = row["exception_severity"]
                    if sev == "CRITICAL":
                        st.markdown(
                            '<span class="badge-critical">✖ CRITICAL</span>',
                            unsafe_allow_html=True,
                        )
                    elif sev == "HIGH":
                        st.markdown(
                            '<span class="badge-high">▲ HIGH</span>',
                            unsafe_allow_html=True,
                        )
                    elif sev == "MEDIUM":
                        st.markdown(
                            '<span class="badge-medium">● MEDIUM</span>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            '<span class="badge-low">○ LOW</span>',
                            unsafe_allow_html=True,
                        )
                    st.caption(row["exception_type"])

                with col_mid:
                    st.markdown(f"**{row['bol']}**")
                    st.caption(row["carrier_name"])
                    st.caption(row["route"])
                    exc_label = EXCEPTION_LABELS.get(row["exception_type"], row["exception_type"])
                    st.caption(f"Issue: {exc_label}")
                    hrs = row["hours_since_update"]
                    hrs_str = f"{int(hrs)}h ago" if hrs is not None else "—"
                    st.caption(f"Last update: {hrs_str}")
                    if row["notes"]:
                        st.caption(f"Notes: {row['notes']}")

                with col_act:
                    action = EXCEPTION_ACTIONS.get(row["exception_type"], "Review shipment details.")
                    st.caption("Recommended Action:")
                    st.info(action, icon="💡")

                    int_type = row["integration_type"]
                    if int_type == "API":
                        badge_html = '<span class="badge-api">API</span>'
                    elif int_type == "EDI":
                        badge_html = '<span class="badge-edi">EDI</span>'
                    else:
                        badge_html = '<span class="badge-flat">Flat File</span>'
                    st.markdown(badge_html, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# TAB 3 — SCORECARDS
# ===========================================================================
with tab_scorecards:

    carriers_in_view = sorted(df["carrier_name"].unique().tolist())

    sc_rows = []
    for carrier in carriers_in_view:
        cdf = df[df["carrier_name"] == carrier]
        int_type = cdf["integration_type"].iloc[0]
        total_c = len(cdf)

        del_df = cdf[cdf["status"] == "delivered"]
        delivered_c = len(del_df)

        if delivered_c > 0:
            on_time_c = int(del_df["is_on_time"].sum())
            otd_val = round(on_time_c / delivered_c * 100, 1)

            transit_days_list = []
            for _, r in del_df.iterrows():
                if pd.notna(r["actual_delivery"]) and r["pickup_date"] is not None:
                    delta = (r["actual_delivery"].date() - r["pickup_date"]).days
                    transit_days_list.append(delta)
            avg_transit = round(sum(transit_days_list) / len(transit_days_list), 1) if transit_days_list else None
        else:
            otd_val = None
            avg_transit = None

        dq_values = []
        for _, r in cdf.iterrows():
            if r["milestones_expected"] > 0:
                dq_values.append(r["milestones_received"] / r["milestones_expected"] * 100)
        dq_pct = round(sum(dq_values) / len(dq_values), 1) if dq_values else 0.0

        exc_count = len(cdf[cdf["exception_type"] != ""])
        exc_rate = round(exc_count / total_c * 100, 1) if total_c > 0 else 0.0

        sc_rows.append({
            "Carrier": carrier,
            "Integration": int_type,
            "Total": total_c,
            "Delivered": delivered_c,
            "OTD %": otd_val,
            "Avg Transit (days)": avg_transit,
            "Data Quality %": dq_pct,
            "Exceptions": exc_count,
            "Exception Rate %": exc_rate,
            "_otd_sort": otd_val if otd_val is not None else -1.0,
        })

    sc_df = (
        pd.DataFrame(sc_rows)
        .sort_values("_otd_sort", ascending=False)
        .drop(columns=["_otd_sort"])
        .reset_index(drop=True)
    )

    # Display-friendly copy
    display_sc = sc_df.copy()
    display_sc["OTD %"] = display_sc["OTD %"].apply(
        lambda x: f"{x}%" if x is not None else "—"
    )
    display_sc["Avg Transit (days)"] = display_sc["Avg Transit (days)"].apply(
        lambda x: str(x) if x is not None else "—"
    )

    st.subheader("Carrier Scorecards")
    st.dataframe(
        display_sc,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Carrier": st.column_config.TextColumn("Carrier", width="medium"),
            "Integration": st.column_config.TextColumn("Integration", width="small"),
            "Total": st.column_config.NumberColumn("Total", width="small"),
            "Delivered": st.column_config.NumberColumn("Delivered", width="small"),
            "OTD %": st.column_config.TextColumn("OTD %", width="small"),
            "Avg Transit (days)": st.column_config.TextColumn("Avg Transit (days)", width="small"),
            "Data Quality %": st.column_config.NumberColumn(
                "Data Quality %", format="%.1f%%", width="small"
            ),
            "Exceptions": st.column_config.NumberColumn("Exceptions", width="small"),
            "Exception Rate %": st.column_config.NumberColumn(
                "Exception Rate %", format="%.1f%%", width="small"
            ),
        },
    )

    st.markdown("---")

    # --- OTD chart (carriers with at least 1 delivery) ---
    chart_otd_df = sc_df[sc_df["OTD %"].notna()].sort_values("OTD %", ascending=True)

    def _color_otd(v):
        if v >= 90:
            return "#2ecc71"
        if v >= 75:
            return "#f39c12"
        return "#e74c3c"

    def _color_dq(v):
        if v >= 95:
            return "#2ecc71"
        if v >= 80:
            return "#f39c12"
        return "#e74c3c"

    col_left, col_right = st.columns(2)

    with col_left:
        otd_colors = [_color_otd(v) for v in chart_otd_df["OTD %"]]
        fig_otd = go.Figure(go.Bar(
            x=chart_otd_df["OTD %"],
            y=chart_otd_df["Carrier"],
            orientation="h",
            marker_color=otd_colors,
            text=[f"{v}%" for v in chart_otd_df["OTD %"]],
            textposition="outside",
            hovertemplate="%{y}: %{x}%<extra></extra>",
        ))
        fig_otd.add_vline(
            x=90,
            line_dash="dash",
            line_color="#aaaaaa",
            annotation_text="Target 90%",
            annotation_position="top right",
            annotation_font_color="#aaaaaa",
        )
        fig_otd.update_layout(
            title="On-Time Delivery % by Carrier",
            template="plotly_white",
            xaxis=dict(range=[0, 115], title="OTD %"),
            yaxis=dict(title=""),
            height=380,
            margin=dict(l=10, r=70, t=50, b=30),
        )
        st.plotly_chart(fig_otd, use_container_width=True)

    with col_right:
        dq_sorted = sc_df.sort_values("Data Quality %", ascending=True)
        dq_colors = [_color_dq(v) for v in dq_sorted["Data Quality %"]]
        fig_dq = go.Figure(go.Bar(
            x=dq_sorted["Data Quality %"],
            y=dq_sorted["Carrier"],
            orientation="h",
            marker_color=dq_colors,
            text=[f"{v}%" for v in dq_sorted["Data Quality %"]],
            textposition="outside",
            hovertemplate="%{y}: %{x}%<extra></extra>",
        ))
        fig_dq.add_vline(
            x=95,
            line_dash="dash",
            line_color="#aaaaaa",
            annotation_text="Target 95%",
            annotation_position="top right",
            annotation_font_color="#aaaaaa",
        )
        fig_dq.update_layout(
            title="Data Quality % by Carrier",
            template="plotly_white",
            xaxis=dict(range=[0, 115], title="Data Quality %"),
            yaxis=dict(title=""),
            height=380,
            margin=dict(l=10, r=70, t=50, b=30),
        )
        st.plotly_chart(fig_dq, use_container_width=True)

    # Summary paragraph
    all_delivered = df[df["status"] == "delivered"]
    if len(all_delivered) > 0:
        net_otd = round(all_delivered["is_on_time"].sum() / len(all_delivered) * 100, 1)
    else:
        net_otd = 0.0

    all_dq_vals = []
    for _, r in df.iterrows():
        if r["milestones_expected"] > 0:
            all_dq_vals.append(r["milestones_received"] / r["milestones_expected"] * 100)
    avg_dq = round(sum(all_dq_vals) / len(all_dq_vals), 1) if all_dq_vals else 0.0

    at_risk_carriers = 0
    for _, sc_row in sc_df.iterrows():
        otd_v = sc_row["OTD %"]
        dq_v = sc_row["Data Quality %"]
        if (otd_v is not None and otd_v < 75) or (dq_v < 80):
            at_risk_carriers += 1

    st.markdown(
        f"**Network OTD: {net_otd}% | Avg data quality: {avg_dq}% | "
        f"{at_risk_carriers} carrier(s) at risk (OTD <75% or DQ <80%)**"
    )
