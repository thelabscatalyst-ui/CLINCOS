# ClinicOS — Claude Code Project Memory

## What This Project Is
ClinicOS is a SaaS appointment management system for independent doctors in Indian Tier 2/3 cities.
Priced at ₹299–499/month. WhatsApp-first, regional language support, mobile-friendly.

Target customer: Dr. Mehta in Nashik — a GP with no digital system, using a paper register.

---

## Three User Types
- **Doctor** — pays ₹299–499/month, manages appointments, sees calendar, gets reports
- **Patient** — books via public link, receives WhatsApp/SMS reminders, no login needed
- **Admin** — platform owner (me), manages all doctors, billing, platform stats

---

## Tech Stack (Do Not Change Without Asking)
| Layer | Tool | Notes |
|---|---|---|
| Backend | FastAPI (Python) | Main framework |
| Frontend | HTML + CSS + Vanilla JS | No React, no Vue |
| Templates | Jinja2 | Server-side rendering |
| Database (dev) | SQLite | File: `clinic.db` |
| Database (prod) | PostgreSQL | Railway.app managed |
| ORM | SQLAlchemy | Python classes, not raw SQL |
| Auth | JWT + Passlib (bcrypt) | Token-based login |
| WhatsApp/SMS | Twilio | Primary notification service |
| Payments | Razorpay | Indian UPI/card payments |
| Scheduler | APScheduler | Background reminder jobs |
| Deployment | Railway.app | Auto-deploy from GitHub |

---

## Known Compatibility Issues (Important)
- **bcrypt must stay at 4.0.1** — passlib 1.7.4 is incompatible with bcrypt 5.x (`__about__` removed). Do NOT upgrade bcrypt.
- **Starlette 1.0.0 TemplateResponse API changed** — `request` is now the FIRST argument: `templates.TemplateResponse(request, "template.html", context)`. Old signature with `{"request": request}` in the context dict causes `TypeError: cannot use 'tuple' as dict key`.
- **httpx required for TestClient** — install `httpx` separately for FastAPI test client to work.
- **Python 3.14 in use** — venv is at `/Users/apple/Desktop/ClinicOS/venv/`.

---

## How to Run
```bash
cd ~/Desktop/ClinicOS
source venv/bin/activate
uvicorn main:app --reload
```
Then open `http://127.0.0.1:8000`. If port 8000 is busy: `kill $(lsof -ti:8000)` then restart.

---

## Folder Structure
```
ClinicOS/
├── main.py                  # Entry point — registers all routers, starts app
├── config.py                # Settings loaded from .env (pydantic-settings)
├── requirements.txt         # All pip packages
├── .env                     # Secret keys — NEVER commit this
├── .gitignore               # Ignores .env, venv/, clinic.db, __pycache__
├── CLAUDE.md                # This file
│
├── database/
│   ├── __init__.py
│   ├── connection.py        # Engine, SessionLocal, Base, get_db(), create_tables()
│   └── models.py            # All 7 SQLAlchemy ORM models + enums
│
├── routers/
│   ├── __init__.py
│   ├── auth.py              # /register, /login, /logout (DONE)
│   ├── doctors.py           # /dashboard, /doctors/settings/* (DONE)
│   ├── appointments.py      # /appointments — CRUD (stub)
│   ├── patients.py          # /patients — list, profile (stub)
│   ├── public.py            # /book/{slug} — no auth needed (stub)
│   └── admin.py             # /admin — platform owner only (stub)
│
├── services/
│   ├── __init__.py
│   ├── auth_service.py      # hash_password, verify_password, create_access_token,
│   │                        # decode_token, get_current_doctor (DONE)
│   ├── appointment_service.py
│   ├── notification_service.py
│   ├── payment_service.py
│   └── scheduler_service.py
│
├── templates/
│   ├── base.html            # Master layout: navbar (active link aware)
│   ├── login.html           # Two-column: brand left, card right (DONE)
│   ├── register.html        # Two-column: brand left, card right (DONE)
│   ├── dashboard.html       # Stats, today's schedule, quick actions (DONE)
│   ├── settings.html        # Working hours, clinic profile, blocked dates (DONE)
│   ├── calendar.html        # (not yet built)
│   ├── patients.html        # (not yet built)
│   ├── patient_detail.html  # (not yet built)
│   ├── reports.html         # (not yet built)
│   ├── billing.html         # (not yet built)
│   ├── public_booking.html  # (not yet built)
│   └── admin/
│       ├── admin_dashboard.html
│       └── doctors_list.html
│
└── static/
    ├── css/
    │   └── main.css         # All styles — dark theme, glow, pop animations
    ├── js/
    └── img/
```

