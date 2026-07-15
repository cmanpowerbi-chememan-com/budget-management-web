"""A11/A12 scheduled jobs — auto_submit, auto_escalate, send_reminders.

Run from `backend/` as `python -m jobs.<name> --fiscal-year <year> [--execute]`.
Every job defaults to a dry-run preview (never-cut safety rule); see
`jobs/common.py` for the shared CLI/logging scaffolding these jobs share.
"""
