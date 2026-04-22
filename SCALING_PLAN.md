# ClinicOS — Strategic Scaling Plan (v2 Pricing & Architecture)

> **Purpose:** Actionable system-design plan to evolve ClinicOS from a single-doctor SaaS into a 3-tier platform: Solo → Clinic → Multi-Clinic Practitioner. Written from a system-design perspective, with workflows, data model, pricing, and phased rollout.
>
> **Status:** Design doc — pre-implementation. Supersedes pricing sections of CLAUDE.md and extends ARCHITECTURE.md.
>
> **Last updated:** 2026-04-22

---

## 1. Executive Summary

ClinicOS today assumes **one doctor = one account = one clinic**. That works for Dr. Mehta in Nashik but collapses the moment you sell into:
- Solo doctors with a receptionist (shared password risk)
- Multi-doctor clinics (no clinic-level admin, no unified billing)
- Visiting consultants working across clinics (no location/clinic awareness)

This plan introduces **three commercial tiers** backed by **one unified data model** (Clinic → Doctor → Staff → Appointment) so you never maintain three divergent codebases.

### The three tiers (proposed)

| Tier | Target | Price (₹/mo) | Seats | Key Unlock |
|---|---|---|---|---|
| **Solo** | 1 doctor + optional receptionist sharing account | 400 | 1 login, PIN-gated sections | Multi-channel booking, receptionist share-mode |
| **Clinic** | 2–5 doctors, 1+ receptionists | 1,499 flat | 5 doctor seats + 2 staff seats | Clinic admin, receptionist dropdown, unified booking page |
| **Clinic+** | 6+ doctors / chains | 1,499 base + 250/extra doctor | Unlimited, contact sales | Multi-location, shift management, SSO, priority support |

*Pricing is corrected from your original draft — see §7 for the reasoning.*

### Core architectural bets
1. **One schema covers all three tiers.** Feature flags per plan, not separate databases.
2. **Clinic is the top-level tenant**, not the doctor. (Even solo doctors get an implicit single-doctor clinic.)
3. **Patient identity is scoped to the clinic**, not the doctor. Fixes Tier 3 cleanly.
4. **RBAC over shared-password PIN-gating** is the long-term play. PIN-gating is tolerated only on the Solo tier.

---

## 2. Tier 1 — Solo Doctor (₹400/month)

### Who it's for
One doctor, one clinic, optionally one receptionist who shares the same login. Think Dr. Mehta in Nashik with Priya at the front desk.

### Account model: "Shared login + PIN-gated sections"
- **One doctor account** — same email/password as today.
- Sensitive views (Billing, Reports, Settings, Patient financials) require a **4–6 digit PIN** that only the doctor knows.
- Receptionist uses the same login for day-to-day work; when she hits a sensitive page, a PIN prompt blocks her.
- PIN set during onboarding, stored as bcrypt hash, re-prompted every session or after 30 min idle on a sensitive page.

**Why this (vs full staff accounts):**
- Zero extra auth infra for the cheapest tier.
- Matches how small clinics *actually* operate — shared logins are universal in Indian Tier 2/3.
- Keeps per-seat cost at zero while still protecting billing & reports.

**What to flag honestly to the buyer:**
- No audit trail of "who did what" — every action is attributed to the doctor.
- If the receptionist leaves, the doctor must rotate both the password and the PIN.
- Upgrade path to Tier 2 is one click: we convert the shared login into doctor + invited staff seats.

### Sensitive sections (PIN-locked)
| Section | Rationale |
|---|---|
| `/billing/*` | Payment history, cards |
| `/reports` | Revenue numbers, patient volume trends |
| `/doctors/settings/*` | Working hours, plan, clinic profile, staff invites |
| Patient financial notes | Unpaid bills, pricing agreements |

### Booking channels — all four paths
Every booking lands in the same `appointments` table; they only differ in the `booked_by` field and who keyed it in.

| # | Channel | Flow | `booked_by` | Notifications |
|---|---|---|---|---|
| 1 | **Patient self-service via link** | Patient opens `/book/{slug}` → picks slot → submits | `patient` | WhatsApp confirmation to patient |
| 2 | **Doctor books directly** | Doctor opens `/appointments/new` on phone or laptop | `doctor` | WhatsApp to patient |
| 3 | **Receptionist books (phone call)** | Patient calls clinic → receptionist takes details → opens `/appointments/new` on shared login | `staff_shared` (new enum value) | WhatsApp to patient |
| 4 | **Walk-in** | Patient walks in → receptionist/doctor creates appointment with `appointment_time = now()` and marks `arrived=True` immediately | `walk_in` (new enum value) | Optional — skip WhatsApp since patient is on-site |

