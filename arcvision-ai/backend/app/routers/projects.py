import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.rbac import Permission
from app.models.project import Project
from app.schemas.common import ProjectCreate, ProjectOut
from app.services.audit import log_action

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Project]:
    # RLS already filters by organization_id; for clients we also gate to created_by.
    q = db.query(Project)
    if user.role == "client":
        q = q.filter(Project.created_by == user.user_id)
    return q.order_by(Project.created_at.desc()).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    user: CurrentUser = Depends(require_permission(Permission.CREATE_PROJECT)),
    db: Session = Depends(get_db),
) -> Project:
    project = Project(
        organization_id=uuid.UUID(user.organization_id),
        created_by=uuid.UUID(user.user_id),
        **payload.model_dump(),
    )
    db.add(project)
    db.flush()
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.user_id,
        action="create",
        entity_type="project",
        entity_id=project.id,
        after={"name": project.name},
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return p
