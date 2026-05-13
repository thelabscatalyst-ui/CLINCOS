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
│   ├── billing_ops.py           # /visits/{id}/bill, /bills/*, /price-catalog — bill CRUD + PDF
│   ├── income.py                # /income, /expenses — revenue dashboard + expense tracker
│   ├── patients.py              # /patients — list, search, detail, notes, vault
│   ├── clinic.py                # /clinic/admin/*, /doctor-invite/* — multi-doctor clinic
│   ├── public.py                # /book/{slug} — public booking (no auth, rate-limited)
│   └── admin.py                 # /admin — platform owner only
│
├── services/
│   ├── auth_service.py          # JWT auth + PIN session auth + all get_*_doctor helpers
│   ├── appointment_service.py   # Slot availability (filter_past=True for today), get_or_create_patient
│   ├── visit_service.py         # Queue logic — check_in, call_next, done_and_call_next, close_visit, etc.
│   ├── notification_service.py  # Twilio WhatsApp + SMS, confirmation + reminder sends
│   ├── payment_service.py       # Razorpay order create + HMAC signature verify
│   ├── bill_pdf_service.py      # fpdf2 PDF bill generation → auto-saved to patient vault
│   └── scheduler_service.py     # APScheduler — T-24h and T-2h reminder jobs
│
├── templates/
│   ├── base.html                # Master layout — navbar, dock (7 items), PIN overlay
│   ├── login.html               # Two-column auth page
│   ├── register.html            # Two-column auth page
│   ├── landing.html             # Public marketing landing page
│   ├── dashboard.html           # Stats row + today's schedule card + quick actions
│   ├── settings.html            # Working hours, clinic profile, blocked dates, subscription, PIN, account
│   ├── appointments.html        # Today's Flow bar + Queue section + Schedule split (Walk-ins | Appointments)
│   ├── appointment_new.html     # New appointment form — card layout with SVG icons + brand panel
│   ├── appointment_card.html    # Appointment detail overlay (partial, loaded via AJAX)
│   ├── appointment_edit.html    # Edit/reschedule form
│   ├── calendar.html            # Monthly calendar view
│   ├── patients.html            # Patient list with search
│   ├── patient_detail.html      # Patient profile, history, notes (Documents button → vault)
│   ├── patient_vault.html       # Document vault — categorised files, search, upload, edit
│   ├── reports.html             # Analytics: charts, top patients, visit types
│   ├── income.html              # Revenue dashboard — daily/monthly charts + transaction list
│   ├── expenses.html            # Expense tracker — log, recurring, by category
│   ├── billing.html             # Plan cards + Razorpay checkout
│   ├── bill_detail.html         # View/edit bill — items, totals, payment info
│   ├── queue_display.html       # Public TV display screen /queue/{slug}
│   ├── public_booking.html      # Patient-facing booking form (no navbar)
│   ├── public_confirm.html      # Booking confirmation + Google Calendar link
│   ├── clinic/
│   │   ├── admin_dashboard.html # Clinic aggregated stats + staff management
│   │   └── doctor_invite.html   # Doctor invite accept page
│   └── admin/
│       ├── admin_dashboard.html # Platform stats
│       └── doctors_list.html    # All registered doctors table
│
├── uploads/                     # Patient vault files — gitignored, auto-created
│   └── patients/{doctor_id}/{patient_id}/
│
└── static/
    ├── css/main.css             # All styles — dark/light theme, shadows, responsive (v139)
    ├── js/
    └── img/
