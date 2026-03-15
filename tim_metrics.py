#!/usr/bin/env python3
"""
TIM Metrics Assessor
--------------------
A carrier integration health assessment tool modelled on the metrics that
matter in a Technical Integration Manager role at a real-time transportation
visibility platform.

Tracks:
  - Carrier Tracking %        (shipments with active tracking data)
  - Data Quality Score         (milestone completeness)
  - SLA Adherence              (time-to-live vs. 30-day target; MTTR)
  - Integration Health         (error rate, connection status, sync recency)
  - Push Interval Health       (for push connections: are messages arriving on schedule?)

Provider types: carrier / tms / gps
Connection directions: push (carrier sends at intervals) / pull (p44 polls)

Usage:
  python tim_metrics.py sample_data.csv
  python tim_metrics.py sample_data.csv --sort tracking
  python tim_metrics.py sample_data.csv --filter error
  python tim_metrics.py sample_data.csv --provider tms
  python tim_metrics.py sample_data.csv --direction push
  python tim_metrics.py sample_data.csv --no-color
"""

import csv
import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ── Thresholds ────────────────────────────────────────────────────────────────
TRACKING_GREEN          = 90    # % — matches project44 Preferred Carrier benchmark
TRACKING_YELLOW         = 70
DATA_QUALITY_GREEN      = 95
DATA_QUALITY_YELLOW     = 80
SLA_TARGET_DAYS         = 30    # project44 TL carrier go-live SLA
ERROR_RATE_GREEN        = 2     # % of shipments
ERROR_RATE_YELLOW       = 5
SYNC_STALE_HOURS        = 24    # for pull connections: hours before considered stale
PUSH_OVERDUE_MULTIPLIER = 2.0   # push flagged late if gap > interval × this factor

console = Console() if HAS_RICH else None


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_date(s):
    """Parse common date formats; return None if blank or unrecognised."""
    if not s or not s.strip():
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def status_color(value, green_threshold, yellow_threshold, higher_is_better=True):
    if higher_is_better:
        if value >= green_threshold:   return 'green'
        elif value >= yellow_threshold: return 'yellow'
        return 'red'
    else:
        if value <= green_threshold:   return 'green'
        elif value <= yellow_threshold: return 'yellow'
        return 'red'


def rich(text, color):
    """Wrap text in rich colour markup if available."""
    return f"[{color}]{text}[/{color}]" if HAS_RICH else str(text)


def fmt_interval(minutes):
    """Display push interval in appropriate unit: minutes (<60) or hours (≥60)."""
    if minutes is None:
        return "?"
    if minutes < 60:
        return f"{minutes}min"
    hours = minutes / 60
    return f"{hours:.0f}h" if hours == int(hours) else f"{hours:.1f}h"


def fmt_duration(minutes):
    """Display a duration in appropriate unit."""
    if minutes is None:
        return "?"
    if minutes < 60:
        return f"{minutes:.0f}m"
    return f"{minutes/60:.1f}h"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_csv(filepath):
    path = Path(filepath)
    if not path.exists():
        sys.exit(f"Error: File not found — {filepath}")
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


# ── Metric calculations ───────────────────────────────────────────────────────

