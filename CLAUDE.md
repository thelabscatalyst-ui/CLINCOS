# ClinicOS — Claude Code Project Memory

## What This Project Is
ClinicOS is a SaaS appointment management system for independent doctors in Indian Tier 2/3 cities.
Priced at ₹399/month (Solo plan). WhatsApp-first, mobile-friendly, zero setup for the doctor.

Target customer: Dr. Mehta in Nashik — a GP with no digital system, currently using a paper register.

---

## Three User Types
- **Doctor** — pays ₹399/month, manages appointments, sees calendar, gets reports
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
│   ├── connection.py            # Engine, SessionLocal, Base, get_db(), create_tables() + _run_migrations()
│   └── models.py                # ORM models + enums (see Database Tables below)
│
├── routers/
│   ├── auth.py                  # /register, /login, /logout
│   ├── doctors.py               # /dashboard, /calendar, /reports, /billing, /doctors/settings/*, /pin-prompt
│   ├── appointments.py          # /appointments — full CRUD + edit + status update + walk-in + queue actions
│   ├── visits.py                # /visits/* — queue state machine + public display screen
│   ├── patients.py              # /patients — list, search, detail, notes
│   ├── public.py                # /book/{slug} — public booking (no auth, rate-limited)
│   └── admin.py                 # /admin — platform owner only
│
├── services/
│   ├── auth_service.py          # JWT auth + PIN session auth + all get_*_doctor helpers
│   ├── appointment_service.py   # Slot availability (filter_past=True for today), get_or_create_patient
│   ├── visit_service.py         # Queue logic — check_in, call_next, done_and_call_next, close_visit, etc.
│   ├── notification_service.py  # Twilio WhatsApp + SMS, confirmation + reminder sends
│   ├── payment_service.py       # Razorpay order create + HMAC signature verify
│   └── scheduler_service.py     # APScheduler — T-24h and T-2h reminder jobs
│
├── templates/
│   ├── base.html                # Master layout — navbar (Settings icon + theme toggle + logout), dock, PIN overlay
│   ├── login.html               # Two-column auth page
│   ├── register.html            # Two-column auth page
│   ├── dashboard.html           # Stats row + today's schedule card (numbered, clickable rows)
│   ├── settings.html            # Working hours, clinic profile, blocked dates, subscription, PIN protection
│   ├── appointments.html        # Queue section (today) + Schedule split (Walk-ins | Appointments)
│   ├── appointment_new.html     # New appointment form with AJAX slot loading + booking channel selector
│   ├── appointment_detail.html  # Detail view + status update + doctor notes
│   ├── appointment_edit.html    # Edit/reschedule form
│   ├── calendar.html            # Monthly calendar view
│   ├── patients.html            # Patient list with search
│   ├── patient_detail.html      # Patient profile, history, notes
│   ├── reports.html             # Analytics: charts, top patients, visit types
│   ├── billing.html             # Solo plan card + Razorpay checkout
│   ├── queue_display.html       # Public TV display screen /queue/{slug}
│   ├── visits_today.html        # Legacy visits page (redirects to /appointments)
│   ├── public_booking.html      # Patient-facing booking form (no navbar)
│   ├── public_confirm.html      # Booking confirmation + Google Calendar link
│   └── admin/
│       ├── admin_dashboard.html # Platform stats
│       └── doctors_list.html    # All registered doctors table
│
└── static/
    ├── css/main.css             # All styles — dark/light theme, glow, pop, responsive (currently v55)
    ├── js/
    └── img/