```

---

## Database Tables
| Table | Key Columns |
|---|---|
| **doctors** | id, name, email, phone, password_hash, pin_hash, specialization, clinic_name, clinic_address, city, languages, slug, is_active, plan_type, trial_ends_at, plan_expires_at, doctor_mode, walkin_policy, avg_consult_mins, created_at |
| **patients** | id, doctor_id, name, phone, age, gender, blood_group, allergies, language_pref, notes, visit_count, first_visit, last_visit, created_at |
| **appointments** | id, doctor_id, patient_id, appointment_date, appointment_time, duration_mins, appointment_type, status, patient_notes, doctor_notes, reminder_24h_sent, reminder_2h_sent, booked_by, visit_id, arrival_status, created_at |
| **visits** | id, doctor_id, patient_id, clinic_id, appointment_id, visit_date, token_number, queue_position, status, source, is_emergency, notes, check_in_time, call_time, done_time, created_by |
| **bills** | id, visit_id, doctor_id, clinic_id, patient_id, subtotal, discount, gst_amount, total, paid_amount, payment_mode, paid_at, notes, created_by |
| **bill_items** | id, bill_id, description, quantity, unit_price, total |
| **price_catalog** | id, doctor_id, name, default_price, is_active, is_pinned |
| **expenses** | id, doctor_id, clinic_id, amount, category, description, expense_date, created_by |
| **recurring_expenses** | id, doctor_id, clinic_id, amount, category, description, frequency, next_due, is_active |
| **doctor_schedules** | id, doctor_id, day_of_week (0=Mon), start_time, end_time, slot_duration, max_patients, is_active |
| **blocked_dates** | id, doctor_id, blocked_date, reason |
| **blocked_times** | id, doctor_id, start_datetime, end_datetime, reason |
| **subscriptions** | id, doctor_id, plan_name, amount (paise), payment_id, start_date, end_date, status |
| **notifications_log** | id, appointment_id, type, channel, message_body, status, sent_at |
| **patient_documents** | id, doctor_id, patient_id, original_name, stored_name, file_size, mime_type, category, description, uploaded_at |
| **clinics** | id, name, slug, plan_type, plan_expires_at, created_at |
| **clinic_doctors** | id, clinic_id, doctor_id, role, joined_at |
| **clinic_doctor_invites** | id, clinic_id, email, token, role, accepted, created_at |

`pin_hash`, `visit_id`, `arrival_status`, `doctor_mode`, `walkin_policy`, `is_emergency`, `avg_consult_mins`, `plan_seats`, and all Phase 2/3 tables added via `_run_migrations()` on startup.

---

## Visit / Queue System

### Visit State Machine
```
WAITING → SERVING → BILLING_PENDING → DONE
                 ↘ CANCELLED
         ↘ SKIPPED
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

### Today's Flow Card (full-width, above queue)
- Horizontal strip with `.flow-counts-row` (Waiting / Serving / Billing / Done counts with brown dots)
- `.flow-bar` progress bar in brown/beige shades only
- `.flow-kpis-row` KPIs (Total, On-Time %, Avg Wait)
- Vertical dividers between sections

### Queue Section (today only, `.queue-section` card)
- Now Serving block + Waiting list + Billing Pending block
- Action buttons per visit state (Call, Done, Free, Skip, Emergency, Cancel)
- Three-dot dropdown menu per row — z-index elevated dynamically on open
- Empty state when queue is empty

### Schedule Section (`.schedule-section` card)
- Header row: "SCHEDULE" label + date nav + search — all on one line, separated by full-width border below
- Two-column split grid (`.appt-split-grid`): **Walk-ins** (left) | **Appointments** (right)
- Each column scrollable independently, capped at 5 visible rows
- Vertical divider line between columns
- Rows are clickable (whole card → appointment detail overlay), no View button
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
- `GET /income`, `GET /income/transactions` — requires PIN
- `GET /expenses` — requires PIN

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
- Right: "Clinic Admin" link (clinic owners only) + "Settings" link + Theme toggle (moon/sun) + Logout (power icon)
- No nav links in navbar — navigation is handled entirely by the dock

