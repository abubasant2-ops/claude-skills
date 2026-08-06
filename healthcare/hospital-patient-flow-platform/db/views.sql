-- =====================================================================
-- Analytical views and materialised views.
--
-- These express the metric definitions in SQL so that BI clients
-- (Power BI, Tableau, direct psql) get exactly the numbers the API
-- serves. The Python analytics layer computes the same definitions;
-- backend/tests/test_sql_parity.py guards the two against drift.
--
-- REQUIRES: the session timezone must be the facility timezone. These
-- views bucket TIMESTAMPTZ values into days, and that bucketing resolves
-- against the session timezone. Run db/00_timezone.sql first, or the day
-- boundaries land at the UTC offset and these views will disagree with
-- the API. This is the one configuration step that silently produces
-- plausible-but-wrong numbers if it is skipped.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Patient journey: one row per encounter with every interval derived.
-- Intervals are minutes, NULL when the milestone was never recorded.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_patient_journey AS
SELECT
    e.encounter_id,
    e.facility_id,
    e.source_encounter_no,
    e.class,
    e.specialty,
    e.admitting_unit_id,
    u.name_en                       AS admitting_unit,
    u.kind                          AS admitting_unit_kind,
    ed.arrival_at,
    ed.ctas_level,
    ed.arrival_mode,
    e.admission_at,
    e.discharge_at,
    e.disposition,

    -- Emergency department segment
    EXTRACT(EPOCH FROM (ed.triage_at      - ed.arrival_at)) / 60 AS door_to_triage_min,
    EXTRACT(EPOCH FROM (ed.room_at        - ed.arrival_at)) / 60 AS door_to_room_min,
    EXTRACT(EPOCH FROM (ed.physician_at   - ed.arrival_at)) / 60 AS door_to_physician_min,
    EXTRACT(EPOCH FROM (ed.disposition_at - ed.arrival_at)) / 60 AS door_to_disposition_min,
    EXTRACT(EPOCH FROM (ed.departure_at   - ed.arrival_at)) / 60 AS ed_los_min,

    -- Boarding: the interval between deciding to admit and physically
    -- leaving the ED. This is the single most useful flow metric an ED has.
    EXTRACT(EPOCH FROM (ed.departure_at - e.admission_decision_at)) / 60 AS ed_boarding_min,

    -- Inpatient placement segment
    EXTRACT(EPOCH FROM (e.bed_assigned_at - e.bed_requested_at)) / 60 AS bed_allocation_min,
    EXTRACT(EPOCH FROM (e.ward_arrival_at - e.bed_assigned_at))   / 60 AS assignment_to_arrival_min,

    -- Discharge segment. discharge_ready_at is when the patient is
    -- clinically and administratively ready; the gap to discharge_at is
    -- pure waste (pharmacy, transport, paperwork).
    EXTRACT(EPOCH FROM (e.discharge_at - e.discharge_order_at)) / 60 AS discharge_order_to_exit_min,
    EXTRACT(EPOCH FROM (e.discharge_at - e.discharge_ready_at)) / 60 AS discharge_delay_min,

    EXTRACT(EPOCH FROM (e.discharge_at - e.admission_at)) / 3600 AS los_hours,
    e.is_death,
    e.is_readmission_30d
FROM enc_encounter e
LEFT JOIN enc_ed_visit ed ON ed.encounter_id = e.encounter_id
LEFT JOIN ref_unit u      ON u.unit_id = e.admitting_unit_id;

-- ---------------------------------------------------------------------
-- Occupancy-weighted patient days.
--
-- Midnight census under-counts short-stay activity, so patient days are
-- derived from the actual overlap between each bed movement and each
-- calendar day rather than from a midnight snapshot.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_unit_day_occupancy AS
WITH bounds AS (
    SELECT
        m.unit_id,
        m.encounter_id,
        m.in_at,
        COALESCE(m.out_at, now()) AS out_at
    FROM ops_bed_movement m
),
days AS (
    SELECT
        b.unit_id,
        b.encounter_id,
        d::date AS service_date,
        GREATEST(b.in_at,  d)                  AS seg_start,
        LEAST   (b.out_at, d + INTERVAL '1 day') AS seg_end
    FROM bounds b
    CROSS JOIN LATERAL generate_series(
        date_trunc('day', b.in_at),
        date_trunc('day', b.out_at),
        INTERVAL '1 day'
    ) AS d
)
SELECT
    u.facility_id,
    dy.unit_id,
    dy.service_date,
    COUNT(DISTINCT dy.encounter_id)                                   AS distinct_patients,
    SUM(EXTRACT(EPOCH FROM (dy.seg_end - dy.seg_start)) / 86400.0)    AS patient_days,
    u.staffed_beds                                                    AS available_beds,
    u.staffed_beds * 1.0                                              AS available_bed_days,
    ROUND((100.0 * SUM(EXTRACT(EPOCH FROM (dy.seg_end - dy.seg_start)) / 86400.0)
        / NULLIF(u.staffed_beds, 0))::numeric, 2)                                                              AS occupancy_rate
