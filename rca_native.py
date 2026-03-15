#!/usr/bin/env python3
"""
RCA Native — Rule-Based Root Cause Analysis for Integration Errors
Detects known failure patterns without AI. Instant, offline, deterministic.

Usage:
  python3 rca_native.py sample_errors/edi_parse_errors.json
  python3 rca_native.py sample_errors/api_push_gap.json --save
  python3 rca_native.py sample_errors/tms_sync_failure.json --save --out reports/
  python3 rca_native.py --metrics sample_data.csv
  python3 rca_native.py --paste
"""

import argparse
import json
import sys
import csv
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule as RichRule
from rich.table import Table
from rich.text import Text
from rich import box

from rca_rules import detect, RCAReport

console = Console()

# ── Severity colours ───────────────────────────────────────────────────────────

SEVERITY_STYLE = {
    "CRITICAL": "bold red",
    "HIGH":     "bold yellow",
    "MEDIUM":   "bold blue",
    "LOW":      "dim",
}

SEVERITY_ICON = {
    "CRITICAL": "✖",
    "HIGH":     "▲",
    "MEDIUM":   "●",
    "LOW":      "○",
}

# ── Metrics analysis ──────────────────────────────────────────────────────────

def analyse_metrics_csv(csv_text: str) -> list[RCAReport]:
    """
    Parse the integration health CSV and synthesise rule-based RCA reports
    for any integration that is in an error state or below threshold.
    """
    from rca_rules import RCAReport

    reader = csv.DictReader(csv_text.splitlines())
    rows = list(reader)
    reports: list[RCAReport] = []

    for row in rows:
        status = row.get("integration_status", "").lower()
        if status not in ("error", "active", "onboarding", "inactive"):
            continue

        name = row.get("carrier_name", "Unknown")
        itype = row.get("integration_type", "?")
        direction = row.get("connection_direction", "?")
        error_count = int(row.get("error_count_30d") or 0)
        milestones_exp = int(row.get("milestones_expected") or 0)
        milestones_rec = int(row.get("milestones_received") or 0)
        total_ships = int(row.get("total_shipments") or 0)
        tracked = int(row.get("tracked_shipments") or 0)
        last_error = row.get("last_error_date", "")
        issue_open = row.get("issue_reported_date", "") and not row.get("issue_resolved_date", "")

        tracking_pct = (tracked / total_ships * 100) if total_ships else 100
        quality_pct  = (milestones_rec / milestones_exp * 100) if milestones_exp else 100

        problems: list[str] = []
        if status == "error":
            problems.append("error_status")
        if status == "inactive":
            problems.append("inactive")
        if tracking_pct < 90 and total_ships > 0:
            problems.append("tracking_below_threshold")
        if quality_pct < 95 and milestones_exp > 0:
            problems.append("quality_below_threshold")
        if error_count > 10:
            problems.append("high_error_count")

        if not problems:
            continue

        # Determine severity
        if status == "error" or tracking_pct < 70 or quality_pct < 70:
            sev = "CRITICAL"
        elif tracking_pct < 90 or quality_pct < 90 or error_count > 20:
            sev = "HIGH"
        else:
            sev = "MEDIUM"

        evidence: list[str] = []
        if status == "error":
            evidence.append(f"integration_status = 'error'")
        if status == "inactive":
            evidence.append(f"integration_status = 'inactive' (no data flowing)")
        if tracking_pct < 90 and total_ships > 0:
            evidence.append(
                f"Tracking rate: {tracking_pct:.1f}% ({tracked}/{total_ships} shipments) "
                f"— below 90% target"
            )
        if quality_pct < 95 and milestones_exp > 0:
            evidence.append(
                f"Milestone completeness: {quality_pct:.1f}% "
                f"({milestones_rec}/{milestones_exp}) — below 95% target"
            )
        if error_count > 0:
            evidence.append(
                f"{error_count} errors in last 30 days"
                + (f" (last: {last_error})" if last_error else "")
            )
        if issue_open:
            evidence.append(
                f"Open issue reported {row['issue_reported_date']} — not yet resolved"
            )

        # Contextual root cause by integration type
        if status == "error" and itype == "EDI":
            root_cause = (
                f"{name} EDI feed is in error state. Likely cause: repeated "
                f"parse failures in recent EDI-214 batches (check EDI error logs). "
                f"Milestone pipeline is suppressing rejected transaction sets."
            )
            fix_steps = [
                "Review EDI parse logs for this carrier for INVALID_ELEMENT or "
                "SEGMENT_NOT_FOUND errors.",
                "Identify the specific element/value causing rejections.",
                "Contact the carrier EDI team with the error detail and request a fix.",
                "Request retransmission of affected transaction sets after the fix.",
            ]
        elif status == "error" and itype == "API" and direction == "push":
            root_cause = (
                f"{name} API push feed is in error state. Likely cause: "
                f"carrier-side API outage or authentication failure causing "
                f"the push endpoint to become unavailable."
            )
            fix_steps = [
                "Check HTTP error logs for this carrier — look for 401, 403, 503.",
                "If 401/403: rotate API credentials and test connectivity.",
                "If 503: check carrier API status page and await recovery.",
                "Confirm push data resumes within the expected interval once resolved.",
            ]
        elif status == "error":
            root_cause = (
                f"{name} integration is in error state "
                f"(type: {itype}, direction: {direction}). "
                f"Manual investigation of integration logs required."
            )
            fix_steps = [
                "Pull the integration error logs for this carrier.",
                "Identify the most recent error event and root cause.",
                "Engage the carrier/provider technical team.",
            ]
        elif status == "inactive":
            root_cause = (
                f"{name} integration is inactive — no data has been received. "
                f"The carrier may have been offboarded or the integration "
                f"deactivated intentionally."
            )
            fix_steps = [
                "Confirm with the account team whether this integration is "
                "intentionally inactive.",
                "If it should be active, re-initiate the onboarding process.",
            ]
        elif quality_pct < 95:
            root_cause = (
                f"{name} milestone completeness is at {quality_pct:.1f}% — "
                f"below the 95% target. Some shipment events are not reaching "
                f"the visibility platform. May indicate partial EDI/API failures "
                f"or mapping gaps in the integration configuration."
            )
            fix_steps = [
                "Compare milestones expected vs received for the last 30 days.",
                "Check for any MILESTONE_REJECTED or SEGMENT_SKIPPED events in logs.",
                "Verify the integration field mapping covers all required event codes.",
                "If EDI: confirm the carrier is transmitting all milestone codes.",
            ]
        else:
            root_cause = (
                f"{name} tracking rate is at {tracking_pct:.1f}% — "
                f"below the 90% target. Some shipments are not receiving "
                f"any tracking updates."
            )
            fix_steps = [
                "Identify shipments with zero tracking events in the last 30 days.",
                "Check whether those shipments were tendered to the carrier correctly.",
                "Verify the carrier is sending tracking data for all accepted tenders.",
            ]

        prevention = [
            "Set automated alerting when tracking rate drops below 90% or "
            "milestone completeness below 95% for more than 2 consecutive hours.",
            "Schedule a monthly integration health review for all carriers "
            "with error_count_30d > 5.",
            "Include a data quality SLA in the carrier integration agreement.",
        ]

        note = (
            f"The {name} integration is currently experiencing data quality issues. "
            f"Our team is investigating and will provide an update once root cause "
            f"is confirmed and remediation is underway."
        )

        reports.append(RCAReport(
            rule_name=f"Metrics: {name}",
            severity=sev,
            root_cause=root_cause,
            evidence=evidence,
            impact=(
                f"{name} ({itype}, {direction}): "
                + (f"tracking {tracking_pct:.1f}%, " if total_ships else "")
                + (f"milestone completeness {quality_pct:.1f}%, " if milestones_exp else "")
                + f"{error_count} errors/30d."
            ),
            fix_steps=fix_steps,
            prevention=prevention,
            stakeholder_note=note,
        ))

    return reports


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_report(report: RCAReport, index: int = 1, total: int = 1) -> None:
    sev_style = SEVERITY_STYLE.get(report.severity, "")
    sev_icon  = SEVERITY_ICON.get(report.severity, "●")

    header = Text.assemble(
        (f"{sev_icon} ", sev_style),
        (report.rule_name, "bold"),
        ("  ·  ", "dim"),
        (report.severity, sev_style),
    )
    if total > 1:
        header = Text.assemble(
            (f"[{index}/{total}] ", "dim"),
            header,
        )

    console.print()
    console.print(Panel(header, border_style=sev_style.split()[-1] if sev_style else "white"))

    # Root Cause
    console.print(RichRule("[bold]Root Cause[/]", style="cyan"))
    console.print(report.root_cause)
    console.print()

    # Evidence
    console.print(RichRule("[bold]Evidence[/]", style="cyan"))
    for point in report.evidence:
        console.print(f"  [cyan]•[/] {point}")
    console.print()

    # Impact
    console.print(RichRule("[bold]Impact[/]", style="cyan"))
    console.print(report.impact)
    if report.outage_minutes is not None:
        h, m = divmod(report.outage_minutes, 60)
        duration = f"{h}h {m}min" if h else f"{report.outage_minutes}min"
        recovered_str = "[green]Recovered[/]" if report.recovered else "[red]Ongoing[/]"
        console.print(
            f"  Outage duration: [bold]{duration}[/]  Status: {recovered_str}"
        )
    console.print()

    # Recommended Fix
    console.print(RichRule("[bold]Recommended Fix[/]", style="cyan"))
    for i, step in enumerate(report.fix_steps, 1):
        console.print(f"  [bold cyan]{i}.[/] {step}")
    console.print()

    # Prevention
    console.print(RichRule("[bold]Prevention[/]", style="cyan"))
    for point in report.prevention:
        console.print(f"  [cyan]▸[/] {point}")
    console.print()

    # Stakeholder Note
    console.print(RichRule("[bold]Stakeholder Note[/]", style="cyan"))
    console.print(
        Panel(
            report.stakeholder_note,
            border_style="green",
            subtitle="[dim]Plain-English summary for account managers[/]",
        )
    )