**Required changes:**
```python
class BookedBy(str, enum.Enum):
    doctor       = "doctor"
    patient      = "patient"
    staff_shared = "staff_shared"  # new — shared-login receptionist
    walk_in      = "walk_in"       # new
```

Add a quick-create "Walk-in" button on `/appointments` that skips the slot picker and books for the current time.

### Tier 1 workflow diagram
```
┌────────────────────┐     ┌─────────────────────┐
│  Public booking    │ ──► │   appointments      │
│  /book/{slug}      │     │   (booked_by set    │
└────────────────────┘     │    per channel)     │
                           │                     │
┌────────────────────┐     │                     │
│ Doctor dashboard   │ ──► │                     │
│ /appointments/new  │     │                     │
└────────────────────┘     │                     │
                           │                     │
┌────────────────────┐     │                     │
│ Receptionist       │ ──► │                     │
│ (shared login)     │     │                     │
│ /appointments/new  │     │                     │
└────────────────────┘     │                     │
                           │                     │
┌────────────────────┐     │                     │
│ Walk-in quick-add  │ ──► │                     │
│ one-tap button     │     │                     │
└────────────────────┘     └─────────────────────┘
                                     │
                                     ▼
                           ┌─────────────────────┐
                           │ Twilio WhatsApp +   │
                           │ APScheduler         │
                           │ reminders           │
                           └─────────────────────┘
```

### Files to touch for Tier 1
- `database/models.py` — extend `BookedBy`, add `pin_hash` column on `Doctor`
- `services/auth_service.py` — add `require_pin()` dependency
- `routers/doctors.py`, `routers/admin.py` equivalents — wrap sensitive routes with `Depends(require_pin)`
- `templates/pin_prompt.html` — full-page PIN challenge (not a modal — avoid DOM-escape bypass)
- `routers/appointments.py` — add "walk-in" quick endpoint
- `templates/settings.html` — PIN setup/change UI

**Estimated effort:** 2 days.

---

## 3. Tier 2 — Clinic (₹1,499/month for 5 doctors)

### Who it's for
A polyclinic or small chain with 2–5 doctors, 1–2 receptionists, and an owner who wants aggregated visibility. Fortis Nashik is the canonical example.

### Account model: proper RBAC
- **Clinic entity** owns billing. One owner doctor (or clinic admin) pays.
- **Doctors** are members of a clinic. Each doctor has their own login, own schedule, own patient notes.
- **Receptionists** are staff members of the clinic with a **dropdown** of doctors they can manage.
- **Clinic admin** (owner) sees aggregated dashboard across all doctors.

### Data model additions
```python
class Clinic(Base):
    __tablename__ = "clinics"
    id              = Column(Integer, primary_key=True)
    name            = Column(String(150), nullable=False)
    address         = Column(Text)
    city            = Column(String(100))
    slug            = Column(String(100), unique=True)     # /book/clinic/fortis-nashik
    plan_type       = Column(String(20), default="trial")  # trial | clinic | clinic_plus
    plan_expires_at = Column(DateTime)
    owner_user_id   = Column(Integer, ForeignKey("users.id"))
    created_at      = Column(DateTime, default=datetime.utcnow)


class ClinicDoctor(Base):           # many-to-many with role
    __tablename__ = "clinic_doctors"
    id         = Column(Integer, primary_key=True)
    clinic_id  = Column(Integer, ForeignKey("clinics.id"))
    doctor_id  = Column(Integer, ForeignKey("doctors.id"))
    role       = Column(String(20), default="associate")   # owner | associate | visiting
    is_active  = Column(Boolean, default=True)
    joined_at  = Column(DateTime, default=datetime.utcnow)


class Staff(Base):
    __tablename__ = "staff"
    id            = Column(Integer, primary_key=True)
    clinic_id     = Column(Integer, ForeignKey("clinics.id"))  # always scoped to a clinic
    name          = Column(String(100))
    email         = Column(String(150), unique=True)
    password_hash = Column(String(255))
    role          = Column(String(20), default="receptionist") # receptionist | manager | admin
    allowed_doctor_ids = Column(JSON, default=list)  # [] = all doctors in clinic
    is_active     = Column(Boolean, default=True)


class StaffShift(Base):              # optional, for larger clinics
    __tablename__ = "staff_shifts"
    id           = Column(Integer, primary_key=True)
    staff_id     = Column(Integer, ForeignKey("staff.id"))
    day_of_week  = Column(Integer)    # 0=Mon
    start_time   = Column(Time)
    end_time     = Column(Time)
    is_active    = Column(Boolean, default=True)
```

