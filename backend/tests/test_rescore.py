"""저장된 편성 다시 채점(rescore_run) 테스트 — DB 없이 MatchRun 모양의 객체로 검증 (AI 담당)."""
from types import SimpleNamespace as NS

from app.engine.constraints import HardRules, SoftWeights
from app.engine.explain import evaluate, hard_from_detail, rescore_run
from app.matching import Candidate

ROLES = ["기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표"]


def cand(i, major, year, roles):
    return Candidate(student_id=f"00000000-0000-0000-0000-{i:012d}", name=f"학생{i}", major=major, year=year,
                     roles=roles, free_slots={f"{d}-{b}" for d in range(2) for b in range(i % 3, 6)},
                     traits={"pace": 1 + i % 5, "prep": 3, "lead": 1 + (i * 2) % 5, "comm": 3})


C = [cand(i, ["A학과", "B학과", "C학과"][i % 3], 2 + i % 3, [ROLES[i % 6], ROLES[(i + 1) % 6]]) for i in range(12)]
DETAIL = {"same_major_max": 2, "separate_pairs": [[C[0].student_id, C[1].student_id]], "fixed_pairs": [],
          "spread_tags": ["4학년"], "role_minimums": {"발표": 1}}


def make_run(groups):
    teams = [NS(id=f"t{k}", fit_score=0, members=[NS(student_id=C[i].student_id) for i in g])
             for k, g in enumerate(groups)]
    return NS(teams=teams, w_major=4, w_role=5, w_time=3, w_trait=3, hard_detail=DETAIL, team_size=4, avg_score=0)


def test_hard_from_detail_roundtrip():
    h = hard_from_detail(DETAIL)
    assert h.same_major_max == 2 and h.separate_pairs == [(C[0].student_id, C[1].student_id)]
    assert h.spread_tags == ["4학년"] and h.role_minimums == {"발표": 1}
    assert hard_from_detail(None) == HardRules()


def test_rescore_matches_evaluate_and_updates_scores():
    groups = [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]]          # 0과 1이 같은 팀 → 분리 규칙 위반
    run = make_run(groups)
    out = rescore_run(run, C)
    ref = evaluate(C, [[C[i].student_id for i in g] for g in groups], SoftWeights(4, 5, 3, 3),
                   hard_from_detail(DETAIL), team_size=4)
    for team, r in zip(run.teams, ref["teams"]):                   # evaluate는 소수 1자리, 저장은 2자리
        assert abs(team.fit_score - r["fit_score"]) < 0.06
    assert abs(run.avg_score - ref["avg_fit"]) < 0.06
    assert out["hard_violations"] == ref["hard_violations"] >= 1
    assert "separate:0" in out["teams"][0]["violations"]
    assert out["team_ids"] == ["t0", "t1", "t2"]


def test_move_changes_scores():
    before = make_run([[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]])
    rescore_run(before, C)
    after = make_run([[0, 2, 3, 4], [1, 5, 6, 7], [8, 9, 10, 11]])  # 1과 4를 맞바꿈 → 분리 위반 해소
    out = rescore_run(after, C)
    assert out["hard_violations"] < rescore_run(before, C)["hard_violations"]
    assert after.teams[2].fit_score == before.teams[2].fit_score      # 손대지 않은 팀은 그대로


def test_empty_team_and_unknown_member():
    run = make_run([[0, 1, 2, 3, 4, 5, 6, 7], [], [8, 9, 10, 11]])
    run.teams[2].members.append(NS(student_id="ffffffff-0000-0000-0000-000000000000"))   # 설문 철회한 학생
    out = rescore_run(run, C)
    assert run.teams[1].fit_score == 0
    assert out["skipped_members"] == ["ffffffff-0000-0000-0000-000000000000"]
    assert out["team_ids"] == ["t0", "t2"]
    assert any("인원 8명" in w for w in out["teams"][0]["warnings"])
