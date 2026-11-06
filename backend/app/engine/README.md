# app/engine — TeamFit 매칭 엔진 v1.1

담당: AI 파트. 라우터(`routers/matching_v2.py`)·스키마·DB는 백엔드 2 담당.
명세: Claude Docs "TeamFit AI 매칭 API 명세 v1.1".

## 파일

| 파일 | 내용 |
| --- | --- |
| `constraints.py` | 점수 축 4개, 태그 어휘(역할·`개발`·`N학년`·학과·`리더`), 하드 규칙 위반 계산, `objective` |
| `scoring.py` | `Evaluator` — 학생을 인덱스로 바꾸고 팀 점수를 캐시하는 빠른 채점기 |
| `precheck.py` | 팀 수 규칙 `team_sizes`, 개수 기반 사전 점검 (`items[].fix` 포함) |
| `optimizer.py` | 희소 태그 우선 초기 배치 → 2-교환 국소 탐색 → 담금질 → 마무리, `starts`번 반복 |
| `explain.py` | 팀 카드 값(하위 점수·공통 시간·요약·경고·위반·역할 배정), 조건 충족 표, `evaluate` |
| `nl_rules.py` | 교수 메모 해석 — 규칙 기반 (팀원 작성), LLM 설정이 있으면 `llm_rules`를 먼저 사용 |
| `llm_rules.py` | 교수 메모 LLM 해석기: 프롬프트, 응답 검증, 캐시, anthropic/openai 호출 |

## 라우터와의 계약 (바뀌지 않음)

```python
precheck(candidates, team_size, hard) -> PrecheckResult(feasible, team_count, composition, items)
optimize(candidates, team_size, weights, hard, starts=3, seed=None) -> Solution(teams, obj, swaps, trace)
objective(teams, w, hard) -> Objective(j, avg_fit, min_fit, violations, team_scores)
```

v1.1에서 늘어난 것 (모두 기본값이 있어 기존 호출부는 그대로 동작):

- `CheckItem.fix`, `PrecheckResult.sizes`
- `Solution.seed`, `.elapsed_ms`, `.alternatives`, `.details`
- `evaluate(candidates, teams, weights, hard, team_size=None)`, `EvaluateError(code, message, items)`

## 라우터에 붙이는 법 (백엔드 2 참고용)

```python
sol = optimize(cands, body.team_size, weights, hard, starts=body.starts, seed=body.seed)
d = sol.details                       # explain.explain_solution 결과
names = [f"{k + 1}팀" for k in range(len(sol.teams))]
for k, (team, info) in enumerate(zip(sol.teams, d["teams"])):
    # info: fit_score, is_lowest, subscores, common_hours, common_slots, summary, warnings, violations,
    #       members[{student_id, assigned_role, preference_rank}]  ← assign_roles 대신 이 값을 쓴다
    ...
conditions = [{**c, "teams": [names[i] for i in c.pop("team_indexes")]} for c in d["conditions"]]
extra = {"seed": d["seed"], "elapsed_ms": d["elapsed_ms"], "alternatives": d["alternatives"]}
```

evaluate 엔드포인트:

```python
try:
    out = evaluate(cands, [t.member_ids for t in body.teams], weights, hard, team_size=body.team_size)
except EvaluateError as e:
    raise HTTPException(422, detail={"code": e.code, "message": e.message, "items": e.items})
```

## 바뀐 동작

- 팀 수: `round(n / size)` → `floor(n / size)` + 남는 학생은 앞 팀부터 1명씩 (46명·4명 → 5,5,4×9).
- 태그 별칭: `개발` = 프론트엔드·백엔드·데이터 희망, `N학년` = 학년. 모르는 태그는 precheck 실패로 알림.
- 역할 점수: 희망 순위 반영 (1지망 1.0 · 2지망 0.6 · 3지망 이하 0.3), 서로 다른 역할 최대 배정.
- 속도: 교환마다 바뀐 두 팀만 다시 채점, 팀 점수 캐시. 45명 약 1초, 90명 약 5초, 전체 상한 20초.

## 교수 메모 해석 (LLM, 선택)

`nl_rules.parse_requirements`는 LLM 설정이 있으면 `llm_rules.py`의 LLM 해석기를 먼저 쓰고, 없거나 실패하면 기존 규칙 기반으로 돌아갑니다. 라우터 코드는 바꿀 필요가 없습니다.

- 설정: `backend/.env`에 `TEAMFIT_LLM_PROVIDER`(anthropic/openai), `TEAMFIT_LLM_MODEL`, API 키 (`.env.example` 참고)
- LLM은 `role_min`·`spread`·`weight` 세 가지 조건과 정해진 태그로만 답하게 하고, 형식·태그·범위를 검사해 어긋난 항목은 버립니다.
- 엔진이 못 하는 요구(특정 학생, 성적, 유학생 등)는 `applied=False`, "적용 안 됨: …"으로 돌려 화면에서 교수에게 보입니다.
- 같은 메모는 한 번만 호출(캐시)해서 사전 점검과 매칭이 같은 해석을 씁니다. temperature 0.
- 평가: `python scripts/eval_memo_parser.py --mode both` — 정답 세트 `tests/data/memo_gold.json`(메모 20개)으로 규칙 기반과 LLM을 비교. 규칙 기반 기준값: 완전 일치 7/20, 재현율 0.50, 지원 안 되는 요구 알림 0/3.

## 확인 필요

- `traits.lead` 5가 "주도형"인지 (아니면 `constraints.LEAD_HIGH` 규칙을 뒤집음).
- 설문 `roles`가 고른 순서대로 저장·조회되는지.

## 테스트

```bash
cd backend && python -m pytest -q tests/test_engine_port.py
```
