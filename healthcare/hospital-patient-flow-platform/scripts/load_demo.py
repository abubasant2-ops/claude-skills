#!/usr/bin/env python3
"""Create the schema, seed a facility, and load a sample dataset directory.

    python scripts/load_demo.py --data data/samples

Runs the same ingestion path the API uses, so a successful run is real
evidence the pipeline works rather than a fixture shortcut.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.analytics.benchmarks import seed_rows                     # noqa: E402
from app.core.db import SessionLocal, init_db                      # noqa: E402
from app.ingest.datasets import LOAD_ORDER                         # noqa: E402
from app.ingest.loader import ingest_file                          # noqa: E402
from app.models import Benchmark, Facility                         # noqa: E402


def seed_facility(session, *, code: str, name_en: str, name_ar: str,
                  licensed_beds: int, ed_spaces: int) -> Facility:
    facility = session.query(Facility).filter(Facility.code == code).one_or_none()
    if facility is None:
        facility = Facility(
            code=code, name_en=name_en, name_ar=name_ar,
            licensed_beds=licensed_beds, ed_treatment_spaces=ed_spaces,
            timezone="Asia/Riyadh", cluster_name="Demo Health Cluster",
        )
        session.add(facility)
        session.flush()
    return facility


def seed_benchmarks(session) -> int:
    existing = {b.metric_key for b in session.query(Benchmark).all()}
    added = 0
    for row in seed_rows():
        if row["metric_key"] in existing:
            continue
        session.add(Benchmark(**row))
        added += 1
    session.flush()
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/samples", help="Directory of dataset CSV files")
    parser.add_argument("--facility-code", default="DEMO-TERT-01")
    parser.add_argument("--facility-name", default="King Fahad Tertiary Medical City (Demo)")
    parser.add_argument("--facility-name-ar", default="مدينة الملك فهد الطبية التخصصية (تجريبي)")
    parser.add_argument("--licensed-beds", type=int, default=500)
    parser.add_argument("--ed-spaces", type=int, default=45)
    args = parser.parse_args()

    data_dir = Path(args.data)
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir.resolve()}", file=sys.stderr)
        print("Run scripts/generate_sample_data.py first.", file=sys.stderr)
        return 1

    init_db()
    session = SessionLocal()
    try:
        facility = seed_facility(
            session, code=args.facility_code, name_en=args.facility_name,
            name_ar=args.facility_name_ar, licensed_beds=args.licensed_beds,
            ed_spaces=args.ed_spaces,
        )
        added = seed_benchmarks(session)
        session.commit()
        print(f"Facility {facility.code} (id={facility.facility_id}); "
              f"{added} benchmark defaults seeded.\n")

        header = f"{'dataset':<20}{'rows':>8}{'loaded':>8}{'rejected':>10}{'quality':>9}  state"
        print(header)
        print("-" * len(header))

        failures = 0
        for dataset in LOAD_ORDER:
            path = data_dir / f"{dataset}.csv"
            if not path.exists():
                continue
            report = ingest_file(
                session, facility_id=facility.facility_id, dataset=dataset,
                path=path, uploaded_by="load_demo.py",
            )
            session.commit()
            print(f"{dataset:<20}{report.row_count:>8,}{report.loaded_rows:>8,}"
                  f"{report.rejected_rows:>10,}{report.quality_score:>9.1f}  {report.state}")

            if report.state not in ("LOADED", "VALIDATED"):
                failures += 1
                for finding in report.validation.get("findings", [])[:5]:
                    if finding["severity"] in ("CRITICAL", "ERROR"):
                        print(f"    [{finding['severity']}] {finding['message_en']}")

        print()
        if failures:
            print(f"{failures} dataset(s) did not load. See the findings above.")
            return 1
        print("All datasets loaded.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
