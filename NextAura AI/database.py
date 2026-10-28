import sqlite3
import os
import shutil
import logging
from werkzeug.security import generate_password_hash

logger = logging.getLogger("nextaura.database")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('customer', 'technician', 'admin')),
    address TEXT,
    locality TEXT DEFAULT 'Indiranagar',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS technicians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    specialties TEXT NOT NULL,
    experience_years INTEGER NOT NULL DEFAULT 5,
    rating REAL NOT NULL DEFAULT 4.8,
    reviews_count INTEGER NOT NULL DEFAULT 24,
    jobs_completed INTEGER NOT NULL DEFAULT 89,
    base_inspection_fee REAL NOT NULL DEFAULT 299.00,
    hourly_rate REAL NOT NULL DEFAULT 450.00,
    verified INTEGER NOT NULL DEFAULT 1 CHECK(verified IN (0, 1)),
    latitude REAL NOT NULL DEFAULT 12.9716,
    longitude REAL NOT NULL DEFAULT 77.5946,
    locality TEXT NOT NULL DEFAULT 'Indiranagar',
    bio TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS diagnostic_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    appliance_type TEXT NOT NULL,
    brand_model TEXT,
    symptoms_input TEXT NOT NULL,
    error_code TEXT,
    symptom_summary TEXT,
    safe_checks TEXT,
    cost_min REAL,
    cost_max REAL,
    cost_breakdown_labor TEXT,
    cost_breakdown_parts TEXT,
    urgency_level TEXT DEFAULT 'Normal',
    escalation_warning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_code TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    technician_id INTEGER,
    appliance_type TEXT NOT NULL,
    brand_model TEXT NOT NULL,
    issue_category TEXT,
    symptom_description TEXT NOT NULL,
    diagnostic_log_id INTEGER,
    preferred_date TEXT NOT NULL,
    time_slot TEXT NOT NULL,
    service_address TEXT NOT NULL,
    locality TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested' CHECK(status IN (
        'requested', 'accepted', 'declined', 'inspecting', 'quoted',
        'quote_approved', 'quote_rejected', 'in_repair', 'completed', 'cancelled'
    )),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES users(id),
    FOREIGN KEY(technician_id) REFERENCES technicians(id),
    FOREIGN KEY(diagnostic_log_id) REFERENCES diagnostic_logs(id)
);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER UNIQUE NOT NULL,
    technician_id INTEGER NOT NULL,
    inspection_fee REAL NOT NULL DEFAULT 299.00,
    labor_cost REAL NOT NULL DEFAULT 0.00,
    parts_cost REAL NOT NULL DEFAULT 0.00,
    parts_breakdown TEXT,
    tax_amount REAL NOT NULL DEFAULT 0.00,
    total_amount REAL NOT NULL DEFAULT 0.00,
    warranty_months INTEGER NOT NULL DEFAULT 3,
    technician_notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY(technician_id) REFERENCES technicians(id)
);

CREATE TABLE IF NOT EXISTS repair_passports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    passport_code TEXT UNIQUE NOT NULL,
    booking_id INTEGER UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    technician_id INTEGER NOT NULL,
    appliance_type TEXT NOT NULL,
    brand_model TEXT NOT NULL,
    work_summary TEXT NOT NULL,
    replaced_parts TEXT,
    total_paid REAL NOT NULL,
    warranty_period TEXT NOT NULL,
    warranty_expiry_date TEXT NOT NULL,
    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
    customer_feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(booking_id) REFERENCES bookings(id),
    FOREIGN KEY(customer_id) REFERENCES users(id),
    FOREIGN KEY(technician_id) REFERENCES technicians(id)
);

