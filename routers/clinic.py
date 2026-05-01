"""
routers/clinic.py — Tier 2 Clinic routes.

  /clinic/reception         — receptionist workspace
  /clinic/admin             — clinic-owner dashboard
  /clinic/admin/staff       — manage staff
  /clinic/admin/staff/invite — send invite
  /clinic/invite/{token}    — accept invite (public)
"""
import secrets
from datetime import date, time, datetime, timedelta

from fastapi import APIRouter, Request, Depends, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.connection import get_db
from database.models import (
    Clinic, ClinicDoctor, Staff, StaffInvite, ClinicDoctorInvite,
    Doctor, Appointment, AppointmentStatus, AppointmentType, BookedBy, Patient,
)
from services.auth_service import (
    get_current_staff, get_clinic_owner, hash_password, get_current_doctor,
)
from services.appointment_service import (
    get_available_slots, is_slot_available, get_or_create_patient,
    has_open_appointment_on_date,
)
from services.notification_service import notify_appointment_confirmed

router = APIRouter(prefix="/clinic", tags=["clinic"])
templates = Jinja2Templates(directory="templates")


# ─────────────────────────────────────────────────────────────────────────── #
#  Helpers                                                                     #
# ─────────────────────────────────────────────────────────────────────────── #

def _get_clinic_doctors(clinic_id: int, db: Session) -> list[Doctor]:
    """Return active doctor objects for a clinic, ordered by name."""
    memberships = (
        db.query(ClinicDoctor)
        .filter(ClinicDoctor.clinic_id == clinic_id, ClinicDoctor.is_active == True)
        .all()
    )
    ids = [m.doctor_id for m in memberships]
    if not ids:
        return []
    return db.query(Doctor).filter(Doctor.id.in_(ids)).order_by(Doctor.name).all()


def _staff_allowed_doctors(staff: Staff, db: Session) -> list[Doctor]:
    """Return the subset of clinic doctors the staff member can manage."""
    all_docs = _get_clinic_doctors(staff.clinic_id, db)
    allowed = staff.allowed_doctor_ids or []
    if not allowed:
        return all_docs  # [] = all
    return [d for d in all_docs if d.id in allowed]


def _get_owner_clinic(doctor_id: int, db: Session) -> Clinic | None:
    membership = (
        db.query(ClinicDoctor)
        .filter(ClinicDoctor.doctor_id == doctor_id, ClinicDoctor.role == "owner")
        .first()
    )
    if not membership:
        return None
    return db.query(Clinic).filter(Clinic.id == membership.clinic_id).first()


# ─────────────────────────────────────────────────────────────────────────── #
#  Reception Dashboard                                                         #
# ─────────────────────────────────────────────────────────────────────────── #

@router.get("/reception/dashboard", response_class=HTMLResponse)
def reception_dashboard(
    request: Request,
    staff: Staff = Depends(get_current_staff),
    db: Session = Depends(get_db),
):
    from database.models import Patient, BookedBy
    today = date.today()
    now   = datetime.now()

    # Time-aware greeting
    hour = now.hour
    if hour < 12:
        greeting = "Good Morning"
    elif hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    doctors = _staff_allowed_doctors(staff, db)

    # Gather today's appointments for all allowed doctors
    all_appts = []
    for doc in doctors:
        appts = (
            db.query(Appointment)
            .filter(
                Appointment.doctor_id == doc.id,
                Appointment.appointment_date == today,
                Appointment.status != AppointmentStatus.cancelled,
            )
            .order_by(Appointment.appointment_time)
            .all()
        )
        for a in appts:
            _ = a.patient   # lazy-load
            a._doctor_name = doc.name   # attach for template use
        all_appts.extend(appts)

    # Sort unified list by time
    all_appts.sort(key=lambda a: a.appointment_time)

    # Stats
    total_today     = len(all_appts)
    pending_today   = sum(1 for a in all_appts if a.status == AppointmentStatus.scheduled)
    completed_today = sum(1 for a in all_appts if a.status == AppointmentStatus.completed)
    walkin_today    = sum(1 for a in all_appts if a.booked_by == BookedBy.walk_in and not a.is_emergency)
    emergency_today = sum(1 for a in all_appts if a.is_emergency)

    # Total patients across all allowed doctors (deduplicated by patient id)
    doctor_ids = [d.id for d in doctors]
    total_patients = (
        db.query(func.count(Patient.id.distinct()))
        .filter(Patient.doctor_id.in_(doctor_ids))
        .scalar()
    ) if doctor_ids else 0

    # Next scheduled appointment across all doctors
    next_appt = next(
        (a for a in all_appts if a.status == AppointmentStatus.scheduled),
        None,
    )

    return templates.TemplateResponse(request, "clinic/reception_dashboard.html", {
        "staff":            staff,
        "doctors":          doctors,
        "today":            today,
        "greeting":         greeting,
        "all_appts":        all_appts,
        "total_today":      total_today,
        "pending_today":    pending_today,
        "completed_today":  completed_today,
        "walkin_today":     walkin_today,
        "emergency_today":  emergency_today,
        "total_patients":   total_patients,
        "next_appt":        next_appt,
        "active":           "dashboard",
        "AppointmentStatus": AppointmentStatus,
    })