```

---

## Database Tables
| Table | Key Columns |
|---|---|
| **doctors** | id, name, email, phone, password_hash, pin_hash, specialization, clinic_name, clinic_address, city, languages, slug, is_active, plan_type, trial_ends_at, plan_expires_at, doctor_mode, walkin_policy, created_at |
| **patients** | id, doctor_id, name, phone, language_pref, notes, visit_count, first_visit, last_visit, created_at |
| **appointments** | id, doctor_id, patient_id, appointment_date, appointment_time, duration_mins, appointment_type, status, patient_notes, doctor_notes, reminder_24h_sent, reminder_2h_sent, booked_by, visit_id, arrival_status, created_at |
| **visits** | id, doctor_id, patient_id, clinic_id, appointment_id, visit_date, token_number, queue_position, status, source, is_emergency, notes, check_in_time, call_time, done_time, created_by |
| **bills** | id, visit_id, doctor_id, clinic_id, patient_id, subtotal, discount, gst_amount, total, paid_amount, payment_mode, paid_at, notes, created_by |
| **bill_items** | id, bill_id, description, quantity, unit_price, total |
| **price_catalog** | id, doctor_id, name, default_price, is_active |
| **expenses** | id, doctor_id, clinic_id, amount, category, description, expense_date, created_by |
| **recurring_expenses** | id, doctor_id, clinic_id, amount, category, description, frequency, next_due, is_active |
| **doctor_schedules** | id, doctor_id, day_of_week (0=Mon), start_time, end_time, slot_duration, max_patients, is_active |
| **blocked_dates** | id, doctor_id, blocked_date, reason |
| **subscriptions** | id, doctor_id, plan_name, amount (paise), payment_id, start_date, end_date, status |
| **notifications_log** | id, appointment_id, type, channel, message_body, status, sent_at |

`pin_hash`, `visit_id`, `arrival_status`, `doctor_mode`, `walkin_policy` added via `_run_migrations()` on startup.

---

## Visit / Queue System (Phase 3)

### Visit State Machine
```
WAITING → SERVING → BILLING_PENDING → DONE
                 ↘ CANCELLED
         ↘ SKIPPED (back to end of WAITING queue)
         ↘ NO_SHOW
```

### Key Rules
- `token_number` — monotonic per doctor per day (UniqueConstraint on doctor_id + visit_date + token_number)
- `queue_position` — mutable, reordered by skip/emergency/move actions
- Walk-in auto-check-in: `vs.check_in()` called inside walk-in POST handler immediately after appointment creation
- Auto-complete appointment: `_auto_complete_appointment()` called before `done_and_call_next()` — marks linked appointment as `completed`
- `visit_map` dict (appt_id → Visit) passed to appointments template for live queue status on rows
- `eff_status` computed in Jinja from visit state, falling back to appointment status

### Visit Service Functions (`services/visit_service.py`)
- `check_in()` — assigns token, sets queue_position per walkin_policy
- `call_next()` — promotes next WAITING visit to SERVING
- `done_and_call_next()` — marks visit BILLING_PENDING, auto-calls next
- `close_visit()` — marks DONE with bill_id
- `skip_visit()` — moves to end of queue
- `promote_emergency()` — jumps to front
- `cancel_visit()` — marks CANCELLED
- `move_visit()` — manual reorder
- `get_today_visits()` — returns (serving, waiting, closed)
- `get_queue_status_json()` — compact JSON for TV/public polling

---

## Appointments Page Layout

### Queue Section (today only, `.queue-section` card)
- Now Serving block + Waiting list + Billing Pending block
- Action buttons per visit state (Call, Done, Free, Skip, Emergency, Cancel)
- Empty state when queue is empty

### Schedule Section (`.schedule-section` card)
- Header row: "SCHEDULE" label + date nav + search — all on one line, separated by full-width border below
- Two-column split grid (`.appt-split-grid`): **Walk-ins** (left) | **Appointments** (right)
- Vertical divider line between columns
- Each column has label + count pill header (no border under column headers)
- Rows are clickable (whole card → appointment detail), no View button
- Row structure: `#token | time-pill | [Check In if applicable]` left, `type · age · gender · Name + tags` right

---

## Auth & Plan Gating Pattern
- JWT stored in **HTTP-only cookie** `access_token` (not localStorage), max-age 24h, samesite=lax
- `get_current_doctor` — verifies JWT, returns doctor or raises 401 → redirects to `/login`
- `get_paying_doctor` — wraps `get_current_doctor`, raises `PlanExpired` if trial + plan both lapsed → redirects to `/billing`
- `get_admin_doctor` — wraps `get_current_doctor`, checks `doctor.email == settings.ADMIN_EMAIL` → 403 otherwise
- `require_pin` — wraps `get_paying_doctor`; sets `request.state.pin_required = True` on GET if PIN not unlocked; raises `PinRequired` on POST
- `require_pin_auth` — same as `require_pin` but wraps `get_current_doctor` (used for billing routes)
- PIN session stored in HTTP-only cookie `pin_session` (30-minute JWT with `pin_ok: True`)
- `PlanExpired` and `PinRequired` exceptions handled in `main.py`
- Doctor slug auto-generated on register: `name + city` → lowercase, hyphens (e.g. `dr-rajesh-mehta-nashik`)
- Trial: 14 days from `datetime.utcnow()` on register

