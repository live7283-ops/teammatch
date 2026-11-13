"""조건 우선순위 · 공통 시간 최소 조건 · 조건 카탈로그 검증 (AI 담당).

실행: cd backend && python -m pytest -q tests/test_priority_conditions.py
"""
import random

from app.engine.catalog import catalog
from app.engine.constraints import (PRIORITY_RATIO, HardRules, SoftWeights, common_slots, has_tag, objective,
                                    priority_order, rule_ids, rule_weights, team_violations, total_violations,
                                    violation_breakdown)
from app.engine.explain import evaluate, hard_from_detail
from app.engine.optimizer import optimize
from app.engine.precheck import precheck
from app.engine.scoring import Evaluator
from app.matching import Candidate
from app.schemas import HardRulesIn, MatchV2Request

ROLES = ["기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표"]
MAJORS = ["수리데이터사이언스학과", "SW융합학과", "컴퓨터공학과", "경영학과", "시각디자인학과", "전기전자공학과"]


def make_class(n=40, seed=1):
    rng = random.Random(seed)
    out = []
    for k in range(n):
        slots = {f"{d}-{b}" for d in range(5) for b in range(12) if rng.random() < 0.6}
        out.append(Candidate(student_id=f"s{k:03d}", name=f"학생{k:02d}", major=rng.choice(MAJORS),
                             year=rng.choice([2, 3, 4]), roles=rng.sample(ROLES, rng.choice([2, 2, 3])),
                             free_slots=slots, traits={key: rng.randint(1, 5) for key in ("pace", "prep", "lead", "comm")}))
    return out


def cand(sid, roles=("기획",), slots=(), major="A학과", year=2):
    return Candidate(student_id=sid, name=sid, major=major, year=year, roles=list(roles), free_slots=set(slots),
                     traits={"pace": 3, "prep": 3, "lead": 4, "comm": 3})


def all_rules(cands):
    ids = [c.student_id for c in cands]
    return HardRules(same_major_max=2, role_minimums={"개발": 1, "발표": 1}, spread_tags=["4학년"],
                     separate_pairs=[(ids[0], ids[1])], fixed_pairs=[(ids[2], ids[3])], min_common_hours=3)


def random_teams(cands, rng, size=4):
    order = list(cands)
    rng.shuffle(order)
    return [order[i:i + size] for i in range(0, len(order), size)]


# ── 조건 id · 배수 ──────────────────────────────────────────────────
def test_rule_ids_cover_every_rule():
    cands = make_class(12)
    hard = all_rules(cands)
    assert rule_ids(hard) == ["same_major_max", "role_min:개발", "role_min:발표", "spread:4학년",
                              "min_common_hours", "separate:0", "fixed:0"]


def test_no_priority_means_equal_weights():
    hard = all_rules(make_class(12))
    assert set(rule_weights(hard).values()) == {1.0}


def test_priority_weights_step_by_ratio_and_unlisted_rules_rank_above():
    hard = all_rules(make_class(12))
    hard.priority = ["role_min:개발", "same_major_max", "min_common_hours", "없는 조건", "role_min:개발"]
    assert priority_order(hard) == ["role_min:개발", "same_major_max", "min_common_hours"]   # 없는 id·중복 무시
    w = rule_weights(hard)
    assert w["min_common_hours"] == 1.0
    assert w["same_major_max"] == PRIORITY_RATIO
    assert w["role_min:개발"] == PRIORITY_RATIO ** 2
    for unlisted in ("role_min:발표", "spread:4학년", "separate:0", "fixed:0"):
        assert w[unlisted] == PRIORITY_RATIO ** 3