# ─────────────────────────────────────────────────────────────────────────── #
#  Reception — Step 3                                                          #
# ─────────────────────────────────────────────────────────────────────────── #

@router.get("/reception", response_class=HTMLResponse)
def reception(
    request: Request,
    doctor_id: int = Query(default=0),
    filter_date: str = Query(default=""),
    staff: Staff = Depends(get_current_staff),
    db: Session = Depends(get_db),
):
    today = date.today()
    try:
        view_date = date.fromisoformat(filter_date) if filter_date else today
    except ValueError:
        view_date = today

    doctors = _staff_allowed_doctors(staff, db)
    if not doctors:
        return templates.TemplateResponse(request, "clinic/reception.html", {
            "staff": staff,
            "doctors": [],
            "selected_doctor": None,
            "appointments": [],
            "view_date": view_date,
            "today": today,
            "prev_date": (view_date - timedelta(days=1)).isoformat(),
            "next_date": (view_date + timedelta(days=1)).isoformat(),
            "active": "reception",
        })

    # Default to first allowed doctor if not specified
    selected = next((d for d in doctors if d.id == doctor_id), doctors[0])

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == selected.id,
            Appointment.appointment_date == view_date,
        )
        .order_by(Appointment.appointment_time)
        .all()
    )
    for a in appointments:
        _ = a.patient  # lazy-load

    return templates.TemplateResponse(request, "clinic/reception.html", {
        "staff": staff,
        "doctors": doctors,
        "selected_doctor": selected,
        "appointments": appointments,
        "view_date": view_date,
        "today": today,
        "prev_date": (view_date - timedelta(days=1)).isoformat(),
        "next_date": (view_date + timedelta(days=1)).isoformat(),
        "active": "reception",
    })


@router.get("/reception/appointments/new", response_class=HTMLResponse)
def reception_new_appointment_page(
    request: Request,
    doctor_id: int = Query(default=0),
    staff: Staff = Depends(get_current_staff),
    db: Session = Depends(get_db),
):
    doctors = _staff_allowed_doctors(staff, db)
    selected = next((d for d in doctors if d.id == doctor_id), doctors[0] if doctors else None)
    return templates.TemplateResponse(request, "clinic/reception_appt_new.html", {
        "staff": staff,
        "doctors": doctors,
        "selected_doctor": selected,
        "today": date.today().isoformat(),
        "error": None,
        "active": "reception",
    })