### PIN-protected routes
- `GET/POST /doctors/settings` — requires PIN
- `GET /reports` — requires PIN
- `GET /billing` and all `/billing/*` — requires PIN (auth only, not plan-gated)
- `GET /patients/{id}` — requires PIN

### PIN blur overlay (base.html)
When `pin_required=True` is in template context, `body` gets class `pin-active`:
- `.pin-active .navbar` and `.pin-active .main-content` get `filter: blur(14px) brightness(0.55); pointer-events: none`
- A `.pin-overlay` with a centered `.pin-dialog` (lock icon + PIN input + Unlock button) is shown
- Back arrow `‹` at top-left of overlay for navigation
- On wrong PIN: redirect to same page with `?pin_error=1` query param → overlay shows "Incorrect PIN"

---

## Navbar & Dock

### Navbar (base.html)
- Left: "ClinicOS" brand link → `/dashboard`
- Right: Settings icon (grey, `var(--muted)`) + Theme toggle (moon/sun) + Logout (red power icon)
- No nav links in navbar — navigation is handled entirely by the dock

### Dock (base.html)
- Auto-hides to left edge, reveals on mouse hover within 12px of left edge
- 5 items: Dashboard · Today's Queue · Patients · Calendar · Reports
- Active item highlighted with `dock-item--active`
- Settings and Appointments removed from dock (Settings is in navbar, Appointments merged into queue)

---

## BookedBy Enum Values
```python
class BookedBy(str, enum.Enum):
    doctor       = "doctor"       # doctor booked manually
    patient      = "patient"      # patient booked via public /book/{slug}
    staff_shared = "staff_shared" # receptionist using doctor's shared login
    walk_in      = "walk_in"      # quick walk-in from appointments page
```

---

## Walk-in Booking
- `POST /appointments/walkin` — books for `datetime.now()`, sets `booked_by=walk_in`, calls `vs.check_in()` immediately
- Accessible from the appointments page (today only) via a slide-down panel
- Walk-in auto-enters the queue on creation — no separate check-in step needed
- Appears in Walk-ins column of schedule, and in the live queue section

---

## Slot Availability
- `get_available_slots(doctor_id, appt_date, db, filter_past=True)` — filters past slots for today by default
- All doctor-side booking routes use `filter_past=True` — past time slots on today's date are hidden
- Edit/reschedule route uses `filter_past=False` — allows re-booking near current time when editing
- Public booking always uses `filter_past=True`

---

