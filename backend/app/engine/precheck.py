"""매칭 전 사전 점검: 개수만 비교해 하드 규칙을 지킬 수 없는 요청을 먼저 걸러낸다.

통과는 필요조건일 뿐이다. 규칙끼리 얽혀 최적화 뒤에도 위반이 남으면 결과의 conditions에 표시된다.
각 실패 항목에는 사람이 읽는 suggestion과, 화면이 버튼으로 바로 적용할 fix({op, path, value})를 둔다.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .constraints import HardRules, has_tag, priority_order, tag_kind


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str
    suggestion: str | None = None
    fix: dict | None = None            # v1.1 추가: {"op": "set"|"remove", "path": "...", "value": ...}
    rule_id: str | None = None         # 어느 조건 줄의 점검인지 (conditions·priority 와 같은 id). 조건과 무관하면 None


@dataclass
class PrecheckResult:
    feasible: bool
    team_count: int
    composition: str
    items: list
    sizes: list = field(default_factory=list)   # v1.1 추가: 팀별 인원 [5, 5, 4, ...]


def team_sizes(n: int, team_size: int) -> list[int]:
    """팀 수 = floor(n / team_size), 남는 학생은 앞 팀부터 1명씩 더한다(목표보다 큰 팀).
    남는 학생이 팀 수보다 많을 때만 팀을 하나 늘려 고르게 나눈다(46명·4명 → 5,5,4×9 / 7명·4명 → 4,3)."""
    if n <= 0:
        return []
    team_size = max(1, team_size)
    k = n // team_size
    if k == 0:
        return [n]
    r = n - k * team_size
    if r > k:
        k += 1
    base, extra = divmod(n, k)
    return [base + 1] * extra + [base] * (k - extra)


def composition(sizes: list[int]) -> str:
    cnt = Counter(sizes)
    return " + ".join(f"{s}명×{cnt[s]}" for s in sorted(cnt, reverse=True))


def _groups(ids, pairs):
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    out: dict = {}
    for i in ids:
        out.setdefault(find(i), []).append(i)
    return list(out.values())


def precheck(candidates, team_size: int, hard: HardRules) -> PrecheckResult:
    cands = list(candidates)
    n = len(cands)
    sizes = team_sizes(n, team_size)
    k = len(sizes)
    items: list[CheckItem] = []
    ids = {c.student_id for c in cands}
    name = {c.student_id: c.name for c in cands}
    majors = {c.major for c in cands if c.major}

    # 1) 후보 수
    ok = n >= max(2, team_size)
    items.append(CheckItem(
        "후보 수", ok, f"후보 {n}명 / 팀 크기 {team_size}명 → {composition(sizes) or '팀 없음'}",
        None if ok else ("설문을 낸 학생이 더 필요합니다." if n < 2 else f"팀 크기를 {n}명 이하로 줄이세요."),
        None if ok or n < 2 else {"op": "set", "path": "team_size", "value": max(2, n)}))

    # 2) 태그 어휘
    for path, tags in (("hard.role_minimums", list((hard.role_minimums or {}).keys())),
                       ("hard.spread_tags", list(hard.spread_tags or []))):
        for t in tags:
            if tag_kind(t, majors) is None:
                items.append(CheckItem(
                    f"태그 '{t}'", False, "태그 어휘(역할 이름, 개발, N학년, 학과 이름, 리더)에 없습니다.",
                    f"'{t}' 조건을 빼거나 어휘에 있는 태그로 바꾸세요.",
                    {"op": "remove", "path": path, "value": t}))

    if k == 0:
        return PrecheckResult(False, 0, "", items, sizes)

    # 3) 같은 학과 상한
    if hard.same_major_max:
        cap = int(hard.same_major_max)
        cnt = Counter(c.major for c in cands if c.major)
        worst = max(cnt.values()) if cnt else 0
        over = [(m, v) for m, v in cnt.items() if v > cap * k]
        detail = (f"가장 많은 학과 {worst}명 / 허용 {cap}명×{k}팀 = {cap * k}명" if not over else
                  ", ".join(f"{m} {v}명" for m, v in over) + f" > 허용 {cap * k}명")
        need = math.ceil(worst / k)
        items.append(CheckItem(
            f"같은 학과 팀당 최대 {cap}명", not over, detail,
            None if not over else f"같은 학과 상한을 {need}명으로 올리세요.",
            None if not over else {"op": "set", "path": "hard.same_major_max", "value": need},
            rule_id="same_major_max"))

    # 4) 태그 최소 인원
    for t, need in (hard.role_minimums or {}).items():
        need = int(need)
        if need <= 0 or tag_kind(t, majors) is None:
            continue
        have = sum(1 for c in cands if has_tag(c, t))
        ok = have >= need * k and need <= min(sizes)
        fix_to = min(have // k, min(sizes))
        items.append(CheckItem(
            f"각 팀 '{t}' {need}명 이상", ok, f"보유 {have}명 / 필요 {need * k}명",
            None if ok else (f"'{t}' 최소 인원을 {fix_to}명으로 낮추세요." if fix_to < need else
                             "팀 크기를 늘리세요."),
            None if ok else {"op": "set", "path": f"hard.role_minimums.{t}", "value": fix_to},
            rule_id=f"role_min:{t}"))

    # 5) 고르게 분산 (개수상 항상 가능 — 상한만 알려 준다)
    for t in hard.spread_tags or []:
        if tag_kind(t, majors) is None:
            continue
        have = sum(1 for c in cands if has_tag(c, t))
        cap = math.ceil(have / k) if have else 0
        items.append(CheckItem(f"'{t}' 팀마다 고르게", True, f"보유 {have}명 → 팀당 최대 {cap}명",
                               rule_id=f"spread:{t}"))

    # 5-1) 공통 가능 시간 최소 N시간 — 학생 한 명의 가능 시간이 N보다 적으면 그 학생의 팀은 지킬 수 없다.
    #      통과해도 팀별로 실제로 겹치는지는 편성 뒤 conditions 에서 확인한다(개수만으로는 알 수 없음).
    if hard.min_common_hours:
        need = int(hard.min_common_hours)
        free = [len(set(c.free_slots or ())) for c in cands]
        short = sum(1 for f in free if f < need)
        lowest = min(free) if free else 0
        items.append(CheckItem(
            f"공통 가능 시간 주 {need}시간 이상", not short,
            f"가능 시간이 {need}시간 미만인 학생 {short}명 (가장 적은 학생 {lowest}시간)" if short else
            f"모든 학생의 가능 시간이 {need}시간 이상 — 팀별 충족 여부는 실행 후 확인",
            None if not short else (f"기준을 {lowest}시간으로 낮추세요." if lowest >= 1 else
                                    "가능 시간을 입력하지 않은 학생이 있습니다. 이 조건을 빼세요."),
            None if not short else ({"op": "set", "path": "hard.min_common_hours", "value": lowest} if lowest >= 1
                                    else {"op": "remove", "path": "hard.min_common_hours", "value": need}),
            rule_id="min_common_hours"))

    # 6) 학생 쌍
    for kind, path, pairs in (("separate", "hard.separate_pairs", hard.separate_pairs or []),
                              ("fixed", "hard.fixed_pairs", hard.fixed_pairs or [])):
        for idx, (a, b) in enumerate(pairs):
            bad = [x for x in (a, b) if x not in ids]
            if bad or a == b:
                items.append(CheckItem(
                    "학생 쌍", False,
                    "이 수업 후보가 아닌 학생: " + ", ".join(bad) if bad else "같은 학생끼리 쌍입니다.",
                    "이 쌍을 빼세요.", {"op": "remove", "path": path, "value": [a, b]},
                    rule_id=f"{kind}:{idx}"))
    if hard.separate_pairs and k < 2:
        items.append(CheckItem("분리 쌍", False, "팀이 1개라 분리할 수 없습니다.", "분리 쌍을 빼세요.",
                               {"op": "set", "path": "hard.separate_pairs", "value": []}))
    if hard.fixed_pairs:
        groups = [g for g in _groups(sorted(ids), hard.fixed_pairs) if len(g) > 1]
        biggest = max((len(g) for g in groups), default=0)
        ok = biggest <= max(sizes)
        items.append(CheckItem(
            "같은 팀 고정", ok, f"가장 큰 고정 묶음 {biggest}명 / 가장 큰 팀 {max(sizes)}명",
            None if ok else "고정 쌍을 줄이세요.",
            None if ok else {"op": "set", "path": "hard.fixed_pairs", "value": []}))
        gid = {i: gi for gi, g in enumerate(groups) for i in g}
        for idx, (a, b) in enumerate(hard.separate_pairs or []):
            if a in gid and gid.get(a) == gid.get(b):
                items.append(CheckItem(
                    "분리·고정 충돌", False, f"{name.get(a, a)}·{name.get(b, b)}이(가) 고정 묶음 안에서 분리 대상입니다.",
                    "분리 쌍을 빼세요.", {"op": "remove", "path": "hard.separate_pairs", "value": [a, b]},
                    rule_id=f"separate:{idx}"))

    # 7) 조건 우선순위 (정보용 — 항상 통과). 걸려 있지 않은 조건 id 는 무시하고 그 사실을 알려 준다.
    if hard.priority:
        order = priority_order(hard)
        ignored = [r for r in dict.fromkeys(hard.priority) if r not in order]
        detail = " > ".join(order) if order else "적용할 순위가 없습니다"
        if ignored:
            detail += " (걸려 있지 않아 무시: " + ", ".join(map(str, ignored)) + ")"
        items.append(CheckItem("조건 우선순위", True, detail))

    feasible = all(i.ok for i in items)
    return PrecheckResult(feasible, k, composition(sizes), items, sizes)
