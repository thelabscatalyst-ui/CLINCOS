from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import settings
from database.connection import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def get_current_doctor(request: Request, db: Session = Depends(get_db)):
    from database.models import Doctor
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    doctor = db.query(Doctor).filter(Doctor.id == payload.get("doctor_id")).first()
    if not doctor or not doctor.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return doctor


class PlanExpired(Exception):
    """Raised when a doctor's trial and paid plan have both expired."""
    pass


class PinRequired(Exception):
    """Raised when a PIN-protected route is hit without a valid PIN session."""
    def __init__(self, return_url: str = "/dashboard"):
        self.return_url = return_url
        super().__init__("PIN required")


PIN_SESSION_MINUTES = 30


def create_pin_token(doctor_id: int) -> str:
    """Create a short-lived JWT for PIN session (30 min)."""
    payload = {
        "doctor_id": doctor_id,
        "pin_ok": True,
        "exp": datetime.utcnow() + timedelta(minutes=PIN_SESSION_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_pin_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("pin_ok"):
            return payload
        return None
    except JWTError:
        return None


def _pin_ok(request: Request, doctor) -> bool:
    """Returns True if PIN session cookie is valid, or if doctor has no PIN set."""
    if not doctor.pin_hash:
        return True
    pin_token = request.cookies.get("pin_session")
    if not pin_token:
        return False
    payload = decode_pin_token(pin_token)
    return bool(payload and payload.get("doctor_id") == doctor.id)


def get_paying_doctor(doctor=Depends(get_current_doctor), db: Session = Depends(get_db)):
    """Dependency for all protected routes — raises PlanExpired if subscription lapsed.
    For clinic-member doctors (no trial, no own plan), checks if their clinic is active.
    A clinic is considered active if:
      (a) it has a paid plan_expires_at in the future, OR
      (b) the clinic owner still has an active trial or plan (clinic is in trial mode)
    """
    now = datetime.utcnow()
    trial_ok = doctor.trial_ends_at and doctor.trial_ends_at > now
    plan_ok  = doctor.plan_expires_at and doctor.plan_expires_at > now
    if not trial_ok and not plan_ok:
        from database.models import ClinicDoctor, Clinic, Doctor as DoctorModel
        # Find all clinics this doctor is an active member of
        memberships = db.query(ClinicDoctor).filter(
            ClinicDoctor.doctor_id == doctor.id,
            ClinicDoctor.is_active == True,
        ).all()
        clinic_ok = False
        for m in memberships:
            clinic = db.query(Clinic).filter(Clinic.id == m.clinic_id).first()
            if not clinic:
                continue
            # (a) Clinic has a paid active plan
            if clinic.plan_expires_at and clinic.plan_expires_at > now:
                clinic_ok = True
                break
            # (b) Clinic is on trial — check owner's trial/plan is still active
            if clinic.owner_doctor_id:
                owner = db.query(DoctorModel).filter(DoctorModel.id == clinic.owner_doctor_id).first()
                if owner:
                    owner_ok = (
                        (owner.trial_ends_at and owner.trial_ends_at > now) or
                        (owner.plan_expires_at and owner.plan_expires_at > now)
                    )
                    if owner_ok:
                        clinic_ok = True
                        break
        if not clinic_ok:
            raise PlanExpired()
    return doctor


def _pin_parent_path(path: str) -> str:
    """Map a non-GET path to its parent GET page so redirect lands on the overlay."""
    if path.startswith("/doctors/settings"):
        return "/doctors/settings"
    if path.startswith("/billing"):
        return "/billing"
    return "/dashboard"


def require_pin(request: Request, doctor=Depends(get_paying_doctor)):
    """PIN-protected + plan-gated.
    GET  → sets request.state.pin_required; route renders page with blur overlay.
    POST → raises PinRequired; handler redirects to parent GET (which shows overlay).
    """
    needs = bool(doctor.pin_hash) and not _pin_ok(request, doctor)
    request.state.pin_required = needs
    if needs and request.method != "GET":
        raise PinRequired(return_url=_pin_parent_path(str(request.url.path)))
    return doctor


def require_pin_auth(request: Request, doctor=Depends(get_current_doctor)):
    """PIN-protected billing routes (no plan gate).
    Same GET/POST split as require_pin.
    """
    needs = bool(doctor.pin_hash) and not _pin_ok(request, doctor)
    request.state.pin_required = needs
    if needs and request.method != "GET":
        raise PinRequired(return_url=_pin_parent_path(str(request.url.path)))
    return doctor


def get_admin_doctor(doctor=Depends(get_current_doctor)):
    """Dependency for /admin routes — only allows the platform owner."""
    from config import settings
    if not settings.ADMIN_EMAIL or doctor.email.lower() != settings.ADMIN_EMAIL.lower():
        raise HTTPException(status_code=403, detail="Admin access required")
    return doctor


# ──────────────────────────────────────────────────────────────────────────── #
#  Phase 2 — Staff / Clinic auth                                               #
# ──────────────────────────────────────────────────────────────────────────── #

def create_staff_token(staff_id: int, clinic_id: int, allowed_doctor_ids: list) -> str:
    """Issue a JWT for a staff member (receptionist / manager)."""
    payload = {
        "user_type":          "staff",
        "staff_id":           staff_id,
        "clinic_id":          clinic_id,
        "allowed_doctor_ids": allowed_doctor_ids or [],
        "exp":                datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_staff(request: Request, db: Session = Depends(get_db)):
    """Dependency: returns the authenticated Staff object, or raises 401."""
    from database.models import Staff
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    payload = decode_token(token)
    if not payload or payload.get("user_type") != "staff":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Staff session required")
    staff = db.query(Staff).filter(Staff.id == payload["staff_id"]).first()
    if not staff or not staff.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Staff account not found")
    # attach allowed_doctor_ids from JWT (may be fresher than DB until next login)
    request.state.staff_allowed_doctors = payload.get("allowed_doctor_ids", [])
    return staff


def get_clinic_owner(request: Request, db: Session = Depends(get_db)):
    """Dependency for /clinic/admin routes — doctor who owns a clinic."""
    from database.models import ClinicDoctor, Clinic
    doctor = get_current_doctor(request, db)
    membership = (
        db.query(ClinicDoctor)
        .filter(ClinicDoctor.doctor_id == doctor.id, ClinicDoctor.role == "owner")
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Clinic owner access required")
    clinic = db.query(Clinic).filter(Clinic.id == membership.clinic_id).first()
    request.state.clinic = clinic
    return doctor
