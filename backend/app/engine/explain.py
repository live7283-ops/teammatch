"""결과 설명과 재채점. 라우터는 여기서 나온 dict를 응답 추가 필드에 그대로 붙이면 된다.

explain_solution(sol)        → match-v2 추가 필드 (teams[i]의 subscores/common_*/summary/warnings/violations,
                                members의 assigned_role/preference_rank, conditions, alternatives, seed)
evaluate(cands, teams, ...)  → POST /evaluate 응답 본체 (드래그 후 재채점, 저장 없음)
"""
from __future__ import annotations

import time

from .constraints import (HARD_PENALTY, LEAD_HIGH, MAXIMIN_LAMBDA, HardRules, SoftWeights, best_roles,
                          has_tag, parse_slot, slot_label)
from .scoring import Evaluator

SHORT_HOURS = 3        # 공통 시간이 주 3시간 미만이면 경고


class EvaluateError(ValueError):
    def __init__(self, code: str, message: str, items=None):
        super().__init__(message)
        self.code, self.message, self.items = code, message, items or []


def rules_of(hard: HardRules, names: dict | None = None) -> list[dict]:
    """하드 규칙 목록 → [{rule_id, label, kind}] (conditions 표의 행 순서)."""
    names = names or {}
    nm = lambda i: names.get(i, i)
    out = []
    if hard.same_major_max:
        out.append({"rule_id": "same_major_max", "kind": "same_major_max",
                    "label": f"같은 학과 팀당 최대 {hard.same_major_max}명"})
    for t, need in (hard.role_minimums or {}).items():
        if int(need) > 0:
            out.append({"rule_id": f"role_min:{t}", "kind": "role_min", "label": f"각 팀 '{t}' {need}명 이상"})
    for t in hard.spread_tags or []:
        out.append({"rule_id": f"spread:{t}", "kind": "spread", "label": f"'{t}' 팀마다 고르게"})
    for k, (a, b) in enumerate(hard.separate_pairs or []):
        out.append({"rule_id": f"separate:{k}", "kind": "separate", "label": f"분리: {nm(a)} · {nm(b)}"})
    for k, (a, b) in enumerate(hard.fixed_pairs or []):
        out.append({"rule_id": f"fixed:{k}", "kind": "fixed", "label": f"같은 팀: {nm(a)} · {nm(b)}"})
    return out


def _team_rule_hits(ev: Evaluator, team: list[int], hard: HardRules) -> dict:
    """팀 하나가 어긴 규칙 {rule_id: 건수}."""
    hits: dict = {}
    s = set(team)
    if hard.same_major_max:
        cnt: dict = {}
        for i in team:
            if ev.major[i] != ev.unknown_major:
                cnt[ev.major[i]] = cnt.get(ev.major[i], 0) + 1
        over = sum(max(0, v - hard.same_major_max) for v in cnt.values())
        if over:
            hits["same_major_max"] = over
    for t, need, flag in ev.min_rules:
        have = sum(1 for i in team if flag[i])
        if have < need:
            hits[f"role_min:{t}"] = need - have
    for t, cap, flag in ev.spread_rules:
        have = sum(1 for i in team if flag[i])
        if have > cap:
            hits[f"spread:{t}"] = have - cap
    for k, (a, b) in enumerate(hard.separate_pairs or []):
        if ev.idx.get(a) in s and ev.idx.get(b) in s:
            hits[f"separate:{k}"] = 1
    for k, (a, b) in enumerate(hard.fixed_pairs or []):
        ia, ib = ev.idx.get(a), ev.idx.get(b)
        if ia is not None and ib is not None and (ia in s) != (ib in s):
            hits[f"fixed:{k}"] = 1
    return hits


