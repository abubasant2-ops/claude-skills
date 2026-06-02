import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.models.document import Document
from app.models.project import Project
from app.schemas.common import DocumentOut
from app.services.audit import log_action
from app.services.classifier import classify_discipline, classify_filetype
from app.services.storage import upload_file
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/v1", tags=["documents"])


@router.post("/projects/{project_id}/documents", status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    file_type = classify_filetype(file.filename or "")
    if file_type == "unknown":
        raise HTTPException(status_code=400, detail="Unsupported file type")
    discipline = classify_discipline(file.filename or "")

    key = upload_file(
        file_obj=file.file,
        organization_id=user.organization_id,
        project_id=str(project_id),
        filename=file.filename or "upload",
        content_type=file.content_type,
    )

    doc = Document(
        organization_id=uuid.UUID(user.organization_id),
        project_id=project_id,
        file_name=file.filename or "upload",
        file_type=file_type,
        discipline=discipline,
        storage_key=key,
        status="classified",
    )
    db.add(doc)
    db.flush()
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.user_id,
        action="upload",
        entity_type="document",
        entity_id=doc.id,
        after={"file_name": doc.file_name, "file_type": doc.file_type},
    )
    db.commit()
    db.refresh(doc)

    # Hand off to async worker (only for types we can process now).
    job_id = None
    if file_type in {"ifc", "pdf"}:
        job = celery_app.send_task("arcvision.process_document", args=[str(doc.id)])
        job_id = job.id

    return {
        "document_id": str(doc.id),
        "status": doc.status,
        "job_id": job_id,
        "poll_url": f"/v1/documents/{doc.id}",
    }


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
def list_documents(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Document]:
    return (
        db.query(Document)
        .filter(Document.project_id == project_id)
        .order_by(Document.created_at.desc())
        .all()
    )