def calculate_metrics(record):
    now = datetime.now()
    m = {}

    total    = int(record.get('total_shipments', 0) or 0)
    tracked  = int(record.get('tracked_shipments', 0) or 0)
    expected = int(record.get('milestones_expected', 0) or 0)
    received = int(record.get('milestones_received', 0) or 0)
    errors   = int(record.get('error_count_30d', 0) or 0)

    # Provider / connection metadata
    m['provider_type']        = record.get('provider_type', 'carrier').strip().lower()
    m['connection_direction'] = record.get('connection_direction', 'push').strip().lower()

    # Tracking %
    m['tracking_pct'] = (tracked / total * 100) if total > 0 else 0.0

    # Data quality (milestone completeness)
    m['data_quality'] = (received / expected * 100) if expected > 0 else 0.0

    # SLA — time to go live
    start = parse_date(record.get('onboarding_start_date'))
    live  = parse_date(record.get('go_live_date'))
    if start and live:
        m['days_to_live']    = (live - start).days
        m['sla_met']         = m['days_to_live'] <= SLA_TARGET_DAYS
        m['days_onboarding'] = None
    elif start:
        m['days_to_live']    = None
        m['sla_met']         = None
        m['days_onboarding'] = (now - start).days
    else:
        m['days_to_live'] = m['sla_met'] = m['days_onboarding'] = None

    # MTTR
    reported = parse_date(record.get('issue_reported_date'))
    resolved = parse_date(record.get('issue_resolved_date'))
    if reported and resolved:
        m['mttr_hours'] = round((resolved - reported).total_seconds() / 3600, 1)
    else:
        m['mttr_hours'] = None

    # Integration health — common
    m['error_count'] = errors
    m['error_rate']  = (errors / total * 100) if total > 0 else 0.0
    m['status']      = record.get('integration_status', 'unknown').strip().lower()

    # ── Push-specific: interval health ────────────────────────────────────────
    push_interval = record.get('push_interval_minutes', '').strip()
    last_push     = parse_date(record.get('last_push_received', ''))

    if m['connection_direction'] == 'push' and push_interval:
        m['push_interval_minutes'] = int(push_interval)
        if last_push:
            mins_since = (now - last_push).total_seconds() / 60
            m['minutes_since_push'] = round(mins_since, 1)
            threshold = m['push_interval_minutes'] * PUSH_OVERDUE_MULTIPLIER
            m['push_on_schedule']   = mins_since <= threshold
            m['push_overdue_by']    = max(0.0, round(mins_since - m['push_interval_minutes'], 1))
        else:
            m['minutes_since_push'] = None
            m['push_on_schedule']   = False
            m['push_overdue_by']    = None
        # push connections don't use the generic sync stale flag
        m['hours_since_sync'] = round(m['minutes_since_push'] / 60, 1) if m['minutes_since_push'] is not None else None
        m['sync_stale']       = not m['push_on_schedule']
    else:
        m['push_interval_minutes'] = None
        m['minutes_since_push']    = None
        m['push_on_schedule']      = None
        m['push_overdue_by']       = None

        # Pull / non-push: use last_sync
        last_sync = parse_date(record.get('last_sync'))
        if last_sync:
            m['hours_since_sync'] = round((now - last_sync).total_seconds() / 3600, 1)
            m['sync_stale']       = m['hours_since_sync'] > SYNC_STALE_HOURS
        else:
            m['hours_since_sync'] = None
            m['sync_stale']       = True

    return m


def overall_score(m):
    """Weighted health score 0–100."""
    tracking_score = min(m['tracking_pct'], 100) * 0.35
    quality_score  = min(m['data_quality'], 100)  * 0.35
    sla_score      = (100 if m['sla_met'] else 40) * 0.15 if m['sla_met'] is not None else 75 * 0.15

    # For push connections, penalise overdue pushes; otherwise use error rate
    if m['connection_direction'] == 'push' and m['push_on_schedule'] is not None:
        push_health  = 100 if m['push_on_schedule'] else max(0, 100 - m['push_overdue_by'] / 10) if m['push_overdue_by'] else 0
        health_score = push_health * 0.15
    else:
        health_score = max(0, 100 - m['error_rate'] * 10) * 0.15

    return round(tracking_score + quality_score + sla_score + health_score, 1)


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_pct(value, green, yellow):
    color = status_color(value, green, yellow)
    return rich(f"{value:.1f}%", color)


def fmt_sla(m):
    if m['days_to_live'] is not None:
        color = 'green' if m['sla_met'] else 'red'
        mark  = '✓' if m['sla_met'] else '✗'
        return rich(f"{m['days_to_live']}d {mark}", color)
    if m['days_onboarding'] is not None:
        color = 'yellow' if m['days_onboarding'] <= SLA_TARGET_DAYS else 'red'
        return rich(f"{m['days_onboarding']}d (active)", color)
    return "N/A"


def fmt_connection(m):
    direction = m['connection_direction']
    if direction == 'push':
        if m['push_interval_minutes'] is not None:
            interval_label = fmt_interval(m['push_interval_minutes'])
            if m['push_on_schedule']:
                last = fmt_duration(m['minutes_since_push'])
                return rich(f"↑ push/{interval_label} | last {last} ago", 'green')
            else:
                overdue = fmt_duration(m['push_overdue_by'])
                return rich(f"↑ push/{interval_label} | overdue {overdue}", 'red')
        return rich("↑ push", 'yellow')
    else:
        sync = f"{m['hours_since_sync']:.1f}h ago" if m['hours_since_sync'] is not None else "never"
        color = 'red' if m['sync_stale'] else 'green'
        return rich(f"↓ pull | last {sync}", color)


