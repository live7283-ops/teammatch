"""Matching: run the engine over submitted surveys, persist teams, list presets."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import matching as engine
from ..database import get_db
from ..models import (
    Class,
    Enrollment,
    MatchPreset,
    MatchRun,
    SurveyResponse,
    Team,
    TeamMember,
    User,
)
from ..schemas import (
    HardConstraints,
    MatchRequest,
    MatchResultOut,
    MemberOut,
    PresetOut,
    TeamOut,
    Weights,
)
from ..security import require_professor

router = APIRouter(prefix="/api", tags=["matching"])


def _load_candidates(db: Session, class_id: uuid.UUID) -> tuple[list[engine.Candidate], dict[str, User]]:
    """Build engine candidates from students whose survey is match-ready."""
    rows = db.scalars(
        select(Enrollment).where(
            Enrollment.class_id == class_id, Enrollment.survey_submitted.is_(True)
        )
    ).all()

    candidates: list[engine.Candidate] = []
    users: dict[str, User] = {}
    for e in rows:
        survey: SurveyResponse | None = e.survey
        if survey is None or not survey.match_ready:
            continue
        student = e.student
        users[str(student.id)] = student
        free = {f"{a.day}-{a.block}" for a in survey.availability if a.state == "y"}
        traits = {
            "pace": survey.trait_pace or 0,
            "prep": survey.trait_prep or 0,
            "lead": survey.trait_lead or 0,
            "comm": survey.trait_comm or 0,
        }
        candidates.append(
            engine.Candidate(
                student_id=str(student.id),
                name=student.name,
                major=student.major,
                year=student.year,
                roles=list(survey.roles or []),
                free_slots=free,
                traits=traits,
            )
        )
    return candidates, users


@router.post("/classes/{class_id}/match", response_model=MatchResultOut)
def run_match(
    class_id: uuid.UUID,
    body: MatchRequest,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> MatchResultOut:
    c = db.get(Class, class_id)
    if not c or c.professor_id != prof.id:
        raise HTTPException(status_code=404, detail="수업을 찾을 수 없습니다.")

    candidates, users = _load_candidates(db, class_id)
    if len(candidates) < body.team_size:
        raise HTTPException(
            status_code=422,
            detail=f"편성 가능한 제출자가 부족합니다. (현재 {len(candidates)}명)",
        )

    outcome = engine.form_teams(
        candidates,
        team_size=body.team_size,
        weights=engine.Weights(**body.weights.model_dump()),
        hard=engine.Hard(**body.hard.model_dump()),
    )

    # Persist run + teams (replace any prior run for this class is left to caller;
    # here we simply append a new immutable run).
    run = MatchRun(
        class_id=class_id,
        team_size=body.team_size,
        w_major=body.weights.major,
        w_role=body.weights.role,
        w_time=body.weights.time,
        w_trait=body.weights.trait,
        h_same_major=body.hard.same_major,
        h_fix_pair=body.hard.fix_pair,
        h_split_pair=body.hard.split_pair,
        h_even_transfer=body.hard.even_transfer,
        note=body.note,
        avg_score=outcome.avg_score,
    )
    db.add(run)
    db.flush()

    team_out: list[TeamOut] = []
    for i, tr in enumerate(outcome.teams, start=1):
        team = Team(run_id=run.id, class_id=class_id, name=f"{i}팀", fit_score=tr.fit_score)
        db.add(team)
        db.flush()
        roles = engine.assign_roles(tr.members)
        members_out: list[MemberOut] = []
        for m in tr.members:
            db.add(
                TeamMember(
                    team_id=team.id,
                    student_id=uuid.UUID(m.student_id),
                    assigned_role=roles.get(m.student_id),
                )
            )
            members_out.append(
                MemberOut(
                    student_id=uuid.UUID(m.student_id),
                    name=m.name,
                    major=m.major,
                    year=m.year,
                    assigned_role=roles.get(m.student_id),
                )
            )
        team_out.append(
            TeamOut(id=team.id, name=team.name, fit_score=tr.fit_score, members=members_out)
        )

    c.status = "편성 완료"
    db.commit()

    return MatchResultOut(
        run_id=run.id,
        class_id=class_id,
        team_size=body.team_size,
        avg_score=outcome.avg_score,
        teams=team_out,
    )


@router.get("/presets", response_model=list[PresetOut])
def list_presets(prof: User = Depends(require_professor), db: Session = Depends(get_db)) -> list[PresetOut]:
    rows = db.scalars(
        select(MatchPreset).where(
            or_(MatchPreset.is_builtin.is_(True), MatchPreset.owner_id == prof.id)
        )
    ).all()
    return [
        PresetOut(
            id=p.id,
            name=p.name,
            description=p.description,
            team_size=p.team_size,
            weights=Weights(major=p.w_major, role=p.w_role, time=p.w_time, trait=p.w_trait),
            hard=HardConstraints(
                same_major=p.h_same_major,
                fix_pair=p.h_fix_pair,
                split_pair=p.h_split_pair,
                even_transfer=p.h_even_transfer,
            ),
            is_builtin=p.is_builtin,
        )
        for p in rows
    ]
