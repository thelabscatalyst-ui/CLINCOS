import calendar as cal_module
from datetime import date, datetime, time as dtime
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from database.connection import get_db
from database.models import (
    Doctor, Appointment, Patient, AppointmentStatus,
    DoctorSchedule, BlockedDate,
)
from services.auth_service import (
    get_current_doctor, get_paying_doctor,
    require_pin, require_pin_auth,
    create_pin_token, decode_pin_token,
    hash_password, verify_password,
)

router = APIRouter(tags=["doctors"])
templates = Jinja2Templates(directory="templates")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ------------------------------------------------------------------ #
#  Dashboard                                                           #
# ------------------------------------------------------------------ #

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    doctor: Doctor = Depends(get_paying_doctor),
    db: Session = Depends(get_db),
):
    today = date.today()

    todays_appointments = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == today,
            Appointment.status != AppointmentStatus.cancelled,
        )
        .order_by(Appointment.appointment_time)
        .all()
    )

    for appt in todays_appointments:
        appt.patient  # lazy-load

    total_patients = db.query(func.count(Patient.id)).filter(Patient.doctor_id == doctor.id).scalar()
    total_today = len(todays_appointments)
    completed_today = sum(1 for a in todays_appointments if a.status == AppointmentStatus.completed)
    pending_today = sum(1 for a in todays_appointments if a.status == AppointmentStatus.scheduled)

    now_time = datetime.now().time()
    next_appointment = next(
        (a for a in todays_appointments
         if a.status == AppointmentStatus.scheduled and a.appointment_time >= now_time),
        None,
    )

    trial_active = False
    days_left = None
    if doctor.plan_type.value == "trial" and doctor.trial_ends_at:
        delta = (doctor.trial_ends_at.date() - today).days
        trial_active = delta >= 0
        days_left = max(delta, 0)

    # Time-aware greeting — use datetime.now() not date.today() (date has no hour)
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good Morning"
    elif hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    # Clinic ownership + primary clinic for display
    from database.models import ClinicDoctor, Clinic as ClinicModel
    own_membership = db.query(ClinicDoctor).filter(
        ClinicDoctor.doctor_id == doctor.id, ClinicDoctor.role == "owner"
    ).first()
    is_clinic_owner = own_membership is not None

    primary_clinic = None
    if own_membership:
        primary_clinic = db.query(ClinicModel).filter(ClinicModel.id == own_membership.clinic_id).first()
    else:
        assoc = db.query(ClinicDoctor).filter(
            ClinicDoctor.doctor_id == doctor.id,
            ClinicDoctor.role == "associate",
            ClinicDoctor.is_active == True,
        ).first()
        if assoc:
            primary_clinic = db.query(ClinicModel).filter(ClinicModel.id == assoc.clinic_id).first()

    return templates.TemplateResponse(request, "dashboard.html", {
        "doctor": doctor,
        "today": today,
        "greeting": greeting,
        "todays_appointments": todays_appointments,
        "total_patients": total_patients,
        "total_today": total_today,
        "completed_today": completed_today,
        "pending_today": pending_today,
        "next_appointment": next_appointment,
        "trial_active": trial_active,
        "days_left": days_left,
        "active": "dashboard",
        "is_clinic_owner": is_clinic_owner,
        "primary_clinic": primary_clinic,
    })


# ------------------------------------------------------------------ #
#  Settings — GET                                                      #
# ------------------------------------------------------------------ #