# ── 채점기 일치 ────────────────────────────────────────────────────
def test_fast_evaluator_matches_reference_with_new_rule():
    cands = make_class(40, seed=3)
    hard = all_rules(cands)
    rng = random.Random(0)
    for _ in range(20):
        teams = random_teams(cands, rng)
        ev = Evaluator(cands, SoftWeights(), hard, len(teams))
        fast = sum(ev.team([ev.idx[m.student_id] for m in t])[1] for t in teams)
        assert round(fast) == total_violations(teams, hard)
        assert sum(violation_breakdown(teams, hard).values()) == total_violations(teams, hard)


def test_without_priority_cost_equals_count():
    cands = make_class(40, seed=4)
    hard = all_rules(cands)
    ev = Evaluator(cands, SoftWeights(), hard, 10)
    assert ev.weighted is False
    rng = random.Random(1)
    for t in random_teams(cands, rng):
        idx = [ev.idx[m.student_id] for m in t]
        assert ev.team(idx) == ev.scored(idx)


def test_weighted_objective_matches_between_reference_and_evaluator():
    cands = make_class(40, seed=5)
    hard = all_rules(cands)
    hard.priority = ["role_min:발표", "min_common_hours", "same_major_max"]
    teams = random_teams(cands, random.Random(2))
    ev = Evaluator(cands, SoftWeights(), hard, len(teams))
    scores, costs = [], []
    for t in teams:
        f, c = ev.scored([ev.idx[m.student_id] for m in t])
        scores.append(f)
        costs.append(c)
    j = ev.j_value(scores, costs)
    assert abs(j - objective(teams, SoftWeights(), hard).j) < 1e-6


# ── 공통 시간 최소 조건 ────────────────────────────────────────────
def test_min_common_hours_violation_is_one_per_short_team():
    mon = [f"0-{b}" for b in range(4)]
    tue = [f"1-{b}" for b in range(4)]
    ok_team = [cand("a", slots=mon), cand("b", slots=mon)]
    bad_team = [cand("c", slots=mon), cand("d", slots=tue)]
    hard = HardRules(min_common_hours=3)
    assert team_violations(ok_team, hard) == 0
    assert team_violations(bad_team, hard) == 1
    assert violation_breakdown([ok_team, bad_team], hard) == {"min_common_hours": 1}


def test_optimizer_enforces_min_common_hours():
    # 요일별로 시간이 갈리는 12명: 같은 요일끼리 묶어야만 공통 4시간이 나온다
    cands = []
    for day in range(3):
        for k in range(4):
            cands.append(cand(f"d{day}k{k}", roles=[ROLES[k], ROLES[k + 1]], major=MAJORS[k],
                              slots=[f"{day}-{b}" for b in range(5)] + [f"4-{(day * 4 + k) % 12}"]))
    hard = HardRules(min_common_hours=4)
    assert precheck(cands, 4, hard).feasible
    sol = optimize(cands, 4, SoftWeights(), hard, starts=2, seed=1)
    assert sol.obj.violations == 0
    assert all(len(common_slots(t)) >= 4 for t in sol.teams)
    cond = {c["rule_id"]: c for c in sol.details["conditions"]}
    assert cond["min_common_hours"]["satisfied"] is True
    assert cond["min_common_hours"]["label"] == "공통 가능 시간 주 4시간 이상"


def test_precheck_min_common_hours_flags_students_with_too_few_hours():
    cands = make_class(12, seed=2)
    cands[0].free_slots = {"0-1"}
    item = next(i for i in precheck(cands, 4, HardRules(min_common_hours=2)).items if i.rule_id == "min_common_hours")
    assert item.ok is False and "1명" in item.detail
    assert item.fix == {"op": "set", "path": "hard.min_common_hours", "value": 1}
    cands[0].free_slots = set()                      # 가능 시간을 아예 안 낸 학생 → 조건을 빼라고 안내
    res = precheck(cands, 4, HardRules(min_common_hours=2))
    item = next(i for i in res.items if i.rule_id == "min_common_hours")
    assert res.feasible is False and item.fix["op"] == "remove"


