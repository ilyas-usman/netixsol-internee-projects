# Week 7 Day 4 — Task 4: n8n Workflow Automation

Built on top of everything else — no Python code changes except one small
additive endpoint (`POST /api/crm/clients/upsert`, for n8n's dedicated CRM
step to call independently).

## What this is

Two ready-to-paste n8n workflows:

| File | Purpose |
|---|---|
| `crm-call-automation-workflow.json` | The main pipeline: Call → Intent → Property Match → Appointment → Calendar → Email → CRM Update |
| `crm-call-automation-error-handler.json` | A companion workflow that fires automatically whenever the main one fails, after retries are exhausted |

### Why it calls your FastAPI backend instead of re-building the AI in n8n

Your Python backend already does the hard part correctly — intent
classification, RAG/SQL property matching, and the entire booking
conversation (Tasks 1-3) — behind one endpoint, `/api/chat`. Re-implementing
that NLU inside n8n nodes would be strictly worse (a second, weaker copy of
logic you've already built and tested). Instead, this workflow uses n8n for
what n8n is actually good at: **being the reliable outer shell** — trigger
handling, branching, retries, and failure alerting — around a single call
into your existing intelligence.

```text
Call/chat event (e.g. Vapi's end-of-call-report webhook)
        │
        ▼
[Webhook: Incoming Call Event]
        │
        ▼
[Set: Normalize Call Data]              (session_id, phone, channel, transcript)
        │
        ▼
[HTTP Request: AI Intent + Property Match]   → POST /api/chat   (retry x3)
        │   (this one call does BOTH intent detection AND property
        │    matching — that's exactly what day3_agent.run_turn() does)
        ▼
[Set: Merge Call + Response Data]
        │
        ▼
[IF: Is Appointment Related?] ──── No ──→ [Property Search / General Turn Handled]
        │ Yes
        ▼
[Code: Check If Booking Finalized]     (regex on the reply for "confirm ho gayi" / an ID)
        │
        ▼
[IF: Booking Confirmed?] ──── No ──→ [Booking Not Yet Finalized (mid-conversation)]
        │ Yes
        ▼
[HTTP Request: Fetch Appointment]        → GET /api/appointments/by-id/{id}   (retry x3)
   (Calendar + Email already happened inside the /api/chat call above —
    this step is the "did it really persist?" confirmation)
        │
        ▼
[HTTP Request: CRM Update — Upsert Client]     → POST /api/crm/clients/upsert   (retry x3)
        │
        ▼
[HTTP Request: CRM Update — Create Follow-up]  → POST /api/crm/reminders        (retry x3, non-blocking)
        │
        ▼
[Pipeline Complete]
```

## How to import

1. Open n8n → create a new, blank workflow.
2. Open `crm-call-automation-workflow.json` in a text editor, select all,
   copy.
3. Click on the empty n8n canvas and paste (**Ctrl+V** / **Cmd+V**) — n8n
   creates every node and connection automatically.
   - Alternatively: workflow list → **Import from File** → pick the JSON.
4. Repeat for `crm-call-automation-error-handler.json` as a **second,
   separate** workflow.
5. In the main workflow → **⋯ menu → Settings** → set **Error Workflow** to
   the error-handler workflow you just imported (this is what makes retries
   + final failure alerting actually connect the two).

## Before you activate it

1. **Replace the backend URL.** Every HTTP Request node points at
   `https://YOUR_PUBLIC_DOMAIN`. Find-and-replace that with wherever your
   `app_day3.py` is actually deployed and reachable from the internet (n8n
   needs a real, public HTTPS URL — not `localhost` — unless n8n itself
   runs on the same machine/network).
2. **Point your call/chat source at the webhook.** After activating the
   workflow, n8n shows a **Production URL** for the "Incoming Call Event"
   node, e.g. `https://your-n8n-instance/webhook/crm-call-automation`. If
   you're using Vapi (as `vapi_property_tool.json` in this project already
   does), set that URL as the assistant's **serverUrl** for
   **end-of-call-report** events in your Vapi dashboard. For a text-chat
   source, just POST `{ "session_id": "...", "phone": "...", "transcript": "..." }`
   to that same URL.
3. **No n8n-side credentials are required** for the main workflow — every
   step is a plain HTTP Request to your own backend, which already handles
   its own Google Calendar / Gmail credentials internally (Tasks 1 & 2).
4. The **Notify Staff** node in the error handler is intentionally a NoOp
   — swap it for n8n's built-in Gmail, Slack, or Microsoft Teams node
   (whichever you use) and wire in your own credential. It's left as a
   placeholder so the workflow imports and runs cleanly before you've set
   any notification channel up.

## How failures and retries are handled

- **Every HTTP Request node** has `retryOnFail: true`, `maxTries: 3`, and a
  3-second wait between attempts — transient backend hiccups (a cold start,
  a momentary DB lock) resolve themselves without any manual intervention.
- **The CRM follow-up reminder step** is additionally set to
  `continueRegularOutput` on error — a failure there (least critical step)
  doesn't stop the workflow or trigger a failure alert; the booking itself
  already succeeded by that point.
- **When retries are exhausted anywhere in the main workflow**, n8n
  automatically hands off to the **Error Handler** workflow (via the
  Settings → Error Workflow link from step 5 above), which:
  1. Captures which node failed and why.
  2. Logs it as an urgent CRM reminder (`client_phone: "SYSTEM"`) via your
     existing `/api/crm/reminders` endpoint, so a failed automation is never
     silently lost — someone will see it the next time anyone checks
     `/api/crm/reminders/due`.
  3. Has a placeholder node ready for you to plug in a real staff
     notification (Slack/Email/Teams).

## Testing it manually

Once imported and pointed at your deployed backend, send a test event with
curl (simulating a call/chat transcript where the client just confirmed a
booking):

```bash
curl -X POST https://your-n8n-instance/webhook/crm-call-automation \
  -H "Content-Type: application/json" \
  -d '{
        "session_id": "n8n-manual-test-1",
        "phone": "+923001234567",
        "channel": "chat",
        "transcript": "haan confirm"
      }'
```

Check the n8n **Executions** tab to see each node run, and
`GET /api/crm/clients/+923001234567` on your backend to confirm the CRM
Update step actually landed.
