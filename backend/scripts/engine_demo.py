"""TeamFit 엔진 시연: 합성 수강생으로 precheck → optimize (→ evaluate)를 돌리고 결과를 출력한다.

실행하는 위치(backend 폴더)의 app.engine을 쓴다. 그래서 같은 명령을 옛 엔진 폴더와 새 엔진 폴더에서
각각 실행하면 같은 데이터로 두 엔진을 비교할 수 있다. DB·서버는 필요 없다.

    cd <backend 폴더>
    python3 scripts/engine_demo.py                 # 45명, 시연 메모 포함
    python3 scripts/engine_demo.py --n 90          # 90명
    python3 scripts/engine_demo.py --json out.json # 응답 모양 JSON 저장 (새 엔진만)
"""
import argparse
import json
import math
import os
import random
import sys
import time
import uuid

sys.path.insert(0, os.getcwd())          # 실행 위치의 app 패키지를 쓴다

from app.matching import Candidate                       # noqa: E402
from app.engine.constraints import HardRules, SoftWeights  # noqa: E402
from app.engine.optimizer import optimize                # noqa: E402
from app.engine.precheck import precheck                 # noqa: E402

try:                                                     # 메모 해석기 (팀원 nl_rules.py)
    from app.engine.nl_rules import parse_requirements
except Exception:                                        # pragma: no cover
    parse_requirements = None

NOTE = "발표 경험이 있는 학생과 개발 경험이 있는 학생을 각 팀에 최소 1명씩 포함해 주세요. 4학년은 한 팀에 몰리지 않게 해주세요."
ROLES = ["기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표"]
MAJORS = ["수리데이터사이언스학과", "SW융합학과", "AI소프트웨어학과", "컴퓨터공학과", "전기전자공학과", "경영학과", "시각디자인학과"]
MAJOR_P = [0.30, 0.18, 0.15, 0.12, 0.10, 0.08, 0.07]
ROLE_BY_MAJOR = {   # 기획, 프론트, 백엔드, 데이터, 디자인, 발표
    "수리데이터사이언스학과": [.15, .10, .15, .40, .10, .10], "SW융합학과": [.15, .30, .30, .10, .05, .10],
    "AI소프트웨어학과": [.10, .20, .30, .30, .05, .05], "컴퓨터공학과": [.10, .30, .35, .15, .05, .05],
    "전기전자공학과": [.15, .20, .25, .20, .10, .10], "경영학과": [.40, .05, .00, .10, .10, .35],
    "시각디자인학과": [.10, .10, .00, .00, .70, .10]}
SURN = list("김이박최정강조윤장임한오서신권황안송류홍")
GIVEN = ["도윤", "서연", "민준", "지수", "예은", "준서", "소희", "지훈", "채원", "현우", "다은", "승민", "수빈", "지원",
         "하은", "시우", "유진", "태윤", "서진", "민서", "은우", "지민", "하준", "나연", "건우", "수아", "도현", "예린"]
PERIODS = {0: (0, 1, 2), 1: (4, 5, 6, 7, 8), 2: (9, 10, 11)}     # 오전 09-12, 오후 13-18, 저녁 18-21
PERIOD_P = (0.40, 0.45, 0.65)


