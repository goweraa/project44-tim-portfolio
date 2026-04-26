#!/usr/bin/env python3
"""
project44 API Simulator
Simulates the project44 carrier status update API for TL and LTL modes.
Returns realistic HTTP responses matching the real project44 API behaviour.
Run with: python3 -m streamlit run api_simulator.py
"""

import streamlit as st
import json
import re
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

TL_ENDPOINT = "POST /api/v4/capacityproviders/tl/shipments/statusUpdates"
LTL_ENDPOINT = "POST /api/v4/capacityproviders/ltl/shipments/statusupdates"

TL_EVENT_TYPES = [
    "ARRIVED", "DEPARTED", "IN_TRANSIT", "DELIVERED",
    "POSITION", "OUT_FOR_DELIVERY", "AT_STOP", "ESTIMATED_DELIVERY"
]

LTL_STATUS_CODES = [
    "READY_FOR_PICKUP", "UPDATED_PICKUP_APPT", "EXCEPTION",
    "PICKED_UP", "ARRIVED_AT_TERMINAL", "REWEIGHT_RECLASS",
    "INFO", "UPDATED_DELIVERY_APPT", "DEPARTED_TERMINAL",
    "OUT_FOR_DELIVERY", "DELIVERED"
]

LTL_STOP_TYPES = ["ORIGIN", "DESTINATION", "TERMINAL"]

CARRIER_ID_TYPES = ["SCAC", "DOT_NUMBER", "MC_NUMBER", "P44_EU", "P44_GLOBAL", "SYSTEM"]

VALID_TOKENS = ["eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN", "test-bearer-token-valid-123"]
EXPIRED_TOKENS = ["eyJhbGciOiJSUzI1NiJ9.EXPIRED_TOKEN", "test-bearer-token-expired-456"]
WRONG_ENV_TOKENS = ["eyJhbGciOiJSUzI1NiJ9.STAGING_TOKEN", "staging-token-789"]

# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def validate_token(token_header):
    """Validate the Authorization header and return (is_valid, error_message)."""
    if not token_header or token_header.strip() == "":
        return False, "missing", "JWT token is missing"

    token_header = token_header.strip()

    if not token_header.startswith("Bearer "):
        if token_header.startswith("Bearer:") or token_header.startswith("bearer "):
            return False, "malformed", "Invalid Authorization header format. Must be: 'Bearer <token>' (capital B, single space)"
        return False, "malformed", "Invalid Authorization header format. Must be: 'Bearer <token>'"

    token = token_header[7:]

    if token in EXPIRED_TOKENS:
        return False, "expired", "JWT token is expired"
    if token in WRONG_ENV_TOKENS:
        return False, "wrong_env", "Invalid credentials for this environment (staging token used in production)"
    if token not in VALID_TOKENS and not token.startswith("eyJ"):
        return False, "invalid", "Invalid JWT token"

    return True, "valid", None


