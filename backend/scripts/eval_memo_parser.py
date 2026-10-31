"""교수 메모 해석기 평가: 정답 세트(tests/data/memo_gold.json)로 규칙 기반과 LLM을 비교한다.

    cd backend
    python scripts/eval_memo_parser.py              # 규칙 기반 (키 없이)
    python scripts/eval_memo_parser.py --mode llm   # LLM (TEAMFIT_LLM_PROVIDER 등 설정 필요)
    python scripts/eval_memo_parser.py --mode both

비교 방법: 적용되는 조건을 (종류, 태그, 인원) / (weight, 축, 부호)로 바꿔 정답과 집합으로 비교.
'지원 안 됨'은 조건을 만들지 않고 교수에게 알렸는지(적용 안 됨 항목이 있는지)로 따로 본다.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

from app.engine import nl_rules                 # noqa: E402
from app.engine.llm_rules import default_llm    # noqa: E402


def norm(rules):
    out, unsupported = set(), 0
    for r in rules:
        if not r.applied:
            unsupported += 1
            continue
        if r.role_min_tag:
            out.add(("role_min", r.role_min_tag, int(r.role_min_count)))
        if r.spread_tag:
            out.add(("spread", r.spread_tag))
        if r.weight_axis:
            out.add(("weight", r.weight_axis, 1 if r.weight_delta > 0 else -1))
    return out, unsupported


def gold_set(item):
    s = set()
    for r in item["rules"]:
        if r[0] == "weight":
            s.add(("weight", r[1], 1 if r[2] > 0 else -1))
        else:
            s.add(tuple(r))
    return s


def evaluate(name, parse, gold):
    tp = fp = fn = exact = rules_exact = flagged = need_flag = wrong_made = 0
    fails = []
    t0 = time.perf_counter()
    for item in gold:
        pred, unsup = norm(parse(item["memo"]))
        g = gold_set(item)
        tp += len(pred & g)
        fp += len(pred - g)
        fn += len(g - pred)
        rules_ok = pred == g
        flag_ok = (unsup > 0) == (item["unsupported"] > 0)
        rules_exact += rules_ok
        exact += rules_ok and flag_ok
        if item["unsupported"]:
            need_flag += 1
            flagged += unsup > 0
        if pred - g:
            wrong_made += 1
        if not (rules_ok and flag_ok):
            fails.append((item["memo"], sorted(g), sorted(pred), unsup))
    el = time.perf_counter() - t0
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    n = len(gold)
    print(f"\n== {name}  ({el:.1f}초)")
    print(f"  메모 완전 일치        {exact}/{n}   (조건만 보면 {rules_exact}/{n})")
    print(f"  조건 정밀도 / 재현율   {p:.2f} / {r:.2f}   (F1 {f1:.2f})")
    print(f"  틀린 조건을 만든 메모  {wrong_made}개")
    print(f"  지원 안 되는 요구 알림 {flagged}/{need_flag}")
    for memo, g, pred, unsup in fails:
        print(f"  ✗ {memo}\n      정답 {g}\n      결과 {pred}{'  + 적용 안 됨 ' + str(unsup) if unsup else ''}")
    return {"exact": exact, "precision": p, "recall": r, "f1": f1, "wrong": wrong_made, "flagged": flagged}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["rule", "llm", "both"], default="rule")
    ap.add_argument("--gold", default="tests/data/memo_gold.json")
    a = ap.parse_args()
    gold = json.load(open(a.gold, encoding="utf-8"))
    print(f"정답 세트 {len(gold)}개 메모")
    if a.mode in ("rule", "both"):
        evaluate("규칙 기반 (nl_rules)", nl_rules._rule_based, gold)
    if a.mode in ("llm", "both"):
        llm = default_llm()
        if llm is None:
            print("\nLLM 설정이 없습니다: TEAMFIT_LLM_PROVIDER, TEAMFIT_LLM_MODEL, API 키를 .env에 넣으세요.")
            return
        evaluate(f"LLM ({os.environ.get('TEAMFIT_LLM_PROVIDER') or '.env'})", llm, gold)


if __name__ == "__main__":
    main()
