# Day 4 Update — How to Apply

This is a DELTA package: only new and modified files. Your existing project
(Property.csv, realestate.db, chroma_db/, day3_memory.db, .venv/, etc.) is
untouched and NOT included here — it's large and nothing in it changed.

## 1. Copy every Python/JSON/config file in this folder into your project root
(the same folder as `app_day3.py`), **except** `env-additions.txt` and this
`APPLY-INSTRUCTIONS.md`:

```
day4_config.py
employees.json
appointment_store.py
calendar_service.py
email_service.py
appointment_agent.py
requirements-day4.txt
test_day4.py
day4-README.md
crm_config.py
crm_store.py
crm_agent.py
app_day3.py       <- replaces your existing app_day3.py
day3_agent.py     <- replaces your existing day3_agent.py
```

`app_day3.py` and `day3_agent.py` are the only two existing files that
changed, and both changes are purely additive — verified by diffing against
your original upload with zero lines removed. (New endpoints appended in
app_day3.py; two small guarded hooks added to day3_agent.py's run_turn() —
one for appointments, one for CRM.)

`crm-call-automation-workflow.json`, `crm-call-automation-error-handler.json`,
and `day4-task4-n8n-README.md` are **not** Python files — they go into n8n,
not your project folder. See step 7.

## 2. Add the Day 4 settings to your `.env`
Open `env-additions.txt` and paste its contents onto the end of your
existing `.env` file. Nothing in your current `.env` needs to change —
these are new keys only, and every one of them is optional (safe defaults
are used if left blank).

## 3. Edit `employees.json`
Replace the placeholder names/emails with your real staff.

## 4. (Optional) Install real Google Calendar / Gmail support
```
pip install -r requirements-day4.txt
```
Skip this and everything still works via the local calendar + console-log
email fallback. Full Google Cloud + Gmail setup steps are in
`day4-README.md`.

## 5. Test
```
python test_day4.py
```
This covers Tasks 1-3 (calendar/email fallback, booking, reschedule,
cancel, business hours) and Task 5 (CRM transcripts, preferences, auto
follow-up reminders, conversational client history/reminders) — plus
several tests that confirm none of it ever interferes with your existing
Day 2/Day 3 conversation flow.

## 6. Run exactly as before
```
python -m uvicorn app_day3:app --reload
```

## 7. Task 4 — n8n Workflow Automation
Two more files, `crm-call-automation-workflow.json` and
`crm-call-automation-error-handler.json`, are ready-to-paste n8n workflows
(Call → Intent → Property Match → Appointment → Calendar → Email → CRM
Update, with retries + failure alerting). They call the backend above over
plain HTTP — no extra Python changes needed except the one new endpoint
already included in `app_day3.py` (`POST /api/crm/clients/upsert`).

See `day4-task4-n8n-README.md` for exact import steps (it's a literal
copy-paste onto the n8n canvas), what URL to replace, and how the
retry/error-handling is wired.

Full documentation: see `day4-README.md` (Tasks 1-3 + 5) and
`day4-task4-n8n-README.md` (Task 4).
