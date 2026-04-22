# ClinicOS — Claude Code Project Memory

## What This Project Is
ClinicOS is a SaaS appointment management system for independent doctors in Indian Tier 2/3 cities.
Priced at ₹299–499/month. WhatsApp-first, mobile-friendly, zero setup for the doctor.

Target customer: Dr. Mehta in Nashik — a GP with no digital system, currently using a paper register.

---

## Three User Types
- **Doctor** — pays ₹299–499/month, manages appointments, sees calendar, gets reports
- **Patient** — books via public link, receives WhatsApp/SMS confirmations + reminders, no login needed
- **Admin** — platform owner, manages all doctors, monitors billing and platform stats at `/admin`

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
| Auth | JWT + Passlib (bcrypt) | Token stored in HTTP-only cookie |
| WhatsApp/SMS | Twilio | Primary notification channel |
| Payments | Razorpay | Indian UPI/card payments |
| Scheduler | APScheduler | Background reminder jobs (every 15 min) |
| Deployment | Railway.app | Auto-deploy from GitHub |

---

## Known Compatibility Issues (Critical)
- **bcrypt must stay at 4.0.1** — passlib 1.7.4 is incompatible with bcrypt 5.x (`__about__` removed). Do NOT upgrade.
- **Starlette 1.0.0 TemplateResponse API** — `request` is now the FIRST positional argument: `templates.TemplateResponse(request, "template.html", context)`. The old signature with `{"request": request}` in the context dict raises `TypeError: cannot use 'tuple' as dict key`.
- **httpx required for TestClient** — install separately; FastAPI test client depends on it.
- **Python 3.14 in use** — venv at `/Users/apple/Desktop/ClinicOS/venv/`.
- **SQLite `connect_args`** — `{"check_same_thread": False}` applied only for SQLite URLs; PostgreSQL skips it automatically (handled in `database/connection.py`).

---

## How to Run Locally
```bash
cd ~/Desktop/ClinicOS
source venv/bin/activate
uvicorn main:app --reload
```
Open `http://127.0.0.1:8000`. If port is busy: `kill $(lsof -ti:8000)` then restart.

---

## Folder Structure
```
ClinicOS/
├── main.py                      # Entry point — routers, lifespan (scheduler start/stop)
├── config.py                    # Settings from .env via pydantic-settings
├── requirements.txt             # All pip packages (pinned)
├── Procfile                     # Railway: web: uvicorn main:app --host 0.0.0.0 --port $PORT
├── .env                         # Secret keys — NEVER commit
├── .gitignore
├── CLAUDE.md                    # This file
├── README.md                    # Public-facing project docs
│
├── database/
│   ├── connection.py            # Engine, SessionLocal, Base, get_db(), create_tables()
│   └── models.py                # 7 ORM models + enums (see Database Tables below)
│
├── routers/
│   ├── auth.py                  # /register, /login, /logout
│   ├── doctors.py               # /dashboard, /calendar, /reports, /billing, /doctors/settings/*
│   ├── appointments.py          # /appointments — full CRUD + edit + status update
│   ├── patients.py              # /patients — list, search, detail, notes
│   ├── public.py                # /book/{slug} — public booking (no auth, rate-limited)
│   └── admin.py                 # /admin — platform owner only
│
├── services/
│   ├── auth_service.py          # JWT auth + get_current_doctor + get_paying_doctor + get_admin_doctor
│   ├── appointment_service.py   # Slot availability, get_or_create_patient
│   ├── notification_service.py  # Twilio WhatsApp + SMS, confirmation + reminder sends
│   ├── payment_service.py       # Razorpay order create + HMAC signature verify
│   └── scheduler_service.py     # APScheduler — T-24h and T-2h reminder jobs
│
├── templates/
│   ├── base.html                # Master layout with active-link navbar
│   ├── login.html               # Two-column auth page
│   ├── register.html            # Two-column auth page
│   ├── dashboard.html           # Stats, today's schedule, quick actions
│   ├── settings.html            # Working hours, clinic profile, blocked dates, subscription
│   ├── appointments.html        # Daily appointment list with date nav
│   ├── appointment_new.html     # New appointment form with AJAX slot loading
│   ├── appointment_detail.html  # Detail view + status update + doctor notes
│   ├── appointment_edit.html    # Edit/reschedule form
│   ├── calendar.html            # Monthly calendar view
│   ├── patients.html            # Patient list with search
│   ├── patient_detail.html      # Patient profile, history, notes
│   ├── reports.html             # Analytics: charts, top patients, visit types
│   ├── billing.html             # Plan cards + Razorpay checkout
│   ├── public_booking.html      # Patient-facing booking form (no navbar)
│   ├── public_confirm.html      # Booking confirmation + Google Calendar link
│   └── admin/
│       ├── admin_dashboard.html # Platform stats
│       └── doctors_list.html    # All registered doctors table
│
└── static/
    ├── css/main.css             # All styles — dark theme, glow, pop, responsive
    ├── js/
    └── img/
```

---