def make_class(n, seed):
    rng = random.Random(seed)
    names, used = [], set()
    while len(names) < n:
        nm = rng.choice(SURN) + rng.choice(GIVEN)
        if nm not in used or len(used) >= len(SURN) * len(GIVEN):
            used.add(nm)
            names.append(nm)
    out = []
    for k in range(n):
        major = rng.choices(MAJORS, MAJOR_P)[0]
        w = ROLE_BY_MAJOR[major]
        r1 = rng.choices(range(6), w)[0]
        r2 = rng.choices([i for i in range(6) if i != r1], [w[i] + 0.05 for i in range(6) if i != r1])[0]
        roles = [ROLES[r1], ROLES[r2]]
        if rng.random() < 0.3:
            roles.append(rng.choice([r for r in ROLES if r not in roles]))
        mult = rng.uniform(0.7, 1.2)
        slots = set()
        for d in range(5):
            for p, blocks in PERIODS.items():
                if rng.random() < min(0.95, PERIOD_P[p] * mult):
                    slots |= {f"{d}-{b}" for b in blocks if rng.random() < 0.85}
        traits = {"pace": rng.randint(1, 5), "prep": rng.choices([1, 2, 3, 4, 5], [1, 2, 3, 3, 2])[0],
                  "lead": rng.randint(1, 5), "comm": rng.randint(1, 5)}
        out.append(Candidate(student_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"teamfit-demo-{seed}-{k}")),
                             name=names[k], major=major, year=rng.choices([2, 3, 4], [0.35, 0.40, 0.25])[0],
                             roles=roles, free_slots=slots, traits=traits))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=45)
    ap.add_argument("--seed", type=int, default=4, help="합성 데이터 시드")
    ap.add_argument("--size", type=int, default=4)
    ap.add_argument("--starts", type=int, default=3)
    ap.add_argument("--no-note", action="store_true", help="교수 메모 없이")
    ap.add_argument("--json", help="응답 모양 JSON을 이 파일로 저장 (새 엔진)")
    a = ap.parse_args()

    C = make_class(a.n, a.seed)
    w = SoftWeights(major=4, role=5, time=3, trait=3)
    role_min, spread = {}, []
    parsed = []
    if not a.no_note and parse_requirements:
        pr = parse_requirements(NOTE)
        hp = getattr(pr, "hard_patch", {}) or {}
        get = (lambda k: hp.get(k)) if isinstance(hp, dict) else (lambda k: getattr(hp, k, None))
        role_min = dict(get("role_minimums") or {})
        spread = list(get("spread_tags") or [])
        parsed = [getattr(r, "description", str(r)) for r in pr.rules]
    hard = HardRules(same_major_max=2, separate_pairs=[(C[6].student_id, C[18 % a.n].student_id)],
                     fixed_pairs=[], spread_tags=spread, role_minimums=role_min)

    print(f"== 엔진: {os.path.abspath('app/engine')}")
    print(f"== 합성 반 {a.n}명 (seed {a.seed}), 팀 크기 {a.size}, 가중치 4/5/3/3, 같은 학과 ≤2, 분리 1쌍")
    if parsed:
        print("== 메모 해석:", " / ".join(parsed))

    pc = precheck(C, a.size, hard)
    print(f"\n[precheck] 가능={pc.feasible}  팀 {pc.team_count}개  구성 {pc.composition}")
    for it in pc.items:
        mark = "OK " if it.ok else "NG "
        extra = f"  → {it.suggestion}" if getattr(it, "suggestion", None) else ""
        print(f"  {mark}{it.name}: {it.detail}{extra}")
    if not pc.feasible:
        print("  (실제 라우터는 여기서 422를 돌려준다. 비교를 위해 최적화는 계속 돌린다)")

    t0 = time.perf_counter()
    sol = optimize(C, a.size, w, hard, a.starts, 0)
    el = time.perf_counter() - t0
    o = sol.obj
    sizes = sorted((len(t) for t in sol.teams), reverse=True)
    print(f"\n[optimize] {el:.2f}초  J={o.j:.2f}  평균 {o.avg_fit:.1f}  최저 {o.min_fit:.1f}  하드 위반 {o.violations}  교환 {sol.swaps}")
    print(f"  팀 인원: {sizes}")
    tr = sol.trace
    print("  수렴:", "  ".join(f"{s} {av:.1f}/{lo:.1f}" for s, av, lo in zip(tr.stage, tr.avg, tr.low)))

    # 하드 규칙을 직접 다시 센다 (엔진 종류와 무관한 검산)
    k = len(sol.teams)
    fourth = sum(1 for c in C if c.year == 4)
    print("\n[검산]")
    print(f"  4학년 팀당 최대: {max(sum(1 for m in t if m.year == 4) for t in sol.teams)}명 (고르게면 ≤ {math.ceil(fourth / k)})")
    dev = {"프론트엔드", "백엔드", "데이터"}
    print(f"  '발표' 희망자 없는 팀: {sum(1 for t in sol.teams if not any('발표' in (m.roles or []) for m in t))}개")
    print(f"  개발 역할 희망자 없는 팀: {sum(1 for t in sol.teams if not any(set(m.roles or []) & dev for m in t))}개")
    print(f"  같은 학과 3명 이상 팀: {sum(1 for t in sol.teams if max([sum(1 for m in t if m.major == x) for x in {m.major for m in t}]) > 2)}개")

    details = getattr(sol, "details", None)
    print("\n[팀]")
    for i, t in enumerate(sol.teams):
        line = f"  {i + 1:>2}팀 {o.team_scores[i]:5.1f}  " + ", ".join(f"{m.name}({m.major[:4]},{m.year})" for m in t)
        print(line)
        if details:
            info = details["teams"][i]
            roles = ", ".join(f"{m.name}:{r['assigned_role']}{'' if r['preference_rank'] else '*'}"
                              for m, r in zip(t, info["members"]))
            print(f"        {info['summary']}  |  역할 {roles}")
            if info["warnings"] or info["violations"]:
                print(f"        경고 {info['warnings']}  위반 {info['violations']}")
    if details:
        print("\n[조건 충족]")
        for c in details["conditions"]:
            print(f"  {'OK ' if c['satisfied'] else 'NG '}{c['label']} (위반 {c['violations']})")
        print(f"\n[대안] " + "  ".join(f"J={x['objective_j']} 평균 {x['avg_fit']} 최저 {x['min_fit']}" for x in details["alternatives"]))
        try:
            from app.engine.explain import evaluate
            moved = [[m.student_id for m in t] for t in sol.teams]
            moved[0][0], moved[1][0] = moved[1][0], moved[0][0]
            ev = evaluate(C, moved, w, hard, team_size=a.size)
            print(f"[evaluate] 1팀·2팀 첫 학생 교환 → 평균 {ev['avg_fit']}  최저 {ev['min_fit']}  하드 위반 {ev['hard_violations']}  ({ev['elapsed_ms']}ms)")
        except ImportError:
            pass
        if a.json:
            json.dump(details, open(a.json, "w"), ensure_ascii=False, indent=2)
            print(f"  → {a.json} 저장")
    else:
        print("\n(이 엔진에는 팀 설명·조건 표·evaluate가 없습니다 — 옛 엔진)")


if __name__ == "__main__":
    main()
