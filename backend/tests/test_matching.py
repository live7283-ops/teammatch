"""Unit tests for the pure matching engine (no DB required)."""
from app import matching as engine


def _mk(i, major, roles, slots, traits, year=2):
    return engine.Candidate(
        student_id=str(i),
        name=f"student{i}",
        major=major,
        year=year,
        roles=roles,
        free_slots=set(slots),
        traits=traits,
    )


def _pool(n=8):
    majors = ["데이터사이언스", "경영학", "컴퓨터공학", "시각디자인"]
    roles = ["기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표"]
    out = []
    for i in range(n):
        out.append(
            _mk(
                i,
                majors[i % len(majors)],
                [roles[i % len(roles)]],
                {f"{i % 5}-{b}" for b in range(3)},
                {"pace": 3, "prep": 3, "lead": 3, "comm": 3},
            )
        )
    return out


def test_team_count_and_coverage():
    pool = _pool(8)
    out = engine.form_teams(pool, team_size=4, weights=engine.Weights(), hard=engine.Hard())
    assert len(out.teams) == 2
    # Every candidate is placed exactly once.
    placed = [m.student_id for t in out.teams for m in t.members]
    assert sorted(placed) == sorted(c.student_id for c in pool)


def test_scores_bounded():
    out = engine.form_teams(_pool(9), team_size=3, weights=engine.Weights(), hard=engine.Hard())
    assert 0 <= out.avg_score <= 100
    for t in out.teams:
        assert 0 <= t.fit_score <= 100


def test_same_major_flips_major_axis():
    same = [_mk(i, "컴퓨터공학", ["기획"], {"0-0"}, {}) for i in range(3)]
    mixed = [_mk(i, m, ["기획"], {"0-0"}, {}) for i, m in enumerate(["A", "B", "C"])]
    hard = engine.Hard(same_major=True)
    w = engine.Weights(major=5, role=1, time=1, trait=1)
    assert engine.team_fit(same, w, hard) > engine.team_fit(mixed, w, hard)


def test_role_coverage_rewarded():
    w = engine.Weights(major=1, role=5, time=1, trait=1)
    diverse = [_mk(i, "A", [r], {"0-0"}, {}) for i, r in enumerate(["기획", "백엔드", "디자인"])]
    same = [_mk(i, "A", ["기획"], {"0-0"}, {}) for i in range(3)]
    assert engine.team_fit(diverse, w, engine.Hard()) > engine.team_fit(same, w, engine.Hard())


def test_empty_pool():
    out = engine.form_teams([], team_size=4, weights=engine.Weights(), hard=engine.Hard())
    assert out.teams == []
    assert out.avg_score == 0.0
