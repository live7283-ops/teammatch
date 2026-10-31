"""실제 서버 + PostgreSQL로 매칭 전체 흐름을 한 번에 검증한다 (DB 필요, 데이터가 실제로 생성됨).

흐름: 교수 가입 → 수업 생성 → 학생 N명 가입·참여·설문 → 사전 점검 → match-v2 → 결과 조회
      → 팀원 교체(swap)·이동(move) 후 점수 재계산 확인 → 확정 → 확정 후 수정 차단(409) → 확정 해제 → 팀 상세

    # 서버를 먼저 띄운 뒤 (backend/에서)
    uvicorn app.main:app --port 8000
    python scripts/e2e_match_flow.py --base http://127.0.0.1:8000 --n 45

외부 패키지 없이 표준 라이브러리만 쓴다. 학생 데이터는 scripts/engine_demo.py의 합성 수강생을 쓴다.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))

from engine_demo import NOTE, make_class                      # noqa: E402

from app.engine.constraints import HardRules, SoftWeights     # noqa: E402
from app.engine.explain import evaluate                       # noqa: E402
from app.matching import Candidate                            # noqa: E402

OK, FAIL = "  OK ", "  NG "
problems = []


def call(base, method, path, token=None, body=None, form=None):
    data, headers = None, {}
    if body is not None:
        data, headers["content-type"] = json.dumps(body).encode(), "application/json"
    if form is not None:
        data, headers["content-type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode(errors="replace")


def check(cond, label):
    print((OK if cond else FAIL) + label)
    if not cond:
        problems.append(label)
    return cond


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=45)
    ap.add_argument("--seed", type=int, default=4)
    a = ap.parse_args()
    tag = str(int(time.time()))
    base = a.base.rstrip("/")

    # 1) 교수 가입 + 수업
    s, r = call(base, "POST", "/api/auth/signup", body={"role": "professor", "name": "교수", "school": "한양대",
                                                         "email": f"prof{tag}@test.com", "password": "password123"})
    check(s == 201, f"교수 가입 ({s})")
    prof = r["access_token"]
    s, cls = call(base, "POST", "/api/classes", prof, {"name": "캡스톤", "code": "SW" + tag[-4:], "term": "2026_2"})
    check(s == 201, f"수업 생성 ({s})")
    class_id, join = cls["id"], cls["join_code"]

    # 2) 학생 N명: 가입 → 참여 → 설문
    t0 = time.perf_counter()
    for k, c in enumerate(make_class(a.n, a.seed)):
        s, r = call(base, "POST", "/api/auth/signup", body={
            "role": "student", "name": c.name, "email": f"s{tag}_{k}@test.com", "password": "password123",
            "major": c.major, "year": c.year, "student_id": f"2026{tag[-4:]}{k:03d}"})
        tok = r["access_token"]
        call(base, "POST", "/api/classes/join", tok, {"join_code": join})
        avail = [{"day": int(x.split("-")[0]), "block": int(x.split("-")[1]), "state": "y"} for x in sorted(c.free_slots)]
        s, _ = call(base, "PUT", f"/api/classes/{class_id}/survey", tok, {
            "roles": c.roles, "skills": [], "traits": c.traits, "availability": avail, "match_ready": True})
        if s != 200:
            check(False, f"설문 제출 실패 {c.name} ({s})")
    print(f"     학생 {a.n}명 가입·참여·설문 ({time.perf_counter() - t0:.1f}초)")

    # 3) 사전 점검 + match-v2
    body = {"team_size": 4, "weights": {"major": 4, "role": 5, "time": 3, "trait": 3},
            "hard": {"same_major_max": 2, "spread_tags": [], "role_minimums": {}}, "note": NOTE, "starts": 3, "seed": 0}
    s, pre = call(base, "POST", f"/api/classes/{class_id}/precheck", prof, body)
    check(s == 200 and pre["feasible"], f"사전 점검 가능 ({s}, {pre.get('composition') if isinstance(pre, dict) else pre})")
    if isinstance(pre, dict):
        for it in pre["items"]:
            print(f"       {'OK' if it['ok'] else 'NG'} {it['name']}: {it['detail']}")
    t0 = time.perf_counter()
    s, res = call(base, "POST", f"/api/classes/{class_id}/match-v2", prof, body)
    if not check(s == 200, f"match-v2 ({s}, {time.perf_counter() - t0:.1f}초)"):
        print("     응답:", res)
        return finish()
    print(f"     팀 {res['team_count']}개, 평균 {res['avg_fit']:.1f} · 최저 {res['min_fit']:.1f}, "
          f"하드 위반 {res['hard_violations']}, 교환 {res['swaps']}")
    check(res["hard_violations"] == 0, "하드 조건 위반 0건")
    dup = sum(len(roles) - len(set(roles)) for roles in
              ([m["assigned_role"] for m in t["members"]] for t in res["teams"]))
    check(dup == 0, f"팀 안 역할 겹침 없음 (겹침 {dup})")

    # 4) 결과 조회 = match-v2 응답
    s, cur = call(base, "GET", f"/api/classes/{class_id}/result", prof)
    check(s == 200, f"결과 조회 ({s})")
    run_id = cur["run_id"]
    by_name = {t["name"]: t for t in cur["teams"]}
    same = all(abs(by_name[t["name"]]["fit_score"] - t["fit_score"]) < 0.01 for t in res["teams"])
    check(same, "조회한 팀 점수 = 편성 응답 점수")

    # 기대값 계산용: 서버 학생 id로 만든 Candidate + 같은 조건
    demo = {c.name: c for c in make_class(a.n, a.seed)}
    cands = []
    for t in cur["teams"]:
        for m in t["members"]:
            c = demo[m["name"]]
            cands.append(Candidate(student_id=m["student_id"], name=c.name, major=c.major, year=c.year,
                                   roles=c.roles, free_slots=c.free_slots, traits=c.traits))
    hard = HardRules(same_major_max=2, spread_tags=["4학년"], role_minimums={"발표": 1, "개발": 1})
    w = SoftWeights(4, 5, 3, 3)

    def expected(result):
        teams = [[m["student_id"] for m in t["members"]] for t in result["teams"]]
        return evaluate(cands, teams, w, hard, team_size=4)

    # 5) 교체(swap): 1팀 첫 학생 ↔ 2팀 첫 학생
    t1, t2 = sorted(cur["teams"], key=lambda t: int(t["name"].rstrip("팀")))[:2]
    a_id, b_id = t1["members"][0]["student_id"], t2["members"][0]["student_id"]
    s, _ = call(base, "PATCH", f"/api/runs/{run_id}/swap", prof, {"student_a": a_id, "student_b": b_id})
    check(s == 204, f"팀원 교체 ({s})")
    s, after = call(base, "GET", f"/api/runs/{run_id}", prof)
    exp = expected(after)
    got = {t["name"]: t["fit_score"] for t in after["teams"]}
    exp_by_name = {t["name"]: e["fit_score"] for t, e in zip(after["teams"], exp["teams"])}
    check(all(abs(got[k] - exp_by_name[k]) < 0.06 for k in got), "교체 후 팀 점수 = AI 엔진 재채점 값")
    check(abs(after["avg_score"] - exp["avg_fit"]) < 0.06,
          f"교체 후 평균 재계산 ({cur['avg_score']:.2f} → {after['avg_score']:.2f})")
    changed = [n for n in (t1["name"], t2["name"]) if abs(got[n] - by_name[n]["fit_score"]) > 0.001]
    print(f"     점수 바뀐 팀: {changed or '없음'}")

    # 6) 이동(move): 3팀 첫 학생 → 4팀
    teams = {t["name"]: t for t in after["teams"]}
    mover = teams["3팀"]["members"][0]["student_id"]
    s, _ = call(base, "PATCH", f"/api/runs/{run_id}/move", prof, {"student_id": mover, "to_team_id": teams["4팀"]["id"]})
    check(s == 204, f"팀원 이동 ({s})")
    s, moved = call(base, "GET", f"/api/runs/{run_id}", prof)
    sizes = {t["name"]: len(t["members"]) for t in moved["teams"]}
    exp = expected(moved)
    check(sizes["4팀"] == len(teams["4팀"]["members"]) + 1, f"이동 후 인원 (3팀 {sizes['3팀']}명, 4팀 {sizes['4팀']}명)")
    check(abs(moved["avg_score"] - exp["avg_fit"]) < 0.06, f"이동 후 평균 재계산 ({moved['avg_score']:.2f})")

    # 7) 확정 → 수정 차단 → 해제
    s, st = call(base, "POST", f"/api/runs/{run_id}/confirm", prof)
    check(s == 200 and st["confirmed"], f"확정 ({s})")
    s, _ = call(base, "PATCH", f"/api/runs/{run_id}/swap", prof, {"student_a": a_id, "student_b": b_id})
    check(s == 409, f"확정 후 수정 차단 ({s})")
    s, st = call(base, "POST", f"/api/runs/{run_id}/unconfirm", prof)
    check(s == 200 and not st["confirmed"], f"확정 해제 ({s})")

    # 8) 팀 상세: 공통 가능 시간 = 엔진 계산
    team = moved["teams"][0]
    s, det = call(base, "GET", f"/api/teams/{team['id']}", prof)
    check(s == 200, f"팀 상세 ({s})")
    common = set.intersection(*[set(next(c for c in cands if c.student_id == m["student_id"]).free_slots)
                                for m in team["members"]])
    check(len(det["common_slots"]) == len(common), f"팀 상세 공통 시간 {len(det['common_slots'])}칸 = 엔진 계산 {len(common)}칸")
    return finish()


def finish():
    print("\n결과:", "모두 통과" if not problems else f"{len(problems)}개 실패 → " + " / ".join(problems))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
