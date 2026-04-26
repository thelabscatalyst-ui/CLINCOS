from datetime import date
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from database.connection import get_db
from database.models import Doctor, Patient, Appointment, AppointmentStatus
from services.auth_service import get_paying_doctor, require_pin

router = APIRouter(prefix="/patients", tags=["patients"])
templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------------ #
#  List                                                                #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def patients_list(
    request: Request,
    q: str = Query(default=""),
    doctor: Doctor = Depends(get_paying_doctor),
    db: Session = Depends(get_db),
):
    query = db.query(Patient).filter(Patient.doctor_id == doctor.id)

    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(Patient.name.ilike(term), Patient.phone.ilike(term))
        )

    # Patients with recent visits first; new patients (no last_visit) at end
    patients = query.order_by(
        Patient.last_visit.desc(), Patient.created_at.desc()
    ).all()

    total = db.query(func.count(Patient.id)).filter(
        Patient.doctor_id == doctor.id
    ).scalar()

    return templates.TemplateResponse(request, "patients.html", {
        "doctor":   doctor,
        "patients": patients,
        "total":    total,
        "q":        q,
        "active":   "patients",
    })


# ------------------------------------------------------------------ #
#  Detail                                                              #
# ------------------------------------------------------------------ #

@router.get("/{patient_id}", response_class=HTMLResponse)
def patient_detail(
    patient_id: int,
    request: Request,
    doctor: Doctor = Depends(require_pin),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == doctor.id,
    ).first()
    if not patient:
        return RedirectResponse(url="/patients", status_code=303)

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.patient_id == patient.id,
            Appointment.doctor_id == doctor.id,
        )
        .order_by(
            Appointment.appointment_date.desc(),
            Appointment.appointment_time.desc(),
        )
        .all()
    )

    completed = sum(1 for a in appointments if a.status == AppointmentStatus.completed)
    upcoming  = sum(1 for a in appointments if a.status == AppointmentStatus.scheduled
                    and a.appointment_date >= date.today())

    return templates.TemplateResponse(request, "patient_detail.html", {
        "doctor":       doctor,
        "patient":      patient,
        "appointments": appointments,
        "completed":    completed,
        "upcoming":     upcoming,
        "active":       "patients",
        "pin_required": getattr(request.state, "pin_required", False),
    })


# ------------------------------------------------------------------ #
#  Update Notes                                                        #
# ------------------------------------------------------------------ #

@router.post("/{patient_id}/delete")
def delete_patient(
    patient_id: int,
    request: Request,
    doctor: Doctor = Depends(require_pin),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == doctor.id,
    ).first()
    if patient:
        db.query(Appointment).filter(Appointment.patient_id == patient.id).delete()
        db.delete(patient)
        db.commit()
    return RedirectResponse(url="/patients", status_code=303)


@router.post("/{patient_id}/edit")
def edit_patient(
    patient_id: int,
    name: str = Form(...),
    phone: str = Form(...),
    doctor: Doctor = Depends(get_paying_doctor),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == doctor.id,
    ).first()
    if patient:
        patient.name = name.strip()
        patient.phone = phone.strip()
        db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}", status_code=303)


@router.post("/{patient_id}/notes", response_class=HTMLResponse)
def update_notes(
    patient_id: int,
    notes: str = Form(""),
    doctor: Doctor = Depends(get_paying_doctor),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == doctor.id,
    ).first()
    if patient:
        patient.notes = notes.strip() or None
        db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}", status_code=303)
