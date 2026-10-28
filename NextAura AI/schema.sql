-- SQLite Database Schema for NextAura AI
-- Uses CREATE TABLE IF NOT EXISTS for safe serverless /tmp and persistent environments

-- Users table: handles Customers, Technicians, and Admins
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

-- Technicians table: verified appliance repair specialists
CREATE TABLE IF NOT EXISTS technicians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    specialties TEXT NOT NULL, -- comma separated e.g. "Air Conditioners, Refrigerators"
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

-- Diagnostic Logs from AI Appliance Doctor
CREATE TABLE IF NOT EXISTS diagnostic_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    appliance_type TEXT NOT NULL,
    brand_model TEXT,
    symptoms_input TEXT NOT NULL,
    error_code TEXT,
    symptom_summary TEXT,
    safe_checks TEXT, -- JSON list of preliminary checks
    cost_min REAL,
    cost_max REAL,
    cost_breakdown_labor TEXT,
    cost_breakdown_parts TEXT,
    urgency_level TEXT DEFAULT 'Normal',
    escalation_warning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- Bookings table: 6-step workflow
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
        'requested',
        'accepted',
        'declined',
        'inspecting',
        'quoted',
        'quote_approved',
        'quote_rejected',
        'in_repair',
        'completed',
        'cancelled'
    )),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES users(id),
    FOREIGN KEY(technician_id) REFERENCES technicians(id),
    FOREIGN KEY(diagnostic_log_id) REFERENCES diagnostic_logs(id)
);

-- Itemized Quotes submitted by Technician after physical inspection
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

-- Repair Passport: Digital service logbook
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

-- Admin Disputes / Complaints table
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