### Dock (base.html)
- Auto-hides to left edge, reveals on mouse hover within 12px of left edge
- **7 items**: Dashboard · Today's Queue · Patients · Calendar · Reports · Income · Expenses
- Active item highlighted with `dock-item--active`

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
| GET | `/pricing` | Auth | Pricing page |
| GET | `/billing` | PIN-Auth | Plan cards + Razorpay |
| POST | `/billing/create-order` | PIN-Auth | Create Razorpay order (JSON) |
| POST | `/billing/verify` | PIN-Auth | Verify payment + activate plan |
| GET/POST | `/doctors/settings` | PIN | Working hours, profile, blocked dates, PIN, subscription, account |
| POST | `/doctors/settings/schedule` | PIN | Save working hours |
| POST | `/doctors/settings/account` | PIN | Save name, email, phone, specialization |
| POST | `/doctors/settings/profile` | PIN | Save clinic profile |
| POST | `/doctors/settings/block` | PIN | Add blocked date |
| POST | `/doctors/settings/unblock/{id}` | PIN | Remove blocked date |
| POST | `/doctors/settings/blocktime` | PIN | Add blocked time window |
| POST | `/doctors/settings/unblocktime/{id}` | PIN | Remove blocked time window |
| POST | `/doctors/settings/pin` | PIN | Set / change / remove PIN |
| GET | `/pin-prompt` | No | Redirects to `next` param |
| POST | `/pin-prompt` | No | Verify PIN → set pin_session cookie |
| GET | `/appointments` | Plan | Today's Flow + Queue + split schedule (walk-ins / booked) |
| GET | `/appointments/slots` | Plan | Available slots JSON (AJAX, filter_past=True) |
| GET | `/appointments/new` | Plan | New appointment form |
| POST | `/appointments` | Plan | Create appointment |
| POST | `/appointments/walkin` | Plan | Quick walk-in booking (auto check-in to queue) |
| GET | `/appointments/{id}` | Plan | Redirect → detail card overlay |
| GET | `/appointments/{id}/card` | Plan | Appointment card HTML (AJAX partial) |
| POST | `/appointments/{id}/status` | Plan | Update status + doctor notes |
| GET | `/appointments/{id}/edit` | Plan | Edit/reschedule form |
| POST | `/appointments/{id}/edit` | Plan | Save rescheduled appointment |
| GET | `/visits/today` | Plan | Redirect → `/appointments` (301) |
| POST | `/visits/check-in` | Plan | Legacy walk-in check-in (hidden route, use walkin instead) |
| POST | `/visits/check-in-appt/{id}` | Plan | Check in from existing appointment |
| POST | `/visits/{id}/call` | Plan | Manually call a waiting visit |
| POST | `/visits/{id}/done` | Plan | Mark serving → billing_pending, auto-call next |
| POST | `/visits/{id}/close-free` | Plan | Close visit with zero charge |
| POST | `/visits/{id}/skip` | Plan | Skip to end of queue |
| POST | `/visits/{id}/emergency` | Plan | Promote to top of queue |
| POST | `/visits/{id}/cancel` | Plan | Cancel visit |
| POST | `/visits/{id}/move` | Plan | Manually reorder queue position |
| GET | `/visits/queue-status` | Plan | JSON snapshot for polling |
| GET | `/visits/{id}/bill-prefill` | Plan | Bill prefill JSON (price catalog + patient) |
| POST | `/visits/{id}/bill` | Plan | Save bill + generate PDF |
| GET | `/bills/{id}` | Plan | View bill detail |
| GET | `/bills/{id}/edit` | PIN | Edit bill form |
| POST | `/bills/{id}/edit` | PIN | Save edited bill |
| POST | `/bills/{id}/mark-paid` | Plan | Mark bill as paid |
| GET | `/bills/{id}/pdf` | Plan | Download bill PDF |
| GET | `/price-catalog` | Plan | Price catalog JSON |
| POST | `/price-catalog` | Plan | Add catalog item |
| POST | `/price-catalog/{id}/delete` | Plan | Delete catalog item |
| POST | `/price-catalog/{id}/pin` | Plan | Toggle catalog item pinned |
| GET | `/income` | PIN | Revenue dashboard |
| GET | `/income/transactions` | PIN | Full transaction history |
| GET | `/expenses` | PIN | Expense tracker |
| POST | `/expenses` | Plan | Add expense |
| POST | `/expenses/{id}/delete` | Plan | Delete expense |
| POST | `/expenses/recurring` | Plan | Add recurring expense rule |
| POST | `/expenses/recurring/{id}/toggle` | Plan | Enable/disable recurring rule |
| POST | `/expenses/recurring/{id}/delete` | Plan | Delete recurring rule |
| GET | `/queue/{slug}` | No | Public TV display screen |
| GET | `/queue/{slug}/status` | No | Public queue JSON for polling |
| GET | `/patients` | Plan | Patient list + search |
| GET | `/patients/{id}` | PIN | Patient profile + history |
| POST | `/patients/{id}/edit` | Plan | Update patient details |
| POST | `/patients/{id}/notes` | Plan | Update patient notes |
| POST | `/patients/{id}/delete` | PIN | Delete patient + all records |
| GET | `/patients/{id}/vault` | PIN | Patient document vault |
| POST | `/patients/{id}/vault/upload` | PIN | Upload files to vault |
| GET | `/patients/{id}/vault/{doc_id}` | PIN | Serve/download vault document |
| POST | `/patients/{id}/vault/{doc_id}/edit` | PIN | Update doc category + description |
| POST | `/patients/{id}/vault/{doc_id}/delete` | PIN | Delete vault document |
| GET | `/book/{slug}` | No | Public booking form |
| GET | `/book/{slug}/slots` | No | Public slots JSON (AJAX) |
| POST | `/book/{slug}` | No | Submit booking (rate-limited) |
| GET | `/book/{slug}/confirm/{id}` | No | Booking confirmation |
| GET | `/clinic/admin` | Clinic Owner | Clinic admin dashboard |
| GET | `/clinic/admin/doctors` | Clinic Owner | Clinic doctors list |
| POST | `/clinic/admin/doctors/invite` | Clinic Owner | Send doctor invite |
| GET | `/doctor-invite/{token}` | No | Accept invite page |
| POST | `/doctor-invite/{token}` | No | Accept invite → create account |
| GET | `/admin` | Admin | Redirect → `/admin/dashboard` |
| GET | `/admin/dashboard` | Admin | Platform stats |
| GET | `/admin/doctors` | Admin | All doctors table |

