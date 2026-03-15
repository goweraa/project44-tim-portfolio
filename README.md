# project44 TIM Portfolio

A suite of five tools built to demonstrate Technical Integration Manager (TIM) competencies for the project44 platform. Each tool addresses a real problem in carrier/TMS/GPS integration management — from monitoring integration health and decoding EDI files, to diagnosing failures and visualising shipment visibility.

---

## Tools at a Glance

| Tool | File(s) | Stack | Run with |
|---|---|---|---|
| TIM Metrics Assessor | `tim_metrics.py` | Python + Rich | `python3 tim_metrics.py` |
| TIM Metrics Dashboard | `tim_dashboard.py` | Streamlit + Plotly | `python3 -m streamlit run tim_dashboard.py` |
| EDI 214 Decoder | `EDI_Decoder_Tool.html` | HTML/JS | Open in browser |
| RCA Summarizer (AI) | `rca_summarizer.py` | Claude API | `python3 rca_summarizer.py <logfile>` |
| RCA Native (rule-based) | `rca_native.py` + `rca_rules.py` | Python + Rich | `python3 rca_native.py <logfile>` |
| Observe | `observe.py` | Streamlit + Plotly | `python3 -m streamlit run observe.py` |

---

## Installation

```bash
pip install -r requirements.txt
```

**requirements.txt includes:** `rich`, `streamlit`, `pandas`, `plotly`, `anthropic`

The RCA Summarizer (AI) additionally requires an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

---

## Tool 1 — TIM Metrics Assessor

**File:** `tim_metrics.py`
**Sample data:** `sample_data.csv`

A CLI tool that evaluates the health of every integration in the network across four dimensions:

| Metric | Target | Description |
|---|---|---|
| Tracking % | ≥ 90% | Tracked shipments / total shipments |
| Data Quality | ≥ 95% | Milestones received / milestones expected |
| SLA Adherence | ≤ 30 days | Days from onboarding start to go-live |
| Push Health | On schedule | Minutes since last push ≤ 2× expected interval |

The tool models three provider types (`carrier`, `tms`, `gps`) and two connection directions (`push`, `pull`). Push intervals are stored internally in minutes and displayed in the appropriate unit:

- GPS: 5–10 min intervals → displayed in minutes
- API carriers: 15 min
- EDI: 4h batch files → displayed in hours
- Flat File: 12h batch files → displayed in hours

```
Usage:
  python3 tim_metrics.py                        # all integrations
  python3 tim_metrics.py --provider carrier     # carriers only
  python3 tim_metrics.py --provider gps         # GPS providers
  python3 tim_metrics.py --direction push       # push integrations
  python3 tim_metrics.py --status error         # error state only
  python3 tim_metrics.py --sort quality         # sort by data quality
```

**Sample output:**

```
┌─────────────────────────────────────────────────────────────────┐
│  TIM Integration Monitor                                        │
│  22 integrations · 15 carriers · 4 TMS · 3 GPS                 │
│  Network tracking: 87.3% · Data quality: 84.1% · Health: 77.3% │
└─────────────────────────────────────────────────────────────────┘

  CARRIER         TYPE       DIR    PUSH      TRACKING   QUALITY    STATUS
  XPO Logistics   API        push   15min     97.8%      98.0%      active
  J.B. Hunt       API        push   15min     99.0%      99.0%      active
  Saia LTL        EDI        push   4h        60.0%      56.0%      ERROR   ✖
  ...
```

---

## Tool 2 — TIM Metrics Dashboard

**File:** `tim_dashboard.py`

A Streamlit GUI that renders the same integration health data from `sample_data.csv` as an interactive dashboard.

```bash
python3 -m streamlit run tim_dashboard.py
```

**Features:**

- **Network summary cards** — total integrations, tracking %, data quality %, push health %, SLA pass rate
- **Tracking & Quality bar chart** — per-integration comparison against targets (90% and 95% reference lines)
- **Push Interval Health chart** — expected vs actual push gap per integration; Y-axis auto-scales to hours for EDI/Flat File, minutes for API/GPS
- **SLA Compliance chart** — onboarding duration vs 30-day target
- **Provider mix donuts** — integration type and connection direction breakdown
- **Full integration table** — colour-coded badges for provider type (CARRIER / TMS / GPS), connection direction (push with last-push time or pull with last-sync time), and health status
- **Attention cards** — surfaced automatically for integrations in error state or below threshold
- **Sidebar filters** — filter by status, provider type, connection direction; sort by any metric

**Distinction from Observe:** this dashboard monitors *integration health* (is the feed working?). Observe monitors *shipment visibility* (where is my freight?).

---

## Tool 3 — EDI 214 Decoder

**File:** `EDI_Decoder_Tool.html`

A fully standalone browser tool for decoding X12 EDI-214 (Motor Carrier Shipment Status) files. No server, no dependencies — open the HTML file in any browser.