@router.get("/doctors/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    doctor: Doctor = Depends(require_pin),
    db: Session = Depends(get_db),
    saved: str = "",
    pin_error: str = "",
):
    schedules_db = db.query(DoctorSchedule).filter(DoctorSchedule.doctor_id == doctor.id).all()
    schedule_map = {s.day_of_week: s for s in schedules_db}

    # Build a list of 7 day dicts for the template
    days_data = []
    for i, name in enumerate(DAYS):
        s = schedule_map.get(i)
        days_data.append({
            "index": i,
            "name": name,
            "is_active": s.is_active if s else False,
            "start_time": s.start_time.strftime("%H:%M") if s else "09:00",
            "end_time": s.end_time.strftime("%H:%M") if s else "18:00",
            "slot_duration": s.slot_duration if s else 15,
            "max_patients": s.max_patients if s else 30,
        })

    blocked = (
        db.query(BlockedDate)
        .filter(BlockedDate.doctor_id == doctor.id)
        .order_by(BlockedDate.blocked_date)
        .all()
    )

    from datetime import datetime as dt
    from config import settings as cfg
    now       = dt.utcnow()
    trial_ok  = doctor.trial_ends_at  and doctor.trial_ends_at  > now
    plan_ok   = doctor.plan_expires_at and doctor.plan_expires_at > now

    def days_left(d):
        if not d: return 0
        return max(0, (d - now).days)

    if plan_ok:
        plan_status = doctor.plan_type.value   # "solo", "basic", or "pro"
        plan_days   = days_left(doctor.plan_expires_at)
    elif trial_ok:
        plan_status = "trial"
        plan_days   = days_left(doctor.trial_ends_at)
    else:
        plan_status = "expired"
        plan_days   = 0

    pin_error_msg = {
        "wrong":    "Incorrect current PIN.",
        "mismatch": "PINs do not match.",
        "invalid":  "PIN must be 4–6 digits.",
    }.get(pin_error, "")

    return templates.TemplateResponse(request, "settings.html", {
        "doctor":               doctor,
        "days_data":            days_data,
        "blocked_dates":        blocked,
        "saved":                saved == "1",
        "active":               "settings",
        "plan_status":          plan_status,
        "plan_days":            plan_days,
        "razorpay_configured":  bool(cfg.RAZORPAY_KEY_ID),
        "pin_error":            pin_error_msg,
        "pin_required":         getattr(request.state, "pin_required", False),
    })


# ------------------------------------------------------------------ #
#  Settings — Save Schedule                                            #
# ------------------------------------------------------------------ #

@router.post("/doctors/settings/schedule", response_class=HTMLResponse)
async def save_schedule(
    request: Request,
    doctor: Doctor = Depends(require_pin),
    db: Session = Depends(get_db),
):
    form = await request.form()

    for i in range(7):
        is_active = form.get(f"active_{i}") == "on"
        start_str = form.get(f"start_{i}", "09:00")
        end_str = form.get(f"end_{i}", "18:00")
        slot_dur = int(form.get(f"slot_{i}", 15))
        max_pat = int(form.get(f"max_{i}", 30))

        try:
            start_t = dtime.fromisoformat(start_str)
            end_t = dtime.fromisoformat(end_str)
        except ValueError:
            continue

        existing = db.query(DoctorSchedule).filter(
            DoctorSchedule.doctor_id == doctor.id,
            DoctorSchedule.day_of_week == i,
        ).first()

        if existing:
            existing.is_active = is_active
            existing.start_time = start_t
            existing.end_time = end_t
            existing.slot_duration = slot_dur
            existing.max_patients = max_pat
        else:
            db.add(DoctorSchedule(
                doctor_id=doctor.id,
                day_of_week=i,
                start_time=start_t,
                end_time=end_t,
                slot_duration=slot_dur,
                max_patients=max_pat,
                is_active=is_active,
            ))

    db.commit()
    return RedirectResponse(url="/doctors/settings?saved=1", status_code=303)


# ------------------------------------------------------------------ #
#  Settings — Save Profile                                             #
# ------------------------------------------------------------------ #

@router.post("/doctors/settings/profile", response_class=HTMLResponse)
def save_profile(
    request: Request,
    clinic_name: str = Form(""),
    city: str = Form(""),
    specialization: str = Form(""),
    clinic_address: str = Form(""),
    languages: str = Form(""),
    doctor: Doctor = Depends(require_pin),
    db: Session = Depends(get_db),
):
    doctor.clinic_name = clinic_name.strip() or None
    doctor.city = city.strip() or None
    doctor.specialization = specialization.strip() or None
    doctor.clinic_address = clinic_address.strip() or None
    doctor.languages = languages.strip() or None
    db.commit()
    return RedirectResponse(url="/doctors/settings?saved=1", status_code=303)


# ------------------------------------------------------------------ #
#  Settings — Add Blocked Date                                         #
# ------------------------------------------------------------------ #

