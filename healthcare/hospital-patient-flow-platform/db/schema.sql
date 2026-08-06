-- =====================================================================
-- Hospital Patient Flow & Operational Intelligence Platform
-- PostgreSQL 15+ physical schema
--
-- Layering:
--   ref_*   reference / dimension data (units, beds, staff, code sets)
--   stg_*   staging for Excel-CSV imports, kept verbatim for audit
--   dq_*    data-quality findings raised during validation
--   enc_*   encounter-grain facts (the patient journey spine)
--   ops_*   operational facts (bed movements, orders, OR, ICU)
--   qly_*   quality and patient-safety events
--   wf_*    workforce / nursing staffing
--   agg_*   derived daily aggregates the dashboards read from
--   ml_*    model registry and prediction store
--
-- Design notes:
--   * Every clinical timestamp is stored as TIMESTAMPTZ. The ingestion
--     layer localises naive Excel timestamps to the facility timezone
--     before insert, so all downstream maths is timezone-safe.
--   * mrn / national_id are stored hashed (see ref_patient). The raw
--     identifier never lands in the warehouse; the salt lives outside
--     the database. This keeps the platform inside PDPL + JCI IMS.
--   * Fact tables carry batch_id so any import can be reversed.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------
-- Enumerated domains
-- ---------------------------------------------------------------------
CREATE TYPE unit_kind AS ENUM (
    'ED', 'ICU', 'HDU', 'WARD', 'OR', 'PACU', 'OPD', 'DAYCASE', 'LDR', 'NICU', 'DIALYSIS'
);

CREATE TYPE encounter_class AS ENUM (
    'EMERGENCY', 'INPATIENT', 'OUTPATIENT', 'DAYCASE', 'OBSERVATION'
);

CREATE TYPE discharge_disposition AS ENUM (
    'HOME', 'TRANSFER_OUT', 'DAMA', 'LAMA', 'LWBS', 'DECEASED', 'ABSCONDED', 'REFERRED'
);

CREATE TYPE bed_status AS ENUM (
    'AVAILABLE', 'OCCUPIED', 'CLEANING', 'BLOCKED', 'RESERVED', 'CLOSED'
);

CREATE TYPE order_domain AS ENUM ('LAB', 'RADIOLOGY', 'CONSULT', 'PROCEDURE');

CREATE TYPE safety_event_kind AS ENUM (
    'FALL', 'PRESSURE_INJURY', 'MEDICATION_ERROR', 'HAI_CLABSI', 'HAI_CAUTI',
    'HAI_VAP', 'HAI_SSI', 'CODE_BLUE', 'RRT_ACTIVATION', 'SEPSIS_ALERT',
    'RETURN_TO_OR', 'WRONG_SITE', 'TRANSFUSION_REACTION', 'OTHER'
);

CREATE TYPE harm_level AS ENUM ('NO_HARM', 'MILD', 'MODERATE', 'SEVERE', 'DEATH');

CREATE TYPE import_state AS ENUM ('RECEIVED', 'PROFILED', 'VALIDATED', 'REJECTED', 'LOADED', 'REVERSED');

CREATE TYPE dq_severity AS ENUM ('INFO', 'WARNING', 'ERROR', 'CRITICAL');

-- ---------------------------------------------------------------------
-- Reference layer
-- ---------------------------------------------------------------------
CREATE TABLE ref_facility (
    facility_id      SERIAL PRIMARY KEY,
    code             TEXT NOT NULL UNIQUE,
    name_en          TEXT NOT NULL,
    name_ar          TEXT,
    timezone         TEXT NOT NULL DEFAULT 'Asia/Riyadh',
    licensed_beds    INTEGER NOT NULL CHECK (licensed_beds >= 0),
    ed_treatment_spaces INTEGER NOT NULL DEFAULT 0,
    cluster_name     TEXT,          -- Saudi health cluster affiliation
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ref_unit (
    unit_id          SERIAL PRIMARY KEY,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id) ON DELETE CASCADE,
    code             TEXT NOT NULL,
    name_en          TEXT NOT NULL,
    name_ar          TEXT,
    kind             unit_kind NOT NULL,
    specialty        TEXT,
    physical_beds    INTEGER NOT NULL DEFAULT 0 CHECK (physical_beds >= 0),
    -- Staffed beds is the true capacity denominator; physical beds may exceed it.
    staffed_beds     INTEGER NOT NULL DEFAULT 0 CHECK (staffed_beds >= 0),
    target_occupancy NUMERIC(5,2) DEFAULT 85.00,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (facility_id, code)
);

