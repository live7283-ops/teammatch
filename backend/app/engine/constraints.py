"""TeamFit 엔진 v1.1 — 점수 축과 하드 규칙.

백엔드 Candidate(student_id, name, major, year, roles, free_slots, traits)를 그대로 받는다.
- roles      : 희망 역할 목록, 앞이 1지망 (1.0 / 0.6 / 0.3)
- free_slots : {"day-block"} — day 0~6(월~일), block 0~11(09~21시, 1시간)
- traits     : 1~5, 0 = 무응답 (index.html 라벨)
               pace 작업 페이스(1 마감 직전 집중 ~ 5 미리 완성), prep 의사결정(1 신속 ~ 5 충분한 논의),
               lead 주도성(1 서포트 ~ 5 주도적 리더십), comm 소통 빈도(1 정기 회의 ~ 5 수시 공유)
공개 이름(SoftWeights, HardRules, soft_score, team_violations, total_violations,
Objective, objective, _has_tag)은 라우터·테스트와의 계약이므로 바꾸지 않는다.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

ROLES = ("기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표")
DEV_ROLES = frozenset({"프론트엔드", "백엔드", "데이터"})
RANK_VALUE = (1.0, 0.6, 0.3)          # 1지망, 2지망, 3지망 이하
TIME_TARGET_HOURS = 6                 # 주 6시간 공통 시간이면 만점
LEAD_HIGH = 4                         # traits.lead >= 4 → 화면 라벨 "주도적 리드" (index.html 확인)
TRAIT_KEYS = ("pace", "prep", "comm")  # 비슷할수록 좋은 성향
NEUTRAL = 0.75                        # 성향 무응답일 때 중립값
HARD_PENALTY = 1000.0
MAXIMIN_LAMBDA = 1.0
DAY_NAMES = ("월", "화", "수", "목", "금", "토", "일")
_YEAR_RE = re.compile(r"^\s*(\d)\s*학년\s*$")


@dataclass
class SoftWeights:
    major: float = 4
    role: float = 5
    time: float = 3
    trait: float = 3

    def total(self) -> float:
        return float(self.major + self.role + self.time + self.trait)


@dataclass
class HardRules:
    same_major_max: int | None = None
    separate_pairs: list = field(default_factory=list)   # [(student_id, student_id)]
    fixed_pairs: list = field(default_factory=list)
    spread_tags: list = field(default_factory=list)      # 팀마다 고르게: 팀당 최대 ceil(보유자/팀 수)
    role_minimums: dict = field(default_factory=dict)    # {태그: 팀당 최소 인원}


# ── 태그 ────────────────────────────────────────────────────────────
def tag_kind(tag: str, majors: set | None = None) -> str | None:
    """태그 어휘: role | dev | year | major | leader | trait. 모르는 태그는 None."""
    t = tag.strip()
    if t in ROLES:
        return "role"
    if t == "개발":
        return "dev"
    if _YEAR_RE.match(t):
        return "year"
    if t == "리더":
        return "leader"
    if t in ("pace", "prep", "lead", "comm"):
        return "trait"
    if majors is not None and t in majors:
        return "major"
    return None


def has_tag(c, tag: str) -> bool:
    t = tag.strip()
    roles = list(c.roles or [])
    if t in roles:
        return True
    if t == "개발":
        return any(r in DEV_ROLES for r in roles)
    m = _YEAR_RE.match(t)
    if m:
        return int(c.year or 0) == int(m.group(1))
    if t == "리더":
        return int((c.traits or {}).get("lead") or 0) >= LEAD_HIGH
    if t in ("pace", "prep", "lead", "comm"):
        return int((c.traits or {}).get(t) or 0) >= 4
    return c.major == t


_has_tag = has_tag   # 이전 이름 호환


def spread_caps(candidates, hard: HardRules, team_count: int) -> dict:
    """spread_tags 태그별 팀당 상한 = ceil(보유자 수 / 팀 수)."""
    caps = {}
    for t in hard.spread_tags or []:
        n = sum(1 for c in candidates if has_tag(c, t))
        caps[t] = max(1, math.ceil(n / max(1, team_count))) if n else 0
    return caps


# ── 점수 축 (0~1) ──────────────────────────────────────────────────
def major_score(members, n_majors: int | None = None) -> float:
    n = len(members)
    if n <= 1:
        return 1.0
    distinct = len({m.major or "" for m in members})   # 학과 미입력(None)은 한 묶음으로
    cap = min(n, n_majors) if n_majors else n
    return min(1.0, distinct / cap)


def _rank_value(k: int) -> float:
    return RANK_VALUE[min(k, len(RANK_VALUE) - 1)]


def best_roles(pref_lists) -> tuple[float, list]:
    """팀원마다 서로 다른 역할 하나씩: 희망 점수 합 최대 배정 (비트마스크 DP).
    반환: (합, [역할 이름 또는 None]) — None은 남는 역할이 없거나 희망 역할을 못 받은 사람."""
    universe = list(ROLES)
    for p in pref_lists:
        for r in p:
            if r not in universe:
                universe.append(r)
    pos = {r: i for i, r in enumerate(universe)}
    vals = []
    for p in pref_lists:
        v = {}
        for k, r in enumerate(p):
            v.setdefault(pos[r], _rank_value(k))
        vals.append(v)
    n = len(vals)
    memo: dict = {}

    def go(i, mask):
        if i == n:
            return 0.0
        key = (i, mask)
        hit = memo.get(key)
        if hit is not None:
            return hit[0]
        best_v, best_r = go(i + 1, mask), -1
        for r, val in vals[i].items():
            if not mask >> r & 1:
                cand = val + go(i + 1, mask | 1 << r)
                if cand > best_v + 1e-12:
                    best_v, best_r = cand, r
        memo[key] = (best_v, best_r)
        return best_v

    total = go(0, 0)
    out, mask = [], 0
    for i in range(n):
        r = memo[(i, mask)][1]
        out.append(universe[r] if r >= 0 else None)
        if r >= 0:
            mask |= 1 << r
    return total, out


def role_score(members) -> float:
    if not members:
        return 0.0
    total, _ = best_roles([tuple(m.roles or ()) for m in members])
    return total / len(members)


def common_slots(members) -> set:
    it = iter(members)
    first = next(it, None)
    if first is None:
        return set()
    s = set(first.free_slots or ())
    for m in it:
        s &= set(m.free_slots or ())
    return s


def time_score(members) -> float:
    return min(1.0, len(common_slots(members)) / TIME_TARGET_HOURS)


def _similarity(vals) -> float:
    vals = [v for v in vals if v]
    if len(vals) < 2:
        return NEUTRAL
    return 1.0 - (max(vals) - min(vals)) / 4.0


def trait_score(members) -> float:
    parts = [_similarity([int((m.traits or {}).get(k) or 0) for m in members]) for k in TRAIT_KEYS]
    leads = [int((m.traits or {}).get("lead") or 0) for m in members]
    leads = [v for v in leads if v]
    parts.append((1.0 if max(leads) >= LEAD_HIGH else 0.0) if leads else NEUTRAL)
    return sum(parts) / len(parts)


def subscores(members, n_majors: int | None = None) -> dict:
    return {"major": major_score(members, n_majors), "role": role_score(members),
            "time": time_score(members), "trait": trait_score(members)}


def combine(sub: dict, w: SoftWeights) -> float:
    tot = w.total()
    if tot <= 0:
        return 100.0
    return 100.0 * (w.major * sub["major"] + w.role * sub["role"]
                    + w.time * sub["time"] + w.trait * sub["trait"]) / tot


def soft_score(members, w: SoftWeights, n_majors: int | None = None) -> float:
    """팀 적합도 0~100."""
    return combine(subscores(members, n_majors), w)


# ── 하드 규칙 ──────────────────────────────────────────────────────
def team_violations(members, hard: HardRules, caps: dict | None = None) -> int:
    """팀 하나의 위반 건수. 고정 쌍은 짝이 다른 팀에 있으면 이 팀에서 1건(전체 집계는 쌍당 1건)."""
    ids = {m.student_id for m in members}
    v = 0
    if hard.same_major_max:
        for cnt in Counter(m.major for m in members if m.major).values():   # 미입력은 세지 않음
            v += max(0, cnt - hard.same_major_max)
    for tag, need in (hard.role_minimums or {}).items():
        have = sum(1 for m in members if has_tag(m, tag))
        v += max(0, int(need) - have)
    for tag, cap in (caps or {}).items():
        have = sum(1 for m in members if has_tag(m, tag))
        v += max(0, have - cap)
    for a, b in hard.separate_pairs or []:
        if a in ids and b in ids:
            v += 1
    for a, b in hard.fixed_pairs or []:
        if (a in ids) != (b in ids):
            v += 1
    return v


def total_violations(teams, hard: HardRules) -> int:
    members = [m for t in teams for m in t]
    caps = spread_caps(members, hard, len(teams))
    v = 0
    for t in teams:
        v += team_violations(t, hard, caps)
    # 고정 쌍은 양쪽 팀에서 한 번씩 세었으므로 쌍당 1건으로 보정
    where = {m.student_id: i for i, t in enumerate(teams) for m in t}
    broken = sum(1 for a, b in hard.fixed_pairs or []
                 if a in where and b in where and where[a] != where[b])
    return v - broken


@dataclass
class Objective:
    j: float
    avg_fit: float
    min_fit: float
    violations: int
    team_scores: list


def objective(teams, w: SoftWeights, hard: HardRules, n_majors: int | None = None) -> Objective:
    members = [m for t in teams for m in t]
    if n_majors is None:
        n_majors = len({m.major for m in members if m.major}) or None
    scores = [soft_score(t, w, n_majors) for t in teams]
    viol = total_violations(teams, hard)
    if not scores:
        return Objective(0.0, 0.0, 0.0, viol, [])
    avg, low = sum(scores) / len(scores), min(scores)
    return Objective(avg + MAXIMIN_LAMBDA * low - HARD_PENALTY * viol, avg, low, viol, scores)


def slot_label(day: int, block: int) -> str:
    d = DAY_NAMES[day] if 0 <= day < len(DAY_NAMES) else str(day)
    return f"{d} {9 + block:02d}–{10 + block:02d}시"


def parse_slot(s: str) -> tuple[int, int]:
    d, b = str(s).split("-")
    return int(d), int(b)