FROM days dy
JOIN ref_unit u ON u.unit_id = dy.unit_id
WHERE dy.seg_end > dy.seg_start
GROUP BY u.facility_id, dy.unit_id, dy.service_date, u.staffed_beds;

-- ---------------------------------------------------------------------
-- Capacity headlines per unit per month.
--   ALOS                 = inpatient days / discharges
--   Bed turnover rate    = discharges / staffed beds
--   Bed turnover interval= idle bed days per discharge, expressed in hours.
--     A negative BTI means the unit is running beyond staffed capacity.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_capacity_month AS
WITH occ AS (
    SELECT
        facility_id,
        unit_id,
        date_trunc('month', service_date)::date AS month_start,
        SUM(patient_days)      AS patient_days,
        SUM(available_bed_days) AS available_bed_days,
        COUNT(*)               AS days_in_period
    FROM v_unit_day_occupancy
    GROUP BY 1, 2, 3
),
flow AS (
    SELECT
        e.facility_id,
        e.discharge_unit_id AS unit_id,
        date_trunc('month', e.discharge_at)::date AS month_start,
        COUNT(*)                                           AS discharges,
        SUM(CASE WHEN e.is_death THEN 1 ELSE 0 END)        AS deaths,
        SUM(COALESCE(e.los_hours, 0)) / 24.0               AS los_days
    FROM enc_encounter e
    WHERE e.discharge_at IS NOT NULL
      AND e.class IN ('INPATIENT', 'OBSERVATION')
    GROUP BY 1, 2, 3
)
SELECT
    o.facility_id,
    o.unit_id,
    u.name_en AS unit_name,
    u.kind    AS unit_kind,
    o.month_start,
    o.patient_days,
    o.available_bed_days,
    o.days_in_period,
    ROUND((o.patient_days / NULLIF(o.days_in_period, 0))::numeric, 2)              AS average_daily_census,
    ROUND((100.0 * o.patient_days / NULLIF(o.available_bed_days, 0))::numeric, 2)  AS occupancy_rate,
    f.discharges,
    f.deaths,
    ROUND((f.los_days / NULLIF(f.discharges, 0))::numeric, 2)                      AS alos_days,
    ROUND((f.discharges::numeric / NULLIF(u.staffed_beds, 0))::numeric, 2)         AS bed_turnover_rate,
    ROUND((24.0 * (o.available_bed_days - o.patient_days) / NULLIF(f.discharges, 0))::numeric, 2)                                                                AS bed_turnover_interval_hours,
    ROUND((100.0 * f.deaths::numeric / NULLIF(f.discharges, 0))::numeric, 2)       AS mortality_rate
FROM occ o
JOIN ref_unit u ON u.unit_id = o.unit_id
LEFT JOIN flow f
       ON f.unit_id = o.unit_id
      AND f.month_start = o.month_start;

-- ---------------------------------------------------------------------
-- Emergency department daily performance.
-- LWBS and LAMA are excluded from the timing medians because an
-- unfinished visit has no meaningful door-to-disposition interval.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_ed_day AS
SELECT
    ed.facility_id,
    ed.arrival_at::date AS service_date,
    COUNT(*)                                                        AS visits,
    COUNT(*) FILTER (WHERE ed.ctas_level = 1)                       AS ctas_1,
    COUNT(*) FILTER (WHERE ed.ctas_level = 2)                       AS ctas_2,
    COUNT(*) FILTER (WHERE ed.ctas_level = 3)                       AS ctas_3,
    COUNT(*) FILTER (WHERE ed.ctas_level = 4)                       AS ctas_4,
    COUNT(*) FILTER (WHERE ed.ctas_level = 5)                       AS ctas_5,

    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (ed.triage_at - ed.arrival_at)) / 60
    ) FILTER (WHERE ed.triage_at IS NOT NULL)                       AS median_door_to_triage_min,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (ed.physician_at - ed.arrival_at)) / 60
    ) FILTER (WHERE ed.physician_at IS NOT NULL)                    AS median_door_to_physician_min,
    PERCENTILE_CONT(0.9) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (ed.physician_at - ed.arrival_at)) / 60
    ) FILTER (WHERE ed.physician_at IS NOT NULL)                    AS p90_door_to_physician_min,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (ed.departure_at - ed.arrival_at)) / 60
    ) FILTER (WHERE ed.departure_at IS NOT NULL AND NOT ed.is_lwbs) AS median_ed_los_min,

    COUNT(*) FILTER (WHERE ed.is_lwbs)                              AS lwbs_count,
    ROUND((100.0 * COUNT(*) FILTER (WHERE ed.is_lwbs) / NULLIF(COUNT(*), 0))::numeric, 2) AS lwbs_rate,
    COUNT(*) FILTER (WHERE ed.is_lama)                              AS lama_count,
    ROUND((100.0 * COUNT(*) FILTER (WHERE ed.is_lama) / NULLIF(COUNT(*), 0))::numeric, 2) AS lama_rate,
    COUNT(*) FILTER (WHERE ed.ed_disposition = 'ADMIT')             AS admissions,
    ROUND((100.0 * COUNT(*) FILTER (WHERE ed.ed_disposition = 'ADMIT')
          / NULLIF(COUNT(*), 0))::numeric, 2)                                 AS admission_rate,
    COUNT(*) FILTER (WHERE ed.is_72h_revisit)                       AS revisits_72h