@router.post("/doctors/settings/block", response_class=HTMLResponse)
def add_blocked_date(
    request: Request,
    blocked_date: str = Form(...),
    reason: str = Form(""),
    doctor: Doctor = Depends(require_pin),
    db: Session = Depends(get_db),
):
    try:
        d = date.fromisoformat(blocked_date)
    except ValueError:
        return RedirectResponse(url="/doctors/settings", status_code=303)

    exists = db.query(BlockedDate).filter(
        BlockedDate.doctor_id == doctor.id,
        BlockedDate.blocked_date == d,
    ).first()

    if not exists:
        db.add(BlockedDate(doctor_id=doctor.id, blocked_date=d, reason=reason.strip() or None))
        db.commit()

    return RedirectResponse(url="/doctors/settings?saved=1", status_code=303)


# ------------------------------------------------------------------ #
#  Settings — Remove Blocked Date                                      #
# ------------------------------------------------------------------ #

@router.post("/doctors/settings/unblock/{block_id}", response_class=HTMLResponse)
def remove_blocked_date(
    block_id: int,
    doctor: Doctor = Depends(require_pin),
    db: Session = Depends(get_db),
):
    record = db.query(BlockedDate).filter(
        BlockedDate.id == block_id,
        BlockedDate.doctor_id == doctor.id,  # security: own records only
    ).first()
    if record:
        db.delete(record)
        db.commit()
    return RedirectResponse(url="/doctors/settings", status_code=303)


# ------------------------------------------------------------------ #
#  Calendar                                                            #
# ------------------------------------------------------------------ #

@router.get("/calendar", response_class=HTMLResponse)
def calendar_view(
    request: Request,
    month: str = Query(default=""),
    doctor: Doctor = Depends(get_paying_doctor),
    db: Session = Depends(get_db),
):
    today = date.today()

    # Parse ?month=YYYY-MM, fall back to current month
    try:
        year, mon = map(int, month.split("-")) if month else (today.year, today.month)
        if not (1 <= mon <= 12):
            raise ValueError
    except (ValueError, AttributeError):
        year, mon = today.year, today.month

    first_day = date(year, mon, 1)
    last_day  = date(year, mon, cal_module.monthrange(year, mon)[1])

    # Prev / next month strings
    if mon == 1:
        prev_month = f"{year - 1}-12"
    else:
        prev_month = f"{year}-{mon - 1:02d}"
    if mon == 12:
        next_month = f"{year + 1}-01"
    else:
        next_month = f"{year}-{mon + 1:02d}"

    # Appointments for this month (non-cancelled)
    month_appts = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date >= first_day,
            Appointment.appointment_date <= last_day,
            Appointment.status != AppointmentStatus.cancelled,
        )
        .all()
    )

    # Group by ISO date string
    appt_by_date: dict = {}
    for a in month_appts:
        key = a.appointment_date.isoformat()
        appt_by_date.setdefault(key, []).append(a)

    # Blocked dates for this month
    blocked = db.query(BlockedDate).filter(
        BlockedDate.doctor_id == doctor.id,
        BlockedDate.blocked_date >= first_day,
        BlockedDate.blocked_date <= last_day,
    ).all()
    blocked_set = {b.blocked_date.isoformat() for b in blocked}

    # Build cal_data: list of weeks → list of day-dicts (None = padding cell)
    cal_data = []
    for week in cal_module.monthcalendar(year, mon):
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append(None)
            else:
                d   = date(year, mon, day_num)
                key = d.isoformat()
                day_appts = appt_by_date.get(key, [])
                week_data.append({
                    "num":       day_num,
                    "date_str":  key,
                    "total":     len(day_appts),
                    "scheduled": sum(1 for a in day_appts if a.status == AppointmentStatus.scheduled),
                    "completed": sum(1 for a in day_appts if a.status == AppointmentStatus.completed),
                    "no_show":   sum(1 for a in day_appts if a.status == AppointmentStatus.no_show),
                    "is_today":  d == today,
                    "is_blocked": key in blocked_set,
                    "is_past":   d < today,
                })
        cal_data.append(week_data)

    current_month = f"{today.year}-{today.month:02d}"
    viewing_current = (year == today.year and mon == today.month)

    return templates.TemplateResponse(request, "calendar.html", {
        "doctor":          doctor,
        "today":           today,
        "year":            year,
        "mon":             mon,
        "month_name":      first_day.strftime("%B %Y"),
        "cal_data":        cal_data,
        "prev_month":      prev_month,
        "next_month":      next_month,
        "current_month":   current_month,
        "viewing_current": viewing_current,
        "active":          "calendar",
    })


