"""Import endpoints: upload, preview, validate, load, reverse."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.ingest import loader, mapper
from app.ingest.datasets import DATASETS, LOAD_ORDER, get_dataset
from app.models import DataQualityFinding, ImportBatch

router = APIRouter(prefix="/api/v1/import", tags=["import"])


@router.get("/datasets", summary="List importable datasets and their fields")
def list_datasets() -> dict:
    return {
        "load_order": list(LOAD_ORDER),
        "datasets": [
            {
                "key": spec.key,
                "title_en": spec.title_en,
                "title_ar": spec.title_ar,
                "natural_key": list(spec.natural_key),
                "requires_encounters": spec.references_encounter,
                "notes": spec.notes,
                "fields": [
                    {
                        "name": f.name,
                        "type": f.dtype,
                        "required": f.required,
                        "domain": list(f.domain) if f.domain else None,
                        "aliases": list(f.aliases),
                        "description": f.description,
                    }
                    for f in spec.fields
                ],
            }
            for spec in DATASETS.values()
        ],
    }


def _save_upload(upload: UploadFile) -> Path:
    settings = get_settings()
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in settings.allowed_upload_suffixes:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"'{suffix or 'unknown'}' is not an accepted file type. "
                f"Accepted: {', '.join(settings.allowed_upload_suffixes)}"
            ),
        )

    target_dir = Path(settings.upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(delete=False, dir=target_dir, suffix=suffix)
    try:
        shutil.copyfileobj(upload.file, handle)
    finally:
        handle.close()

    path = Path(handle.name)
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is {size_mb:.1f} MB; the limit is {settings.max_upload_mb} MB.",
        )
    return path


@router.post("/preview", summary="Profile a file and show the proposed column mapping")
async def preview(
    dataset: str = Form(...),
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
) -> dict:
    """Dry inspection with no database writes -- what the upload wizard calls
    before the user commits to a load."""
    spec = _spec_or_404(dataset)
    path = _save_upload(file)
    try:
        frame, sheet_name = loader.read_table(path, spec, sheet)
        if frame.empty:
            return {"dataset": dataset, "sheet": sheet_name, "row_count": 0,
                    "columns": [], "mapping": {}, "unmapped_required": list(spec.required_fields)}

        profiles = mapper.profile_columns(frame)
        mapping = mapper.map_columns(profiles, spec)
        return {
            "dataset": dataset,
            "sheet": sheet_name,
            "row_count": int(len(frame)),
            "columns": [p.to_dict() for p in profiles],
            "mapping": mapping,
            "unmapped_required": [f for f in spec.required_fields if f not in mapping],
            "sample_rows": frame.head(5).astype(str).to_dict(orient="records"),
        }
    finally:
        path.unlink(missing_ok=True)


@router.post("/upload", summary="Validate and load a file")
async def upload(
    dataset: str = Form(...),
    file: UploadFile = File(...),
    facility_id: int = Form(1),
    sheet: str | None = Form(None),
    dry_run: bool = Form(False),
    uploaded_by: str | None = Form(None),
    session: Session = Depends(get_session),
) -> dict:
    _spec_or_404(dataset)
    path = _save_upload(file)
    try:
        report = loader.ingest_file(
            session, facility_id=facility_id, dataset=dataset, path=path,
            sheet=sheet, uploaded_by=uploaded_by, dry_run=dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)

    # Restore the original filename for the audit trail; the temp name is noise.
    batch = session.get(ImportBatch, report.batch_id)
    if batch is not None and file.filename:
        batch.source_filename = file.filename
        report.filename = file.filename

    return report.to_dict()


@router.get("/batches", summary="Import history")
def list_batches(
    facility_id: int = Query(1),
    dataset: str | None = Query(None),
    limit: int = Query(50, le=200),
    session: Session = Depends(get_session),
) -> dict:
    query = select(ImportBatch).where(ImportBatch.facility_id == facility_id)
    if dataset:
        query = query.where(ImportBatch.dataset == dataset)
    batches = session.scalars(query.order_by(desc(ImportBatch.uploaded_at)).limit(limit)).all()

    return {
        "batches": [
            {
                "batch_id": b.batch_id,
                "dataset": b.dataset,
                "filename": b.source_filename,
                "sheet": b.sheet_name,
                "state": b.state,
                "row_count": b.row_count,
                "accepted_rows": b.accepted_rows,
                "rejected_rows": b.rejected_rows,
                "quality_score": round(b.quality_score, 2) if b.quality_score else None,
                "uploaded_by": b.uploaded_by,
                "uploaded_at": b.uploaded_at.isoformat() if b.uploaded_at else None,
                "loaded_at": b.loaded_at.isoformat() if b.loaded_at else None,
            }
            for b in batches
        ]
    }


@router.get("/batches/{batch_id}", summary="Data quality report for one import")
def batch_detail(batch_id: int, session: Session = Depends(get_session)) -> dict:
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Batch {batch_id} not found")

    findings = session.scalars(
        select(DataQualityFinding).where(DataQualityFinding.batch_id == batch_id)
    ).all()

    severity_order = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}
    return {
        "batch_id": batch.batch_id,
        "dataset": batch.dataset,
        "filename": batch.source_filename,
        "state": batch.state,
        "quality_score": round(batch.quality_score, 2) if batch.quality_score else None,
        "row_count": batch.row_count,
        "accepted_rows": batch.accepted_rows,
        "rejected_rows": batch.rejected_rows,
        "column_mapping": batch.column_mapping,
        "profile": batch.profile,
        "findings": sorted(
            [
                {
                    "rule_code": f.rule_code,
                    "severity": f.severity,
                    "column": f.column_name,
                    "affected_rows": f.affected_rows,
                    "sample_rows": f.sample_rows,
                    "message_en": f.message_en,
                    "message_ar": f.message_ar,
                }
                for f in findings
            ],
            key=lambda f: severity_order.get(f["severity"], 9),
        ),
    }


@router.post("/batches/{batch_id}/reverse", summary="Undo a completed import")
def reverse(batch_id: int, session: Session = Depends(get_session)) -> dict:
    try:
        removed = loader.reverse_batch(session, batch_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"batch_id": batch_id, "rows_removed": removed, "state": "REVERSED"}


def _spec_or_404(dataset: str):
    try:
        return get_dataset(dataset)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