## Complete Route Table
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | No | Redirect → `/login` |
| GET/POST | `/register` | No | Doctor registration |
| GET/POST | `/login` | No | Doctor login |
| GET | `/logout` | No | Clear cookie |
| GET | `/dashboard` | Plan | Stats + today's schedule + quick actions |
| GET | `/calendar` | Plan | Monthly calendar |
| GET | `/reports` | PIN | Analytics + charts |
| GET | `/billing` | PIN-Auth | Plan cards + Razorpay |
| POST | `/billing/create-order` | PIN-Auth | Create Razorpay order (JSON) |
| POST | `/billing/verify` | PIN-Auth | Verify payment + activate plan |
| GET/POST | `/doctors/settings` | PIN | Working hours, profile, blocked dates, PIN, subscription |
| POST | `/doctors/settings/schedule` | PIN | Save working hours |
| POST | `/doctors/settings/profile` | PIN | Save clinic profile |
| POST | `/doctors/settings/block` | PIN | Add blocked date |
| POST | `/doctors/settings/unblock/{id}` | PIN | Remove blocked date |
| POST | `/doctors/settings/pin` | PIN | Set / change / remove PIN |
| GET | `/pin-prompt` | No | Redirects to `next` param |
| POST | `/pin-prompt` | No | Verify PIN → set pin_session cookie |
| GET | `/appointments` | Plan | Queue + split schedule (walk-ins / booked) |
| GET | `/appointments/slots` | Plan | Available slots JSON (AJAX, filter_past=True) |
| GET | `/appointments/new` | Plan | New appointment form |
| POST | `/appointments` | Plan | Create appointment |
| POST | `/appointments/walkin` | Plan | Quick walk-in booking (auto check-in to queue) |
| GET | `/appointments/{id}` | Plan | Appointment detail |
| POST | `/appointments/{id}/status` | Plan | Update status + doctor notes |
| GET | `/appointments/{id}/edit` | Plan | Edit/reschedule form |
| POST | `/appointments/{id}/edit` | Plan | Save rescheduled appointment |
| GET | `/visits/today` | Plan | Redirect → `/appointments` (301) |
| POST | `/visits/check-in` | Plan | Check in walk-in patient |
| POST | `/visits/check-in-appt/{id}` | Plan | Check in from existing appointment |
| POST | `/visits/{id}/call` | Plan | Manually call a waiting visit |
| POST | `/visits/{id}/done` | Plan | Mark serving → billing_pending, auto-call next |
| POST | `/visits/{id}/close-free` | Plan | Close visit with zero charge |
| POST | `/visits/{id}/skip` | Plan | Skip to end of queue |
| POST | `/visits/{id}/emergency` | Plan | Promote to top of queue |
| POST | `/visits/{id}/cancel` | Plan | Cancel visit |
| POST | `/visits/{id}/move` | Plan | Manually reorder queue position |
| GET | `/visits/queue-status` | Plan | JSON snapshot for polling |
| GET | `/queue/{slug}` | No | Public TV display screen |
| GET | `/queue/{slug}/status` | No | Public queue JSON for polling |
| GET | `/patients` | Plan | Patient list + search |
| GET | `/patients/{id}` | PIN | Patient profile + history |
| POST | `/patients/{id}/edit` | Plan | Update patient name + phone |
| POST | `/patients/{id}/notes` | Plan | Update patient notes |
| POST | `/patients/{id}/delete` | PIN | Delete patient + all appointments |
| GET | `/book/{slug}` | No | Public booking form |
| GET | `/book/{slug}/slots` | No | Public slots JSON (AJAX) |
| POST | `/book/{slug}` | No | Submit booking (rate-limited) |
| GET | `/book/{slug}/confirm/{id}` | No | Booking confirmation |
| GET | `/admin` | Admin | Redirect → `/admin/dashboard` |
| GET | `/admin/dashboard` | Admin | Platform stats |
| GET | `/admin/doctors` | Admin | All doctors table |

Auth column: **No** = public, **Auth** = JWT only, **Plan** = JWT + active trial/plan, **PIN** = Plan + PIN unlock, **PIN-Auth** = JWT + PIN unlock, **Admin** = platform owner email

---

## Design System (main.css — currently v113)
Supports **dark** (default) and **light** themes. Theme toggled via navbar button, saved to `localStorage`, applied to `<html>` element (`html.light` class).

**Palette: warm sepia/parchment** — NOT neutral grey. Both themes share a brown-amber aesthetic.
The authoritative token reference is `docs/design-tokens.md`. Always read that file before touching CSS or templates.

### Dark theme (default — `:root`)
- Background: `#1a1612`, Cards: `#211d18`, Inputs: `#302b25`
- Text: `#ede8e2`, Muted: `#9a8f85`, Dim: `#5e5650`, Border: `#3d3630`
- Navbar/Dock bg: `#2e1e0c` (always dark brown, both themes)

### Light theme (`html.light`)
- Background: `#ede7de`, Cards: `#e4ddd4`, Inputs: `#d2cabf`
- Text: `#1a1410`, Muted: `#6b5f55`, Dim: `#a89e94`, Border: `#c2a98a`
- Navbar/Dock bg: `#2e1e0c` (always dark brown, both themes)

### Common
- Warm sepia/parchment palette throughout — no cold greys or pure white/black
- Every card and button: soft glow (`--glow`) + `translateY + scale` pop on hover (`--transition-pop`)
- Fonts: `Playfair Display` (headings, logo, page titles) + `Inter` (body)
- Border radius: `--radius: 20px` (cards), `--radius-sm: 10px` (inputs, buttons, badges)
- Layout: `.main-content { padding: 32px 24px; }` — no max-width, full screen width, equal side gaps