def fmt_health(m):
    status = m['status']
    if status == 'error':
        color, icon = 'red', '✗'
    elif status == 'onboarding':
        color, icon = 'yellow', '⟳'
    elif m['sync_stale'] and status not in ('onboarding', 'inactive'):
        color, icon = 'red', '✗'
    elif m['error_count'] > 0:
        color, icon = 'yellow', '!'
    else:
        color, icon = 'green', '✓'
    return rich(f"{icon} {status} | {m['error_count']} err", color)


def fmt_score(score):
    color = 'green' if score >= 80 else 'yellow' if score >= 60 else 'red'
    return rich(f"{score}", color)


def fmt_provider(m):
    ptype = m['provider_type']
    color = {'carrier': 'cyan', 'tms': 'magenta', 'gps': 'green'}.get(ptype, 'white')
    return rich(ptype.upper(), color)


# ── Output sections ───────────────────────────────────────────────────────────

def print_summary(rows):
    n = len(rows)
    if n == 0:
        return

    avg_tracking = sum(m['tracking_pct'] for _, m, _ in rows) / n
    avg_quality  = sum(m['data_quality']  for _, m, _ in rows) / n
    avg_score    = sum(s                  for _, _, s in rows) / n

    sla_vals  = [m['sla_met'] for _, m, _ in rows if m['sla_met'] is not None]
    sla_rate  = (sum(sla_vals) / len(sla_vals) * 100) if sla_vals else 0.0

    active     = sum(1 for _, m, _ in rows if m['status'] == 'active')
    onboarding = sum(1 for _, m, _ in rows if m['status'] == 'onboarding')
    error      = sum(1 for _, m, _ in rows if m['status'] == 'error')

    push_rows  = [(c, m, s) for c, m, s in rows if m['connection_direction'] == 'push' and m['push_on_schedule'] is not None]
    push_ok    = sum(1 for _, m, _ in push_rows if m['push_on_schedule'])
    push_total = len(push_rows)
    push_rate  = (push_ok / push_total * 100) if push_total > 0 else None

    carriers = sum(1 for _, m, _ in rows if m['provider_type'] == 'carrier')
    tms      = sum(1 for _, m, _ in rows if m['provider_type'] == 'tms')
    gps      = sum(1 for _, m, _ in rows if m['provider_type'] == 'gps')

    tc  = status_color(avg_tracking, TRACKING_GREEN, TRACKING_YELLOW)
    qc  = status_color(avg_quality,  DATA_QUALITY_GREEN, DATA_QUALITY_YELLOW)
    sc  = 'green' if avg_score >= 80 else 'yellow' if avg_score >= 60 else 'red'
    slc = 'green' if sla_rate  >= 90 else 'yellow' if sla_rate  >= 70 else 'red'

    if HAS_RICH:
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        t.add_column("Metric", style="bold")
        t.add_column("Value")
        t.add_row("Total Integrations",
                  f"[cyan]{carriers} carriers[/cyan] · [magenta]{tms} TMS[/magenta] · [green]{gps} GPS[/green]")
        t.add_row("Active / Onboarding / Error",
                  f"[green]{active}[/green] / [yellow]{onboarding}[/yellow] / [red]{error}[/red]")
        t.add_row("Avg Tracking %",    f"[{tc}]{avg_tracking:.1f}%[/{tc}]")
        t.add_row("Avg Data Quality",  f"[{qc}]{avg_quality:.1f}%[/{qc}]")
        t.add_row("SLA Compliance",    f"[{slc}]{sla_rate:.1f}%[/{slc}]")
        if push_rate is not None:
            pc = 'green' if push_rate >= 90 else 'yellow' if push_rate >= 70 else 'red'
            t.add_row("Push On Schedule", f"[{pc}]{push_ok}/{push_total} ({push_rate:.0f}%)[/{pc}]")
        t.add_row("Avg Health Score",  f"[{sc}]{avg_score:.1f} / 100[/{sc}]")
        console.print(Panel(t, title="[bold cyan]Network Summary[/bold cyan]", border_style="cyan"))
    else:
        print("\n=== NETWORK SUMMARY ===")
        print(f"  Integrations        : {carriers} carriers · {tms} TMS · {gps} GPS")
        print(f"  Active/Onboard/Error: {active} / {onboarding} / {error}")
        print(f"  Avg Tracking %      : {avg_tracking:.1f}%")
        print(f"  Avg Data Quality    : {avg_quality:.1f}%")
        print(f"  SLA Compliance      : {sla_rate:.1f}%")
        if push_rate is not None:
            print(f"  Push On Schedule    : {push_ok}/{push_total} ({push_rate:.0f}%)")
        print(f"  Avg Health Score    : {avg_score:.1f} / 100")


