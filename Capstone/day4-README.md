# Week 7 — Day 4: Workflows, Scheduling & Business Automation

Day 4 is implemented directly on top of the Day 3 project. **Every Day 2 and
Day 3 file behaves exactly as before** — nothing was rewritten, and the only
two existing files touched at all are `day3_agent.py` (one small guarded
hook at the top of `run_turn()`) and `app_day3.py` (new endpoints appended
after the existing ones). Everything else is new files.

Because both text chat (`/api/chat`) and voice (`/ws/voice/{session_id}`)
already funnel through `day3_agent.run_turn()`, appointment booking,
rescheduling and cancellation work identically **on chat and on a live
call** with zero extra wiring — there is nothing voice-specific to build.

## Architecture

```text
User message (chat or voice, transcribed by Deepgram as in Day 3)
        │
        ▼
day3_agent.run_turn(session_id, text)
        │
        ▼
appointment_agent.handle_appointment_turn()   <-- NEW, Day 4
        │  returns None if this turn is not appointment-related
        │  (booking/reschedule/cancel intent, or a flow already
        │  in progress for this session)
        │
   ┌────┴─────────────────────────┐
   │ None                         │ not None
   ▼                              ▼
Day 3 graph runs exactly    Day 4 owns this turn:
as before (SQL/RAG/         - extract slots (name, phone, date,
objections/chat)              time, property, notes)
                             - ask for whatever is missing
                             - check business hours
                             - check employee availability
                               (calendar_service)
                             - ask the client to confirm
                               ("are you free at this time?")
                             - on confirm: create/update/delete
                               the calendar event, store the
                               appointment, email the employee
                               (email_service)
                             - on a successful booking/cancel:
                               log the client + preferences and
                               schedule a follow-up reminder
                               (crm_store) — Task 5
        │
        ▼
crm_agent.log_turn_to_crm()   <-- NEW, Day 4 Task 5
runs on EVERY turn, regardless of route: logs the transcript,
and merges known preferences once a phone number is linked.
```

## New files (Day 4)

| File | Purpose |
|---|---|
| `day4_config.py` | All Day 4 settings (Calendar, Email, business hours). Every setting has a safe default/fallback. |
| `employees.json` | Staff directory (name/email/phone) used to assign appointments. **Replace the placeholders with your real team.** |
| `appointment_store.py` | Its own SQLite database (`appointments.db`) for appointment records and in-progress booking conversations. Does **not** touch `day3_memory.db`. |
| `calendar_service.py` | `GoogleCalendarProvider` (real Google Calendar) + `LocalCalendarProvider` (SQLite-backed fallback), auto-selected. |
| `email_service.py` | `GmailAPIEmailProvider`, `SMTPEmailProvider`, `ConsoleEmailProvider` (logs to a file), auto-selected. |
| `appointment_agent.py` | Intent detection, Urdu/Roman-Urdu/English slot extraction, and the booking/reschedule/cancel conversation flow. |
| `requirements-day4.txt` | Extra packages needed only for real Google Calendar/Gmail API use. |
| `test_day4.py` | Automated tests — run with `python test_day4.py`. |
| `crm_config.py` | Task 5 CRM settings (follow-up delays, which slots count as preferences). |
| `crm_store.py` | Task 5 CRM storage — its own SQLite database (`crm.db`): clients, transcripts, follow-up reminders. |
| `crm_agent.py` | Task 5 CRM conversational commands (client history/profile, add/list reminders) + unconditional per-turn transcript/preference logging. |

## Task 1 — Google Calendar Integration

Every appointment event includes client name, phone, employee, property,
date/time and meeting notes (see `GoogleCalendarProvider.create_event` in
`calendar_service.py`). Until you configure Google credentials, the
**local fallback calendar** (backed by `appointments.db`) is used
automatically — booking, conflict detection, reschedule and cancel all work
end-to-end without any Google setup, which is what `test_day4.py` exercises.

## Task 2 — Email Automation

`email_service.py` emails the assigned employee on every book / reschedule /
cancel, with meeting time, property, client details and requirements/notes
(`send_employee_notification`, `send_employee_reschedule_notice`,
`send_employee_cancellation_notice`). It supports **both** transports you
asked for:

- **Gmail API** (OAuth or a domain-wide-delegated service account)
- **SMTP** (works with a Gmail "App Password", or any SMTP server)

If neither is configured, emails are written to `appointment_emails.log`
instead of failing silently, so nothing breaks before you set up real
credentials.

## Task 3 — Appointment Management

Booking, rescheduling and cancellation are all conversational (English +
Roman Urdu + Urdu script), over chat or a call:

- **Booking**: "mujhe property visit ke liye appointment book karni hai" →
  the agent asks for whatever's missing (name, phone, date, time — the
  property is inferred from the last property you were shown), checks
  business hours and the assigned employee's availability, then explicitly
  asks **"Confirm karein — aap is waqt free hain?"** before creating
  anything.