@router.post("/reception/appointments", response_class=HTMLResponse)
def reception_create_appointment(
    request: Request,
    doctor_id: int = Form(...),
    patient_name: str = Form(...),
    patient_phone: str = Form(...),
    appt_date: str = Form(...),
    appt_time: str = Form(...),
    appointment_type: str = Form("follow_up"),
    patient_notes: str = Form(""),
    staff: Staff = Depends(get_current_staff),
    db: Session = Depends(get_db),
):
    doctors = _staff_allowed_doctors(staff, db)
    selected = next((d for d in doctors if d.id == doctor_id), None)

    def _error(msg):
        return templates.TemplateResponse(request, "clinic/reception_appt_new.html", {
            "staff": staff, "doctors": doctors, "selected_doctor": selected,
            "today": date.today().isoformat(), "error": msg, "active": "reception",
        }, status_code=400)

    if not selected:
        return _error("Invalid doctor selection.")

    try:
        a_date = date.fromisoformat(appt_date)
        a_time = time.fromisoformat(appt_time)
    except ValueError:
        return _error("Invalid date or time.")

    phone = patient_phone.strip()
    if not phone or not phone.isdigit() or len(phone) != 10:
        return _error("Phone number must be exactly 10 digits.")
    if has_open_appointment_on_date(selected.id, phone, a_date, db):
        return _error(
            "This patient already has a scheduled appointment on this day. "
            "Mark it as completed, no-show, or cancelled before booking again."
        )

    ok, reason = is_slot_available(selected.id, a_date, a_time, db)
    if not ok:
        return _error(reason)

    # Defensive enum parse — match the pattern used by /appointments and /book/{slug}
    try:
        appt_type = AppointmentType(appointment_type)
    except ValueError:
        appt_type = AppointmentType.follow_up

    patient = get_or_create_patient(selected.id, patient_name.strip(), phone, db)

    appt = Appointment(
        doctor_id        = selected.id,
        patient_id       = patient.id,
        clinic_id        = staff.clinic_id,
        staff_id         = staff.id,
        appointment_date = a_date,
        appointment_time = a_time,
        appointment_type = appt_type,
        patient_notes    = patient_notes.strip() or None,
        booked_by        = BookedBy.staff,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    try:
        notify_appointment_confirmed(appt, selected, db)
    except Exception:
        pass

    return RedirectResponse(
        url=f"/clinic/reception?doctor_id={selected.id}&filter_date={a_date.isoformat()}",
        status_code=303,
    )


@router.post("/reception/walkin", response_class=HTMLResponse)
def reception_walkin(
    request: Request,
    doctor_id: int = Form(...),
    patient_name: str = Form(...),
    patient_phone: str = Form(...),
    staff: Staff = Depends(get_current_staff),
    db: Session = Depends(get_db),
):
    doctors = _staff_allowed_doctors(staff, db)
    selected = next((d for d in doctors if d.id == doctor_id), None)
    if not selected:
        return RedirectResponse(url="/clinic/reception", status_code=303)

    phone_walkin = patient_phone.strip()
    if not phone_walkin or not phone_walkin.isdigit() or len(phone_walkin) != 10:
        return RedirectResponse(url="/clinic/reception?walkin_error=1", status_code=303)

    now = datetime.now()
    patient = get_or_create_patient(selected.id, patient_name.strip(), phone_walkin, db)

    appt = Appointment(
        doctor_id        = selected.id,
        patient_id       = patient.id,
        clinic_id        = staff.clinic_id,
        staff_id         = staff.id,
        appointment_date = now.date(),
        appointment_time = now.time().replace(second=0, microsecond=0),
        appointment_type = AppointmentType.follow_up,
        booked_by        = BookedBy.walk_in,
    )
    db.add(appt)
    db.commit()

    return RedirectResponse(
        url=f"/clinic/reception?doctor_id={selected.id}",
        status_code=303,
    )


# ─────────────────────────────────────────────────────────────────────────── #
#  Clinic Admin Dashboard — Step 4                                             #
# ─────────────────────────────────────────────────────────────────────────── #

@router.get("/admin", response_class=HTMLResponse)
def clinic_admin_dashboard(
    request: Request,
    doctor: Doctor = Depends(get_clinic_owner),
    db: Session = Depends(get_db),
):
    clinic = _get_owner_clinic(doctor.id, db)
    if not clinic:
        return RedirectResponse(url="/dashboard", status_code=303)

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    doctors = _get_clinic_doctors(clinic.id, db)
    staff_list = db.query(Staff).filter(Staff.clinic_id == clinic.id).all()

    doctor_stats = []
    for d in doctors:
        today_count = db.query(Appointment).filter(
            Appointment.doctor_id == d.id,
            Appointment.appointment_date == today,
            Appointment.status != AppointmentStatus.cancelled,
        ).count()
        week_count = db.query(Appointment).filter(
            Appointment.doctor_id == d.id,
            Appointment.appointment_date >= week_start,
            Appointment.appointment_date <= today,
            Appointment.status != AppointmentStatus.cancelled,
        ).count()
        membership = db.query(ClinicDoctor).filter(
            ClinicDoctor.doctor_id == d.id,
            ClinicDoctor.clinic_id == clinic.id,
        ).first()
        doctor_stats.append({
            "doctor": d,
            "today": today_count,
            "week": week_count,
            "role": membership.role if membership else "associate",
        })

    total_today = sum(s["today"] for s in doctor_stats)

    return templates.TemplateResponse(request, "clinic/admin_dashboard.html", {
        "doctor": doctor,
        "clinic": clinic,
        "doctor_stats": doctor_stats,
        "staff_list": staff_list,
        "total_today": total_today,
        "active": "clinic_admin",
    })


# ─────────────────────────────────────────────────────────────────────────── #
#  Staff Management — Step 2                                                   #
# ─────────────────────────────────────────────────────────────────────────── #

@router.get("/admin/staff", response_class=HTMLResponse)
def staff_list_page(
    request: Request,
    doctor: Doctor = Depends(get_clinic_owner),
    db: Session = Depends(get_db),
):
    clinic = _get_owner_clinic(doctor.id, db)
    if not clinic:
        return RedirectResponse(url="/dashboard", status_code=303)
    staff_members = db.query(Staff).filter(Staff.clinic_id == clinic.id).all()
    pending_invites = (
        db.query(StaffInvite)
        .filter(
            StaffInvite.clinic_id == clinic.id,
            StaffInvite.used_at == None,
            StaffInvite.expires_at > datetime.utcnow(),
        )
        .all()
    )
    doctors = _get_clinic_doctors(clinic.id, db)
    return templates.TemplateResponse(request, "clinic/staff_list.html", {
        "doctor": doctor,
        "clinic": clinic,
        "staff_members": staff_members,
        "pending_invites": pending_invites,
        "doctors": doctors,
        "active": "clinic_admin",
        "success": None,
        "error": None,
    })


@router.post("/admin/staff/invite", response_class=HTMLResponse)
def send_staff_invite(
    request: Request,
    invite_email: str = Form(...),
    invite_role: str = Form("receptionist"),
    doctor: Doctor = Depends(get_clinic_owner),
    db: Session = Depends(get_db),
):
    clinic = _get_owner_clinic(doctor.id, db)
    if not clinic:
        return RedirectResponse(url="/dashboard", status_code=303)

    email = invite_email.lower().strip()

    # Check if email already has a staff account in this clinic
    existing = db.query(Staff).filter(Staff.email == email, Staff.clinic_id == clinic.id).first()
    if existing:
        staff_members = db.query(Staff).filter(Staff.clinic_id == clinic.id).all()
        pending_invites = db.query(StaffInvite).filter(
            StaffInvite.clinic_id == clinic.id, StaffInvite.used_at == None,
            StaffInvite.expires_at > datetime.utcnow(),
        ).all()
        doctors = _get_clinic_doctors(clinic.id, db)
        return templates.TemplateResponse(request, "clinic/staff_list.html", {
            "doctor": doctor, "clinic": clinic, "staff_members": staff_members,
            "pending_invites": pending_invites, "doctors": doctors,
            "active": "clinic_admin", "success": None,
            "error": f"{email} already has a staff account at this clinic.",
        }, status_code=400)

    # Revoke any existing unused invite for this email+clinic
    db.query(StaffInvite).filter(
        StaffInvite.clinic_id == clinic.id,
        StaffInvite.email == email,
        StaffInvite.used_at == None,
    ).delete()
    db.commit()

    token = secrets.token_urlsafe(32)
    invite = StaffInvite(
        clinic_id  = clinic.id,
        email      = email,
        token      = token,
        role       = invite_role,
        expires_at = datetime.utcnow() + timedelta(days=7),
    )
    db.add(invite)
    db.commit()

    # Send invite email (best-effort — failure doesn't block the invite creation)
    try:
        from services.invite_service import send_invite_email
        send_invite_email(email, token, clinic.name, doctor.name)
    except Exception:
        pass

    staff_members = db.query(Staff).filter(Staff.clinic_id == clinic.id).all()
    pending_invites = db.query(StaffInvite).filter(
        StaffInvite.clinic_id == clinic.id, StaffInvite.used_at == None,
        StaffInvite.expires_at > datetime.utcnow(),
    ).all()
    doctors_list = _get_clinic_doctors(clinic.id, db)
    return templates.TemplateResponse(request, "clinic/staff_list.html", {
        "doctor": doctor, "clinic": clinic, "staff_members": staff_members,
        "pending_invites": pending_invites, "doctors": doctors_list,
        "active": "clinic_admin", "error": None,
        "success": f"Invite sent to {email}. They have 7 days to accept.",
    })


@router.post("/admin/staff/{staff_id}/deactivate")
def deactivate_staff(
    staff_id: int,
    doctor: Doctor = Depends(get_clinic_owner),
    db: Session = Depends(get_db),
):
    clinic = _get_owner_clinic(doctor.id, db)
    if not clinic:
        raise HTTPException(status_code=403)
    staff = db.query(Staff).filter(Staff.id == staff_id, Staff.clinic_id == clinic.id).first()
    if staff:
        staff.is_active = False
        db.commit()
    return RedirectResponse(url="/clinic/admin/staff", status_code=303)


@router.post("/admin/staff/{staff_id}/reactivate")
def reactivate_staff(
    staff_id: int,
    doctor: Doctor = Depends(get_clinic_owner),
    db: Session = Depends(get_db),
):
    clinic = _get_owner_clinic(doctor.id, db)
    if not clinic:
        raise HTTPException(status_code=403)
    staff = db.query(Staff).filter(Staff.id == staff_id, Staff.clinic_id == clinic.id).first()
    if staff:
        staff.is_active = True
        db.commit()
    return RedirectResponse(url="/clinic/admin/staff", status_code=303)


# ─────────────────────────────────────────────────────────────────────────── #
#  Invite Accept — public (no auth)                                            #
# ─────────────────────────────────────────────────────────────────────────── #

@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_accept_page(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    invite = db.query(StaffInvite).filter(StaffInvite.token == token).first()
    if not invite or invite.used_at or invite.expires_at < datetime.utcnow():
        return templates.TemplateResponse(request, "clinic/invite_invalid.html", {
            "reason": "This invite link is invalid or has expired."
        }, status_code=410)
    clinic = db.query(Clinic).filter(Clinic.id == invite.clinic_id).first()
    return templates.TemplateResponse(request, "clinic/invite_accept.html", {
        "invite": invite, "clinic": clinic, "error": None,
    })


@router.post("/invite/{token}", response_class=HTMLResponse)
def invite_accept_submit(
    token: str,
    request: Request,
    staff_name: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    invite = db.query(StaffInvite).filter(StaffInvite.token == token).first()
    clinic = db.query(Clinic).filter(Clinic.id == invite.clinic_id).first() if invite else None

    def _invalid(reason="This invite link is invalid or has expired."):
        return templates.TemplateResponse(
            request, "clinic/invite_invalid.html", {"reason": reason}, status_code=410
        )

    def _error(msg):
        return templates.TemplateResponse(
            request, "clinic/invite_accept.html",
            {"invite": invite, "clinic": clinic, "error": msg}, status_code=400
        )

    if not invite or invite.used_at or invite.expires_at < datetime.utcnow():
        return _invalid()

    if password != confirm_password:
        return _error("Passwords do not match.")
    if len(password) < 6:
        return _error("Password must be at least 6 characters.")

    # Check if email already has an account
    existing = db.query(Staff).filter(Staff.email == invite.email).first()
    if existing:
        return _error("This email already has a staff account. Please log in.")

    staff = Staff(
        clinic_id     = invite.clinic_id,
        name          = staff_name.strip(),
        email         = invite.email,
        password_hash = hash_password(password),
        role          = invite.role,
    )
    db.add(staff)
    invite.used_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url="/login?registered=1", status_code=303)


# ─────────────────────────────────────────────────────────────────────────── #
#  Slots JSON for reception (AJAX)                                             #
# ─────────────────────────────────────────────────────────────────────────── #

@router.get("/reception/slots")
def reception_slots(
    date_str: str = Query(..., alias="date"),
    doctor_id: int = Query(...),
    staff: Staff = Depends(get_current_staff),
    db: Session = Depends(get_db),
):
    allowed = _staff_allowed_doctors(staff, db)
    if not any(d.id == doctor_id for d in allowed):
        return JSONResponse({"slots": [], "error": "Not allowed"})
    try:
        appt_date = date.fromisoformat(date_str)
    except ValueError:
        return JSONResponse({"slots": [], "error": "Invalid date"})
    slots = get_available_slots(doctor_id, appt_date, db, filter_past=False)
    return JSONResponse({"slots": slots})


# ─────────────────────────────────────────────────────────────────────────── #
#  Doctor Management — invite doctors to join clinic                           #
# ─────────────────────────────────────────────────────────────────────────── #

@router.get("/admin/doctors", response_class=HTMLResponse)
def doctors_list_page(
    request: Request,
    doctor: Doctor = Depends(get_clinic_owner),
    db: Session = Depends(get_db),
):
    clinic = _get_owner_clinic(doctor.id, db)
    if not clinic:
        return RedirectResponse(url="/dashboard", status_code=303)

    # All doctors in this clinic with their roles
    memberships = (
        db.query(ClinicDoctor)
        .filter(ClinicDoctor.clinic_id == clinic.id)
        .all()
    )
    clinic_doctors = []
    for m in memberships:
        d = db.query(Doctor).filter(Doctor.id == m.doctor_id).first()
        if d:
            clinic_doctors.append({"doctor": d, "role": m.role, "is_active": m.is_active, "membership_id": m.id})

    # Pending doctor invites
    pending_invites = (
        db.query(ClinicDoctorInvite)
        .filter(
            ClinicDoctorInvite.clinic_id == clinic.id,
            ClinicDoctorInvite.used_at == None,
            ClinicDoctorInvite.expires_at > datetime.utcnow(),
        )
        .all()
    )

    return templates.TemplateResponse(request, "clinic/admin_doctors.html", {
        "doctor": doctor,
        "clinic": clinic,
        "clinic_doctors": clinic_doctors,
        "pending_invites": pending_invites,
        "active": "clinic_admin",
        "success": None,
        "error": None,
    })


@router.post("/admin/doctors/invite", response_class=HTMLResponse)
def send_doctor_invite(
    request: Request,
    invite_email: str = Form(...),
    doctor: Doctor = Depends(get_clinic_owner),
    db: Session = Depends(get_db),
):
    clinic = _get_owner_clinic(doctor.id, db)
    if not clinic:
        return RedirectResponse(url="/dashboard", status_code=303)

    email = invite_email.lower().strip()

    def _render(success=None, error=None):
        memberships = db.query(ClinicDoctor).filter(ClinicDoctor.clinic_id == clinic.id).all()
        clinic_doctors = []
        for m in memberships:
            d = db.query(Doctor).filter(Doctor.id == m.doctor_id).first()
            if d:
                clinic_doctors.append({"doctor": d, "role": m.role, "is_active": m.is_active, "membership_id": m.id})
        pending_invites = db.query(ClinicDoctorInvite).filter(
            ClinicDoctorInvite.clinic_id == clinic.id,
            ClinicDoctorInvite.used_at == None,
            ClinicDoctorInvite.expires_at > datetime.utcnow(),
        ).all()
        return templates.TemplateResponse(request, "clinic/admin_doctors.html", {
            "doctor": doctor, "clinic": clinic,
            "clinic_doctors": clinic_doctors, "pending_invites": pending_invites,
            "active": "clinic_admin", "success": success, "error": error,
        }, status_code=400 if error else 200)

    # Check if this doctor is already in the clinic
    existing_doctor = db.query(Doctor).filter(Doctor.email == email).first()
    if existing_doctor:
        already = db.query(ClinicDoctor).filter(
            ClinicDoctor.clinic_id == clinic.id,
            ClinicDoctor.doctor_id == existing_doctor.id,
        ).first()
        if already:
            return _render(error=f"{email} is already a doctor in this clinic.")

    # Revoke any existing unused invite for this email+clinic
    db.query(ClinicDoctorInvite).filter(
        ClinicDoctorInvite.clinic_id == clinic.id,
        ClinicDoctorInvite.email == email,
        ClinicDoctorInvite.used_at == None,
    ).delete()
    db.commit()

    token = secrets.token_urlsafe(32)
    invite = ClinicDoctorInvite(
        clinic_id  = clinic.id,
        email      = email,
        token      = token,
        expires_at = datetime.utcnow() + timedelta(days=7),
    )
    db.add(invite)
    db.commit()

    # Send invite email (best-effort)
    try:
        from services.invite_service import send_invite_email
        send_invite_email(email, token, clinic.name, doctor.name)
    except Exception:
        pass

    return _render(success=f"Invite sent to {email}. They have 7 days to accept.")


# ─────────────────────────────────────────────────────────────────────────── #
#  Doctor Invite Accept — public                                               #
# ─────────────────────────────────────────────────────────────────────────── #

@router.get("/doctor-invite/{token}", response_class=HTMLResponse)
def doctor_invite_page(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    invite = db.query(ClinicDoctorInvite).filter(ClinicDoctorInvite.token == token).first()
    if not invite or invite.used_at or invite.expires_at < datetime.utcnow():
        return templates.TemplateResponse(request, "clinic/invite_invalid.html", {
            "reason": "This invite link is invalid or has expired."
        }, status_code=410)

    clinic = db.query(Clinic).filter(Clinic.id == invite.clinic_id).first()

    # Try to detect if a doctor is already logged in (soft check)
    logged_in_doctor = None
    token_cookie = request.cookies.get("access_token")
    if token_cookie:
        try:
            from jose import jwt
            from config import settings
            payload = jwt.decode(token_cookie, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            doctor_id = payload.get("doctor_id")
            if doctor_id:
                logged_in_doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        except Exception:
            pass

    # Check if logged-in doctor is already in this clinic
    already_member = False
    if logged_in_doctor:
        already_member = db.query(ClinicDoctor).filter(
            ClinicDoctor.clinic_id == invite.clinic_id,
            ClinicDoctor.doctor_id == logged_in_doctor.id,
        ).first() is not None

    return templates.TemplateResponse(request, "clinic/doctor_invite.html", {
        "invite": invite,
        "clinic": clinic,
        "logged_in_doctor": logged_in_doctor,
        "already_member": already_member,
        "error": None,
    })


@router.post("/doctor-invite/{token}", response_class=HTMLResponse)
def doctor_invite_accept(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    invite = db.query(ClinicDoctorInvite).filter(ClinicDoctorInvite.token == token).first()
    if not invite or invite.used_at or invite.expires_at < datetime.utcnow():
        return templates.TemplateResponse(request, "clinic/invite_invalid.html", {
            "reason": "This invite link is invalid or has expired."
        }, status_code=410)

    clinic = db.query(Clinic).filter(Clinic.id == invite.clinic_id).first()

    # Must be logged in as a doctor
    logged_in_doctor = None
    token_cookie = request.cookies.get("access_token")
    if token_cookie:
        try:
            from jose import jwt
            from config import settings
            payload = jwt.decode(token_cookie, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            doctor_id = payload.get("doctor_id")
            if doctor_id:
                logged_in_doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        except Exception:
            pass

    if not logged_in_doctor:
        return templates.TemplateResponse(request, "clinic/doctor_invite.html", {
            "invite": invite, "clinic": clinic,
            "logged_in_doctor": None, "already_member": False,
            "error": "Please log in first, then come back to this link.",
        })

    # Check not already in this clinic
    already = db.query(ClinicDoctor).filter(
        ClinicDoctor.clinic_id == invite.clinic_id,
        ClinicDoctor.doctor_id == logged_in_doctor.id,
    ).first()
    if already:
        return templates.TemplateResponse(request, "clinic/doctor_invite.html", {
            "invite": invite, "clinic": clinic,
            "logged_in_doctor": logged_in_doctor, "already_member": True,
            "error": "You are already a member of this clinic.",
        })

    # Add doctor to clinic as associate
    db.add(ClinicDoctor(
        clinic_id=invite.clinic_id,
        doctor_id=logged_in_doctor.id,
        role="associate",
        is_active=True,
    ))
    invite.used_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url="/dashboard?joined=1", status_code=303)
