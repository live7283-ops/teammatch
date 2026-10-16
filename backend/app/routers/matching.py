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
    RunSummary,
    TeamDetail,
    TeamMemberDetail,
    TeamOut,
    Weights,
)
from ..security import get_owned_class, require_professor

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
    # 과목별 접근 제어: 공용 소유 확인 함수 사용(없는 수업/남의 수업 모두 404)
    c = get_owned_class(db, class_id, prof)

    # 계층 방어 0: 이미 편성이 끝난 수업은 재실행을 막는다(중복 run/team 방지).
    # 단, force=true 면 이전 편성 결과를 지우고 재편성을 허용한다.
    if c.status == "편성 완료":
        if not body.force:
            raise HTTPException(
                status_code=409,
                detail="이미 팀 편성이 완료된 수업입니다. 다시 편성하려면 force=true 로 요청하세요.",
            )
        # 재편성: 이 수업의 기존 매칭 run 들을 삭제(연관 team/member는 CASCADE).
        for old in db.scalars(select(MatchRun).where(MatchRun.class_id == class_id)).all():
            db.delete(old)
        db.flush()

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

    # 결과 저장: 새 run 을 추가한다(불변 이력).
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
# 백엔드1 5번: 저장된 매칭 결과 조회
# ================================================================
def _run_to_result(db: Session, run: MatchRun) -> MatchResultOut:
    """저장된 MatchRun 을 MatchResultOut(팀/팀원 포함)으로 조립."""
    teams_out: list[TeamOut] = []
    for team in sorted(run.teams, key=lambda t: t.name):
        members_out: list[MemberOut] = []
        for tm in team.members:
            u = db.get(User, tm.student_id)
            members_out.append(
                MemberOut(
                    student_id=tm.student_id,
                    name=u.name if u else "(탈퇴/삭제된 학생)",
                    major=u.major if u else None,
                    year=u.year if u else None,
                    assigned_role=tm.assigned_role,
                )
            )
        teams_out.append(
            TeamOut(
                id=team.id,
                name=team.name,
                fit_score=float(team.fit_score),
                members=members_out,
            )
        )
    return MatchResultOut(
        run_id=run.id,
        class_id=run.class_id,
        team_size=run.team_size,
        avg_score=float(run.avg_score) if run.avg_score is not None else 0.0,
        teams=teams_out,
    )


@router.get("/classes/{class_id}/result", response_model=MatchResultOut)
def get_latest_result(
    class_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> MatchResultOut:
    """해당 수업의 가장 최근 매칭 결과를 조회."""
    get_owned_class(db, class_id, prof)
    run = db.scalar(
        select(MatchRun)
        .where(MatchRun.class_id == class_id)
        .order_by(MatchRun.created_at.desc())
    )
    if run is None:
        raise HTTPException(status_code=404, detail="아직 편성된 매칭 결과가 없습니다.")
    return _run_to_result(db, run)


@router.get("/classes/{class_id}/runs", response_model=list[RunSummary])
def list_runs(
    class_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> list[RunSummary]:
    """해당 수업의 매칭 실행 이력 목록(요약)."""
    get_owned_class(db, class_id, prof)
    runs = db.scalars(
        select(MatchRun)
        .where(MatchRun.class_id == class_id)
        .order_by(MatchRun.created_at.desc())
    ).all()
    return [
        RunSummary(
            run_id=r.id,
            class_id=r.class_id,
            team_size=r.team_size,
            team_count=len(r.teams),
            avg_score=float(r.avg_score) if r.avg_score is not None else None,
            note=r.note,
            created_at=r.created_at,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=MatchResultOut)
def get_run(
    run_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> MatchResultOut:
    """특정 매칭 실행 이력 상세 조회."""
    run = db.get(MatchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="매칭 이력을 찾을 수 없습니다.")
    # 소유 확인: 그 run 이 속한 수업의 담당 교수인지
    get_owned_class(db, run.class_id, prof)
    return _run_to_result(db, run)


# ================================================================
# 백엔드1 6번: 팀 단위 상세 조회 (팀원 + 일정)
# ================================================================
def _student_avail(db: Session, class_id: uuid.UUID, student_id: uuid.UUID) -> list[str]:
    """해당 수업에서 학생이 가능('y')하다고 한 시간 슬롯("day-block") 목록."""
    e = db.scalar(
        select(Enrollment).where(
            Enrollment.class_id == class_id, Enrollment.student_id == student_id
        )
    )
    if not e or not e.survey:
        return []
    return [f"{a.day}-{a.block}" for a in e.survey.availability if a.state == "y"]


def _student_roles(db: Session, class_id: uuid.UUID, student_id: uuid.UUID) -> list[str]:
    e = db.scalar(
        select(Enrollment).where(
            Enrollment.class_id == class_id, Enrollment.student_id == student_id
        )
    )
    if not e or not e.survey:
        return []
    return list(e.survey.roles or [])


@router.get("/teams/{team_id}", response_model=TeamDetail)
def get_team_detail(
    team_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> TeamDetail:
    """팀 상세: 팀원 정보 + 각자의 가능 시간 + 팀 공통 가능 시간."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")
    # 소유 확인: 그 팀이 속한 수업의 담당 교수인지
    get_owned_class(db, team.class_id, prof)

    members: list[TeamMemberDetail] = []
    slot_sets: list[set[str]] = []
    for tm in team.members:
        u = db.get(User, tm.student_id)
        slots = _student_avail(db, team.class_id, tm.student_id)
        slot_sets.append(set(slots))
        members.append(
            TeamMemberDetail(
                student_id=tm.student_id,
                name=u.name if u else "(탈퇴/삭제된 학생)",
                major=u.major if u else None,
                year=u.year if u else None,
                email=u.email if u else None,
                assigned_role=tm.assigned_role,
                preferred_roles=_student_roles(db, team.class_id, tm.student_id),
                available_slots=slots,
            )
        )

    # 팀 전원 공통 가능 시간(교집합). 슬롯 정보가 없는 팀원이 있으면 공통은 빈 집합.
    common = sorted(set.intersection(*slot_sets)) if slot_sets and all(slot_sets) else []

    return TeamDetail(
        team_id=team.id,
        name=team.name,
        fit_score=float(team.fit_score),
        class_id=team.class_id,
        run_id=team.run_id,
        members=members,
        common_slots=common,
    )
