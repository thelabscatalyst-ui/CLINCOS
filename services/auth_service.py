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


def get_paying_doctor(doctor=Depends(get_current_doctor)):
    """Dependency for all protected routes — raises PlanExpired if subscription lapsed."""
    now = datetime.utcnow()
    trial_ok = doctor.trial_ends_at and doctor.trial_ends_at > now
    plan_ok  = doctor.plan_expires_at and doctor.plan_expires_at > now
    if not trial_ok and not plan_ok:
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
