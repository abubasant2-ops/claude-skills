# ArcVision AI — MVP Platform

منصة ذكاء اصطناعي لتحليل المشاريع الإنشائية والمقاولات (السوق السعودي).
هذه نسخة الـ MVP (Sprints S0–S8) من Founding Blueprint.

> **النطاق:** IFC + PDF takeoff → Human Review → Cost Engine → BOQ Export
> **الحوكمة:** Multi-tenant (RLS) · RBAC للأدوار الستة · audit logs · provenance لكل رقم

---

## المعمارية (MVP)

```
Next.js (RTL)  →  FastAPI (BFF + Core)  →  PostgreSQL (RLS) + Redis + MinIO
                          │
                          ├── Celery worker: IFC (IfcOpenShell)
                          ├── Celery worker: PDF (OCR + Vision-LLM)
                          └── Cost Engine (deterministic)
```

## التشغيل المحلي (Local Dev)

```bash
cp .env.example .env
docker compose up --build
```

ثم:

- Frontend: <http://localhost:3000>
- Backend API + OpenAPI: <http://localhost:8000/docs>
- MinIO Console: <http://localhost:9001>  (user: `minioadmin` / pass: `minioadmin`)

## الترحيلات (Migrations)

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed   # بيانات ابتدائية + price book
```

## الاختبارات

```bash
docker compose exec backend pytest
```

## هيكل المشروع

```
arcvision-ai/
├── backend/                 # FastAPI + Celery + SQLAlchemy + Alembic
│   ├── app/
│   │   ├── models/          # SQLAlchemy models (organizations, projects, ...)
│   │   ├── schemas/         # Pydantic I/O models
│   │   ├── routers/         # REST endpoints (/v1/*)
│   │   ├── services/        # cost_engine, aggregator, storage, classifier
│   │   ├── workers/         # Celery tasks: IFC + PDF processing
│   │   └── core/            # auth, RBAC, RLS context, config
│   └── alembic/             # migrations
├── frontend/                # Next.js 14 (App Router) + RTL + Tailwind
│   ├── app/                 # routes: login, dashboard, projects/[id]/...
│   ├── components/
│   └── lib/                 # API client, auth
├── infrastructure/
│   └── postgres/init.sql    # RLS bootstrap
└── docker-compose.yml
```

## الأدوار (RBAC)

| الدور | الصلاحيات الأساسية |
|---|---|
| `owner` | كل شيء + إدارة المستخدمين + رؤية الهامش |
| `executive` | عرض كل المشاريع + الهامش (بلا تعديل) |
| `pm` | إدارة مشاريعه + مراجعة الحصر |
| `estimator` | الحصر + Cost Engine + Price Book |
| `qs` | مراجعة/تعديل الحصر فقط |
| `client` | مشاريعه فقط، بدون الهامش الداخلي |

## ما الذي يعمل في الـ MVP

- [x] Multi-tenant auth (JWT) + RBAC + Postgres RLS
- [x] رفع الملفات إلى MinIO + تصنيف أولي
- [x] IFC worker: استخراج العناصر و BaseQuantities عبر IfcOpenShell
- [x] PDF worker: OCR (Tesseract عربي/إنجليزي) + Vision-LLM hooks
- [x] Unified Element Model + Quantity Aggregation
- [x] شاشة مراجعة الحصر (Takeoff Review) مع provenance
- [x] Cost Engine: مواد + عمالة + معدات + غير مباشر + طوارئ + هامش
- [x] تصدير BOQ + ملخص مالي (xlsx/json)
- [x] Audit logs لكل عملية حساسة

## مؤجَّل عمداً (V1 وما بعد)

- Revit/DWG via Autodesk Platform Services (Enterprise)
- RAG (pgvector) + Chat Assistant
- Risk Engine + Contract Analysis
- التنبؤي (ML للمدة/التدفق)
- تكامل Etimad

راجع الوثيقة الأصلية في `ArcVision_AI_Execution_Document.md`.