### Key CSS Rules
- Page buttons are always `btn-sm` (not full-width) unless it's a standalone auth form submit
- `<button>` that is NOT a form submit MUST have `type="button"` to prevent accidental form submission
- Never use `disabled` on inputs inside active forms — use CSS class-based dimming (e.g. `schedule-row--off`)
- Inline flex sizing (`flex: 1`) goes on `<input>` elements directly, not `.form-group` wrappers
- Select dropdowns use `appearance: none` + custom SVG arrow background-image
- `.btn` has `box-sizing: border-box`, `line-height: 1`, `-webkit-appearance: none` to normalise `<button>` vs `<a>` sizing

### Appointment Row Structure
```
.appt-row (flex, space-between, clickable via onclick)
  .appt-left
    .appt-token-num   (#1, #2 — Playfair Display, bold)
    .appt-left-divider (1px vertical line)
    .appt-time        (time pill — border, 8px radius, 5px 11px padding)
    [Check In button if applicable]
  .appt-right
    .appt-patient
      .appt-name-line  (type · age · gender · Name — all 13px)
      .appt-tags       (status badge + channel badge, right-aligned)
```

### Badge Channel Classes
- `badge-channel--walkin` (gold)
- `badge-channel--staff` (purple)
- `badge-channel--doctor` (green `#22c55e`)
- `badge-channel--patient` (grey `#a0a0a0`)
- `badge-channel--scheduled`, `--completed`, `--cancelled`, `--no_show`
- `badge-channel--in_queue`, `--serving`, `--billing_pending`, `--emergency`

### Queue & Schedule Cards
- `.queue-section` and `.schedule-section`: `bg-2, border, border-radius: 20px, padding: 20px 24px, box-shadow: glow`
- `.schedule-section-header`: flex row with "SCHEDULE" label + date nav + search, `border-bottom` divider
- `.appt-split-grid`: CSS grid `1fr 1px 1fr`, Walk-ins left, Appointments right, `.appt-col-divider` between

---

## Notification Flow
1. Doctor or patient books appointment → `notify_appointment_confirmed()` fires immediately
2. Sends WhatsApp via Twilio; falls back to SMS if `TWILIO_SMS_FROM` is set
3. Every send (success or failure) is logged to `notifications_log` table
4. APScheduler runs `_check_reminders()` every 15 minutes:
   - Queries appointments where `reminder_24h_sent=False` within 23–25h window → sends, sets flag
   - Queries appointments where `reminder_2h_sent=False` within 90–150min window → sends, sets flag
5. All notification functions are wrapped in `try/except` in routers — a Twilio failure never blocks a booking
6. Walk-in bookings (`booked_by=walk_in`) skip the confirmation notification

---

## Payment Flow
1. Doctor clicks Subscribe → JS calls `POST /billing/create-order?plan=solo|basic|pro`
2. Backend calls `razorpay.order.create()` → returns `{order_id, amount, currency, key_id}`
3. Frontend opens Razorpay checkout popup (loaded from CDN)
4. On payment success, Razorpay returns `{payment_id, order_id, signature}`
5. Frontend POSTs these to `POST /billing/verify`
6. Backend verifies HMAC-SHA256 signature → on match: creates `Subscription` row, sets `doctor.plan_expires_at = now + 30 days`, updates `doctor.plan_type`
7. Redirects to `/billing?success=1`

---

## Subscription Plans
| Plan | Price | Notes |
|---|---|---|
| Free Trial | 14 days | Full access |
| Solo | ₹399/month | Primary plan for individual doctors |
| Basic | ₹299/month | Legacy — 30 appointments/day |
| Pro | ₹499/month | Legacy — Unlimited appointments |

PLAN_AMOUNTS in `payment_service.py`: `solo=39900, basic=29900, pro=49900` (paise).

---

