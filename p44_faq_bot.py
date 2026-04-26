import streamlit as st

st.set_page_config(
    page_title="project44 Support",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── FAQ data ───────────────────────────────────────────────────────────────────

CARRIER_FAQ = [
    # ── Authentication ──────────────────────────────────────────────────────
    {
        "category": "🔐 Authentication",
        "question": "Why am I getting a 401 Unauthorized error?",
        "keywords": ["401", "unauthorized", "token", "auth", "credential", "bearer"],
        "answer": """**Fault:** Carrier side.

**What it means:** Authentication failed. Your Bearer token is missing, expired, malformed, or wrong for this environment.

**Check the Authorization header first:**
```
Authorization: Bearer <your_token>
```
Must be exactly that — capital B, single space, no colon, no quotes around the token.

**Most common cause on a live integration:** Token expired. Tokens typically last 1 hour. If you have no automatic refresh logic, this will happen every hour.

**Fix for expired token:**
1. Generate a fresh token using your `client_id` and `client_secret`
2. Implement automatic refresh — request a new token before **80% of `expires_in`** has elapsed
3. Never hard-code a token in your code

**New integration that never worked?** Check in this order:
1. Header format exactly as shown above
2. Token was freshly generated (not a sample or copied token)
3. You are using the correct environment — staging credentials do not work in production
4. `expires_in` in the token response is in the future

**Rule:** 4xx = carrier fixes it.""",
    },
    {
        "category": "🔐 Authentication",
        "question": "My integration was working and suddenly started returning 401",
        "keywords": ["401", "working", "suddenly", "broke", "stopped", "expired", "was working"],
        "answer": """**Fault:** Carrier side — expired token.

This is almost always the same issue: your token has expired and you have no automatic refresh logic.

**Why it happens:** OAuth 2.0 tokens expire (typically after 3600 seconds / 1 hour). If your code generated a token at setup time and stored it as a constant, it will work for an hour — then fail for everyone, all at once.

**Immediate fix:**
1. Generate a new token right now using your `client_id` and `client_secret`
2. Replace the expired token in your configuration
3. Test with one request to confirm 202 response

**Permanent fix — implement refresh logic:**
- Before every API call, check the token expiry time
- If less than 20% of `expires_in` remains, request a new token
- Store the new token and its expiry, then proceed with the call

**Also check:**
- Were credentials rotated on either side without the other being notified? (e.g. a project44 admin regenerated your client secret)
- Is the token being shared across multiple servers that may have cached different copies?""",
    },
    {
        "category": "🔐 Authentication",
        "question": "What is the correct format for the Authorization header?",
        "keywords": ["header", "authorization", "format", "bearer", "how to"],
        "answer": """**The correct format:**
```
Authorization: Bearer <access_token>
```

**Rules:**
- Capital **B** in Bearer
- Single space between Bearer and the token
- No colon after Bearer
- No quotes around the token
- No line breaks

**Common mistakes:**

| Wrong | Right |
|---|---|
| `authorization: Bearer <token>` | `Authorization: Bearer <token>` |
| `Authorization: bearer <token>` | `Authorization: Bearer <token>` |
| `Authorization:Bearer <token>` | `Authorization: Bearer <token>` |
| `Authorization: Bearer "<token>"` | `Authorization: Bearer <token>` |

**In Postman:** Use the **Authorization** tab → Type: **Bearer Token** → paste your token. Postman adds the header automatically in the correct format.""",
    },
    {
        "category": "🔐 Authentication",
        "question": "How do I generate a Bearer token?",
        "keywords": ["generate", "token", "how", "create", "get token", "client id", "client secret", "oauth"],
        "answer": """**Authentication method:** OAuth 2.0 Client Credentials grant.

**Five steps to get a token:**
1. Create a client application in project44
2. Add the appropriate roles to the client application
3. Add the client application to access groups
4. Generate a token using your `client_id` and `client_secret`
5. Use the token in the `Authorization: Bearer <token>` header on every request

**Token request (standard OAuth 2.0):**
```
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=YOUR_CLIENT_ID
&client_secret=YOUR_CLIENT_SECRET
```

**Token response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Important:** `expires_in` is in seconds. A value of 3600 means the token expires in 1 hour. Implement refresh logic — never wait for a 401 to know the token expired. Refresh proactively at 80% of `expires_in`.""",
    },

    # ── Payload Errors ─────────────────────────────────────────────────────
    {
        "category": "📦 Payload & Errors",
        "question": "I'm getting a 400 Bad Request — how do I fix it?",
        "keywords": ["400", "bad request", "payload", "malformed", "fix", "wrong field", "missing field"],
        "answer": """**Fault:** Carrier side.

**What it means:** Your payload is malformed — a required field is missing, has the wrong data type, or contains an invalid value.

**Step 1:** Read the error response body — it almost always names the specific field that failed.

**Common causes:**

| Problem | Example |
|---|---|
| Wrong `eventType` value | `"ARRIVE"` instead of `"ARRIVED"` |
| Wrong timestamp format | `"26/04/2026"` instead of `"2026-04-26T14:30:00Z"` |
| Missing required field | No `shipmentIdentifiers` in payload |
| Wrong identifier for mode | PRO number in TL endpoint (TL needs BOL or ORDER) |
| Malformed JSON | Missing closing bracket, trailing comma |
| Wrong data type | String where integer expected |

**Fix process:**
1. Copy the full error response body
2. Find the field name mentioned in the error
3. Compare your payload against the required fields list for your mode (TL or LTL)
4. Correct the field value
5. Retest in Postman before returning to production

**Remember:** 4xx = carrier fixes it. The request never reached processing — nothing was accepted.""",
    },
    {
        "category": "📦 Payload & Errors",
        "question": "What's the difference between a 400 and a 422 error?",
        "keywords": ["400", "422", "difference", "unprocessable", "bad request", "vs"],
        "answer": """Both are carrier-side errors, but they fail at different stages:

**400 Bad Request — the request is broken**
- JSON is malformed, a required field is missing, or a field has the wrong data type
- The server couldn't even parse what you sent
- Fix: check the structure and field types

**422 Unprocessable Entity — the request is formed correctly but the values don't make sense**
- JSON is valid, all fields present, data types correct
- But the *content* fails business logic validation
- Fix: check the actual values

**422 common causes:**
- `eventStopNumber` references a stop that doesn't exist on the shipment
- `utcTimestamp` is set in the future
- `latitude`/`longitude` outside valid ranges (-90 to 90 and -180 to 180)
- `customerId` not registered in the platform

**Quick rule:**
- 400 = *"I can't read this"*
- 422 = *"I can read it but it doesn't make sense"*

In both cases: read the response body — it will tell you which field failed and why.""",
    },
    {
        "category": "📦 Payload & Errors",
        "question": "I'm sending LTL updates but keep getting errors",
        "keywords": ["ltl", "error", "updates", "sending", "less than truckload", "status update"],
        "answer": """Check these LTL-specific requirements in order:

**1. Correct endpoint?**
```
POST /api/v4/capacityproviders/ltl/shipments/statusupdates
```
Note: all lowercase `statusupdates` — not camelCase.

**2. Required fields present?**
- `customerAccount.accountIdentifier`
- `carrierIdentifier.type` — must be `"SCAC"` (LTL only accepts SCAC)
- `carrierIdentifier.value` — your SCAC code
- `shipmentIdentifiers` — must include a **PRO number** (not BOL, not ORDER)
- `statusCode` — must be one of the accepted values (see below)
- `timestamp` — with UTC offset

**3. Valid `statusCode` value?**
Accepted values: `READY_FOR_PICKUP`, `UPDATED_PICKUP_APPT`, `PICKED_UP`, `ARRIVED_AT_TERMINAL`, `DEPARTED_TERMINAL`, `REWEIGHT_RECLASS`, `INFO`, `UPDATED_DELIVERY_APPT`, `OUT_FOR_DELIVERY`, `DELIVERED`, `EXCEPTION`

**4. Sending EXCEPTION?** Must include:
```json
"statusReason": {
  "reasonSummaryCode": "DELAY",
  "reasonDetailCode": "WEATHER"
}
```

**5. Sending PICKED_UP, DELIVERED, ARRIVED_AT_TERMINAL, or DEPARTED_TERMINAL?**
Also required: `stopType` (ORIGIN, DESTINATION, or TERMINAL) and `stopNumber`""",
    },
    {
        "category": "📦 Payload & Errors",
        "question": "What fields are required for a TL status update?",
        "keywords": ["tl", "truckload", "required", "fields", "payload", "mandatory"],
        "answer": """**TL endpoint:**
```
POST /api/v4/capacityproviders/tl/shipments/statusUpdates
```

**Required fields (must be in every TL request):**

| Field | Type | Notes |
|---|---|---|
| `shipmentIdentifiers` | Array | Must include `BILL_OF_LADING` or `ORDER` type |
| `latitude` | Decimal | Current position — use `0` if unavailable |
| `longitude` | Decimal | Current position — use `0` if unavailable |
| `utcTimestamp` | String | Format: `2026-04-26T14:30:00` — must be UTC |
| `customerId` | String | Provided by project44 |

**Minimum valid payload:**
```json
{
  "shipmentIdentifiers": [
    { "type": "BILL_OF_LADING", "value": "BOL123456" }
  ],
  "customerId": "CUSTOMER_001",
  "latitude": 41.8781,
  "longitude": -87.6298,
  "utcTimestamp": "2026-04-26T14:30:00",
  "eventType": "IN_TRANSIT"
}
```

**`eventType` values:** `ARRIVED`, `DEPARTED`, `IN_TRANSIT`, `DELIVERED`, `POSITION`

**Best practice:** Send status event + position in the same request. A position-only update has low value on its own. ETA cannot be sent without a position or status event.""",
    },

    # ── Endpoints & URLs ────────────────────────────────────────────────────
    {
        "category": "🔗 Endpoints & URLs",
        "question": "Which endpoint do I use for LTL shipments?",
        "keywords": ["ltl", "endpoint", "url", "which", "less than truckload", "path"],
        "answer": """**LTL endpoint:**
```
POST /api/v4/capacityproviders/ltl/shipments/statusupdates
```

**Full production URL (Americas):**
```
https://na12.api.project44.com/api/v4/capacityproviders/ltl/shipments/statusupdates
```

**Full production URL (Europe):**
```
https://eu12.api.project44.com/api/v4/capacityproviders/ltl/shipments/statusupdates
```

**Sandbox (testing only):**
```
https://na12.api.sandbox.p-44.com/api/v4/capacityproviders/ltl/shipments/statusupdates
```

**Important:** Note `statusupdates` is all lowercase in the LTL endpoint. The TL endpoint uses camelCase `statusUpdates`. Getting this wrong causes a 404.""",
    },
    {
        "category": "🔗 Endpoints & URLs",
        "question": "I'm getting a 404 — what's wrong with my URL?",
        "keywords": ["404", "not found", "url", "path", "endpoint", "wrong url"],
        "answer": """**Fault:** Carrier side (usually).

**What it means:** The endpoint URL doesn't exist as configured — wrong path, wrong environment, or a typo.

**Check in this order:**

**1. Staging vs production?**
- Sandbox: `https://na12.api.sandbox.p-44.com/api/v4`
- Production (Americas): `https://na12.api.project44.com/api/v4`
- Production (Europe): `https://eu12.api.project44.com/api/v4`

Most common cause: carrier copied the sandbox URL into their production config.

**2. API version correct?**
Must be `/api/v4/` — not `/api/v3/` or `/api/v2/`

**3. TL vs LTL path?**
- TL: `/capacityproviders/tl/shipments/statusUpdates` (camelCase)
- LTL: `/capacityproviders/ltl/shipments/statusupdates` (lowercase)

**4. Trailing slash or typo?**
Check every character in the path. A trailing slash or a misspelled segment causes 404.

**5. Europe-based carrier using Americas URL?**
European carriers must use `eu12.api.project44.com` — using the Americas URL causes routing issues.""",
    },
    {
        "category": "🔗 Endpoints & URLs",
        "question": "What's the difference between the sandbox and production URL?",
        "keywords": ["sandbox", "production", "url", "environment", "difference", "testing"],
        "answer": """**Sandbox (testing):**
```
https://na12.api.sandbox.p-44.com/api/v4
```
Use this for integration testing only. Data sent here does not appear on live shipper dashboards.

**Production (Americas):**
```
https://na12.api.project44.com/api/v4
```
Live environment. Data sent here appears on shippers' real dashboards.

**Production (Europe):**
```
https://eu12.api.project44.com/api/v4
```
For European carriers. Using the Americas URL instead causes routing issues.

**Key rules:**
- Use separate credentials for sandbox and production — never cross them
- Confirm which base URL your system is configured against before troubleshooting
- The most common 404 cause is a sandbox URL being used in production
- After completing sandbox testing, update the base URL before go-live""",
    },
    {
        "category": "🔗 Endpoints & URLs",
        "question": "Do TL and LTL use the same endpoint?",
        "keywords": ["tl", "ltl", "same", "endpoint", "different", "which", "truckload"],
        "answer": """**No — TL and LTL use different endpoints.** This is one of the most important things to get right.

| Mode | Endpoint |
|---|---|
| **TL (Truckload)** | `POST /api/v4/capacityproviders/tl/shipments/statusUpdates` |
| **LTL (Less-than-Truckload)** | `POST /api/v4/capacityproviders/ltl/shipments/statusupdates` |

**They also have different requirements:**

| | TL | LTL |
|---|---|---|
| Shipment identifier | `BILL_OF_LADING` or `ORDER` | PRO number |
| Status field name | `eventType` | `statusCode` |
| GPS coordinates | Required | Not required |
| Carrier identifier | SCAC, DOT, MC, P44_EU, P44_GLOBAL, SYSTEM | SCAC only |
| Terminal events | Not applicable | `ARRIVED_AT_TERMINAL`, `DEPARTED_TERMINAL` |

Sending TL payloads to the LTL endpoint (or vice versa) will result in 400 or 404 errors.""",
    },

    # ── Integration Setup ───────────────────────────────────────────────────
    {
        "category": "⚙️ Integration Setup",
        "question": "What identifier do I use for LTL shipments?",
        "keywords": ["ltl", "identifier", "pro", "pro number", "shipment id", "identify"],
        "answer": """**LTL shipments are identified by PRO number.**

PRO number (Progressive Rotating Order) is the unique freight identifier assigned by the carrier when they pick up the shipment.

**In your payload:**
```json
"shipmentIdentifiers": [
  { "type": "PRO", "value": "123456789" }
]
```

**For TL shipments:** Use `BILL_OF_LADING` or `ORDER` instead.

**Important:** The PRO number must match exactly what is in the project44 platform. If the shipper used a different PRO format than what you're sending, the update will arrive as a 202 (received) but fail to match downstream — the shipper will see nothing.

Always confirm the PRO number format with your project44 integration contact before testing.""",
    },
    {
        "category": "⚙️ Integration Setup",
        "question": "My SCAC isn't being recognised — what are my options?",
        "keywords": ["scac", "not recognised", "no scac", "carrier id", "identifier", "alternative"],
        "answer": """If your SCAC isn't working or you don't have one, TL integrations support alternative carrier identifiers:

| Identifier Type | What it is |
|---|---|
| `SCAC` | Standard Carrier Alpha Code — most common |
| `DOT_NUMBER` | US DOT number — federal motor carrier ID |
| `MC_NUMBER` | Motor Carrier number — FMCSA issued |
| `P44_EU` | project44 European carrier ID |
| `P44_GLOBAL` | project44 global carrier ID |
| `SYSTEM` | Internal system identifier |

**In your TL payload:**
```json
"carrierIdentifier": {
  "type": "DOT_NUMBER",
  "value": "1234567"
}
```

**Note:** LTL integrations accept SCAC only — no alternatives. If you don't have a SCAC for LTL, contact your project44 integration manager.

**If your SCAC exists but isn't being recognised:** Confirm the SCAC is registered and active in the project44 platform. Contact your integration manager to verify.""",
    },
    {
        "category": "⚙️ Integration Setup",
        "question": "What eventType values can I send for TL?",
        "keywords": ["eventtype", "event type", "tl", "values", "truckload", "status", "what can i send"],
        "answer": """**TL `eventType` accepted values:**

| Value | What it means |
|---|---|
| `IN_TRANSIT` | Truck is moving between stops |
| `ARRIVED` | Truck has arrived at a stop |
| `DEPARTED` | Truck has departed a stop |
| `DELIVERED` | Shipment delivered — final status |
| `POSITION` | GPS location update only (no status change) |

**Rules:**
- The value must match exactly — `"ARRIVE"` will cause a 400 (it must be `"ARRIVED"`)
- `DELIVERED` closes the shipment record
- `POSITION` alone has low value — best practice is to combine a status event with a position update
- When sending `ARRIVED` or `DEPARTED`, include `eventStopNumber` to identify which stop

**Example with stop number:**
```json
{
  "eventType": "ARRIVED",
  "eventStopNumber": 1,
  "latitude": 41.8781,
  "longitude": -87.6298
}
```""",
    },
    {
        "category": "⚙️ Integration Setup",
        "question": "What statusCode values can I send for LTL?",
        "keywords": ["statuscode", "status code", "ltl", "values", "less than truckload", "what can i send"],
        "answer": """**LTL `statusCode` accepted values:**

| Status Code | What it means |
|---|---|
| `READY_FOR_PICKUP` | Freight ready to be collected |
| `UPDATED_PICKUP_APPT` | Pickup appointment changed |
| `PICKED_UP` | Carrier has collected the freight |
| `ARRIVED_AT_TERMINAL` | Freight arrived at a carrier hub |
| `DEPARTED_TERMINAL` | Freight left the hub |
| `REWEIGHT_RECLASS` | Weight or freight class corrected |
| `INFO` | General information update |
| `UPDATED_DELIVERY_APPT` | Delivery appointment changed |
| `OUT_FOR_DELIVERY` | On the delivery vehicle, final mile |
| `DELIVERED` | **Final status — closes the shipment** |
| `EXCEPTION` | Something went wrong |

**Extra requirements:**

For `EXCEPTION`: must include reason codes:
```json
"statusReason": {
  "reasonSummaryCode": "DELAY",
  "reasonDetailCode": "WEATHER"
}
```

For `PICKED_UP`, `DELIVERED`, `ARRIVED_AT_TERMINAL`, `DEPARTED_TERMINAL`: must include `stopType` (ORIGIN, DESTINATION, or TERMINAL) and `stopNumber`.

`DELIVERED` is mandatory — do not close an integration without sending it.""",
    },

    # ── Server Errors ───────────────────────────────────────────────────────
    {
        "category": "🔴 Server Errors",
        "question": "I'm getting a 500 Internal Server Error",
        "keywords": ["500", "internal server", "server error", "p44", "platform"],
        "answer": """**Fault:** project44 — not you.

**What it means:** An unhandled exception occurred on project44's platform. Your request was valid — the platform broke while processing it.

**Do NOT ask the carrier to change anything — their payload was fine.**

**What to do:**
1. Copy the `requestId` from the response body — this is the key reference for Engineering
2. Note the exact timestamp
3. Save the full payload that triggered the error
4. Note the frequency — is this happening on one request, or all requests?

**Escalate internally to Engineering with:**
- `requestId`
- Timestamp of the error
- Full request payload
- Frequency (one-off or recurring?)

**What to tell the carrier:**
> "We've identified an issue on our side and are investigating. Your integration is set up correctly."

**If it resolves on its own:** May have been transient. Monitor for recurrence.
**If it persists:** Engineering must prioritise it — do not let the carrier keep retrying against a broken endpoint.""",
    },
    {
        "category": "🔴 Server Errors",
        "question": "What does a 502 or 503 error mean?",
        "keywords": ["502", "503", "bad gateway", "service unavailable", "down", "maintenance"],
        "answer": """Both are **project44 infrastructure errors** — not caused by anything on your side.

**502 Bad Gateway**
An upstream service that project44 depends on returned an invalid response. Almost always transient.
- Wait 2–3 minutes and retry
- If it persists beyond 10 minutes, escalate internally
- Tell the carrier to implement retry logic with backoff so they handle this automatically in future

**503 Service Unavailable**
project44's platform is temporarily overloaded or down for maintenance.
- Check the `Retry-After` header — it tells you exactly how many seconds to wait
- Tell the carrier to back off and retry after the specified interval
- If this occurs during a go-live: **pause the go-live**. Communicate to the shipper: *"We're experiencing a brief platform issue — we will resume shortly"*
- Escalate internally if it exceeds 15 minutes

**For both:** Do not ask the carrier to change their payload or configuration — the issue is on project44's infrastructure side.""",
    },
    {
        "category": "🔴 Server Errors",
        "question": "I'm getting 429 Too Many Requests",
        "keywords": ["429", "rate limit", "too many", "requests", "throttle", "backoff"],
        "answer": """**Fault:** Carrier side (for push integrations).

**What it means:** You are sending requests faster than project44's rate limit allows.

**Immediate fix:**
1. Check the `Retry-After` header — it tells you exactly how many seconds to wait before retrying
2. Stop sending until that time has elapsed
3. Resume at a lower frequency

**Root cause — check if the carrier is:**
- Sending on every GPS ping (potentially hundreds per hour) instead of on status events only
- Retrying failed requests in a tight loop without backoff

**Permanent fix — implement exponential backoff:**
- After a 429, wait, retry, wait twice as long, retry, etc.
- Respect the `Retry-After` header value on every 429

**For parcel/polling integrations:** 429 is the most common failure mode.
- Reduce polling frequency
- Batch multiple tracking numbers in a single API call where the carrier supports it
- Remove DELIVERED and cancelled shipments from active polling immediately — they don't need polling

If your legitimate update volume genuinely exceeds the rate limit, contact project44 to request an increase.""",
    },
    {
        "category": "🔴 Server Errors",
        "question": "A 403 Forbidden — is this my fault?",
        "keywords": ["403", "forbidden", "permission", "scope", "access", "authorised"],
        "answer": """**Fault:** Carrier side — but specifically a credential configuration issue, not a payload issue.

**What it means:** Your token is valid and authentication passed — but the credentials don't have permission to access this specific endpoint or resource.

**Difference from 401:**
- 401 = *"Who are you?"* — identity not established
- 403 = *"I know who you are, but you can't do this"* — identity established, permission denied

**What to check:**
1. Are you hitting the right endpoint for your freight type? Using the TL endpoint when your credentials are scoped for LTL (or vice versa) causes 403
2. Does the client application have the correct roles assigned in project44?
3. Has the client application been added to the correct access groups?

**Fix:**
- Confirm the credential scope matches the endpoint being called
- Re-issue credentials with the correct permissions if needed
- Contact your project44 integration manager to verify role and access group setup""",
    },
]

SHIPPER_FAQ = [
    # ── Tracking Gaps ───────────────────────────────────────────────────────
    {
        "category": "📍 Tracking Gaps",
        "question": "I can see pickup but no updates since then",
        "keywords": ["pickup", "no updates", "nothing since", "stopped", "gap", "after pickup", "picked up"],
        "answer": """This is normal behaviour for LTL shipments — and the most common question shippers have.

**Why it happens:** LTL tracking is milestone-based, not continuous GPS. project44 only shows updates when the carrier sends them. Between milestones, there are no updates to show.

**The LTL journey:**
1. ✅ `PICKED_UP` — you saw this
2. ⏳ *(freight travelling to first terminal — no update until it arrives)*
3. `ARRIVED_AT_TERMINAL` — freight arrives at carrier hub
4. *(freight being sorted and reloaded)*
5. `DEPARTED_TERMINAL` — freight leaves the hub
6. *(repeat for each terminal in the route)*
7. `OUT_FOR_DELIVERY` — on the delivery truck
8. `DELIVERED`

**Typical gap times:** 4–24 hours between PICKED_UP and ARRIVED_AT_TERMINAL depending on distance. Multi-day transit = multiple terminal stops.

**Action needed?** Only if it's been more than 48 hours with no update and the expected transit time is shorter than that. In that case, contact your project44 account manager to verify the carrier integration is active.""",
    },
    {
        "category": "📍 Tracking Gaps",
        "question": "Tracking stopped after Arrived at Terminal",
        "keywords": ["arrived at terminal", "stopped", "terminal", "hub", "stuck", "no update after"],
        "answer": """**This is normal — your freight is at a carrier hub being sorted.**

`ARRIVED_AT_TERMINAL` means the freight has reached a carrier sorting facility. It is being:
- Unloaded from the inbound trailer
- Scanned and sorted
- Reloaded onto an outbound trailer going toward the delivery destination

The next update you'll see is `DEPARTED_TERMINAL` when it leaves the hub.

**Typical dwell time:** 4–24 hours is normal. During peak periods or bad weather, dwell times can extend to 36–48 hours.

**If freight is at terminal for more than 48 hours** with no update and no exception status:
1. Note the terminal location shown on the platform
2. Contact the carrier directly with the PRO number — ask for the status at that terminal
3. Contact your project44 account manager if you suspect the carrier isn't sending updates

**One terminal or multiple?** Long-distance LTL shipments typically go through 2–4 terminals. Each ARRIVED_AT_TERMINAL → DEPARTED_TERMINAL pair is one hub. This is expected.""",
    },
    {
        "category": "📍 Tracking Gaps",
        "question": "There are no updates at all on my shipment",
        "keywords": ["no updates", "nothing", "blank", "no tracking", "no data", "not showing", "empty"],
        "answer": """If you're seeing zero updates — not even a PICKED_UP — work through this checklist:

**1. Is the PRO number correct?**
LTL shipments are tracked by PRO number. Confirm the exact PRO number with the carrier — even one digit off means no match.

**2. Did the carrier actually pick up the shipment?**
project44 can only show updates the carrier sends. If the carrier picked up the freight but didn't send a PICKED_UP event, there will be no tracking start.

**3. Is this carrier integrated with project44?**
Not all carriers have active integrations. Contact your project44 account manager to confirm whether this specific carrier is actively sending data.

**4. Is the shipment in the right time window?**
Some carriers have a delay before their first update — allow up to 4 hours after confirmed pickup before escalating.

**5. Check the shipment record on the platform:**
Is the shipment record created? If the shipment itself isn't visible (not just missing updates), there may be a data entry issue with how the shipment was created in the platform.

**Escalate to your project44 account manager** if the carrier confirmed pickup more than 4 hours ago and nothing is showing.""",
    },
    {
        "category": "📍 Tracking Gaps",
        "question": "Why hasn't tracking started yet?",
        "keywords": ["tracking", "start", "hasn't started", "not started", "beginning", "when does tracking start"],
        "answer": """**For LTL shipments:** Tracking starts when the carrier sends `PICKED_UP`. Until that event is sent, the shipment record exists on the platform but shows no movement.

**For TL shipments:** Tracking typically starts when the driver is assigned to the load and begins sending GPS pings. This may happen before physical pickup.

**Common reasons tracking hasn't started:**
- The carrier has a delay in processing and sending PICKED_UP (some carriers batch their updates)
- The pickup hasn't happened yet
- The driver hasn't been assigned yet (TL)
- The PRO number on the platform doesn't match what the carrier is using

**How long to wait:**
- Allow up to 4 hours after confirmed pickup before escalating
- If pickup was confirmed yesterday and there's still nothing, escalate

**What to do:**
1. Confirm with the carrier that pickup happened and get the PRO number directly from them
2. Verify the PRO number in project44 matches exactly
3. Contact your project44 account manager if it's been more than 4 hours since confirmed pickup""",
    },

    # ── Status Meanings ─────────────────────────────────────────────────────
    {
        "category": "📋 Status Meanings",
        "question": "What does ARRIVED_AT_TERMINAL mean?",
        "keywords": ["arrived at terminal", "terminal", "what does", "mean", "hub", "facility"],
        "answer": """**ARRIVED_AT_TERMINAL** means your freight has reached one of the carrier's sorting hubs or freight terminals.

**What's happening:** The freight has been unloaded from an inbound trailer and is being processed at the hub — scanned, sorted, and prepared to be loaded onto an outbound trailer toward the delivery destination.

**This is a normal, expected step** in the LTL journey. Long-distance shipments typically pass through 2–4 terminals.

**What comes next:** `DEPARTED_TERMINAL` — when the freight leaves the hub on an outbound trailer. Dwell time at the terminal is typically 4–24 hours.

**The terminal location** shown on the platform is the hub address, not your freight's final destination.

**Does this mean there's a problem?** No — unless it's been more than 48 hours at the same terminal with no update and no exception status. In that case, contact the carrier with the PRO number to get a status update.""",
    },
    {
        "category": "📋 Status Meanings",
        "question": "What's the difference between OUT_FOR_DELIVERY and DELIVERED?",
        "keywords": ["out for delivery", "delivered", "difference", "final", "last mile"],
        "answer": """**OUT_FOR_DELIVERY**
The freight has been loaded onto the local delivery truck and is on its way to the final destination. The driver is actively making deliveries on their route. Your shipment will be delivered today (or at the scheduled appointment time if there is one).

This status does not mean the freight has arrived — it means it is in transit on the last mile, on a truck that is making multiple stops.

---

**DELIVERED**
The freight has been physically delivered and the carrier has confirmed it. This is the **final status** — it closes the shipment record in project44.

After DELIVERED, the shipment is considered complete. No further tracking updates will be sent.

---

**If you see OUT_FOR_DELIVERY but the shipment doesn't arrive today:**
- The driver may have run out of time (hours of service) and rescheduled
- There may have been a delivery issue — check if an EXCEPTION status follows
- Contact the carrier with the PRO number for an update""",
    },
    {
        "category": "📋 Status Meanings",
        "question": "My shipment shows IN_TRANSIT — where is it exactly?",
        "keywords": ["in transit", "where is it", "location", "position", "exactly", "where"],
        "answer": """The answer depends on whether your shipment is TL or LTL:

**TL (Truckload) — IN_TRANSIT with live GPS**
For TL shipments, `IN_TRANSIT` comes with GPS coordinates. The map on the platform shows the truck's actual current position. This updates regularly as the carrier sends position pings.

**LTL (Less-than-Truckload) — no GPS between milestones**
For LTL, `IN_TRANSIT` or the equivalent (the gap between DEPARTED_TERMINAL and ARRIVED_AT_TERMINAL) means the freight is on a trailer somewhere between two terminals. There is no live GPS position for LTL — only the last known terminal location is shown.

**If you need to know the exact location of an LTL shipment in transit:**
Contact the carrier directly with the PRO number. They can check their internal systems for the trailer number and current location.

**ETA shown on platform:** This is the carrier's estimated arrival time. For TL it's calculated from GPS position. For LTL it's provided by the carrier and may change as the shipment moves through terminals.""",
    },
    {
        "category": "📋 Status Meanings",
        "question": "What does DEPARTED_TERMINAL mean?",
        "keywords": ["departed terminal", "departed", "left terminal", "left hub", "what does mean"],
        "answer": """**DEPARTED_TERMINAL** means your freight has left a carrier sorting hub and is now in transit to the next stop — either another terminal or the delivery destination.

**What happened:** The freight was loaded onto an outbound trailer at the hub and that trailer has now departed.

**What comes next:**
- If there are more terminals in the route: `ARRIVED_AT_TERMINAL` at the next hub
- If this is the last leg: `OUT_FOR_DELIVERY` followed by `DELIVERED`

**How do you know if there are more terminals?** The platform may show the destination terminal. You can also check the carrier's transit time estimate — multi-day transits usually involve multiple terminals.

**Departed but not arrived at next terminal yet?** Normal. The freight is on a truck between hubs. Transit between terminals can take anywhere from a few hours to overnight depending on distance.""",
    },

    # ── Exceptions & Delays ─────────────────────────────────────────────────
    {
        "category": "⚠️ Exceptions & Delays",
        "question": "My shipment has EXCEPTION status — what happened?",
        "keywords": ["exception", "what happened", "problem", "issue", "exception status", "went wrong"],
        "answer": """**EXCEPTION** means the carrier has flagged a problem with the shipment. It does not mean the shipment is lost.

**Common exception reasons:**

| Reason | What it means |
|---|---|
| Weather delay | Adverse weather affecting transit |
| Mechanical | Truck breakdown or equipment issue |
| Missed delivery | Delivery attempted but not completed |
| Refused delivery | Consignee refused to accept the freight |
| Address issue | Problem with the delivery address |
| Damaged freight | Carrier noted damage |

**What to do:**
1. Check the exception details on the platform — a reason code should be shown
2. Contact the carrier directly with the PRO number — they have the operational detail
3. If the delivery was refused or there's an address issue, work with the carrier to arrange redelivery

**Does EXCEPTION mean the shipment is cancelled?** No. Exceptions are often resolved and delivery continues. The carrier will send further updates — either a new delivery attempt status or DELIVERED once resolved.

**Contact your project44 account manager** if the exception reason code isn't visible on the platform or if the exception has been unresolved for more than 48 hours.""",
    },
    {
        "category": "⚠️ Exceptions & Delays",
        "question": "The ETA keeps changing — is something wrong?",
        "keywords": ["eta", "changing", "keeps changing", "estimate", "moving", "different", "wrong"],
        "answer": """**For LTL shipments: changing ETAs are completely normal — this is not a platform error.**

**Why ETAs change for LTL:**
- The carrier recalculates ETA each time the freight moves through a terminal
- Terminal dwell times vary (sorting speed, volume, driver availability)
- Weather or mechanical issues cause recalculation
- The route may have been adjusted (e.g. going through a different terminal)

**For TL shipments:**
TL ETAs are calculated from GPS position and route. They update as the truck moves. If traffic causes a delay, the ETA adjusts automatically. This is the system working correctly.

**When should you be concerned?**
- ETA has slipped by more than 24 hours with no exception status
- ETA is showing as "unknown" or blank when it was previously showing
- The shipment has missed its delivery appointment and there's no communication from the carrier

**What to do if ETA has slipped significantly:**
1. Check if there's an EXCEPTION status explaining the delay
2. Contact the carrier directly with the PRO number for an operational update
3. If a delivery appointment exists and is at risk, contact the consignee to manage expectations""",
    },
    {
        "category": "⚠️ Exceptions & Delays",
        "question": "How do I find out why there's an exception?",
        "keywords": ["exception", "why", "reason", "find out", "cause", "details", "reason code"],
        "answer": """**Step 1 — Check the platform**
The exception status should include a reason code. Look at the shipment detail view for the exception event — it should show something like "DELAY / WEATHER" or "MISSED_DELIVERY / ACCESS_ISSUE".

**Step 2 — Contact the carrier directly**
The carrier has the operational detail that project44 can only reflect if the carrier sends it. Call or email the carrier with:
- The PRO number
- The shipment origin, destination, and expected delivery date
- Ask: what is the exception, and what is the revised delivery plan?

**Step 3 — Contact your project44 account manager if:**
- The exception reason code isn't visible on the platform
- The carrier claims they sent an update but it's not showing in project44
- The exception has been unresolved for more than 48 hours

**Common exception reason codes:**

| Code | Meaning |
|---|---|
| WEATHER | Adverse weather |
| MECHANICAL | Equipment breakdown |
| MISSED_DELIVERY | Delivery attempted, not completed |
| REFUSED | Consignee refused delivery |
| ADDRESS_ISSUE | Delivery address problem |
| DAMAGED | Freight damage noted |""",
    },
    {
        "category": "⚠️ Exceptions & Delays",
        "question": "What does a REWEIGHT_RECLASS status mean?",
        "keywords": ["reweight", "reclass", "weight", "class", "freight class", "corrected"],
        "answer": """**REWEIGHT_RECLASS** means the carrier has corrected either the weight or the freight class of your shipment.

**What happened:**
When freight is processed at a terminal, the carrier may weigh it or inspect it and find that the declared weight or freight class doesn't match the actual shipment.

**Why it matters:**
LTL pricing is based on weight, freight class, and distance. A reweight or reclass will affect the final invoice. You may receive a billing adjustment.

**What to do:**
1. Note the date and terminal where this occurred (shown in the event details)
2. Compare the corrected values against what was originally declared
3. If the adjustment seems incorrect, contact the carrier with the PRO number and the original declared weight/class
4. Review the final invoice when it arrives — it will reflect the corrected values

**This does not mean there is a problem with the delivery itself.** The shipment will continue moving normally. REWEIGHT_RECLASS is an administrative update, not a service failure.

**If you dispute the reweight:** Contact the carrier directly — they can provide the scale ticket and inspection details.""",
    },

    # ── Delivery Issues ─────────────────────────────────────────────────────
    {
        "category": "✅ Delivery Issues",
        "question": "Tracking shows DELIVERED but we didn't receive the shipment",
        "keywords": ["delivered", "not received", "didn't receive", "shows delivered", "wrong", "dispute"],
        "answer": """This needs to be resolved urgently. Here's the priority order:

**1. Contact the carrier immediately**
Call the carrier with the PRO number. Ask for:
- The name of the person who signed for the delivery
- The time and date of delivery
- A copy of the Proof of Delivery (POD)

The carrier's driver will have a delivery record. A DELIVERED status without a valid POD is a serious issue.

**2. Check the delivery location**
- Was the freight delivered to the correct address?
- Could it have been received by someone else at your facility?
- Could it have been left at a different dock or entrance?

**3. Contact your project44 account manager**
Let them know DELIVERED was shown but freight wasn't received. They can:
- Verify that the DELIVERED event came from the carrier (not a data error)
- Confirm the PRO number matched correctly to the right shipment
- Escalate if the event appears to be a mismatch

**4. Document everything**
Keep a record of when you noticed the discrepancy, who you spoke to at the carrier, and what was said. This is important for any freight claim.

**Do not assume the freight is lost** until you've confirmed with the carrier — many cases are resolved by finding freight was received at a different dock.""",
    },
    {
        "category": "✅ Delivery Issues",
        "question": "The delivery location looks wrong on the map",
        "keywords": ["location", "wrong", "map", "incorrect", "address", "showing wrong place"],
        "answer": """There are a few common explanations — most are not cause for concern:

**For LTL shipments:**
The map location often shows the **terminal address**, not your freight's exact location. LTL freight moves through carrier hubs, and the platform shows the last known terminal. The terminal may be in a different city to your delivery destination — this is normal.

**For TL shipments:**
The map shows the **truck's GPS position**. The truck may be:
- Taking a route that looks unusual (detour, roadworks, fuel stop)
- At a rest stop or overnight parking location
- In a staging area near the destination before the delivery appointment

**When to be concerned:**
- TL: the truck appears to have stopped in an unexpected location for more than 12 hours with no explanation (check for EXCEPTION status)
- LTL: the terminal location shown is in the wrong country or completely unrelated to the expected route

**What to do if something looks genuinely wrong:**
Contact the carrier with the PRO number (LTL) or BOL number (TL) and ask for the current location and status of the shipment.""",
    },
    {
        "category": "✅ Delivery Issues",
        "question": "My shipment was refused — what does that mean?",
        "keywords": ["refused", "refusal", "rejected", "consignee", "refused delivery", "exception"],
        "answer": """**Refused delivery** means the person at the delivery address declined to accept the freight when the carrier's driver arrived.

**You'll typically see this as:**
- `EXCEPTION` status with reason code `REFUSED`
- Or a note in the exception details saying "consignee refused"

**Common reasons freight is refused:**
- Freight arrived damaged
- Freight arrived at the wrong time (missed appointment)
- The consignee was not expecting the delivery
- The wrong quantity or items were delivered
- The consignee no longer wants the goods

**What to do:**
1. **Contact the consignee** — find out why they refused and whether they want the freight redelivered
2. **Contact the carrier** — the freight is now being held or returned. You need to instruct them on what to do (redelivery, return to origin, hold at terminal)
3. **Act quickly** — carriers charge storage fees for freight held at their facilities. The longer you wait, the higher the cost

**Important:** Refused freight will often be returned to origin if you don't provide instructions within a short window (typically 3–5 business days). Confirm with the carrier what their policy is and act accordingly.""",
    },
    {
        "category": "✅ Delivery Issues",
        "question": "When should I contact the carrier vs project44?",
        "keywords": ["contact", "who", "carrier", "project44", "escalate", "account manager", "call"],
        "answer": """**Contact the carrier directly for:**
- Operational questions about a specific shipment (where is it, when will it arrive)
- Exceptions, delays, or delivery issues requiring action (redelivery, return, dispute)
- Proof of delivery requests
- Damaged freight claims
- Refused delivery instructions
- Anything requiring the carrier to take a physical action

**Contact your project44 account manager for:**
- Tracking not showing when the carrier says they're sending updates
- A carrier integration appears to be down (multiple shipments with no updates)
- DELIVERED shown but freight wasn't received and you need to verify the data
- Adding a new carrier to your tracking setup
- Configuring alert thresholds or notification rules
- Billing or account questions related to the platform

**A useful rule:** If the question is about *what happened to the freight* — call the carrier. If the question is about *what's showing on the platform* — contact project44.

The two are sometimes both needed: if freight was delivered but not showing as DELIVERED on the platform, you'd confirm delivery with the carrier and then contact project44 if the status doesn't update.""",
    },
]

# ── Build lookup indexes ────────────────────────────────────────────────────────

def score_match(query: str, keywords: list[str]) -> int:
    q = query.lower()
    return sum(1 for kw in keywords if kw.lower() in q)

def find_matches(query: str, faq: list[dict], top_n: int = 3) -> list[dict]:
    scored = [(score_match(query, item["keywords"]), item) for item in faq]
    scored = [(s, item) for s, item in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_n]]

