import os
import json
import random
import datetime
import logging
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db, get_db_path
from ai_doctor import diagnose_appliance, SYSTEM_PROMPT

# Configure structured logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("nextaura.app")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "nextaura-ai-secret-key-2026-prototype")

# Ensure database exists and is initialized safely
try:
    if not os.path.exists(get_db_path()):
        init_db()
except Exception as e:
    logger.warning("Startup database initialization notice: %s", e)

# ----------------- AUTH HELPERS -----------------

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash(f"Unauthorized. Access requires {role} privileges.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.context_processor
def inject_user():
    return {
        "current_user": {
            "id": session.get("user_id"),
            "email": session.get("email"),
            "name": session.get("full_name"),
            "role": session.get("role")
        } if "user_id" in session else None,
        "now": datetime.datetime.now()
    }

# ----------------- CORE ROUTES -----------------

@app.route("/")
def index():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.*, u.full_name, u.phone, u.locality 
        FROM technicians t
        JOIN users u ON t.user_id = u.id
        WHERE t.verified = 1
        LIMIT 6
    """)
    featured_technicians = cursor.fetchall()
    
    # Platform quick stats
    cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'completed'")
    completed_jobs_count = cursor.fetchone()[0] or 148
    
    conn.close()
    return render_template("index.html", 
                           technicians=featured_technicians,
                           completed_jobs_count=completed_jobs_count)

# ----------------- AUTHENTICATION -----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name']}!", "success")

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            elif user["role"] == "technician":
                return redirect(url_for("technician_dashboard"))
            else:
                return redirect(url_for("customer_dashboard"))
        else:
            flash("Invalid email or password. You can also use Quick Demo Switch.", "danger")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        role = request.form.get("role", "customer")
        locality = request.form.get("locality", "Indiranagar")
        address = request.form.get("address", "")

        if not full_name or not email or not password:
            flash("Please fill in all required fields.", "warning")
            return redirect(url_for("register"))

        conn = get_db()
        cursor = conn.cursor()
        try:
            hashed_pwd = generate_password_hash(password)
            cursor.execute("""
                INSERT INTO users (email, password_hash, full_name, phone, role, address, locality)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (email, hashed_pwd, full_name, phone, role, address, locality))
            new_user_id = cursor.lastrowid

            if role == "technician":
                specialties = request.form.get("specialties", "Air Conditioners, Refrigerators")
                cursor.execute("""
                    INSERT INTO technicians (user_id, specialties, experience_years, rating, locality, verified)
                    VALUES (?, ?, 3, 5.0, ?, 0)
                """, (new_user_id, specialties, locality))

            conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            conn.rollback()
            flash(f"Email already registered or error: {str(e)}", "danger")
        finally:
            conn.close()

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been securely logged out.", "info")
    return redirect(url_for("index"))