**`users` table** — if you want one unified identity layer (recommended):
```python
class User(Base):
    id           = Column(Integer, primary_key=True)
    email        = Column(String(150), unique=True)
    password_hash = Column(String(255))
    user_type    = Column(String(20))  # doctor | staff | admin
    linked_id    = Column(Integer)      # FK into doctors or staff depending on type
```
This is cleaner than having `auth` scattered across `doctors` and `staff` tables. Strongly recommended before Tier 2 ships.

### Receptionist interface — how the dropdown works

**Login flow:**
1. Receptionist goes to `/login`.
2. Server detects `user_type == "staff"` → issues JWT with `staff_id` + `clinic_id` + `allowed_doctor_ids`.
3. Redirected to `/clinic/reception` (new route).

**Reception workspace:**
```
┌────────────────────────────────────────────────────┐
│  Fortis Nashik — Reception                         │
│  Logged in: Priya Sharma                           │
│  ────────────────────────────────────────────────  │
│  Managing doctor:  [ Dr. Mehta        ▼]           │
│                       Dr. Mehta                    │
│                       Dr. Sharma                   │
│                       Dr. Patel                    │
│                       ─── All doctors ───          │
│                                                    │
│  [New appointment]  [Walk-in]  [Today's list]     │
│                                                    │
│  Today's schedule for Dr. Mehta                    │
│  09:00 — Rahul V.       Scheduled                  │
│  09:15 — Meena K.       Arrived                    │
│  ...                                               │
└────────────────────────────────────────────────────┘
```

**Key behaviour:**
- Dropdown scoped to `staff.allowed_doctor_ids`.
- "All doctors" view merges calendars and color-codes by doctor.
- Every action automatically filters by the currently-selected doctor.
- Sensitive views (billing, reports, settings) are **fully hidden** for staff — no PIN escape hatch. This is the big win over Tier 1.
- Each doctor's private patient notes still require that doctor's login to read/edit (staff sees "appointment exists" but not clinical notes).

### Booking system for Tier 2 — how it works

You have **four booking paths** just like Tier 1, but the entry points and the "which doctor" decision are different:

#### Path A — Unified clinic booking URL
```
https://clinicos.app/book/clinic/fortis-nashik
```
Landing page shows all active doctors:
```
Fortis Nashik
Choose your doctor:
  [ Dr. Mehta — GP       ]  [Book]
  [ Dr. Sharma — Cardio  ]  [Book]
  [ Dr. Patel — Paeds    ]  [Book]
```
Patient picks → gets that doctor's slot picker → booking saved with `doctor_id + clinic_id`.

#### Path B — Direct doctor booking URL (same as today)
```
https://clinicos.app/book/dr-mehta-nashik
```
Still works. Doctor's individual link routes into the same appointments table, with `clinic_id` auto-resolved from the doctor's active clinic membership.

#### Path C — Receptionist books on behalf of patient (phone-in)
Receptionist uses the dropdown → picks doctor → `/appointments/new` → enters patient details → submit. `booked_by = staff`, `staff_id` recorded for audit.

#### Path D — Walk-in
Receptionist one-taps "Walk-in" → picks doctor → patient details → `booked_by = walk_in`.

### Shifts / login pages — what you need to build

**Login:**
- Use one `/login` route. Backend detects `user.user_type` and routes:
  - `doctor` → `/dashboard`
  - `staff` → `/clinic/reception`
  - `admin` (clinic owner) → `/clinic/admin`

**Shift management (optional, Tier 2 nice-to-have):**
- Admin sets shift for each staff member (Priya: Mon–Fri 9am–2pm, Anjali: Mon–Fri 2pm–8pm).
- When a receptionist logs in outside her shift, she sees a read-only warning; she can still book emergencies.
- Shift data also drives "who's on duty now" on the clinic admin dashboard.