def render_no_match(source_label: str) -> None:
    console.print()
    console.print(
        Panel(
            Text.assemble(
                ("No known error patterns detected in ", ""),
                (source_label, "bold yellow"),
                (".\n\n", ""),
                ("This may mean:\n", "dim"),
                ("  • The log contains only successful events\n", "dim"),
                ("  • The error type is not yet covered by a rule\n", "dim"),
                ("  • The log format is not recognised\n", "dim"),
            ),
            title="No Match",
            border_style="yellow",
        )
    )


# ── Save ──────────────────────────────────────────────────────────────────────

def report_to_markdown(report: RCAReport, source_label: str) -> str:
    lines = [
        "# Root Cause Analysis Report\n",
        f"**Source:** {source_label}  ",
        f"**Rule:** {report.rule_name}  ",
        f"**Severity:** {report.severity}  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        "\n---\n",
        "## Root Cause",
        report.root_cause,
        "",
        "## Evidence",
    ]
    for p in report.evidence:
        lines.append(f"- {p}")
    lines += [
        "",
        "## Impact",
        report.impact,
    ]
    if report.outage_minutes is not None:
        h, m = divmod(report.outage_minutes, 60)
        duration = f"{h}h {m}min" if h else f"{report.outage_minutes}min"
        status = "Recovered" if report.recovered else "Ongoing"
        lines.append(f"\n**Outage duration:** {duration}  **Status:** {status}")
    lines += ["", "## Recommended Fix"]
    for i, step in enumerate(report.fix_steps, 1):
        lines.append(f"{i}. {step}")
    lines += ["", "## Prevention"]
    for p in report.prevention:
        lines.append(f"- {p}")
    lines += ["", "## Stakeholder Note", report.stakeholder_note, ""]
    return "\n".join(lines)


