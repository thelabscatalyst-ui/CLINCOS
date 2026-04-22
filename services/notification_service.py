"""
Notification service — Twilio WhatsApp + SMS sending.

SETUP REQUIRED (see README section below):
  1. Create a free Twilio account at twilio.com
  2. Get your Account SID + Auth Token from the Twilio Console
  3. Activate the WhatsApp Sandbox (free, no approval needed for testing)
  4. Add credentials to your .env file
"""
import logging
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
#  Twilio client (lazy, graceful if not configured)                   #
# ------------------------------------------------------------------ #

def _twilio_client():
    """Return a Twilio REST client, or None if credentials are missing."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.debug("Twilio credentials not configured — notifications skipped.")
        return None
    try:
        from twilio.rest import Client
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception as exc:
        logger.warning(f"Twilio client init failed: {exc}")
        return None


# ------------------------------------------------------------------ #
#  Low-level senders                                                   #
# ------------------------------------------------------------------ #

def send_whatsapp(to_phone: str, message: str) -> tuple[bool, str]:
    """Send a WhatsApp message via Twilio.

    Returns (success: bool, sid_or_error: str).
    Never raises — failures are returned as (False, reason).
    """
    client = _twilio_client()
    if not client:
        return False, "Twilio not configured"
    try:
        msg = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,          # "whatsapp:+14155238886"
            to=f"whatsapp:{_e164(to_phone)}",
            body=message,
        )
        return True, msg.sid
    except Exception as exc:
        logger.error(f"WhatsApp send failed to {to_phone}: {exc}")
        return False, str(exc)


def send_sms(to_phone: str, message: str) -> tuple[bool, str]:
    """Send a plain SMS via Twilio.

    Returns (success: bool, sid_or_error: str).
    Only used if TWILIO_SMS_FROM is set in .env.
    """
    if not settings.TWILIO_SMS_FROM:
        return False, "TWILIO_SMS_FROM not configured"
    client = _twilio_client()
    if not client:
        return False, "Twilio not configured"
    try:
        msg = client.messages.create(
            from_=settings.TWILIO_SMS_FROM,
            to=_e164(to_phone),
            body=message,
        )
        return True, msg.sid
    except Exception as exc:
        logger.error(f"SMS send failed to {to_phone}: {exc}")
        return False, str(exc)


# ------------------------------------------------------------------ #
#  Message builders                                                    #
# ------------------------------------------------------------------ #

def _confirmation_msg(appt: Appointment, doctor) -> str:
    clinic   = doctor.clinic_name or f"Dr. {doctor.name}'s clinic"
    date_str = appt.appointment_date.strftime("%d %b %Y")
    time_str = appt.appointment_time.strftime("%I:%M %p").lstrip("0")
    return (
        f"Hello {appt.patient.name},\n\n"
        f"Your appointment at *{clinic}* is confirmed.\n"
        f"Date: *{date_str}*  Time: *{time_str}*\n"
        f"Duration: {appt.duration_mins} mins\n\n"
        f"Please arrive 5 minutes early. "
        f"To reschedule, call the clinic directly."
    )


def _reminder_msg(appt: Appointment, doctor, reminder_type: str) -> str:
    clinic   = doctor.clinic_name or f"Dr. {doctor.name}'s clinic"
    time_str = appt.appointment_time.strftime("%I:%M %p").lstrip("0")
    date_str = appt.appointment_date.strftime("%d %b %Y")

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
    appt_id: int,
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

def _send_with_fallback(
    phone: str, message: str
) -> tuple[bool, NotificationChannel, str]:
    """Try WhatsApp first; fall back to SMS if WhatsApp fails.

    Returns (success, channel_used, sid_or_error).
    """
    success, result = send_whatsapp(phone, message)
    if success:
        return True, NotificationChannel.whatsapp, result

    # WhatsApp failed — try SMS if configured
    sms_success, sms_result = send_sms(phone, message)
    if sms_success:
        return True, NotificationChannel.sms, sms_result

    return False, NotificationChannel.whatsapp, result  # both failed


def notify_appointment_confirmed(appt: Appointment, doctor, db: Session):
    """Send booking confirmation — tries WhatsApp, falls back to SMS.

    Called immediately after an appointment is created (by doctor or patient).
    Failure is logged but never raises — the booking always succeeds.
    """
    _ = appt.patient  # ensure lazy-loaded
    message = _confirmation_msg(appt, doctor)

    success, channel, result = _send_with_fallback(appt.patient.phone, message)
    status = "sent" if success else "failed"
    _log(appt.id, NotificationType.confirmation, channel, message, status, db)

    if success:
        logger.info(f"Confirmation sent ({channel.value}) for appt #{appt.id} sid={result}")
    else:
        logger.warning(f"Confirmation failed for appt #{appt.id}: {result}")


def notify_reminder(appt: Appointment, doctor, db: Session, reminder_type: str):
    """Send a reminder — tries WhatsApp, falls back to SMS.

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
        logger.info(f"{reminder_type} reminder sent ({channel.value}) for appt #{appt.id} sid={result}")
    else:
        logger.warning(f"{reminder_type} reminder failed for appt #{appt.id}: {result}")