def validate_tl_payload(payload):
    """Validate a TL status update payload. Returns list of errors."""
    errors = []

    # shipmentIdentifiers
    if "shipmentIdentifiers" not in payload:
        errors.append({"field": "shipmentIdentifiers", "message": "must not be null"})
    else:
        identifiers = payload["shipmentIdentifiers"]
        if not isinstance(identifiers, list) or len(identifiers) == 0:
            errors.append({"field": "shipmentIdentifiers", "message": "must contain at least one identifier"})
        else:
            for i, ident in enumerate(identifiers):
                if "type" not in ident:
                    errors.append({"field": f"shipmentIdentifiers[{i}].type", "message": "must not be null"})
                elif ident["type"] not in ["BILL_OF_LADING", "ORDER"]:
                    errors.append({"field": f"shipmentIdentifiers[{i}].type", "message": f"invalid value '{ident['type']}'. Must be BILL_OF_LADING or ORDER"})
                if "value" not in ident or not ident["value"]:
                    errors.append({"field": f"shipmentIdentifiers[{i}].value", "message": "must not be blank"})

    # latitude
    if "latitude" not in payload:
        errors.append({"field": "latitude", "message": "must not be null"})
    else:
        try:
            lat = float(payload["latitude"])
            if lat < -90 or lat > 90:
                errors.append({"field": "latitude", "message": "must be between -90 and 90"})
        except (ValueError, TypeError):
            errors.append({"field": "latitude", "message": "must be a valid decimal number"})

    # longitude
    if "longitude" not in payload:
        errors.append({"field": "longitude", "message": "must not be null"})
    else:
        try:
            lon = float(payload["longitude"])
            if lon < -180 or lon > 180:
                errors.append({"field": "longitude", "message": "must be between -180 and 180"})
        except (ValueError, TypeError):
            errors.append({"field": "longitude", "message": "must be a valid decimal number"})

    # utcTimestamp
    if "utcTimestamp" not in payload:
        errors.append({"field": "utcTimestamp", "message": "must not be null"})
    else:
        ts = payload["utcTimestamp"]
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        if not re.match(pattern, str(ts)):
            errors.append({"field": "utcTimestamp", "message": "invalid format. Must be yyyy-mm-ddTHH:mm:ss"})
        else:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt > datetime.now(timezone.utc):
                    errors.append({"field": "utcTimestamp", "message": "must be a past or present date (422)"})
            except ValueError:
                errors.append({"field": "utcTimestamp", "message": "invalid datetime value"})

    # customerId
    if "customerId" not in payload or not payload["customerId"]:
        errors.append({"field": "customerId", "message": "must not be blank"})

    # eventType — if present, validate
    if "eventType" in payload:
        if payload["eventType"] not in TL_EVENT_TYPES:
            errors.append({"field": "eventType", "message": f"invalid value '{payload['eventType']}'. Must be one of: {', '.join(TL_EVENT_TYPES)}"})
        # eventStopNumber required with eventType (unless POSITION)
        if payload["eventType"] != "POSITION" and "eventStopNumber" not in payload:
            errors.append({"field": "eventStopNumber", "message": "must not be null when eventType is set (except POSITION)"})

    # ETA without position or status
    if "shipmentStops" in payload:
        has_position = "latitude" in payload and "longitude" in payload
        has_event = "eventType" in payload and payload.get("eventType") != "POSITION"
        if not has_position and not has_event:
            errors.append({"field": "shipmentStops", "message": "ETA cannot be sent without a position update or status event"})

    return errors