def save_reports(reports: list[RCAReport], source_label: str, out_dir: str | None) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = (
        Path(source_label).stem
        if source_label not in ("pasted input",)
        else "pasted"
    )
    safe_label = safe_label.replace("metrics file: ", "metrics_")

    for i, report in enumerate(reports, 1):
        suffix = f"_{i}" if len(reports) > 1 else ""
        filename = f"rca_{safe_label}{suffix}_{timestamp}.md"

        if out_dir:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            filepath = Path(out_dir) / filename
        else:
            filepath = Path(filename)

        filepath.write_text(report_to_markdown(report, source_label), encoding="utf-8")
        console.print(f"[bold green]Saved:[/] {filepath}")


# ── Input helpers ─────────────────────────────────────────────────────────────

def load_events(path: str) -> tuple[list[dict], str]:
    p = Path(path)
    if not p.exists():
        console.print(f"[red]File not found:[/] {path}")
        sys.exit(1)
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
        events = data if isinstance(data, list) else [data]
    except json.JSONDecodeError as e:
        console.print(f"[red]JSON parse error:[/] {e}")
        sys.exit(1)
    return events, p.name


def load_paste() -> tuple[list[dict], str]:
    console.print(
        Panel(
            "[bold]Paste JSON log data, then press [cyan]Ctrl+D[/] (Linux/Mac) "
            "or [cyan]Ctrl+Z + Enter[/] (Windows).[/]",
            title="Paste Mode",
            border_style="cyan",
        )
    )
    raw = sys.stdin.read()
    if not raw.strip():
        console.print("[red]No input received.[/]")
        sys.exit(1)
    try:
        data = json.loads(raw)
        events = data if isinstance(data, list) else [data]
    except json.JSONDecodeError as e:
        console.print(f"[red]JSON parse error:[/] {e}")
        sys.exit(1)
    return events, "pasted input"


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rule-based RCA — no AI, instant, offline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("logfile", nargs="?", help="JSON log file")
    input_group.add_argument("--paste", action="store_true", help="Read from stdin")
    input_group.add_argument("--metrics", metavar="CSV", help="Integration health CSV")
    parser.add_argument("--save", action="store_true", help="Save report(s) to markdown")
    parser.add_argument("--out", metavar="DIR", default=None, help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Banner ────────────────────────────────────────────────────────────────
    console.print(
        Panel(
            Text.assemble(
                ("TIM RCA Native  ", "bold"),
                ("·  Rule-based · No AI · Deterministic", "dim"),
            ),
            border_style="blue",
        )
    )

    # ── Load input and detect ─────────────────────────────────────────────────
    if args.metrics:
        p = Path(args.metrics)
        if not p.exists():
            console.print(f"[red]File not found:[/] {args.metrics}")
            sys.exit(1)
        source_label = f"metrics file: {p.name}"
        console.print(f"[dim]Analysing metrics CSV:[/] {p.name}")
        reports = analyse_metrics_csv(p.read_text(encoding="utf-8"))

    else:
        if args.paste:
            events, source_label = load_paste()
        else:
            events, source_label = load_events(args.logfile)

        console.print(
            f"[dim]Loaded [bold]{len(events)}[/] events from [bold]{source_label}[/][/]"
        )
        reports = detect(events)

    # ── Render ────────────────────────────────────────────────────────────────
    if not reports:
        render_no_match(source_label)
        sys.exit(0)

    console.print(
        f"\n[bold]Found [green]{len(reports)}[/green] matching rule(s)[/]"
    )

    for i, report in enumerate(reports, 1):
        render_report(report, index=i, total=len(reports))

    # ── Save ──────────────────────────────────────────────────────────────────
    if args.save:
        console.print()
        console.print(RichRule(style="green"))
        save_reports(reports, source_label, args.out)

    console.print()


if __name__ == "__main__":
    main()