@app.route("/switch_demo_user/<role>")
def switch_demo_user(role):
    """
    Helper for seamless pitch/demo presentation to switch personas with one click.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE role = ? LIMIT 1", (role,))
    user = cursor.fetchone()
    conn.close()

    if user:
        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]
        flash(f"Switched session to {user['full_name']} ({role.upper()}).", "success")

        if role == "admin":
            return redirect(url_for("admin_dashboard"))
        elif role == "technician":
            return redirect(url_for("technician_dashboard"))
        else:
            return redirect(url_for("customer_dashboard"))
    
    flash("Demo account not found.", "danger")
    return redirect(url_for("index"))

# ----------------- 6-STEP WORKFLOW & AI DIAGNOSIS -----------------

@app.route("/diagnose")
def diagnose_page():
    conn = get_db()
    cursor = conn.cursor()
    # Fetch verified technicians for the Match & Schedule step
    cursor.execute("""
        SELECT t.*, u.full_name, u.phone, u.address 
        FROM technicians t
        JOIN users u ON t.user_id = u.id
        WHERE t.verified = 1
        ORDER BY t.rating DESC
    """)
    technicians = cursor.fetchall()
    conn.close()

    return render_template("diagnose.html", technicians=technicians)

@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    """
    AI Appliance Doctor API route.
    Evaluates symptoms, returns safe preliminary checks and indicative cost range,
    and logs diagnostic notes into SQLite.
    """
    data = request.get_json() or {}
    appliance_type = data.get("appliance_type", "Air Conditioners")
    brand_model = data.get("brand_model", "")
    symptoms = data.get("symptoms", "")
    error_code = data.get("error_code", "")

    if not symptoms:
        return jsonify({"error": "Please describe the symptoms or issues observed."}), 400

    diagnosis = diagnose_appliance(appliance_type, brand_model, symptoms, error_code)

    # Transaction handling: Persist diagnosis safely to diagnostic_logs
    diag_id = None
    conn = None
    try:
        user_id = session.get("user_id")
        conn = get_db()
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO diagnostic_logs (
                    user_id, appliance_type, brand_model, symptoms_input, error_code,
                    symptom_summary, safe_checks, cost_min, cost_max,
                    cost_breakdown_labor, cost_breakdown_parts, urgency_level, escalation_warning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                diagnosis["appliance_type"],
                diagnosis["brand_model"],
                symptoms,
                error_code,
                diagnosis["symptom_summary"],
                json.dumps(diagnosis["safe_checks"]),
                diagnosis["indicative_cost"]["min_total"],
                diagnosis["indicative_cost"]["max_total"],
                diagnosis["indicative_cost"]["labor_breakdown"],
                diagnosis["indicative_cost"]["parts_breakdown"],
                diagnosis["urgency"],
                diagnosis["safety_warning"]
            ))
            diag_id = cursor.lastrowid
        logger.info("Diagnosis successfully recorded in database (ID: %s, Appliance: %s)", diag_id, diagnosis["appliance_type"])
    except Exception as e:
        logger.error("Database write error in api_diagnose: %s", str(e), exc_info=True)
    finally:
        if conn:
            conn.close()

    diagnosis["diagnostic_log_id"] = diag_id
    return jsonify(diagnosis)

@app.route("/api/book_repair", methods=["POST"])
@login_required()
def api_book_repair():
    """
    Creates a new booking from Step 4 (Match & Schedule).
    """
    data = request.form if request.form else (request.get_json() or {})
    
    appliance_type = data.get("appliance_type", "Air Conditioners")
    brand_model = data.get("brand_model", "Standard")
    symptom_description = data.get("symptoms", "Appliance issue")
    diagnostic_log_id = data.get("diagnostic_log_id")
    technician_id = data.get("technician_id")
    preferred_date = data.get("preferred_date")
    time_slot = data.get("time_slot", "10:00 AM - 12:00 PM")
    service_address = data.get("service_address", "Customer Home Address")
    locality = data.get("locality", "Indiranagar")

    if not preferred_date:
        preferred_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    booking_code = f"NXA-BK-{random.randint(1000, 9999)}"
    customer_id = session.get("user_id")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bookings (
            booking_code, customer_id, technician_id, appliance_type, brand_model,
            symptom_description, diagnostic_log_id, preferred_date, time_slot,
            service_address, locality, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'requested')
    """, (
        booking_code, customer_id, technician_id, appliance_type, brand_model,
        symptom_description, diagnostic_log_id, preferred_date, time_slot,
        service_address, locality
    ))
    booking_id = cursor.lastrowid
    conn.commit()
    conn.close()

    flash(f"Booking {booking_code} requested successfully! The technician has been notified.", "success")
    return redirect(url_for("customer_dashboard"))

# ----------------- CUSTOMER DASHBOARD & ACTIONS -----------------

