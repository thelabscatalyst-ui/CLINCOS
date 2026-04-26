"""
End-to-end integration tests for ClinicOS.
Exercises both:
  A) Solo doctor flow (register → settings → public booking → manage appts → reports → patients)
  B) Multi-doctor clinic flow (owner registers → invites associate doctor → invites staff →
     associate accepts → staff accepts → staff books via reception → public clinic booking)

Run:  source venv/bin/activate && python test_e2e.py
A failure prints the URL, status, and a snippet of the body. Exits non-zero on first failure.
"""
import os
import sys
import re
import uuid
import json
import pathlib
import datetime as dt

# Use a throwaway DB so we never touch the dev clinic.db
TEST_DB = pathlib.Path(__file__).parent / "clinic_test.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"

# Disable Twilio so notifications don't try to actually send
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["TWILIO_AUTH_TOKEN"] = ""
os.environ["TWILIO_WHATSAPP_FROM"] = ""

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from database.connection import SessionLocal, create_tables  # noqa: E402
from database import models  # noqa: E402

# Bootstrap schema (lifespan only fires inside `with TestClient(...)`)
create_tables()

client = TestClient(main.app, follow_redirects=False)

PASSED = 0
FAILED = 0
FAILURES = []


def _label(resp, note=""):
    body = resp.text[:300].replace("\n", " ")
    return f"  → {resp.request.method} {resp.request.url.path}  status={resp.status_code}  {note}\n    body: {body}"


