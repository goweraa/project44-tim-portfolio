#!/usr/bin/env python3
"""
RCA Summarizer — AI-Powered Root Cause Analysis for Integration Errors
Uses Claude claude-opus-4-6 with adaptive thinking to diagnose carrier/TMS/GPS integration failures.

Usage:
  python3 rca_summarizer.py sample_errors/edi_parse_errors.json
  python3 rca_summarizer.py sample_errors/api_push_gap.json --save
  python3 rca_summarizer.py sample_errors/tms_sync_failure.json --save --out reports/
  python3 rca_summarizer.py --paste           (interactive: paste logs then Ctrl+D)
  python3 rca_summarizer.py --metrics sample_data.csv   (analyse integration health CSV)
"""

import argparse
import json
import sys
import os
import csv
from datetime import datetime
from pathlib import Path

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

console = Console()

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Senior Technical Integration Manager at a real-time transportation \
visibility platform. You specialise in diagnosing integration failures across carrier EDI feeds, \
GPS telematics APIs, and TMS synchronisation pipelines.

When given raw integration logs or metrics data, you produce a concise Root Cause Analysis (RCA) \
report. Your reports are read by two audiences:
1. Engineers — who need the exact technical cause and fix steps
2. Account managers / customer success — who need a plain-English stakeholder note

Always structure your response exactly as follows (use these exact headings):

## Root Cause
One or two sentences identifying the precise technical cause.

## Evidence
Bullet points citing specific log entries, error codes, timestamps, or metric values that \
confirm the diagnosis. Be specific — quote exact values.

## Impact
What was affected: which carriers/providers, how many shipments, which milestones/metrics, \
duration of the outage/degradation.

## Recommended Fix
Numbered step-by-step remediation actions, ordered by priority.

## Prevention
Two or three concrete measures to prevent recurrence (monitoring rules, process changes, \
or technical improvements).

## Stakeholder Note
A 2–3 sentence plain-English summary suitable for an account manager to send to a customer. \
No jargon. Focus on what happened, how long, and what was done.

Be direct and precise. Do not speculate beyond what the data shows."""


def build_user_prompt(log_text: str, source_label: str) -> str:
    return f"""Analyse the following integration log data from {source_label} and produce a \
Root Cause Analysis report.

<log_data>
{log_text}
</log_data>

Identify the root cause, evidence, impact, remediation steps, and prevention measures. \
Then write a short stakeholder note."""


def build_metrics_prompt(csv_text: str) -> str:
    return f"""Analyse the following integration health metrics CSV from the TIM monitoring \
system and produce a Root Cause Analysis report for all integrations showing errors or \
degraded performance.

Focus on integrations where:
- integration_status is 'error'
- tracking % is below 90%
- milestone completeness (milestones_received / milestones_expected) is below 95%
- error_count_30d is high relative to shipment volume

<metrics_csv>
{csv_text}
</metrics_csv>

