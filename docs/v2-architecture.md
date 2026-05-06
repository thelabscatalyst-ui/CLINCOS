# ClinicOS v2 — Production Architecture & Roadmap

> Comprehensive system design document covering the next major version of ClinicOS — turning the current MVP into a production-ready clinic SaaS for the Indian market.

**Document version:** 1.0
**Last updated:** 6 May 2026
**Audience:** Product owner, engineering, future contributors

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Market Reality & Competitor Analysis](#2-market-reality--competitor-analysis)
3. [The Architectural Shift](#3-the-architectural-shift)
4. [Problem 1 — Token + Appointment Engine](#4-problem-1--token--appointment-engine)
5. [Problem 2 — Status Pipeline + Billing on Close](#5-problem-2--status-pipeline--billing-on-close)
6. [Problem 3 — Income Dashboard + Expense Tracker](#6-problem-3--income-dashboard--expense-tracker)
7. [Problem 4 — Members, Roles, Emergency, Documents](#7-problem-4--members-roles-emergency-documents)
8. [UI Restructure — Dock as Primary Nav](#8-ui-restructure--dock-as-primary-nav)
9. [Data Model Changes](#9-data-model-changes)
10. [API Surface](#10-api-surface)
11. [Build Roadmap](#11-build-roadmap)
12. [Trade-offs & Future Concerns](#12-trade-offs--future-concerns)
13. [Differentiation Pitch](#13-differentiation-pitch)
14. [Appendix — Sources](#14-appendix--sources)

---

## 1. Executive Summary

### What we're solving

The current ClinicOS MVP solves *appointment chaos* — a doctor can list slots, patients can book, walk-ins can be added. That alone is not enough to keep a clinic paying ₹399/month.

This document defines **ClinicOS v2** — a production-ready clinic SaaS that handles the full daily workflow of an Indian clinic: queue management, billing, income tracking, expense management, staff roles, emergencies, and document storage.

### The headline insight

> **Indian clinics are walk-in-first, not appointment-first.** 60–70% of OPD patients walk in without booking. Every competitor (Practo Ray, Halemind, Clinicea, DocOn) treats appointments as primary and walk-ins as edge cases. ClinicOS v2 flips the model — the **queue is primary, the appointment is just a future claim on a token**.

### Pricing strategy

| Plan | Price | Audience |
|---|---|---|
| Solo | **₹599 / month** | Individual doctor or 1-doctor clinic |
| Clinic | **₹1,499 / month** | Multi-doctor clinic (up to 5 doctors) |

Below Halemind (₹999) and far below Practo Ray (₹1,499–4,999). Single flat tier per category — no feature gating within a plan.

### Build effort

~10 weeks for one focused engineer to ship Phase 3.0 → 3.8.
**Phase 3.0–3.3 (4 weeks)** is the core revenue-generating loop and is enough to justify the price increase.

---

## 2. Market Reality & Competitor Analysis

### 2.1 The Indian OPD Truth

Three statistics that drive every design decision:

| Statistic | Implication |
|---|---|
| **60–70% of OPD patients are walk-ins** | Walk-in must be a first-class flow, not an afterthought |
| **45-min wait for 5-min consultation** (avg) | Queue visibility and live status are massive value-adds |
| **Receptionist (not doctor) runs the front desk** | Software's primary user is her, not the doctor |

### 2.2 Competitor Landscape

| Product | Pricing | Strength | Weakness |
|---|---|---|---|
| **Practo Ray** | ₹1,499–₹4,999/mo | Brand recognition, marketplace | Locked-in, expensive, "you're just a listing" |
| **Halemind** | ₹999–₹4,999/mo | Specialty templates, ABDM-ready | Heavy onboarding, complex UI |
| **Clinicea** | Quote-based (enterprise) | 20+ specialties, white-label | Built for chains, overkill for solo |
| **DocOn** | Mid-tier | Prescription/EMR | Narrow scope, weak billing |
| **DocTrue** | Mid-tier | Queue management focus | Standalone module, not full suite |
| **Lifemaan** | Free → paid tiers | Works on tablets | Newer, unproven at scale |

> **Naming caveat:** there is an existing product at `clinicos.care` — a case-notes app for medical PG residents. Different product category, but worth knowing. Brand differentiation may be needed at scale.

### 2.3 Competitor Pain Points (and How ClinicOS v2 Wins)

| Pain Point | Competitors | ClinicOS v2 |
|---|---|---|
| Walk-in is afterthought | Appointment-centric data model | Token-centric data model, appointments are pre-claims |
| ₹1,500+/month pricing | Bundle features doctors don't use | Single ₹599/mo flat plan |
| Receptionist UI is bad | Built for doctors first | Receptionist is primary user |
| Doctor must use a device | Forces login + screen time | Reception-only mode fully supported |
| Onboarding takes days | Sales calls, training, data import | 5-minute self-onboarding, no calls |
| Marketplace dependency | Patient leakage to platform | Public booking is your-domain only |
| English-only | Hindi/Marathi/Tamil missing | Bilingual UI in Phase 5 |
| Feature bloat | 200+ features, doctor uses 10 | 20 features, doctor uses 18 |

**Our wedge:** *token-first, receptionist-led, ₹599 flat, WhatsApp-native, zero training.*

---

## 3. The Architectural Shift

### 3.1 The Mistake in v1

The current schema treats `Appointment` as the primary entity — a row tied to a fixed `slot`, `duration_mins`, and `scheduled_time`. This works in theory but breaks in reality:

- A 30-minute appointment finishes in 5 minutes
- A walk-in walks in
- A booked patient arrives 2 hours late
- An emergency interrupts everything

The `slot` model can't represent any of these cleanly.

### 3.2 The v2 Model — Visit + Token

A new entity `Visit` becomes the primary thing the system tracks. An `Appointment` is now just a "pre-claim" on a future Visit.

```
        ┌─────────────────────────────────────────────┐
        │              VISIT  (one per patient/day)   │
        │                                             │
        │  • token_number: 7                          │
        │  • status: waiting | serving | done         │
        │  • check_in_time                            │
        │  • call_time                                │
        │  • complete_time                            │
        │  • bill_id (when closed)                    │
        │  • appointment_id (optional, if pre-booked) │
        │  • is_emergency                             │
        │  • source: walk_in | appointment | follow_up│
        └─────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │         APPOINTMENT  (optional, advance)    │
        │  • scheduled_time  (now: a HINT, not strict)│
        │  • patient_id                               │
        │  • status: booked | arrived | no_show       │
        └─────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │            BILL  (one per Visit)            │
        │  • items[], total, paid_amount              │
        │  • payment_mode, paid_at                    │
        └─────────────────────────────────────────────┘
```

### 3.3 Key Insight

**The queue is computed from `Visit` rows, not `Appointment` rows.** An appointment that hasn't been "checked in" yet is just future intent — it's not in the queue. The moment the patient walks in and the receptionist clicks "Check In", a Visit is created with a token, and the appointment is linked.

This single model change resolves the entire token-vs-appointment confusion.

---

## 4. Problem 1 — Token + Appointment Engine

### 4.1 State Machine

Each Visit moves through this state machine:

```
       (created on check-in)
              │
              ▼
        ┌──────────┐
        │ WAITING  │◄──────────── (re-queue if doctor skips)
        └──────────┘
              │  receptionist clicks "Call Next"
              │  OR doctor clicks "Done with this one, send next"
              ▼
        ┌──────────┐
        │ SERVING  │
        └──────────┘
              │  consultation done
              ▼
        ┌──────────┐
        │ BILLING  │  ← optional state, only if billing pending
        └──────────┘
              │  payment received OR marked free
              ▼
        ┌──────────┐
        │   DONE   │
        └──────────┘

Side states (any → terminal):
  CANCELLED  — patient told receptionist they're leaving
  NO_SHOW    — pre-booked patient never arrived (auto after T+2h past slot)
  SKIPPED    — called but absent at clinic (re-queue or escalate)
```

### 4.2 Token Assignment Logic

When a patient walks in (or arrives for an appointment), the receptionist clicks **"Check In"**. The system runs:

```python
def assign_token(patient, current_time):
    today_queue = visits.filter(date=today, status=WAITING)
    has_appointment = appointments.find(patient_id, date=today)

    if is_emergency:
        # Insert at position 0 (or after current "serving" if any)
        return new_token, queue_position=0

    if has_appointment:
        slot_time = appointment.scheduled_time
        drift = current_time - slot_time

        if drift < -30min:        # very early
            queue_position = end_of_queue
        elif -30min <= drift <= 30min:   # around slot
            # Slot in around the position where the slot would naturally fall
            queue_position = computed_from_slot_order
        elif 30min < drift <= 2h:        # late
            queue_position = end_of_queue   # flagged "was late"
        else:                             # very late (>2h)
            prompt_receptionist()
    else:  # walk-in
        queue_position = end_of_queue

    token_number = next_monotonic_token_for_today
    return Visit(token_number, queue_position)
```

### 4.3 Token vs Queue Position

**Critical distinction:**

| Field | Visibility | Behavior |
|---|---|---|
| `token_number` | Patient-visible (printed on slip) | Monotonic, never changes, never reused |
| `queue_position` | Internal (receptionist UI) | Mutable, reorders as queue evolves |

The doctor's "Now Serving" display shows `token_number`. The receptionist's queue management view shows the order based on `queue_position`.

### 4.4 Edge Case — "Booked Patient Hasn't Arrived"

**Scenario:** It's 11:00 AM. Patient X has an 11:00 AM slot. He hasn't arrived.

System shows a soft alert in the queue view:

```
┌────────────────────────────────────────────────────────┐
│  ⚠ Booked patient missing — Mr. Sharma (11:00 slot)   │
│  [ Skip & continue ]   [ Call him now ]   [ Wait 5min ]│
└────────────────────────────────────────────────────────┘
```

| Action | Behavior |
|---|---|
| **Skip & continue** | Next walk-in is called. Mr. Sharma → `delayed`. When he arrives, normal check-in inserts him into the next available position. |
| **Wait 5 min** | Alert snoozes. Doctor continues with current patient. After snooze expires, alert returns. |
| **Call him now** | Opens one-tap "Where are you?" WhatsApp template. |

After **2 hours past slot** with no arrival, system auto-marks `no_show`.

### 4.5 Edge Case — "Walk-in Waiting, Booked Patient Arrives"

Walk-in #5 has been waiting since 9 AM. Booked patient arrives at his 11 AM slot.

This is a clinic *policy* decision, not a software decision. ClinicOS v2 lets the doctor configure this in Settings:

```
Walk-in priority policy:
  ⦿ Booked patients always jump (default)
  ○ First-come-first-served once checked in
  ○ Ask me each time
```

Most clinics will pick "booked jumps". This single setting collapses 80% of edge cases.

### 4.6 Doctor's "Send Next" Workflow (Three Variants)

Different doctors will use different workflows. Support all three:

**Variant A — Doctor never touches the system**
- Receptionist clicks "Done & Call Next" each time
- Doctor walks in, sees patient, walks out, says "send next" verbally
- *Most common in Tier 2/3 cities*

**Variant B — Doctor on phone PWA**
- Doctor's phone shows a single button: "Done with current → Call next"
- Tap once, patient called via display screen + receptionist gets notified

**Variant C — Doctor on cabin laptop**
- Full queue view, sees waitlist, can preview next patient's name + history before calling

All three converge on the same backend transition: `Visit.status: SERVING → DONE` triggers the next `WAITING` visit to become `SERVING`.

### 4.7 Display Screen (Patient-Facing TV)

```
URL: /queue/{clinic_or_doctor_slug}
(Open on a TV in fullscreen, or a 2nd monitor)

┌────────────────────────────────────────────┐
│                                            │
│         NOW SERVING                        │
│                                            │
│              Token #7                      │
│           Mr. Ramesh K.                    │
│                                            │
│  Up next:    #8   #9   #10                 │
│                                            │
│  Total in queue: 12      Avg wait: 14 min  │
│                                            │
└────────────────────────────────────────────┘
```

**Implementation:** polls `/queue/{slug}/status` (JSON) every 5 seconds. **No WebSockets** — overkill for our scale (max ~30 polling clients per clinic). Switch to SSE later if needed.

---

## 5. Problem 2 — Status Pipeline + Billing on Close

### 5.1 Status Mapping

Map your terminology to the system status:

| Terminology | System status | Meaning |
|---|---|---|
| **Open** | `WAITING` | Token issued, in queue |
| **In** | `SERVING` | Patient with the doctor |
| **Closed** | `DONE` | Visit complete, billed (or marked free) |

### 5.2 Today's Visits Page (Replaces Appointments)

```
┌─────────────────────────────────────────────────────────────────┐
│  TODAY  · 6 May 2026          [+ Walk-in]  [+ Appointment]      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  NOW SERVING                                                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ #7  Ramesh Kumar    9:42 AM start   [ Done →  ]         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  WAITING (5)                                                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ #8  Priya Patel       9:30 booked    [ Call ]  [ ⋮ ]    │    │
│  │ #9  Amit Singh        walk-in        [ Call ]  [ ⋮ ]    │    │
│  │ #10 Mrs. Verma  🚨    emergency      [ Call ]  [ ⋮ ]    │    │
│  │ #11 K.R. Iyer         10:00 booked   [ Call ]  [ ⋮ ]    │    │
│  │ #12 Sahil Gupta       walk-in        [ Call ]  [ ⋮ ]    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  CLOSED TODAY (3)              [ Show all ]                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ #4  Mr. Joshi    Cash ₹500    9:15 AM    [view bill]    │    │
│  │ #5  Mrs. Khan    UPI ₹800     9:25 AM    [view bill]    │    │
│  │ #6  Anil Desai   Free         9:35 AM    [view bill]    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

The `⋮` per row gives quick actions: Move up, Move down, Mark Emergency, Cancel, No-show.

### 5.3 The Close & Bill Modal

When the doctor (or receptionist) clicks **Done →** on the current patient:

```
┌──────────────────────────────────────────────────┐
│  Closing visit — #7 Ramesh Kumar                 │
├──────────────────────────────────────────────────┤
│                                                  │
│  Quick add:  [Consultation ₹300] [+ Custom]      │
│                                                  │
│  Items                                           │
│  ┌────────────────────────────────────────────┐  │
│  │ Consultation         1 × ₹300    ₹300   ✕  │  │
│  │ Injection            1 × ₹80     ₹80    ✕  │  │
│  └────────────────────────────────────────────┘  │
│  [+ Add item]                                    │
│                                                  │
│  Subtotal:               ₹380                    │
│  Discount: [   0   ]     ₹0                      │
│  TOTAL:                  ₹380                    │
│                                                  │
│  Payment Mode:                                   │
│   ⦿ Cash    ○ UPI    ○ Card    ○ Free           │
│                                                  │
│  Notes (optional): [_______________________]     │
│                                                  │
│  [ Cancel ]   [ Save & WhatsApp Bill ]   [ Save ]│
└──────────────────────────────────────────────────┘
```

**Three close options:**

| Button | Effect |
|---|---|
| **Save & WhatsApp Bill** | Creates Bill, marks Visit DONE, sends PDF to patient, prints local receipt |
| **Save** | Creates Bill, marks Visit DONE, no patient notification |
| **Save as unpaid** | Creates Bill with `paid_amount: 0`. Visit moves to `BILLING_PENDING` substate, shows in "Pending Payments" |

### 5.4 Quick-Add Catalog

Receptionists must close 50+ bills a day. Speed matters.

In Settings → Pricing Catalog:

```
Consultation        ₹300    [⭐ pinned]
Follow-up           ₹200    [⭐ pinned]
ECG                 ₹150
Dressing            ₹100    [⭐ pinned]
Injection           ₹80     [⭐ pinned]
Nebulization        ₹120
```

Pinned items appear as one-tap buttons at the top of the close-bill modal.
**Three taps for the average bill:** pick consultation → pick payment mode → save.

### 5.5 State Transition Rules

| Current | Allowed transitions | Edge case |
|---|---|---|
| WAITING | SERVING, CANCELLED, NO_SHOW, SKIPPED, EMERGENCY | If doctor on break, queue freezes (no auto-call) |
| SERVING | DONE, BILLING_PENDING, EMERGENCY (interrupt) | Only one patient can be SERVING per doctor at a time |
| BILLING_PENDING | DONE | Visit reappears in "Pending Payments" until closed |
| DONE | (no transitions) | Cannot un-close. To undo: requires owner override (audit-logged) |
| CANCELLED | (no transitions) | Patient told receptionist they left; visit stays in record |
| NO_SHOW | WAITING | If patient eventually arrives, can be reactivated |

---

## 6. Problem 3 — Income Dashboard + Expense Tracker

### 6.1 Income Dashboard

Single page, four sections:

#### Section 1 — KPI Strip (top)
```
Today        ₹4,820    +12%       Pending: ₹600
This Month   ₹38,500   +8%        Last month: ₹35,600
This Year    ₹4,12,000 ─          Avg/day: ₹3,420
```

#### Section 2 — Daily Revenue Line Chart
- 30-day rolling line, hover shows breakdown
- Toggle: Total / By payment mode / By visit type

#### Section 3 — Breakdowns (3-column grid)
```
By Payment Mode      By Visit Type       By Day of Week
─────────────────    ────────────────    ──────────────
Cash       62%       Consultation 70%    Mon  ████████ 18%
UPI        31%       Procedures   18%    Tue  ██████   14%
Card        5%       Follow-ups   12%    Wed  █████    11%
Free        2%                           Thu  ███████  16%
                                         Fri  ████████ 19%
                                         Sat  ██████   13%
                                         Sun  ████     9%
```

#### Section 4 — Pending Collections (actionable)
- List of bills with `paid_amount: 0`
- Each row has [WhatsApp reminder] and [Mark paid] buttons
- This single section drives recoverable revenue — typical clinic has ₹5–15k stuck here

### 6.2 Expense Tracker

#### Categories (fixed, simple)

```
Rent              (typically 1× monthly)
Salaries          (typically monthly per staff)
Medicines/Stock   (irregular)
Equipment         (irregular)
Utilities         (electricity, water, internet — monthly)
Marketing         (irregular)
Misc              (catch-all)
```

#### Recurring expenses

Cron job creates expense rows automatically on the configured day_of_month.

```
Add recurring expense:
  Category: Rent
  Amount:   ₹8,000
  Day:      5th of every month
  Label:    Clinic rent

→ On 5th May, 5th June, etc., row auto-created with status "auto-generated"
```

### 6.3 The Profit Number

Income page shows one big number at the top:

> **Net this month: ₹15,300**

Calculated as `(income − expenses)`. This is the number every clinic owner cares about. Most software hides it behind 4 reports. ClinicOS v2 puts it front and center.

### 6.4 Optional — GST Toggle (for later)

For clinics that issue formal invoices (mostly larger ones, not solo):

- Settings → "Enable GST on bills"
- When enabled, bill items can be marked taxable, GST line appears in invoice
- Quarterly export to CSV for the doctor's CA

**Not in Phase 3** — but the schema supports it from day one (`bill_items.gst_rate`, `bill.gst_amount`, default 0).

---

## 7. Problem 4 — Members, Roles, Emergency, Documents

### 7.1 Roles

```
                    PLATFORM ADMIN          (you, the SaaS operator)
                          │
                          ▼
            ┌────────────────────────┐
            │   CLINIC OWNER         │   (subscription holder)
            └────────────────────────┘
                ▲              ▲
                │              │
       ┌────────┴───┐   ┌──────┴────────┐
       │  DOCTOR    │   │  ADMIN_STAFF  │   (clinic manager)
       └────────────┘   └───────────────┘
            ▲
            │
       ┌────┴──────────┐
       │ RECEPTIONIST  │   (front desk — queue, billing, patients)
       └───────────────┘

PATIENT — no login, accesses via signed WhatsApp links only
```

### 7.2 Permission Matrix

| Action | Owner | Admin Staff | Doctor | Receptionist |
|---|---|---|---|---|
| View today's queue | ✓ | ✓ | ✓ (own) | ✓ |
| Check in patient | ✓ | ✓ | ✓ | ✓ |
| Call next patient | ✓ | ✓ | ✓ | ✓ |
| Close visit + bill | ✓ | ✓ | ✓ | ✓ |
| Edit closed bill (audit-logged) | ✓ | ✓ | – | – |
| View income dashboard | ✓ | ✓ | own only | summary only |
| Manage expenses | ✓ | ✓ | – | – |
| Manage staff | ✓ | ✓ | – | – |
| Manage doctors | ✓ | ✓ | – | – |
| Edit price catalog | ✓ | ✓ | own only | – |
| Manage subscription/billing | ✓ | – | – | – |
| Configure clinic settings | ✓ | ✓ | – | – |
| View document vault | ✓ | ✓ | own patients | – |
| Upload to vault | ✓ | ✓ | ✓ | ✓ |
| Delete from vault | ✓ | – | – | – |

### 7.3 Doctor Mode (No-Laptop Pattern)

Three deployment modes the clinic chooses in Settings:

```
Doctor Mode:
  ⦿ Receptionist-driven   (doctor never logs in; reception runs everything)
  ○ Phone-only            (doctor uses PWA on phone for queue + done button)
  ○ Cabin terminal        (doctor has a laptop with full access)
```

**Receptionist-driven** is the mode 60–70% of Tier 2/3 clinics will use. **Optimize for it.**

In this mode:
- Doctor login is created but never used
- Receptionist's terminal is the only interface
- Doctor walks in, sees patient, walks out
- Receptionist clicks "Done & Call Next"

### 7.4 Emergency Handling

Emergency is a **Visit attribute** (`is_emergency: bool`), not a separate flow.

When set:
- Visit jumps to position 0 of the queue (or directly behind currently-serving)
- Visual marker on queue: red border + 🚨 icon
- Optional: WhatsApp ping to doctor's phone (if Phone-only mode)
- Display screen highlights it: "Emergency — Token #10 next"

Two ways to flag emergency:
1. **At check-in** — receptionist toggles "Emergency" when adding the visit
2. **Promote existing visit** — any waiting visit can be flagged emergency by receptionist via the row's `⋮` menu

When the emergency completes, queue reverts to normal order. The "interrupted" patient who was being served goes back to position 0.

### 7.5 Document Vault

#### Schema

```sql
clinic_documents
├── id
├── clinic_id (and/or doctor_id)
├── patient_id (nullable — clinic-level docs without patient)
├── visit_id (nullable — link to a specific visit)
├── kind (enum: lab_report, prescription_scan, id_proof, insurance, misc)
├── file_url (R2/S3 signed URL)
├── file_name
├── mime_type
├── file_size
├── uploaded_by (FK staff/doctor)
├── uploaded_at
└── expires_at (optional, for shared links)
```

#### Storage choice

**Cloudflare R2** — ~$0.015/GB, **no egress fees** for India-region traffic. Much cheaper than AWS S3 for our use case.

#### Access pattern

- Doctor opens patient profile → sees attached docs → clicks → fetches signed URL (15-min expiry)
- Patient gets a WhatsApp link with a longer-expiry signed URL
- **All access goes through ClinicOS** — no direct R2 URLs exposed to public

#### Privacy

Vault is PIN-protected (use existing `require_pin`).

#### Storage limits

| Plan | Vault storage |
|---|---|
| Solo (₹599) | 1 GB per clinic |
| Clinic (₹1,499) | 5 GB per clinic |

---

## 8. UI Restructure — Dock as Primary Nav

The current navbar is approaching capacity. Move all primary navigation to the side dock.

### 8.1 New Navbar (Minimal)

```
┌────────────────────────────────────────────────────────────────────┐
│  ClinicOS                                          🌙   ⚙   ⏻      │
└────────────────────────────────────────────────────────────────────┘
       brand                                       theme  settings  logout
```

That's it. Settings + Theme + Logout.

### 8.2 Side Dock (Primary Nav)

```
[ 🏠 ] Dashboard
[ 📋 ] Today's Visits     ← was "Appointments"
[ 📅 ] Calendar
[ 👥 ] Patients
[ 💰 ] Income
[ 📉 ] Expenses
[ 📁 ] Documents
[ 👨‍⚕️ ] Staff             ← (Owner/Admin only)
[ 📊 ] Reports
```

The dock is already auto-hide, reveals on left-edge hover, present on every page. Each item gets its tooltip on hover. Active page highlighted (subtle accent).

### 8.3 Settings Dropdown (Top-Right)

Clicking ⚙ opens a small dropdown:

```
  ┌────────────────────────────┐
  │ Clinic Profile             │
  │ Working Hours              │
  │ Price Catalog              │
  │ Staff & Permissions        │
  │ Subscription & Billing     │
  │ PIN Protection             │
  │ Doctor Mode                │
  │ ────────────────────────── │
  │ Help & Support             │
  └────────────────────────────┘
```

**Reduces cognitive load:** Settings is for setup-time things; dock is for daily-driver things.

---

## 9. Data Model Changes

### 9.1 New Tables

```sql
-- Replaces "active appointment" usage; appointments still exist as pre-claims
CREATE TABLE visits (
  id INTEGER PRIMARY KEY,
  doctor_id INTEGER NOT NULL,
  patient_id INTEGER NOT NULL,
  clinic_id INTEGER,
  appointment_id INTEGER,  -- NULL for walk-ins

  visit_date DATE NOT NULL,
  token_number INTEGER NOT NULL,  -- monotonic per (doctor, date)
  queue_position INTEGER,         -- mutable; ordering hint

  status VARCHAR(20),   -- WAITING|SERVING|BILLING_PENDING|DONE|CANCELLED|NO_SHOW|SKIPPED
  is_emergency BOOLEAN DEFAULT FALSE,
  source VARCHAR(20),   -- walk_in|appointment|follow_up|referral

  check_in_time TIMESTAMP,
  call_time TIMESTAMP,
  complete_time TIMESTAMP,

  bill_id INTEGER,      -- set once closed
  notes TEXT,
  created_by INTEGER,   -- staff who checked in

  UNIQUE(doctor_id, visit_date, token_number)
);

CREATE TABLE bills (
  id INTEGER PRIMARY KEY,
  visit_id INTEGER UNIQUE,
  doctor_id INTEGER NOT NULL,
  clinic_id INTEGER,
  patient_id INTEGER NOT NULL,

  subtotal NUMERIC(10,2),
  discount NUMERIC(10,2) DEFAULT 0,
  gst_amount NUMERIC(10,2) DEFAULT 0,
  total NUMERIC(10,2),

  paid_amount NUMERIC(10,2) DEFAULT 0,
  payment_mode VARCHAR(20),  -- cash|upi|card|insurance|free|partial
  paid_at TIMESTAMP,

  notes TEXT,
  created_by INTEGER,
  created_at TIMESTAMP
);

CREATE TABLE bill_items (
  id INTEGER PRIMARY KEY,
  bill_id INTEGER,
  description VARCHAR(200),
  category VARCHAR(50),  -- consultation|procedure|medicine|lab|other
  quantity INTEGER DEFAULT 1,
  unit_price NUMERIC(10,2),
  total NUMERIC(10,2),
  gst_rate NUMERIC(4,2) DEFAULT 0
);

CREATE TABLE price_catalog (
  id INTEGER PRIMARY KEY,
  doctor_id INTEGER,    -- or clinic_id for clinic-wide
  name VARCHAR(100),
  category VARCHAR(50),
  default_price NUMERIC(10,2),
  is_pinned BOOLEAN DEFAULT FALSE,  -- show as quick button
  sort_order INTEGER,
  is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE expenses (
  id INTEGER PRIMARY KEY,
  doctor_id INTEGER,
  clinic_id INTEGER,
  category VARCHAR(30),
  amount NUMERIC(10,2),
  expense_date DATE,
  description VARCHAR(300),
  recurring_id INTEGER,     -- FK if part of recurring
  receipt_doc_id INTEGER,   -- FK to clinic_documents
  created_by INTEGER,
  created_at TIMESTAMP
);

CREATE TABLE recurring_expenses (
  id INTEGER PRIMARY KEY,
  doctor_id INTEGER,
  clinic_id INTEGER,
  category VARCHAR(30),
  amount NUMERIC(10,2),
  label VARCHAR(100),
  day_of_month INTEGER,    -- 1..28 (cap to be safe)
  is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE clinic_documents (
  id INTEGER PRIMARY KEY,
  clinic_id INTEGER,
  doctor_id INTEGER,
  patient_id INTEGER,
  visit_id INTEGER,
  kind VARCHAR(30),
  file_url VARCHAR(500),
  file_name VARCHAR(200),
  mime_type VARCHAR(80),
  file_size INTEGER,
  uploaded_by INTEGER,
  uploaded_at TIMESTAMP
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  actor_type VARCHAR(20),     -- doctor|staff|owner
  actor_id INTEGER,
  clinic_id INTEGER,
  action VARCHAR(50),         -- e.g., "bill.edit_after_close"
  entity_type VARCHAR(30),    -- visit|bill|patient|...
  entity_id INTEGER,
  before JSON,
  after JSON,
  reason VARCHAR(300),
  created_at TIMESTAMP
);
```

### 9.2 Tables Modified

```sql
-- Appointments: now a "pre-claim" not the active record
ALTER TABLE appointments ADD COLUMN visit_id INTEGER;     -- linked once checked in
ALTER TABLE appointments ADD COLUMN status_v2 VARCHAR(20);
  -- booked|delayed|arrived|no_show|cancelled

-- Doctors: deployment mode
ALTER TABLE doctors ADD COLUMN doctor_mode VARCHAR(30) DEFAULT 'reception_driven';

-- Doctors / clinics: walk-in priority policy
ALTER TABLE doctors ADD COLUMN walkin_policy VARCHAR(20) DEFAULT 'booked_jumps';
```

### 9.3 Tables Phased Out

- `appointments.duration_mins` — becomes a hint, not a constraint
- `doctor_schedules` — still defines working hours and slot duration for the "advance booking" UI, but the queue itself doesn't read it
- `notifications_log` — stays, extended to cover bill PDFs and queue alerts

---

## 10. API Surface

### 10.1 Visit / Queue Endpoints

```
GET    /visits/today                  Today's full visit list (queue view)
POST   /visits/check-in               Check in a walk-in OR appointment-holder
POST   /visits/{id}/call-next         Move SERVING → DONE, next WAITING → SERVING
POST   /visits/{id}/done              Close current visit, opens bill modal
POST   /visits/{id}/skip              Mark SKIPPED, send to end of queue
POST   /visits/{id}/emergency         Promote to top
POST   /visits/{id}/cancel            Mark cancelled
POST   /visits/{id}/move              Manual reorder (drag-drop in queue)
GET    /queue/{slug}/status           Public JSON for display screen polling
GET    /queue/{slug}                  Public HTML for TV display
```

### 10.2 Bill Endpoints

```
GET    /visits/{id}/bill              View/edit bill for a visit
POST   /visits/{id}/bill              Save bill + payment
GET    /bills                         Bill history with filters
GET    /bills/{id}/pdf                PDF for WhatsApp/print
POST   /bills/{id}/whatsapp           Send PDF via Twilio
POST   /bills/{id}/edit               Edit a closed bill (audit-logged, owner only)
```

### 10.3 Catalog / Settings

```
GET/POST   /settings/price-catalog
POST       /settings/catalog/{id}/pin
POST       /settings/walkin-policy
POST       /settings/doctor-mode
```

### 10.4 Income / Expense

```
GET    /income                        Dashboard
GET    /income/export                 CSV download (this month / range)
GET    /expenses                      List + add
POST   /expenses
POST   /expenses/recurring            Create recurring rule
GET    /pnl                           Profit & loss summary
```

### 10.5 Staff / RBAC

```
GET    /staff                         List clinic staff
POST   /staff/invite                  Send invite (already exists, extend with role)
POST   /staff/{id}/role               Change role
POST   /staff/{id}/disable            Disable login
```

### 10.6 Documents

```
GET    /documents                     Vault list (filter by patient/visit/kind)
POST   /documents/upload              Multi-part upload → R2
GET    /documents/{id}                Signed URL (auth-gated)
DELETE /documents/{id}                Owner-only, audit-logged
POST   /documents/{id}/share          Generate WhatsApp-able signed link
```

---

## 11. Build Roadmap

Eight focused phases. Each is shippable on its own.

| Phase | Deliverable | Effort |
|---|---|---|
| **3.0** | Foundation refactor — `Visit` table, service layer, token assignment, status state machine, walk-in policy setting | ~2 weeks |
| **3.1** | Today's Visits page — queue-style UI with Call Next / Done / Skip / Emergency / Move | ~1 week |
| **3.2** | Display screen — public `/queue/{slug}`, polling JSON, fullscreen UI | ~3 days |
| **3.3** | Billing on Close — price catalog CRUD, bill modal with quick-add, WeasyPrint PDF, WhatsApp send, pending payments list | ~2 weeks |
| **3.4** | Income Dashboard — KPI strip, revenue line chart, breakdowns, pending collections | ~1 week |
| **3.5** | Expense Tracker — add/list, recurring expense engine, P&L | ~1 week |
| **3.6** | Members & RBAC — role enum, permission middleware, doctor mode, audit log, emergency UI | ~2 weeks |
| **3.7** | Document Vault — Cloudflare R2 integration, upload flow, patient attachments, signed URLs | ~1 week |
| **3.8** | UI Restructure — strip navbar, move nav to dock, settings dropdown | ~3 days |

**Total: ~10 weeks** for one focused engineer.

> **Strategic shipping:** Phases **3.0–3.3 (4 weeks)** form the core revenue-generating loop. Ship those first — that alone is enough to charge ₹599/mo with a straight face.

---

## 12. Trade-offs & Future Concerns

| Decision | Trade-off | When to revisit |
|---|---|---|
| 5-second polling for queue display | Simple, no WebSocket infra | If polling cost > 0.5% of CPU at 1000 clinics, switch to SSE |
| Single Postgres per environment | No multi-tenancy isolation | At ~500 clinics, consider per-tenant schemas |
| WeasyPrint for PDF | Pure Python, no Chrome | If PDF gen latency > 800ms, move to background worker |
| R2 for documents | Cheap, India-friendly egress | Add CDN signing later if traffic spikes |
| No payment gateway in bills | Avoids GST/TDS/refund complexity | When 30%+ of clinics ask for it |
| English-only UI | Faster to ship | Add Hindi (Phase 5), Marathi/Tamil later |
| No EMR/SOAP notes | Explicitly excluded for now | Re-evaluate when 40%+ of clinics ask |
| No ABDM integration | Compliance burden, slow API | Required for government clinic segment |
| Single-clinic billing per subscription | Simpler entitlement logic | Multi-clinic owner accounts at ~1000 clinics |
| Token monotonic per doctor/day | Easy to reason about | Switch to clinic-wide if multi-doctor clinics complain |

### What NOT to Build (Yet)

| Feature | Why skip |
|---|---|
| Online payment collection | Doctors trust cash/UPI QR. Adds GST/TDS complexity. |
| Insurance / TPA claims | Enormous compliance burden. Not a solo-doctor problem. |
| Full EMR (SOAP notes, vitals) | Heavy, doctors won't fill it. Start simpler. |
| Video consultation | Different product, different pricing. |
| Inventory management | Only relevant if doctor dispenses medicines. |
| Multi-branch | Already partially built — polish later. |
| Prescription | Excluded by user request for v2. |

---

## 13. Differentiation Pitch

> *Every other clinic SaaS in India treats the appointment as primary and the walk-in as awkward. ClinicOS flips it: the queue is primary, the appointment is just a future claim on a token. The receptionist runs everything from one screen — she checks patients in, the doctor sees them, she closes the bill, the patient gets their receipt on WhatsApp. Total income, total expenses, today's profit — one click. ₹599 a month, flat. No marketplace. No training calls. Five-minute setup.*

---

## 14. Appendix — Sources

Competitor research (May 2026):

- [Ray by Practo — Clinic Management Software](https://www.practo.com/providers/clinics/ray)
- [Practo Ray — Reviews and Pricing 2026 (Capterra)](https://www.capterra.com/p/167778/Ray/)
- [Top Alternatives to Practo for Clinic Management 2026](https://doccure.io/top-alternatives-to-practo-for-clinic-management-in-2026/)
- [Best Clinic Management Software in India 2026 (Doccure)](https://doccure.io/best-clinic-management-software-in-india-2026-comprehensive-review-and-comparison/)
- [Halemind — EMR Pricing & Reviews](https://www.softwaredekho.in/software/halemind)
- [Clinicea — Clinic Management Software](https://clinicea.com/)
- [7 Clinic Management Systems Powering India's Digital Health Revolution](https://allhealthtech.com/clinic-management-systems-in-india/)
- [DocTrue — Hospital Queue Management System](https://www.doctrue.in/hospital-queue-management-system)
- [OPD Queue Management System: 2026 Guide (Adrine)](https://www.adrine.in/blog/opd-queue-management-system-guide)
- [Patient Appointment System Explained (DocTrue)](https://www.doctrue.in/blogs/patient-appointment-system-explained)
- [10 Best Clinic Management Software in India 2026](https://technologycounter.com/clinic-management-software)
- [20 Best Clinic Management Software in India for 2026](https://www.softwaresuggest.com/clinic-management-software)

---

*End of document.*
