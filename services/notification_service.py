"""
Notification service — YCloud WhatsApp sending.

SETUP (add to .env):
  YCLOUD_API_KEY=your_ycloud_api_key
  YCLOUD_WHATSAPP_NUMBER=+919XXXXXXXXXX   # your registered WhatsApp Business number
"""
import logging
import requests
from datetime import datetime

from sqlalchemy.orm import Session

from config import settings
from database.models import (
    Appointment, NotificationLog, NotificationChannel, NotificationType,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Phone formatting                                                    #
# ------------------------------------------------------------------ #

def _e164(phone: str) -> str:
    """Convert various Indian phone formats to E.164 (+91XXXXXXXXXX)."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        return phone                      # already E.164
    if phone.startswith("91") and len(phone) == 12:
        return f"+{phone}"               # 919876543210 → +919876543210
    if len(phone) == 10:
        return f"+91{phone}"             # 9876543210  → +919876543210
    return f"+{phone}"                   # best-effort for unusual formats


# ------------------------------------------------------------------ #
#  Low-level sender (YCloud)                                           #
# ------------------------------------------------------------------ #

def send_whatsapp(to_phone: str, message: str) -> tuple[bool, str]:
    """Send a WhatsApp message via YCloud REST API.

    Returns (success: bool, id_or_error: str).
    Never raises — failures are returned as (False, reason).
    """
    if not settings.YCLOUD_API_KEY or not settings.YCLOUD_WHATSAPP_NUMBER:
        return False, "YCloud not configured"
    try:
        resp = requests.post(
            "https://api.ycloud.com/v2/whatsapp/messages",
            headers={
                "X-API-Key": settings.YCLOUD_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "from": settings.YCLOUD_WHATSAPP_NUMBER,
                "to": _e164(to_phone),
                "type": "text",
                "text": {"body": message},
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return True, resp.json().get("id", "sent")
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        logger.error(f"YCloud WhatsApp error: {e}")
        return False, str(e)


# ------------------------------------------------------------------ #
#  Send with fallback (single channel — WhatsApp only)                #
# ------------------------------------------------------------------ #

def _send_with_fallback(
    phone: str, message: str
) -> tuple[bool, NotificationChannel, str]:
    """Send via WhatsApp (YCloud). Returns (success, channel, id_or_error)."""
    ok, sid = send_whatsapp(phone, message)
    return ok, NotificationChannel.whatsapp, sid


# ------------------------------------------------------------------ #
#  Message builders                                                    #
# ------------------------------------------------------------------ #

def _confirmation_msg(appt: Appointment, doctor) -> str:
    clinic_name = doctor.clinic_name or f"Dr. {doctor.name}'s clinic"
    date_str = appt.appointment_date.strftime("%-d %b %Y")
    t = appt.appointment_time
    hour = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    time_str = f"{hour}:{t.minute:02d} {ampm}"

    lines = [
        f"Hello {appt.patient.name},\n",
        f"Your appointment at *{clinic_name}* is confirmed.",
        f"Date: *{date_str}*  Time: *{time_str}*",
        f"Duration: {appt.duration_mins} mins",
    ]
    if doctor.clinic_address:
        lines.append(
            f"Address: {doctor.clinic_address}, {doctor.city or ''}".rstrip(", ")
        )
    lines.append("\nPlease arrive 5 minutes early. To reschedule, call the clinic directly.")
    return "\n".join(lines)


def _reminder_msg(appt: Appointment, doctor, reminder_type: str) -> str:
    clinic   = doctor.clinic_name or f"Dr. {doctor.name}'s clinic"
    t        = appt.appointment_time
    hour     = t.hour % 12 or 12
    ampm     = "AM" if t.hour < 12 else "PM"
    time_str = f"{hour}:{t.minute:02d} {ampm}"
    date_str = appt.appointment_date.strftime("%-d %b %Y")

    if reminder_type == "24h":
        return (
            f"Reminder: You have an appointment at *{clinic}* "
            f"tomorrow (*{date_str}*) at *{time_str}*.\n\n"
            f"See you then!"
        )
    # 2h
    return (
        f"Reminder: Your appointment at *{clinic}* "
        f"is in about 2 hours, at *{time_str}* today.\n\n"
        f"See you soon!"
    )


# ------------------------------------------------------------------ #
#  DB log helper                                                       #
# ------------------------------------------------------------------ #

def _log(
    appt_id,       # int or None — nullable since bill/walk-in logs have no appointment
    notif_type: NotificationType,
    channel: NotificationChannel,
    message: str,
    status: str,
    db: Session,
):
    entry = NotificationLog(
        appointment_id=appt_id,
        type=notif_type,
        channel=channel,
        message_body=message,
        status=status,
        sent_at=datetime.utcnow() if status == "sent" else None,
    )
    db.add(entry)
    db.commit()


# ------------------------------------------------------------------ #
#  High-level triggers (called from routers / scheduler)              #
# ------------------------------------------------------------------ #

def notify_appointment_confirmed(appt: Appointment, doctor, db: Session):
    """Send booking confirmation via WhatsApp (YCloud).

    Called immediately after an appointment is created (by doctor or patient).
    Failure is logged but never raises — the booking always succeeds.
    """
    _ = appt.patient  # ensure lazy-loaded
    message = _confirmation_msg(appt, doctor)

    success, channel, result = _send_with_fallback(appt.patient.phone, message)
    status = "sent" if success else "failed"
    _log(appt.id, NotificationType.confirmation, channel, message, status, db)

    if success:
        logger.info(f"Confirmation sent ({channel.value}) for appt #{appt.id} id={result}")
    else:
        logger.warning(f"Confirmation failed for appt #{appt.id}: {result}")


def notify_followup_confirmed(appt: Appointment, doctor, db: Session):
    """Send follow-up appointment confirmation via WhatsApp."""
    if not appt.patient or not appt.patient.phone:
        return
    clinic_name = doctor.clinic_name or f"Dr. {doctor.name}'s clinic"
    date_str = appt.appointment_date.strftime("%-d %b %Y")
    t = appt.appointment_time
    hour = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    time_str = f"{hour}:{t.minute:02d} {ampm}"

    message = (
        f"Hello {appt.patient.name},\n\n"
        f"Your follow-up appointment at *{clinic_name}* is confirmed.\n"
        f"Date: *{date_str}*  Time: *{time_str}*\n"
        f"Duration: {appt.duration_mins} mins\n\n"
        f"Please bring your previous reports and prescriptions.\n"
        f"To reschedule, call the clinic directly."
    )
    ok, channel, sid = _send_with_fallback(appt.patient.phone, message)
    _log(appt.id, NotificationType.confirmation, channel, message, "sent" if ok else "failed", db)


def notify_reminder(appt: Appointment, doctor, db: Session, reminder_type: str):
    """Send a reminder via WhatsApp.

    Called by the background scheduler.
    """
    _ = appt.patient  # ensure lazy-loaded
    message = _reminder_msg(appt, doctor, reminder_type)

    success, channel, result = _send_with_fallback(appt.patient.phone, message)
    notif_type = (
        NotificationType.reminder_24h if reminder_type == "24h"
        else NotificationType.reminder_2h
    )
    status = "sent" if success else "failed"
    _log(appt.id, notif_type, channel, message, status, db)

    if success:
        logger.info(f"{reminder_type} reminder sent ({channel.value}) for appt #{appt.id} id={result}")
    else:
        logger.warning(f"{reminder_type} reminder failed for appt #{appt.id}: {result}")


def notify_walkin_queued(visit, doctor, db: Session):
    """Send queue position + estimated wait to a walk-in patient."""
    patient = visit.patient
    if not patient or not patient.phone:
        return
    clinic_name = doctor.clinic_name or f"Dr. {doctor.name}'s clinic"

    # Count WAITING visits ahead in queue
    from database.models import Visit as VisitModel, VisitStatus
    people_ahead = db.query(VisitModel).filter(
        VisitModel.doctor_id == doctor.id,
        VisitModel.visit_date == visit.visit_date,
        VisitModel.status == VisitStatus.waiting,
        VisitModel.queue_position < visit.queue_position,
    ).count()

    avg_mins = doctor.avg_consult_mins or 10
    estimated_wait = people_ahead * avg_mins

    message = (
        f"Hello {patient.name},\n\n"
        f"You are checked in at *{clinic_name}*.\n"
        f"Token: *#{visit.token_number}*\n"
        f"People ahead of you: *{people_ahead}*\n"
        f"Estimated wait: *~{estimated_wait} mins*\n\n"
        f"We will call you shortly."
    )
    ok, channel, sid = _send_with_fallback(patient.phone, message)
    _log(None, NotificationType.walkin_queue, channel, message, "sent" if ok else "failed", db)


def notify_bill_receipt(bill, doctor, db: Session):
    """Send a text bill receipt to the patient via WhatsApp."""
    from database.models import Patient
    patient = db.query(Patient).filter(Patient.id == bill.patient_id).first()
    if not patient or not patient.phone:
        return
    clinic_name = doctor.clinic_name or f"Dr. {doctor.name}'s clinic"

    # Build items list (top 3)
    items = list(bill.items)[:3] if bill.items else []
    if items:
        items_text = "\n".join(f"• {i.description}: ₹{i.total:.0f}" for i in items)
    else:
        items_text = f"• Consultation: ₹{bill.total:.0f}"

    # Payment mode label
    mode_labels = {
        "cash":      "Cash",
        "upi":       "UPI",
        "card":      "Card",
        "insurance": "Insurance",
        "free":      "Free",
        "partial":   "Partial",
    }
    mode_label = mode_labels.get(
        bill.payment_mode.value if bill.payment_mode else "cash", "Cash"
    )

    message = (
        f"Hello {patient.name},\n\n"
        f"Your bill at *{clinic_name}* has been recorded.\n\n"
        f"{items_text}\n"
        f"Total: *₹{bill.total:.0f}*\n"
        f"Paid via: {mode_label}\n\n"
        f"Thank you for visiting *{clinic_name}*."
    )
    ok, channel, sid = _send_with_fallback(patient.phone, message)
    _log(None, NotificationType.bill_receipt, channel, message, "sent" if ok else "failed", db)