def print_integration_table(rows):
    if HAS_RICH:
        t = Table(
            title="Integration Metrics",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold magenta",
        )
        t.add_column("Name",           min_width=22)
        t.add_column("Provider",       justify="center", min_width=8)
        t.add_column("Proto",          justify="center", min_width=6)
        t.add_column("Tracking %",     justify="right",  min_width=10)
        t.add_column("Data Quality",   justify="right",  min_width=11)
        t.add_column("SLA",            justify="center", min_width=12)
        t.add_column("Score",          justify="right",  min_width=6)
        t.add_column("Connection")
        t.add_column("Health")
        for record, m, score in rows:
            t.add_row(
                record.get('carrier_name', record.get('carrier_id', '?')),
                fmt_provider(m),
                record.get('integration_type', '?').upper(),
                fmt_pct(m['tracking_pct'], TRACKING_GREEN, TRACKING_YELLOW),
                fmt_pct(m['data_quality'],  DATA_QUALITY_GREEN, DATA_QUALITY_YELLOW),
                fmt_sla(m),
                fmt_score(score),
                fmt_connection(m),
                fmt_health(m),
            )
        console.print(t)
    else:
        hdr = f"{'Name':<24} {'Prov':<8} {'Proto':<6} {'Track%':>8} {'Quality':>9} {'SLA':>10} {'Score':>6}  Connection"
        print("\n" + hdr)
        print("─" * 100)
        for record, m, score in rows:
            name  = record.get('carrier_name', '?')[:23]
            ptype = m['provider_type'].upper()[:7]
            itype = record.get('integration_type', '?').upper()[:5]
            sla   = f"{m['days_to_live']}d" if m['days_to_live'] is not None else (
                    f"{m['days_onboarding']}d*" if m['days_onboarding'] is not None else "N/A")
            if m['connection_direction'] == 'push' and m['push_interval_minutes']:
                conn = f"push/{m['push_interval_minutes']}min {'OK' if m['push_on_schedule'] else 'LATE'}"
            else:
                sync = f"{m['hours_since_sync']:.0f}h" if m['hours_since_sync'] is not None else "?"
                conn = f"pull/{sync}"
            print(f"{name:<24} {ptype:<8} {itype:<6} {m['tracking_pct']:>7.1f}% {m['data_quality']:>8.1f}% "
                  f"{sla:>10} {score:>6.1f}  {conn}")


