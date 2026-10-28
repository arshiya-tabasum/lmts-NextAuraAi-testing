# NextAura AI — Smart Home Appliance Repair & AI Doctor MVP

A full-stack prototype engineered strictly according to the **16-slide startup blueprint**:
- **Target Appliances**: Air Conditioners (ACs), Refrigerators, Washing Machines
- **Tech Stack**: Python (Flask backend), SQLite (database), HTML5 / CSS3 / Vanilla JS, Leaflet.js (map visualization).

---

## 🚀 The 6-Step Workflow Implemented

1. **Describe**: Customer enters appliance type, model details, and symptom description / error code.
2. **Understand**: "AI Appliance Doctor" API route evaluates symptoms, provides preliminary safe checks, and logs diagnostic notes.
3. **Estimate**: System displays an indicative cost range with labor and parts breakdown assumptions.
4. **Match & Schedule**: Filter verified technicians by skill, locality, and available appointment time slots on an interactive Leaflet.js map.
5. **Repair Approval**: Technician inspects appliance on-site and submits an itemized quotation requiring explicit customer approval before work proceeds.
6. **Repair Passport**: Tamper-proof digital logbook storing completed job details, warranty validity, and invoice in SQLite.

---

## 👥 Three Complete User Dashboards

- **Customer Dashboard (`/customer/dashboard`)**:
  - Appliance repair and maintenance budget tracking (annual budget gauge, replacement savings vs buying new).
  - Active booking pipeline with real-time status badges.
  - Interactive itemized quotation approval (one-click Approve / Decline).
  - Permanent Digital Repair Passports wallet with printable warranty certificate.
  - Dispute resolution trigger.

- **Technician Console (`/technician/dashboard`)**:
  - Assigned job queue.
  - Accept / Decline incoming requests.
  - Arrived & Physical Inspection status.
  - Itemized Quotation submission form (Inspection fee + Labor + Parts OEM + Tax + Warranty duration).
  - Complete job and issue the Digital Repair Passport.
  - Rating and earnings tracker.

- **Admin Dispatch & Operations (`/admin/dashboard`)**:
  - Gross Platform Volume (GMV), Total Bookings, Active Customers, Verified Specialists.
  - Technician credential verification manager (Approve / Revoke verification).
  - Live dispatch pipeline monitoring all bookings in real time.
  - Dispute & complaint resolution panel.

- **Appliance Budget & Financial Hub (`/budget-calculator`)**:
  - "Repair vs Replace" 50% Rule Calculator.
  - Annual household appliance maintenance planner.
  - Market parts and labor indicative price index (Bengaluru).

---

## 🔑 Demo Personas (1-Click Switch Available on Navbar)

| Persona | Role | Email | Password | Features Highlighted |
|---|---|---|---|---|
| **Rahul Mehta** | Customer | `customer@nextaura.ai` | `password123` | Active AC repair in "Quoted" status waiting for approval, completed Washing Machine Repair Passport |
| **Anand Verma** | Technician | `tech.anand@nextaura.ai` | `password123` | Assigned Voltas AC job, submit itemized quote, complete repair |
| **Priya Sharma** | Admin | `admin@nextaura.ai` | `password123` | Verify technician profiles, live dispatch table, resolve disputes |

---

## 🌐 Vercel Serverless Architecture & Database Note

### Why the Read-Only Database Error Occurs on Vercel:
On Vercel and AWS Lambda, the root deployment directory (`/var/task`) is mounted as a **read-only filesystem**. When SQLite attempts to write or create journal lockfiles in `/var/task/nextaura.db`, the operating system denies write access with `sqlite3.OperationalError: attempt to write a readonly database`.

### How NextAura AI Resolves This on Vercel:
1. **Automatic `/tmp` Detection (`database.py`)**:
   - `database.py` automatically detects when the application is running in a serverless environment (`VERCEL`, `AWS_LAMBDA_FUNCTION_NAME`, or read-only directory).
   - In serverless mode, it automatically places the SQLite database in the writable **`/tmp/nextaura.db`** directory.
   - If a bundled `nextaura.db` exists, it copies the data using `shutil.copyfile` and explicitly sets `0o666` permissions. If no database exists, it creates tables and seeds realistic demo data automatically.

> ⚠️ **IMPORTANT NOTE ON `/tmp` PERSISTENCE**:
> In serverless platforms like Vercel and AWS Lambda, the `/tmp` filesystem is **ephemeral and temporary**. Container instances spin down when idle, so records written to `/tmp/nextaura.db` will periodically disappear across cold starts.
> 
> **For permanent production history across all instances**:
> Connect a hosted database (such as **Neon Serverless Postgres**, **Supabase**, or **Turso LibSQL**) by setting the `DATABASE_URL` environment variable in your Vercel Project Settings.

---

## 🛠️ How to Run Locally

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Server**:
   ```bash
   python app.py
   ```

3. **Run Automated Test Suite**:
   ```bash
   python test_vercel_fix.py
   ```