def validate_ltl_payload(payload):
    """Validate an LTL status update payload. Returns list of errors."""
    errors = []

    # customerAccount.accountIdentifier
    if "customerAccount" not in payload:
        errors.append({"field": "customerAccount", "message": "must not be null"})
    else:
        if "accountIdentifier" not in payload["customerAccount"] or not payload["customerAccount"]["accountIdentifier"]:
            errors.append({"field": "customerAccount.accountIdentifier", "message": "must not be blank"})

    # carrierIdentifier
    if "carrierIdentifier" not in payload:
        errors.append({"field": "carrierIdentifier", "message": "must not be null"})
    else:
        ci = payload["carrierIdentifier"]
        if "type" not in ci:
            errors.append({"field": "carrierIdentifier.type", "message": "must not be null"})
        elif ci["type"] != "SCAC":
            errors.append({"field": "carrierIdentifier.type", "message": f"invalid value '{ci['type']}'. LTL only accepts SCAC"})
        if "value" not in ci or not ci["value"]:
            errors.append({"field": "carrierIdentifier.value", "message": "must not be blank"})
        elif ci.get("type") == "SCAC" and (len(ci["value"]) < 2 or len(ci["value"]) > 4):
            errors.append({"field": "carrierIdentifier.value", "message": "SCAC must be 2-4 characters"})

    # shipmentIdentifiers (PRO number)
    if "shipmentIdentifiers" not in payload:
        errors.append({"field": "shipmentIdentifiers", "message": "must not be null — must include PRO number"})
    else:
        identifiers = payload["shipmentIdentifiers"]
        if not isinstance(identifiers, list) or len(identifiers) == 0:
            errors.append({"field": "shipmentIdentifiers", "message": "must contain at least one PRO number"})
        else:
            for i, ident in enumerate(identifiers):
                if "type" not in ident:
                    errors.append({"field": f"shipmentIdentifiers[{i}].type", "message": "must not be null"})
                elif ident["type"] != "PRO":
                    errors.append({"field": f"shipmentIdentifiers[{i}].type", "message": f"invalid value '{ident['type']}'. LTL uses PRO number"})
                if "value" not in ident or not ident["value"]:
                    errors.append({"field": f"shipmentIdentifiers[{i}].value", "message": "must not be blank"})

    # statusCode
    if "statusCode" not in payload:
        errors.append({"field": "statusCode", "message": "must not be null"})
    else:
        if payload["statusCode"] not in LTL_STATUS_CODES:
            errors.append({"field": "statusCode", "message": f"invalid value '{payload['statusCode']}'. Must be one of: {', '.join(LTL_STATUS_CODES)}"})
        else:
            # Conditionally required fields
            stop_required = ["PICKED_UP", "DELIVERED", "ARRIVED_AT_TERMINAL", "DEPARTED_TERMINAL"]
            if payload["statusCode"] in stop_required:
                if "stopType" not in payload:
                    errors.append({"field": "stopType", "message": f"must not be null when statusCode is {payload['statusCode']}"})
                elif payload["stopType"] not in LTL_STOP_TYPES:
                    errors.append({"field": "stopType", "message": f"invalid value. Must be: {', '.join(LTL_STOP_TYPES)}"})
                if "stopNumber" not in payload:
                    errors.append({"field": "stopNumber", "message": f"must not be null when statusCode is {payload['statusCode']}"})

            # Exception requires reason codes
            if payload["statusCode"] == "EXCEPTION":
                if "statusReason" not in payload:
                    errors.append({"field": "statusReason", "message": "must not be null when statusCode is EXCEPTION"})
                else:
                    if "reasonSummaryCode" not in payload["statusReason"]:
                        errors.append({"field": "statusReason.reasonSummaryCode", "message": "must not be null when statusCode is EXCEPTION"})

    # timestamp
    if "timestamp" not in payload:
        errors.append({"field": "timestamp", "message": "must not be null"})
    else:
        ts = str(payload["timestamp"])
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        if not re.match(pattern, ts):
            errors.append({"field": "timestamp", "message": "invalid format. Must be yyyy-mm-ddTHH:mm:ss+0000"})

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_response(status_code, errors=None, extra=None):
    """Build a realistic project44 API response."""
    if status_code == 202:
        return status_code, "202 Accepted", {}

    body = {"httpStatus": status_code}

    messages = {
        400: "Validation failed",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }

    status_names = {
        400: "400 Bad Request",
        401: "401 Unauthorized",
        403: "403 Forbidden",
        404: "404 Not Found",
        409: "409 Conflict",
        422: "422 Unprocessable Entity",
        429: "429 Too Many Requests",
        500: "500 Internal Server Error",
        503: "503 Service Unavailable",
    }

    body["errorMessage"] = messages.get(status_code, "Error")
    if errors:
        body["errors"] = errors
    if status_code == 500:
        body["requestId"] = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    if extra:
        body.update(extra)

    return status_code, status_names.get(status_code, str(status_code)), body


# ─────────────────────────────────────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def status_colour(code):
    if code == 202:
        return "#2ecc71"
    elif 400 <= code < 500:
        return "#e74c3c"
    else:
        return "#c0392b"