CREATE TABLE IF NOT EXISTS disputes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    technician_id INTEGER,
    reason TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'under_review', 'resolved', 'dismissed')),
    admin_notes TEXT,
    resolution_amount REAL DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(booking_id) REFERENCES bookings(id),
    FOREIGN KEY(customer_id) REFERENCES users(id),
    FOREIGN KEY(technician_id) REFERENCES technicians(id)
);
"""

def is_serverless():
    """
    Detects if the application is running in a serverless environment
    such as Vercel, AWS Lambda, or a container with a read-only root filesystem.
    """
    serverless_vars = [
        "VERCEL",
        "VERCEL_ENV",
        "VERCEL_REGION",
        "NOW_REGION",
        "AWS_LAMBDA_FUNCTION_NAME",
        "AWS_EXECUTION_ENV",
        "LAMBDA_TASK_ROOT",
        "SERVERLESS"
    ]
    if any(os.environ.get(var) for var in serverless_vars):
        return True

    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir.startswith(("/var/task", "/var/runtime", "/opt")):
        return True

    # Probe filesystem writability directly
    try:
        probe_path = os.path.join(current_dir, ".write_test_probe")
        with open(probe_path, "w") as f:
            f.write("probe")
        os.remove(probe_path)
        return False
    except (OSError, IOError, PermissionError):
        return True

def get_db_path():
    """
    Resolves the writable database path.
    
    IMPORTANT ARCHITECTURE NOTE:
    - In standard local execution, nextaura.db is stored in the project directory.
    - In Vercel and AWS Lambda, the root deployment directory (/var/task) is mounted
      as read-only. Attempting to write there results in:
          sqlite3.OperationalError: attempt to write a readonly database
    - On Vercel, we automatically locate the SQLite database at /tmp/nextaura.db,
      which is the only writable directory in the serverless environment.
    """
    if os.environ.get("DB_PATH"):
        return os.environ.get("DB_PATH")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    bundled_db_path = os.path.join(current_dir, "nextaura.db")

    if not is_serverless():
        return bundled_db_path

    # Serverless fallback: use writable temporary directory (/tmp)
    tmp_dir = "/tmp" if os.path.isdir("/tmp") else os.environ.get("TEMP", os.environ.get("TMP", current_dir))
    tmp_db_path = os.path.join(tmp_dir, "nextaura.db")

    # If the database does not exist in /tmp, copy the bundled one or initialize fresh
    if not os.path.exists(tmp_db_path):
        if os.path.exists(bundled_db_path):
            try:
                shutil.copyfile(bundled_db_path, tmp_db_path)
                os.chmod(tmp_db_path, 0o666)
                logger.info(f"Copied bundled database to writable serverless path: {tmp_db_path}")
            except Exception as e:
                logger.warning(f"Could not copy bundled DB to {tmp_db_path}: {e}. Initializing fresh DB.")
                init_db(tmp_db_path)
        else:
            logger.info(f"Initializing fresh database at serverless path: {tmp_db_path}")
            init_db(tmp_db_path)
    else:
        try:
            os.chmod(tmp_db_path, 0o666)
        except Exception:
            pass

    return tmp_db_path

def get_db():
    """
    Establishes and returns a connection to the SQLite database.
    Ensures tables exist and PRAGMA settings are configured.
    """
    db_path = get_db_path()

    # Ensure tables exist
    ensure_tables(db_path)

    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception as e:
        logger.debug(f"Journal mode pragma note: {e}")

    return conn

def ensure_tables(db_path=None):
    """
    Idempotently verifies that all required tables exist.
    Creates missing tables if needed without dropping data.
    """
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path, timeout=15)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='diagnostic_logs'")
        if not cursor.fetchone():
            logger.info("Tables missing in database. Executing embedded schema script...")
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            seed_demo_data(conn)
    except Exception as e:
        logger.error(f"Error ensuring tables in {db_path}: {e}")
    finally:
        conn.close()

def init_db(db_path=None):
    """
    Initializes database schema and seeds initial prototype records.
    """
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        seed_demo_data(conn)
    finally:
        conn.close()

def seed_demo_data(conn=None):
    """
    Seeds initial realistic demo users, technicians, sample bookings, and passports.
    """
    should_close = False
    if conn is None:
        conn = sqlite3.connect(get_db_path(), timeout=15)
        conn.row_factory = sqlite3.Row
        should_close = True

    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] > 0:
            return

        hashed_pwd = generate_password_hash("password123")
        users_data = [
            ("admin@nextaura.ai", hashed_pwd, "Priya Sharma (Admin)", "+91 98450 11001", "admin", "NextAura HQ, Indiranagar", "Indiranagar"),
            ("customer@nextaura.ai", hashed_pwd, "Rahul Mehta", "+91 98765 43210", "customer", "Flat 402, Sunshine Apts, 12th Main, Indiranagar", "Indiranagar"),
            ("tech.rajesh@nextaura.ai", hashed_pwd, "Rajesh Kumar", "+91 98220 54321", "technician", "Service Hub 3, Koramangala", "Koramangala"),
            ("tech.anand@nextaura.ai", hashed_pwd, "Anand Verma", "+91 98330 65432", "technician", "Service Hub 1, Indiranagar", "Indiranagar"),
            ("tech.deepak@nextaura.ai", hashed_pwd, "Deepak Joshi", "+91 98440 76543", "technician", "Service Hub 5, HSR Layout", "HSR Layout"),
        ]

        cursor.executemany("""
            INSERT INTO users (email, password_hash, full_name, phone, role, address, locality)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, users_data)

        technicians_data = [
            (3, "Air Conditioners, Refrigerators", 8, 4.9, 142, 310, 299.0, 450.0, 1, 12.9352, 77.6245, "Koramangala", "Certified HVAC & Inverter Refrigerator Specialist with 8+ years experience. Expert in Daikin, LG, Samsung, Voltas."),
            (4, "Washing Machines, Air Conditioners", 6, 4.8, 98, 220, 249.0, 400.0, 1, 12.9784, 77.6408, "Indiranagar", "Front-load & Top-load drum, motor, and PCB repair technician. Whirlpool, Bosch, IFB authorized background."),
            (5, "Air Conditioners, Refrigerators, Washing Machines", 10, 4.95, 215, 520, 349.0, 500.0, 1, 12.9121, 77.6446, "HSR Layout", "Senior Master Technician. Advanced compressor analysis, gas charge testing, inverter PCB diagnostics."),
        ]

        cursor.executemany("""
            INSERT INTO technicians (user_id, specialties, experience_years, rating, reviews_count, jobs_completed, base_inspection_fee, hourly_rate, verified, latitude, longitude, locality, bio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, technicians_data)

        cursor.execute("""
            INSERT INTO diagnostic_logs (user_id, appliance_type, brand_model, symptoms_input, error_code, symptom_summary, safe_checks, cost_min, cost_max, cost_breakdown_labor, cost_breakdown_parts, urgency_level, escalation_warning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            2,
            "Air Conditioners",
            "Voltas 1.5 Ton Split Inverter",
            "AC is blowing room-temperature air, outdoor unit makes buzzing sound every 2 minutes.",
            "None",
            "AC running but not cooling properly; outdoor compressor attempting to start.",
            '["Verify remote is set to COOL mode at 22°C (not FAN mode)", "Inspect indoor air filters for thick dust blockage", "Check if outdoor unit fan blades are obstructed by debris"]',
            1200.0,
            2800.0,
            "₹450 - ₹650 (Coil cleaning, electrical terminal check)",
            "₹750 - ₹2150 (Run capacitor replacement / relay check)",
            "Medium",
            "DO NOT attempt to open outdoor electrical casing or inspect refrigerant piping. High voltage risk."
        ))
        diag_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO bookings (booking_code, customer_id, technician_id, appliance_type, brand_model, issue_category, symptom_description, diagnostic_log_id, preferred_date, time_slot, service_address, locality, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "NXA-BK-2026-901",
            2,
            2,
            "Air Conditioners",
            "Voltas 1.5 Ton Split Inverter",
            "Cooling Failure",
            "Blowing warm air, outdoor unit humming.",
            diag_id,
            "2026-10-30",
            "10:00 AM - 12:00 PM",
            "Flat 402, Sunshine Apts, 12th Main, Indiranagar",
            "Indiranagar",
            "quoted"
        ))
        booking_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO quotes (booking_id, technician_id, inspection_fee, labor_cost, parts_cost, parts_breakdown, tax_amount, total_amount, warranty_months, technician_notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            booking_id,
            2,
            249.0,
            450.0,
            850.0,
            '{"items": [{"name": "Heavy-duty 45uF Run Capacitor (Voltas OEM)", "cost": 850.0}]}',
            80.0,
            1629.0,
            3,
            "Physical inspection revealed degraded motor capacitor (measured 12uF instead of 45uF). Fan motor and compressor windings tested safe. Replacing capacitor will restore full 100% cooling capacity.",
            "pending"
        ))

        cursor.execute("""
            INSERT INTO bookings (booking_code, customer_id, technician_id, appliance_type, brand_model, issue_category, symptom_description, preferred_date, time_slot, service_address, locality, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "NXA-BK-2026-804",
            2,
            1,
            "Washing Machines",
            "LG 7kg Front Load Wi-Fi Inverter",
            "Drain Pump / Spin Error",
            "Error OE displayed on screen, water not draining during spin cycle.",
            "2026-09-14",
            "02:00 PM - 04:00 PM",
            "Flat 402, Sunshine Apts, 12th Main, Indiranagar",
            "Indiranagar",
            "completed"
        ))
        prev_booking_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO repair_passports (passport_code, booking_id, customer_id, technician_id, appliance_type, brand_model, work_summary, replaced_parts, total_paid, warranty_period, warranty_expiry_date, rating, customer_feedback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "NXA-RP-2026-4491",
            prev_booking_id,
            2,
            1,
            "Washing Machines",
            "LG 7kg Front Load Wi-Fi Inverter",
            "Drain filter cleared of coin obstruction, drain impeller inspected, high-speed spin cycle tested with zero leakage.",
            "Drain Pump Impeller Seal OEM",
            1150.0,
            "6 Months NextAura Guarantee",
            "2027-03-14",
            5,
            "Super transparent estimate from AI Doctor beforehand, technician arrived on time and showed old vs new part!"
        ))

        conn.commit()
    except Exception as e:
        logger.error(f"Error seeding demo data: {e}")
    finally:
        if should_close:
            conn.close()

if __name__ == "__main__":
    init_db()
    print("Database path:", get_db_path())