FROM enc_ed_visit ed
GROUP BY ed.facility_id, ed.arrival_at::date;

-- ---------------------------------------------------------------------
-- Diagnostic turnaround. Radiology TAT is measured order -> verified
-- report; laboratory TAT is measured collection -> verified result,
-- which is the definition CBAHI audits against.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_diagnostic_turnaround AS
SELECT
    e.facility_id,
    o.ordered_at::date AS service_date,
    o.domain,
    o.modality,
    o.is_stat,
    COUNT(*) AS order_count,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (
            o.resulted_at - CASE WHEN o.domain = 'LAB'
                                 THEN COALESCE(o.collected_at, o.ordered_at)
                                 ELSE o.ordered_at END)) / 60
    ) AS median_tat_min,
    PERCENTILE_CONT(0.9) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (
            o.resulted_at - CASE WHEN o.domain = 'LAB'
                                 THEN COALESCE(o.collected_at, o.ordered_at)
                                 ELSE o.ordered_at END)) / 60
    ) AS p90_tat_min
FROM ops_order o
JOIN enc_encounter e ON e.encounter_id = o.encounter_id
WHERE o.resulted_at IS NOT NULL
GROUP BY e.facility_id, o.ordered_at::date, o.domain, o.modality, o.is_stat;

-- ---------------------------------------------------------------------
-- Safety events normalised to 1,000 patient days, the rate every
-- accreditation body expects. Raw counts are meaningless across units
-- of different sizes.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_safety_rate_month AS
WITH pd AS (
    SELECT
        facility_id,
        unit_id,
        date_trunc('month', service_date)::date AS month_start,
        SUM(patient_days) AS patient_days
    FROM v_unit_day_occupancy
    GROUP BY 1, 2, 3
),
ev AS (
    SELECT
        facility_id,
        unit_id,
        date_trunc('month', occurred_at)::date AS month_start,
        kind,
        COUNT(*) AS events,
        COUNT(*) FILTER (WHERE harm IN ('MODERATE','SEVERE','DEATH')) AS harmful_events
    FROM qly_safety_event
    WHERE NOT present_on_admission
    GROUP BY 1, 2, 3, 4
)
SELECT
    ev.facility_id,
    ev.unit_id,
    u.name_en AS unit_name,
    ev.month_start,
    ev.kind,
    ev.events,
    ev.harmful_events,
    pd.patient_days,
    ROUND((1000.0 * ev.events / NULLIF(pd.patient_days, 0))::numeric, 2) AS rate_per_1000_patient_days
FROM ev
JOIN ref_unit u ON u.unit_id = ev.unit_id
LEFT JOIN pd
       ON pd.unit_id = ev.unit_id
      AND pd.month_start = ev.month_start;