- **Rescheduling**: "mujhe apni appointment reschedule karni hai" → finds
  your existing appointment, asks for the new date/time, re-checks
  availability, confirms, then updates the calendar event and emails the
  employee.
- **Cancelling**: "cancel appointment kardo" → confirms, then deletes the
  calendar event, marks it cancelled, and emails the employee.

Every step re-checks:
1. **Business hours** (`BUSINESS_HOURS_START`/`END`, `BUSINESS_DAYS` in `.env`)
2. **Employee availability** (double-booking check via `calendar_service`)
   — if busy, the next available slot is suggested automatically.

There are also direct REST endpoints (for a dashboard, n8n, or QA — the
conversational flow above does **not** need these):

| Endpoint | Purpose |
|---|---|
| `GET /api/employees` | List the staff directory |
| `GET /api/appointments/availability?date=YYYY-MM-DD` | Booked slots per employee for a day |
| `POST /api/appointments/book` | Book directly (bypasses the chat flow) |
| `POST /api/appointments/reschedule` | Reschedule by `appointment_id` |
| `POST /api/appointments/cancel` | Cancel by `appointment_id` |
| `GET /api/appointments/{session_id}` | List a session's appointments |
| `GET /api/appointments/by-id/{appointment_id}` | Fetch one appointment |

## Task 5 — CRM Logging

Built on top of Tasks 1-3, with zero further changes to Day 2/Day 3 code.
Two new files (`crm_config.py`, `crm_store.py`, `crm_agent.py` — its own
SQLite database, `crm.db`) add a running CRM layer:

- **Call transcripts**: every turn (chat or voice) is logged automatically
  — no command needed. Once a client's phone number is known (typically
  from a booking), transcripts are retroactively linked to that client too.
- **Client preferences**: whenever a phone is known, their budget, city,
  bedrooms, purpose and property-type slots (from Day 3's conversation
  memory) are merged into a standing preferences record.
- **Appointment history**: pulled live from `appointment_store` (Task 3) —
  every booking, reschedule and cancellation, not duplicated storage.
- **Follow-up reminders**: created automatically —
  - one day after a completed viewing ("check how the visit went"),
  - a few days after a cancellation ("win-back" follow-up) —
  and can also be created/listed conversationally by staff, on chat or a
  call, e.g.:
  - `"03211234567 ka profile dikhao"` → preferences, appointment count, pending follow-ups
  - `"follow up karna hai 03211234567 5 din baad payment plan discuss karna hai"` → creates a reminder for that date with that note
  - `"meri reminders dikhao 03211234567"` → lists that client's pending follow-ups

CRM commands never interrupt an in-progress booking/reschedule/cancel
conversation — they're checked first, but immediately defer if a
booking flow already owns that session.

REST endpoints (dashboard/n8n/QA use):

| Endpoint | Purpose |
|---|---|
| `GET /api/crm/clients` | List all known clients |
| `GET /api/crm/clients/{phone}` | Full profile: client + preferences + appointment history + reminders + recent transcripts |
| `GET /api/crm/transcripts/{session_id}` | Transcript for one session |
| `GET /api/crm/clients/{phone}/transcripts` | Transcript history for one client |
| `POST /api/crm/reminders` | Create a reminder directly |
| `GET /api/crm/reminders/due` | Reminders due today or earlier (for a staff dashboard) |
| `GET /api/crm/reminders?phone=&status=` | Filtered reminder list |
| `POST /api/crm/reminders/{id}/complete` | Mark a reminder done |
| `POST /api/crm/reminders/{id}/cancel` | Cancel a reminder |

---

## Where to put your API keys

All Day 4 settings go in the existing **`.env`** file — I appended a new,
clearly-marked section to it (nothing existing was changed or removed).
Open `.env` and fill in whichever of these you want to use:

```env
# --- Google Calendar (service account) ---
GOOGLE_SERVICE_ACCOUNT_FILE=./google_service_account.json
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=Asia/Karachi
CALENDAR_MODE=auto

# --- Email ---
EMAIL_PROVIDER=auto              # gmail_api | smtp | console | auto

# Gmail API (Workspace, domain-wide delegation)
GMAIL_SERVICE_ACCOUNT_FILE=./google_service_account.json
GMAIL_DELEGATED_USER=

# Gmail API (personal @gmail.com, OAuth token)
GMAIL_OAUTH_CLIENT_SECRET_FILE=./gmail_oauth_client_secret.json
GMAIL_OAUTH_TOKEN_FILE=./gmail_oauth_token.json

# SMTP (Gmail App Password or any SMTP server)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
ADMIN_NOTIFICATION_EMAIL=
```

Put the downloaded **service-account JSON key file itself** (not its
contents pasted into `.env`) in the project root, next to `app_day3.py`, as
`google_service_account.json` (or point `GOOGLE_SERVICE_ACCOUNT_FILE` /
`GMAIL_SERVICE_ACCOUNT_FILE` at wherever you saved it). **Never commit this
file** — add it to `.gitignore`.

Also edit **`employees.json`** with your real staff (name, email, phone) —
this is what appointments get assigned against.

