from datetime import date, time, datetime, timedelta
from typing import List, Tuple
from sqlalchemy.orm import Session

from database.models import (
    Appointment, AppointmentStatus, DoctorSchedule, BlockedDate, Patient
)


def _generate_slots(start: time, end: time, duration_mins: int) -> List[time]:
    """Generate all time slots between start and end with given duration."""
    slots = []
    current = datetime.combine(date.today(), start)
    end_dt = datetime.combine(date.today(), end)
    delta = timedelta(minutes=duration_mins)
    while current + delta <= end_dt:
        slots.append(current.time())
        current += delta
    return slots


def get_available_slots(doctor_id: int, appt_date: date, db: Session) -> List[str]:
    """Return list of available HH:MM time slots for a doctor on a given date."""
    # Check blocked date
    blocked = db.query(BlockedDate).filter(
        BlockedDate.doctor_id == doctor_id,
        BlockedDate.blocked_date == appt_date,
    ).first()
    if blocked:
        return []

    # Get schedule for that day of week (0=Mon … 6=Sun)
    dow = appt_date.weekday()
    schedule = db.query(DoctorSchedule).filter(
        DoctorSchedule.doctor_id == doctor_id,
        DoctorSchedule.day_of_week == dow,
        DoctorSchedule.is_active == True,
    ).first()
    if not schedule:
        return []

    # All slots for this shift
    all_slots = _generate_slots(schedule.start_time, schedule.end_time, schedule.slot_duration)

    # Already-booked (non-cancelled) appointments
    booked = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appt_date,
        Appointment.status != AppointmentStatus.cancelled,
    ).all()

    # max_patients cap
    if len(booked) >= schedule.max_patients:
        return []

    booked_times = {a.appointment_time for a in booked}
    available = [s for s in all_slots if s not in booked_times]

    return [s.strftime("%H:%M") for s in available]


def is_slot_available(
    doctor_id: int, appt_date: date, appt_time: time, db: Session
) -> Tuple[bool, str]:
    """Returns (True, '') if slot is available, or (False, reason) otherwise."""
    # Blocked date check
    blocked = db.query(BlockedDate).filter(
        BlockedDate.doctor_id == doctor_id,
        BlockedDate.blocked_date == appt_date,
    ).first()
    if blocked:
        return False, "This date is blocked. Please choose another date."

    # Schedule check
    dow = appt_date.weekday()
    schedule = db.query(DoctorSchedule).filter(
        DoctorSchedule.doctor_id == doctor_id,
        DoctorSchedule.day_of_week == dow,
        DoctorSchedule.is_active == True,
    ).first()
    if not schedule:
        return False, "No working hours set for this day. Check Settings → Schedule."

    if appt_time < schedule.start_time or appt_time >= schedule.end_time:
        return (
            False,
            f"Time is outside working hours "
            f"({schedule.start_time.strftime('%H:%M')} – {schedule.end_time.strftime('%H:%M')}).",
        )

    # Double-booking check
    conflict = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appt_date,
        Appointment.appointment_time == appt_time,
        Appointment.status != AppointmentStatus.cancelled,
    ).first()
    if conflict:
        return False, "This time slot is already booked."

    # Max-patients cap
    day_count = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appt_date,
        Appointment.status != AppointmentStatus.cancelled,
    ).count()
    if day_count >= schedule.max_patients:
        return False, "Maximum patients for this day has been reached."

    return True, ""


def is_slot_available_for_edit(
    doctor_id: int, appt_date: date, appt_time: time,
    exclude_appt_id: int, db: Session
) -> Tuple[bool, str]:
    """Same as is_slot_available but ignores the appointment being edited."""
    blocked = db.query(BlockedDate).filter(
        BlockedDate.doctor_id == doctor_id,
        BlockedDate.blocked_date == appt_date,
    ).first()
    if blocked:
        return False, "This date is blocked. Please choose another date."

    dow = appt_date.weekday()
    schedule = db.query(DoctorSchedule).filter(
        DoctorSchedule.doctor_id == doctor_id,
        DoctorSchedule.day_of_week == dow,
        DoctorSchedule.is_active == True,
    ).first()
    if not schedule:
        return False, "No working hours set for this day. Check Settings → Schedule."

    if appt_time < schedule.start_time or appt_time >= schedule.end_time:
        return (
            False,
            f"Time is outside working hours "
            f"({schedule.start_time.strftime('%H:%M')} – {schedule.end_time.strftime('%H:%M')}).",
        )

    conflict = db.query(Appointment).filter(
        Appointment.id != exclude_appt_id,
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appt_date,
        Appointment.appointment_time == appt_time,
        Appointment.status != AppointmentStatus.cancelled,
    ).first()
    if conflict:
        return False, "This time slot is already booked."

    day_count = db.query(Appointment).filter(
        Appointment.id != exclude_appt_id,
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appt_date,
        Appointment.status != AppointmentStatus.cancelled,
    ).count()
    if day_count >= schedule.max_patients:
        return False, "Maximum patients for this day has been reached."

    return True, ""


def get_or_create_patient(
    doctor_id: int, name: str, phone: str, db: Session
) -> Patient:
    """Look up patient by phone for this doctor, or create a new record."""
    patient = db.query(Patient).filter(
        Patient.doctor_id == doctor_id,
        Patient.phone == phone,
    ).first()
    if not patient:
        patient = Patient(doctor_id=doctor_id, name=name, phone=phone)
        db.add(patient)
        db.flush()  # populate patient.id without full commit
    return patient
