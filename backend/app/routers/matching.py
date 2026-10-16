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
    MatchRunSummary,
    MemberOut,
    PresetOut,
    TeamOut,
    TeamUpdate,
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


def _assert_no_duplicate_assignment(teams) -> None:
    """엔진 결과 안전망: 한 학생이 두 팀 이상에 배정되지 않았는지 검증.

    엔진에 버그가 생겨도 잘못된 편성을 DB에 저장하지 않도록 막는 최후 방어선.
    """
    seen: set[str] = set()
    for tr in teams:
        for m in tr.members:
            if m.student_id in seen:
                raise HTTPException(
                    status_code=500,
                    detail="편성 결과에 중복 배정된 학생이 있습니다. 매칭을 다시 실행하세요.",
                )
            seen.add(m.student_id)


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

    # 계층 방어 1: 제출자가 아예 없음 (교수의 조치 = 학생에게 설문 독려)
    if len(candidates) == 0:
        raise HTTPException(
            status_code=422,
            detail="매칭 참여가 가능한 설문 제출 학생이 없습니다.",
        )
    # 계층 방어 2: 제출자는 있으나 팀 크기보다 적음 (조치 = team_size 조정)
    if len(candidates) < body.team_size:
        raise HTTPException(
            status_code=422,
            detail=f"편성 가능한 제출자가 부족합니다. (현재 {len(candidates)}명 / 팀 크기 {body.team_size}명)",
        )

    outcome = engine.form_teams(
        candidates,
        team_size=body.team_size,
        weights=engine.Weights(**body.weights.model_dump()),
        hard=engine.Hard(**body.hard.model_dump()),
    )

    # 계층 방어 3: 엔진이 빈 결과를 돌려주면 저장하지 않고 중단
    if not outcome.teams:
        raise HTTPException(
            status_code=422,
            detail="주어진 조건으로 팀을 편성하지 못했습니다. 조건을 완화해 보세요.",
        )
    # 계층 방어 4: 중복 배정 안전망
    _assert_no_duplicate_assignment(outcome.teams)

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

# ================================================================
# 2. 매칭 결과 조회 API
# ================================================================

@router.get("/classes/{class_id}/matches", response_model=list[MatchRunSummary])
def list_match_runs(
    class_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> list[MatchRunSummary]:
    """해당 과목의 과거 매칭 실행 이력 목록을 조회합니다."""
    c = db.get(Class, class_id)
    if not c or c.professor_id != prof.id:
        raise HTTPException(status_code=404, detail="수업을 찾을 수 없습니다.")

    runs = db.scalars(
        select(MatchRun)
        .where(MatchRun.class_id == class_id)
        .order_by(MatchRun.created_at.desc())
    ).all()

    out: list[MatchRunSummary] = []
    for r in runs:
        out.append(
            MatchRunSummary(
                id=r.id,
                class_id=r.class_id,
                team_size=r.team_size,
                avg_score=float(r.avg_score) if r.avg_score is not None else None,
                note=r.note,
                created_at=r.created_at,
                team_count=len(r.teams),
            )
        )
    return out


@router.get("/matchings/{run_id}", response_model=MatchResultOut)
def get_match_run(
    run_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> MatchResultOut:
    """특정 매칭 실행 결과의 상세 팀 구성 및 팀원 목록을 조회합니다."""
    run = db.get(MatchRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="매칭 결과를 찾을 수 없습니다.")

    c = db.get(Class, run.class_id)
    if not c or c.professor_id != prof.id:
        raise HTTPException(status_code=404, detail="수업을 찾을 수 없거나 권한이 없습니다.")

    teams_out: list[TeamOut] = []
    for t in run.teams:
        members_out: list[MemberOut] = []
        for tm in t.members:
            student = db.get(User, tm.student_id)
            if student:
                members_out.append(
                    MemberOut(
                        student_id=student.id,
                        name=student.name,
                        major=student.major,
                        year=student.year,
                        assigned_role=tm.assigned_role,
                    )
                )
        teams_out.append(
            TeamOut(
                id=t.id,
                name=t.name,
                fit_score=float(t.fit_score),
                members=members_out,
            )
        )

    return MatchResultOut(
        run_id=run.id,
        class_id=run.class_id,
        team_size=run.team_size,
        avg_score=float(run.avg_score) if run.avg_score is not None else None,
        teams=teams_out,
    )


# ================================================================
# 3. 팀 수정 및 최종 확정 API
# ================================================================

@router.put("/teams/{team_id}", response_model=TeamOut)
def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> TeamOut:
    """팀 이름 변경 및 팀원/역할 수동 변경."""
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    c = db.get(Class, team.class_id)
    if not c or c.professor_id != prof.id:
        raise HTTPException(status_code=404, detail="수업을 찾을 수 없거나 권한이 없습니다.")

    # 1. 팀 이름 변경
    if body.name is not None:
        team.name = body.name

    # 2. 팀원/역할 수동 조정
    if body.members is not None:
        team.members.clear()
        db.flush()

        for m in body.members:
            student = db.get(User, m.student_id)
            if not student or student.role != "student":
                raise HTTPException(
                    status_code=400,
                    detail=f"존재하지 않거나 학생 계정이 아닙니다: {m.student_id}",
                )
            team.members.append(
                TeamMember(
                    team_id=team.id,
                    student_id=m.student_id,
                    assigned_role=m.assigned_role,
                )
            )

    db.commit()
    db.refresh(team)

    members_out: list[MemberOut] = []
    for tm in team.members:
        s = db.get(User, tm.student_id)
        if s:
            members_out.append(
                MemberOut(
                    student_id=s.id,
                    name=s.name,
                    major=s.major,
                    year=s.year,
                    assigned_role=tm.assigned_role,
                )
            )

    return TeamOut(
        id=team.id,
        name=team.name,
        fit_score=float(team.fit_score),
        members=members_out,
    )


@router.post("/matchings/{run_id}/confirm")
def confirm_match_run(
    run_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """해당 매칭 결과를 최종 확정하고 과목 상태를 '편성 확정'으로 전환합니다."""
    run = db.get(MatchRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="매칭 결과를 찾을 수 없습니다.")

    c = db.get(Class, run.class_id)
    if not c or c.professor_id != prof.id:
        raise HTTPException(status_code=404, detail="수업을 찾을 수 없거나 권한이 없습니다.")

    c.status = "편성 확정"
    db.commit()

    return {"message": "팀 편성이 성공적으로 확정되었습니다.", "status": c.status}
