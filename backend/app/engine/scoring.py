"""빠른 채점기. 학생을 정수 인덱스로 바꿔 두고 팀 점수를 캐시한다.

optimizer가 교환 한 번마다 바뀐 두 팀만 다시 채점할 때 쓴다. 결과는 constraints.soft_score /
team_violations와 같은 값을 내야 하며 tests/test_engine_port.py가 이를 확인한다.
"""
from __future__ import annotations

from collections import Counter

from .constraints import (HARD_PENALTY, LEAD_HIGH, MAXIMIN_LAMBDA, NEUTRAL, RANK_VALUE, ROLES, TIME_TARGET_HOURS,
                          TRAIT_KEYS, HardRules, SoftWeights, has_tag, spread_caps)


class Evaluator:
    def __init__(self, candidates, weights: SoftWeights, hard: HardRules, team_count: int):
        self.cands = list(candidates)
        self.n = len(self.cands)
        self.w = weights
        self.hard = hard
        self.idx = {c.student_id: i for i, c in enumerate(self.cands)}
        majors = sorted({c.major or "" for c in self.cands})
        mid = {m: k for k, m in enumerate(majors)}
        self.major = [mid[c.major or ""] for c in self.cands]
        self.unknown_major = mid.get("", -1)          # 학과 미입력 묶음 — 같은 학과 상한에서 제외
        self.n_majors = max(1, len([m for m in majors if m]))
        self.prefs = [tuple(c.roles or ()) for c in self.cands]
        # 역할 → 비트, 학생별 [(비트, 희망 점수)] (1지망 1.0 · 2지망 0.6 · 3지망 이하 0.3)
        universe = list(ROLES)
        for p in self.prefs:
            for r in p:
                if r not in universe:
                    universe.append(r)
        bit = {r: 1 << k for k, r in enumerate(universe)}
        self.pv = []
        for p in self.prefs:
            seen, row = 0, []
            for k, r in enumerate(p):
                if not seen & bit[r]:
                    seen |= bit[r]
                    row.append((bit[r], RANK_VALUE[min(k, len(RANK_VALUE) - 1)]))
            self.pv.append(tuple(row))
        self.first = [row[0][0] if row else 0 for row in self.pv]
        slot_ids: dict = {}
        self.mask = []
        for c in self.cands:
            m = 0
            for s in c.free_slots or ():
                m |= 1 << slot_ids.setdefault(s, len(slot_ids))
            self.mask.append(m)
        self.all_mask = (1 << len(slot_ids)) - 1
        tr = [c.traits or {} for c in self.cands]
        self.tv = {k: [int(t.get(k) or 0) for t in tr] for k in TRAIT_KEYS + ("lead",)}
        # 하드 규칙 컴파일
        self.team_count = team_count
        self.caps = spread_caps(self.cands, hard, team_count)
        self.min_rules = [(t, int(need), [has_tag(c, t) for c in self.cands])
                          for t, need in (hard.role_minimums or {}).items() if int(need) > 0]
        self.spread_rules = [(t, cap, [has_tag(c, t) for c in self.cands]) for t, cap in self.caps.items()]
        self.sep = [set() for _ in range(self.n)]
        for a, b in hard.separate_pairs or []:
            if a in self.idx and b in self.idx and a != b:
                self.sep[self.idx[a]].add(self.idx[b])
                self.sep[self.idx[b]].add(self.idx[a])
        self.fix = [set() for _ in range(self.n)]
        for a, b in hard.fixed_pairs or []:
            if a in self.idx and b in self.idx and a != b:
                self.fix[self.idx[a]].add(self.idx[b])
                self.fix[self.idx[b]].add(self.idx[a])
        self.wsum = weights.total()
        self._cache: dict = {}
        self.n_evals = 0

    # ── 하위 점수 ──
    def _role(self, team) -> float:
        # 1지망이 모두 다르면 바로 만점
        used = 0
        for i in team:
            f = self.first[i]
            if not f or used & f:
                break
            used |= f
        else:
            return 1.0
        # 앞으로 가는 DP: {사용한 역할 마스크: 최대 합}
        states = {0: 0.0}
        for i in team:
            nxt = dict(states)
            for mask, v in states.items():
                for b, val in self.pv[i]:
                    if not mask & b:
                        m2 = mask | b
                        if nxt.get(m2, -1.0) < v + val:
                            nxt[m2] = v + val
            states = nxt
        return max(states.values()) / len(team)

    def _trait(self, team) -> float:
        parts = []
        for k in TRAIT_KEYS:
            vals = [x for x in (self.tv[k][i] for i in team) if x]
            parts.append(1.0 - (max(vals) - min(vals)) / 4.0 if len(vals) >= 2 else NEUTRAL)
        leads = [x for x in (self.tv["lead"][i] for i in team) if x]
        parts.append((1.0 if max(leads) >= LEAD_HIGH else 0.0) if leads else NEUTRAL)
        return sum(parts) / len(parts)

    def common_mask(self, team) -> int:
        m = self.all_mask
        for i in team:
            m &= self.mask[i]
        return m

    def sub(self, team) -> dict:
        k = len(team)
        if k == 0:
            return {"major": 0.0, "role": 0.0, "time": 0.0, "trait": 0.0}
        major = 1.0 if k <= 1 else min(1.0, len({self.major[i] for i in team}) / min(k, self.n_majors))
        return {"major": major, "role": self._role(team),
                "time": min(1.0, bin(self.common_mask(team)).count("1") / TIME_TARGET_HOURS),
                "trait": self._trait(team)}

    def fit(self, sub: dict) -> float:
        if self.wsum <= 0:
            return 100.0
        w = self.w
        return 100.0 * (w.major * sub["major"] + w.role * sub["role"]
                        + w.time * sub["time"] + w.trait * sub["trait"]) / self.wsum

    def hard_count(self, team) -> float:
        """팀 위반 건수. 고정 쌍은 깨진 쪽마다 0.5 → 전체 합이 쌍당 1건."""
        h = 0.0
        cap = self.hard.same_major_max
        if cap:
            for cnt in Counter(self.major[i] for i in team if self.major[i] != self.unknown_major).values():
                if cnt > cap:
                    h += cnt - cap
        for _, need, flag in self.min_rules:
            have = sum(1 for i in team if flag[i])
            if have < need:
                h += need - have
        for _, c, flag in self.spread_rules:
            have = sum(1 for i in team if flag[i])
            if have > c:
                h += have - c
        s = set(team)
        for i in team:
            if self.sep[i]:
                h += 0.5 * len(self.sep[i] & s)
            if self.fix[i]:
                h += 0.5 * len(self.fix[i] - s)
        return h

    def team(self, team) -> tuple[float, float]:
        """(fit 0~100, 위반 건수). team은 인덱스 묶음."""
        key = tuple(sorted(team))
        hit = self._cache.get(key)
        if hit is None:
            self.n_evals += 1
            hit = (self.fit(self.sub(key)), self.hard_count(key)) if key else (0.0, 0.0)
            self._cache[key] = hit
        return hit

    # ── 목적함수 ──
    @staticmethod
    def j_value(scores, hards) -> float:
        return sum(scores) / len(scores) + MAXIMIN_LAMBDA * min(scores) - HARD_PENALTY * sum(hards)

    def objective_of(self, teams) -> tuple[float, list, list]:
        sc, hd = [], []
        for t in teams:
            f, h = self.team(t)
            sc.append(f)
            hd.append(h)
        return self.j_value(sc, hd), sc, hd
