"""POST /api/engine/solve 테스트 (DB·인증 없음)."""
import random

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

MAJORS = ["컴퓨터공학과", "경영학과", "시각디자인학과", "SW융합학과"]
ROLES = ["기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표"]
W = {"major": 3, "role": 3, "time": 3, "trait": 3}


def _cands(n: int, seed: int = 1) -> list[dict]:
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        out.append({
            "student_id": f"s{i}",
            "name": f"학생{i}",
            "major": MAJORS[i % len(MAJORS)],
            "year": 1 + i % 4,
            "roles": rnd.sample(ROLES, 2),
            "free_slots": [f"{d}-{b}" for d in range(5) for b in range(4, 10) if rnd.random() < 0.7],
            "traits": {"pace": rnd.randint(1, 5), "prep": rnd.randint(1, 5),
                       "lead": rnd.randint(1, 5), "comm": rnd.randint(1, 5)},
        })
    return out


def test_solve_feasible():
    r = client.post("/api/engine/solve", json={
        "team_size": 4, "weights": W, "seed": 7, "candidates": _cands(12)})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["feasible"] is True
    teams = d["result"]["teams"]
    assert len(teams) == 3
    ids = sorted(m["student_id"] for t in teams for m in t["members"])
    assert ids == sorted(f"s{i}" for i in range(12))      # 전원 배정, 중복 없음
    assert d["result"]["hard_violations"] == 0
    assert d["trace"]["stage"] and d["precheck"]["feasible"] is True


def test_solve_same_seed_is_deterministic():
    body = {"team_size": 4, "weights": W, "seed": 3, "candidates": _cands(12)}
    a = client.post("/api/engine/solve", json=body).json()["result"]["teams"]
    b = client.post("/api/engine/solve", json=body).json()["result"]["teams"]
    assert [[m["student_id"] for m in t["members"]] for t in a] == [[m["student_id"] for m in t["members"]] for t in b]


def test_solve_infeasible_returns_200_with_items():
    # 2명을 같은 팀에 묶고 동시에 분리 -> 불가능
    r = client.post("/api/engine/solve", json={
        "team_size": 4, "weights": W, "candidates": _cands(12),
        "hard": {"fixed_pairs": [["s0", "s1"]], "separate_pairs": [["s0", "s1"]]}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["feasible"] is False
    assert any(not i["ok"] for i in d["precheck"]["items"])
    assert "result" not in d


def test_solve_validation():
    base = {"team_size": 4, "weights": W, "candidates": _cands(12)}
    assert client.post("/api/engine/solve", json={**base, "team_size": 1}).status_code == 422
    assert client.post("/api/engine/solve", json={**base, "weights": {**W, "major": 9}}).status_code == 422
    dup = _cands(12)
    dup[1]["student_id"] = "s0"
    assert client.post("/api/engine/solve", json={**base, "candidates": dup}).status_code == 422
    bad = _cands(12)
    bad[0]["free_slots"] = ["9-99"]
    assert client.post("/api/engine/solve", json={**base, "candidates": bad}).status_code == 422
    too_many = _cands(301)
    assert client.post("/api/engine/solve", json={**base, "candidates": too_many}).status_code == 422
