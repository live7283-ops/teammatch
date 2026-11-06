"""TeamFit 엔진 v1.1 포팅 검증 (AI 담당). 실행: cd backend && python -m pytest -q tests/test_engine_port.py"""
import random

import pytest

# app/engine/__init__.py는 팀원 파일을 그대로 두므로, 새 모듈에서 직접 import 한다.
from app.engine.constraints import (HardRules, SoftWeights, best_roles, has_tag, objective, soft_score,
                                    team_violations)
from app.engine.explain import EvaluateError, evaluate
from app.engine.optimizer import optimize
from app.engine.precheck import precheck, team_sizes
from app.engine.scoring import Evaluator
from app.matching import Candidate

ROLES = ["기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표"]
MAJORS = ["수리데이터사이언스학과", "SW융합학과", "컴퓨터공학과", "경영학과", "시각디자인학과", "전기전자공학과"]


def make_class(n=45, seed=1, no_presenter=False):
    rng = random.Random(seed)
    out = []
    for k in range(n):
        roles = rng.sample(ROLES, rng.choice([2, 2, 3]))
        if no_presenter:
            roles = [r for r in roles if r != "발표"] or ["기획"]
        slots = {f"{d}-{b}" for d in range(5) for b in range(12) if rng.random() < 0.45}
        traits = {key: rng.randint(1, 5) for key in ("pace", "prep", "lead", "comm")}
        out.append(Candidate(student_id=f"s{k:03d}", name=f"학생{k:02d}", major=rng.choice(MAJORS),
                             year=rng.choice([2, 3, 4]), roles=roles, free_slots=slots, traits=traits))
    return out


W = SoftWeights(4, 5, 3, 3)


@pytest.mark.parametrize("n,size,expected", [
    (45, 4, [5] + [4] * 10), (46, 4, [5, 5] + [4] * 9), (44, 4, [4] * 11),
    (7, 4, [4, 3]), (5, 4, [5]), (3, 4, [3]), (8, 4, [4, 4]), (30, 6, [6] * 5),
])
def test_team_sizes(n, size, expected):
    assert team_sizes(n, size) == expected
    assert sum(team_sizes(n, size)) == n


def test_tag_aliases():
    c = Candidate(student_id="a", name="가", major="경영학과", year=4, roles=["발표", "백엔드"],
                  free_slots=set(), traits={"lead": 5})
    assert has_tag(c, "발표") and has_tag(c, "개발") and has_tag(c, "4학년") and has_tag(c, "경영학과")
    assert has_tag(c, "리더") and not has_tag(c, "디자인") and not has_tag(c, "3학년")


def test_best_roles_respects_rank():
    total, roles = best_roles([("프론트엔드", "백엔드"), ("프론트엔드", "디자인"), ("프론트엔드",)])
    assert roles[2] == "프론트엔드"                      # 1지망뿐인 사람이 프론트엔드
    assert abs(total - (1.0 + 0.6 + 0.6)) < 1e-9
    assert sorted(r for r in roles if r) == ["디자인", "백엔드", "프론트엔드"]


def test_fast_scorer_matches_reference():
    C = make_class(40, 3)
    hard = HardRules(same_major_max=2, role_minimums={"발표": 1, "개발": 1}, spread_tags=["4학년"],
                     separate_pairs=[("s001", "s002")], fixed_pairs=[("s003", "s004")])
    ev = Evaluator(C, W, hard, 10)
    rng = random.Random(0)
    n_majors = len({c.major for c in C})
    for _ in range(200):
        idx = rng.sample(range(40), 4)
        f, h = ev.team(idx)
        members = [C[i] for i in idx]
        assert abs(f - soft_score(members, W, n_majors)) < 1e-9
        ref = team_violations(members, hard, ev.caps)
        assert abs(h - ref) <= 0.5 * sum(1 for a, b in hard.fixed_pairs
                                         if (a in {m.student_id for m in members}) != (b in {m.student_id for m in members}))


