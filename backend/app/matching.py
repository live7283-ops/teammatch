"""Team-matching engine.

Pure Python, no DB imports, so it can be unit-tested in isolation.
The API layer converts ORM rows into `Candidate` objects, runs `form_teams`,
then persists the returned `MatchOutcome`.

Approach
--------
This is a greedy balancing heuristic (not an exact optimizer):

1. Decide team count from candidate pool and desired team size.
2. Seed each team, then assign remaining students one at a time to the
   team where they raise that team's fit the most, respecting hard
   constraints where possible.
3. Score each team on four axes, blended by the professor's weights:
     - major   : diversity of majors (higher = more mixed)
     - role    : coverage of distinct roles
     - time    : overlap of available schedule slots
     - trait   : balance of working-style traits (lower variance = better)

Scores are 0..100. `same_major` hard rule flips the major axis from
"reward diversity" to "reward sameness".
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from math import ceil


@dataclass
class Candidate:
    student_id: str
    name: str
    major: str | None
    year: int | None
    roles: list[str] = field(default_factory=list)
    # set of "day-block" strings that are available (state == 'y')
    free_slots: set[str] = field(default_factory=set)
    # working-style traits, each 1..5
    traits: dict[str, int] = field(default_factory=dict)


@dataclass
class Weights:
    major: int = 3
    role: int = 3
    time: int = 3
    trait: int = 3


@dataclass
class Hard:
    same_major: bool = False
    fix_pair: bool = False
    split_pair: bool = False
    even_transfer: bool = False


@dataclass
class TeamResult:
    members: list[Candidate]
    fit_score: float


@dataclass
class MatchOutcome:
    teams: list[TeamResult]
    avg_score: float


TRAIT_KEYS = ("pace", "prep", "lead", "comm")


def _team_count(n_candidates: int, team_size: int) -> int:
    if n_candidates <= 0 or team_size <= 0:
        return 0
    return max(1, ceil(n_candidates / team_size))


def _major_score(members: list[Candidate], same_major: bool) -> float:
    majors = [m.major for m in members if m.major]
    if not majors:
        return 50.0
    distinct = len(set(majors))
    diversity = (distinct - 1) / (len(majors) - 1) if len(majors) > 1 else 1.0
    # When same_major is enforced, sameness is the goal instead of diversity.
    value = (1 - diversity) if same_major else diversity
    return round(value * 100, 2)


def _role_score(members: list[Candidate]) -> float:
    roles = {r for m in members for r in m.roles}
    if not members:
        return 0.0
    # Reward covering as many distinct roles as there are members (capped).
    return round(min(len(roles) / len(members), 1.0) * 100, 2)


def _time_score(members: list[Candidate]) -> float:
    if len(members) < 2:
        return 100.0
    common = set.intersection(*[m.free_slots for m in members]) if all(
        m.free_slots for m in members
    ) else set()
    # Normalize against a reasonable target of 6 shared slots.
    return round(min(len(common) / 6.0, 1.0) * 100, 2)


def _trait_score(members: list[Candidate]) -> float:
    if len(members) < 2:
        return 100.0
    penalties = []
    for key in TRAIT_KEYS:
        vals = [m.traits[key] for m in members if key in m.traits and m.traits[key]]
        if len(vals) >= 2:
            # Lower spread => more compatible working styles. stdev of 0..~2.
            penalties.append(min(statistics.pstdev(vals) / 2.0, 1.0))
    if not penalties:
        return 60.0
    return round((1 - sum(penalties) / len(penalties)) * 100, 2)


def team_fit(members: list[Candidate], weights: Weights, hard: Hard) -> float:
    """Weighted blend of the four axis scores, 0..100."""
    if not members:
        return 0.0
    axes = {
        "major": _major_score(members, hard.same_major),
        "role": _role_score(members),
        "time": _time_score(members),
        "trait": _trait_score(members),
    }
    w = {"major": weights.major, "role": weights.role, "time": weights.time, "trait": weights.trait}
    total_w = sum(w.values()) or 1
    return round(sum(axes[k] * w[k] for k in axes) / total_w, 2)


def _violates_hard(team: list[Candidate], cand: Candidate, hard: Hard) -> bool:
    """Cheap hard-constraint check applied during greedy assignment."""
    if hard.even_transfer:
        # keep transfer-like (year>=3 as a proxy) spread out: block a 3rd senior.
        seniors = sum(1 for m in team if (m.year or 0) >= 3)
        if (cand.year or 0) >= 3 and seniors >= 2:
            return True
    return False


def form_teams(
    candidates: list[Candidate],
    team_size: int,
    weights: Weights,
    hard: Hard,
) -> MatchOutcome:
    """Greedy team formation. Returns balanced teams with fit scores."""
    pool = [c for c in candidates]
    n = len(pool)
    k = _team_count(n, team_size)
    if k == 0:
        return MatchOutcome(teams=[], avg_score=0.0)

    # Seed: sort by role rarity so we spread distinct roles across teams first.
    role_freq: dict[str, int] = {}
    for c in pool:
        for r in c.roles:
            role_freq[r] = role_freq.get(r, 0) + 1
    pool.sort(key=lambda c: (min((role_freq.get(r, 99) for r in c.roles), default=99), -(c.year or 0)))

    teams: list[list[Candidate]] = [[] for _ in range(k)]

    # Round-robin seed one member per team, then greedily fill the rest.
    idx = 0
    for c in pool[:k]:
        teams[idx].append(c)
        idx += 1

    for c in pool[k:]:
        best_team = None
        best_gain = float("-inf")
        for t in teams:
            if len(t) >= team_size and any(len(x) < team_size for x in teams):
                continue  # prefer under-filled teams
            if _violates_hard(t, c, hard) and any(
                not _violates_hard(x, c, hard) for x in teams
            ):
                continue
            gain = team_fit(t + [c], weights, hard) - team_fit(t, weights, hard)
            if gain > best_gain:
                best_gain = gain
                best_team = t
        (best_team if best_team is not None else min(teams, key=len)).append(c)

    results = [TeamResult(members=t, fit_score=team_fit(t, weights, hard)) for t in teams if t]
    avg = round(sum(r.fit_score for r in results) / len(results), 2) if results else 0.0
    return MatchOutcome(teams=results, avg_score=avg)


def assign_roles(team: list[Candidate]) -> dict[str, str]:
    """Best-effort: give each member one distinct role they listed."""
    taken: set[str] = set()
    out: dict[str, str] = {}
    for m in team:
        chosen = next((r for r in m.roles if r not in taken), (m.roles[0] if m.roles else None))
        if chosen:
            taken.add(chosen)
        out[m.student_id] = chosen or "미정"
    return out