### How to set up Google Calendar (service account)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create
   a project (or reuse one).
2. **APIs & Services → Library** → enable **Google Calendar API**.
3. **APIs & Services → Credentials → Create Credentials → Service account**.
   Give it any name (e.g. "booking-bot").
4. Open the new service account → **Keys → Add key → Create new key → JSON**.
   This downloads the file — save it as `google_service_account.json` in
   the project root.
5. Copy the service account's **email address** (looks like
   `booking-bot@your-project.iam.gserviceaccount.com`).
6. Open **Google Calendar** in the browser, under the calendar you want to
   book into → **Settings and sharing → Share with specific people** → add
   the service-account email with **"Make changes to events"** permission.
7. Set `GOOGLE_CALENDAR_ID` in `.env` to that calendar's ID (found in the
   same Settings page, under "Integrate calendar" — for a normal Google
   account's primary calendar this is just `primary`).

That's it — no OAuth consent screen or user login needed for Calendar,
since the service account itself is the "user" writing events.

### How to set up Gmail — two options

**Option A: SMTP with an App Password (simplest, works for any Gmail account)**
1. On the Gmail account you want to send from, enable 2-Step Verification.
2. Go to [Google Account → Security → App passwords](https://myaccount.google.com/apppasswords).
3. Generate an app password for "Mail".
4. In `.env`: set `EMAIL_PROVIDER=smtp`, `SMTP_USER=youraddress@gmail.com`,
   `SMTP_PASSWORD=<the 16-character app password>`,
   `SMTP_FROM_EMAIL=youraddress@gmail.com`.

**Option B: Gmail API (needed if you want a Google Workspace service
account to send "as" a shared mailbox, e.g. `bookings@yourcompany.com`)**
1. Same Google Cloud project as above → enable **Gmail API**.
2. Reuse the same service account, or create a new one.
3. In **Google Workspace Admin Console** (requires a Workspace admin) →
   **Security → API controls → Domain-wide delegation** → add the service
   account's **Client ID** with scope
   `https://www.googleapis.com/auth/gmail.send`.
4. In `.env`: `EMAIL_PROVIDER=gmail_api`,
   `GMAIL_DELEGATED_USER=bookings@yourcompany.com`.

   This option does **not** work for a personal `@gmail.com` account
   (domain-wide delegation requires Workspace) — use Option A for that.

If you skip both, `EMAIL_PROVIDER=auto` (the default) falls back to writing
emails to `appointment_emails.log` instead of sending them, so the rest of
the app keeps working while you set email up.

---

## Installing the extra dependencies

```bash
pip install -r requirements-day4.txt
```

This only adds the Google client libraries. Nothing else changes — your
existing `requirements-day3.txt` install still works exactly as before, and
the app still runs with zero Day 4 packages installed (using the local
calendar + console email fallback).

## Running & testing

Startup is unchanged — same command as Day 3:

```bash
python -m uvicorn app_day3:app --reload
```

Run the Day 4 tests (booking, conflict detection, reschedule, cancel,
business-hours enforcement, and confirmation that ordinary Day 2/3 messages
are never intercepted):

```bash
python test_day4.py
```

Try it manually in chat (`/api/chat` or the existing `ui/` frontend — no UI
changes were needed, it's just conversation):

```
You: DHA Phase 5 Lahore mein ghar dikhao
Bot: [existing Day 3 property search — unchanged]
You: is property ke liye appointment book karni hai
Bot: Ji bilkul, appointment book kar dete hain. Aapka poora naam? ...
You: mera naam Ali Raza hai, number 03001234567
Bot: Kis din aana chahenge...
You: kal shaam 5 baje
Bot: Ji, 2026-08-31 ko 17:00 baje, House, DHA Phase 5, Lahore ke liye
     Usama Khan ke sath appointment set kar sakte hain. Confirm karein —
     aap is waqt free hain? (haan/nahi)
You: haan
Bot: Ji, appointment confirm ho gayi hai (ID: ab12cd34ef). ...
     Employee ko email bhi bhej di gayi hai.
```

The exact same conversation works over `/ws/voice/{session_id}` with no
changes on your end.

## Design notes / known limits

- Date/time parsing is regex-based (matching the pragmatic style already
  used in `day3_router.py`/`day3_objections.py`), not a full NLU date
  parser — it covers "aaj/kal/parso", weekday names (English + Roman Urdu +
  Urdu script), "15 September", `DD/MM/YYYY`, `HH:MM`, and "5 baje" style
  Urdu times with an AM/PM heuristic. Edge cases (e.g. relative expressions
  like "agle hafte") may need a follow-up pass if real transcripts surface
  them — the same honest caveat Day 3 already gives for its own heuristics.
- Employee assignment first tries to match the property's own `agent`
  field (already present in `realestate.db`) against `employees.json`;
  otherwise it round-robins across the staff list by current load.
- The local fallback calendar and console-log email are there so the whole
  system is 100% testable and demoable before any Google/Gmail credentials
  exist — swap in real credentials whenever you're ready, no code changes
  needed.