-- ---------------------------------------------------------------------
-- Nursing indicators per unit per month.
--   NCHPD  = productive nursing hours / patient days
--   RN skill mix = RN hours / all nursing hours
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_nursing_month AS
WITH pd AS (
    SELECT unit_id,
           date_trunc('month', service_date)::date AS month_start,
           SUM(patient_days) AS patient_days
    FROM v_unit_day_occupancy
    GROUP BY 1, 2
),
st AS (
    SELECT
        unit_id,
        date_trunc('month', service_date)::date AS month_start,
        SUM(rn_productive_hours)  AS rn_hours,
        SUM(lpn_productive_hours) AS lpn_hours,
        SUM(na_productive_hours)  AS na_hours,
        SUM(overtime_hours)       AS overtime_hours,
        SUM(agency_hours)         AS agency_hours,
        SUM(sick_leave_hours)     AS sick_hours,
        SUM(scheduled_hours)      AS scheduled_hours,
        SUM(non_productive_hours) AS non_productive_hours,
        AVG(budgeted_fte)         AS budgeted_fte,
        AVG(filled_fte)           AS filled_fte,
        SUM(separations)          AS separations,
        AVG(headcount)            AS avg_headcount
    FROM wf_staffing_day
    GROUP BY 1, 2
)
SELECT
    st.unit_id,
    u.facility_id,
    u.name_en AS unit_name,
    u.kind    AS unit_kind,
    st.month_start,
    pd.patient_days,
    st.rn_hours + st.lpn_hours + st.na_hours AS total_nursing_hours,
    ROUND(((st.rn_hours + st.lpn_hours + st.na_hours) / NULLIF(pd.patient_days, 0))::numeric, 2)
        AS nchpd,
    ROUND((st.rn_hours / NULLIF(pd.patient_days, 0))::numeric, 2)              AS rn_hppd,
    ROUND((100.0 * st.rn_hours
          / NULLIF(st.rn_hours + st.lpn_hours + st.na_hours, 0))::numeric, 2) AS rn_skill_mix_pct,
    -- Average patients per RN across 12-hour shifts.
    ROUND((pd.patient_days * 24.0 / NULLIF(st.rn_hours, 0))::numeric, 2)       AS nurse_to_patient_ratio,
    ROUND((100.0 * (st.rn_hours + st.lpn_hours + st.na_hours)
          / NULLIF(st.rn_hours + st.lpn_hours + st.na_hours + st.non_productive_hours, 0))::numeric, 2)
        AS staffing_utilization_pct,
    ROUND((100.0 * st.overtime_hours
          / NULLIF(st.rn_hours + st.lpn_hours + st.na_hours, 0))::numeric, 2) AS overtime_rate_pct,
    ROUND((100.0 * st.agency_hours
          / NULLIF(st.rn_hours + st.lpn_hours + st.na_hours, 0))::numeric, 2) AS agency_rate_pct,
    ROUND((100.0 * st.sick_hours / NULLIF(st.scheduled_hours, 0))::numeric, 2) AS sick_leave_rate_pct,
    ROUND((100.0 * (st.budgeted_fte - st.filled_fte)
          / NULLIF(st.budgeted_fte, 0))::numeric, 2)                          AS vacancy_rate_pct,
    ROUND((100.0 * st.separations / NULLIF(st.avg_headcount, 0))::numeric, 2)  AS turnover_rate_pct
FROM st
JOIN ref_unit u ON u.unit_id = st.unit_id
LEFT JOIN pd ON pd.unit_id = st.unit_id AND pd.month_start = st.month_start;

-- ---------------------------------------------------------------------
-- 30-day unplanned readmissions.
-- An encounter counts as an index admission only when it was a live
-- discharge; deaths and transfers-out are excluded from the denominator.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_readmission AS
WITH idx AS (
    SELECT
        encounter_id, facility_id, patient_id, discharge_at, discharge_unit_id, specialty
    FROM enc_encounter
    WHERE class IN ('INPATIENT','OBSERVATION')
      AND discharge_at IS NOT NULL
      AND NOT is_death
      AND (disposition IS NULL OR disposition NOT IN ('TRANSFER_OUT','DECEASED'))
)
SELECT
    i.facility_id,
    date_trunc('month', i.discharge_at)::date AS month_start,
    i.discharge_unit_id AS unit_id,
    i.specialty,
    COUNT(*) AS index_discharges,
    COUNT(r.encounter_id) AS readmissions_30d,
    ROUND((100.0 * COUNT(r.encounter_id) / NULLIF(COUNT(*), 0))::numeric, 2) AS readmission_rate_pct
FROM idx i
LEFT JOIN LATERAL (
    SELECT e2.encounter_id
    FROM enc_encounter e2
    WHERE e2.patient_id = i.patient_id
      AND e2.class IN ('INPATIENT','OBSERVATION')
      AND e2.admission_at > i.discharge_at
      AND e2.admission_at <= i.discharge_at + INTERVAL '30 days'
      AND COALESCE(e2.is_elective, FALSE) = FALSE
    ORDER BY e2.admission_at
    LIMIT 1
) r ON TRUE
GROUP BY 1, 2, 3, 4;

-- ---------------------------------------------------------------------
-- Materialised rollup powering the executive tiles. Refreshed at the
-- end of every successful import (see analytics/refresh.py).
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_executive_daily AS
SELECT
    c.facility_id,
    c.service_date,
    SUM(c.midnight_census)                                        AS census,
    SUM(c.admissions)                                             AS admissions,
    SUM(c.discharges)                                             AS discharges,
    SUM(c.deaths)                                                 AS deaths,
    ROUND((100.0 * SUM(c.patient_days)
          / NULLIF(SUM(c.available_bed_days), 0))::numeric, 2)              AS occupancy_rate,
    ROUND((100.0 * SUM(c.deaths) / NULLIF(SUM(c.discharges), 0))::numeric, 2) AS mortality_rate
FROM agg_census_day c
GROUP BY c.facility_id, c.service_date;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_exec_daily
    ON mv_executive_daily (facility_id, service_date);