## Database Tables
| Table | Key Columns |
|---|---|
| **doctors** | id, name, email, phone, password_hash, specialization, clinic_name, clinic_address, city, languages, slug, is_active, plan_type, trial_ends_at, plan_expires_at, created_at |
| **patients** | id, doctor_id, name, phone, language_pref, notes, visit_count, first_visit, last_visit, created_at |
| **appointments** | id, doctor_id, patient_id, appointment_date, appointment_time, duration_mins, appointment_type, status, patient_notes, doctor_notes, reminder_24h_sent, reminder_2h_sent, booked_by, created_at |
| **doctor_schedules** | id, doctor_id, day_of_week (0=Mon), start_time, end_time, slot_duration, max_patients, is_active |
| **blocked_dates** | id, doctor_id, blocked_date, reason |
| **subscriptions** | id, doctor_id, plan_name, amount (paise), payment_id, start_date, end_date, status |
| **notifications_log** | id, appointment_id, type, channel, message_body, status, sent_at |

---

## Auth & Plan Gating Pattern
- JWT stored in **HTTP-only cookie** `access_token` (not localStorage), max-age 24h, samesite=lax
- `get_current_doctor` — verifies JWT, returns doctor or raises 401 → redirects to `/login`
- `get_paying_doctor` — wraps `get_current_doctor`, raises `PlanExpired` if trial + plan both lapsed → redirects to `/billing`
- `get_admin_doctor` — wraps `get_current_doctor`, checks `doctor.email == settings.ADMIN_EMAIL` → 403 otherwise
- All doctor-facing routes use `Depends(get_paying_doctor)` **except** `/billing/*` (uses `get_current_doctor`) and `/admin/*` (uses `get_admin_doctor`)
- `PlanExpired` exception handled in `main.py` → `RedirectResponse("/billing")`
- Doctor slug auto-generated on register: `name + city` → lowercase, hyphens (e.g. `dr-rajesh-mehta-nashik`)
- Trial: 14 days from `datetime.utcnow()` on register

---

## Complete Route Table
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | No | Redirect → `/login` |
| GET/POST | `/register` | No | Doctor registration |
| GET/POST | `/login` | No | Doctor login |
| GET | `/logout` | No | Clear cookie |
| GET | `/dashboard` | Plan | Stats + today's schedule |
| GET | `/calendar` | Plan | Monthly calendar |
| GET | `/reports` | Plan | Analytics + charts |
| GET | `/billing` | Auth | Plan cards + Razorpay |
| POST | `/billing/create-order` | Auth | Create Razorpay order (JSON) |
| POST | `/billing/verify` | Auth | Verify payment + activate plan |
| GET/POST | `/doctors/settings` | Plan | Working hours, profile, blocked dates, subscription |
| POST | `/doctors/settings/schedule` | Plan | Save working hours |
| POST | `/doctors/settings/profile` | Plan | Save clinic profile |
| POST | `/doctors/settings/block` | Plan | Add blocked date |
| POST | `/doctors/settings/unblock/{id}` | Plan | Remove blocked date |
| GET | `/appointments` | Plan | Daily appointment list |
| GET | `/appointments/slots` | Plan | Available slots JSON (AJAX) |
| GET | `/appointments/new` | Plan | New appointment form |
| POST | `/appointments` | Plan | Create appointment |
| GET | `/appointments/{id}` | Plan | Appointment detail |
| POST | `/appointments/{id}/status` | Plan | Update status + doctor notes |
| GET | `/appointments/{id}/edit` | Plan | Edit/reschedule form |
| POST | `/appointments/{id}/edit` | Plan | Save rescheduled appointment |
| GET | `/patients` | Plan | Patient list + search |
| GET | `/patients/{id}` | Plan | Patient profile + history |
| POST | `/patients/{id}/notes` | Plan | Update patient notes |
| GET | `/book/{slug}` | No | Public booking form |
| GET | `/book/{slug}/slots` | No | Public slots JSON (AJAX) |
| POST | `/book/{slug}` | No | Submit booking (rate-limited) |
| GET | `/book/{slug}/confirm/{id}` | No | Booking confirmation |
| GET | `/admin` | Admin | Redirect → `/admin/dashboard` |
| GET | `/admin/dashboard` | Admin | Platform stats |
| GET | `/admin/doctors` | Admin | All doctors table |

Auth column: **No** = public, **Auth** = JWT only, **Plan** = JWT + active trial/plan, **Admin** = platform owner email

---

## Design System (main.css)
All pages use a **pitch-dark theme** with white/grey palette:
- Background: `#080808`, Cards: `#111111`, Inputs: `#1a1a1a`
- Text: `#f0f0f0`, Muted: `#888`, Dim: `#555`, Border: `rgba(255,255,255,0.06)`
- No colour accents — white/grey only throughout
- Every card and button: soft white glow (`--glow`) + `translateY + scale` pop on hover (`--transition-pop`)
- Fonts: `Playfair Display` (headings, logo, page titles) + `Inter` (body)
- Border radius: `--radius: 20px` (cards), `--radius-sm: 10px` (inputs, buttons, badges)

