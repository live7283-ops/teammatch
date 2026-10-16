import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.models import User
from app.security import require_professor

client = TestClient(app)


def test_unauthenticated_access_denied():
    """인증 토큰 없이 접근 시 401 Unauthorized 상태 코드가 반환되는지 검증합니다."""
    dummy_uuid = str(uuid.uuid4())

    assert client.get(f"/api/classes/{dummy_uuid}/matches").status_code == 401
    assert client.get(f"/api/matchings/{dummy_uuid}").status_code == 401
    assert client.put(f"/api/teams/{dummy_uuid}", json={"name": "팀명 변경 테스트"}).status_code == 401
    assert client.post(f"/api/matchings/{dummy_uuid}/confirm").status_code == 401


def test_invalid_uuid_handling():
    """로그인된 상태에서 잘못된 UUID 형식이 들어왔을 때 422 Unprocessable Entity를 내는지 검증합니다."""
    # 테스트용 가짜 교수 계정 주입
    mock_prof = User(id=uuid.uuid4(), role="professor", name="테스트교수", email="prof@test.com")
    app.dependency_overrides[require_professor] = lambda: mock_prof

    try:
        invalid_id = "not-a-valid-uuid"

        assert client.get(f"/api/classes/{invalid_id}/matches").status_code == 422
        assert client.get(f"/api/matchings/{invalid_id}").status_code == 422
        assert client.put(f"/api/teams/{invalid_id}", json={"name": "테스트"}).status_code == 422
        assert client.post(f"/api/matchings/{invalid_id}/confirm").status_code == 422
    finally:
        app.dependency_overrides.clear()