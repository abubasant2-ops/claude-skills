"""Celery tasks — async document processing pipeline (PRD §2.3)."""

from __future__ import annotations

import os
import tempfile
import uuid

from sqlalchemy import text

from app.core.database import session_scope
from app.models.document import Document
from app.models.element import ExtractedElement
from app.services.aggregator import aggregate_project_takeoff
from app.services.storage import download_to_path
from app.workers.celery_app import celery_app


@celery_app.task(name="arcvision.process_document", bind=True)
def process_document(self, document_id: str) -> dict:
    """Routes a document to the right extractor and persists results.

    Pipeline (matches PRD §2.3):
      1. Load document row, transition to status=processing.
      2. Download file from object storage to a temp path.
      3. Route by file_type → IFC / PDF extractor.
      4. Persist ExtractedElement rows.
      5. Recompute the project's takeoff (aggregator).
      6. Mark document ready_for_review.
    """
    with session_scope() as db:
        doc = db.get(Document, uuid.UUID(document_id))
        if doc is None:
            return {"status": "missing"}
        # bypass RLS for the worker — set tenant context from the document row.
        db.execute(text("SET LOCAL app.current_org = :org"), {"org": str(doc.organization_id)})

        doc.status = "processing"
        db.flush()
        organization_id = doc.organization_id
        project_id = doc.project_id
        file_type = doc.file_type
        storage_key = doc.storage_key
        document_id_uuid = doc.id

    # --- Heavy work outside the txn ---
    suffix = "." + file_type if file_type in {"pdf", "ifc"} else ""
    extracted: list[dict] = []
    page_count: int | None = None
    error: str | None = None

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        local_path = tmp.name
    try:
        download_to_path(storage_key, local_path)

        if file_type == "ifc":
            from app.workers.ifc_extractor import extract_elements as ifc_extract

            for el in ifc_extract(local_path):
                extracted.append(
                    {
                        "element_type": el.element_type,
                        "discipline": el.discipline,
                        "geometry": el.geometry,
                        "source_ref": el.source_ref,
                        "confidence": el.confidence,
                        "extraction_method": el.extraction_method,
                    }
                )
        elif file_type == "pdf":
            from app.workers.pdf_extractor import extract_elements as pdf_extract

            elements, page_count = pdf_extract(local_path)
            for el in elements:
                extracted.append(
                    {
                        "element_type": el.element_type,
                        "discipline": el.discipline,
                        "geometry": el.geometry,
                        "source_ref": el.source_ref,
                        "confidence": el.confidence,
                        "extraction_method": el.extraction_method,
                    }
                )
        else:
            error = f"file_type '{file_type}' not supported in MVP"
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            os.unlink(local_path)
        except OSError:
            pass

    # --- Persist results ---
    with session_scope() as db:
        db.execute(text("SET LOCAL app.current_org = :org"), {"org": str(organization_id)})
        doc = db.get(Document, document_id_uuid)
        if doc is None:
            return {"status": "missing"}

        if error:
            doc.status = "error"
            doc.error_message = error
            return {"status": "error", "error": error}

        for el in extracted:
            db.add(
                ExtractedElement(
                    organization_id=organization_id,
                    project_id=project_id,
                    document_id=document_id_uuid,
                    **el,
                )
            )

        if page_count is not None:
            doc.page_count = page_count
        doc.processing_meta = {"elements_extracted": len(extracted)}
        doc.status = "ready_for_review"
        db.flush()

        # Refresh the project's pending takeoff items
        aggregate_project_takeoff(
            db, organization_id=organization_id, project_id=project_id
        )

    return {"status": "ok", "elements": len(extracted)}
