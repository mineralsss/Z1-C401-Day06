PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT,
    normalized_name TEXT,
    phone TEXT,
    email TEXT,
    date_of_birth TEXT,
    gender TEXT,
    nationality_type TEXT CHECK (nationality_type IN ('local', 'foreigner') OR nationality_type IS NULL),
    identity_no TEXT,
    address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facilities (
    facility_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    normalized_name TEXT NOT NULL UNIQUE,
    address TEXT,
    province TEXT,
    latitude REAL,
    longitude REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS specialties (
    specialty_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_specialty_id INTEGER UNIQUE,
    name TEXT NOT NULL UNIQUE,
    normalized_name TEXT NOT NULL UNIQUE,
    is_master INTEGER NOT NULL DEFAULT 0 CHECK (is_master IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doctors (
    doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    degrees TEXT,
    description TEXT,
    qualification TEXT,
    raw_speciality TEXT,
    facility_id INTEGER NOT NULL,
    price_local INTEGER NOT NULL DEFAULT 0,
    price_foreigner INTEGER NOT NULL DEFAULT 0,
    profile_type TEXT NOT NULL DEFAULT 'doctor' CHECK (profile_type IN ('doctor', 'service', 'unknown')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    UNIQUE (normalized_name, facility_id)
);

CREATE TABLE IF NOT EXISTS doctor_specialties (
    doctor_id INTEGER NOT NULL,
    specialty_id INTEGER NOT NULL,
    PRIMARY KEY (doctor_id, specialty_id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
    FOREIGN KEY (specialty_id) REFERENCES specialties(specialty_id)
);

CREATE TABLE IF NOT EXISTS doctor_schedules (
    schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL,
    facility_id INTEGER NOT NULL,
    work_date TEXT NOT NULL,
    shift TEXT NOT NULL CHECK (shift IN ('morning', 'afternoon', 'evening', 'full_day', 'custom')),
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    UNIQUE (doctor_id, work_date, shift, start_at, end_at)
);

CREATE TABLE IF NOT EXISTS doctor_schedule_slots (
    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    slot_date TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'booked', 'blocked', 'completed', 'cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (schedule_id) REFERENCES doctor_schedules(schedule_id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
    UNIQUE (doctor_id, start_at, end_at)
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    facility_id INTEGER NOT NULL,
    specialty_id INTEGER,
    slot_id INTEGER NOT NULL UNIQUE,
    symptom_text TEXT,
    booking_note TEXT,
    nationality_type TEXT CHECK (nationality_type IN ('local', 'foreigner') OR nationality_type IS NULL),
    consultation_fee INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('pending', 'confirmed', 'completed', 'cancelled', 'no_show')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TEXT,
    cancelled_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (specialty_id) REFERENCES specialties(specialty_id),
    FOREIGN KEY (slot_id) REFERENCES doctor_schedule_slots(slot_id)
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_facilities_normalized_name ON facilities(normalized_name);
CREATE INDEX IF NOT EXISTS idx_specialties_normalized_name ON specialties(normalized_name);
CREATE INDEX IF NOT EXISTS idx_doctors_normalized_name ON doctors(normalized_name);
CREATE INDEX IF NOT EXISTS idx_doctors_facility ON doctors(facility_id);
CREATE INDEX IF NOT EXISTS idx_doctor_schedules_doctor_date ON doctor_schedules(doctor_id, work_date);
CREATE INDEX IF NOT EXISTS idx_slots_doctor_date_status ON doctor_schedule_slots(doctor_id, slot_date, status);
CREATE INDEX IF NOT EXISTS idx_appointments_user_status ON appointments(user_id, status);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor_status ON appointments(doctor_id, status);

CREATE VIEW IF NOT EXISTS vw_available_slots AS
SELECT
    slot.slot_id,
    slot.schedule_id,
    slot.doctor_id,
    doc.full_name AS doctor_name,
    sched.facility_id,
    fac.name AS facility_name,
    slot.slot_date,
    slot.start_at,
    slot.end_at,
    slot.status
FROM doctor_schedule_slots AS slot
JOIN doctor_schedules AS sched
    ON sched.schedule_id = slot.schedule_id
JOIN doctors AS doc
    ON doc.doctor_id = slot.doctor_id
JOIN facilities AS fac
    ON fac.facility_id = sched.facility_id
LEFT JOIN appointments AS appt
    ON appt.slot_id = slot.slot_id
    AND appt.status IN ('pending', 'confirmed')
WHERE slot.status = 'available'
  AND appt.appointment_id IS NULL;