def render_postman_response(status_code, status_label, body, response_time, endpoint, token_header):
    """Render a Postman-style response panel."""

    colour = status_colour(status_code)

    st.markdown("---")
    st.markdown("#### Response")

    # Request bar
    st.code(f"{endpoint}\nAuthorization: {token_header if token_header else '(none)'}", language=None)

    # Status line
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(
            f'<span style="background-color:{colour};color:white;padding:4px 10px;'
            f'border-radius:4px;font-weight:bold;font-size:14px;">Status: {status_label}</span>',
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(f"⏱ **Time:** {response_time} ms")
    with col3:
        body_str = json.dumps(body)
        st.markdown(f"📦 **Size:** {len(body_str)} B")

    # Body
    st.markdown("**Body**")
    if body:
        st.json(body)
    else:
        st.code("{}", language="json")

    # Headers tab for 429/503
    if status_code in [429, 503]:
        with st.expander("Headers (click to view — check Retry-After)"):
            st.json({
                "Content-Type": "application/json",
                "Retry-After": "60",
                "X-RateLimit-Limit": "100",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1714140660"
            })
    elif status_code == 500:
        with st.expander("Headers (click to view — copy the X-Request-ID)"):
            st.json({
                "Content-Type": "application/json",
                "X-Request-ID": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
            })

    # Diagnosis tip
    st.markdown("---")
    st.markdown("**What to do next:**")
    tips = {
        202: "✅ Data received. **Do not stop here.** Go to the project44 platform and verify the update matched the correct shipment. Check BOL and SCAC if the shipper sees nothing.",
        400: "🔴 Carrier-side fix. Read the **errors array** — it shows exactly which field is wrong and why. Fix the payload and resend.",
        401: "🔴 Authentication failed. Check: (1) Is the header format `Bearer <token>` with capital B and single space? (2) Is the token expired? (3) Are they using staging credentials against production?",
        403: "🔴 Credentials valid but no permission. Re-issue credentials with the correct scope for this endpoint.",
        404: "🔴 Wrong URL. Check character by character — staging vs production base URL, API version (v4), spelling of the path.",
        409: "🔴 Duplicate request. Carrier is sending the same update more than once. Check their retry logic.",
        422: "🔴 Payload structure is valid but values fail business logic. Check: future timestamp, invalid stop number, coordinates out of range, unregistered customerId.",
        429: "🔴 Rate limit hit. Click **Headers** above and check `Retry-After`. For parcel: batch requests, reduce polling frequency, remove inactive shipments from polling set.",
        500: "🔴 **project44 platform error — not the carrier's fault.** Copy the `requestId` from the body. Escalate to Engineering with: requestId + timestamp + payload. Do NOT ask the carrier to change anything.",
        503: "🔴 Platform temporarily unavailable. Click **Headers** above for `Retry-After`. Tell carrier to back off and retry. Escalate to Engineering if over 15 minutes.",
    }
    st.info(tips.get(status_code, "Review the response and diagnose accordingly."))


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT PAYLOADS
# ─────────────────────────────────────────────────────────────────────────────

TL_DEFAULT = {
    "shipmentIdentifiers": [
        {"type": "BILL_OF_LADING", "value": "BOL123456"}
    ],
    "carrierIdentifier": {"type": "SCAC", "value": "ABCD"},
    "customerId": "CUSTOMER_001",
    "eventType": "ARRIVED",
    "eventStopNumber": 1,
    "utcTimestamp": "2026-04-26T14:30:00",
    "latitude": 41.8781,
    "longitude": -87.6298
}

LTL_DEFAULT = {
    "customerAccount": {"accountIdentifier": "CUSTOMER_001"},
    "carrierIdentifier": {"type": "SCAC", "value": "ABCD"},
    "shipmentIdentifiers": [
        {"type": "PRO", "value": "PRO987654"}
    ],
    "statusCode": "PICKED_UP",
    "stopType": "ORIGIN",
    "stopNumber": 1,
    "timestamp": "2026-04-26T14:30:00+0000"
}


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIOS
# ─────────────────────────────────────────────────────────────────────────────

TL_SCENARIOS = {
    "✅ Valid TL update": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": TL_DEFAULT,
        "expected": 202
    },
    "❌ Missing eventType field": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "shipmentIdentifiers": [{"type": "BILL_OF_LADING", "value": "BOL123456"}],
            "customerId": "CUSTOMER_001",
            "utcTimestamp": "2026-04-26T14:30:00",
            "latitude": 41.8781,
            "longitude": -87.6298
        },
        "expected": 202
    },
    "❌ Expired token (401)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.EXPIRED_TOKEN",
        "payload": TL_DEFAULT,
        "expected": 401
    },
    "❌ Missing Authorization header (401)": {
        "token": "",
        "payload": TL_DEFAULT,
        "expected": 401
    },
    "❌ Wrong header format — colon instead of space (401)": {
        "token": "Bearer:eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": TL_DEFAULT,
        "expected": 401
    },
    "❌ Staging token in production (401)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.STAGING_TOKEN",
        "payload": TL_DEFAULT,
        "expected": 401
    },
    "❌ Missing BOL value (400)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "shipmentIdentifiers": [{"type": "BILL_OF_LADING", "value": ""}],
            "customerId": "CUSTOMER_001",
            "eventType": "ARRIVED",
            "eventStopNumber": 1,
            "utcTimestamp": "2026-04-26T14:30:00",
            "latitude": 41.8781,
            "longitude": -87.6298
        },
        "expected": 400
    },
    "❌ Invalid eventType value (400)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "shipmentIdentifiers": [{"type": "BILL_OF_LADING", "value": "BOL123456"}],
            "customerId": "CUSTOMER_001",
            "eventType": "ARRIVE",
            "eventStopNumber": 1,
            "utcTimestamp": "2026-04-26T14:30:00",
            "latitude": 41.8781,
            "longitude": -87.6298
        },
        "expected": 400
    },
    "❌ Future timestamp (422)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "shipmentIdentifiers": [{"type": "BILL_OF_LADING", "value": "BOL123456"}],
            "customerId": "CUSTOMER_001",
            "eventType": "ARRIVED",
            "eventStopNumber": 1,
            "utcTimestamp": "2099-12-31T23:59:59",
            "latitude": 41.8781,
            "longitude": -87.6298
        },
        "expected": 422
    },
    "❌ Missing customerId (400)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "shipmentIdentifiers": [{"type": "BILL_OF_LADING", "value": "BOL123456"}],
            "eventType": "ARRIVED",
            "eventStopNumber": 1,
            "utcTimestamp": "2026-04-26T14:30:00",
            "latitude": 41.8781,
            "longitude": -87.6298
        },
        "expected": 400
    },
}

