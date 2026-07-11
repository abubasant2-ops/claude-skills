from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.therapist import CaseloadRowOut
from app.services.therapist import build_caseload

router = APIRouter(prefix="/therapist", tags=["therapist"])


@router.get("/caseload", response_model=list[CaseloadRowOut])
def caseload(db: Session = Depends(get_db)) -> list[dict]:
    """T1 — caseload table: adherence and GOP trend per child."""
    return build_caseload(db)