@app.route("/customer/dashboard")
@login_required(role="customer")
def customer_dashboard():
    customer_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    # Active and recent bookings
    cursor.execute("""
        SELECT b.*, 
               t.rating as tech_rating, 
               t.hourly_rate as tech_rate,
               u.full_name as tech_name,
               u.phone as tech_phone,
               q.id as quote_id,
               q.inspection_fee,
               q.labor_cost,
               q.parts_cost,
               q.parts_breakdown,
               q.total_amount,
               q.warranty_months,
               q.technician_notes,
               q.status as quote_status,
               rp.passport_code
        FROM bookings b
        LEFT JOIN technicians t ON b.technician_id = t.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN quotes q ON b.id = q.booking_id
        LEFT JOIN repair_passports rp ON b.id = rp.booking_id
        WHERE b.customer_id = ?
        ORDER BY b.id DESC
    """, (customer_id,))
    bookings = cursor.fetchall()

    # Repair Passports
    cursor.execute("""
        SELECT rp.*, u.full_name as tech_name, b.booking_code
        FROM repair_passports rp
        JOIN technicians t ON rp.technician_id = t.id
        JOIN users u ON t.user_id = u.id
        JOIN bookings b ON rp.booking_id = b.id
        WHERE rp.customer_id = ?
        ORDER BY rp.id DESC
    """, (customer_id,))
    passports = cursor.fetchall()

    # Budget & Maintenance Summary Calculations
    total_spent = sum([p["total_paid"] for p in passports]) + sum([b["total_amount"] for b in bookings if b["quote_status"] == "approved" and b["status"] != "completed"])
    total_repairs = len(bookings)
    active_repairs = len([b for b in bookings if b["status"] not in ("completed", "cancelled", "quote_rejected")])

    conn.close()
    return render_template("customer_dashboard.html",
                           bookings=bookings,
                           passports=passports,
                           total_spent=total_spent,
                           total_repairs=total_repairs,
                           active_repairs=active_repairs)

@app.route("/booking/<int:booking_id>/quote_action", methods=["POST"])
@login_required(role="customer")
def quote_action(booking_id):
    """
    Step 5: Customer explicitly approves or rejects the itemized quote.
    """
    action = request.form.get("action") # 'approve' or 'reject'
    customer_id = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    # Verify ownership
    cursor.execute("SELECT * FROM bookings WHERE id = ? AND customer_id = ?", (booking_id, customer_id))
    booking = cursor.fetchone()

    if not booking:
        conn.close()
        flash("Booking not found or unauthorized.", "danger")
        return redirect(url_for("customer_dashboard"))

    if action == "approve":
        cursor.execute("UPDATE quotes SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE booking_id = ?", (booking_id,))
        cursor.execute("UPDATE bookings SET status = 'quote_approved' WHERE id = ?", (booking_id,))
        conn.commit()
        flash("Quotation Approved! The technician is authorized to proceed with the repair.", "success")
    elif action == "reject":
        cursor.execute("UPDATE quotes SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE booking_id = ?", (booking_id,))
        cursor.execute("UPDATE bookings SET status = 'quote_rejected' WHERE id = ?", (booking_id,))
        conn.commit()
        flash("Quotation rejected. Only the base inspection fee applies.", "warning")

    conn.close()
    return redirect(url_for("customer_dashboard"))

@app.route("/booking/<int:booking_id>/dispute", methods=["POST"])
@login_required(role="customer")
def submit_dispute(booking_id):
    customer_id = session["user_id"]
    reason = request.form.get("reason", "Service Dispute")
    description = request.form.get("description", "")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT technician_id FROM bookings WHERE id = ? AND customer_id = ?", (booking_id, customer_id))
    b = cursor.fetchone()

    if b:
        cursor.execute("""
            INSERT INTO disputes (booking_id, customer_id, technician_id, reason, description, status)
            VALUES (?, ?, ?, ?, ?, 'open')
        """, (booking_id, customer_id, b["technician_id"], reason, description))
        conn.commit()
        flash("Dispute raised. NextAura Admin has been alerted to mediate within 24 hours.", "info")
    
    conn.close()
    return redirect(url_for("customer_dashboard"))

# ----------------- TECHNICIAN DASHBOARD & ACTIONS -----------------