**How to use:**
1. Open `EDI_Decoder_Tool.html` in a browser
2. Paste raw EDI content into the text area **or** upload a `.edi` / `.txt` file
3. Click **Decode**

**What it decodes:**

| Segment | Description |
|---|---|
| ISA / IEA | Interchange control envelope — sender/receiver IDs, date/time |
| GS / GE | Functional group header/trailer |
| ST / SE | Transaction set control |
| B10 | **Critical** — Bill of Lading number (BOL) + carrier SCAC |
| AT7 | **Critical** — Shipment status event (status code, reason code, date/time, timezone AT7-06) |
| MS1 | Event location (city, state) |
| L11 | Reference identification numbers |
| LX | Assigned number |

Each segment is rendered as a colour-coded card with field-by-field explanations. Invalid or unrecognised values are highlighted in red — for example, an `AT7-06` (Time Code) value of `XX` would be flagged as unrecognised with the accepted values listed (`CT`, `ET`, `MT`, `PT`, `UT`, `LT`).

---

## Tool 4 — RCA Summarizer (AI-powered)

**File:** `rca_summarizer.py`
**Sample error logs:** `sample_errors/`

Uses the Claude claude-opus-4-6 model with adaptive thinking and streaming to analyse integration error logs and produce a structured Root Cause Analysis report.

```bash
# Analyse a JSON error log
python3 rca_summarizer.py sample_errors/edi_parse_errors.json

# Analyse and save the report to a markdown file
python3 rca_summarizer.py sample_errors/api_push_gap.json --save

# Save to a specific directory
python3 rca_summarizer.py sample_errors/tms_sync_failure.json --save --out reports/

# Paste logs interactively
python3 rca_summarizer.py --paste

# Analyse the integration health CSV
python3 rca_summarizer.py --metrics sample_data.csv
```

**Output format** — every report contains six sections:

1. **Root Cause** — precise technical diagnosis in 1–2 sentences
2. **Evidence** — specific log entries, error codes, timestamps, and metric values
3. **Impact** — affected carriers/providers, shipment count, duration
4. **Recommended Fix** — numbered remediation steps in priority order
5. **Prevention** — concrete measures to prevent recurrence
6. **Stakeholder Note** — plain-English 2–3 sentence summary for account managers

The model streams its response token-by-token to the terminal so output appears in real time.

**Three included error scenarios:**

| File | Scenario |
|---|---|
| `sample_errors/edi_parse_errors.json` | Saia LTL Freight EDI-214 feed: `AT7-06` Time Code sending `XX` (invalid). 33/40 transaction sets rejected across two batches. Milestone completeness drops from 91.2% to 56.0%. |
| `sample_errors/api_push_gap.json` | Verizon Connect GPS feed goes silent for 2h 35min. HTTP 503 on `/v2/vehicles/positions`. 890 active shipments lose real-time location. |
| `sample_errors/tms_sync_failure.json` | MercuryGate TMS OAuth2 credentials rotated without notice. All poll attempts return HTTP 401. 280 shipments stale for 2h 50min. |

---

## Tool 5 — RCA Native (rule-based)

**Files:** `rca_native.py`, `rca_rules.py`

A deterministic, offline alternative to the AI summarizer. Uses pattern-matching rules to detect known failure signatures in JSON log files and generates the same structured RCA output — no API key, no network, instant results.

```bash
# Analyse a log file
python3 rca_native.py sample_errors/edi_parse_errors.json

# Save report to markdown
python3 rca_native.py sample_errors/api_push_gap.json --save --out reports/

# Analyse metrics CSV
python3 rca_native.py --metrics sample_data.csv

# Paste logs interactively
python3 rca_native.py --paste
```

**Three detection rules in `rca_rules.py`:**

| Rule | Trigger signals | What it detects |
|---|---|---|
| `EDIInvalidElementRule` | `INVALID_ELEMENT` events | Unrecognised EDI field values — extracts the bad code, expected values, affected BOLs, per-file failure rate, downstream quality impact |
| `APIPushGapRule` | `PUSH_OVERDUE`, `PUSH_MISSED`, `HTTP_ERROR` | GPS/API feed silence — measures outage duration, identifies HTTP error codes, calculates affected shipment count |
| `TMSAuthFailureRule` | `AUTH_TOKEN_EXPIRED`, `TOKEN_REFRESH_FAILED`, `POLL_FAILED` | OAuth2 credential failure — distinguishes expired vs revoked tokens, measures sync gap, notes credential rotation |

The engine runs all matching rules against the event list. A single log can trigger multiple rules (compound failures). The rule engine (`rca_rules.py`) is separated from the CLI (`rca_native.py`) so rules can be imported and reused programmatically.

**AI vs Native — when to use each:**

| | RCA Summarizer (AI) | RCA Native |
|---|---|---|
| Novel / unknown error types | Yes | No |
| No internet / no API key | No | Yes |
| Instant, deterministic output | No | Yes |
| Explains context beyond the logs | Yes | No |
| Production alerting pipeline | No | Yes |

