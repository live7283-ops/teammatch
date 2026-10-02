"""Classes: professor CRUD + roster, student enrollment via join code."""
from __future__ import annotations

import datetime as dt
import secrets
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Class, Enrollment, User
from ..schemas import ClassCreate, ClassOut, JoinRequest
from ..security import get_current_user, require_professor, require_student

router = APIRouter(prefix="/api/classes", tags=["classes"])

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _generate_join_code(db: Session) -> str:
    for _ in range(20):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        if not db.scalar(select(Class).where(Class.join_code == code)):
            return code
    raise HTTPException(status_code=500, detail="참여 코드를 생성하지 못했습니다.")


def _to_out(db: Session, c: Class) -> ClassOut:
    enrolled = db.scalar(
        select(func.count()).select_from(Enrollment).where(Enrollment.class_id == c.id)
    ) or 0
    submitted = db.scalar(
        select(func.count())
        .select_from(Enrollment)
        .where(Enrollment.class_id == c.id, Enrollment.survey_submitted.is_(True))
    ) or 0
    out = ClassOut.model_validate(c)
    out.enrolled = enrolled
    out.submitted = submitted
    return out


@router.post("", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
def create_class(
    body: ClassCreate, prof: User = Depends(require_professor), db: Session = Depends(get_db)
) -> ClassOut:
    c = Class(
        professor_id=prof.id,
        name=body.name,
        code=body.code,
        term=body.term,
        capacity=body.capacity,
        kind=body.kind,
        survey_deadline=body.survey_deadline,
        join_code=_generate_join_code(db),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _to_out(db, c)


@router.get("", response_model=list[ClassOut])
def list_classes(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ClassOut]:
    if user.role == "professor":
        rows = db.scalars(select(Class).where(Class.professor_id == user.id)).all()
    else:
        rows = db.scalars(
            select(Class)
            .join(Enrollment, Enrollment.class_id == Class.id)
            .where(Enrollment.student_id == user.id)
        ).all()
    return [_to_out(db, c) for c in rows]


@router.get("/{class_id}/roster")
def roster(
    class_id: uuid.UUID, prof: User = Depends(require_professor), db: Session = Depends(get_db)
) -> list[dict]:
    c = db.get(Class, class_id)
    if not c or c.professor_id != prof.id:
        raise HTTPException(status_code=404, detail="수업을 찾을 수 없습니다.")
    rows = db.scalars(
        select(Enrollment).where(Enrollment.class_id == class_id)
    ).all()
    out = []
    for e in rows:
        s = e.student
        out.append(
            {
                "student_id": str(s.id),
                "name": s.name,
                "major": s.major,
                "year": s.year,
                "survey_submitted": e.survey_submitted,
                "reminders": e.reminders,
                "submitted_at": e.submitted_at,
            }
        )
    return out


@router.post("/join", response_model=ClassOut)
def join_class(
    body: JoinRequest, student: User = Depends(require_student), db: Session = Depends(get_db)
) -> ClassOut:
    c = db.scalar(select(Class).where(Class.join_code == body.join_code.upper()))
    if not c:
        raise HTTPException(status_code=404, detail="참여 코드가 올바르지 않습니다.")

    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.class_id == c.id, Enrollment.student_id == student.id
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="이미 참여한 수업입니다.")

    db.add(Enrollment(class_id=c.id, student_id=student.id))
    db.commit()
    return _to_out(db, c)