Auth column: **No** = public, **Auth** = JWT only, **Plan** = JWT + active trial/plan, **PIN** = Plan + PIN unlock, **PIN-Auth** = JWT + PIN unlock, **Clinic Owner** = clinic owner role, **Admin** = platform owner email

---

## Design System (main.css — currently v139)
Supports **dark** (default) and **light** themes. Theme toggled via navbar button, saved to `localStorage`, applied to `<html>` element (`html.light` class).

**Palette: warm sepia/parchment** — NOT neutral grey. Both themes share a brown-amber aesthetic.
The authoritative token reference is `docs/design-tokens.md`. Always read that file before touching CSS or templates.

### Dark theme (default — `:root`)
- Background: `#1a1612`, Cards: `#211d18`, Inputs: `#302b25`
- Text: `#ede8e2`, Muted: `#9a8f85`, Dim: `#5e5650`, Border: `#3d3630`
- Navbar/Dock bg: `#2e1e0c` (always dark brown, both themes)
- Card shadow: `0 4px 20px rgba(0,0,0,0.50), 0 1px 4px rgba(0,0,0,0.35)`

### Light theme (`html.light`)
- Background: `#e6e0d7`, Cards: `#f5f2ec`, Inputs: `#dfd9d0`
- Text: `#1a1410`, Muted: `#6b5f55`, Dim: `#a89e94`, Border: `#c2a98a`
- Navbar/Dock bg: `#2e1e0c` (always dark brown, both themes)
- Card shadow: `0 4px 16px rgba(60,40,20,0.14), 0 1px 4px rgba(60,40,20,0.10)`

### Common
- Warm sepia/parchment palette throughout — no cold greys or pure white/black
- **No paper texture** — plain flat background color on `body`
- **No ambient glow** — `--glow` is pure drop shadow only, no white halo
- Every card gets `box-shadow: var(--glow)` + `translateY + scale` pop on hover (`--transition-pop`)
- **Fonts**: `Inter` is the primary font for all body text. `Playfair Display` only for: `.navbar-brand`, `.page-title`, `.pub-clinic-name`, `.brand-title`, `.appt-brand-title`
- **Border radius tokens**: `--radius-xs: 6px` · `--radius-sm: 8px` · `--radius: 16px` · `--radius-lg: 24px`
- Layout: `.main-content { padding: 32px 24px; }` — no max-width, full screen width, equal side gaps

