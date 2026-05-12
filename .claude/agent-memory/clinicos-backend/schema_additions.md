---
name: Schema Additions Tracker
description: Columns and tables added via _run_migrations() beyond the CLAUDE.md baseline, tracked to avoid duplicate migrations
type: project
---

Track all `_add_column` calls added after the initial CLAUDE.md baseline. Prevents duplicate migrations across sessions.

## 2026-05-12
- `doctors.avg_consult_mins` — INTEGER DEFAULT 10 — for walk-in wait time estimates (YCloud notification system)
- `notifications_log.appointment_id` — changed to nullable=True in ORM model (SQLite cannot ALTER NOT NULL → NULL, but new rows will have nullable FK)

## NotificationType enum additions (2026-05-12)
- `walkin_queue` — walk-in queue position notification
- `bill_receipt` — bill payment receipt notification