@app.route("/technician/dashboard")
@login_required(role="technician")
def technician_dashboard():
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    # Find technician profile
    cursor.execute("SELECT * FROM technicians WHERE user_id = ?", (user_id,))
    tech = cursor.fetchone()

    if not tech:
        conn.close()
        flash("Technician profile not found.", "danger")
        return redirect(url_for("index"))

    tech_id = tech["id"]

    # Fetch assigned jobs
    cursor.execute("""
        SELECT b.*, 
               u.full_name as customer_name,
               u.phone as customer_phone,
               u.address as customer_address,
               q.id as quote_id,
               q.total_amount,
               q.status as quote_status
        FROM bookings b
        JOIN users u ON b.customer_id = u.id
        LEFT JOIN quotes q ON b.id = q.booking_id
        WHERE b.technician_id = ?
        ORDER BY b.id DESC
    """, (tech_id,))
    jobs = cursor.fetchall()

    # Earnings & statistics
    cursor.execute("""
        SELECT SUM(q.labor_cost + q.inspection_fee) as tech_earnings
        FROM quotes q
        JOIN bookings b ON q.booking_id = b.id
        WHERE b.technician_id = ? AND b.status = 'completed'
    """, (tech_id,))
    earnings_row = cursor.fetchone()
    total_earnings = earnings_row["tech_earnings"] or 0.0

    completed_count = len([j for j in jobs if j["status"] == "completed"])
    pending_count = len([j for j in jobs if j["status"] in ("requested", "accepted", "inspecting", "quoted")])

    conn.close()
    return render_template("technician_dashboard.html",
                           tech=tech,
                           jobs=jobs,
                           total_earnings=total_earnings,
                           completed_count=completed_count,
                           pending_count=pending_count)

@app.route("/technician/job/<int:booking_id>/update_status", methods=["POST"])
@login_required(role="technician")
def tech_update_status(booking_id):
    new_status = request.form.get("status")
    user_id = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM technicians WHERE user_id = ?", (user_id,))
    tech = cursor.fetchone()

    if not tech:
        conn.close()
        flash("Unauthorized technician.", "danger")
        return redirect(url_for("technician_dashboard"))

    if new_status in ('accepted', 'declined', 'inspecting', 'in_repair'):
        cursor.execute("UPDATE bookings SET status = ? WHERE id = ? AND technician_id = ?", (new_status, booking_id, tech["id"]))
        conn.commit()
        flash(f"Job status updated to '{new_status}'.", "success")

    conn.close()
    return redirect(url_for("technician_dashboard"))

