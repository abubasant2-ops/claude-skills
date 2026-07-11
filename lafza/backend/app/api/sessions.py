import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Child, PhonemeProfile, TherapySession, TreatmentPlan
from app.models.enums import PhonemePosition
from app.schemas.session import SessionCreate, SessionOut, UtteranceScoreOut
from app.services.scoring import ScoringService

router = APIRouter(prefix="/sessions", tags=["sessions"])

scoring_service = ScoringService()


def get_session_or_404(session_id: uuid.UUID, db: Session) -> TherapySession:
    session = db.get(TherapySession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.post("", response_model=SessionOut, status_code=201)
def create_session(
    payload: SessionCreate, db: Session = Depends(get_db)
) -> TherapySession:
    if db.get(Child, payload.child_id) is None:
        raise HTTPException(status_code=404, detail="child not found")
    if payload.plan_id is not None and db.get(TreatmentPlan, payload.plan_id) is None:
        raise HTTPException(status_code=404, detail="treatment plan not found")
    session = TherapySession(
        child_id=payload.child_id,
        plan_id=payload.plan_id,
        activity_ids=payload.activity_ids,
    )
    db.add(session)
    db.commit()
    return session


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: uuid.UUID, db: Session = Depends(get_db)
) -> TherapySession:
    return get_session_or_404(session_id, db)


@router.post(
    "/{session_id}/utterances",
    response_model=UtteranceScoreOut,
    status_code=201,
)
async def score_session_utterance(
    session_id: uuid.UUID,
    audio: UploadFile = File(...),
    target_phoneme: str = Form(min_length=1, max_length=4),
    position: PhonemePosition = Form(...),
    db: Session = Depends(get_db),
) -> dict:
    """Capture → ScoringService → phoneme_profiles (CLAUDE.md Phase C).

    The audio lands in a temp file that is always deleted after scoring —
    persistent storage (recordings + retention_until) is wired separately.
    Raw audio and child identifiers are never logged (hard rule 5).
    """
    session = get_session_or_404(session_id, db)

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=422, detail="empty audio upload")

    fd, audio_path = tempfile.mkstemp(suffix=".audio")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        result = scoring_service.score_utterance(
            audio_path, target_phoneme, position.value
        )
    finally:
        os.unlink(audio_path)

    profile = PhonemeProfile(
        child_id=session.child_id,
        phoneme=result["phoneme"],
        position=result["position"],
        gop_score=result["gop_score"],
        error_type=result["error_type"],
    )
    db.add(profile)
    db.commit()

    return {
        **result,
        "phoneme_profile_id": profile.id,
        "child_id": session.child_id,
    }
