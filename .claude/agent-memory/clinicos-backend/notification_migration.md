---
name: Notification System Migration to YCloud
description: Twilio fully removed; YCloud REST API replaces it for WhatsApp; new notification types and nullable appointment_id
type: project
---

Twilio was removed from the notification system on 2026-05-12. YCloud REST API now handles all WhatsApp sending.

**Why:** Approved architectural decision — no Twilio SDK, no SMS fallback, simpler integration via `requests` HTTP calls.

**How to apply:** All future notification work uses `send_whatsapp()` in `services/notification_service.py` which calls `https://api.ycloud.com/v2/whatsapp/messages`. SMS is gone. `_send_with_fallback` is now a thin wrapper around `send_whatsapp` only.

**Key changes made:**
- `config.py`: Added `YCLOUD_API_KEY` and `YCLOUD_WHATSAPP_NUMBER` fields. Twilio fields kept as deprecated so existing `.env` files don't break.
- `database/models.py`: `NotificationLog.appointment_id` changed to `nullable=True` — bill receipt and walk-in queue logs have no appointment_id. New enum values: `walkin_queue`, `bill_receipt`.
- `database/models.py`: `Doctor.avg_consult_mins` column added (INTEGER DEFAULT 10) — drives walk-in wait time estimates.
- `services/notification_service.py`: Full rewrite. New functions: `notify_walkin_queued`, `notify_bill_receipt`, `notify_followup_confirmed`.
- `routers/appointments.py`: `create_appointment` now sends `notify_followup_confirmed` for follow_up type, `notify_appointment_confirmed` for others. `create_walkin` sends `notify_walkin_queued` after check-in.
- `routers/billing_ops.py`: `create_bill` triggers `generate_and_store_bill_pdf` + `notify_bill_receipt`. `mark_bill_paid` triggers `notify_bill_receipt`.
- `routers/doctors.py`: `save_schedule` now accepts `avg_consult_mins: int = Form(10)` and saves it to `doctor.avg_consult_mins`.

**Bill receipt = text-only** — no PDF attachment in WhatsApp. PDF still auto-saves to vault silently via `generate_and_store_bill_pdf`.