**Staff management UI (admin only):**
- `/clinic/admin/staff` — invite staff, edit allowed_doctor_ids, set shifts, deactivate.
- Invite flow: admin enters staff email → system sends one-time link → staff sets password → done.

### Permission matrix (Tier 2)

| Feature | Clinic Admin | Doctor | Receptionist |
|---|---|---|---|
| Book appointment | ✅ all docs | ✅ own | ✅ allowed docs |
| View/edit appointment | ✅ all | ✅ own | ✅ allowed docs |
| Patient list | ✅ all | ✅ own | ✅ allowed docs (basic fields) |
| Clinical notes | ❌ | ✅ own | ❌ |
| Doctor schedule | ✅ all | ✅ own | view-only |
| Reports (per-doctor) | ✅ all | ✅ own | ❌ |
| Reports (clinic-wide) | ✅ | ❌ | ❌ |
| Billing/subscription | ✅ | ❌ | ❌ |
| Staff management | ✅ | ❌ | ❌ |
| Clinic settings | ✅ | ❌ | ❌ |

---

## 4. Tier 3 — Doctor at Multiple Clinics

### Who it's for
Visiting consultants (cardiologist who spends 2 days/week at Clinic A, 3 days at Clinic B, runs her own practice on weekends).

This is where the data model has to be *right* or you'll paint yourself into a corner.

### The central architectural question
> Does a patient belong to the **doctor** or the **clinic**?

**Recommended answer: patient belongs to the clinic. The doctor gets a per-doctor private clinical record layered on top.**

Why:
- A patient who visits Apollo Nashik is Apollo's patient for billing, registration, and records.
- Dr. Sharma has her own clinical notes on that patient — private to her.
- If Dr. Sharma leaves Apollo, Apollo keeps the patient. Dr. Sharma keeps her notes.

Concrete structure:
```python
class Patient(Base):
    id         = Column(Integer, primary_key=True)
    clinic_id  = Column(Integer, ForeignKey("clinics.id"))   # was doctor_id
    name, phone, ...

class PatientDoctorRecord(Base):
    __tablename__ = "patient_doctor_records"
    id              = Column(Integer, primary_key=True)
    patient_id      = Column(Integer, ForeignKey("patients.id"))
    doctor_id       = Column(Integer, ForeignKey("doctors.id"))
    clinical_notes  = Column(Text)
    allergies       = Column(Text)
    # … doctor-private fields
```

**Migration impact:** The existing `Patient.doctor_id` becomes `Patient.clinic_id`. Every solo doctor gets an implicit clinic row (already proposed in §3) so no data loss. This is the single biggest migration in the plan — do it early, before Tier 2 goes live.

### Booking system for Tier 3

A visiting doctor has **one doctor profile** but appears under multiple clinics via `clinic_doctors` junction. Her schedule is per-clinic.

```python
class DoctorSchedule(Base):
    # existing fields
    clinic_id = Column(Integer, ForeignKey("clinics.id"))   # new — required
    day_of_week, start_time, end_time, slot_duration, ...
```

Same `day_of_week` rows per clinic — so Dr. Sharma has:
- `clinic_id=1` (her own), Mon/Wed/Fri, 10–16:00
- `clinic_id=2` (Apollo), Tue/Thu, 09–13:00

### Booking URLs for Tier 3

| URL | What it shows |
|---|---|
| `/book/clinic/sharma-heart-clinic` | Her own clinic only — her schedule there |
| `/book/clinic/apollo-nashik` | Apollo's page — all doctors including Dr. Sharma |
| `/book/clinic/apollo-nashik?doctor=dr-sharma` | Dr. Sharma specifically at Apollo |
| `/book/dr-sharma` | **Unified doctor page** — patient picks which clinic first, then sees that clinic's slots |

The unified doctor page is the Tier 3 unlock:
```
Dr. Sharma — Cardiologist
Where would you like to see her?
  ○ Sharma Heart Clinic (Mon/Wed/Fri)
  ○ Apollo Nashik (Tue/Thu)
[Continue →]
```

### Appointment model
```python
class Appointment(Base):
    # existing fields
    doctor_id  = Column(Integer, ForeignKey("doctors.id"))
    clinic_id  = Column(Integer, ForeignKey("clinics.id"))   # new — required
    patient_id = Column(Integer, ForeignKey("patients.id"))  # patient is clinic-scoped now
```