# ------------------------------------------------------------------ #
#  Reports                                                             #
# ------------------------------------------------------------------ #

@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    doctor: Doctor = Depends(require_pin),
    db: Session = Depends(get_db),
):
    import json
    from datetime import timedelta
    today = date.today()

    # ---- This week vs last week ----
    start_of_week      = today - timedelta(days=today.weekday())
    start_of_last_week = start_of_week - timedelta(days=7)
    end_of_last_week   = start_of_week - timedelta(days=1)

    this_week = db.query(func.count(Appointment.id)).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.appointment_date >= start_of_week,
        Appointment.appointment_date <= today,
        Appointment.status != AppointmentStatus.cancelled,
    ).scalar() or 0

    last_week = db.query(func.count(Appointment.id)).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.appointment_date >= start_of_last_week,
        Appointment.appointment_date <= end_of_last_week,
        Appointment.status != AppointmentStatus.cancelled,
    ).scalar() or 0

    # ---- Completion & no-show rates ----
    past_total = db.query(func.count(Appointment.id)).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.status.in_([
            AppointmentStatus.completed,
            AppointmentStatus.no_show,
        ]),
    ).scalar() or 0

    completed_count = db.query(func.count(Appointment.id)).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.status == AppointmentStatus.completed,
    ).scalar() or 0

    no_show_count = db.query(func.count(Appointment.id)).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.status == AppointmentStatus.no_show,
    ).scalar() or 0

    completion_rate = round(completed_count / past_total * 100) if past_total else 0
    no_show_rate    = round(no_show_count   / past_total * 100) if past_total else 0

    # ---- Monthly trend — last 6 months ----
    monthly_labels = []
    monthly_counts = []
    for i in range(5, -1, -1):
        m = today.replace(day=1)
        for _ in range(i):
            m = (m - timedelta(days=1)).replace(day=1)
        if m.month == 12:
            next_m = m.replace(year=m.year + 1, month=1)
        else:
            next_m = m.replace(month=m.month + 1)
        cnt = db.query(func.count(Appointment.id)).filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date >= m,
            Appointment.appointment_date < next_m,
            Appointment.status != AppointmentStatus.cancelled,
        ).scalar() or 0
        monthly_labels.append(m.strftime("%b %Y"))
        monthly_counts.append(cnt)

    # ---- Top 5 patients ----
    top_patients = (
        db.query(Patient, func.count(Appointment.id).label("cnt"))
        .join(Appointment, Patient.id == Appointment.patient_id)
        .filter(
            Appointment.doctor_id == doctor.id,
            Appointment.status != AppointmentStatus.cancelled,
        )
        .group_by(Patient.id)
        .order_by(func.count(Appointment.id).desc())
        .limit(5)
        .all()
    )

    # ---- Visit type breakdown ----
    type_rows = (
        db.query(Appointment.appointment_type, func.count(Appointment.id).label("cnt"))
        .filter(
            Appointment.doctor_id == doctor.id,
            Appointment.status != AppointmentStatus.cancelled,
        )
        .group_by(Appointment.appointment_type)
        .all()
    )
    type_total = sum(r.cnt for r in type_rows) or 1
    type_breakdown = [
        {
            "label": r.appointment_type.value.replace("_", " ").title(),
            "count": r.cnt,
            "pct":   round(r.cnt / type_total * 100),
        }
        for r in type_rows
    ]

    # ---- New patients this month vs last ----
    start_this_month = today.replace(day=1)
    start_last_month = (start_this_month - timedelta(days=1)).replace(day=1)

    patients_this_month = db.query(func.count(Patient.id)).filter(
        Patient.doctor_id == doctor.id,
        Patient.created_at >= start_this_month,
    ).scalar() or 0

    patients_last_month = db.query(func.count(Patient.id)).filter(
        Patient.doctor_id == doctor.id,
        Patient.created_at >= start_last_month,
        Patient.created_at < start_this_month,
    ).scalar() or 0

    return templates.TemplateResponse(request, "reports.html", {
        "doctor":              doctor,
        "today":               today,
        "this_week":           this_week,
        "last_week":           last_week,
        "completion_rate":     completion_rate,
        "no_show_rate":        no_show_rate,
        "monthly_labels":      json.dumps(monthly_labels),
        "monthly_counts":      json.dumps(monthly_counts),
        "top_patients":        top_patients,
        "type_breakdown":      type_breakdown,
        "patients_this_month": patients_this_month,
        "patients_last_month": patients_last_month,
        "active":              "reports",
        "pin_required":        getattr(request.state, "pin_required", False),
    })


