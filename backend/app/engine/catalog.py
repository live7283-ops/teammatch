"""조건 카탈로그: 이 수업에서 교수가 고를 수 있는 편성 조건의 틀과 빈칸에 넣을 수 있는 값.

편성 설정 화면이 조건 종류를 하드코딩하지 않고 이 목록으로 "조건 추가" 메뉴를 그리게 하려는 것이다.
조건은 설문에 실제로 있는 항목(희망 역할, 학년, 학과, 성향, 가능 시간)에서만 만든다.
설문에 없는 항목(유학생·성적 등)은 unsupported 로 따로 알려 준다.

    catalog(candidates, team_size) → {"team_count", "sizes", "conditions": [...], "always_on": [...], "unsupported": [...]}

conditions[i]
  kind     : HardRules 의 어느 조건인지 (role_min / same_major_max / spread / min_common_hours / separate / fixed)
  rule_id  : priority·conditions·precheck 에서 쓰는 id 모양 ({tag}, {index} 자리 표시)
  path     : 요청 본문(MatchV2Request.hard)에서 값을 넣는 자리
  text     : 화면 문장 틀 — {이름} 자리에 params 의 값을 끼운다
  params   : 빈칸 목록 [{name, type: tag|int|student, ...}]
  check    : "instant" = precheck 가 실행 전에 바로 판정 / "after_run" = 팀을 짜 봐야 알 수 있음
"""
from __future__ import annotations

import math
from collections import Counter

from .constraints import DEV_ROLES, LEAD_HIGH, ROLES, SoftWeights, has_tag
from .precheck import team_sizes

DEFAULT_MIN_COMMON_HOURS = 2
SOFT_LABELS = (("major", "전공을 고르게 섞기"), ("role", "희망 역할이 겹치지 않게"),
               ("time", "함께 모일 수 있는 시간이 많게"), ("trait", "협업 성향이 잘 맞게"))
UNSUPPORTED = (
    {"label": "유학생·외국인·편입생 조건", "reason": "설문과 학적 정보에 해당 항목이 없습니다."},
    {"label": "성적 분포", "reason": "설문에 성적 항목이 없습니다."},
)


def tag_options(candidates) -> list[dict]:
    """빈칸 {tag} 에 넣을 수 있는 값: 역할 6개, 개발, 리더, 반에 있는 학년·학과. holders = 해당 학생 수."""
    cands = list(candidates)
    out = [{"value": r, "label": f"'{r}' 희망자", "group": "role"} for r in ROLES]
    out.append({"value": "개발", "label": "개발 가능자 (" + "·".join(r for r in ROLES if r in DEV_ROLES) + " 희망)",
                "group": "role"})
    out.append({"value": "리더", "label": f"주도형 (주도성 {LEAD_HIGH}점 이상)", "group": "trait"})
    for y in sorted({int(c.year) for c in cands if c.year}):
        out.append({"value": f"{y}학년", "label": f"{y}학년", "group": "year"})
    for m, _ in Counter(c.major for c in cands if c.major).most_common():
        out.append({"value": m, "label": m, "group": "major"})
    for o in out:
        o["holders"] = sum(1 for c in cands if has_tag(c, o["value"]))
    return out


def catalog(candidates, team_size: int) -> dict:
    cands = list(candidates)
    sizes = team_sizes(len(cands), team_size)
    k = len(sizes)
    smallest, largest = (min(sizes), max(sizes)) if sizes else (0, 0)
    tags = tag_options(cands)
    # 각 팀 N명 이상: 팀마다 채울 수 있는 최대 N = min(보유자 ÷ 팀 수, 가장 작은 팀 인원). 0이면 고를 수 없음
    min_tags = [{**t, "max": min(t["holders"] // k, smallest) if k else 0} for t in tags]
    # 고르게 분산: 팀당 상한 = ceil(보유자 ÷ 팀 수)
    spread_tags = [{**t, "cap": math.ceil(t["holders"] / k) if k and t["holders"] else 0}
                   for t in tags if t["holders"]]
    worst_major = max(Counter(c.major for c in cands if c.major).values(), default=0)
    major_min = max(1, math.ceil(worst_major / k)) if k else 1
    free = [len(set(c.free_slots or ())) for c in cands]
    hours_max = min(free) if free else 0
    w = SoftWeights()
    return {
        "candidates": len(cands), "team_size": team_size, "team_count": k, "sizes": sizes,
        "conditions": [
            {"kind": "role_min", "rule_id": "role_min:{tag}", "path": "hard.role_minimums.{tag}",
             "text": "각 팀에 {tag} {count}명 이상", "check": "instant",
             "params": [{"name": "tag", "type": "tag", "options": min_tags},
                        {"name": "count", "type": "int", "min": 1, "default": 1}]},
            {"kind": "same_major_max", "rule_id": "same_major_max", "path": "hard.same_major_max",
             "text": "같은 학과는 팀당 {count}명 이하", "check": "instant",
             "params": [{"name": "count", "type": "int", "min": major_min, "max": max(major_min, largest),
                         "default": max(2, major_min)}]},
            {"kind": "spread", "rule_id": "spread:{tag}", "path": "hard.spread_tags[]",
             "text": "{tag} 학생을 팀마다 고르게", "check": "instant",
             "params": [{"name": "tag", "type": "tag", "options": spread_tags}]},
            {"kind": "min_common_hours", "rule_id": "min_common_hours", "path": "hard.min_common_hours",
             "text": "공통 가능 시간 주 {hours}시간 이상", "check": "after_run",
             "params": [{"name": "hours", "type": "int", "min": 1, "max": hours_max,
                         "default": min(DEFAULT_MIN_COMMON_HOURS, hours_max) or None}]},
            {"kind": "separate", "rule_id": "separate:{index}", "path": "hard.separate_pairs[]",
             "text": "{a} · {b} 다른 팀으로", "check": "instant",
             "params": [{"name": "a", "type": "student"}, {"name": "b", "type": "student"}]},
            {"kind": "fixed", "rule_id": "fixed:{index}", "path": "hard.fixed_pairs[]",
             "text": "{a} · {b} 같은 팀으로", "check": "instant",
             "params": [{"name": "a", "type": "student"}, {"name": "b", "type": "student"}]},
        ],
        # 조건을 지킨 다음 항상 함께 반영하는 점수 항목(가중치는 엔진 기본값으로 고정)
        "always_on": [{"key": key, "label": label, "weight": getattr(w, key)} for key, label in SOFT_LABELS],
        "unsupported": [dict(u) for u in UNSUPPORTED],
    }