def print_attention_list(rows):
    flagged = []
    for record, m, score in rows:
        issues = []
        if m['tracking_pct'] < TRACKING_YELLOW:
            issues.append(f"Low tracking ({m['tracking_pct']:.1f}%)")
        if m['data_quality'] < DATA_QUALITY_YELLOW:
            issues.append(f"Poor data quality ({m['data_quality']:.1f}%)")
        if m['sla_met'] is False:
            issues.append(f"SLA breached ({m['days_to_live']}d > {SLA_TARGET_DAYS}d target)")
        if m['status'] == 'error':
            issues.append("Integration in error state")
        # Push-specific alert
        if m['connection_direction'] == 'push' and m['push_on_schedule'] is False:
            overdue = m['push_overdue_by']
            interval_label = fmt_interval(m['push_interval_minutes'])
            overdue_label  = fmt_duration(overdue) if overdue else None
            issues.append(
                f"Push overdue by {overdue_label} (expected every {interval_label})"
                if overdue_label else "Push messages not received"
            )
        # Pull-specific alert
        elif m['connection_direction'] == 'pull' and m['sync_stale'] and m['status'] not in ('onboarding', 'inactive'):
            h = m['hours_since_sync']
            issues.append(f"Stale pull ({h:.1f}h since last sync)" if h else "No sync recorded")
        if m['error_rate'] >= ERROR_RATE_YELLOW:
            issues.append(f"High error rate ({m['error_rate']:.1f}%)")
        if issues:
            flagged.append((record.get('carrier_name', '?'), issues, score))

    flagged.sort(key=lambda x: x[2])

    if HAS_RICH:
        if not flagged:
            console.print("[green]✓ All integrations within acceptable thresholds.[/green]\n")
            return
        t = Table(
            title="[bold red]Integrations Requiring Attention[/bold red]",
            box=box.ROUNDED, header_style="bold red",
        )
        t.add_column("Name")
        t.add_column("Issues")
        t.add_column("Score", justify="right")
        for name, issues, score in flagged:
            color = 'red' if score < 60 else 'yellow'
            t.add_row(name, "\n".join(f"• {i}" for i in issues), rich(str(score), color))
        console.print(t)
    else:
        if not flagged:
            print("\n✓ All integrations within acceptable thresholds.")
            return
        print("\n=== INTEGRATIONS REQUIRING ATTENTION ===")
        for name, issues, score in flagged:
            print(f"\n  {name}  (score: {score})")
            for issue in issues:
                print(f"    • {issue}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="TIM Metrics Assessor — integration health tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python tim_metrics.py sample_data.csv
  python tim_metrics.py sample_data.csv --sort tracking
  python tim_metrics.py sample_data.csv --filter error
  python tim_metrics.py sample_data.csv --provider tms
  python tim_metrics.py sample_data.csv --direction push
  python tim_metrics.py sample_data.csv --no-color > report.txt
        """,
    )
    parser.add_argument('csv_file',     help='Path to integration data CSV file')
    parser.add_argument('--sort',       choices=['score', 'tracking', 'quality', 'name'],
                        default='score', help='Sort order (default: score, worst first)')
    parser.add_argument('--filter',     choices=['all', 'active', 'onboarding', 'error', 'inactive'],
                        default='all',  help='Filter by integration status')
    parser.add_argument('--provider',   choices=['all', 'carrier', 'tms', 'gps'],
                        default='all',  help='Filter by provider type')
    parser.add_argument('--direction',  choices=['all', 'push', 'pull'],
                        default='all',  help='Filter by connection direction')
    parser.add_argument('--no-color',   action='store_true', help='Plain text output')
    args = parser.parse_args()

    global HAS_RICH
    if args.no_color:
        HAS_RICH = False

    raw = load_csv(args.csv_file)
    if not raw:
        sys.exit("No data found in file.")

    rows = [(c, calculate_metrics(c), 0.0) for c in raw]
    rows = [(c, m, overall_score(m)) for c, m, _ in rows]

    if args.filter    != 'all':
        rows = [(c, m, s) for c, m, s in rows if m['status']               == args.filter]
    if args.provider  != 'all':
        rows = [(c, m, s) for c, m, s in rows if m['provider_type']        == args.provider]
    if args.direction != 'all':
        rows = [(c, m, s) for c, m, s in rows if m['connection_direction'] == args.direction]

    sort_key = {
        'score':    lambda x: x[2],
        'tracking': lambda x: x[1]['tracking_pct'],
        'quality':  lambda x: x[1]['data_quality'],
        'name':     lambda x: x[0].get('carrier_name', ''),
    }[args.sort]
    rows.sort(key=sort_key)

    if HAS_RICH:
        console.print()
        console.rule("[bold cyan]TIM Metrics Assessor[/bold cyan]")
        console.print(
            f"[dim]File: {args.csv_file}  |  "
            f"Integrations loaded: {len(rows)}  |  "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]\n"
        )
    else:
        print(f"\n=== TIM METRICS ASSESSOR ===")
        print(f"File: {args.csv_file}  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print_summary(rows)
    print_integration_table(rows)
    print_attention_list(rows)

    if HAS_RICH:
        console.print()
        console.rule(style="dim")


if __name__ == '__main__':
    main()