CREATE TABLE ref_bed (
    bed_id           SERIAL PRIMARY KEY,
    unit_id          INTEGER NOT NULL REFERENCES ref_unit(unit_id) ON DELETE CASCADE,
    code             TEXT NOT NULL,
    room             TEXT,
    is_isolation     BOOLEAN NOT NULL DEFAULT FALSE,
    is_negative_pressure BOOLEAN NOT NULL DEFAULT FALSE,
    gender_restriction  CHAR(1) CHECK (gender_restriction IN ('M','F')),
    current_status   bed_status NOT NULL DEFAULT 'AVAILABLE',
    UNIQUE (unit_id, code)
);

CREATE TABLE ref_patient (
    patient_id       BIGSERIAL PRIMARY KEY,
    -- SHA-256 of (salt || MRN). Raw MRN is never persisted.
    mrn_hash         TEXT NOT NULL UNIQUE,
    birth_year       SMALLINT CHECK (birth_year BETWEEN 1900 AND 2200),
    sex              CHAR(1) CHECK (sex IN ('M','F','U')),
    nationality_group TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ref_staff (
    staff_id         SERIAL PRIMARY KEY,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id) ON DELETE CASCADE,
    staff_hash       TEXT NOT NULL,
    role             TEXT NOT NULL,           -- RN, CONSULTANT, RESIDENT, NA, ...
    home_unit_id     INTEGER REFERENCES ref_unit(unit_id),
    UNIQUE (facility_id, staff_hash)
);

-- Benchmark targets drive the RAG (red/amber/green) status on every tile.
CREATE TABLE ref_benchmark (
    benchmark_id     SERIAL PRIMARY KEY,
    metric_key       TEXT NOT NULL,
    scope            TEXT NOT NULL DEFAULT 'FACILITY',   -- FACILITY | UNIT_KIND | UNIT
    scope_value      TEXT,
    target_value     NUMERIC(12,4),
    amber_threshold  NUMERIC(12,4),
    red_threshold    NUMERIC(12,4),
    -- TRUE when a higher number is better (e.g. satisfaction); FALSE for wait times.
    higher_is_better BOOLEAN NOT NULL DEFAULT FALSE,
    source           TEXT,                                -- CBAHI | JCI | MAGNET | HSTP | INTERNAL
    UNIQUE (metric_key, scope, scope_value)
);

-- ---------------------------------------------------------------------
-- Staging + data quality layer
-- ---------------------------------------------------------------------
CREATE TABLE stg_import_batch (
    batch_id         BIGSERIAL PRIMARY KEY,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    dataset          TEXT NOT NULL,          -- encounters | ed_visits | bed_movements | ...
    source_filename  TEXT NOT NULL,
    source_sha256    TEXT NOT NULL,
    sheet_name       TEXT,
    row_count        INTEGER NOT NULL DEFAULT 0,
    accepted_rows    INTEGER NOT NULL DEFAULT 0,
    rejected_rows    INTEGER NOT NULL DEFAULT 0,
    quality_score    NUMERIC(5,2),
    state            import_state NOT NULL DEFAULT 'RECEIVED',
    column_mapping   JSONB,                  -- detected header -> canonical field
    profile          JSONB,                  -- per-column type/null/cardinality profile
    uploaded_by      TEXT,
    uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    loaded_at        TIMESTAMPTZ
);
CREATE INDEX idx_batch_facility_dataset ON stg_import_batch (facility_id, dataset, uploaded_at DESC);
-- The same file cannot be loaded twice into the same dataset.
CREATE UNIQUE INDEX uq_batch_content ON stg_import_batch (facility_id, dataset, source_sha256)
    WHERE state <> 'REVERSED';