**Billing implications:** The appointment counts toward both:
- Dr. Sharma's own subscription (if she runs her own clinic)
- Apollo's clinic subscription (Apollo pays for its slot count)

This is correct — both parties provided value, both pay their share. It's also how every scalable marketplace bills (Uber pays driver, rider pays Uber).

### Conflict prevention (critical)
Dr. Sharma cannot be booked at Clinic A 10:00 AM Tuesday and Clinic B 10:00 AM Tuesday. Slot-availability function must cross-check:
```python
def is_slot_available(doctor_id, clinic_id, date, time):
    # existing check: no conflict within the clinic
    # NEW check: no conflict across ALL clinics for this doctor at this date+time
    conflicting = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == date,
        Appointment.appointment_time == time,
        Appointment.status != 'cancelled',
    ).first()
    return conflicting is None
```

---

## 5. Unified Data Model (End State)

```
┌──────────┐       ┌─────────────────┐       ┌──────────┐
│ clinics  │◄──────│ clinic_doctors  │──────►│ doctors  │
└────┬─────┘       └─────────────────┘       └────┬─────┘
     │                                            │
     │  ┌─────────┐                               │
     ├──►│ staff   │                              │
     │  └─────────┘                               │
     │                                            │
     │  ┌──────────┐                              │
     ├──►│ patients │◄──────┐                     │
     │  └──────────┘        │                     │
     │                      │                     │
     │  ┌──────────────┐    │                     │
     ├──►│ appointments │────┼────────────────────┤
     │  └──────────────┘    │                     │
     │                      │                     │
     │  ┌──────────────────┐│                     │
     │  │ patient_doctor_  │├─────────────────────┤
     │  │ records          ││                     │
     │  └──────────────────┘│                     │
     │                      │                     │
     │  ┌───────────────┐   │                     │
     │  │ doctor_       │───┴─────────────────────┤
     │  │ schedules     │                         │
     │  └───────────────┘                         │
     │                                            │
     │  ┌───────────────┐                         │
     └──►│ subscriptions│                         │
        └───────────────┘                         │
                                                  │
                                        ┌─────────▼─────────┐
                                        │ doctor-owned      │
                                        │ private data      │
                                        │ (notes, prefs)    │
                                        └───────────────────┘
```

### Single tenancy rule
Every data query MUST filter by `clinic_id` first, then optionally by `doctor_id`. Port the existing "never omit `doctor_id`" rule to "never omit `clinic_id`".

---

## 6. Workflows (end-to-end)

### 6.1 Solo doctor — Priya receives phone call
```
Patient calls → Priya picks up
  → Priya (already logged into shared account) goes to /appointments/new
  → Searches patient by phone; new patient? fills name + phone
  → Picks slot, submits
  → booked_by = staff_shared
  → WhatsApp sent to patient
  → Priya confirms verbally
Total: ~45 seconds
```

### 6.2 Solo doctor — Priya tries to view revenue
```
Priya clicks "Reports" in nav
  → Server middleware sees /reports requires PIN
  → Returns /pin-prompt page
  → Priya doesn't know PIN → blocked
  → Audit log: "PIN failure, route=/reports, IP=…" (optional Tier 1+ feature)
```

### 6.3 Clinic — patient self-books with Dr. Sharma at Apollo
```
Patient opens WhatsApp link: /book/clinic/apollo-nashik
  → Picks Dr. Sharma from doctor list
  → Picks Tuesday 10:15 AM slot (system checks Apollo + Dr. Sharma's other clinics)
  → Submits
  → Appointment created: clinic_id=apollo, doctor_id=sharma, booked_by=patient
  → Patient added to Apollo's patient list
  → Dr. Sharma's private record auto-created (empty clinical notes)
  → WhatsApp sent
```

### 6.4 Clinic — receptionist Anjali handles walk-in during her shift
```
Walk-in patient arrives at Fortis reception
  → Anjali clicks "Walk-in" button → picks Dr. Mehta from dropdown
  → Types name + phone, clicks Save
  → Appointment created for now(), booked_by=walk_in, staff_id=anjali
  → Doctor's dashboard gets real-time update (SSE or poll)
Total: ~20 seconds
```

