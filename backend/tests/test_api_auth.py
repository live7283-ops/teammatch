"""API 레벨 테스트 — 인증/권한/검증/에러 형식 (백엔드1 9번).

DB에 실제로 붙지 않고도 검증 가능한 범위만 다룬다:
  - 인증 없이 보호된 엔드포인트 접근 시 401
  - 잘못된 UUID 등 요청 검증 실패 시 422
  - 공통 에러 응답 형식({"error": {...}})이 적용되는지

실제 DB 흐름(가입→매칭→조회)은 PostgreSQL 이 필요하므로 여기서 다루지 않는다.
(Docker: docker compose up 으로 DB를 띄운 뒤 수동/별도 통합 테스트로 확인)
"""
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---- 인증 없이 접근 → 401 -------------------------------------------
def test_protected_endpoints_require_auth():
    rid = str(uuid.uuid4())
    # 교수 전용 엔드포인트들: 토큰 없이 호출하면 401
    assert client.get("/api/classes").status_code == 401
    assert client.get(f"/api/classes/{rid}/roster").status_code == 401
    assert client.get(f"/api/classes/{rid}/candidates").status_code == 401
    assert client.get(f"/api/classes/{rid}/result").status_code == 401
    assert client.get(f"/api/runs/{rid}").status_code == 401
    assert client.get(f"/api/teams/{rid}").status_code == 401
    assert client.post(f"/api/runs/{rid}/confirm").status_code == 401


def test_me_requires_auth():
    assert client.get("/api/auth/me").status_code == 401


# ---- 요청 검증 실패 → 422 -------------------------------------------
def test_signup_validation():
    # 비밀번호 8자 미만 → 검증 실패
    r = client.post("/api/auth/signup", json={
        "role": "student", "name": "A", "email": "a@test.com",
        "password": "short", "student_id": "1", "major": "CS", "year": 2,
    })
    assert r.status_code == 422


def test_invalid_email_rejected():
    r = client.post("/api/auth/signup", json={
        "role": "professor", "name": "A", "email": "not-an-email",
        "password": "password123",
    })
    assert r.status_code == 422


# ---- 공통 에러 응답 형식 -------------------------------------------
def test_error_response_shape_on_401():
    """에러 응답이 통일 형식({"error":{code,message,detail,path}})인지."""
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    body = r.json()
    assert "error" in body
    err = body["error"]
    assert err["code"] == 401
    assert "message" in err
    assert err["path"] == "/api/auth/me"


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
