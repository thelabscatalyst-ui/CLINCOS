from datetime import date, time, timedelta
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import (
    Doctor, Appointment, AppointmentStatus, AppointmentType, BookedBy,
)
from services.auth_service import get_current_doctor
from services.appointment_service import (
    get_available_slots, is_slot_available, get_or_create_patient,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])
templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------------ #
#  List                                                                #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def appointments_list(
    request: Request,
    filter_date: str = Query(default=""),
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    today = date.today()
    try:
        view_date = date.fromisoformat(filter_date) if filter_date else today
    except ValueError:
        view_date = today

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == view_date,
        )
        .order_by(Appointment.appointment_time)
        .all()
    )
    for a in appointments:
        a.patient  # lazy-load patient

    return templates.TemplateResponse(request, "appointments.html", {
        "doctor": doctor,
        "appointments": appointments,
        "view_date": view_date,
        "today": today,
        "prev_date": (view_date - timedelta(days=1)).isoformat(),
        "next_date": (view_date + timedelta(days=1)).isoformat(),
        "active": "appointments",
    })


# ------------------------------------------------------------------ #
#  Available Slots — JSON (for AJAX on new-appointment form)           #
# ------------------------------------------------------------------ #

@router.get("/slots")
def available_slots(
    date_str: str = Query(..., alias="date"),
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    try:
        appt_date = date.fromisoformat(date_str)
    except ValueError:
        return JSONResponse({"slots": [], "error": "Invalid date"})
    slots = get_available_slots(doctor.id, appt_date, db)
    return JSONResponse({"slots": slots})


# ------------------------------------------------------------------ #
#  New Appointment — GET                                               #
# ------------------------------------------------------------------ #

@router.get("/new", response_class=HTMLResponse)
def new_appointment_page(
    request: Request,
    prefill_date: str = Query(default=""),
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    today = date.today()
    try:
        initial_date = date.fromisoformat(prefill_date) if prefill_date else today
    except ValueError:
        initial_date = today

    slots = get_available_slots(doctor.id, initial_date, db)

    return templates.TemplateResponse(request, "appointment_new.html", {
        "doctor": doctor,
        "today": today.isoformat(),
        "initial_date": initial_date.isoformat(),
        "slots": slots,
        "appointment_types": [e.value for e in AppointmentType],
        "active": "appointments",
        "error": None,
        "form_data": {},
    })


# ------------------------------------------------------------------ #
#  Create Appointment — POST                                           #
# ------------------------------------------------------------------ #

@router.post("", response_class=HTMLResponse)
async def create_appointment(
    request: Request,
    patient_name: str = Form(...),
    patient_phone: str = Form(...),
    appt_date: str = Form(...),
    appt_time: str = Form(...),
    appointment_type: str = Form("follow_up"),
    duration: int = Form(15),
    patient_notes: str = Form(""),
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    today = date.today()
    form_data = {
        "patient_name": patient_name,
        "patient_phone": patient_phone,
        "appt_date": appt_date,
        "appt_time": appt_time,
        "appointment_type": appointment_type,
        "duration": duration,
        "patient_notes": patient_notes,
    }

    def render_error(msg: str):
        try:
            d = date.fromisoformat(appt_date)
        except (ValueError, TypeError):
            d = today
        slots = get_available_slots(doctor.id, d, db)
        return templates.TemplateResponse(request, "appointment_new.html", {
            "doctor": doctor,
            "today": today.isoformat(),
            "initial_date": appt_date,
            "slots": slots,
            "appointment_types": [e.value for e in AppointmentType],
            "active": "appointments",
            "error": msg,
            "form_data": form_data,
        })

    # Parse date / time
    try:
        appt_date_obj = date.fromisoformat(appt_date)
        appt_time_obj = time.fromisoformat(appt_time)
    except ValueError:
        return render_error("Invalid date or time. Please pick a valid slot.")

    # Validate patient fields
    name = patient_name.strip()
    phone = patient_phone.strip()
    if not name:
        return render_error("Patient name is required.")
    if not phone or len(phone) < 10:
        return render_error("A valid phone number is required (at least 10 digits).")

    # Slot availability check
    ok, reason = is_slot_available(doctor.id, appt_date_obj, appt_time_obj, db)
    if not ok:
        return render_error(reason)

    # Get or create patient
    patient = get_or_create_patient(doctor.id, name, phone, db)

    # Parse appointment type
    try:
        appt_type = AppointmentType(appointment_type)
    except ValueError:
        appt_type = AppointmentType.follow_up

    # Create the appointment
    appt = Appointment(
        doctor_id=doctor.id,
        patient_id=patient.id,
        appointment_date=appt_date_obj,
        appointment_time=appt_time_obj,
        duration_mins=duration,
        appointment_type=appt_type,
        patient_notes=patient_notes.strip() or None,
        booked_by=BookedBy.doctor,
        status=AppointmentStatus.scheduled,
    )
    db.add(appt)

    # Update patient visit stats
    if patient.first_visit is None:
        patient.first_visit = appt_date_obj
    patient.last_visit = appt_date_obj
    patient.visit_count = (patient.visit_count or 0) + 1

    db.commit()
    db.refresh(appt)

    return RedirectResponse(url=f"/appointments/{appt.id}", status_code=303)


# ------------------------------------------------------------------ #
#  Detail — GET                                                        #
# ------------------------------------------------------------------ #

@router.get("/{appt_id}", response_class=HTMLResponse)
def appointment_detail(
    appt_id: int,
    request: Request,
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    appt = db.query(Appointment).filter(
        Appointment.id == appt_id,
        Appointment.doctor_id == doctor.id,
    ).first()
    if not appt:
        return RedirectResponse(url="/appointments", status_code=303)

    appt.patient  # lazy-load

    return templates.TemplateResponse(request, "appointment_detail.html", {
        "doctor": doctor,
        "appt": appt,
        "active": "appointments",
        "AppointmentStatus": AppointmentStatus,
    })


# ------------------------------------------------------------------ #
#  Update Status — POST                                                #
# ------------------------------------------------------------------ #

@router.post("/{appt_id}/status", response_class=HTMLResponse)
def update_status(
    appt_id: int,
    status: str = Form(...),
    doctor_notes: str = Form(""),
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    appt = db.query(Appointment).filter(
        Appointment.id == appt_id,
        Appointment.doctor_id == doctor.id,
    ).first()
    if not appt:
        return RedirectResponse(url="/appointments", status_code=303)

    try:
        appt.status = AppointmentStatus(status)
    except ValueError:
        pass

    if doctor_notes.strip():
        appt.doctor_notes = doctor_notes.strip()

    db.commit()
    return RedirectResponse(url=f"/appointments/{appt_id}", status_code=303)
