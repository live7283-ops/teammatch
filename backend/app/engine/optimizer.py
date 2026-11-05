"""TeamFit 엔진 v1.1 — 팀 편성 최적화.

목적함수 J = 평균 적합도 + λ·최저 팀 적합도 − 1000·하드 위반 (λ = 1)
순서: 희소 태그 우선 초기 배치 → 2-교환 국소 탐색 → 담금질(SA) → 마무리 국소 탐색, starts번 반복.
교환 한 번에 바뀐 두 팀만 다시 채점하고(Evaluator 캐시), 최저 점수는 하위 3개를 유지해 O(1)로 갱신한다.
공개 이름(Trace, Solution, optimize)과 인자는 라우터와의 계약이므로 바꾸지 않는다.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from .constraints import HARD_PENALTY, MAXIMIN_LAMBDA, HardRules, Objective, SoftWeights, has_tag
from .precheck import team_sizes
from .scoring import Evaluator

SA_ITERS_PER_STUDENT = 400
T_START, T_END = 1.5, 0.02
FOCUS_LOWEST = 0.3          # 담금질에서 최저 팀을 골라 교환할 확률 (maximin 가속)
TRACE_POINTS = 5            # 담금질 중간 기록 횟수
TIME_LIMIT_SEC = 20.0       # 전체 계산 상한. 넘으면 남은 담금질을 줄인다 (45명 ≈ 1초라 보통 닿지 않음)


@dataclass
class Trace:
    stage: list = field(default_factory=list)
    avg: list = field(default_factory=list)
    low: list = field(default_factory=list)

    def add(self, stage, scores):
        self.stage.append(stage)
        self.avg.append(round(sum(scores) / len(scores), 2))
        self.low.append(round(min(scores), 2))


@dataclass
class Solution:
    teams: list                       # [[Candidate]]
    obj: Objective
    swaps: int
    trace: Trace
    # v1.1 추가 (기본값이 있어 기존 호출부에 영향 없음)
    seed: int = 0
    elapsed_ms: int = 0
    alternatives: list = field(default_factory=list)   # [Solution] — 2·3등 시작
    details: dict = field(default_factory=dict)        # explain.explain_solution 결과
    evaluator: object = field(default=None, repr=False)


class _State:
    """팀 목록 + 팀별 (점수, 위반) + J. 교환·이동을 시험하고 적용한다."""

    def __init__(self, ev: Evaluator, teams):
        self.ev = ev
        self.teams = [list(t) for t in teams]
        self.where = [0] * ev.n
        for ti, t in enumerate(self.teams):
            for i in t:
                self.where[i] = ti
        self.sc, self.hd = [], []
        for t in self.teams:
            f, h = ev.team(t)
            self.sc.append(f)
            self.hd.append(h)
        self.sum_s, self.sum_h = sum(self.sc), sum(self.hd)
        self._low3()

    def _low3(self):
        self.low = sorted(range(len(self.sc)), key=self.sc.__getitem__)[:3]

    def j(self):
        k = len(self.sc)
        return self.sum_s / k + MAXIMIN_LAMBDA * self.sc[self.low[0]] - HARD_PENALTY * self.sum_h

    def _min_without(self, a, b):
        for t in self.low:
            if t != a and t != b:
                return self.sc[t]
        return math.inf

    def try_pair(self, a, ta, b, tb):
        """팀 a, b를 ta, tb로 바꿨을 때의 (J, 점수 a, 위반 a, 점수 b, 위반 b)."""
        fa, ha = self.ev.team(ta)
        fb, hb = self.ev.team(tb)
        k = len(self.sc)
        s = self.sum_s - self.sc[a] - self.sc[b] + fa + fb
        h = self.sum_h - self.hd[a] - self.hd[b] + ha + hb
        low = min(self._min_without(a, b), fa, fb)
        return s / k + MAXIMIN_LAMBDA * low - HARD_PENALTY * h, fa, ha, fb, hb

    def apply(self, a, ta, b, tb, fa, ha, fb, hb):
        self.teams[a], self.teams[b] = ta, tb
        for i in ta:
            self.where[i] = a
        for i in tb:
            self.where[i] = b
        self.sum_s += fa + fb - self.sc[a] - self.sc[b]
        self.sum_h += ha + hb - self.hd[a] - self.hd[b]
        self.sc[a], self.hd[a], self.sc[b], self.hd[b] = fa, ha, fb, hb
        self._low3()


def _units(ev: Evaluator):
    """고정 쌍을 묶음(unit)으로. union-find."""
    parent = list(range(ev.n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(ev.n):
        for j in ev.fix[i]:
            parent[find(i)] = find(j)
    out: dict = {}
    for i in range(ev.n):
        out.setdefault(find(i), []).append(i)
    return list(out.values())


def greedy_init(ev: Evaluator, sizes, rng: random.Random):
    """희소 태그 보유자 → 고정 묶음 → 나머지 순으로, 점수(−위반×1000)가 가장 많이 오르는 팀에 넣는다."""
    k = len(sizes)
    units = _units(ev)
    rng.shuffle(units)
    scarcity = {}
    for tag, need, flag in ev.min_rules:
        have = sum(flag)
        scarcity[tag] = have / max(1, need * k)
    flags = {tag: flag for tag, _, flag in ev.min_rules}

    def unit_key(u):
        s = [scarcity[t] for t in scarcity if any(flags[t][i] for i in u)]
        return (0, min(s), -len(u)) if s else (1, 0.0, -len(u))

    units.sort(key=unit_key)                       # 안정 정렬: 같은 순위끼리는 섞인 순서 유지
    teams = [[] for _ in range(k)]
    for u in units:
        best, best_gain = None, -math.inf
        for ti in range(k):
            if len(teams[ti]) + len(u) > sizes[ti]:
                continue
            f0, h0 = ev.team(teams[ti]) if teams[ti] else (0.0, 0.0)
            f1, h1 = ev.team(teams[ti] + u)
            gain = (f1 - f0) - HARD_PENALTY * (h1 - h0) - 0.01 * len(teams[ti]) + rng.random() * 1e-6
            if gain > best_gain:
                best, best_gain = ti, gain
        if best is None:                           # 묶음이 너무 커서 안 들어가면 낱개로
            for i in u:
                ti = max(range(k), key=lambda t: sizes[t] - len(teams[t]))
                teams[ti].append(i)
        else:
            teams[best].extend(u)
    return teams


def local_search(st: _State, max_passes: int = 50) -> int:
    """2-교환(+크기 차 1인 팀 사이 1명 이동) first-improvement. 받아들인 교환 수를 돌려준다."""
    accepted = 0
    k = len(st.teams)
    for _ in range(max_passes):
        improved = False
        for a in range(k):
            for b in range(a + 1, k):
                for x in list(st.teams[a]):
                    if x not in st.teams[a]:
                        continue
                    for y in list(st.teams[b]):
                        if y not in st.teams[b] or x not in st.teams[a]:
                            continue
                        j0 = st.j()
                        ta = [y if i == x else i for i in st.teams[a]]
                        tb = [x if i == y else i for i in st.teams[b]]
                        res = st.try_pair(a, ta, b, tb)
                        if res[0] > j0 + 1e-9:
                            st.apply(a, ta, b, tb, *res[1:])
                            accepted += 1
                            improved = True
                    # 이동: a가 b보다 1명 많으면 x를 b로 (팀 크기 구성 유지)
                    if x in st.teams[a] and len(st.teams[a]) == len(st.teams[b]) + 1:
                        ta = [i for i in st.teams[a] if i != x]
                        tb = st.teams[b] + [x]
                        res = st.try_pair(a, ta, b, tb)
                        if res[0] > st.j() + 1e-9:
                            st.apply(a, ta, b, tb, *res[1:])
                            accepted += 1
                            improved = True
        if not improved:
            break
    return accepted


def anneal(st: _State, rng: random.Random, iters: int, trace: Trace | None = None,
           deadline: float | None = None) -> int:
    k = len(st.teams)
    if k < 2 or iters <= 0:
        return 0
    alpha = (T_END / T_START) ** (1.0 / iters)
    T = T_START
    cur = st.j()
    best_j, best_teams = cur, [list(t) for t in st.teams]
    improved = 0
    every = max(1, iters // TRACE_POINTS)
    for it in range(1, iters + 1):
        if rng.random() < FOCUS_LOWEST:
            a = st.low[0]
            b = rng.randrange(k - 1)
            b += b >= a
        else:
            a, b = rng.sample(range(k), 2)
        A, B = st.teams[a], st.teams[b]
        if len(A) == len(B) + 1 and rng.random() < 0.15:  # 크기 구성은 유지하는 1명 이동
            x = rng.choice(A)
            ta, tb = [i for i in A if i != x], B + [x]
        else:
            x, y = rng.choice(A), rng.choice(B)
            ta = [y if i == x else i for i in A]
            tb = [x if i == y else i for i in B]
        res = st.try_pair(a, ta, b, tb)
        d = res[0] - cur
        if d >= 0 or rng.random() < math.exp(d / T):
            st.apply(a, ta, b, tb, *res[1:])
            cur = res[0]
            if d > 1e-9:
                improved += 1
            if cur > best_j + 1e-9:
                best_j, best_teams = cur, [list(t) for t in st.teams]
        T *= alpha
        if trace is not None and it % every == 0 and len(trace.stage) < 2 + TRACE_POINTS:
            trace.add(f"담금질 {it * 100 // iters}%", [st.ev.team(t)[0] for t in best_teams])
        if deadline is not None and it % 256 == 0 and time.perf_counter() > deadline:
            break
    # 가장 좋았던 상태로 되돌림
    st.__init__(st.ev, best_teams)
    return improved


def _run(ev: Evaluator, sizes, rng: random.Random, sa_iters: int, deadline):
    trace = Trace()
    st = _State(ev, greedy_init(ev, sizes, rng))
    trace.add("초기 배치", st.sc)
    swaps = local_search(st)
    trace.add("국소 탐색", st.sc)
    swaps += anneal(st, rng, sa_iters, trace, deadline)
    swaps += local_search(st)
    trace.add("최종", st.sc)
    return st, swaps, trace


def _to_solution(ev: Evaluator, st: _State, swaps: int, trace: Trace) -> Solution:
    order = sorted(range(len(st.teams)), key=lambda t: sorted(st.teams[t]))   # 학생 순서 기준으로 팀 번호 고정
    teams = [[ev.cands[i] for i in sorted(st.teams[t], key=lambda i: ev.cands[i].name)] for t in order]
    scores = [st.sc[t] for t in order]
    viol = int(round(st.sum_h))
    avg, low = sum(scores) / len(scores), min(scores)
    obj = Objective(avg + MAXIMIN_LAMBDA * low - HARD_PENALTY * viol, avg, low, viol, scores)
    return Solution(teams, obj, swaps, trace)


def optimize(candidates, team_size: int, weights: SoftWeights, hard: HardRules,
             starts: int = 3, seed: int | None = None, *, sa_iters_per_student: int = SA_ITERS_PER_STUDENT,
             time_limit: float | None = TIME_LIMIT_SEC) -> Solution:
    t0 = time.perf_counter()
    cands = list(candidates)
    if seed is None:
        seed = random.SystemRandom().randrange(1, 2 ** 31)
    sizes = team_sizes(len(cands), team_size)
    if not sizes:
        return Solution([], Objective(0.0, 0.0, 0.0, 0, []), 0, Trace(), seed=seed)
    ev = Evaluator(cands, weights, hard, len(sizes))
    runs = []
    starts = max(1, starts)
    for s in range(starts):
        rng = random.Random(seed * 1000003 + s)
        deadline = None
        if time_limit:   # 남은 시간을 남은 시작 횟수로 나눠 각 시작의 담금질 마감으로
            now = time.perf_counter()
            deadline = now + max(0.2, (t0 + time_limit - now) / (starts - s))
        st, swaps, trace = _run(ev, sizes, rng, sa_iters_per_student * len(cands), deadline)
        runs.append(_to_solution(ev, st, swaps, trace))
    runs.sort(key=lambda r: -r.obj.j)
    best = runs[0]
    best.alternatives = runs[1:]
    best.seed = seed
    best.evaluator = ev
    from .explain import explain_solution     # 순환 import 방지
    best.details = explain_solution(best)
    best.elapsed_ms = int((time.perf_counter() - t0) * 1000)
    best.details["elapsed_ms"] = best.elapsed_ms
    return best