## Reports — Completion Rate Fix
`past_total` (denominator for completion/no-show rates) counts all appointments with status `completed` or `no_show` across all dates. It does NOT filter by `appointment_date < today` — that caused 0% rates when completions were from today.

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
10. **Dashboard greeting** — use `datetime.now().hour` (not `date.today()`) for time-aware Good Morning/Afternoon/Evening
11. **Slot filter** — use `filter_past=True` for all new appointment creation; `filter_past=False` only for edit/reschedule

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
| 22 | PIN protection for billing/reports/settings/patients (blur overlay) | ✅ Done |
| 23 | Walk-in quick booking | ✅ Done |
| 24 | Solo plan (₹399) + BookedBy enum extensions | ✅ Done |
| 25 | Dark/light theme toggle in navbar | ✅ Done |
| 26 | Full-screen layout (no max-width, equal side gaps) | ✅ Done |
| 27 | Reports completion/no-show rate bug fix | ✅ Done |
| 28 | Phase 2: Clinic schema — Clinic, ClinicDoctor, Staff, StaffInvite tables | ✅ Done |
| 29 | Phase 2: Staff login (receptionist/manager JWT via /login) | ✅ Done |
| 30 | Phase 2: Staff invite flow (email one-time link + accept page) | ✅ Done |
| 31 | Phase 2: Reception workspace (/clinic/reception — doctor dropdown, appt list) | ✅ Done |
| 32 | Phase 2: Clinic admin dashboard (/clinic/admin — aggregated stats, staff list) | ✅ Done |
| 33 | Phase 2: Unified clinic public booking (/book/clinic/{slug}) | ✅ Done |
| 34 | Phase 2: Clinic plan billing (₹1,499/month, Razorpay + clinic.plan_expires_at) | ✅ Done |
| 35 | Remove Patient — PIN-gated delete (patient + appointments) | ✅ Done |
| 36 | Edit Patient — modal to update name + phone | ✅ Done |
| 37 | Pre-fill booking from patient profile (name, phone, last-seen doctor) | ✅ Done |
| 38 | Booking channel badges — Doctor / Patient / Walk-in / Reception | ✅ Done |
| 39 | Calendar today ring fix — light theme dark border + glow | ✅ Done |
| 40 | Doctor's Notes textarea — vertical-only resize | ✅ Done |
| 41 | New Appointment split layout — form left, ClinicOS branding panel right | ✅ Done |
| 42 | PIN gate extended to patient detail page | ✅ Done |
| 43 | Phase 3: Visit/queue models — Visit, Bill, BillItem, PriceCatalog, Expense tables | ✅ Done |
| 44 | Phase 3: visit_service — full queue state machine | ✅ Done |
| 45 | Phase 3: Queue merged into /appointments — live queue + split schedule | ✅ Done |
| 46 | Phase 3: Walk-in auto check-in to queue on creation | ✅ Done |
| 47 | Phase 3: Auto-complete appointment when visit marked done | ✅ Done |
| 48 | Navbar stripped — Settings icon + theme + logout only | ✅ Done |
| 49 | Dock cleaned — 5 items (Dashboard, Queue, Patients, Calendar, Reports) | ✅ Done |
| 50 | Appointment rows — clickable cards, token numbers, time pill, no View button | ✅ Done |
| 51 | Dashboard Today's Schedule — numbered rows, clickable, in schedule-section card | ✅ Done |
| 52 | Past time slots hidden when booking for today | ✅ Done |
| 53 | Phase 3.3: Billing on close — bill modal, price catalog, payment recording | ⬜ Next |
| 54 | Phase 3.4: Income dashboard — daily/monthly revenue + expense tracker | ⬜ Planned |
| 55 | Deploy on Railway.app | ⬜ Planned |

---

## Patient Page — PIN Protection Note
`GET /patients/{id}` uses `require_pin` (not `get_paying_doctor`) so the blur overlay renders when PIN is set. The `pin_required` flag is passed explicitly in the template context. `_pin_parent_path` in `auth_service.py` maps `/patients/{id}/delete` → `/patients/{id}` for the PIN redirect.

## New Appointment Split Layout
`appointment_new.html` uses `.appt-new-split` (CSS grid, `1fr 360px`). Page header + error alert sit OUTSIDE the grid. The grid contains: left `<div>` (wraps `.appt-form-card` with `flex:1`) + right `.appt-brand-panel` (flex column, centered, `align-items: stretch` fills height). Responsive: brand panel hidden below 960px.

---

## Session Startup Checklist
When starting a new Claude Code session:
> "Read CLAUDE.md. We are continuing ClinicOS. Features 1–52 are complete. Today we are working on [describe task]."

---

*Last updated: 2026-05-06*
*Current phase: Phase 3 queue system complete — Billing on Close (Phase 3.3) is next*