def test_precheck_items_carry_rule_ids():
    cands = make_class(12, seed=2)
    hard = all_rules(cands)
    hard.min_common_hours = 1
    hard.priority = ["same_major_max", "지운 조건"]
    items = precheck(cands, 4, hard).items
    got = {i.rule_id for i in items if i.rule_id}
    assert {"same_major_max", "role_min:개발", "role_min:발표", "spread:4학년", "min_common_hours"} <= got
    info = next(i for i in items if i.name == "조건 우선순위")
    assert info.ok and "same_major_max" in info.detail and "지운 조건" in info.detail


# ── 우선순위: 다 지킬 수 없을 때 아래 순위부터 양보 ─────────────────
def _conflict_class():
    """발표 희망자가 p1, p2 둘뿐인 8명·2팀. '각 팀 발표 1명'과 'p1·p2 같은 팀'은 동시에 지킬 수 없다."""
    slots = [f"0-{b}" for b in range(6)]
    cands = [cand("p1", roles=["발표", "기획"], slots=slots, major="A학과"),
             cand("p2", roles=["발표", "디자인"], slots=slots, major="B학과")]
    for k in range(6):
        cands.append(cand(f"x{k}", roles=[ROLES[k % 5], ROLES[(k + 1) % 5]], slots=slots, major=MAJORS[k % 4]))
    return cands


def _presenters_per_team(sol):
    return sorted(sum(1 for m in t if has_tag(m, "발표")) for t in sol.teams)


def test_priority_decides_which_rule_gives_way():
    cands = _conflict_class()
    base = dict(role_minimums={"발표": 1}, fixed_pairs=[("p1", "p2")])
    assert precheck(cands, 4, HardRules(**base)).feasible          # 하나씩은 가능해서 사전 점검은 통과

    for seed in range(1, 6):
        role_first = optimize(cands, 4, SoftWeights(), HardRules(**base, priority=["role_min:발표", "fixed:0"]),
                              starts=2, seed=seed)
        assert _presenters_per_team(role_first) == [1, 1]          # 발표 조건을 지키고 고정 쌍을 양보
        cond = {c["rule_id"]: c for c in role_first.details["conditions"]}
        assert cond["role_min:발표"]["satisfied"] and not cond["fixed:0"]["satisfied"]
        assert [c["rule_id"] for c in role_first.details["conditions"]] == ["role_min:발표", "fixed:0"]
        assert [c["priority"] for c in role_first.details["conditions"]] == [1, 2]

        pair_first = optimize(cands, 4, SoftWeights(), HardRules(**base, priority=["fixed:0", "role_min:발표"]),
                              starts=2, seed=seed)
        assert _presenters_per_team(pair_first) == [0, 2]          # 고정 쌍을 지키고 발표 조건을 양보
        cond = {c["rule_id"]: c for c in pair_first.details["conditions"]}
        assert cond["fixed:0"]["satisfied"] and not cond["role_min:발표"]["satisfied"]
        assert role_first.obj.violations == pair_first.obj.violations == 1


def test_priority_does_not_cost_anything_when_all_rules_can_hold():
    cands = make_class(40, seed=6)
    base = dict(same_major_max=2, role_minimums={"개발": 1}, min_common_hours=2)
    plain = optimize(cands, 4, SoftWeights(), HardRules(**base), starts=2, seed=3, time_limit=None)
    ranked = optimize(cands, 4, SoftWeights(), HardRules(**base, priority=["role_min:개발", "same_major_max",
                                                                         "min_common_hours"]),
                      starts=2, seed=3, time_limit=None)
    assert plain.obj.violations == ranked.obj.violations == 0
    # 위반이 없으면 벌점이 0이라 순위는 결과에 영향을 주지 않는다
    assert [[m.student_id for m in t] for t in plain.teams] == [[m.student_id for m in t] for t in ranked.teams]