### Key CSS Rules
- Page buttons are always `btn-sm` (not full-width) unless it's a standalone auth form submit
- `<button>` that is NOT a form submit MUST have `type="button"` to prevent accidental form submission
- Never use `disabled` on inputs inside active forms — use CSS class-based dimming (e.g. `schedule-row--off`)
- Inline flex sizing (`flex: 1`) goes on `<input>` elements directly, not `.form-group` wrappers
- Select dropdowns use `appearance: none` + custom SVG arrow background-image

---

## Notification Flow
1. Doctor or patient books appointment → `notify_appointment_confirmed()` fires immediately
2. Sends WhatsApp via Twilio; falls back to SMS if `TWILIO_SMS_FROM` is set
3. Every send (success or failure) is logged to `notifications_log` table
4. APScheduler runs `_check_reminders()` every 15 minutes:
   - Queries appointments where `reminder_24h_sent=False` within 23–25h window → sends, sets flag
   - Queries appointments where `reminder_2h_sent=False` within 90–150min window → sends, sets flag
5. All notification functions are wrapped in `try/except` in routers — a Twilio failure never blocks a booking

---

## Payment Flow
1. Doctor clicks Subscribe → JS calls `POST /billing/create-order?plan=basic|pro`
2. Backend calls `razorpay.order.create()` → returns `{order_id, amount, currency, key_id}`
3. Frontend opens Razorpay checkout popup (loaded from CDN)
4. On payment success, Razorpay returns `{payment_id, order_id, signature}`
5. Frontend POSTs these to `POST /billing/verify`
6. Backend verifies HMAC-SHA256 signature → on match: creates `Subscription` row, sets `doctor.plan_expires_at = now + 30 days`, updates `doctor.plan_type`
7. Redirects to `/billing?success=1`

---

## Subscription Plans
| Plan | Price | Limits |
|---|---|---|
| Free Trial | 14 days | Full access |
| Basic | ₹299/month | 30 appointments/day |
| Pro | ₹499/month | Unlimited appointments |

---

## Coding Rules (Always Follow)
1. **Never store plain passwords** — always `passlib` bcrypt hashing
2. **Never hardcode secrets** — all keys from `.env` via `config.py`
3. **Always filter by `doctor_id`** — doctors must never see other doctors' data
4. **Validate inputs server-side** — never trust frontend data
5. **Rate limit public booking** — max 5 bookings per phone per 24h (enforced in `routers/public.py`)
6. **Keep routes thin** — business logic in `services/`, not `routers/`
7. **TemplateResponse signature** — always `templates.TemplateResponse(request, "file.html", context)`
8. **bcrypt pinned to 4.0.1** — do not upgrade
9. **Notifications never block bookings** — always wrapped in `try/except` at call sites

---

## Environment Variables (.env)
```
# Core
DATABASE_URL=sqlite:///./clinic.db        # dev; switch to PostgreSQL URL on Railway
SECRET_KEY=your-random-jwt-secret-here    # generate: python -c "import secrets; print(secrets.token_hex(32))"
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Twilio (WhatsApp/SMS notifications)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886   # sandbox; replace with approved number for prod
TWILIO_SMS_FROM=                             # optional Twilio SMS number e.g. +1XXXXXXXXXX

# Razorpay (payments)
RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXXXXXX
RAZORPAY_KEY_SECRET=XXXXXXXXXXXXXXXXXXXXXXXX

# Admin
ADMIN_EMAIL=your-email@example.com          # must match the email used to register the admin doctor account
```

---

## Build Status
| # | Feature | Status |
|---|---|---|
| 1 | Project setup + virtual environment | ✅ Done |
| 2 | Database models — all 7 tables | ✅ Done |
| 3 | Database connection + migrations | ✅ Done |
| 4 | config.py + .env | ✅ Done |
| 5 | main.py — FastAPI app + lifespan | ✅ Done |
| 6 | Auth — register + login + JWT cookie | ✅ Done |
| 7 | Dashboard — stats, today's schedule, quick actions | ✅ Done |
| 8 | Settings — working hours, profile, blocked dates | ✅ Done |
| 9 | Appointments — create, list, detail, status update | ✅ Done |
| 10 | Calendar view — monthly grid | ✅ Done |
| 11 | Public booking page `/book/{slug}` | ✅ Done |
| 12 | Slot availability logic — no double-booking | ✅ Done |
| 13 | Patient profiles — list, search, detail, notes | ✅ Done |
| 14 | WhatsApp/SMS notifications (Twilio) | ✅ Done |
| 15 | Background reminder scheduler (APScheduler) | ✅ Done |
| 16 | Appointment edit / reschedule | ✅ Done |
| 17 | Reports + analytics page | ✅ Done |
| 18 | Razorpay payment integration | ✅ Done |
| 19 | Subscription plan gating | ✅ Done |
| 20 | Subscription section in Settings | ✅ Done |
| 21 | Admin panel — dashboard + doctors list | ✅ Done |
| 22 | Deploy on Railway.app | ⬜ Next |

---

## Session Startup Checklist
When starting a new Claude Code session:
> "Read CLAUDE.md. We are continuing ClinicOS. All features 1–21 are complete. Today we are working on [describe task]."

---

*Last updated: 2026-04-22*
*Current phase: Production-ready — deploying to Railway.app next*