def explain_team(ev: Evaluator, team: list[int], target_size: int | None = None) -> dict:
    sub = ev.sub(team)
    fit, _ = ev.team(team)
    members = [ev.cands[i] for i in team]
    _, roles = best_roles([tuple(m.roles or ()) for m in members])
    free = [r for r in ("기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표") if r not in roles]
    out_members, matched = [], 0
    for m, r in zip(members, roles):
        rank = None
        if r is not None and r in (m.roles or []):
            rank = list(m.roles).index(r) + 1
            matched += 1
        elif r is None:
            r = free.pop(0) if free else ((m.roles or [None])[0])
        out_members.append({"student_id": m.student_id, "assigned_role": r, "preference_rank": rank})
    common = sorted(parse_slot(s) for s in set.intersection(*[set(m.free_slots or ()) for m in members])) \
        if members else []
    hours = len(common)
    warnings = []
    if hours < SHORT_HOURS:
        warnings.append(f"공통 시간 주 {hours}h — 회의 시간 잡기 어려움")
    leads = [int((m.traits or {}).get("lead") or 0) for m in members]
    if any(leads) and max(leads) < LEAD_HIGH:
        warnings.append("주도적 리드 성향 학생 없음")
    if matched < len(members):
        warnings.append(f"희망 외 역할 {len(members) - matched}명")
    paces = [int((m.traits or {}).get("pace") or 0) for m in members if (m.traits or {}).get("pace")]
    if len(paces) >= 2 and max(paces) - min(paces) >= 3:
        warnings.append("작업 페이스 차이 큼 (마감 집중형 ↔ 미리 완료형)")
    if target_size and abs(len(members) - target_size) >= 2:
        warnings.append(f"인원 {len(members)}명 (목표 {target_size}명)")
    n_major = len({m.major for m in members if m.major})
    return {
        "fit_score": round(fit, 1),
        "subscores": {k: round(v * 100, 1) for k, v in sub.items()},
        "common_hours": hours,
        "common_slots": [{"day": d, "block": b} for d, b in common],
        "common_labels": [slot_label(d, b) for d, b in common],
        "summary": f"전공 {n_major}개 · 희망 역할 {matched}/{len(members)}명 · 공통 시간 주 {hours}h",
        "warnings": warnings,
        "members": out_members,
    }


def _details(ev: Evaluator, teams_idx: list[list[int]], hard: HardRules, target_size: int | None = None) -> dict:
    names = {c.student_id: c.name for c in ev.cands}
    rules = rules_of(hard, names)
    per_team, scores, hards = [], [], []
    team_hits = []
    for t in teams_idx:
        info = explain_team(ev, t, target_size)
        hits = _team_rule_hits(ev, t, hard)
        info["violations"] = list(hits)
        team_hits.append(hits)
        per_team.append(info)
        f, h = ev.team(t)
        scores.append(f)
        hards.append(h)
    conditions = []
    for r in rules:
        idx = [ti for ti, h in enumerate(team_hits) if r["rule_id"] in h]
        cnt = sum(team_hits[ti][r["rule_id"]] for ti in idx)
        if r["kind"] == "fixed":
            cnt = 1 if idx else 0          # 쌍 하나는 위반 1건
        conditions.append({**r, "satisfied": not idx, "violations": cnt, "team_indexes": idx})
    viol = int(round(sum(hards)))
    avg = sum(scores) / len(scores) if scores else 0.0
    low = min(scores) if scores else 0.0
    lowest = scores.index(low) if scores else -1
    for ti, info in enumerate(per_team):
        info["is_lowest"] = ti == lowest
    return {"objective_j": round(avg + MAXIMIN_LAMBDA * low - HARD_PENALTY * viol, 2),
            "avg_fit": round(avg, 1), "min_fit": round(low, 1), "hard_violations": viol,
            "teams": per_team, "conditions": conditions}


def explain_solution(sol) -> dict:
    ev: Evaluator = sol.evaluator
    teams_idx = [[ev.idx[m.student_id] for m in t] for t in sol.teams]
    out = _details(ev, teams_idx, ev.hard)
    out["seed"] = sol.seed
    out["alternatives"] = [{
        "objective_j": round(a.obj.j, 2), "avg_fit": round(a.obj.avg_fit, 1),
        "min_fit": round(a.obj.min_fit, 1), "hard_violations": a.obj.violations,
        "teams": [[m.student_id for m in t] for t in a.teams]} for a in sol.alternatives]
    return out


def evaluate(candidates, teams, weights: SoftWeights, hard: HardRules, team_size: int | None = None) -> dict:
    """드래그 후 재채점. teams = [[student_id, ...], ...] 또는 [[Candidate, ...], ...]."""
    t0 = time.perf_counter()
    cands = list(candidates)
    ids = [[getattr(x, "student_id", x) for x in t] for t in teams]
    known = {c.student_id for c in cands}
    flat = [i for t in ids for i in t]
    unknown = sorted({i for i in flat if i not in known})
    if unknown:
        raise EvaluateError("UNKNOWN_STUDENT", "이 수업 후보가 아닌 학생이 있습니다.", unknown)
    dup = sorted({i for i in flat if flat.count(i) > 1})
    missing = sorted(known - set(flat))
    if dup or missing:
        raise EvaluateError("INVALID_TEAMS", "teams가 후보를 빠짐없이, 중복 없이 담아야 합니다.",
                            [{"duplicated": dup, "missing": missing}])
    if any(len(t) == 0 for t in ids):
        raise EvaluateError("INVALID_TEAMS", "빈 팀이 있습니다.", [])
    ev = Evaluator(cands, weights, hard, len(ids))
    out = _details(ev, [[ev.idx[i] for i in t] for t in ids], hard, team_size)
    out["team_count"] = len(ids)
    out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return out
