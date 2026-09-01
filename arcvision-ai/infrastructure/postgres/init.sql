-- ArcVision AI — Postgres bootstrap
-- يُنفَّذ مرة عند إنشاء الـ container أول مرة.
-- إنشاء extensions ضرورية. RLS policies تُنشأ في Alembic.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- pgvector اختياري للـ MVP (RAG في V1). نُفعّله إن وُجد:
DO $$
BEGIN
  BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector extension not available — skipping (OK for MVP).';
  END;
END$$;
