"""팀 관리 라우터 (백엔드2 6·7번).

- 팀원 교체/이동/역할 수정 (교수가 매칭 결과를 수동 조정)
- 매칭 결과 확정 / 확정 해제

모든 수정은 '확정 전(confirmed_at IS NULL)'인 run 에 대해서만 허용한다.
확정된 결과는 잠근다(최종 확정). 접근은 담당 교수만 가능(get_owned_class).
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MatchRun, Team, TeamMember, User
from ..schemas import (
    MoveMemberRequest,
    RunStatusOut,
    SetMemberRoleRequest,
    SwapMembersRequest,
)
from ..security import get_owned_class, require_professor

router = APIRouter(prefix="/api", tags=["teams"])


def _get_run_for_edit(db: Session, run_id: uuid.UUID, prof: User) -> MatchRun:
    """수정 대상 run 을 가져오되, 소유 확인 + 확정 여부를 검사한다."""
    run = db.get(MatchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="매칭 이력을 찾을 수 없습니다.")
    get_owned_class(db, run.class_id, prof)  # 담당 교수만
    if run.confirmed_at is not None:
        raise HTTPException(
            status_code=409,
            detail="이미 확정된 편성입니다. 수정하려면 먼저 확정을 해제하세요.",
        )
    return run


def _team_in_run(db: Session, run: MatchRun, team_id: uuid.UUID) -> Team:
    team = db.get(Team, team_id)
    if team is None or team.run_id != run.id:
        raise HTTPException(status_code=404, detail="해당 편성에 속한 팀이 아닙니다.")
    return team


def _find_member(run: MatchRun, student_id: uuid.UUID) -> tuple[Team, TeamMember]:
    for team in run.teams:
        for tm in team.members:
            if tm.student_id == student_id:
                return team, tm
    raise HTTPException(status_code=404, detail="이 편성에 속한 학생이 아닙니다.")


# ---- 6번: 팀원 이동 / 교체 / 역할 수정 --------------------------------
@router.patch("/runs/{run_id}/move", status_code=204, response_class=Response, response_model=None)
def move_member(
    run_id: uuid.UUID,
    body: MoveMemberRequest,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> Response:
    """학생 한 명을 다른 팀으로 이동."""
    run = _get_run_for_edit(db, run_id, prof)
    _src_team, tm = _find_member(run, body.student_id)
    dst = _team_in_run(db, run, body.to_team_id)
    if tm.team_id != dst.id:  # 이미 그 팀이면 변화 없음
        tm.team_id = dst.id
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/runs/{run_id}/swap", status_code=204, response_class=Response, response_model=None)
def swap_members(
    run_id: uuid.UUID,
    body: SwapMembersRequest,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> Response:
    """두 학생의 소속 팀을 맞바꾼다."""
    run = _get_run_for_edit(db, run_id, prof)
    _ta, a = _find_member(run, body.student_a)
    _tb, b = _find_member(run, body.student_b)
    a.team_id, b.team_id = b.team_id, a.team_id
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/runs/{run_id}/role", status_code=204, response_class=Response, response_model=None)
def set_member_role(
    run_id: uuid.UUID,
    body: SetMemberRoleRequest,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> Response:
    """팀원의 배정 역할을 수정."""
    run = _get_run_for_edit(db, run_id, prof)
    _team, tm = _find_member(run, body.student_id)
    tm.assigned_role = body.assigned_role
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- 7번: 확정 / 확정 해제 --------------------------------------------
@router.post("/runs/{run_id}/confirm", response_model=RunStatusOut)
def confirm_run(
    run_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> RunStatusOut:
    """매칭 결과를 최종 확정한다(이후 수정 잠금)."""
    run = db.get(MatchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="매칭 이력을 찾을 수 없습니다.")
    get_owned_class(db, run.class_id, prof)
    if run.confirmed_at is None:
        run.confirmed_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
    return RunStatusOut(
        run_id=run.id, class_id=run.class_id,
        confirmed=True, confirmed_at=run.confirmed_at,
    )


@router.post("/runs/{run_id}/unconfirm", response_model=RunStatusOut)
def unconfirm_run(
    run_id: uuid.UUID,
    prof: User = Depends(require_professor),
    db: Session = Depends(get_db),
) -> RunStatusOut:
    """확정을 해제해 다시 수정 가능하게 한다."""
    run = db.get(MatchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="매칭 이력을 찾을 수 없습니다.")
    get_owned_class(db, run.class_id, prof)
    run.confirmed_at = None
    db.commit()
    return RunStatusOut(
        run_id=run.id, class_id=run.class_id,
        confirmed=False, confirmed_at=None,
    )
