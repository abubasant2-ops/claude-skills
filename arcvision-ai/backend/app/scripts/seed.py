"""Seed minimal data so the platform is usable immediately after boot.

Idempotent: skips if the demo organization already exists.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.price_book import PriceBookItem
from app.models.user import User


_DEMO_ORG = "Arco View — منظور القوس"

# Indicative Saudi-market prices (SAR). The operator should overwrite via UI.
_PRICE_BOOK: list[dict] = [
    {"category": "concrete", "unit": "m3", "description": "خرسانة مسلحة (شامل صب)",
     "material_rate": 320, "labor_rate": 80, "equipment_rate": 40, "waste_factor": 0.05},
    {"category": "rebar", "unit": "ton", "description": "حديد تسليح",
     "material_rate": 2800, "labor_rate": 350, "equipment_rate": 0, "waste_factor": 0.03},
    {"category": "block", "unit": "m2", "description": "مباني بلوك خرساني 20 سم",
     "material_rate": 45, "labor_rate": 35, "equipment_rate": 0, "waste_factor": 0.07},
    {"category": "door", "unit": "no", "description": "باب خشبي داخلي",
     "material_rate": 850, "labor_rate": 120, "equipment_rate": 0, "waste_factor": 0.02},
    {"category": "window", "unit": "no", "description": "نافذة ألمنيوم زجاج مزدوج",
     "material_rate": 1200, "labor_rate": 150, "equipment_rate": 0, "waste_factor": 0.02},
    {"category": "finishing_floor", "unit": "m2", "description": "تشطيب أرضيات بلاط",
     "material_rate": 90, "labor_rate": 45, "equipment_rate": 0, "waste_factor": 0.08},
    {"category": "cable", "unit": "m", "description": "كابل كهرباء (متوسط)",
     "material_rate": 8, "labor_rate": 4, "equipment_rate": 0, "waste_factor": 0.05},
    {"category": "pipe", "unit": "m", "description": "مواسير سباكة (PPR/PVC)",
     "material_rate": 18, "labor_rate": 12, "equipment_rate": 0, "waste_factor": 0.06},
    {"category": "hvac_unit", "unit": "no", "description": "وحدة تكييف سبليت",
     "material_rate": 2400, "labor_rate": 350, "equipment_rate": 0, "waste_factor": 0.02},
]


def run() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Organization).filter(Organization.name == _DEMO_ORG).first()
        if existing is not None:
            print(f"[seed] organization '{_DEMO_ORG}' already exists — skipping.")
            return

        org = Organization(name=_DEMO_ORG, plan="mvp", region="sa")
        db.add(org)
        db.flush()
        # Set RLS context so we can insert into RLS-guarded tables.
        db.execute(text("SET LOCAL app.current_org = :o"), {"o": str(org.id)})

        users = [
            ("owner@arcoview.sa", "owner", "بندر — المالك"),
            ("estimator@arcoview.sa", "estimator", "خالد — مدير التقدير"),
            ("qs@arcoview.sa", "qs", "نورة — مساح الكميات"),
            ("pm@arcoview.sa", "pm", "محمد — مدير المشروع"),
            ("exec@arcoview.sa", "executive", "سعد — تنفيذي"),
            ("client@arcoview.sa", "client", "ضيف — عميل"),
        ]
        for email, role, name in users:
            db.add(
                User(
                    organization_id=org.id,
                    email=email,
                    password_hash=hash_password("ChangeMe!123"),
                    full_name=name,
                    role=role,
                )
            )

        for row in _PRICE_BOOK:
            data = dict(row)  # copy so re-runs don't mutate the template
            db.add(
                PriceBookItem(
                    organization_id=org.id,
                    waste_factor=Decimal(str(data.pop("waste_factor"))),
                    material_rate=Decimal(str(data.pop("material_rate"))),
                    labor_rate=Decimal(str(data.pop("labor_rate"))),
                    equipment_rate=Decimal(str(data.pop("equipment_rate"))),
                    source="market",
                    **data,
                )
            )

        db.commit()
        print(f"[seed] created org '{_DEMO_ORG}' + 6 users + {len(_PRICE_BOOK)} price-book items.")
        print("[seed] login: owner@arcoview.sa / ChangeMe!123  (and similar for other roles)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