---

## Tool 6 — Observe (Shipment Visibility Platform)

**File:** `observe.py`
**Sample data:** `observe_shipments.csv`

A Streamlit application modelled on project44's Observe product. Where the TIM Metrics Dashboard monitors integration health, Observe monitors individual shipments — tracking milestones, surfacing exceptions, and benchmarking carrier performance.

```bash
python3 -m streamlit run observe.py
```

The app loads 55 simulated shipments across 11 carriers, covering LTL and FTL freight with API, EDI, and Flat File integrations.

**Sidebar filters:** Carrier, Status, Mode (LTL/FTL), Integration Type

**Summary bar:** Total shipments · In Transit/At Risk · Delivered Today · Exceptions · Network OTD %

### Tab 1 — Shipments

A filterable table showing every shipment with:
- Route (origin city → destination city)
- Integration type and transport mode
- Scheduled vs estimated delivery
- Status badge: In Transit / At Risk / Exception / Delivered
- Last update (e.g., "3h ago")
- Milestone completeness (e.g., "4/6")
- Exception flag if applicable

Select any BOL from the dropdown to view its **milestone timeline** — a Plotly horizontal chart showing the full event sequence (Pickup Confirmed → In Transit → At Facility → Out for Delivery → Delivered). Completed milestones appear as filled blue circles; pending milestones as open grey circles; exception milestones in red.

### Tab 2 — Exceptions

An exception queue sorted by severity (CRITICAL → HIGH → MEDIUM → LOW). Each exception card shows:
- Severity badge and exception type
- Carrier, route, and time since last update
- Recommended action tailored to the exception type:
  - **NO_UPDATE** → Contact carrier operations, verify feed is active
  - **DATA_GAP** → Review EDI parse logs, check AT7 segment mapping
  - **DELAY** → Notify customer of revised ETA
  - **MISSED_PICKUP** → Confirm with carrier dispatcher, re-tender if needed
- Integration type badge (EDI / API / Flat File)

The Saia LTL exceptions in this tab (DATA_GAP, NO_UPDATE) are the same shipments affected by the AT7-06 EDI error scenario in `sample_errors/edi_parse_errors.json` — demonstrating the end-to-end connection between the RCA tools and the visibility platform.

### Tab 3 — Scorecards

A per-carrier performance table with:
- On-Time Delivery % (OTD) — delivered on or before scheduled delivery date
- Average transit days
- Data quality % — milestones received / expected
- Exception count and exception rate %

Two side-by-side Plotly bar charts:
- **OTD % by carrier** — colour-coded (green ≥90%, orange 75–90%, red <75%) with a 90% target line
- **Data Quality % by carrier** — colour-coded (green ≥95%, orange 80–95%, red <80%) with a 95% target line

Network summary line beneath the charts: overall OTD%, average data quality, and count of at-risk carriers.

---

## Sample Data

### `sample_data.csv` — 22 integrations

| Provider | Count | Integration Types |
|---|---|---|
| Carriers | 15 | API, EDI, Flat File |
| TMS | 4 | SAP LBN, Oracle OTM, Blue Yonder, MercuryGate |
| GPS | 3 | Samsara, Geotab, Verizon Connect |

Key scenarios embedded in the data:
- **Saia LTL** (`C009`) — EDI, error state, 27 errors/30d, milestone completeness 56%
- **Estes Express** (`C005`) — EDI, active but 12 errors/30d, open unresolved issue
- **Verizon Connect** (`G003`) — GPS, error state, last push 2026-03-14 (24h+ gap)
- **LSO** (`C014`) — Flat File, inactive, zero tracked shipments

### `observe_shipments.csv` — 55 shipments

55 LTL/FTL shipments across 11 carriers for March 2026, with realistic exception distribution:
- 1 CRITICAL — Saia LTL (no update in 7 days, EDI feed in error state)
- 6 HIGH — data gaps, no-update gaps, and delay exceptions
- 5 MEDIUM — minor delays and incomplete milestone data

---

## How the Tools Connect

```
sample_data.csv ──► tim_metrics.py (CLI health check)
                └──► tim_dashboard.py (GUI health dashboard)

sample_errors/*.json ──► rca_summarizer.py (AI diagnosis)
                     └──► rca_native.py (rule-based diagnosis)

observe_shipments.csv ──► observe.py (shipment visibility)
                           ├── Tab 1: milestone timelines
                           ├── Tab 2: exceptions (link back to RCA tools)
                           └── Tab 3: carrier scorecards

EDI_Decoder_Tool.html ──► decode raw EDI-214 files
                          (AT7-06 errors visible here → diagnosed by RCA tools)
```

The exception data in Observe, the error logs in `sample_errors/`, and the degraded metrics in `sample_data.csv` all describe the same set of carrier incidents — showing how a TIM would move from detecting a problem in the visibility platform, to pulling the raw logs, to running an RCA, to communicating the resolution.
