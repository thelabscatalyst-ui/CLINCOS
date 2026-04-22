from datetime import datetime, date
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.connection import get_db
from database.models import Doctor, Appointment, Patient, Subscription, AppointmentStatus
from services.auth_service import get_admin_doctor

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def admin_root():
    return RedirectResponse(url="/admin/dashboard", status_code=303)


# ------------------------------------------------------------------ #
#  Admin Dashboard                                                     #
# ------------------------------------------------------------------ #

@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    doctor: Doctor = Depends(get_admin_doctor),
    db: Session    = Depends(get_db),
):
    now   = datetime.utcnow()
    today = date.today()
    start_of_month = today.replace(day=1)

    total_doctors = db.query(func.count(Doctor.id)).scalar() or 0

    active_trials = db.query(func.count(Doctor.id)).filter(
        Doctor.trial_ends_at > now,
        Doctor.plan_expires_at == None,
    ).scalar() or 0

    active_plans = db.query(func.count(Doctor.id)).filter(
        Doctor.plan_expires_at > now,
    ).scalar() or 0

    expired = db.query(func.count(Doctor.id)).filter(
        Doctor.trial_ends_at < now,
        (Doctor.plan_expires_at == None) | (Doctor.plan_expires_at < now),
    ).scalar() or 0

    new_doctors_month = db.query(func.count(Doctor.id)).filter(
        Doctor.created_at >= start_of_month,
    ).scalar() or 0

    # Revenue this month (sum of subscriptions)
    revenue_result = db.query(func.sum(Subscription.amount)).filter(
        Subscription.start_date >= start_of_month,
        Subscription.status == "active",
    ).scalar() or 0
    revenue_inr = revenue_result // 100  # paise → rupees

    # Total appointments today (across all doctors)
    appts_today = db.query(func.count(Appointment.id)).filter(
        Appointment.appointment_date == today,
    ).scalar() or 0

    return templates.TemplateResponse(request, "admin/admin_dashboard.html", {
        "admin":              doctor,
        "total_doctors":      total_doctors,
        "active_trials":      active_trials,
        "active_plans":       active_plans,
        "expired":            expired,
        "new_doctors_month":  new_doctors_month,
        "revenue_inr":        revenue_inr,
        "appts_today":        appts_today,
        "active":             "admin_dashboard",
    })


# ------------------------------------------------------------------ #
#  Doctors List                                                        #
# ------------------------------------------------------------------ #

@router.get("/doctors", response_class=HTMLResponse)
def admin_doctors(
    request: Request,
    doctor: Doctor = Depends(get_admin_doctor),
    db: Session    = Depends(get_db),
):
    now = datetime.utcnow()
    doctors = db.query(Doctor).order_by(Doctor.created_at.desc()).all()

    rows = []
    for d in doctors:
        trial_ok = d.trial_ends_at  and d.trial_ends_at  > now
        plan_ok  = d.plan_expires_at and d.plan_expires_at > now
        if plan_ok:
            status = "active_plan"
        elif trial_ok:
            status = "trial"
        else:
            status = "expired"
        rows.append({
            "doctor": d,
            "status": status,
        })

    return templates.TemplateResponse(request, "admin/doctors_list.html", {
        "admin":   doctor,
        "rows":    rows,
        "active":  "admin_doctors",
    })