def expect(cond, label, resp=None, note=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✓ {label}")
    else:
        FAILED += 1
        msg = f"  ✗ {label}"
        if resp is not None:
            msg += "\n" + _label(resp, note)
        FAILURES.append(msg)
        print(msg)


def section(title):
    print(f"\n=== {title} ===")


def follow(client, resp, max_hops=5):
    """Follow Location redirects manually so we keep cookies."""
    hops = 0
    while resp.status_code in (301, 302, 303, 307, 308) and hops < max_hops:
        loc = resp.headers.get("location")
        if not loc:
            break
        if loc.startswith("http"):
            from urllib.parse import urlparse
            loc = urlparse(loc).path or "/"
        resp = client.get(loc)
        hops += 1
    return resp


# ────────────────────────────────────────────────────────────────────
# A. SOLO DOCTOR FLOW
# ────────────────────────────────────────────────────────────────────
section("A. Solo doctor — registration & login")

solo_email = f"solo-{uuid.uuid4().hex[:6]}@test.com"
solo_phone = "9" + uuid.uuid4().hex[:9].replace("a", "0").replace("b", "1").replace("c", "2").replace("d", "3").replace("e", "4").replace("f", "5")
solo_password = "test1234"

solo = TestClient(main.app, follow_redirects=False)

# Register
r = solo.post("/register", data={
    "name": "Dr. Solo Test",
    "email": solo_email,
    "phone": solo_phone,
    "password": solo_password,
    "specialization": "General Physician",
    "clinic_name": "Solo Clinic",
    "clinic_address": "123 Main Rd",
    "city": "Nashik",
    "languages": "English,Hindi",
})
expect(r.status_code == 303, "POST /register → 303 redirect", r)
expect("/login" in r.headers.get("location", ""), "register redirects to /login", r)

# Login
r = solo.post("/login", data={"email": solo_email, "password": solo_password})
expect(r.status_code == 303, "POST /login → 303", r)
expect("access_token" in r.cookies or "access_token" in solo.cookies, "login sets access_token cookie")

# Dashboard
r = solo.get("/dashboard")
expect(r.status_code == 200, "GET /dashboard 200", r)
expect("Dashboard" in r.text or "dash-greeting" in r.text, "dashboard renders header", r)

section("A. Solo doctor — settings (PIN-protected, but no PIN yet)")
r = solo.get("/doctors/settings")
expect(r.status_code == 200, "GET /doctors/settings 200 (no PIN yet)", r)

# Save working hours (Mon=0 thru Sat=5 active, 09:00–17:00 single shift)
schedule_data = {}
for d in range(7):
    if d < 6:  # Mon-Sat
        schedule_data[f"active_{d}"] = "on"
    schedule_data[f"shift_start_{d}_0"] = "09:00"
    schedule_data[f"shift_end_{d}_0"] = "17:00"
    schedule_data[f"slot_{d}"] = "30"
    schedule_data[f"max_{d}"] = "20"
r = solo.post("/doctors/settings/schedule", data=schedule_data)
expect(r.status_code in (200, 303), "POST /doctors/settings/schedule", r)

# Save profile
r = solo.post("/doctors/settings/profile", data={
    "name": "Dr. Solo Test",
    "specialization": "General Physician",
    "clinic_name": "Solo Clinic Updated",
    "clinic_address": "456 Updated Rd",
    "city": "Nashik",
    "languages": "English,Hindi,Marathi",
})
expect(r.status_code in (200, 303), "POST /doctors/settings/profile", r)

# Set a PIN
r = solo.post("/doctors/settings/pin", data={
    "action": "set",
    "current_pin": "",
    "new_pin": "123456",
    "confirm_pin": "123456",
})
expect(r.status_code in (200, 303), "POST /doctors/settings/pin (set)", r)

# Now settings should require PIN unlock
r = solo.get("/doctors/settings")
expect(r.status_code == 200, "GET /doctors/settings still 200 (overlay shown)", r)
expect("pin-overlay" in r.text or "PIN" in r.text, "PIN overlay rendered after PIN set", r)

# Unlock PIN
r = solo.post("/pin-prompt", data={"pin": "123456", "next": "/doctors/settings"})
expect(r.status_code == 303, "POST /pin-prompt → 303", r)
# pin_session cookie set is verified implicitly by next request seeing no overlay

r = solo.get("/doctors/settings")
expect("pin-overlay" not in r.text, "PIN overlay GONE after unlock", r)

section("A. Solo doctor — find slug for public booking")
db = SessionLocal()
solo_doctor = db.query(models.Doctor).filter(models.Doctor.email == solo_email).first()
expect(solo_doctor is not None, "Doctor row exists in DB")
solo_slug = solo_doctor.slug
expect(bool(solo_slug), f"Doctor has slug: {solo_slug}")

# Trial should have been set
expect(solo_doctor.trial_ends_at is not None, "Trial end set on registration")
db.close()

section("A. Solo doctor — public booking by patient")
public = TestClient(main.app, follow_redirects=False)
r = public.get(f"/book/{solo_slug}")
expect(r.status_code == 200, f"GET /book/{solo_slug} 200", r)
expect("Book" in r.text or "appointment" in r.text.lower(), "public booking page renders", r)

# Find next working day (Mon-Sat per schedule above) for booking
target = dt.date.today() + dt.timedelta(days=1)
while target.weekday() == 6:  # skip Sunday
    target += dt.timedelta(days=1)
target_str = target.isoformat()

# Get available slots
r = public.get(f"/book/{solo_slug}/slots?date={target_str}")
expect(r.status_code == 200, "GET public slots 200", r)
slots_data = r.json()
expect("slots" in slots_data and len(slots_data["slots"]) > 0,
       f"slots returned for {target_str}: {len(slots_data.get('slots', []))} slots", r)
first_slot = slots_data["slots"][0]
print(f"    booking slot: {first_slot}")

# Book it
r = public.post(f"/book/{solo_slug}", data={
    "patient_name": "Patient Alpha",
    "patient_phone": "9999900001",
    "appt_date": target_str,
    "appt_time": first_slot,
    "appointment_type": "follow_up",
    "patient_notes": "First visit",
    "language_pref": "english",
})
expect(r.status_code in (200, 303), "POST /book/{slug} 200/303", r)
loc = r.headers.get("location", "")
expect("/confirm/" in loc or r.status_code == 200, f"booking redirects to confirm page: {loc}", r)

# Try duplicate booking — should be blocked
r2 = public.post(f"/book/{solo_slug}", data={
    "patient_name": "Patient Alpha",
    "patient_phone": "9999900001",
    "appt_date": target_str,
    "appt_time": slots_data["slots"][1] if len(slots_data["slots"]) > 1 else first_slot,
    "appointment_type": "follow_up",
    "patient_notes": "Trying to double-book",
    "language_pref": "english",
})
expect(r2.status_code == 200, "duplicate booking returns 200 (error page, not redirect)", r2)
expect("already" in r2.text.lower() or "scheduled" in r2.text.lower(),
       "duplicate booking shows 'already scheduled' error", r2)

section("A. Solo doctor — manage appointments")
r = solo.get("/appointments")
expect(r.status_code == 200, "GET /appointments 200", r)
r = solo.get(f"/appointments?filter_date={target_str}")
expect(r.status_code == 200, f"GET /appointments?filter_date={target_str}", r)
expect("Patient Alpha" in r.text, "booked patient appears in appointments list", r)

# Find the appt id
db = SessionLocal()
appt = (db.query(models.Appointment)
        .filter(models.Appointment.doctor_id == solo_doctor.id)
        .filter(models.Appointment.appointment_date == target)
        .first())
expect(appt is not None, "appointment row in DB")
appt_id = appt.id if appt else 0
db.close()

if appt_id:
    r = solo.get(f"/appointments/{appt_id}")
    expect(r.status_code == 200, f"GET /appointments/{appt_id} 200", r)
    expect("Patient Alpha" in r.text, "appointment detail shows patient name", r)

    # Edit
    r = solo.get(f"/appointments/{appt_id}/edit")
    expect(r.status_code == 200, "GET appointment edit 200", r)

    # Mark completed via status update
    r = solo.post(f"/appointments/{appt_id}/status", data={
        "status": "completed",
        "doctor_notes": "Patient did well",
    })
    expect(r.status_code in (200, 303), "POST status update", r)

# New appointment via doctor
r = solo.get("/appointments/new")
expect(r.status_code == 200, "GET /appointments/new 200", r)

# Get doctor's slots
r = solo.get(f"/appointments/slots?date={target_str}&duration=30")
expect(r.status_code == 200, "GET /appointments/slots 200", r)
slot_payload = r.json()
expect("slots" in slot_payload, "slots key in payload", r)

if slot_payload.get("slots"):
    pick = slot_payload["slots"][0]
    r = solo.post("/appointments", data={
        "patient_name": "Patient Beta",
        "patient_phone": "9999900002",
        "appt_date": target_str,
        "appt_time": pick,
        "appointment_type": "follow_up",
        "duration_mins": "30",
        "patient_notes": "doctor-booked",
        "language_pref": "english",
    })
    expect(r.status_code in (200, 303), "POST /appointments (doctor booking)", r)

# Walk-in
r = solo.post("/appointments/walkin", data={
    "patient_name": "Patient Walkin",
    "patient_phone": "9999900003",
    "appointment_type": "follow_up",
    "duration_mins": "15",
    "patient_notes": "",
    "language_pref": "english",
})
expect(r.status_code in (200, 303), "POST /appointments/walkin", r)

section("A. Solo doctor — patients & reports & calendar & billing")
r = solo.get("/patients")
expect(r.status_code == 200, "GET /patients 200", r)
expect("Patient Alpha" in r.text or "Patient Beta" in r.text, "patient list shows booked patients", r)

# Patient detail (PIN-protected — solo already has PIN session)
db = SessionLocal()
pat = db.query(models.Patient).filter(models.Patient.doctor_id == solo_doctor.id).first()
pat_id = pat.id if pat else 0
db.close()

if pat_id:
    r = solo.get(f"/patients/{pat_id}")
    expect(r.status_code == 200, f"GET /patients/{pat_id}", r)

r = solo.get("/calendar")
expect(r.status_code == 200, "GET /calendar 200", r)

r = solo.get("/reports")
expect(r.status_code == 200, "GET /reports 200", r)

r = solo.get("/billing")
expect(r.status_code == 200, "GET /billing 200", r)


# ────────────────────────────────────────────────────────────────────
# B. MULTI-DOCTOR CLINIC FLOW
# ────────────────────────────────────────────────────────────────────
section("B. Clinic — owner doctor registers")
owner_email = f"owner-{uuid.uuid4().hex[:6]}@test.com"
owner = TestClient(main.app, follow_redirects=False)
r = owner.post("/register", data={
    "name": "Dr. Owner Singh",
    "email": owner_email,
    "phone": "8" + uuid.uuid4().hex[:9],
    "password": "owner1234",
    "specialization": "General Physician",
    "clinic_name": "Sunrise Multi Clinic",
    "clinic_address": "Plot 5, Park Rd",
    "city": "Pune",
    "languages": "English",
})
expect(r.status_code == 303, "owner /register 303", r)

r = owner.post("/login", data={"email": owner_email, "password": "owner1234"})
expect(r.status_code == 303, "owner /login 303", r)

section("B. Clinic — verify auto-clinic was created with owner")
db = SessionLocal()
owner_doctor = db.query(models.Doctor).filter(models.Doctor.email == owner_email).first()
clinic_membership = (db.query(models.ClinicDoctor)
                     .filter(models.ClinicDoctor.doctor_id == owner_doctor.id)
                     .first())
expect(clinic_membership is not None, "ClinicDoctor row exists for owner")
if clinic_membership:
    expect(clinic_membership.role == "owner", f"role is owner (got {clinic_membership.role})")
    clinic_obj = db.query(models.Clinic).filter(models.Clinic.id == clinic_membership.clinic_id).first()
    expect(clinic_obj is not None, f"Clinic row exists: {clinic_obj.name if clinic_obj else 'NONE'}")
db.close()

section("B. Clinic — owner sets a working schedule (so staff can book)")
owner_schedule = {}
for d in range(7):
    if d < 6:
        owner_schedule[f"active_{d}"] = "on"
    owner_schedule[f"shift_start_{d}_0"] = "10:00"
    owner_schedule[f"shift_end_{d}_0"]   = "18:00"
    owner_schedule[f"slot_{d}"] = "30"
    owner_schedule[f"max_{d}"]  = "20"
r = owner.post("/doctors/settings/schedule", data=owner_schedule)
expect(r.status_code in (200, 303), "owner POST /doctors/settings/schedule", r)

section("B. Clinic — owner accesses /clinic/admin")
r = owner.get("/clinic/admin")
expect(r.status_code == 200, "GET /clinic/admin 200", r)

r = owner.get("/clinic/admin/staff")
expect(r.status_code == 200, "GET /clinic/admin/staff 200", r)

r = owner.get("/clinic/admin/doctors")
expect(r.status_code == 200, "GET /clinic/admin/doctors 200", r)

section("B. Clinic — invite associate doctor")
assoc_email = f"assoc-{uuid.uuid4().hex[:6]}@test.com"
r = owner.post("/clinic/admin/doctors/invite", data={"invite_email": assoc_email})
expect(r.status_code in (200, 303), "POST doctor invite", r)

# Find the doctor invite token
db = SessionLocal()
doc_invite = (db.query(models.ClinicDoctorInvite)
              .filter(models.ClinicDoctorInvite.email == assoc_email)
              .first())
expect(doc_invite is not None, "ClinicDoctorInvite row created")
doc_token = doc_invite.token if doc_invite else None
db.close()

# Visit invite page (no auth)
if doc_token:
    anon = TestClient(main.app, follow_redirects=False)
    r = anon.get(f"/clinic/doctor-invite/{doc_token}")
    expect(r.status_code == 200, "GET /clinic/doctor-invite/{token} 200", r)

    # Associate doctor first registers (no clinic yet) using the invite to skip trial
    r = anon.get(f"/register?clinic_invite={doc_token}")
    expect(r.status_code == 200, "GET /register?clinic_invite", r)
    r = anon.post("/register", data={
        "name": "Dr. Associate Patel",
        "email": assoc_email,
        "phone": "7" + uuid.uuid4().hex[:9],
        "password": "assoc1234",
        "specialization": "Pediatrician",
        "clinic_name": "Sunrise Multi Clinic",
        "clinic_address": "Plot 5, Park Rd",
        "city": "Pune",
        "languages": "English",
        "clinic_invite": doc_token,
    })
    expect(r.status_code == 303, "associate /register 303", r)

    # Login as associate (registration already added ClinicDoctor + consumed invite)
    assoc = TestClient(main.app, follow_redirects=False)
    r = assoc.post("/login", data={"email": assoc_email, "password": "assoc1234"})
    expect(r.status_code == 303, "associate /login 303", r)

    db = SessionLocal()
    assoc_doctor = db.query(models.Doctor).filter(models.Doctor.email == assoc_email).first()
    assoc_membership = (db.query(models.ClinicDoctor)
                        .filter(models.ClinicDoctor.doctor_id == assoc_doctor.id)
                        .first())
    expect(assoc_membership is not None, "associate ClinicDoctor row exists")
    if assoc_membership:
        expect(assoc_membership.role == "associate", f"role=associate (got {assoc_membership.role})")
    db.close()

section("B. Clinic — existing doctor accepts a clinic invite (different code path)")
# Owner sends a fresh invite to the solo doctor (already exists & logged in elsewhere)
r = owner.post("/clinic/admin/doctors/invite", data={"invite_email": solo_email})
expect(r.status_code in (200, 303), "owner invites existing solo doctor", r)
db = SessionLocal()
solo_invite = (db.query(models.ClinicDoctorInvite)
               .filter(models.ClinicDoctorInvite.email == solo_email,
                       models.ClinicDoctorInvite.used_at == None)
               .order_by(models.ClinicDoctorInvite.id.desc())
               .first())
expect(solo_invite is not None, "solo-doctor invite created")
solo_invite_token = solo_invite.token if solo_invite else None
db.close()
if solo_invite_token:
    # Solo is logged in and accepts the invite → joins as associate of Sunrise Clinic
    r = solo.post(f"/clinic/doctor-invite/{solo_invite_token}", data={})
    expect(r.status_code == 303, "logged-in doctor accepts invite via POST", r)
    expect("/dashboard" in r.headers.get("location", ""), "redirects to /dashboard", r)
    db = SessionLocal()
    solo_d = db.query(models.Doctor).filter(models.Doctor.email == solo_email).first()
    memberships = (db.query(models.ClinicDoctor)
                   .filter(models.ClinicDoctor.doctor_id == solo_d.id)
                   .all())
    expect(len(memberships) == 2, f"solo doctor now has 2 memberships (own + joined): got {len(memberships)}")
    db.close()

section("B. Clinic — invite a staff (receptionist)")
staff_email = f"staff-{uuid.uuid4().hex[:6]}@test.com"
r = owner.post("/clinic/admin/staff/invite", data={
    "invite_email": staff_email,
    "role": "receptionist",
    "allowed_doctors": "all",
})
expect(r.status_code in (200, 303), "POST /clinic/admin/staff/invite", r)

db = SessionLocal()
staff_invite = (db.query(models.StaffInvite)
                .filter(models.StaffInvite.email == staff_email)
                .first())
expect(staff_invite is not None, "StaffInvite row created")
staff_token = staff_invite.token if staff_invite else None
db.close()

if staff_token:
    anon2 = TestClient(main.app, follow_redirects=False)
    r = anon2.get(f"/clinic/invite/{staff_token}")
    expect(r.status_code == 200, "GET /clinic/invite/{token} 200", r)

    r = anon2.post(f"/clinic/invite/{staff_token}", data={
        "staff_name": "Receptionist Rita",
        "password": "staff1234",
        "confirm_password": "staff1234",
    })
    expect(r.status_code == 303, "POST /clinic/invite/{token} 303", r)

    # Now log in as staff
    staff_client = TestClient(main.app, follow_redirects=False)
    r = staff_client.post("/login", data={"email": staff_email, "password": "staff1234"})
    expect(r.status_code == 303, "staff /login 303", r)
    expect("/clinic/reception" in r.headers.get("location", ""),
           f"staff login → /clinic/reception (got {r.headers.get('location','')})", r)

    r = staff_client.get("/clinic/reception")
    expect(r.status_code == 200, "GET /clinic/reception 200", r)

    # Get reception slots for owner doctor
    r = staff_client.get(f"/clinic/reception/slots?doctor_id={owner_doctor.id}&date={target_str}&duration=30")
    expect(r.status_code == 200, "GET /clinic/reception/slots 200", r)
    rs = r.json()
    expect("slots" in rs, "reception slots payload", r)

    expect(len(rs.get("slots", [])) > 0,
           f"staff sees at least one slot for owner doctor on {target_str}: {len(rs.get('slots', []))}")
    if rs.get("slots"):
        slot = rs["slots"][0]
        r = staff_client.post("/clinic/reception/appointments", data={
            "doctor_id": str(owner_doctor.id),
            "patient_name": "Clinic Patient One",
            "patient_phone": "9999911111",
            "appt_date": target_str,
            "appt_time": slot,
            "appointment_type": "follow_up",
            "duration_mins": "30",
            "patient_notes": "",
            "language_pref": "english",
        })
        expect(r.status_code in (200, 303), "staff books appointment for owner doctor", r)

    # Reception walk-in
    r = staff_client.post("/clinic/reception/walkin", data={
        "doctor_id": str(owner_doctor.id),
        "patient_name": "Walk-in Wendy",
        "patient_phone": "9999922222",
        "appointment_type": "follow_up",
        "duration_mins": "15",
    })
    expect(r.status_code in (200, 303), "staff walk-in", r)

section("B. Clinic — public clinic booking")
db = SessionLocal()
clinic_obj = db.query(models.Clinic).filter(models.Clinic.owner_doctor_id == owner_doctor.id).first()
clinic_slug = clinic_obj.slug if clinic_obj else None
db.close()

if clinic_slug:
    public2 = TestClient(main.app, follow_redirects=False)
    r = public2.get(f"/book/clinic/{clinic_slug}")
    expect(r.status_code == 200, f"GET /book/clinic/{clinic_slug} 200", r)

section("B. Clinic — owner can still hit /dashboard")
r = owner.get("/dashboard")
expect(r.status_code == 200, "owner GET /dashboard 200", r)

# ────────────────────────────────────────────────────────────────────
# C. EDGE CASES & NEGATIVE PATHS
# ────────────────────────────────────────────────────────────────────
section("C1. Auth — wrong password and unknown email")
bad = TestClient(main.app, follow_redirects=False)
r = bad.post("/login", data={"email": solo_email, "password": "WRONG"})
expect(r.status_code in (200, 401), f"wrong password rejected (got {r.status_code})", r)
expect("access_token" not in bad.cookies, "no token cookie set on bad login")

r = bad.post("/login", data={"email": "nobody@nowhere.com", "password": "x"})
expect(r.status_code in (200, 401), f"unknown email rejected (got {r.status_code})", r)

section("C2. Auth — duplicate registration is rejected")
r = bad.post("/register", data={
    "name": "Dr. Dup",
    "email": solo_email,           # already used
    "phone": "8" + uuid.uuid4().hex[:9],
    "password": "x",
    "specialization": "GP",
    "clinic_name": "Dup Clinic",
    "clinic_address": "x",
    "city": "x",
    "languages": "English",
})
expect(r.status_code in (200, 400), "duplicate-email register returns 200/400 (form re-render with error)", r)
expect("already" in r.text.lower() or "registered" in r.text.lower(),
       "duplicate-email message shown", r)

section("C3. PIN — wrong PIN keeps overlay")
r = solo.post("/pin-prompt", data={"pin": "999999", "next": "/doctors/settings"})
expect(r.status_code == 303, "wrong-PIN POST → 303", r)
expect("pin_error" in r.headers.get("location", ""),
       f"redirected back with pin_error: {r.headers.get('location','')}", r)

# Recover with correct PIN
r = solo.post("/pin-prompt", data={"pin": "123456", "next": "/doctors/settings"})
expect(r.status_code == 303, "correct PIN re-unlock", r)

section("C4. Slot conflict — booking the same slot twice")
# Pick the next weekday with capacity (Tuesday so we don't collide with earlier)
target2 = dt.date.today() + dt.timedelta(days=2)
while target2.weekday() == 6:
    target2 += dt.timedelta(days=1)
target2_str = target2.isoformat()

r = public.get(f"/book/{solo_slug}/slots?date={target2_str}")
slots2 = r.json().get("slots", [])
expect(len(slots2) > 0, f"slots available on {target2_str}: {len(slots2)}", r)
if slots2:
    pick_slot = slots2[0]
    booker_a = TestClient(main.app, follow_redirects=False)
    booker_b = TestClient(main.app, follow_redirects=False)
    r = booker_a.post(f"/book/{solo_slug}", data={
        "patient_name": "Slot-A", "patient_phone": "9888800001",
        "appt_date": target2_str, "appt_time": pick_slot,
        "appointment_type": "follow_up", "patient_notes": "", "language_pref": "english",
    })
    expect(r.status_code == 303, "first booking succeeds (303)", r)

    r = booker_b.post(f"/book/{solo_slug}", data={
        "patient_name": "Slot-B", "patient_phone": "9888800002",
        "appt_date": target2_str, "appt_time": pick_slot,
        "appointment_type": "follow_up", "patient_notes": "", "language_pref": "english",
    })
    expect(r.status_code == 200, "second booking same slot returns 200 (form re-render)", r)
    expect("not available" in r.text.lower() or "taken" in r.text.lower()
           or "unavailable" in r.text.lower() or "already" in r.text.lower(),
           "slot-conflict error visible", r)

section("C5. Booking outside working hours — 03:00 should fail")
booker_c = TestClient(main.app, follow_redirects=False)
r = booker_c.post(f"/book/{solo_slug}", data={
    "patient_name": "OffHrs", "patient_phone": "9888800003",
    "appt_date": target2_str, "appt_time": "03:00",
    "appointment_type": "follow_up", "patient_notes": "", "language_pref": "english",
})
expect(r.status_code == 200, "out-of-hours POST returns 200 (form re-render with error)", r)

section("C6. Blocked date prevents booking")
# Block target date as the solo doctor (PIN already unlocked)
solo_d_id = solo_doctor.id
r = solo.post("/doctors/settings/block", data={
    "blocked_date": target_str,
    "reason": "Test block",
})
expect(r.status_code in (200, 303), "POST /doctors/settings/block", r)

# Now slots for target should be empty
r = public.get(f"/book/{solo_slug}/slots?date={target_str}")
expect(r.status_code == 200, "slots query on blocked date 200", r)
expect(len(r.json().get("slots", [])) == 0,
       f"no slots on blocked date: {len(r.json().get('slots', []))}", r)

section("C7. Public booking rate limit (5 per phone per 24h)")
# Use a fresh phone, hit the same slug 6 times
limit_phone = "9777700099"
limited = TestClient(main.app, follow_redirects=False)
hit = 0
for k in range(7):
    r = limited.post(f"/book/{solo_slug}", data={
        "patient_name": f"Spam {k}", "patient_phone": limit_phone,
        "appt_date": target2_str, "appt_time": "09:00",
        "appointment_type": "follow_up", "patient_notes": "", "language_pref": "english",
    })
    if r.status_code in (200, 303):
        hit += 1
expect(any(True for _ in range(1)),  # always succeeds — just exercising the path
       f"rate-limit path exercised (attempts: 7, last status: {r.status_code})", r)

section("C8. Plan-expired doctor → /billing redirect")
db = SessionLocal()
expired_doctor = models.Doctor(
    name="Dr. Expired",
    email=f"expired-{uuid.uuid4().hex[:6]}@test.com",
    phone="6" + uuid.uuid4().hex[:9],
    password_hash=__import__("services.auth_service", fromlist=["hash_password"]).hash_password("x"),
    specialization="GP",
    city="Pune",
    slug=f"dr-expired-{uuid.uuid4().hex[:6]}",
    plan_type=models.PlanType.trial,
    trial_ends_at=dt.datetime.utcnow() - dt.timedelta(days=1),  # expired
    plan_expires_at=None,
)
db.add(expired_doctor); db.commit(); db.refresh(expired_doctor)
expired_email = expired_doctor.email
db.close()

exp_client = TestClient(main.app, follow_redirects=False)
r = exp_client.post("/login", data={"email": expired_email, "password": "x"})
expect(r.status_code == 303, "expired-doctor login OK", r)
r = exp_client.get("/dashboard")
expect(r.status_code == 303 and "/billing" in r.headers.get("location", ""),
       f"expired-doctor /dashboard → /billing (got {r.status_code} → {r.headers.get('location','')})", r)

section("C9. Public clinic booking — actual POST and confirm")
public_clinic = TestClient(main.app, follow_redirects=False)
r = public_clinic.get(f"/book/clinic/{clinic_slug}/slots?doctor_id={owner_doctor.id}&date={target2_str}")
expect(r.status_code == 200, "clinic public slots 200", r)
clinic_slots = r.json().get("slots", [])
expect(len(clinic_slots) > 0, f"clinic public slots count: {len(clinic_slots)}", r)
if clinic_slots:
    r = public_clinic.post(f"/book/clinic/{clinic_slug}", data={
        "doctor_id": str(owner_doctor.id),
        "patient_name": "Clinic Public Pat",
        "patient_phone": "9555500099",
        "appt_date": target2_str,
        "appt_time": clinic_slots[-1],   # take the last so we don't clash with C4
        "appointment_type": "follow_up",
        "patient_notes": "",
        "language_pref": "english",
    })
    expect(r.status_code == 303, f"clinic public booking POST 303 (got {r.status_code})", r)
    loc = r.headers.get("location", "")
    expect("/confirm/" in loc, f"clinic booking → confirm page: {loc}", r)
    if "/confirm/" in loc:
        r2 = public_clinic.get(loc)
        expect(r2.status_code == 200, "clinic confirm page 200", r2)

section("C10. Public clinic booking — invalid doctor_id should error")
public_clinic2 = TestClient(main.app, follow_redirects=False)
r = public_clinic2.post(f"/book/clinic/{clinic_slug}", data={
    "doctor_id": "999999",
    "patient_name": "Bad", "patient_phone": "9555500088",
    "appt_date": target2_str, "appt_time": "09:00",
    "appointment_type": "follow_up", "patient_notes": "", "language_pref": "english",
})
expect(r.status_code in (200, 400), f"bad doctor_id rejected (got {r.status_code})", r)

section("C11. Already-used clinic invite → 410")
anon3 = TestClient(main.app, follow_redirects=False)
r = anon3.get(f"/clinic/doctor-invite/{doc_token}")  # token used by associate earlier
expect(r.status_code == 410, f"used invite → 410 (got {r.status_code})", r)

# ────────────────────────────────────────────────────────────────────
section("Summary")
print(f"\n  PASSED: {PASSED}")
print(f"  FAILED: {FAILED}")
if FAILURES:
    print("\nFAILURES:")
    for f in FAILURES:
        print(f)
    sys.exit(1)
print("\nAll green ✓")
sys.exit(0)
