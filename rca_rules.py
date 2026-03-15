"""
Rule-based RCA engine — pattern detectors for integration error logs.

Each Rule class implements:
  matches(events)  -> bool
  analyse(events)  -> RCAReport
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class RCAReport:
    rule_name: str
    severity: str          # CRITICAL | HIGH | MEDIUM | LOW
    root_cause: str
    evidence: list[str]
    impact: str
    fix_steps: list[str]
    prevention: list[str]
    stakeholder_note: str
    outage_minutes: int | None = None   # None = not a timed outage
    recovered: bool = False


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ts(event: dict) -> datetime | None:
    raw = event.get("timestamp")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _gap_minutes(t1: datetime | None, t2: datetime | None) -> int | None:
    if t1 and t2:
        return int(abs((t2 - t1).total_seconds()) / 60)
    return None


def _fmt_ts(event: dict) -> str:
    return event.get("timestamp", "unknown time")


def _carrier(events: list[dict]) -> str:
    for e in events:
        v = e.get("carrier") or e.get("provider")
        if v:
            return v
    return "Unknown provider"


def _scac(events: list[dict]) -> str:
    for e in events:
        if e.get("scac"):
            return e["scac"]
    return ""


# ── Rule base ──────────────────────────────────────────────────────────────────

class Rule:
    name: str = "BaseRule"
    priority: int = 0   # higher = checked first

    def matches(self, events: list[dict]) -> bool:
        raise NotImplementedError

    def analyse(self, events: list[dict]) -> RCAReport:
        raise NotImplementedError


# ── Rule 1 — EDI Invalid Element ──────────────────────────────────────────────

class EDIInvalidElementRule(Rule):
    """Repeated INVALID_ELEMENT errors in an EDI file batch."""

    name = "EDI Invalid Element"
    priority = 90

    def matches(self, events: list[dict]) -> bool:
        return any(e.get("error") == "INVALID_ELEMENT" for e in events)

    def analyse(self, events: list[dict]) -> RCAReport:
        bad = [e for e in events if e.get("error") == "INVALID_ELEMENT"]
        rejected = [e for e in events if e.get("error") == "MILESTONE_REJECTED"]
        quality_drop = next(
            (e for e in events if e.get("rule") == "DATA_QUALITY_DROP"), None
        )
        completions = [
            e for e in events if e.get("event") == "FILE_COMPLETE"
        ]

        # Characterise the bad element
        segments  = {e.get("segment", "?") for e in bad}
        elements  = {e.get("element", "?") for e in bad}
        details   = bad[0].get("details", "") if bad else ""

        # Extract the bad value and expected values from the first detail string
        # e.g. "Unrecognised Time Code value 'XX'. Expected: CT, ET, MT, PT, UT, LT"
        bad_value = ""
        expected  = ""
        if "value '" in details:
            try:
                bad_value = details.split("value '")[1].split("'")[0]
            except IndexError:
                pass
        if "Expected:" in details:
            expected = details.split("Expected:")[1].strip()

        carrier   = _carrier(events)
        scac      = _scac(events)

        # Total failed transaction sets across all files
        total_failed = sum(c.get("transaction_sets_failed", 0) for c in completions)
        total_sets   = sum(c.get("transaction_sets_processed", 0) for c in completions)
        affected_bols = {e.get("bol") for e in bad if e.get("bol")} | \
                        {e.get("bol") for e in rejected if e.get("bol")}

        severity = "CRITICAL" if (quality_drop or total_failed > 10) else "HIGH"

        evidence = [
            f"{len(bad)} INVALID_ELEMENT errors on segment "
            f"{'/'.join(segments)}, element {'/'.join(elements)}",
        ]
        if bad_value:
            evidence.append(
                f"Unrecognised value '{bad_value}' — expected values: {expected}"
            )
        if bad:
            evidence.append(
                f"First occurrence: {_fmt_ts(bad[0])} "
                f"(transaction set {bad[0].get('transaction_set_control', '?')})"
            )
        for c in completions:
            failed = c.get("transaction_sets_failed", 0)
            total  = c.get("transaction_sets_processed", 0)
            fname  = c.get("filename", "unknown file")
            evidence.append(
                f"{fname}: {failed}/{total} transaction sets failed "
                f"({int(failed/total*100) if total else 0}% failure rate)"
            )
        if rejected:
            evidence.append(
                f"{len(rejected)} MILESTONE_REJECTED event(s) — "
                f"shipment milestones suppressed from visibility dashboard"
            )
        if quality_drop:
            evidence.append(
                f"DATA_QUALITY_DROP alert at {_fmt_ts(quality_drop)}: "
                f"milestone completeness {quality_drop.get('current_value')} "
                f"(was {quality_drop.get('threshold', '?')} threshold, "
                f"30-day avg {quality_drop.get('message', '').split('from ')[-1].split(' in')[0]})"
            )

        impacted_milestones = sum(
            e.get("affected_milestones", 0) for e in rejected
        )

        impact = (
            f"{carrier} ({scac}): {total_failed} of {total_sets} EDI-214 transaction sets "
            f"rejected across {len(completions)} file batch(es). "
        )
        if affected_bols:
            impact += f"{len(affected_bols)} unique BOL(s) affected. "
        if impacted_milestones:
            impact += (
                f"{impacted_milestones} shipment milestone(s) suppressed from the "
                f"visibility dashboard. "
            )
        if quality_drop:
            impact += (
                f"Milestone completeness degraded to "
                f"{quality_drop.get('current_value')} (threshold: "
                f"{quality_drop.get('threshold', '?')})."
            )

        element_label = "/".join(elements) if elements else "unknown element"
        segment_label = "/".join(segments) if segments else "unknown segment"

        fix_steps = [
            f"Contact {carrier} EDI team and provide the error log — "
            f"segment {segment_label}, element {element_label} is sending "
            f"'{bad_value}' which is not a valid code.",
            f"Request the carrier correct the Time Code field to one of the "
            f"accepted values: {expected}." if expected else
            f"Request the carrier correct the {element_label} field to a valid value.",
            "Once the carrier confirms the fix, request a retransmission of "
            "the affected transaction sets.",
            "After retransmission, verify milestone completeness returns to "
            "≥95% in the TIM dashboard.",
            "Manually trigger a data reconciliation job to backfill any "
            "suppressed milestones for the affected shipments.",
        ]

        prevention = [
            f"Add an EDI pre-validation rule that rejects files with "
            f"unrecognised {element_label} values before they reach the "
            "milestone pipeline, and fires an alert immediately.",
            "Include accepted code values in the carrier EDI onboarding "
            "guide so mapping errors are caught before go-live.",
            "Set a DATA_QUALITY_DROP alert threshold at ≥80% completeness "
            "with auto-escalation if not resolved within 30 minutes.",
        ]

        note = (
            f"We experienced a data quality issue with {carrier}'s EDI shipment "
            f"update feed today. A non-standard code value in the carrier's files "
            f"caused {total_failed} updates to be rejected, temporarily reducing "
            f"shipment milestone visibility. We have notified the carrier and "
            f"requested a corrected retransmission; no shipment deliveries were "
            f"affected — only the real-time tracking updates in the portal."
        )

        return RCAReport(
            rule_name=self.name,
            severity=severity,
            root_cause=(
                f"The {carrier} EDI-214 feed is populating {segment_label} element "
                f"{element_label} with the value '{bad_value}', which is not a "
                f"recognised code in the X12 specification. The integration parser "
                f"rejects every transaction set containing this value, preventing "
                f"the milestones from reaching the visibility platform."
            ),
            evidence=evidence,
            impact=impact,
            fix_steps=fix_steps,
            prevention=prevention,
            stakeholder_note=note,
        )


# ── Rule 2 — API Push Gap / Carrier Endpoint Down ─────────────────────────────

class APIPushGapRule(Rule):
    """GPS or carrier API feed goes silent — push gap exceeds 2× interval."""

    name = "API Push Gap"
    priority = 80

    def matches(self, events: list[dict]) -> bool:
        return any(
            e.get("event") in ("PUSH_OVERDUE", "PUSH_MISSED", "PUSH_HEALTH_BREACH")
            or e.get("rule") in ("PUSH_HEALTH_BREACH", "CARRIER_API_DOWN")
            for e in events
        )

    def analyse(self, events: list[dict]) -> RCAReport:
        overdue_events = [
            e for e in events if e.get("event") in ("PUSH_OVERDUE", "PUSH_MISSED")
        ]
        http_errors = [e for e in events if e.get("event") == "HTTP_ERROR"]
        breach_alert = next(
            (e for e in events if e.get("rule") == "PUSH_HEALTH_BREACH"), None
        )
        down_alert   = next(
            (e for e in events if e.get("rule") == "CARRIER_API_DOWN"), None
        )
        recovery     = next(
            (e for e in events if e.get("status") == "RECOVERED"), None
        )
        last_ok      = next(
            (e for e in events if e.get("event") == "PUSH_RECEIVED"
             and e.get("status") == "OK"), None
        )

        carrier  = _carrier(events)
        interval = None
        for e in events:
            if e.get("push_interval_minutes"):
                interval = e["push_interval_minutes"]
                break

        # Determine outage duration
        outage_minutes = None
        if recovery:
            outage_minutes = recovery.get("minutes_since_last_push")
        elif overdue_events:
            max_gap = max(
                e.get("minutes_since_last_push", 0) for e in overdue_events
            )
            outage_minutes = max_gap if max_gap else None

        # HTTP error codes
        http_codes = {e.get("http_status") for e in http_errors if e.get("http_status")}
        endpoints  = {e.get("endpoint") for e in http_errors if e.get("endpoint")}

        # Affected shipments
        affected = None
        for e in events:
            if e.get("affected_shipments"):
                affected = e["affected_shipments"]
                break
        if not affected and recovery:
            affected = recovery.get("shipments_updated")

        severity = "CRITICAL" if (outage_minutes and outage_minutes >= 30) else "HIGH"

        # Build evidence
        evidence: list[str] = []
        if last_ok:
            evidence.append(
                f"Last successful push at {_fmt_ts(last_ok)} "
                f"({last_ok.get('shipments_updated', '?')} shipments updated)"
            )
        if overdue_events:
            worst = max(overdue_events, key=lambda e: e.get("minutes_since_last_push", 0))
            evidence.append(
                f"Push gap reached {worst.get('minutes_since_last_push')} min "
                f"at {_fmt_ts(worst)} "
                f"(threshold: {worst.get('threshold_minutes', interval*2 if interval else '?')} min)"
            )
        if http_errors:
            evidence.append(
                f"{len(http_errors)} HTTP {'/'.join(str(c) for c in http_codes)} error(s) "
                f"on endpoint(s): {', '.join(e for e in endpoints if e)}"
            )
            if http_errors[0].get("retry_count"):
                evidence.append(
                    f"Each request failed after "
                    f"{http_errors[0]['retry_count']} retries"
                )
        if breach_alert:
            evidence.append(f"PUSH_HEALTH_BREACH alert: {breach_alert.get('message', '')}")
        if down_alert:
            evidence.append(f"CARRIER_API_DOWN alert: {down_alert.get('message', '')}")
        if recovery:
            evidence.append(
                f"Feed recovered at {_fmt_ts(recovery)} — "
                f"gap of {recovery.get('minutes_since_last_push')} min. "
                f"Backfill may be incomplete."
            )

        # Impact
        impact = f"{carrier} GPS/API push feed was silent for "
        if outage_minutes:
            h, m = divmod(outage_minutes, 60)
            impact += f"{h}h {m}min. " if h else f"{outage_minutes} min. "
        if affected:
            impact += f"{affected} active shipments lost real-time location updates. "
        if interval:
            impact += (
                f"Expected push interval: {interval} min. "
                f"Visibility gap exceeded 2× threshold."
            )

        # Determine whether it's a carrier-side outage or something else
        if http_codes & {503, 502, 504}:
            cause_detail = (
                f"The {carrier} API endpoint "
                f"({', '.join(e for e in endpoints if e)}) "
                f"returned HTTP {'/'.join(str(c) for c in http_codes)} errors, "
                f"indicating a carrier-side service outage or infrastructure failure. "
                f"The integration's retry logic exhausted all attempts without success."
            )
        else:
            cause_detail = (
                f"The {carrier} push feed stopped sending position updates. "
                f"The exact carrier-side trigger is not captured in these logs."
            )

        root_cause = (
            f"The {carrier} push feed went silent due to a carrier-side API outage. "
            f"{cause_detail}"
        )

        fix_steps = [
            f"Check {carrier}'s API status page or contact their technical support "
            f"to confirm the outage and expected recovery time.",
            "Verify the integration's retry/backoff configuration is active and "
            "that alerts fired within the expected 2× interval window.",
            f"Once the feed recovers, confirm push data resumes at the expected "
            f"{interval}-min interval and shipment counts normalise.",
            "Trigger a backfill request to the carrier for any position data "
            "missed during the outage window if their API supports historical replay.",
            "Review affected shipments in the visibility dashboard and "
            "manually update ETA estimates if needed.",
        ]

        prevention = [
            "Implement a carrier-side health check (HTTP HEAD/GET on the "
            "position endpoint) that fires a P1 alert if the endpoint "
            "returns 5xx errors for more than 5 consecutive minutes.",
            "Add a push-gap alert that escalates to the carrier account manager "
            "if silence exceeds 3× the expected interval with no HTTP error context.",
            "Negotiate a guaranteed SLA with the GPS provider for feed uptime "
            "and require advance maintenance window notifications.",
        ]

        outage_str = ""
        if outage_minutes:
            h, m = divmod(outage_minutes, 60)
            outage_str = f"{h} hours and {m} minutes" if h else f"{outage_minutes} minutes"

        note = (
            f"The real-time GPS tracking feed from {carrier} experienced an "
            f"outage lasting approximately {outage_str} today due to an issue "
            f"on the carrier's API infrastructure. "
            f"During this period, live vehicle location updates were unavailable "
            f"in the portal. The feed has since recovered and we are monitoring "
            f"for full data continuity."
        )

        return RCAReport(
            rule_name=self.name,
            severity=severity,
            root_cause=root_cause,
            evidence=evidence,
            impact=impact,
            fix_steps=fix_steps,
            prevention=prevention,
            stakeholder_note=note,
            outage_minutes=outage_minutes,
            recovered=recovery is not None,
        )


# ── Rule 3 — TMS Authentication / Credential Failure ─────────────────────────

class TMSAuthFailureRule(Rule):
    """TMS sync fails due to expired or revoked OAuth2 / API credentials."""

    name = "TMS Auth Failure"
    priority = 85

    def matches(self, events: list[dict]) -> bool:
        return any(
            e.get("error") in ("AUTH_TOKEN_EXPIRED", "REFRESH_TOKEN_INVALID")
            or e.get("event") in ("TOKEN_REFRESH_FAILED",)
            or e.get("rule") in ("TMS_AUTH_FAILURE", "TMS_SYNC_GAP", "TMS_SYNC_CRITICAL")
            for e in events
        )

    def analyse(self, events: list[dict]) -> RCAReport:
        poll_failures = [
            e for e in events if e.get("event") == "POLL_FAILED"
        ]
        token_failure = next(
            (e for e in events if e.get("event") == "TOKEN_REFRESH_FAILED"), None
        )
        auth_alert   = next(
            (e for e in events if e.get("rule") == "TMS_AUTH_FAILURE"), None
        )
        gap_alert    = next(
            (e for e in events if e.get("rule") in ("TMS_SYNC_GAP", "TMS_SYNC_CRITICAL")), None
        )
        cred_update  = next(
            (e for e in events if e.get("event") == "CREDENTIALS_UPDATED"), None
        )
        recovery     = next(
            (e for e in events if e.get("status") == "RECOVERED"), None
        )

        provider = _carrier(events)

        # Outage duration from recovery event or gap alert
        outage_minutes = None
        if recovery:
            outage_minutes = gap_alert.get("current_value") if gap_alert else None
            # Better: use the gap_minutes field on recovery event if present
            outage_minutes = recovery.get("gap_minutes") or outage_minutes
        elif gap_alert:
            outage_minutes = gap_alert.get("current_value")

        affected = None
        for e in events:
            if e.get("affected_shipments"):
                affected = e["affected_shipments"]
                break

        # HTTP codes seen in poll failures
        http_codes = {e.get("http_status") for e in poll_failures if e.get("http_status")}

        # Build evidence
        evidence: list[str] = []
        if poll_failures:
            first_fail = poll_failures[0]
            evidence.append(
                f"First POLL_FAILED at {_fmt_ts(first_fail)} — "
                f"error: {first_fail.get('error')} "
                f"(HTTP {first_fail.get('http_status', '?')})"
            )
        if token_failure:
            evidence.append(
                f"TOKEN_REFRESH_FAILED at {_fmt_ts(token_failure)}: "
                f"{token_failure.get('details', token_failure.get('error', ''))}"
            )
        if auth_alert:
            evidence.append(f"TMS_AUTH_FAILURE alert: {auth_alert.get('message', '')}")
        if len(poll_failures) > 1:
            evidence.append(
                f"{len(poll_failures)} consecutive POLL_FAILED events "
                f"(retries 1–{len(poll_failures)}) — all returned "
                f"HTTP {'/'.join(str(c) for c in http_codes)}"
            )
        if gap_alert:
            evidence.append(
                f"TMS sync gap alert at {_fmt_ts(gap_alert)}: "
                f"{gap_alert.get('current_value')} min without sync "
                f"(threshold: {gap_alert.get('threshold', '?')} min). "
                f"{affected or gap_alert.get('affected_shipments', '?')} shipments affected."
            )
        if cred_update:
            evidence.append(
                f"Credentials rotated at {_fmt_ts(cred_update)}: "
                f"{cred_update.get('details', '')}"
            )
        if recovery:
            evidence.append(
                f"Sync recovered at {_fmt_ts(recovery)} — "
                f"{recovery.get('shipments_updated', '?')} shipments resynced. "
                f"Total gap: {outage_minutes} min."
            )

        # Root cause
        root_cause = (
            f"The {provider} integration lost sync access because the OAuth2 "
            f"client credentials were rotated on the TMS side without advance notice "
            f"to the integration team. The stored refresh token was invalidated, "
            f"causing all subsequent poll attempts to return HTTP 401. "
            f"Re-authentication was impossible until new credentials were provisioned."
        )

        impact = f"{provider} sync was down for "
        if outage_minutes:
            h, m = divmod(outage_minutes, 60)
            impact += f"{h}h {m}min. " if h else f"{outage_minutes} min. "
        if affected:
            impact += (
                f"{affected} shipments had stale status data during the outage window. "
            )
        impact += (
            "TMS-originated shipment events (pickup confirmations, "
            "delivery updates) were not visible in the platform during this period."
        )

        fix_steps = [
            f"Confirm with {provider} account admin that the new OAuth2 credentials "
            "are active and update the integration credential store immediately.",
            "Restart the poll scheduler and verify the first successful POLL_SUCCESS "
            "event arrives within the next poll window.",
            "Trigger a full resync of all affected shipments to backfill any "
            "status events missed during the outage.",
            "Audit other TMS integrations for credential age — rotate any that "
            "are near expiry proactively.",
        ]

        prevention = [
            "Establish a formal change-notification process with TMS vendors: "
            "any credential rotation must be communicated at least 48 hours in "
            "advance with the new credentials delivered securely.",
            "Implement credential expiry monitoring — alert the integration team "
            "7 days before any OAuth2 token or API key is due to expire.",
            "Set a TMS_SYNC_GAP alert threshold at 45 minutes with immediate "
            "auto-escalation to the TMS account manager if the root cause "
            "is authentication-related.",
        ]

        outage_str = ""
        if outage_minutes:
            h, m = divmod(outage_minutes, 60)
            outage_str = (
                f"{h} hours and {m} minutes" if h else f"{outage_minutes} minutes"
            )

        note = (
            f"The {provider} TMS connection experienced an outage lasting "
            f"approximately {outage_str} today. "
            f"The outage was caused by an unannounced security credential rotation "
            f"on the TMS side, which temporarily blocked our integration from syncing "
            f"shipment updates. New credentials have been applied and the connection "
            f"is fully restored; all affected shipment data has been resynchronised."
        )

        return RCAReport(
            rule_name=self.name,
            severity="CRITICAL" if (outage_minutes and outage_minutes >= 60) else "HIGH",
            root_cause=root_cause,
            evidence=evidence,
            impact=impact,
            fix_steps=fix_steps,
            prevention=prevention,
            stakeholder_note=note,
            outage_minutes=outage_minutes,
            recovered=recovery is not None,
        )


# ── Rule registry ──────────────────────────────────────────────────────────────

ALL_RULES: list[Rule] = sorted(
    [
        EDIInvalidElementRule(),
        APIPushGapRule(),
        TMSAuthFailureRule(),
    ],
    key=lambda r: r.priority,
    reverse=True,
)


def detect(events: list[dict]) -> list[RCAReport]:
    """Run all matching rules against the event list. Returns one report per match."""
    return [rule.analyse(events) for rule in ALL_RULES if rule.matches(events)]