# ── Session state ──────────────────────────────────────────────────────────────

for key, default in {
    "mode": "carrier",
    "selected": None,
    "search_results": [],
    "last_query": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Who are you?")
    mode_choice = st.radio(
        "role",
        options=["carrier", "shipper"],
        format_func=lambda x: "🔧 Carrier — API integration" if x == "carrier" else "📦 Shipper — tracking & visibility",
        label_visibility="collapsed",
    )
    if mode_choice != st.session_state.mode:
        st.session_state.mode = mode_choice
        st.session_state.selected = None
        st.session_state.search_results = []
        st.session_state.last_query = ""

    st.divider()
    st.markdown("### Browse by topic")

    faq = CARRIER_FAQ if st.session_state.mode == "carrier" else SHIPPER_FAQ
    categories = {}
    for item in faq:
        categories.setdefault(item["category"], []).append(item)

    for cat, items in categories.items():
        with st.expander(cat, expanded=False):
            for item in items:
                if st.button(
                    item["question"],
                    key=f"btn_{abs(hash(item['question']))}",
                    use_container_width=True,
                ):
                    st.session_state.selected = item
                    st.session_state.search_results = []
                    st.session_state.last_query = ""
                    st.rerun()

    st.divider()
    if st.button("↩ Back to start", use_container_width=True):
        st.session_state.selected = None
        st.session_state.search_results = []
        st.session_state.last_query = ""
        st.rerun()

# ── Main area ──────────────────────────────────────────────────────────────────

if st.session_state.mode == "carrier":
    st.title("🔧 Carrier Integration Support")
    st.caption("For carriers integrating with the project44 API.")
else:
    st.title("📦 Shipper Tracking Support")
    st.caption("For shippers tracking shipments on project44.")

query = st.text_input(
    "Search",
    placeholder="Type a keyword or question — e.g. '401', 'LTL endpoint', 'exception status'",
    label_visibility="collapsed",
)

if query and query != st.session_state.last_query:
    st.session_state.last_query = query
    st.session_state.search_results = find_matches(query, faq)
    st.session_state.selected = None

st.divider()

# ── Show selected answer ────────────────────────────────────────────────────────

if st.session_state.selected:
    item = st.session_state.selected
    st.markdown(f"## {item['question']}")
    st.markdown(item["answer"])

# ── Show search results ─────────────────────────────────────────────────────────

elif st.session_state.search_results:
    results = st.session_state.search_results
    if len(results) == 1:
        st.markdown(f"## {results[0]['question']}")
        st.markdown(results[0]["answer"])
    else:
        st.markdown(f"**{len(results)} results for:** _{query}_")
        for i, item in enumerate(results):
            with st.expander(item["question"], expanded=(i == 0)):
                st.markdown(item["answer"])

elif query and not st.session_state.search_results:
    st.warning(f"No results for **{query}**. Try a different keyword, or browse by topic in the sidebar.")

# ── Welcome screen ──────────────────────────────────────────────────────────────

else:
    if st.session_state.mode == "carrier":
        st.markdown("""
Search above or use the sidebar to browse topics:

- **Authentication** — 401 errors, token expiry, header format, generating tokens
- **Payload & Errors** — 400, 422, required fields, LTL and TL payloads
- **Endpoints & URLs** — which URL to use, 404 errors, sandbox vs production
- **Integration Setup** — identifiers, SCAC alternatives, eventType and statusCode values
- **Server Errors** — 500, 502, 503, 429, 403

**Quick searches to try:** `401` · `400` · `LTL endpoint` · `SCAC` · `429` · `500` · `sandbox`
""")
    else:
        st.markdown("""
Search above or use the sidebar to browse topics:

- **Tracking Gaps** — no updates after pickup, stopped at terminal, tracking not started
- **Status Meanings** — what each status event means in plain English
- **Exceptions & Delays** — exception status, changing ETAs, reason codes
- **Delivery Issues** — DELIVERED but not received, refused freight, who to contact

**Quick searches to try:** `exception` · `terminal` · `ETA` · `delivered` · `no updates` · `refused`
""")