def test_evaluate_reports_priority_and_weighted_j():
    cands = _conflict_class()
    hard = HardRules(role_minimums={"발표": 1}, fixed_pairs=[("p1", "p2")], priority=["fixed:0", "role_min:발표"])
    teams = [["p1", "x0", "x1", "x2"], ["p2", "x3", "x4", "x5"]]     # 고정 쌍(1순위)을 어긴 편성
    out = evaluate(cands, teams, SoftWeights(), hard)
    assert out["hard_violations"] == 1
    assert [(c["rule_id"], c["priority"], c["satisfied"]) for c in out["conditions"]] == \
        [("fixed:0", 1, False), ("role_min:발표", 2, True)]
    assert out["objective_j"] < -9000          # 1순위 위반 1건 = 1000 × 10


# ── 저장·입력 형식 ─────────────────────────────────────────────────
def test_hard_detail_roundtrip_keeps_new_fields():
    hard = hard_from_detail({"same_major_max": 2, "min_common_hours": 3, "priority": ["min_common_hours"]})
    assert hard.min_common_hours == 3 and hard.priority == ["min_common_hours"]
    old = hard_from_detail({"same_major_max": 2})            # 이전에 저장된 편성(새 키 없음)
    assert old.min_common_hours is None and old.priority == []


def test_request_schema_defaults():
    body = MatchV2Request(team_size=4)                       # 가중치 생략 → 엔진 기본값
    w = SoftWeights()
    assert (body.weights.major, body.weights.role, body.weights.time, body.weights.trait) == \
        (w.major, w.role, w.time, w.trait)
    assert body.hard.min_common_hours is None and body.hard.priority == []
    hard = HardRulesIn(min_common_hours=2, priority=["role_min:개발", "min_common_hours"])
    assert hard.priority[0] == "role_min:개발"


# ── 조건 카탈로그 ──────────────────────────────────────────────────
def test_catalog_lists_conditions_from_survey_fields():
    cands = make_class(45, seed=7)
    cat = catalog(cands, 4)
    assert cat["team_count"] == 11 and sum(cat["sizes"]) == 45
    by_kind = {c["kind"]: c for c in cat["conditions"]}
    assert set(by_kind) == {"role_min", "same_major_max", "spread", "min_common_hours", "separate", "fixed"}
    assert by_kind["min_common_hours"]["check"] == "after_run"
    assert all(c["check"] == "instant" for k, c in by_kind.items() if k != "min_common_hours")

    tags = {o["value"]: o for o in by_kind["role_min"]["params"][0]["options"]}
    assert {"개발", "발표", "리더", "2학년"} <= set(tags)
    dev = sum(1 for c in cands if has_tag(c, "개발"))
    assert tags["개발"]["holders"] == dev and tags["개발"]["max"] == min(dev // 11, 4)

    hours = by_kind["min_common_hours"]["params"][0]
    assert hours["max"] == min(len(c.free_slots) for c in cands)
    assert [a["key"] for a in cat["always_on"]] == ["major", "role", "time", "trait"]
    assert any("유학생" in u["label"] for u in cat["unsupported"])


def test_catalog_limits_agree_with_precheck():
    cands = make_class(45, seed=8)
    cat = catalog(cands, 4)
    by_kind = {c["kind"]: c for c in cat["conditions"]}
    for o in by_kind["role_min"]["params"][0]["options"]:
        if o["max"] >= 1:        # 카탈로그가 가능하다고 한 값은 사전 점검도 통과해야 한다
            assert precheck(cands, 4, HardRules(role_minimums={o["value"]: o["max"]})).feasible
        assert not precheck(cands, 4, HardRules(role_minimums={o["value"]: o["max"] + 1})).feasible
    low = by_kind["same_major_max"]["params"][0]["min"]
    assert precheck(cands, 4, HardRules(same_major_max=low)).feasible
    top = by_kind["min_common_hours"]["params"][0]["max"]
    assert precheck(cands, 4, HardRules(min_common_hours=top)).feasible
    assert not precheck(cands, 4, HardRules(min_common_hours=top + 1)).feasible
