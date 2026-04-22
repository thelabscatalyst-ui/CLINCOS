from datetime import date, time, datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import (
    Doctor, Appointment, Patient, AppointmentStatus, AppointmentType, BookedBy,
)
from services.appointment_service import (
    get_available_slots, is_slot_available, get_or_create_patient,
)
from services.notification_service import notify_appointment_confirmed

router = APIRouter(prefix="/book", tags=["public"])
templates = Jinja2Templates(directory="templates")


def _rate_limit_ok(phone: str, db: Session) -> bool:
    """Allow max 5 patient-booked appointments per phone number per 24 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    count = (
        db.query(Appointment)
        .join(Patient, Appointment.patient_id == Patient.id)
        .filter(
            Patient.phone == phone,
            Appointment.booked_by == BookedBy.patient,
            Appointment.created_at >= cutoff,
        )
        .count()
    )
    return count < 5


# ------------------------------------------------------------------ #
#  Public slots — AJAX (no auth, keyed by slug)                       #
# ------------------------------------------------------------------ #

@router.get("/{slug}/slots")
def public_slots(
    slug: str,
    date_str: str = Query(..., alias="date"),
    db: Session = Depends(get_db),
):
    doctor = db.query(Doctor).filter(
        Doctor.slug == slug, Doctor.is_active == True,
    ).first()
    if not doctor:
        return JSONResponse({"slots": []})
    try:
        appt_date = date.fromisoformat(date_str)
    except ValueError:
        return JSONResponse({"slots": []})
    return JSONResponse({"slots": get_available_slots(doctor.id, appt_date, db)})


# ------------------------------------------------------------------ #
#  Booking Form — GET                                                  #
# ------------------------------------------------------------------ #

@router.get("/{slug}", response_class=HTMLResponse)
def booking_page(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    doctor = db.query(Doctor).filter(
        Doctor.slug == slug, Doctor.is_active == True,
    ).first()

    if not doctor:
        return templates.TemplateResponse(
            request, "public_booking.html",
            {"doctor": None, "not_found": True},
            status_code=404,
        )

    today = date.today()
    slots = get_available_slots(doctor.id, today, db)

    return templates.TemplateResponse(request, "public_booking.html", {
        "doctor": doctor,
        "not_found": False,
        "today": today.isoformat(),
        "initial_date": today.isoformat(),
        "slots": slots,
        "appointment_types": [e.value for e in AppointmentType],
        "error": None,
        "form_data": {},
    })


# ------------------------------------------------------------------ #
#  Booking Form — POST                                                 #
# ------------------------------------------------------------------ #

@router.post("/{slug}", response_class=HTMLResponse)
async def book_appointment(
    slug: str,
    request: Request,
    patient_name: str = Form(...),
    patient_phone: str = Form(...),
    appt_date: str = Form(...),
    appt_time: str = Form(...),
    appointment_type: str = Form("new_patient"),
    patient_notes: str = Form(""),
    db: Session = Depends(get_db),
):
    doctor = db.query(Doctor).filter(
        Doctor.slug == slug, Doctor.is_active == True,
    ).first()
    if not doctor:
        return RedirectResponse(url="/", status_code=303)

    today = date.today()
    form_data = {
        "patient_name": patient_name,
        "patient_phone": patient_phone,
        "appt_date": appt_date,
        "appt_time": appt_time,
        "appointment_type": appointment_type,
        "patient_notes": patient_notes,
    }

    def render_error(msg: str):
        try:
            d = date.fromisoformat(appt_date)
        except (ValueError, TypeError):
            d = today
        slots = get_available_slots(doctor.id, d, db)
        return templates.TemplateResponse(request, "public_booking.html", {
            "doctor": doctor,
            "not_found": False,
            "today": today.isoformat(),
            "initial_date": appt_date,
            "slots": slots,
            "appointment_types": [e.value for e in AppointmentType],
            "error": msg,
            "form_data": form_data,
        })

    # Parse date / time
    try:
        appt_date_obj = date.fromisoformat(appt_date)
        appt_time_obj = time.fromisoformat(appt_time)
    except ValueError:
        return render_error("Invalid date or time. Please select a valid slot.")

    # Validate patient fields
    name  = patient_name.strip()
    phone = patient_phone.strip()
    if not name:
        return render_error("Please enter your full name.")
    if not phone or len(phone) < 10:
        return render_error("Please enter a valid 10-digit phone number.")

    # Rate limit
    if not _rate_limit_ok(phone, db):
        return render_error(
            "Too many bookings from this number in the last 24 hours. "
            "Please call the clinic directly."
        )

    # Slot availability
    ok, reason = is_slot_available(doctor.id, appt_date_obj, appt_time_obj, db)
    if not ok:
        return render_error(reason)

    # Get or create patient
    patient = get_or_create_patient(doctor.id, name, phone, db)

    try:
        appt_type = AppointmentType(appointment_type)
    except ValueError:
        appt_type = AppointmentType.new_patient

    # Create appointment
    appt = Appointment(
        doctor_id=doctor.id,
        patient_id=patient.id,
        appointment_date=appt_date_obj,
        appointment_time=appt_time_obj,
        duration_mins=15,
        appointment_type=appt_type,
        patient_notes=patient_notes.strip() or None,
        booked_by=BookedBy.patient,
        status=AppointmentStatus.scheduled,
    )
    db.add(appt)

    if patient.first_visit is None:
        patient.first_visit = appt_date_obj
    patient.last_visit = appt_date_obj
    patient.visit_count = (patient.visit_count or 0) + 1

    db.commit()
    db.refresh(appt)

    # Send WhatsApp confirmation to patient (non-blocking)
    try:
        notify_appointment_confirmed(appt, doctor, db)
    except Exception:
        pass

    return RedirectResponse(url=f"/book/{slug}/confirm/{appt.id}", status_code=303)


# ------------------------------------------------------------------ #
#  Confirmation — GET                                                  #
# ------------------------------------------------------------------ #

@router.get("/{slug}/confirm/{appt_id}", response_class=HTMLResponse)
def booking_confirm(
    slug: str,
    appt_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    doctor = db.query(Doctor).filter(Doctor.slug == slug).first()
    if not doctor:
        return RedirectResponse(url=f"/book/{slug}", status_code=303)

    appt = db.query(Appointment).filter(
        Appointment.id == appt_id,
        Appointment.doctor_id == doctor.id,
    ).first()
    if not appt:
        return RedirectResponse(url=f"/book/{slug}", status_code=303)

    appt.patient  # lazy-load

    # Build Google Calendar add link
    dt_start = datetime.combine(appt.appointment_date, appt.appointment_time)
    dt_end   = dt_start + timedelta(minutes=appt.duration_mins)
    clinic   = (doctor.clinic_name or f"Dr. {doctor.name}").replace(" ", "+")
    gc_url = (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text=Appointment+at+{clinic}"
        f"&dates={dt_start.strftime('%Y%m%dT%H%M%S')}/{dt_end.strftime('%Y%m%dT%H%M%S')}"
        f"&details=Appointment+with+Dr.+{doctor.name.replace(' ', '+')}"
        + (f"&location={doctor.clinic_address.replace(' ', '+')}" if doctor.clinic_address else "")
    )

    return templates.TemplateResponse(request, "public_confirm.html", {
        "doctor": doctor,
        "appt":   appt,
        "gc_url": gc_url,
        "slug":   slug,
    })