LTL_SCENARIOS = {
    "✅ Valid LTL pickup update": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": LTL_DEFAULT,
        "expected": 202
    },
    "✅ Valid LTL delivery (closes shipment)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "customerAccount": {"accountIdentifier": "CUSTOMER_001"},
            "carrierIdentifier": {"type": "SCAC", "value": "ABCD"},
            "shipmentIdentifiers": [{"type": "PRO", "value": "PRO987654"}],
            "statusCode": "DELIVERED",
            "stopType": "DESTINATION",
            "stopNumber": 2,
            "timestamp": "2026-04-26T16:00:00+0000"
        },
        "expected": 202
    },
    "❌ Wrong identifier type — BOL instead of PRO (400)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "customerAccount": {"accountIdentifier": "CUSTOMER_001"},
            "carrierIdentifier": {"type": "SCAC", "value": "ABCD"},
            "shipmentIdentifiers": [{"type": "BILL_OF_LADING", "value": "BOL123456"}],
            "statusCode": "PICKED_UP",
            "stopType": "ORIGIN",
            "stopNumber": 1,
            "timestamp": "2026-04-26T14:30:00+0000"
        },
        "expected": 400
    },
    "❌ Wrong carrier ID type — DOT_NUMBER not allowed in LTL (400)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "customerAccount": {"accountIdentifier": "CUSTOMER_001"},
            "carrierIdentifier": {"type": "DOT_NUMBER", "value": "1234567"},
            "shipmentIdentifiers": [{"type": "PRO", "value": "PRO987654"}],
            "statusCode": "PICKED_UP",
            "stopType": "ORIGIN",
            "stopNumber": 1,
            "timestamp": "2026-04-26T14:30:00+0000"
        },
        "expected": 400
    },
    "❌ Invalid statusCode value (400)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "customerAccount": {"accountIdentifier": "CUSTOMER_001"},
            "carrierIdentifier": {"type": "SCAC", "value": "ABCD"},
            "shipmentIdentifiers": [{"type": "PRO", "value": "PRO987654"}],
            "statusCode": "DELIVERED_OK",
            "stopType": "DESTINATION",
            "stopNumber": 2,
            "timestamp": "2026-04-26T14:30:00+0000"
        },
        "expected": 400
    },
    "❌ EXCEPTION without reason codes (400)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "customerAccount": {"accountIdentifier": "CUSTOMER_001"},
            "carrierIdentifier": {"type": "SCAC", "value": "ABCD"},
            "shipmentIdentifiers": [{"type": "PRO", "value": "PRO987654"}],
            "statusCode": "EXCEPTION",
            "timestamp": "2026-04-26T14:30:00+0000"
        },
        "expected": 400
    },
    "❌ Missing stopType for DELIVERED (400)": {
        "token": "Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
        "payload": {
            "customerAccount": {"accountIdentifier": "CUSTOMER_001"},
            "carrierIdentifier": {"type": "SCAC", "value": "ABCD"},
            "shipmentIdentifiers": [{"type": "PRO", "value": "PRO987654"}],
            "statusCode": "DELIVERED",
            "stopNumber": 2,
            "timestamp": "2026-04-26T14:30:00+0000"
        },
        "expected": 400
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="project44 API Simulator",
        page_icon="🚚",
        layout="wide"
    )

    st.title("🚚 project44 API Simulator")
    st.caption("Practice sending carrier status updates and reading HTTP responses — exactly as you would in Postman.")

    # Sidebar
    st.sidebar.header("Base URLs")
    st.sidebar.code("Production (Americas)\nhttps://na12.api.project44.com/api/v4")
    st.sidebar.code("Production (Europe)\nhttps://eu12.api.project44.com/api/v4")
    st.sidebar.code("Sandbox\nhttps://na12.api.sandbox.p-44.com/api/v4")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Test Tokens**")
    st.sidebar.markdown("✅ Valid:")
    st.sidebar.code("Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN")
    st.sidebar.markdown("❌ Expired:")
    st.sidebar.code("Bearer eyJhbGciOiJSUzI1NiJ9.EXPIRED_TOKEN")
    st.sidebar.markdown("❌ Wrong env:")
    st.sidebar.code("Bearer eyJhbGciOiJSUzI1NiJ9.STAGING_TOKEN")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**The Rule**")
    st.sidebar.error("4xx = carrier fixes it")
    st.sidebar.error("5xx = project44 fixes it")
    st.sidebar.success("202 = received (verify matching!)")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["🚛 TL Simulator", "📦 LTL Simulator", "🎯 Scenario Drills"])

    # ── TL TAB ──────────────────────────────────────────────────────────────
    with tab1:
        st.subheader("TL Status Update")
        st.code(TL_ENDPOINT)

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("**Authorization Header**")
            tl_token = st.text_input(
                "Authorization",
                value="Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
                key="tl_token",
                help="Must be: Bearer <token> — capital B, single space"
            )

            st.markdown("**Request Payload (JSON)**")
            tl_payload_str = st.text_area(
                "Payload",
                value=json.dumps(TL_DEFAULT, indent=2),
                height=400,
                key="tl_payload"
            )

            simulate_tl = st.button("Send Request →", key="tl_send", type="primary")

        with col2:
            if simulate_tl:
                import time
                start = time.time()

                try:
                    payload = json.loads(tl_payload_str)
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")
                    st.stop()

                # Auth check
                token_valid, token_status, token_error = validate_token(tl_token)

                elapsed = int((time.time() - start) * 1000) + 142

                if not token_valid:
                    error_messages = {
                        "missing": [{"message": "JWT token is missing"}],
                        "expired": [{"message": "JWT token is expired"}],
                        "malformed": [{"message": token_error}],
                        "wrong_env": [{"message": "Invalid credentials for this environment"}],
                        "invalid": [{"message": "Invalid JWT token"}],
                    }
                    code, label, body = build_response(401, error_messages.get(token_status))
                else:
                    errors = validate_tl_payload(payload)
                    future_ts_errors = [e for e in errors if "past or present" in e.get("message", "")]
                    other_errors = [e for e in errors if "past or present" not in e.get("message", "")]

                    if other_errors:
                        code, label, body = build_response(400, other_errors)
                    elif future_ts_errors:
                        code, label, body = build_response(422, future_ts_errors)
                    else:
                        code, label, body = build_response(202)

                render_postman_response(code, label, body, elapsed, TL_ENDPOINT, tl_token)

    # ── LTL TAB ─────────────────────────────────────────────────────────────
    with tab2:
        st.subheader("LTL Status Update")
        st.code(LTL_ENDPOINT)

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("**Authorization Header**")
            ltl_token = st.text_input(
                "Authorization",
                value="Bearer eyJhbGciOiJSUzI1NiJ9.VALID_TEST_TOKEN",
                key="ltl_token"
            )

            st.markdown("**Request Payload (JSON)**")
            ltl_payload_str = st.text_area(
                "Payload",
                value=json.dumps(LTL_DEFAULT, indent=2),
                height=400,
                key="ltl_payload"
            )

            simulate_ltl = st.button("Send Request →", key="ltl_send", type="primary")

        with col2:
            if simulate_ltl:
                import time
                start = time.time()

                try:
                    payload = json.loads(ltl_payload_str)
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")
                    st.stop()

                token_valid, token_status, token_error = validate_token(ltl_token)
                elapsed = int((time.time() - start) * 1000) + 118

                if not token_valid:
                    error_messages = {
                        "missing": [{"message": "JWT token is missing"}],
                        "expired": [{"message": "JWT token is expired"}],
                        "malformed": [{"message": token_error}],
                        "wrong_env": [{"message": "Invalid credentials for this environment"}],
                        "invalid": [{"message": "Invalid JWT token"}],
                    }
                    code, label, body = build_response(401, error_messages.get(token_status))
                else:
                    errors = validate_ltl_payload(payload)
                    if errors:
                        code, label, body = build_response(400, errors)
                    else:
                        code, label, body = build_response(202)

                render_postman_response(code, label, body, elapsed, LTL_ENDPOINT, ltl_token)

    # ── SCENARIO DRILLS TAB ──────────────────────────────────────────────────
    with tab3:
        st.subheader("🎯 Scenario Drills")
        st.markdown("Load a pre-built scenario, predict the response code, then send to check your answer.")

        mode = st.radio("Mode", ["TL Scenarios", "LTL Scenarios"], horizontal=True)

        scenarios = TL_SCENARIOS if mode == "TL Scenarios" else LTL_SCENARIOS
        endpoint = TL_ENDPOINT if mode == "TL Scenarios" else LTL_ENDPOINT

        scenario_name = st.selectbox("Select a scenario", list(scenarios.keys()))
        scenario = scenarios[scenario_name]

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("**Authorization Header**")
            st.code(scenario["token"] if scenario["token"] else "(none)")

            st.markdown("**Payload**")
            st.json(scenario["payload"])

            prediction = st.selectbox(
                "What HTTP code do you expect?",
                ["-- Select your answer --", "202", "400", "401", "403", "404", "409", "422", "429", "500"]
            )

            run_scenario = st.button("Send Request →", key="scenario_send", type="primary")

        with col2:
            if run_scenario:
                import time
                start = time.time()

                token_valid, token_status, token_error = validate_token(scenario["token"])
                elapsed = int((time.time() - start) * 1000) + 134

                if not token_valid:
                    error_messages = {
                        "missing": [{"message": "JWT token is missing"}],
                        "expired": [{"message": "JWT token is expired"}],
                        "malformed": [{"message": token_error}],
                        "wrong_env": [{"message": "Invalid credentials for this environment"}],
                        "invalid": [{"message": "Invalid JWT token"}],
                    }
                    code, label, body = build_response(401, error_messages.get(token_status))
                else:
                    if mode == "TL Scenarios":
                        errors = validate_tl_payload(scenario["payload"])
                        future_ts_errors = [e for e in errors if "past or present" in e.get("message", "")]
                        other_errors = [e for e in errors if "past or present" not in e.get("message", "")]
                        if other_errors:
                            code, label, body = build_response(400, other_errors)
                        elif future_ts_errors:
                            code, label, body = build_response(422, future_ts_errors)
                        else:
                            code, label, body = build_response(202)
                    else:
                        errors = validate_ltl_payload(scenario["payload"])
                        if errors:
                            code, label, body = build_response(400, errors)
                        else:
                            code, label, body = build_response(202)

                # Score the prediction
                if prediction != "-- Select your answer --":
                    if int(prediction) == code:
                        st.success(f"✅ Correct! You predicted {prediction} and got {code}.")
                    else:
                        st.error(f"❌ You predicted {prediction} — actual response is {code}.")

                render_postman_response(code, label, body, elapsed, endpoint, scenario["token"])


if __name__ == "__main__":
    main()