def test_optimize_feasible_class_has_no_violations():
    C = make_class(45, 1)
    hard = HardRules(same_major_max=2, role_minimums={"발표": 1, "개발": 1}, spread_tags=["4학년"],
                     separate_pairs=[("s000", "s001"), ("s002", "s003")], fixed_pairs=[("s010", "s011")])
    assert precheck(C, 4, hard).feasible
    sol = optimize(C, 4, W, hard, starts=2, seed=7)
    assert sol.obj.violations == 0
    assert sorted(len(t) for t in sol.teams) == sorted(team_sizes(45, 4))
    where = {m.student_id: i for i, t in enumerate(sol.teams) for m in t}
    assert where["s000"] != where["s001"] and where["s002"] != where["s003"]
    assert where["s010"] == where["s011"]
    cap = -(-sum(1 for c in C if c.year == 4) // len(sol.teams))
    assert max(sum(1 for m in t if m.year == 4) for t in sol.teams) <= cap
    ref = objective(sol.teams, W, hard)
    assert abs(ref.j - sol.obj.j) < 1e-6 and ref.violations == 0
    assert sol.trace.stage[0] == "초기 배치" and sol.trace.stage[-1] == "최종"
    assert sol.obj.min_fit >= sol.trace.low[0] - 1e-9


def test_optimize_is_reproducible():
    C = make_class(30, 2)
    a = optimize(C, 4, W, HardRules(same_major_max=2), starts=1, seed=11)
    b = optimize(C, 4, W, HardRules(same_major_max=2), starts=1, seed=11)
    assert [[m.student_id for m in t] for t in a.teams] == [[m.student_id for m in t] for t in b.teams]


def test_details_shape():
    C = make_class(24, 5)
    sol = optimize(C, 4, W, HardRules(role_minimums={"발표": 1}), starts=2, seed=1)
    d = sol.details
    assert len(d["teams"]) == len(sol.teams) == 6 and len(d["alternatives"]) == 1
    t = d["teams"][0]
    assert set(t) >= {"fit_score", "subscores", "common_hours", "common_slots", "summary", "warnings",
                      "violations", "members", "is_lowest"}
    assert [m["student_id"] for m in t["members"]] == [m.student_id for m in sol.teams[0]]
    for m, c in zip(t["members"], sol.teams[0]):
        if m["preference_rank"] is not None:
            assert c.roles[m["preference_rank"] - 1] == m["assigned_role"]
    assert d["conditions"][0]["rule_id"] == "role_min:발표"


def test_precheck_reports_fix():
    C = make_class(45, 1, no_presenter=True)
    C[0] = Candidate(student_id="p0", name="발표자", major=MAJORS[0], year=3, roles=["발표"],
                     free_slots=set(), traits={})
    res = precheck(C, 4, HardRules(role_minimums={"발표": 1}, spread_tags=["유학생"]))
    assert not res.feasible
    bad = {i.name: i for i in res.items if not i.ok}
    assert bad["각 팀 '발표' 1명 이상"].fix == {"op": "set", "path": "hard.role_minimums.발표", "value": 0}
    assert bad["태그 '유학생'"].fix == {"op": "remove", "path": "hard.spread_tags", "value": "유학생"}


def test_evaluate_rescores_and_validates():
    C = make_class(12, 4)
    teams = [[c.student_id for c in C[i:i + 4]] for i in (0, 4, 8)]
    out = evaluate(C, teams, W, HardRules(separate_pairs=[("s000", "s001")]), team_size=4)
    assert out["hard_violations"] == 1 and out["teams"][0]["violations"] == ["separate:0"]
    assert out["conditions"][0]["satisfied"] is False
    with pytest.raises(EvaluateError) as e:
        evaluate(C, teams[:2], W, HardRules())
    assert e.value.code == "INVALID_TEAMS"
    with pytest.raises(EvaluateError) as e:
        evaluate(C, teams + [["nobody"]], W, HardRules())
    assert e.value.code == "UNKNOWN_STUDENT"


def test_missing_major_and_year_are_tolerated():
    C = make_class(16, 9)
    C[0] = Candidate(student_id="x0", name="미입력", major=None, year=None, roles=["발표"],
                     free_slots=set(), traits={})
    C[1] = Candidate(student_id="x1", name="미입력2", major=None, year=None, roles=[],
                     free_slots=set(), traits={})
    hard = HardRules(same_major_max=1, role_minimums={"발표": 1}, spread_tags=["4학년"])
    precheck(C, 4, hard)
    sol = optimize(C, 4, W, hard, starts=1, seed=3)
    assert sum(len(t) for t in sol.teams) == 16
    ref = objective(sol.teams, W, hard)
    assert abs(ref.j - sol.obj.j) < 1e-6