Identify the root causes, evidence, impact, remediation steps, and prevention measures \
for the problem integrations. Then write a short stakeholder note."""


# ── Input helpers ─────────────────────────────────────────────────────────────

def read_log_file(path: str) -> tuple[str, str]:
    """Return (log_text, source_label)."""
    p = Path(path)
    if not p.exists():
        console.print(f"[red]File not found:[/] {path}")
        sys.exit(1)

    raw = p.read_text(encoding="utf-8")

    if p.suffix.lower() == ".json":
        try:
            parsed = json.loads(raw)
            # Pretty-print for the model
            text = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            text = raw
    else:
        text = raw

    label = p.name
    return text, label


def read_paste() -> tuple[str, str]:
    """Read from stdin until EOF (Ctrl+D)."""
    console.print(
        Panel(
            "[bold]Paste your log data below, then press [cyan]Ctrl+D[/] (Linux/Mac) "
            "or [cyan]Ctrl+Z + Enter[/] (Windows) to submit.[/]",
            title="Paste Mode",
            border_style="cyan",
        )
    )
    lines = sys.stdin.read()
    if not lines.strip():
        console.print("[red]No input received.[/]")
        sys.exit(1)
    return lines, "pasted input"


def read_metrics_csv(path: str) -> tuple[str, str]:
    """Read metrics CSV and return as formatted text."""
    p = Path(path)
    if not p.exists():
        console.print(f"[red]File not found:[/] {path}")
        sys.exit(1)
    return p.read_text(encoding="utf-8"), f"metrics file: {p.name}"


# ── Claude API call ───────────────────────────────────────────────────────────

def run_rca(log_text: str, source_label: str, is_metrics: bool = False) -> str:
    """Call Claude claude-opus-4-6 with adaptive thinking + streaming. Returns full RCA text."""
    client = anthropic.Anthropic()

    user_prompt = (
        build_metrics_prompt(log_text)
        if is_metrics
        else build_user_prompt(log_text, source_label)
    )

    console.print()
    console.print(Rule("[bold cyan]Analysing with Claude claude-opus-4-6[/]", style="cyan"))
    console.print()

    rca_chunks: list[str] = []
    thinking_shown = False

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "thinking" and not thinking_shown:
                    console.print("[dim italic]Claude is reasoning...[/]")
                    thinking_shown = True
                elif event.content_block.type == "text":
                    if thinking_shown:
                        console.print()
                    console.print(Rule("[bold green]Root Cause Analysis[/]", style="green"))
                    console.print()

            elif event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    text = event.delta.text
                    rca_chunks.append(text)
                    # Stream live to terminal
                    console.print(text, end="", highlight=False)

    console.print()  # newline after stream ends
    return "".join(rca_chunks)


# ── Output ────────────────────────────────────────────────────────────────────

def save_report(rca_text: str, source_label: str, out_dir: str | None) -> str:
    """Save RCA to a markdown file. Returns the file path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitise source label for filename
    safe_label = (
        Path(source_label).stem
        if source_label != "pasted input"
        else "pasted"
    )
    filename = f"rca_{safe_label}_{timestamp}.md"

    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        filepath = Path(out_dir) / filename
    else:
        filepath = Path(filename)

    header = (
        f"# Root Cause Analysis Report\n\n"
        f"**Source:** {source_label}  \n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
        f"**Model:** claude-opus-4-6 (adaptive thinking)\n\n---\n\n"
    )

    filepath.write_text(header + rca_text, encoding="utf-8")
    return str(filepath)


def print_summary_header(source_label: str, is_metrics: bool) -> None:
    mode = "Metrics Analysis" if is_metrics else "Log Analysis"
    console.print(
        Panel(
            Text.assemble(
                ("Mode: ", "bold"),
                (mode + "\n", "cyan"),
                ("Source: ", "bold"),
                (source_label, "yellow"),
            ),
            title="[bold]TIM RCA Summarizer[/]",
            border_style="blue",
        )
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-powered Root Cause Analysis for integration errors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "logfile",
        nargs="?",
        help="Path to a JSON or text log file",
    )
    input_group.add_argument(
        "--paste",
        action="store_true",
        help="Read log data interactively from stdin",
    )
    input_group.add_argument(
        "--metrics",
        metavar="CSV",
        help="Analyse the integration health CSV from the TIM monitor",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the RCA report to a markdown file",
    )
    parser.add_argument(
        "--out",
        metavar="DIR",
        default=None,
        help="Directory to save the report (default: current directory)",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    is_metrics = bool(args.metrics)

    # --- Load input ---
    if args.paste:
        log_text, source_label = read_paste()
    elif args.metrics:
        log_text, source_label = read_metrics_csv(args.metrics)
    else:
        log_text, source_label = read_log_file(args.logfile)

    print_summary_header(source_label, is_metrics)

    # --- Run analysis ---
    try:
        rca_text = run_rca(log_text, source_label, is_metrics=is_metrics)
    except anthropic.AuthenticationError:
        console.print("\n[red bold]Authentication error.[/] Check your ANTHROPIC_API_KEY.")
        sys.exit(1)
    except anthropic.APIConnectionError:
        console.print("\n[red bold]Connection error.[/] Check your internet connection.")
        sys.exit(1)
    except anthropic.RateLimitError:
        console.print("\n[red bold]Rate limited.[/] Wait a moment and retry.")
        sys.exit(1)
    except anthropic.APIStatusError as e:
        console.print(f"\n[red bold]API error {e.status_code}:[/] {e.message}")
        sys.exit(1)

    # --- Save if requested ---
    if args.save:
        saved_path = save_report(rca_text, source_label, args.out)
        console.print()
        console.print(Rule(style="green"))
        console.print(f"[bold green]Report saved:[/] {saved_path}")

    console.print()


if __name__ == "__main__":
    main()