@app.route("/technician/job/<int:booking_id>/submit_quote", methods=["POST"])
@login_required(role="technician")
def tech_submit_quote(booking_id):
    """
    Technician submits an itemized quotation after inspecting the appliance.
    """
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM technicians WHERE user_id = ?", (user_id,))
    tech = cursor.fetchone()

    if not tech:
        conn.close()
        flash("Unauthorized.", "danger")
        return redirect(url_for("technician_dashboard"))

    tech_id = tech["id"]
    inspection_fee = float(request.form.get("inspection_fee", 299.0))
    labor_cost = float(request.form.get("labor_cost", 450.0))
    parts_cost = float(request.form.get("parts_cost", 0.0))
    parts_desc = request.form.get("parts_breakdown", "Standard Replacement Component")
    warranty_months = int(request.form.get("warranty_months", 3))
    notes = request.form.get("technician_notes", "")

    tax_amount = round((labor_cost + parts_cost) * 0.05, 2)
    total_amount = round(inspection_fee + labor_cost + parts_cost + tax_amount, 2)

    parts_json = json.dumps({"description": parts_desc, "cost": parts_cost})

    # Check if quote already exists
    cursor.execute("SELECT id FROM quotes WHERE booking_id = ?", (booking_id,))
    existing_quote = cursor.fetchone()

    if existing_quote:
        cursor.execute("""
            UPDATE quotes SET 
                inspection_fee = ?, labor_cost = ?, parts_cost = ?, parts_breakdown = ?,
                tax_amount = ?, total_amount = ?, warranty_months = ?, technician_notes = ?,
                status = 'pending', updated_at = CURRENT_TIMESTAMP
            WHERE booking_id = ?
        """, (inspection_fee, labor_cost, parts_cost, parts_json, tax_amount, total_amount, warranty_months, notes, booking_id))
    else:
        cursor.execute("""
            INSERT INTO quotes (
                booking_id, technician_id, inspection_fee, labor_cost, parts_cost,
                parts_breakdown, tax_amount, total_amount, warranty_months, technician_notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (booking_id, tech_id, inspection_fee, labor_cost, parts_cost, parts_json, tax_amount, total_amount, warranty_months, notes))

    # Update booking status to 'quoted'
    cursor.execute("UPDATE bookings SET status = 'quoted' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()

    flash("Itemized quotation submitted! Customer will be notified for approval.", "success")
    return redirect(url_for("technician_dashboard"))

@app.route("/technician/job/<int:booking_id>/complete", methods=["POST"])
@login_required(role="technician")
def tech_complete_job(booking_id):
    """
    Step 6: Technician marks repair as completed and issues the Digital Repair Passport.
    """
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM technicians WHERE user_id = ?", (user_id,))
    tech = cursor.fetchone()

    if not tech:
        conn.close()
        flash("Unauthorized.", "danger")
        return redirect(url_for("technician_dashboard"))

    tech_id = tech["id"]
    work_summary = request.form.get("work_summary", "Completed repair & certified 100% operational test.")
    parts_replaced = request.form.get("parts_replaced", "Capacitor / Relay")

    # Fetch booking and quote details
    cursor.execute("""
        SELECT b.*, q.total_amount, q.warranty_months, u.full_name as tech_name
        FROM bookings b
        JOIN quotes q ON b.id = q.booking_id
        JOIN users u ON u.id = ?
        WHERE b.id = ?
    """, (user_id, booking_id))
    b = cursor.fetchone()

    if not b:
        conn.close()
        flash("Booking or approved quote not found.", "danger")
        return redirect(url_for("technician_dashboard"))

    passport_code = f"NXA-RP-2026-{random.randint(1000, 9999)}"
    warranty_months = b["warranty_months"] or 3
    warranty_expiry = (datetime.date.today() + datetime.timedelta(days=warranty_months * 30)).strftime("%Y-%m-%d")

    cursor.execute("""
        INSERT INTO repair_passports (
            passport_code, booking_id, customer_id, technician_id,
            appliance_type, brand_model, work_summary, replaced_parts,
            total_paid, warranty_period, warranty_expiry_date, rating
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 5)
    """, (
        passport_code, booking_id, b["customer_id"], tech_id,
        b["appliance_type"], b["brand_model"], work_summary, parts_replaced,
        b["total_amount"], f"{warranty_months} Months NextAura Guarantee",
        warranty_expiry
    ))

    # Update booking status to completed
    cursor.execute("UPDATE bookings SET status = 'completed' WHERE id = ?", (booking_id,))
    # Increment technician jobs completed
    cursor.execute("UPDATE technicians SET jobs_completed = jobs_completed + 1 WHERE id = ?", (tech_id,))
    conn.commit()
    conn.close()

    flash(f"Repair marked as Completed! Digital Repair Passport {passport_code} generated.", "success")
    return redirect(url_for("technician_dashboard"))

# ----------------- ADMIN DASHBOARD & DISPATCH -----------------

@app.route("/admin/dashboard")
@login_required(role="admin")
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()

    # All bookings with details
    cursor.execute("""
        SELECT b.*, 
               cu.full_name as customer_name, cu.phone as customer_phone,
               tu.full_name as tech_name,
               q.total_amount as quote_amount,
               q.status as quote_status
        FROM bookings b
        JOIN users cu ON b.customer_id = cu.id
        LEFT JOIN technicians t ON b.technician_id = t.id
        LEFT JOIN users tu ON t.user_id = tu.id
        LEFT JOIN quotes q ON b.id = q.booking_id
        ORDER BY b.id DESC
    """)
    all_bookings = cursor.fetchall()

    # All technicians with verification status
    cursor.execute("""
        SELECT t.*, u.full_name, u.email, u.phone 
        FROM technicians t
        JOIN users u ON t.user_id = u.id
        ORDER BY t.id DESC
    """)
    all_technicians = cursor.fetchall()

    # Disputes
    cursor.execute("""
        SELECT d.*, 
               cu.full_name as customer_name,
               b.booking_code
        FROM disputes d
        JOIN users cu ON d.customer_id = cu.id
        JOIN bookings b ON d.booking_id = b.id
        ORDER BY d.id DESC
    """)
    disputes = cursor.fetchall()

    # Analytics metrics
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
    customer_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM technicians WHERE verified = 1")
    verified_tech_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM bookings")
    total_bookings = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(total_amount) FROM quotes WHERE status = 'approved'")
    gmv_row = cursor.fetchone()
    platform_gmv = gmv_row[0] or 0.0

    conn.close()
    return render_template("admin_dashboard.html",
                           bookings=all_bookings,
                           technicians=all_technicians,
                           disputes=disputes,
                           customer_count=customer_count,
                           verified_tech_count=verified_tech_count,
                           total_bookings=total_bookings,
                           platform_gmv=platform_gmv)

@app.route("/admin/verify_technician/<int:tech_id>", methods=["POST"])
@login_required(role="admin")
def verify_technician(tech_id):
    action = request.form.get("action") # 'approve' or 'revoke'
    new_val = 1 if action == "approve" else 0

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE technicians SET verified = ? WHERE id = ?", (new_val, tech_id))
    conn.commit()
    conn.close()

    flash(f"Technician verification status updated to {'Verified' if new_val == 1 else 'Unverified'}.", "info")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/resolve_dispute/<int:dispute_id>", methods=["POST"])
@login_required(role="admin")
def resolve_dispute(dispute_id):
    resolution_notes = request.form.get("admin_notes", "Resolved after customer and technician review.")
    resolution_amount = float(request.form.get("resolution_amount", 0.0))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE disputes 
        SET status = 'resolved', admin_notes = ?, resolution_amount = ?
        WHERE id = ?
    """, (resolution_notes, resolution_amount, dispute_id))
    conn.commit()
    conn.close()

    flash("Dispute resolved successfully.", "success")
    return redirect(url_for("admin_dashboard"))

