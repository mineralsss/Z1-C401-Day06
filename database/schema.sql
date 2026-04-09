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
    schedule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id       INTEGER NOT NULL,
    facility_id     INTEGER NOT NULL,
    work_date       TEXT NOT NULL,
    shift           TEXT NOT NULL CHECK (shift IN ('morning', 'afternoon')),
    max_bookings    INTEGER NOT NULL DEFAULT 50,
    booked_count    INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'full')),
    note            TEXT,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    UNIQUE (doctor_id, facility_id, work_date, shift)
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    doctor_id        INTEGER NOT NULL,
    facility_id      INTEGER NOT NULL,
    specialty_id     INTEGER,
    schedule_id      INTEGER NOT NULL,
    symptom_text     TEXT,
    booking_note     TEXT,
    nationality_type TEXT CHECK (nationality_type IN ('local', 'foreigner') OR nationality_type IS NULL),
    consultation_fee INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('pending', 'confirmed', 'completed', 'cancelled', 'no_show')),
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at     TEXT,
    cancelled_at     TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (specialty_id) REFERENCES specialties(specialty_id),
    FOREIGN KEY (schedule_id) REFERENCES doctor_schedules(schedule_id)
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_facilities_normalized_name ON facilities(normalized_name);
CREATE INDEX IF NOT EXISTS idx_specialties_normalized_name ON specialties(normalized_name);
CREATE INDEX IF NOT EXISTS idx_doctors_normalized_name ON doctors(normalized_name);
CREATE INDEX IF NOT EXISTS idx_doctors_facility ON doctors(facility_id);
CREATE INDEX IF NOT EXISTS idx_doctor_schedules_doctor_date ON doctor_schedules(doctor_id, work_date);
CREATE INDEX IF NOT EXISTS idx_appointments_user_status ON appointments(user_id, status);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor_status ON appointments(doctor_id, status);
CREATE INDEX IF NOT EXISTS idx_appointments_schedule ON appointments(schedule_id);

-- Trả về các ca còn chỗ đặt (booked_count < max_bookings)
CREATE VIEW IF NOT EXISTS vw_available_schedules AS
SELECT
    s.schedule_id,
    s.doctor_id,
    d.full_name        AS doctor_name,
    s.facility_id,
    f.name             AS facility_name,
    s.work_date,
    s.shift,
    s.max_bookings,
    s.booked_count,
    (s.max_bookings - s.booked_count) AS remaining_slots
FROM doctor_schedules s
JOIN doctors    d ON d.doctor_id    = s.doctor_id
JOIN facilities f ON f.facility_id  = s.facility_id
WHERE s.status = 'active'
  AND s.booked_count < s.max_bookings;

-- Trả về toàn bộ lịch sử đặt khám kèm thông tin đầy đủ
CREATE VIEW IF NOT EXISTS vw_appointment_detail AS
SELECT
    a.appointment_id,
    a.status           AS appointment_status,
    a.created_at       AS booked_at,
    u.user_id,
    u.full_name        AS patient_name,
    u.phone,
    d.doctor_id,
    d.full_name        AS doctor_name,
    f.name             AS facility_name,
    sp.name            AS specialty_name,
    s.work_date,
    s.shift,
    a.nationality_type,
    a.consultation_fee,
    a.symptom_text,
    a.booking_note
FROM appointments a
JOIN users            u  ON u.user_id      = a.user_id
JOIN doctors          d  ON d.doctor_id    = a.doctor_id
JOIN facilities       f  ON f.facility_id  = a.facility_id
JOIN doctor_schedules s  ON s.schedule_id  = a.schedule_id
LEFT JOIN specialties sp ON sp.specialty_id = a.specialty_id;
