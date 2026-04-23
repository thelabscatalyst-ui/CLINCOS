import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Doctor, PlanType, Staff
from services.auth_service import hash_password, verify_password, create_access_token, create_staff_token

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")


def _make_slug(name: str, city: str) -> str:
    """Generate a URL-safe slug from doctor name + city."""
    raw = f"{name}-{city}".lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug


def _unique_slug(base: str, db: Session) -> str:
    slug = base
    counter = 1
    while db.query(Doctor).filter(Doctor.slug == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


# ------------------------------------------------------------------ #
#  Register                                                            #
# ------------------------------------------------------------------ #

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})


@router.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    specialization: str = Form(""),
    clinic_name: str = Form(""),
    city: str = Form(""),
    db: Session = Depends(get_db),
):
    # Check duplicates
    if db.query(Doctor).filter(Doctor.email == email).first():
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Email already registered. Please login."},
            status_code=400,
        )
    if db.query(Doctor).filter(Doctor.phone == phone).first():
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Phone number already registered."},
            status_code=400,
        )

    slug = _unique_slug(_make_slug(name, city or "clinic"), db)

    doctor = Doctor(
        name=name,
        email=email.lower().strip(),
        phone=phone.strip(),
        password_hash=hash_password(password),
        specialization=specialization.strip() or None,
        clinic_name=clinic_name.strip() or None,
        city=city.strip() or None,
        slug=slug,
        plan_type=PlanType.trial,
        trial_ends_at=datetime.utcnow() + timedelta(days=14),
    )
    db.add(doctor)
    db.commit()

    return RedirectResponse(url="/login?registered=1", status_code=303)


# ------------------------------------------------------------------ #
#  Login                                                               #
# ------------------------------------------------------------------ #

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, registered: str = ""):
    success = "Account created! Please log in." if registered == "1" else None
    return templates.TemplateResponse(request, "login.html", {"error": None, "success": success})


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    normalized_email = email.lower().strip()

    # ── Try doctor first ──────────────────────────────────────────────────────
    doctor = db.query(Doctor).filter(Doctor.email == normalized_email).first()
    if doctor:
        if not verify_password(password, doctor.password_hash):
            return templates.TemplateResponse(
                request, "login.html",
                {"error": "Invalid email or password.", "success": None},
                status_code=401,
            )
        if not doctor.is_active:
            return templates.TemplateResponse(
                request, "login.html",
                {"error": "Your account has been deactivated.", "success": None},
                status_code=403,
            )
        token = create_access_token({"doctor_id": doctor.id})
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(
            key="access_token", value=token,
            httponly=True, max_age=60 * 60 * 24, samesite="lax",
        )
        return response

    # ── Try staff (receptionist / manager) ───────────────────────────────────
    staff = db.query(Staff).filter(Staff.email == normalized_email).first()
    if staff and staff.password_hash and verify_password(password, staff.password_hash):
        if not staff.is_active:
            return templates.TemplateResponse(
                request, "login.html",
                {"error": "Your account has been deactivated.", "success": None},
                status_code=403,
            )
        allowed = staff.allowed_doctor_ids or []
        token = create_staff_token(staff.id, staff.clinic_id, allowed)
        response = RedirectResponse(url="/clinic/reception", status_code=303)
        response.set_cookie(
            key="access_token", value=token,
            httponly=True, max_age=60 * 60 * 24, samesite="lax",
        )
        return response

    return templates.TemplateResponse(
        request, "login.html",
        {"error": "Invalid email or password.", "success": None},
        status_code=401,
    )


# ------------------------------------------------------------------ #
#  Logout                                                              #
# ------------------------------------------------------------------ #

@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response