# ------------------------------------------------------------------ #
#  Billing                                                             #
# ------------------------------------------------------------------ #

@router.get("/billing", response_class=HTMLResponse)
def billing_page(
    request: Request,
    success: str = Query(default=""),
    doctor: Doctor = Depends(require_pin_auth),   # PIN-gated but not plan-gated — must stay accessible
    db: Session = Depends(get_db),
):
    from datetime import datetime as dt
    from config import settings as cfg

    now = dt.utcnow()
    trial_ok  = doctor.trial_ends_at  and doctor.trial_ends_at  > now
    plan_ok   = doctor.plan_expires_at and doctor.plan_expires_at > now
    is_expired = not trial_ok and not plan_ok

    def days_left(dt_obj):
        if not dt_obj:
            return 0
        delta = dt_obj - now
        return max(0, delta.days)

    # Clinic plan context
    from database.models import ClinicDoctor, Clinic
    membership = db.query(ClinicDoctor).filter(
        ClinicDoctor.doctor_id == doctor.id, ClinicDoctor.role == "owner"
    ).first()
    clinic = db.query(Clinic).filter(Clinic.id == membership.clinic_id).first() if membership else None
    clinic_doctor_count = 0
    clinic_plan_ok = False
    if clinic:
        clinic_doctor_count = db.query(ClinicDoctor).filter(
            ClinicDoctor.clinic_id == clinic.id, ClinicDoctor.is_active == True
        ).count()
        clinic_plan_ok = bool(clinic.plan_expires_at and clinic.plan_expires_at > now)

    return templates.TemplateResponse(request, "billing.html", {
        "doctor":              doctor,
        "trial_ok":            trial_ok,
        "plan_ok":             plan_ok,
        "is_expired":          is_expired,
        "trial_days_left":     days_left(doctor.trial_ends_at),
        "plan_days_left":      days_left(doctor.plan_expires_at),
        "razorpay_configured": bool(cfg.RAZORPAY_KEY_ID),
        "success":             success,
        "active":              "billing",
        "pin_required":        getattr(request.state, "pin_required", False),
        "clinic":              clinic,
        "clinic_doctor_count": clinic_doctor_count,
        "clinic_plan_ok":      clinic_plan_ok,
        "clinic_plan_days_left": days_left(clinic.plan_expires_at) if clinic else 0,
    })


@router.post("/billing/create-order")
def billing_create_order(
    plan: str = Query(...),
    doctor: Doctor = Depends(require_pin_auth),
):
    from fastapi.responses import JSONResponse
    from services.payment_service import create_order
    result = create_order(plan)
    return JSONResponse(result)


@router.post("/billing/verify", response_class=HTMLResponse)
def billing_verify(
    razorpay_payment_id: str = Form(...),
    razorpay_order_id:   str = Form(...),
    razorpay_signature:  str = Form(...),
    plan:                str = Form(...),
    doctor: Doctor = Depends(require_pin_auth),
    db: Session    = Depends(get_db),
):
    from datetime import datetime as dt, timedelta
    from services.payment_service import verify_signature, PLAN_AMOUNTS
    from database.models import Subscription, PlanType

    if not verify_signature(razorpay_payment_id, razorpay_order_id, razorpay_signature):
        return RedirectResponse(url="/billing?success=fail", status_code=303)

    now      = dt.utcnow()
    end_date = now + timedelta(days=30)

    if plan == "clinic":
        # Clinic plan — activate the clinic, also extend doctor's own access
        from database.models import ClinicDoctor, Clinic
        membership = db.query(ClinicDoctor).filter(
            ClinicDoctor.doctor_id == doctor.id, ClinicDoctor.role == "owner"
        ).first()
        if membership:
            clinic = db.query(Clinic).filter(Clinic.id == membership.clinic_id).first()
            if clinic:
                clinic.plan_type       = "clinic"
                clinic.plan_expires_at = end_date
                sub = Subscription(
                    doctor_id=doctor.id, clinic_id=clinic.id,
                    plan_name=plan, amount=PLAN_AMOUNTS.get(plan, 0),
                    payment_id=razorpay_payment_id,
                    start_date=now.date(), end_date=end_date.date(), status="active",
                )
                db.add(sub)
        # Also extend doctor's individual plan so they can still log in
        doctor.plan_expires_at = end_date
        doctor.plan_type = PlanType.solo
    else:
        # Solo / legacy plans
        sub = Subscription(
            doctor_id=doctor.id,
            plan_name=plan, amount=PLAN_AMOUNTS.get(plan, 0),
            payment_id=razorpay_payment_id,
            start_date=now.date(), end_date=end_date.date(), status="active",
        )
        db.add(sub)
        plan_map = {"solo": PlanType.solo, "basic": PlanType.basic, "pro": PlanType.pro}
        doctor.plan_expires_at = end_date
        doctor.plan_type = plan_map.get(plan, PlanType.solo)

    db.commit()
    return RedirectResponse(url="/billing?success=1", status_code=303)


