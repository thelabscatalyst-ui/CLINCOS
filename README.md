# ClinicOS

Appointment management SaaS for independent doctors in Indian Tier 2/3 cities.

Doctors get a personal booking page, WhatsApp reminders, patient records, and a reports dashboard — all for ₹299–499/month. No app download needed for patients.

---

## Features

**For doctors**
- Dashboard with today's schedule and weekly stats
- Create, edit, and reschedule appointments with a split-layout booking form
- Walk-in quick booking from the appointments page
- Monthly calendar view with today's date ring indicator
- Patient records — list, search, edit name/phone, doctor's notes, visit history
- Remove a patient (PIN-protected, deletes all appointments)
- Pre-filled booking form when booking from a patient's profile (name, phone, last-seen doctor)
- Reports — completion rates, no-show rates, top patients, monthly trend chart
- Configurable working hours, slot duration, and blocked dates
- PIN protection for sensitive pages (reports, settings, billing, patient delete)
- Dark / light theme toggle persisted via localStorage

**Appointments**
- Booking channel badges: Walk-in (gold), Reception (purple), Doctor (green), Patient (grey)
- Appointment status: Scheduled, Completed, No-show, Cancelled

**For patients**
- Book appointments via a public URL — no login, no app
- WhatsApp confirmation immediately after booking
- Automatic reminders 24 hours and 2 hours before the appointment

**Platform**
- 14-day free trial, then ₹399/month (Solo plan)
- Clinic / multi-doctor plan at ₹1,499/month
- Razorpay payments — UPI, cards, net banking
- Admin panel for platform owner to monitor all doctors and revenue

---

## Tech Stack

| Layer | Tool |
|---|---|
| Backend | FastAPI (Python) |
| Templates | Jinja2 (server-side rendering) |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL |
| ORM | SQLAlchemy |
| Auth | JWT in HTTP-only cookie (Passlib + bcrypt) |
| Notifications | Twilio WhatsApp + SMS |
| Payments | Razorpay |
| Scheduler | APScheduler |
| Deployment | Railway.app |

---

## Local Setup

**Prerequisites:** Python 3.10+

```bash
# 1. Clone and enter project
git clone <repo-url>
cd ClinicOS

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env              # then fill in your values (see below)

# 5. Run
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000` — you'll be redirected to the login page.

---

## Environment Variables

Create a `.env` file in the project root:

```env
# Core
DATABASE_URL=sqlite:///./clinic.db
SECRET_KEY=replace-with-random-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Twilio — WhatsApp/SMS notifications
# Get from: console.twilio.com
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_SMS_FROM=

# Razorpay — payments
# Get from: dashboard.razorpay.com → Settings → API Keys
RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXXXXXX
RAZORPAY_KEY_SECRET=XXXXXXXXXXXXXXXXXXXXXXXX

# Admin panel
# Must match the email used to register your doctor account
ADMIN_EMAIL=your-email@example.com
```

Generate a strong `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Twilio and Razorpay keys are optional for local development. The app runs without them — notifications log as `failed` and the payment button shows "not configured".

---

## Project Structure

```
ClinicOS/
├── main.py                 # App entry point — routers + scheduler lifespan
├── config.py               # Settings loaded from .env
├── requirements.txt
├── Procfile                # Railway deployment command
│
├── database/
│   ├── connection.py       # SQLAlchemy engine + session + create_tables()
│   └── models.py           # All ORM models and enums
│
├── routers/
│   ├── auth.py             # /register, /login, /logout
│   ├── doctors.py          # /dashboard, /calendar, /reports, /billing, /doctors/settings/*
│   ├── appointments.py     # /appointments — full CRUD
│   ├── patients.py         # /patients — list, profiles, notes
│   ├── public.py           # /book/{slug} — public booking (no auth)
│   └── admin.py            # /admin — platform owner only
│
├── services/
│   ├── auth_service.py         # JWT + plan gating dependencies
│   ├── appointment_service.py  # Slot logic, patient upsert
│   ├── notification_service.py # Twilio WhatsApp/SMS
│   ├── payment_service.py      # Razorpay order + verification
│   └── scheduler_service.py    # APScheduler reminder jobs
│
├── templates/              # Jinja2 HTML templates
└── static/
    └── css/main.css        # Dark/light theme design system
```

---

## How Notifications Work

1. Appointment booked (by doctor or patient) → WhatsApp confirmation sent immediately
2. Falls back to SMS if WhatsApp fails and `TWILIO_SMS_FROM` is set
3. Background scheduler checks every 15 minutes:
   - Sends 24-hour reminder when appointment is 23–25 hours away
   - Sends 2-hour reminder when appointment is 90–150 minutes away
4. Every send is logged in the `notifications_log` table with status `sent` or `failed`

For production, join the Twilio WhatsApp sandbox for testing, or apply for a WhatsApp Business number. See [Twilio WhatsApp docs](https://www.twilio.com/docs/whatsapp).

---

## How Payments Work

1. Doctor clicks Subscribe → `POST /billing/create-order?plan=basic|pro`
2. Razorpay checkout popup opens in-browser
3. On payment: Razorpay signature verified server-side with HMAC-SHA256
4. Plan activated: `doctor.plan_expires_at = now + 30 days`
5. Subscription recorded in `subscriptions` table

Use Razorpay test keys for development — no real charges.

---

## Subscription Plans

| Plan | Price | Notes |
|---|---|---|
| Free Trial | 14 days | Full access, no card needed |
| Solo | ₹399/month | Primary plan — individual doctor |
| Clinic | ₹1,499/month | Multi-doctor clinic with reception workspace |
| Basic | ₹299/month | Legacy |
| Pro | ₹499/month | Legacy |

---

## Admin Panel

Visit `/admin/dashboard` while logged in with the email set in `ADMIN_EMAIL`.

Shows: total registered doctors, active trials, paid plans, expired accounts, month-to-date revenue, and a full doctors table.

---

## Deployment (Railway.app)

1. Push this repo to GitHub
2. Create a new project on [railway.app](https://railway.app)
3. Add a PostgreSQL service — Railway provides `DATABASE_URL` automatically
4. Set all environment variables in Railway's Variables tab
5. Railway auto-deploys on every push to `main`

The `Procfile` tells Railway how to start the app:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

## License

Private — all rights reserved.
