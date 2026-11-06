"""실제 DB 및 FastAPI 라우터 연동 매칭 E2E 통합 테스트.

시드 데이터(45명)를 바탕으로 다음 전체 흐름을 자동 검증합니다:
1. 교수 계정 로그인 & JWT 토큰 발급
2. 수업(DEMO45) ID 조회
3. POST /api/matching/v2/classes/{class_id}/run 매칭 실행
4. DB (MatchRun, Team, TeamMember) 테이블 영속성 및 45명 전원 배치 여부 검증

실행 방법:
    docker compose exec backend pytest tests/test_full_matching_flow.py -v -s
"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine
from app.main import app
from app.models import Class, MatchRun, Team, TeamMember

client = TestClient(app)


def test_full_matching_e2e_flow():
    # 1. 교수 계정 로그인 및 토큰 발급
    login_res = client.post(
        "/api/auth/login",
        data={"username": "prof_demo@teammatch.ai", "password": "password123"},
    )
    assert login_res.status_code == 200, f"로그인 실패: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. DEMO45 수업 조회
    classes_res = client.get("/api/classes/", headers=headers)
    assert classes_res.status_code == 200, f"수업 조회 실패: {classes_res.text}"
    classes = classes_res.json()

    demo_class = next((c for c in classes if c.get("join_code") == "DEMO45"), None)
    assert demo_class is not None, "DEMO45 수업이 존재하지 않습니다. (seed_demo 실행 필요)"
    class_id = demo_class["id"]

    # 3. v2 매칭 알고리즘 실행 (Pydantic 중첩 스키마 적용)
    payload = {
        "team_size": 4,
        "weights": {
            "major": 3,
            "role": 3,
            "time": 3,
            "trait": 3
        },
        "hard_constraints": {
            "same_major_max": 2
        }
    }
    match_res = client.post(
        f"/api/classes/{class_id}/match-v2",
        json=payload,
        headers=headers,
    )
    assert match_res.status_code == 200, f"매칭 실행 실패: {match_res.text}"

    # 4. DB 실제 저장 및 45명 누락 없는 팀 배치 검증
    with Session(engine) as db:
        # 생성된 최신 MatchRun 검증
        run = db.scalar(
            select(MatchRun)
            .where(MatchRun.class_id == class_id)
            .order_by(MatchRun.created_at.desc())
        )
        assert run is not None, "MatchRun 데이터가 DB에 저장되지 않았습니다."
        assert run.team_size == 4

        # 생성된 팀 목록 조회
        teams = db.scalars(select(Team).where(Team.run_id == run.id)).all()
        assert len(teams) > 0, "생성된 팀이 없습니다."

        # 45명 전원 누락 없이 특정 팀에 소속되었는지 검증
        total_members = 0
        for team in teams:
            members = db.scalars(select(TeamMember).where(TeamMember.team_id == team.id)).all()
            total_members += len(members)

        assert total_members == 45, f"배치된 총 인원이 45명이 아닙니다 (실제: {total_members}명)"

        print(f"\n [E2E 성공] 45명 학생이 누락 없이 총 {len(teams)}개 팀으로 매칭 완료되었습니다!")