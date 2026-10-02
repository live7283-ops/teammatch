"""Survey submission + retrieval, scoped to (student, class) enrollment."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Enrollment, SurveyAvailability, SurveyResponse, SurveySkill, User
from ..schemas import SkillIn, SurveyOut, SurveySubmit, Traits
from ..security import require_student

router = APIRouter(prefix="/api/classes/{class_id}/survey", tags=["surveys"])


def _get_enrollment(db: Session, class_id: uuid.UUID, student_id: uuid.UUID) -> Enrollment:
    e = db.scalar(
        select(Enrollment).where(
            Enrollment.class_id == class_id, Enrollment.student_id == student_id
        )
    )
    if not e:
        raise HTTPException(status_code=404, detail="해당 수업에 참여하지 않았습니다.")
    return e


def _to_out(survey: SurveyResponse, enrollment_id: uuid.UUID) -> SurveyOut:
    return SurveyOut(
        enrollment_id=enrollment_id,
        roles=list(survey.roles or []),
        skills=[SkillIn(name=s.name, level=s.level) for s in survey.skills],
        traits=Traits(
            pace=survey.trait_pace, prep=survey.trait_prep,
            lead=survey.trait_lead, comm=survey.trait_comm,
        ),
        availability=[
            {"day": a.day, "block": a.block, "state": a.state} for a in survey.availability
        ],
        match_ready=survey.match_ready,
        updated_at=survey.updated_at,
    )


@router.put("", response_model=SurveyOut)
def submit_survey(
    class_id: uuid.UUID,
    body: SurveySubmit,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> SurveyOut:
    enrollment = _get_enrollment(db, class_id, student.id)

    survey = enrollment.survey
    if survey is None:
        survey = SurveyResponse(enrollment_id=enrollment.id)
        db.add(survey)
        db.flush()

    survey.roles = body.roles
    survey.trait_pace = body.traits.pace
    survey.trait_prep = body.traits.prep
    survey.trait_lead = body.traits.lead
    survey.trait_comm = body.traits.comm
    survey.match_ready = body.match_ready

    # Replace child collections wholesale — simplest correct upsert.
    survey.skills.clear()
    survey.availability.clear()
    db.flush()
    for sk in body.skills:
        survey.skills.append(SurveySkill(survey_id=survey.id, name=sk.name, level=sk.level))
    for slot in body.availability:
        survey.availability.append(
            SurveyAvailability(survey_id=survey.id, day=slot.day, block=slot.block, state=slot.state)
        )

    enrollment.survey_submitted = body.match_ready
    if body.match_ready and enrollment.submitted_at is None:
        enrollment.submitted_at = dt.datetime.now(dt.timezone.utc)

    db.commit()
    db.refresh(survey)
    return _to_out(survey, enrollment.id)


@router.get("", response_model=SurveyOut)
def get_survey(
    class_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> SurveyOut:
    enrollment = _get_enrollment(db, class_id, student.id)
    if enrollment.survey is None:
        raise HTTPException(status_code=404, detail="아직 제출한 설문이 없습니다.")
    return _to_out(enrollment.survey, enrollment.id)
