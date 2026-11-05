"""교수 메모 LLM 해석기 테스트 — 실제 LLM 없이 가짜 응답으로 검증 (AI 담당)."""
import json

import pytest

from app.engine import llm_rules, nl_rules
from app.engine.llm_rules import make_llm_parser, to_rules


def fake(answer, calls=None):
    """미리 정한 JSON(또는 문자열)을 돌려주는 가짜 LLM."""
    def complete(text):
        if calls is not None:
            calls.append(text)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    return complete


MEMO = "팀마다 디자이너가 한 명은 꼭 있었으면 하고, 회의 시간 맞는 게 중요해요. 민수와 지훈은 떨어뜨려 주세요."
ANSWER = {
    "rules": [
        {"kind": "role_min", "tag": "디자인", "count": 1, "source": "팀마다 디자이너가 한 명은 꼭 있었으면"},
        {"kind": "weight", "axis": "time", "delta": 1, "source": "회의 시간 맞는 게 중요해요"},
    ],
    "unsupported": [{"source": "민수와 지훈은 떨어뜨려", "reason": "특정 학생 분리는 화면에서 지정"}],
}


def test_llm_rules_feed_engine_conditions():
    res = nl_rules.parse_requirements(MEMO, llm=make_llm_parser(fake(ANSWER)))
    assert res.hard_patch.role_minimums == {"디자인": 1}
    assert res.weight_patch == {"time": 1}
    shown = [(r.description, r.applied) for r in res.rules]
    assert ("각 팀에 '디자인' 1명 이상", True) in shown
    assert ("공통 시간 가중치 +1", True) in shown
    assert ("적용 안 됨: 특정 학생 분리는 화면에서 지정", False) in shown


def test_invalid_items_are_dropped_and_values_clamped():
    data = {"rules": [
        {"kind": "role_min", "tag": "디자이너", "count": 1, "source": "x"},     # 어휘에 없는 태그
        {"kind": "role_min", "tag": "발표", "count": 9, "source": "x"},         # 인원 범위 밖
        {"kind": "role_min", "tag": "4학년", "count": 2, "source": "x"},
        {"kind": "role_min", "tag": "4학년", "count": 1, "source": "x"},        # 중복
        {"kind": "spread", "tag": "유학생", "source": "x"},                     # 어휘에 없는 태그
        {"kind": "weight", "axis": "major", "delta": 5, "source": "x"},        # ±2로 자름
        {"kind": "weight", "axis": "grade", "delta": 1, "source": "x"},        # 없는 축
        {"kind": "max_value", "tag": "4학년", "source": "x"},                   # 없는 종류
        "문자열",
    ]}
    rules = to_rules(data, "메모")
    assert [(r.role_min_tag, r.role_min_count, r.weight_axis, r.weight_delta) for r in rules] == [
        ("4학년", 2, None, 0), (None, 1, "major", 2)]


def test_quote_not_in_memo_falls_back_to_whole_memo():
    rules = to_rules({"rules": [{"kind": "spread", "tag": "3학년", "source": "지어낸 문장"}]}, "3학년 고르게")
    assert rules[0].source == "3학년 고르게"


def test_json_wrapped_in_code_fence_is_read():
    parse = make_llm_parser(fake("```json\n" + json.dumps(ANSWER, ensure_ascii=False) + "\n```"))
    assert len(parse(MEMO)) == 3


def test_llm_failure_falls_back_to_rules():
    memo = "발표 경험이 있는 학생을 각 팀에 최소 1명씩 포함해 주세요."
    res = nl_rules.parse_requirements(memo, llm=make_llm_parser(fake(TimeoutError("timeout"))))
    assert res.hard_patch.role_minimums == {"발표": 1}          # 규칙 기반 결과


def test_same_memo_calls_llm_once_and_returns_fresh_rules():
    calls = []
    parse = make_llm_parser(fake(ANSWER, calls))
    a = parse(MEMO)
    a[0].applied = False                                          # 교수가 하나를 꺼도
    b = parse(MEMO)
    assert len(calls) == 1 and b[0].applied is True               # 캐시에 영향 없음


def test_empty_memo_does_not_call_llm():
    calls = []
    assert make_llm_parser(fake(ANSWER, calls))("   ") == [] and calls == []


def test_default_llm_is_off_without_settings(monkeypatch, tmp_path):
    for k in ("TEAMFIT_LLM_PROVIDER", "TEAMFIT_LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)                                    # .env 없음
    assert llm_rules.default_llm() is None
    (tmp_path / ".env").write_text("TEAMFIT_LLM_PROVIDER=anthropic\nTEAMFIT_LLM_MODEL=some-model\n"
                                   "ANTHROPIC_API_KEY=sk-test-123456\n", encoding="utf-8")
    assert callable(llm_rules.default_llm())                        # .env만으로 켜짐 (호출은 안 함)


@pytest.mark.parametrize("tag,ok", [("발표", True), ("개발", True), ("리더", True), ("4학년", True),
                                    ("5학년", False), ("디자이너", False), ("", False)])
def test_allowed_tags(tag, ok):
    assert llm_rules.allowed_tag(tag) is ok


def test_provider_requests_and_responses(monkeypatch):
    sent = []

    def fake_post(url, headers, body, timeout):
        sent.append((url, headers, body))
        text = json.dumps(ANSWER, ensure_ascii=False)
        if "anthropic" in url:
            return {"content": [{"type": "text", "text": text}]}
        return {"choices": [{"message": {"content": text}}]}

    monkeypatch.setattr(llm_rules, "_post", fake_post)
    for maker in (llm_rules.anthropic_complete, llm_rules.openai_complete):
        out = maker("model-x", "key-123", 5)(MEMO)
        assert json.loads(out) == ANSWER
    (u1, h1, b1), (u2, h2, b2) = sent
    assert u1.endswith("/v1/messages") and h1["x-api-key"] == "key-123" and b1["temperature"] == 0
    assert b1["system"] == llm_rules.SYSTEM_PROMPT and b1["messages"][-1] == {"role": "user", "content": MEMO}
    assert u2.endswith("/v1/chat/completions") and h2["authorization"] == "Bearer key-123"
    assert b2["response_format"] == {"type": "json_object"} and b2["messages"][0]["role"] == "system"
