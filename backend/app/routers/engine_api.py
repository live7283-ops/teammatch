"""DB·인증 없는 무상태 엔진 API (프론트 '매칭 실행' 연동/데모용).

POST /api/engine/solve
  후보 학생 목록을 요청 본문으로 직접 받아 TeamFit 엔진(precheck → optimize)을 실행한다.
  - DB 에 읽거나 쓰지 않는다. 인증도 없다. (저장이 필요한 운영 흐름은 /api/classes/{id}/match-v2)
  - 남용 방지: 후보 수 상한(300), starts 상한(5).
  - 사전 점검에서 불가능이면 422 가 아니라 200 + feasible=false + items 로 돌려준다.
"""
from __future__ import annotations

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator, model_validator

from ..engine import nl_rules
from ..engine.constraints import HardRules, SoftWeights
from ..engine.optimizer import optimize
from ..engine.precheck import precheck
from ..matching import Candidate
from ..schemas import HardRulesIn, Weights

router = APIRouter(prefix="/api/engine", tags=["engine"])

MAX_CANDIDATES = 300
_SLOT_RE = re.compile(r"^[0-6]-(?:[0-9]|1[01])$")  # 요일 0~6, 블록 0~11


class EngineCandidateIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    major: str | None = Field(default=None, max_length=64)
    year: int | None = Field(default=None, ge=1, le=10)
    roles: list[str] = Field(default_factory=list, max_length=10)
    free_slots: list[str] = Field(default_factory=list, max_length=84)
    traits: dict[str, int] = Field(default_factory=dict)

    @field_validator("free_slots")
    @classmethod
    def _slots(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if not _SLOT_RE.match(s)]
        if bad:
            raise ValueError(f"free_slots 형식 오류(예: '0-5'): {bad[:3]}")
        return v

    @field_validator("traits")
    @classmethod
    def _traits(cls, v: dict[str, int]) -> dict[str, int]:
        for k, x in v.items():
            if not 0 <= x <= 5:
                raise ValueError(f"traits[{k}] 는 0~5 이어야 합니다.")
        return v


class EngineSolveRequest(BaseModel):
    team_size: int = Field(ge=2, le=8)
    weights: Weights
    hard: HardRulesIn = HardRulesIn()
    note: str | None = Field(default=None, max_length=2000)
    starts: int = Field(default=3, ge=1, le=5)
    seed: int | None = None
    candidates: list[EngineCandidateIn] = Field(min_length=2, max_length=MAX_CANDIDATES)

    @model_validator(mode="after")
    def _check(self):
        ids = [c.student_id for c in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("candidates 의 student_id 가 중복되었습니다.")
        if len(ids) < self.team_size:
            raise ValueError("후보 수가 팀 인원보다 적습니다.")
        return self


def _to_candidate(c: EngineCandidateIn) -> Candidate:
    return Candidate(
        student_id=c.student_id, name=c.name, major=c.major, year=c.year,
        roles=list(c.roles), free_slots=set(c.free_slots), traits=dict(c.traits),
    )


def _merge_hard(body: EngineSolveRequest, note_hard: HardRules | None) -> HardRules:
    """요청 하드 제약 + 메모 해석 하드 제약 병합 (matching_v2._build_hard 와 동일 규칙)."""
    hard = HardRules(
        same_major_max=body.hard.same_major_max,
        separate_pairs=[tuple(p) for p in body.hard.separate_pairs],
        fixed_pairs=[tuple(p) for p in body.hard.fixed_pairs],
        spread_tags=list(body.hard.spread_tags),
        role_minimums=dict(body.hard.role_minimums),
    )
    if note_hard:
        for tag, need in note_hard.role_minimums.items():
            hard.role_minimums[tag] = max(hard.role_minimums.get(tag, 0), need)
        for tag in note_hard.spread_tags:
            if tag not in hard.spread_tags:
                hard.spread_tags.append(tag)
    return hard


def _hard_dict(h: HardRules) -> dict:
    return {
        "same_major_max": h.same_major_max,
        "separate_pairs": [list(p) for p in h.separate_pairs],
        "fixed_pairs": [list(p) for p in h.fixed_pairs],
        "spread_tags": list(h.spread_tags),
        "role_minimums": dict(h.role_minimums),
    }


@router.post("/solve")
def solve(body: EngineSolveRequest) -> dict:
    candidates = [_to_candidate(c) for c in body.candidates]

    # 1) 메모 해석 → 소프트 가중치/하드 제약 보정
    parsed = nl_rules.parse_requirements(body.note or "")
    weights = nl_rules.apply_weight_patch(SoftWeights(**body.weights.model_dump()), parsed.weight_patch)
    hard = _merge_hard(body, parsed.hard_patch)
    parsed_rules = [
        {"source": r.source, "kind": r.kind, "description": r.description, "applied": r.applied}
        for r in parsed.rules
    ]

    # 2) 사전 점검
    pc = precheck(candidates, body.team_size, hard)
    check = {
        "feasible": pc.feasible,
        "team_count": pc.team_count,
        "composition": pc.composition,
        "sizes": list(pc.sizes),
        "items": [
            {"name": i.name, "ok": i.ok, "detail": i.detail,
             "suggestion": i.suggestion, "fix": i.fix}
            for i in pc.items
        ],
    }
    base = {"parsed_rules": parsed_rules, "precheck": check, "hard_used": _hard_dict(hard)}
    if not pc.feasible:
        return {"feasible": False, **base}

    # 3) 최적화
    sol = optimize(candidates, body.team_size, weights, hard, starts=body.starts, seed=body.seed)
    return {
        "feasible": True,
        **base,
        "weights_used": {"major": weights.major, "role": weights.role,
                         "time": weights.time, "trait": weights.trait},
        "swaps": sol.swaps,
        "trace": {"stage": list(sol.trace.stage), "avg": list(sol.trace.avg), "low": list(sol.trace.low)},
        "result": sol.details,
    }