CREATE TABLE stg_import_row (
    row_id           BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT NOT NULL REFERENCES stg_import_batch(batch_id) ON DELETE CASCADE,
    source_row_number INTEGER NOT NULL,
    payload          JSONB NOT NULL,
    is_rejected      BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_stg_row_batch ON stg_import_row (batch_id) WHERE is_rejected;

CREATE TABLE dq_finding (
    finding_id       BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT NOT NULL REFERENCES stg_import_batch(batch_id) ON DELETE CASCADE,
    rule_code        TEXT NOT NULL,
    severity         dq_severity NOT NULL,
    column_name      TEXT,
    affected_rows    INTEGER NOT NULL DEFAULT 0,
    sample_rows      INTEGER[] DEFAULT '{}',
    message_en       TEXT NOT NULL,
    message_ar       TEXT,
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_dq_batch_sev ON dq_finding (batch_id, severity);

-- ---------------------------------------------------------------------
-- Encounter spine
-- ---------------------------------------------------------------------
CREATE TABLE enc_encounter (
    encounter_id     BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    patient_id       BIGINT NOT NULL REFERENCES ref_patient(patient_id),
    source_encounter_no TEXT NOT NULL,
    class            encounter_class NOT NULL,
    admitting_unit_id INTEGER REFERENCES ref_unit(unit_id),
    discharge_unit_id INTEGER REFERENCES ref_unit(unit_id),
    specialty        TEXT,
    primary_diagnosis_code TEXT,             -- ICD-10-AM
    drg_code         TEXT,
    is_elective      BOOLEAN,

    -- Journey timestamps. Nullable by design: not every encounter has every stage.
    registration_at  TIMESTAMPTZ,
    admission_at     TIMESTAMPTZ,
    admission_decision_at TIMESTAMPTZ,
    bed_requested_at TIMESTAMPTZ,
    bed_assigned_at  TIMESTAMPTZ,
    ward_arrival_at  TIMESTAMPTZ,
    discharge_order_at TIMESTAMPTZ,
    discharge_ready_at TIMESTAMPTZ,
    discharge_at     TIMESTAMPTZ,

    disposition      discharge_disposition,
    is_death         BOOLEAN NOT NULL DEFAULT FALSE,
    -- Denormalised for query speed; recomputed by the analytics layer.
    los_hours        NUMERIC(10,2),
    is_readmission_30d BOOLEAN,
    index_encounter_id BIGINT REFERENCES enc_encounter(encounter_id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (facility_id, source_encounter_no),
    CONSTRAINT chk_discharge_after_admit
        CHECK (discharge_at IS NULL OR admission_at IS NULL OR discharge_at >= admission_at)
);
CREATE INDEX idx_enc_admission ON enc_encounter (facility_id, admission_at);
CREATE INDEX idx_enc_discharge ON enc_encounter (facility_id, discharge_at);
CREATE INDEX idx_enc_patient ON enc_encounter (patient_id, discharge_at);
CREATE INDEX idx_enc_unit ON enc_encounter (admitting_unit_id, admission_at);

CREATE TABLE enc_ed_visit (
    ed_visit_id      BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    encounter_id     BIGINT NOT NULL UNIQUE REFERENCES enc_encounter(encounter_id) ON DELETE CASCADE,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),

    arrival_at       TIMESTAMPTZ NOT NULL,
    arrival_mode     TEXT,                   -- WALK_IN | AMBULANCE | REFERRAL | TRANSFER
    triage_at        TIMESTAMPTZ,
    ctas_level       SMALLINT CHECK (ctas_level BETWEEN 1 AND 5),
    room_at          TIMESTAMPTZ,            -- placed in a treatment space
    physician_at     TIMESTAMPTZ,            -- first physician contact
    disposition_at   TIMESTAMPTZ,            -- disposition decision
    departure_at     TIMESTAMPTZ,            -- physically left the ED
    ed_disposition   TEXT,                   -- ADMIT | DISCHARGE | TRANSFER | LWBS | LAMA | DEATH
    is_lwbs          BOOLEAN NOT NULL DEFAULT FALSE,
    is_lama          BOOLEAN NOT NULL DEFAULT FALSE,
    is_72h_revisit   BOOLEAN,
    on_ventilator    BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT chk_ed_sequence
        CHECK (departure_at IS NULL OR departure_at >= arrival_at)
);
CREATE INDEX idx_ed_arrival ON enc_ed_visit (facility_id, arrival_at);
CREATE INDEX idx_ed_ctas ON enc_ed_visit (facility_id, ctas_level, arrival_at);

-- ---------------------------------------------------------------------
-- Operational facts
-- ---------------------------------------------------------------------
CREATE TABLE ops_bed_movement (
    movement_id      BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    encounter_id     BIGINT NOT NULL REFERENCES enc_encounter(encounter_id) ON DELETE CASCADE,
    unit_id          INTEGER NOT NULL REFERENCES ref_unit(unit_id),
    bed_id           INTEGER REFERENCES ref_bed(bed_id),
    seq_no           SMALLINT NOT NULL,
    in_at            TIMESTAMPTZ NOT NULL,
    out_at           TIMESTAMPTZ,
    movement_reason  TEXT,                   -- ADMISSION | TRANSFER | ESCALATION | STEPDOWN | DISCHARGE
    -- TRUE when a patient sat in a unit that was not clinically indicated
    is_outlier_placement BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (encounter_id, seq_no),
    CONSTRAINT chk_move_window CHECK (out_at IS NULL OR out_at >= in_at)
);
CREATE INDEX idx_move_unit_window ON ops_bed_movement (unit_id, in_at, out_at);
CREATE INDEX idx_move_encounter ON ops_bed_movement (encounter_id, seq_no);

CREATE TABLE ops_order (
    order_id         BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    encounter_id     BIGINT NOT NULL REFERENCES enc_encounter(encounter_id) ON DELETE CASCADE,
    domain           order_domain NOT NULL,
    order_code       TEXT,
    order_name       TEXT,
    modality         TEXT,                   -- CT | MRI | XR | US for radiology
    is_stat          BOOLEAN NOT NULL DEFAULT FALSE,
    ordered_at       TIMESTAMPTZ NOT NULL,
    collected_at     TIMESTAMPTZ,            -- specimen collection / patient in scanner
    performed_at     TIMESTAMPTZ,
    resulted_at      TIMESTAMPTZ,            -- verified result available
    acknowledged_at  TIMESTAMPTZ,
    responding_specialty TEXT,               -- consults
    CONSTRAINT chk_order_window CHECK (resulted_at IS NULL OR resulted_at >= ordered_at)
);
CREATE INDEX idx_order_domain_time ON ops_order (domain, ordered_at);
CREATE INDEX idx_order_encounter ON ops_order (encounter_id, domain);

CREATE TABLE ops_or_case (
    or_case_id       BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    encounter_id     BIGINT NOT NULL REFERENCES enc_encounter(encounter_id) ON DELETE CASCADE,
    theatre_unit_id  INTEGER REFERENCES ref_unit(unit_id),
    theatre_code     TEXT,
    procedure_code   TEXT,
    specialty        TEXT,
    is_emergency     BOOLEAN NOT NULL DEFAULT FALSE,
    scheduled_start_at TIMESTAMPTZ,
    holding_at       TIMESTAMPTZ,
    wheels_in_at     TIMESTAMPTZ,
    anesthesia_start_at TIMESTAMPTZ,
    incision_at      TIMESTAMPTZ,
    closure_at       TIMESTAMPTZ,
    wheels_out_at    TIMESTAMPTZ,
    pacu_in_at       TIMESTAMPTZ,
    pacu_out_at      TIMESTAMPTZ,
    is_cancelled     BOOLEAN NOT NULL DEFAULT FALSE,
    cancellation_reason TEXT
);
CREATE INDEX idx_or_case_time ON ops_or_case (theatre_unit_id, wheels_in_at);

CREATE TABLE ops_icu_stay (
    icu_stay_id      BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    encounter_id     BIGINT NOT NULL REFERENCES enc_encounter(encounter_id) ON DELETE CASCADE,
    unit_id          INTEGER NOT NULL REFERENCES ref_unit(unit_id),
    admit_at         TIMESTAMPTZ NOT NULL,
    discharge_at     TIMESTAMPTZ,
    apache_ii        SMALLINT,
    ventilated_hours NUMERIC(8,2),
    is_readmission_48h BOOLEAN,
    outcome          TEXT                    -- SURVIVED | DIED | TRANSFERRED
);
CREATE INDEX idx_icu_unit_window ON ops_icu_stay (unit_id, admit_at, discharge_at);

CREATE TABLE ops_vitals_ews (
    vitals_id        BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    encounter_id     BIGINT NOT NULL REFERENCES enc_encounter(encounter_id) ON DELETE CASCADE,
    recorded_at      TIMESTAMPTZ NOT NULL,
    respiratory_rate SMALLINT,
    spo2             SMALLINT,
    on_oxygen        BOOLEAN,
    systolic_bp      SMALLINT,
    heart_rate       SMALLINT,
    temperature_c    NUMERIC(4,1),
    consciousness    TEXT,                   -- A | C | V | P | U (ACVPU)
    news2_score      SMALLINT,               -- computed by the analytics layer
    news2_band       TEXT                    -- LOW | LOW_MEDIUM | MEDIUM | HIGH
);
CREATE INDEX idx_vitals_enc_time ON ops_vitals_ews (encounter_id, recorded_at);

-- ---------------------------------------------------------------------
-- Quality and patient safety
-- ---------------------------------------------------------------------
CREATE TABLE qly_safety_event (
    event_id         BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    encounter_id     BIGINT REFERENCES enc_encounter(encounter_id) ON DELETE SET NULL,
    unit_id          INTEGER REFERENCES ref_unit(unit_id),
    kind             safety_event_kind NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL,
    harm             harm_level NOT NULL DEFAULT 'NO_HARM',
    -- Present-on-admission flag separates hospital-acquired from imported harm.
    present_on_admission BOOLEAN NOT NULL DEFAULT FALSE,
    pressure_injury_stage TEXT,
    medication_error_stage TEXT,             -- PRESCRIBING | TRANSCRIBING | DISPENSING | ADMINISTRATION
    detail           JSONB,
    is_sentinel      BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_safety_kind_time ON qly_safety_event (facility_id, kind, occurred_at);
CREATE INDEX idx_safety_unit_time ON qly_safety_event (unit_id, occurred_at);

CREATE TABLE qly_sepsis_bundle (
    sepsis_id        BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    encounter_id     BIGINT NOT NULL REFERENCES enc_encounter(encounter_id) ON DELETE CASCADE,
    recognition_at   TIMESTAMPTZ NOT NULL,
    lactate_at       TIMESTAMPTZ,
    cultures_at      TIMESTAMPTZ,
    antibiotics_at   TIMESTAMPTZ,
    fluids_at        TIMESTAMPTZ,
    bundle_complete_1h BOOLEAN,
    bundle_complete_3h BOOLEAN,
    outcome          TEXT
);

CREATE TABLE qly_patient_experience (
    survey_id        BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    unit_id          INTEGER REFERENCES ref_unit(unit_id),
    encounter_id     BIGINT REFERENCES enc_encounter(encounter_id) ON DELETE SET NULL,
    surveyed_at      TIMESTAMPTZ NOT NULL,
    overall_rating   SMALLINT CHECK (overall_rating BETWEEN 0 AND 10),
    would_recommend  SMALLINT CHECK (would_recommend BETWEEN 0 AND 10),
    domain_scores    JSONB
);
CREATE INDEX idx_experience_time ON qly_patient_experience (facility_id, surveyed_at);

-- ---------------------------------------------------------------------
-- Workforce / nursing
-- ---------------------------------------------------------------------
CREATE TABLE wf_staffing_day (
    staffing_id      BIGSERIAL PRIMARY KEY,
    batch_id         BIGINT REFERENCES stg_import_batch(batch_id) ON DELETE SET NULL,
    unit_id          INTEGER NOT NULL REFERENCES ref_unit(unit_id),
    service_date     DATE NOT NULL,
    shift            TEXT NOT NULL DEFAULT 'DAY',   -- DAY | NIGHT | ALL

    -- Hours are the currency of every nursing indicator.
    rn_productive_hours   NUMERIC(9,2) NOT NULL DEFAULT 0,
    lpn_productive_hours  NUMERIC(9,2) NOT NULL DEFAULT 0,
    na_productive_hours   NUMERIC(9,2) NOT NULL DEFAULT 0,
    non_productive_hours  NUMERIC(9,2) NOT NULL DEFAULT 0,
    overtime_hours        NUMERIC(9,2) NOT NULL DEFAULT 0,
    agency_hours          NUMERIC(9,2) NOT NULL DEFAULT 0,
    sick_leave_hours      NUMERIC(9,2) NOT NULL DEFAULT 0,
    scheduled_hours       NUMERIC(9,2) NOT NULL DEFAULT 0,

    budgeted_fte     NUMERIC(8,2),
    filled_fte       NUMERIC(8,2),
    separations      SMALLINT NOT NULL DEFAULT 0,
    headcount        SMALLINT,
    patient_days     NUMERIC(9,2),           -- may be supplied or derived from census
    UNIQUE (unit_id, service_date, shift)
);
CREATE INDEX idx_staffing_date ON wf_staffing_day (service_date, unit_id);

-- ---------------------------------------------------------------------
-- Derived aggregates (rebuilt by the analytics layer after each load)
-- ---------------------------------------------------------------------
CREATE TABLE agg_census_day (
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    unit_id          INTEGER NOT NULL REFERENCES ref_unit(unit_id),
    service_date     DATE NOT NULL,
    midnight_census  INTEGER NOT NULL DEFAULT 0,
    patient_days     NUMERIC(10,3) NOT NULL DEFAULT 0,   -- occupancy-weighted, not midnight-only
    available_bed_days NUMERIC(10,3) NOT NULL DEFAULT 0,
    admissions       INTEGER NOT NULL DEFAULT 0,
    discharges       INTEGER NOT NULL DEFAULT 0,
    transfers_in     INTEGER NOT NULL DEFAULT 0,
    transfers_out    INTEGER NOT NULL DEFAULT 0,
    deaths           INTEGER NOT NULL DEFAULT 0,
    occupancy_rate   NUMERIC(6,2),
    peak_census      INTEGER,
    PRIMARY KEY (unit_id, service_date)
);
CREATE INDEX idx_census_facility_date ON agg_census_day (facility_id, service_date);

CREATE TABLE agg_ed_hour (
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    bucket_start     TIMESTAMPTZ NOT NULL,
    arrivals         INTEGER NOT NULL DEFAULT 0,
    departures       INTEGER NOT NULL DEFAULT 0,
    census           INTEGER NOT NULL DEFAULT 0,
    boarders         INTEGER NOT NULL DEFAULT 0,
    longest_boarding_hours NUMERIC(8,2),
    longest_wait_minutes   NUMERIC(8,2),
    ventilated       INTEGER NOT NULL DEFAULT 0,
    nedocs_score     NUMERIC(8,2),
    nedocs_band      TEXT,
    PRIMARY KEY (facility_id, bucket_start)
);

CREATE TABLE agg_metric_day (
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    unit_id          INTEGER REFERENCES ref_unit(unit_id),
    service_date     DATE NOT NULL,
    metric_key       TEXT NOT NULL,
    value            NUMERIC(14,4),
    numerator        NUMERIC(14,4),
    denominator      NUMERIC(14,4),
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (facility_id, service_date, metric_key, unit_id)
);
CREATE INDEX idx_metric_key_date ON agg_metric_day (metric_key, service_date DESC);

-- ---------------------------------------------------------------------
-- Model registry + predictions
-- ---------------------------------------------------------------------
CREATE TABLE ml_model (
    model_id         SERIAL PRIMARY KEY,
    model_key        TEXT NOT NULL,          -- ed_crowding | bed_occupancy | ...
    version          TEXT NOT NULL,
    algorithm        TEXT NOT NULL,
    trained_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    training_rows    INTEGER,
    feature_names    JSONB,
    metrics          JSONB,                  -- backtest scores
    artifact_path    TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (model_key, version)
);

CREATE TABLE ml_prediction (
    prediction_id    BIGSERIAL PRIMARY KEY,
    model_id         INTEGER NOT NULL REFERENCES ml_model(model_id) ON DELETE CASCADE,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    unit_id          INTEGER REFERENCES ref_unit(unit_id),
    target_key       TEXT NOT NULL,
    horizon_at       TIMESTAMPTZ NOT NULL,
    generated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    predicted_value  NUMERIC(14,4),
    lower_bound      NUMERIC(14,4),
    upper_bound      NUMERIC(14,4),
    predicted_class  TEXT,
    probability      NUMERIC(6,4),
    actual_value     NUMERIC(14,4),          -- back-filled for drift monitoring
    drivers          JSONB                   -- top feature contributions
);
CREATE INDEX idx_pred_lookup ON ml_prediction (facility_id, target_key, horizon_at DESC);

CREATE TABLE ml_anomaly (
    anomaly_id       BIGSERIAL PRIMARY KEY,
    facility_id      INTEGER NOT NULL REFERENCES ref_facility(facility_id),
    unit_id          INTEGER REFERENCES ref_unit(unit_id),
    service_date     DATE NOT NULL,
    metric_key       TEXT NOT NULL,
    observed_value   NUMERIC(14,4),
    expected_value   NUMERIC(14,4),
    deviation_score  NUMERIC(10,4),
    severity         dq_severity NOT NULL DEFAULT 'WARNING',
    explanation_en   TEXT,
    explanation_ar   TEXT,
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_anomaly_lookup ON ml_anomaly (facility_id, service_date DESC, metric_key);

-- ---------------------------------------------------------------------
-- Access control + audit (JCI IMS.2 / PDPL traceability)
-- ---------------------------------------------------------------------
CREATE TABLE app_user (
    user_id          SERIAL PRIMARY KEY,
    email            TEXT NOT NULL UNIQUE,
    display_name     TEXT NOT NULL,
    role             TEXT NOT NULL,          -- CEO | COO | CNO | ED_DIRECTOR | QUALITY | BED_MANAGER | ANALYST | ADMIN
    facility_id      INTEGER REFERENCES ref_facility(facility_id),
    locale           TEXT NOT NULL DEFAULT 'en',
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    audit_id         BIGSERIAL PRIMARY KEY,
    user_id          INTEGER REFERENCES app_user(user_id),
    action           TEXT NOT NULL,
    object_type      TEXT,
    object_id        TEXT,
    detail           JSONB,
    ip_address       INET,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_time ON audit_log (occurred_at DESC);