---

## Database Tables (Summary)
- **doctors** — id, name, email, phone, password_hash, specialization, clinic_name, clinic_address, city, languages, slug, is_active, plan_type, trial_ends_at, plan_expires_at, created_at
- **patients** — id, doctor_id, name, phone, language_pref, notes, visit_count, first_visit, last_visit, created_at
- **appointments** — id, doctor_id, patient_id, appointment_date, appointment_time, duration_mins, appointment_type, status, patient_notes, doctor_notes, reminder_24h_sent, reminder_2h_sent, created_at, booked_by
- **doctor_schedules** — id, doctor_id, day_of_week(0=Mon), start_time, end_time, slot_duration, max_patients, is_active
- **blocked_dates** — id, doctor_id, blocked_date, reason
- **subscriptions** — id, doctor_id, plan_name, amount(paise), payment_id, start_date, end_date, status
- **notifications_log** — id, appointment_id, type, channel, message_body, status, sent_at

---

## Auth & Session Pattern
- JWT stored in **HTTP-only cookie** named `access_token` (not localStorage)
- Cookie max-age: 24 hours, samesite=lax
- Protected routes use `Depends(get_current_doctor)` from `services/auth_service.py`
- Unauthenticated requests → 401 → caught by `main.py` exception handler → redirect to `/login`
- Doctor slug auto-generated on register: `name + city` → lowercase, hyphens (e.g. `dr-rajesh-mehta-nashik`)
- Trial set to 14 days from `datetime.utcnow()` on register

---

## Design System (main.css)
All pages use a **pitch-dark theme** with grey/white palette. Key rules:
- Background: `#080808`, Cards: `#111111`, Inputs: `#1a1a1a`
- Text: `#f0f0f0`, Muted: `#888`, Dim: `#555`
- No blue — accent color is white/light grey only
- **Every card and button has a soft white glow** (`--glow`, `--glow-hover` CSS vars)
- **Every card and button pops on hover** (`translateY + scale` via `--transition-pop`)
- Font: `Playfair Display` (headings/logo), `Inter` (body)
- Border radius: `--radius: 20px` (cards), `--radius-sm: 10px` (inputs/buttons)
- Auth pages: two-column grid — brand/logo left, form card right
- All `TemplateResponse` calls use new Starlette 1.0 signature (request as first arg)

### Component Classes
- `.card`, `.stat-card`, `.quick-card`, `.settings-card` — dark cards with glow + pop
- `.btn-primary` — white bg, dark text, full-width by default
- `.btn-sm` — overrides to `width: auto`, `margin-top: 0`, smaller padding
- `.btn-secondary` — dark bg, border, grey text
- `.badge--scheduled/completed/cancelled/no_show` — status pill colours
- `.input-sm` — compact dark input for dense forms (schedule grid, blocked dates)
- `.toggle` — CSS toggle switch (grey track → white when checked)
- `.page-title` — Playfair Display, flexbox row with `.page-date` inline
- `schedule-row--off` — dims `.schedule-day` and `.input-sm` only, NOT the toggle

### Key Design Rules to Maintain
- Buttons on pages are `btn-sm` (not full-width) unless it's a standalone form submit
- `<button>` elements that are not form submits MUST have `type="button"`
- Do NOT use `disabled` on inputs inside forms — use CSS class-based dimming instead
- Inline `flex:1/2` goes directly on `<input>` elements, not on `.form-group` wrappers

---

## Routes Built So Far
| Method | Path | Handler | Auth |
|---|---|---|---|
| GET | `/` | Redirect → `/login` | No |
| GET | `/register` | `auth.register_page` | No |
| POST | `/register` | `auth.register` | No |
| GET | `/login` | `auth.login_page` | No |
| POST | `/login` | `auth.login` | No |
| GET | `/logout` | `auth.logout` | No |
| GET | `/dashboard` | `doctors.dashboard` | Yes |
| GET | `/doctors/settings` | `doctors.settings_page` | Yes |
| POST | `/doctors/settings/schedule` | `doctors.save_schedule` | Yes |
| POST | `/doctors/settings/profile` | `doctors.save_profile` | Yes |
| POST | `/doctors/settings/block` | `doctors.add_blocked_date` | Yes |
| POST | `/doctors/settings/unblock/{id}` | `doctors.remove_blocked_date` | Yes |