### Key CSS Rules
- Page buttons are always `btn-sm` (not full-width) unless it's a standalone auth form submit
- `<button>` that is NOT a form submit MUST have `type="button"` to prevent accidental form submission
- Never use `disabled` on inputs inside active forms — use CSS class-based dimming (e.g. `schedule-row--off`)
- Inline flex sizing (`flex: 1`) goes on `<input>` elements directly, not `.form-group` wrappers
- Select dropdowns use `appearance: none` + custom SVG arrow background-image
- `.btn` has `box-sizing: border-box`, `line-height: 1`, `-webkit-appearance: none` to normalise `<button>` vs `<a>` sizing
- `.appt-row` has `flex-shrink: 0` — prevents rows from compressing in flex columns
- Dropdown menus (`.visit-menu`) use dynamic z-index elevation via JS `toggleMenu()` to prevent overlap

### Appointment Row Structure
```
.appt-row (flex, space-between, clickable via onclick, flex-shrink: 0)
  .appt-left
    .appt-token-num   (#1, #2 — bold)
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
- `.queue-section` and `.schedule-section`: `bg-2, border, border-radius: var(--radius), padding: 20px 24px, box-shadow: var(--glow)`
- `.schedule-section-header`: flex row with "SCHEDULE" label + date nav + search, `border-bottom` divider
- `.appt-split-grid`: CSS grid `1fr 1px 1fr`, Walk-ins left, Appointments right, `.appt-col-divider` between
- `.appt-col-body`: max-height capped, independently scrollable per column

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
1. Doctor clicks Subscribe → JS calls `POST /billing/create-order?plan=solo|clinic`
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
| Solo | ₹399/month | Individual doctor |
| Clinic | ₹1,499/month | Multi-doctor clinic |

PLAN_AMOUNTS in `payment_service.py`: `solo=39900, clinic=149900` (paise).

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
12. **get_or_create_patient signature** — `get_or_create_patient(doctor_id, name, phone, db, age=None, gender=None)` — positional order matters

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
| 2 | Database models — all tables | ✅ Done |
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
| 31 | Phase 2: Clinic admin dashboard (/clinic/admin — aggregated stats, staff list) | ✅ Done |
| 32 | Phase 2: Unified clinic public booking (/book/clinic/{slug}) | ✅ Done |
| 33 | Phase 2: Clinic plan billing (₹1,499/month, Razorpay + clinic.plan_expires_at) | ✅ Done |
| 34 | Remove Patient — PIN-gated delete (patient + appointments) | ✅ Done |
| 35 | Edit Patient — modal to update name + phone + medical details | ✅ Done |
| 36 | Pre-fill booking from patient profile (name, phone, last-seen doctor) | ✅ Done |
| 37 | Booking channel badges — Doctor / Patient / Walk-in / Reception | ✅ Done |
| 38 | Doctor's Notes textarea — vertical-only resize | ✅ Done |
| 39 | New Appointment redesign — card layout with section icons + brand panel | ✅ Done |
| 40 | PIN gate extended to patient detail page | ✅ Done |
| 41 | Phase 3: Visit/queue models — Visit, Bill, BillItem, PriceCatalog, Expense tables | ✅ Done |
| 42 | Phase 3: visit_service — full queue state machine | ✅ Done |
| 43 | Phase 3: Queue merged into /appointments — live queue + split schedule | ✅ Done |
| 44 | Phase 3: Walk-in auto check-in to queue on creation | ✅ Done |
| 45 | Phase 3: Auto-complete appointment when visit marked done | ✅ Done |
| 46 | Navbar stripped — Settings + Clinic Admin (owners only) + theme + logout | ✅ Done |
| 47 | Dock expanded — 7 items (Dashboard, Queue, Patients, Calendar, Reports, Income, Expenses) | ✅ Done |
| 48 | Appointment rows — clickable cards, token numbers, time pill, flex-shrink fix | ✅ Done |
| 49 | Dashboard Today's Schedule — numbered rows, clickable, in schedule-section card | ✅ Done |
| 50 | Past time slots hidden when booking for today | ✅ Done |
| 51 | Phase 3.3: Billing on close — bill modal, price catalog, payment recording | ✅ Done |
| 52 | Settings — Account Details card (name, email, phone, specialization edit) | ✅ Done |
| 53 | Settings — Price Catalog Quick-add + pin toggle | ✅ Done |
| 54 | Settings — Clinic subscription active plan details | ✅ Done |
| 55 | Patient Document Vault — categorised file storage, upload, search, inline edit, delete | ✅ Done |
| 56 | Auto-generate PDF bill on payment → saved to patient vault (invoice category, "Auto" badge) | ✅ Done |
| 57 | Bill PDF — warm parchment palette, rounded cards, pre-calculated heights | ✅ Done |
| 58 | Phase 3.4: Income dashboard — daily/monthly revenue + charts + transaction history | ✅ Done |
| 59 | Expense tracker — log, recurring rules, category breakdown | ✅ Done |
| 60 | Today's Flow card — full-width bar with brown/beige shades + KPIs | ✅ Done |
| 61 | Schedule columns — capped at 5 rows, independent scroll per column | ✅ Done |
| 62 | Font standardisation — Inter primary, Playfair Display brand-only | ✅ Done |
| 63 | Border radius token system — xs/sm/md/lg variables throughout | ✅ Done |
| 64 | Dropdown z-index fix — dynamic elevation on open, no overlap with next row | ✅ Done |
| 65 | Paper texture removed + ambient glow removed — clean drop shadows only | ✅ Done |
| 66 | Card shadows — visible in both dark and light themes | ✅ Done |
| 67 | Landing page `--amber` token fix — beige in dark, darker amber in light | ✅ Done |
| 68 | Legacy `POST /visits/check-in` argument order bug fixed | ✅ Done |
| 69 | Deploy on Railway.app | ⬜ Planned |

---

## Patient Page — PIN Protection Note
`GET /patients/{id}` uses `require_pin` (not `get_paying_doctor`) so the blur overlay renders when PIN is set. The `pin_required` flag is passed explicitly in the template context. `_pin_parent_path` in `auth_service.py` maps `/patients/{id}/delete` → `/patients/{id}` for the PIN redirect.

## New Appointment Layout
`appointment_new.html` uses `.appt-new-split` (CSS grid, `1fr 360px`). Page header + error alert sit OUTSIDE the grid. The grid contains: left `<div>` (wraps `.appt-form-card` with `flex:1`) + right `.appt-brand-panel` (flex column, centered, `align-items: stretch` fills height). Responsive: brand panel hidden below 960px. Form uses `.apn-section` dividers with circular icon badges, and `.apn-input-wrap` for SVG-icon-decorated inputs.

---

## Patient Document Vault

### Storage
Files saved to `uploads/patients/{doctor_id}/{patient_id}/` (auto-created). `PatientDocument` ORM model stores metadata: `doctor_id`, `patient_id`, `original_name`, `stored_name`, `file_size`, `mime_type`, `category`, `description`, `uploaded_at`.

### Categories (`DOCUMENT_CATEGORIES` in `database/models.py`)
`invoice`, `lab_report`, `prescription`, `xray_scan`, `discharge_summary`, `insurance`, `other`

### Auto-generated Bills
`services/bill_pdf_service.py` → `generate_and_store_bill_pdf(bill, db)` called from `routers/billing_ops.py` after every successful bill save. Failures are silently swallowed (never crash billing). PDFs stored as `bill_{id}_{hex6}.pdf`, categorised as `invoice`, shown with an "Auto" badge in the vault UI.

### Bill PDF Design
Built with `fpdf2` (pure Python, no system deps). Warm parchment palette matching app: BG `#f8f2ea`, CARD_BG `#ede7de`, BORDER `#c2a98a`. All section cards use `_rounded_card()` helper. Heights pre-calculated before drawing to prevent text overflow. Sections: clinic header, patient info card, items table card, totals card, payment card, footer.

### Content-Disposition header
Vault file serving uses RFC 5987 encoding for non-ASCII filenames:
```python
headers["Content-Disposition"] = f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'
```

---

## Settings — Account Details
`POST /doctors/settings/account` updates `doctor.name`, `doctor.email`, `doctor.phone`, `doctor.specialization`. Email uniqueness checked against other doctors. Error param `account_error` shown as alert in the Account Details card.

---

## Session Startup Checklist
When starting a new Claude Code session:
> "Read CLAUDE.md. We are continuing ClinicOS. Features 1–68 are complete. Today we are working on [describe task]."

---

*Last updated: 2026-05-13*
*Current phase: Core feature-complete — Railway deployment is next*