# ----------------- REPAIR PASSPORT & BUDGET TOOLS -----------------

@app.route("/passport/<passport_code>")
def view_repair_passport(passport_code):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT rp.*, 
               u.full_name as tech_name,
               u.phone as tech_phone,
               t.specialties as tech_specialties,
               cu.full_name as customer_name,
               cu.address as customer_address,
               b.booking_code,
               b.symptom_description,
               q.inspection_fee,
               q.labor_cost,
               q.parts_cost,
               q.tax_amount,
               q.parts_breakdown
        FROM repair_passports rp
        JOIN technicians t ON rp.technician_id = t.id
        JOIN users u ON t.user_id = u.id
        JOIN users cu ON rp.customer_id = cu.id
        JOIN bookings b ON rp.booking_id = b.id
        LEFT JOIN quotes q ON b.id = q.booking_id
        WHERE rp.passport_code = ?
    """, (passport_code,))
    passport = cursor.fetchone()
    conn.close()

    if not passport:
        flash("Repair Passport not found.", "warning")
        return redirect(url_for("index"))

    return render_template("repair_passport.html", p=passport)

@app.route("/budget-calculator")
def budget_calculator():
    """
    Dedicated Appliance Maintenance & Budget Planning Hub.
    """
    return render_template("budget_calculator.html")

# ----------------- RUN SERVER -----------------

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