---

## Coding Rules (Always Follow)
1. **Never store plain passwords** — always use `passlib` bcrypt hashing
2. **Never hardcode secrets** — all keys come from `.env` via `config.py`
3. **Always filter by doctor_id** — doctors must never see other doctors' data
4. **Validate inputs server-side** — never trust frontend data
5. **Rate limit public booking** — max 5 bookings per phone per 24h
6. **Keep routes thin** — business logic belongs in services/, not routers/
7. **One feature at a time** — build and test before moving to next feature
8. **TemplateResponse signature** — always `templates.TemplateResponse(request, "file.html", context)`
9. **bcrypt pinned to 4.0.1** — do not upgrade

---

## Subscription Plans
- **Free Trial** — 14 days, full access, no card needed
- **Basic** — ₹299/month, up to 30 appointments/day, reminders, public booking
- **Pro** — ₹499/month, unlimited appointments, two-way WhatsApp, analytics, export

---

## Build Order (Current Progress Tracker)

| # | Feature | Status |
|---|---|---|
| 1 | Project setup + virtual environment | ✅ Done |
| 2 | database/models.py — all 7 tables | ✅ Done |
| 3 | database/connection.py | ✅ Done |
| 4 | config.py + .env setup | ✅ Done |
| 5 | main.py — base FastAPI app | ✅ Done |
| 6 | auth — register + login + JWT | ✅ Done |
| 7 | Dashboard page (stats, today's schedule, quick actions) | ✅ Done |
| 8 | Schedule settings (working hours, slot duration, blocked dates) | ✅ Done |
| 9 | Appointment creation form (backend + frontend) | ⬜ Next |
| 10 | Calendar view | ⬜ Not started |
| 11 | Public booking page | ⬜ Not started |
| 12 | Slot availability logic (no double-booking) | ⬜ Not started |
| 13 | Patient profile pages | ⬜ Not started |
| 14 | WhatsApp/SMS notifications (Twilio) | ⬜ Not started |
| 15 | Background reminder scheduler (APScheduler) | ⬜ Not started |
| 16 | Two-way WhatsApp reply handling | ⬜ Not started |
| 17 | Razorpay payment integration | ⬜ Not started |
| 18 | Subscription plan gating | ⬜ Not started |
| 19 | Reports + analytics page | ⬜ Not started |
| 20 | Admin panel | ⬜ Not started |
| 21 | Deploy on Railway.app | ⬜ Not started |

---

## Key Business Rules to Always Enforce
- A slot is unavailable if: another appointment exists at same date+time for same doctor, OR the time is outside doctor's schedule hours, OR the date is in blocked_dates, OR max_patients for that shift is reached
- Reminders fire at: T-24h and T-2h before appointment_date + appointment_time
- No-show auto-trigger: if status not updated to 'completed' within 30 min after appointment end time, system flags it for doctor review
- Free trial: 14 days from created_at on doctors table
- Plan expiry check: run on every protected route — if plan_expires_at < today AND trial_ends_at < today, redirect to billing page

---

## Environment Variables Needed (.env file)
```
DATABASE_URL=sqlite:///./clinic.db
SECRET_KEY=your-jwt-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

RAZORPAY_KEY_ID=your-razorpay-key
RAZORPAY_KEY_SECRET=your-razorpay-secret
```

---

## What "Done" Means for Each Feature
A feature is only done when:
- [ ] Backend route works (tested in browser or Postman)
- [ ] Frontend page displays correctly on mobile screen size
- [ ] Data is correctly saved/retrieved from database (verified in DB Browser)
- [ ] No hardcoded values — everything comes from DB or .env
- [ ] Tested with wrong inputs (empty form, wrong password, double booking attempt)

---

## Session Startup Checklist
When starting a new Claude Code session, say:
> "Read CLAUDE.md. We are continuing ClinicOS. Last completed feature was [8 — Schedule Settings]. Today we are building [Feature 9 — Appointment creation form]."

---

*Last updated: 2026-04-22*
*Current phase: Core features — Features 1–8 complete, Feature 9 next*