### 6.5 Visiting doctor — Dr. Sharma checks her cross-clinic day
```
Dr. Sharma logs in on her phone morning of Tuesday
  → Dashboard shows "Today — Apollo Nashik (9 appts)"
  → Tomorrow (Wed) shows "Sharma Heart Clinic (12 appts)"
  → All in one unified calendar, color-coded per clinic
```

---

## 7. Pricing Correction (Important)

Your original proposal:
- ₹400 solo
- ₹1400 for 5 doctors = **₹280/doctor**
- ₹200/doctor above 5

This breaks pricing logic: a 5-doctor clinic pays **less per seat** than a solo doctor. Small clinics will game this.

### Recommended pricing

| Plan | Price | Seats | Per-seat effective |
|---|---|---|---|
| **Solo** | ₹399/mo | 1 doctor (shared PIN model, unlimited receptionist seats on same login) | ₹399 |
| **Clinic** | ₹1,499/mo flat | Up to 5 doctors + 2 staff seats | ₹300 at max |
| **Clinic+** | ₹1,499 + ₹299/extra doctor | 6+ doctors, unlimited staff | ₹299 marginal |
| **Visiting consultant add-on** | ₹199/extra clinic | Doctor belongs to one base clinic + N visiting clinics | — |

Rationale:
- Solo at ₹399 is your entry drug; Clinic plan is a clear upgrade (5x seats for 3.75x price).
- Per-seat stays consistent (~₹299–399), so no arbitrage.
- Visiting consultant surcharge monetizes the Tier 3 complexity directly — you bill the doctor, not the clinic.
- ₹1,499 is psychologically under ₹1,500, matches Indian SaaS pricing conventions.

### Annual discounts to push LTV
- 2 months free on annual plans across all tiers (standard SaaS)
- Quarterly billing for clinics (₹4,299 for 3 months, save ₹198)

---

## 8. Implementation Phases

Ordered to minimize rework and ship revenue-generating features fastest.

### Phase 0 — Foundation (Week 1)
**Goal:** Prepare schema without breaking today's product.
- Introduce `clinics` table; auto-create one clinic per existing doctor on migration
- Add `clinic_id` FK to `patients`, `appointments`, `doctor_schedules`, `subscriptions` (nullable initially, backfill from doctor)
- Introduce unified `users` table; migrate doctor auth into it
- Keep all existing routes working via compatibility layer

**Acceptance:** Prod traffic unaffected. Every query now has `clinic_id` available. No user-visible change.

### Phase 1 — Tier 1 hardening (Week 2)
- Add `pin_hash` to `doctors`
- Ship PIN middleware + prompt screen
- Extend `BookedBy` enum (`staff_shared`, `walk_in`)
- Ship Walk-in quick-create button on `/appointments`
- New pricing: rename "Basic/Pro" to "Solo", introduce ₹399 SKU

**Revenue unlock:** Can now upsell existing solo doctors who share credentials to an official, PIN-protected plan.

### Phase 2 — Tier 2 Clinic (Weeks 3–5)
- Ship `staff` table + staff login flow
- Ship `/clinic/reception` dropdown interface
- Ship `/clinic/admin` owner dashboard (aggregated stats)
- Ship `/book/clinic/{slug}` unified public booking
- Ship clinic subscription billing (₹1,499 flat SKU)
- Ship staff invite flow (email-based, one-time link)
- **Defer shifts to Phase 2.5** — release Tier 2 without shift management first; add if customers ask.

**Revenue unlock:** Can now sell to multi-doctor clinics.

### Phase 2.5 — Shifts & audit log (Week 6)
- `staff_shifts` table
- Shift-aware reception UI ("You're outside your shift — continue anyway?")
- Audit log table that records who did what (addresses the Tier 1 PIN-gating weakness too)

### Phase 3 — Tier 3 Multi-clinic doctor (Weeks 7–8)
- Ship `clinic_doctors` junction
- Ship `patient_doctor_records` split
- **Run the big migration:** `Patient.doctor_id` → `Patient.clinic_id`, split clinical notes into `patient_doctor_records`
- Ship `/book/dr-{slug}` clinic-picker page
- Ship cross-clinic slot conflict check
- Ship visiting-consultant add-on billing

**Revenue unlock:** Visiting consultants as a net-new customer segment.

