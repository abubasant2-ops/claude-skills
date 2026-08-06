"""Guard the SQL views and the Python metric modules against drift.

The platform deliberately expresses each metric twice -- once in
``db/views.sql`` for BI clients reading the warehouse directly, once in
``app/analytics/`` for the API. That only helps if the two agree, and two
implementations of the same definition drift silently unless something
checks.

These tests need a real PostgreSQL instance (the views use
``generate_series``, ``FILTER`` and ``PERCENTILE_CONT``, none of which
SQLite has) loaded with data. They skip cleanly when one is not
configured, so the default suite stays dependency-free:

    createdb hpf_parity
    psql -d hpf_parity -f db/schema.sql -f db/views.sql
    HPF_DATABASE_URL=postgresql+psycopg://... \\
        python scripts/load_demo.py --data data/samples
    HPF_TEST_POSTGRES_URL=postgresql+psycopg://... \\
        python -m pytest backend/tests/test_sql_parity.py -v
"""

from __future__ import annotations

import os
import calendar
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PARITY_URL = os.environ.get("HPF_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not PARITY_URL,
    reason="Set HPF_TEST_POSTGRES_URL to a loaded PostgreSQL warehouse to run parity checks",
)

# Rates are compared to 0.01; medians to 0.01 minutes. Anything looser
# would let a genuine definitional difference hide inside the tolerance.
TOLERANCE = 0.01


@pytest.fixture(scope="module")
def pg_session():
    engine = create_engine(PARITY_URL, future=True)
    factory = sessionmaker(bind=engine, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="module")
def busiest_ed_day(pg_session) -> date:
    """Pick a day with enough volume that a definitional gap would show."""
    row = pg_session.execute(
        text("SELECT service_date FROM v_ed_day ORDER BY visits DESC LIMIT 1")
    ).first()
    if row is None:
        pytest.skip("No ED data loaded in the parity database")
    return row[0]


def _python_ed(session, day: date) -> dict:
    from app.analytics import repository
    from app.analytics.common import interval_minutes, median_minutes, safe_div

    visits = repository.load_ed_visits(session, 1, day, day)
    if visits.empty:
        pytest.skip(f"No ED visits on {day}")

    lwbs = int(visits["is_lwbs"].fillna(False).astype(bool).sum())
    admitted = int((visits["ed_disposition"] == "ADMIT").sum())
    return {
        "visits": len(visits),
        "median_door_to_physician_min": median_minutes(
            interval_minutes(visits["physician_at"], visits["arrival_at"])
        ),
        "lwbs_rate": safe_div(lwbs, len(visits), scale=100),
        "admission_rate": safe_div(admitted, len(visits), scale=100),
    }


def test_ed_daily_metrics_match(pg_session, busiest_ed_day):
    sql = pg_session.execute(
        text(
            """
            SELECT visits, median_door_to_physician_min, lwbs_rate, admission_rate
            FROM v_ed_day WHERE service_date = :day
            """
        ),
        {"day": busiest_ed_day},
    ).mappings().first()

    python = _python_ed(pg_session, busiest_ed_day)

    assert sql["visits"] == python["visits"]
    for field in ("median_door_to_physician_min", "lwbs_rate", "admission_rate"):
        assert float(sql[field]) == pytest.approx(python[field], abs=TOLERANCE), (
            f"{field} differs between v_ed_day and the Python ED module on {busiest_ed_day}"
        )


def test_patient_days_match(pg_session):
    """The occupancy denominator underpins capacity, nursing and harm rates.

    If ``v_unit_day_occupancy`` and ``expand_to_days`` disagree here, every
    rate built on patient days disagrees too.
    """
    from app.analytics import repository
    from app.analytics.capacity import unit_day_occupancy

    window = pg_session.execute(
        text(
            """
            SELECT MIN(service_date) AS lo, MAX(service_date) AS hi
            FROM v_unit_day_occupancy
            """
        )
    ).mappings().first()
    if window is None or window["lo"] is None:
        pytest.skip("No occupancy data loaded")

    # A fortnight well inside the loaded range, so neither side is clipped.
    start = window["lo"]
    end = min(window["hi"], start.fromordinal(start.toordinal() + 13))

    sql_total = pg_session.execute(
        text(
            """
            SELECT SUM(patient_days) FROM v_unit_day_occupancy
            WHERE service_date BETWEEN :start AND :end
            """
        ),
        {"start": start, "end": end},
    ).scalar()

    units = repository.load_units(pg_session, 1)
    movements = repository.load_bed_movements(pg_session, 1, start, end)
    daily = unit_day_occupancy(movements, units, start, end)
    python_total = float(daily["patient_days"].sum())

    # 0.1% rather than an absolute tolerance: the totals run to thousands
    # of patient days, and floating-point summation order differs between
    # PostgreSQL and pandas.
    assert float(sql_total) == pytest.approx(python_total, rel=0.001), (
        "v_unit_day_occupancy and expand_to_days disagree on total patient days"
    )


def test_readmission_denominator_matches(pg_session):
    """Both implementations must exclude deaths and transfers-out."""
    from app.analytics import repository
    from app.analytics.quality import readmission_rate

    window = pg_session.execute(
        text("SELECT MIN(month_start) AS lo FROM v_readmission")
    ).mappings().first()
    if window is None or window["lo"] is None:
        pytest.skip("No readmission data loaded")

    month_start = window["lo"]
    month_end = month_start.replace(
        day=calendar.monthrange(month_start.year, month_start.month)[1]
    )

    sql_denominator = pg_session.execute(
        text(
            """
            SELECT SUM(index_discharges) FROM v_readmission
            WHERE month_start = :month
            """
        ),
        {"month": month_start},
    ).scalar()

    source = repository.load_all_encounters_for_readmission(
        pg_session, 1, month_start, month_end
    )
    _, _, python_denominator = readmission_rate(source, month_start, month_end)

    assert int(sql_denominator) == python_denominator, (
        "v_readmission and quality.readmission_rate disagree on the index-discharge "
        "denominator; check the death and transfer-out exclusions"
    )