# ------------------------------------------------------------------ #
#  PIN Prompt — GET (show entry form)                                  #
# ------------------------------------------------------------------ #

@router.get("/pin-prompt", response_class=HTMLResponse)
def pin_prompt_page(
    next: str = Query(default="/dashboard"),
):
    # Overlay is now inline on each protected page.
    # This route just redirects to the destination (which will show the overlay).
    return RedirectResponse(url=next, status_code=303)


# ------------------------------------------------------------------ #
#  PIN Prompt — POST (verify and set cookie)                           #
# ------------------------------------------------------------------ #

@router.post("/pin-prompt", response_class=HTMLResponse)
async def verify_pin_post(
    request: Request,
    pin: str = Form(...),
    next: str = Form(default="/dashboard"),
    doctor: Doctor = Depends(get_current_doctor),
):
    if not doctor.pin_hash:
        return RedirectResponse(url=next, status_code=303)

    if not verify_password(pin.strip(), doctor.pin_hash):
        from urllib.parse import quote
        # Redirect back to the same page — the overlay will show with error
        sep = "&" if "?" in next else "?"
        return RedirectResponse(url=f"{next}{sep}pin_error=1", status_code=303)

    resp = RedirectResponse(url=next, status_code=303)
    token = create_pin_token(doctor.id)
    resp.set_cookie("pin_session", token, httponly=True, samesite="lax", max_age=1800)
    return resp


# ------------------------------------------------------------------ #
#  Settings — PIN Setup / Change / Remove                              #
# ------------------------------------------------------------------ #

@router.post("/doctors/settings/pin", response_class=HTMLResponse)
async def update_pin(
    request: Request,
    current_pin: str = Form(""),
    new_pin: str = Form(""),
    confirm_pin: str = Form(""),
    action: str = Form("set"),
    doctor: Doctor = Depends(get_paying_doctor),   # not require_pin — PIN setup is the entry point
    db: Session = Depends(get_db),
):
    if action == "remove":
        if not doctor.pin_hash:
            return RedirectResponse("/doctors/settings?saved=1", 303)
        if not verify_password(current_pin.strip(), doctor.pin_hash):
            return RedirectResponse("/doctors/settings?pin_error=wrong", 303)
        doctor.pin_hash = None
        db.commit()
        resp = RedirectResponse("/doctors/settings?saved=1", 303)
        resp.delete_cookie("pin_session")
        return resp

    # Validate new PIN
    pin = new_pin.strip()
    confirm = confirm_pin.strip()
    if not pin.isdigit() or not (4 <= len(pin) <= 6):
        return RedirectResponse("/doctors/settings?pin_error=invalid", 303)
    if pin != confirm:
        return RedirectResponse("/doctors/settings?pin_error=mismatch", 303)
    if doctor.pin_hash and not verify_password(current_pin.strip(), doctor.pin_hash):
        return RedirectResponse("/doctors/settings?pin_error=wrong", 303)

    doctor.pin_hash = hash_password(pin)
    db.commit()

    # Issue pin_session so the doctor stays verified after setting PIN
    resp = RedirectResponse("/doctors/settings?saved=1", 303)
    token = create_pin_token(doctor.id)
    resp.set_cookie("pin_session", token, httponly=True, samesite="lax", max_age=1800)
    return resp