### Phase 4 — Polish & scale (ongoing)
- SSO for Clinic+ customers (Google Workspace)
- Role-based report permissions (e.g., doctor can see own revenue, admin sees all)
- Multi-location per clinic (covered partially by current "clinic" — only add if real customer demand)
- White-label option for Clinic+ (custom subdomain)

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| PIN-gating on Tier 1 leaks via shared browser session | Receptionist accidentally sees billing | Force PIN re-entry on every sensitive-page load; auto-logout sensitive routes after 5 min idle |
| Patient-to-clinic migration corrupts existing records | Data loss, chargebacks | Dual-write for 2 weeks; diff-check before cutover; keep `doctor_id` column on `patients` as read-only backup for 90 days |
| Clinic admin becomes bottleneck (every staff invite needs admin) | Ops drag | Add a "manager" role that can invite receptionists but not billing |
| Pricing arbitrage — solo doctors register as "clinic of 1" | Revenue loss | Clinic plan minimum is 2 active doctors; enforce at billing |
| Tier 3 doctor exits a clinic with patients mid-way | Data dispute | Contractual: patients belong to clinic; doctor retains a *copy* of their own clinical notes on exit; built-in export feature |
| Cross-clinic slot conflicts not caught | Double-booked visiting doctor | Slot-availability check queries across all doctor's clinics; add DB unique constraint on `(doctor_id, date, time)` where status != cancelled |
| WhatsApp template approval per clinic brand | Onboarding lag | Use a single Twilio WhatsApp template with dynamic clinic name variable — one approval covers all tenants |
| Receptionist sees too many doctors in dropdown (noisy UI) | UX friction | `allowed_doctor_ids` defaults to a curated list; admin configures per receptionist |

---

## 10. Open Decisions (Need Founder Input)

Flagging these so they don't get decided silently during implementation:

1. **Single identity vs per-tenant email** — Can Dr. Sharma use `sharma@gmail.com` at both Apollo and her own clinic, or do we require different emails per clinic membership? *Recommendation: single identity, membership is a join row.*
2. **Patient portability** — If a patient visits Clinic A and later Clinic B (never overlapping doctors), are they one patient record or two? *Recommendation: two, for privacy. Patient chooses to link them manually.*
3. **Clinic+ enterprise features** — SSO, SOC2, HIPAA — do we invest in this now or wait until first enterprise deal? *Recommendation: wait. Ship tiers 1–3 first.*
4. **Pricing experiments** — Should we A/B test ₹399 vs ₹499 on the Solo tier? *Recommendation: yes, on new signups only, 2-week test.*
5. **Offline/low-bandwidth mode** — Tier 2/3 markets often have patchy connectivity. Service worker + offline queue? *Recommendation: Phase 4 scope, not blocker.*

---

## 11. Quick Decision Table

Use this in sales/support conversations.

| Customer says… | Route them to… |
|---|---|
| "I'm alone, I'll do bookings myself" | Solo ₹399, no PIN |
| "I have one receptionist, I want her to help but not see billing" | Solo ₹399, PIN enabled |
| "I have 2–5 doctors, one front desk" | Clinic ₹1,499 |
| "I have 8 doctors across 2 locations" | Clinic+ ₹1,499 + ₹299×3 extra = ₹2,396 |
| "I'm a visiting cardiologist at 3 clinics plus my own" | Solo ₹399 + Visiting add-on ₹199×3 = ₹996, OR clinics each pay their own + doctor doesn't |
| "We're a chain with 30 doctors across 5 cities" | Clinic+ custom quote; likely ₹8,000–12,000/mo + SSO |

---

## 12. Next Actions (Founder Checklist)

- [ ] Confirm pricing grid in §7 — or propose an alternative
- [ ] Decide on `users` table refactor (big lift but right long-term)
- [ ] Approve Phase 0 migration plan (biggest risk — backup DB, dry-run on staging)
- [ ] Identify 1–2 friendly beta clinics for Phase 2 (target 3-doctor polyclinic in Nashik or Nagpur)
- [ ] Update landing page copy to reflect 3 tiers before Phase 1 goes live
- [ ] Draft Twilio WhatsApp multi-tenant template for approval (2–4 weeks Meta review lag)

---

*Owner: Meher • Doc version: v2.0 • Supersedes: ARCHITECTURE.md §4 (multi-doctor clinic sketch)*
