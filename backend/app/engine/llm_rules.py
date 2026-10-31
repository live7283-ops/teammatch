"""교수 메모 → 조건 해석: LLM 연결부 (AI 담당).

nl_rules.parse_requirements(text, llm=...)의 `llm` 자리에 들어가는 콜백을 만든다.
LLM은 정해진 JSON 형식으로만 답하게 하고, 엔진이 아는 조건·태그만 통과시킨다.
LLM이 설정되지 않았거나 실패하면 None/예외 → nl_rules가 규칙 기반 해석으로 돌아간다.

설정 (환경변수 또는 backend/.env)
  TEAMFIT_LLM_PROVIDER   anthropic | openai   (비우면 LLM 사용 안 함)
  TEAMFIT_LLM_MODEL      사용할 모델 이름        (필수)
  ANTHROPIC_API_KEY / OPENAI_API_KEY
  TEAMFIT_LLM_TIMEOUT    초, 기본 15

엔진이 지원하는 조건
  role_min : 팀마다 태그 보유자 최소 count명      → HardRules.role_minimums
  spread   : 태그 보유자를 팀마다 고르게            → HardRules.spread_tags
  weight   : 점수 축 가중치 조정 (major/role/time/trait, ±1~2)
그 밖의 요구(특정 학생 분리, 성적, 유학생 등)는 unsupported로 돌려 교수에게 "적용 안 됨"으로 보여 준다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from functools import lru_cache
from typing import Callable

from .constraints import ROLES
from .nl_rules import ParsedRule

AXES = {"major": "전공 다양성", "role": "역할 균형", "time": "공통 시간", "trait": "협업 성향"}
EXTRA_TAGS = ("개발", "리더")
_YEAR = re.compile(r"^[1-4]학년$")

SYSTEM_PROMPT = """너는 대학 수업 팀 편성 서비스의 조건 해석기다.
교수가 쓴 요구사항 메모를 읽고, 팀 편성 엔진이 실행할 수 있는 조건으로만 바꿔 JSON 하나로 답한다.

쓸 수 있는 조건 (이 세 가지뿐):
1. role_min — 팀마다 어떤 태그를 가진 학생이 최소 count명 있어야 함
   {"kind": "role_min", "tag": "<태그>", "count": <1~4 정수>, "source": "<메모 원문 조각>"}
2. spread — 어떤 태그를 가진 학생을 여러 팀에 고르게 나눔 (한 팀에 몰리지 않게)
   {"kind": "spread", "tag": "<태그>", "source": "<메모 원문 조각>"}
3. weight — 점수 축의 중요도 조정. axis는 major(전공 다양성), role(역할 겹치지 않게), time(회의 시간 맞추기), trait(성향 비슷하게)
   {"kind": "weight", "axis": "<major|role|time|trait>", "delta": <-2~2, 0 아님>, "source": "<메모 원문 조각>"}

태그는 아래 목록에 있는 글자 그대로만 쓴다.
- 희망 역할: 기획, 프론트엔드, 백엔드, 데이터, 디자인, 발표
- 개발 (프론트엔드·백엔드·데이터 중 하나라도 희망), 리더 (주도적 성향)
- 학년: 1학년, 2학년, 3학년, 4학년
"디자이너"는 디자인, "발표 잘하는/발표 경험"은 발표, "개발자/개발 경험"은 개발, "리더 역할/팀장"은 리더처럼 뜻이 같은 태그로 바꾼다.

위 조건으로 표현할 수 없는 요구(특정 학생 이름이나 쌍, 성적, 유학생·편입생, 팀당 최대 인원 등)는 억지로 바꾸지 말고 unsupported에 넣는다.
요구사항이 없으면 두 목록 모두 비운다. source는 메모에서 그대로 따온 짧은 조각이다.

답은 아래 JSON 하나만, 설명 없이:
{"rules": [...], "unsupported": [{"source": "<원문 조각>", "reason": "<지원하지 않는 이유 한 줄>"}]}"""

FEW_SHOT = [
    ("발표 경험자는 팀마다 한 명씩, 4학년은 한 팀에 몰리지 않게 해 주세요.",
     {"rules": [{"kind": "role_min", "tag": "발표", "count": 1, "source": "발표 경험자는 팀마다 한 명씩"},
                {"kind": "spread", "tag": "4학년", "source": "4학년은 한 팀에 몰리지 않게"}],
      "unsupported": []}),
    ("회의 시간 맞는 게 제일 중요하고, 민수와 지훈은 떨어뜨려 주세요.",
     {"rules": [{"kind": "weight", "axis": "time", "delta": 2, "source": "회의 시간 맞는 게 제일 중요"}],
      "unsupported": [{"source": "민수와 지훈은 떨어뜨려", "reason": "특정 학생 분리는 조건 설정 화면의 '분리할 학생'에서 지정"}]}),
]


# ── 설정 ────────────────────────────────────────────────────────────
def _env(name: str) -> str | None:
    """환경변수 → 없으면 현재 폴더의 .env (KEY=VALUE)에서 찾는다."""
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:
        with open(".env", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, val = line.split("=", 1)
                    if k.strip() == name:
                        return val.strip().strip('"').strip("'") or None
    except OSError:
        pass
    return None


# ── 응답 검증 → ParsedRule ──────────────────────────────────────────
def allowed_tag(tag: str) -> bool:
    return tag in ROLES or tag in EXTRA_TAGS or bool(_YEAR.match(tag))


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def to_rules(data: dict, text: str) -> list[ParsedRule]:
    """LLM JSON → ParsedRule 목록. 형식·태그·범위를 검사하고 어긋난 항목은 버린다."""
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    out: list[ParsedRule] = []
    seen = set()
    memo = _norm(text)

    def src(item) -> str:
        s = str(item.get("source") or "").strip()
        return s if s and _norm(s) in memo else text.strip()   # 메모에 없는 인용이면 메모 전체로

    for item in data.get("rules") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind == "role_min":
            tag = str(item.get("tag", "")).strip()
            try:
                count = int(item.get("count", 1))
            except (TypeError, ValueError):
                continue
            if not allowed_tag(tag) or not 1 <= count <= 4:
                continue
            key = ("role_min", tag)
            if key in seen:
                continue
            seen.add(key)
            out.append(ParsedRule(source=src(item), kind="hard", description=f"각 팀에 '{tag}' {count}명 이상",
                                  role_min_tag=tag, role_min_count=count))
        elif kind == "spread":
            tag = str(item.get("tag", "")).strip()
            key = ("spread", tag)
            if not allowed_tag(tag) or key in seen:
                continue
            seen.add(key)
            out.append(ParsedRule(source=src(item), kind="hard", description=f"'{tag}'을(를) 여러 팀에 고르게 분산",
                                  spread_tag=tag))
        elif kind == "weight":
            axis = str(item.get("axis", "")).strip()
            try:
                delta = int(item.get("delta", 0))
            except (TypeError, ValueError):
                continue
            key = ("weight", axis)
            if axis not in AXES or delta == 0 or key in seen:
                continue
            delta = max(-2, min(2, delta))
            seen.add(key)
            out.append(ParsedRule(source=src(item), kind="soft",
                                  description=f"{AXES[axis]} 가중치 {'+' if delta > 0 else ''}{delta}",
                                  weight_axis=axis, weight_delta=delta))
    for item in data.get("unsupported") or []:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "엔진이 지원하지 않는 조건").strip()
        # weight_axis 없음 + applied=False → 집계에서 빠지고, 화면에는 '적용 안 됨'으로 보인다
        out.append(ParsedRule(source=src(item), kind="soft", description=f"적용 안 됨: {reason}", applied=False))
    return out


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.S)          # 코드 블록이나 앞뒤 설명이 붙어 와도 JSON만 꺼냄
    return json.loads(m.group(0) if m else raw)


# ── 공급자 호출 ─────────────────────────────────────────────────────
def _post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"content-type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _messages(text: str) -> list[dict]:
    msgs = []
    for q, a in FEW_SHOT:
        msgs.append({"role": "user", "content": q})
        msgs.append({"role": "assistant", "content": json.dumps(a, ensure_ascii=False)})
    msgs.append({"role": "user", "content": text})
    return msgs


def anthropic_complete(model: str, api_key: str, timeout: float) -> Callable[[str], str]:
    def call(text: str) -> str:
        r = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                  {"model": model, "max_tokens": 1024, "temperature": 0, "system": SYSTEM_PROMPT,
                   "messages": _messages(text)}, timeout)
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
    return call


def openai_complete(model: str, api_key: str, timeout: float) -> Callable[[str], str]:
    def call(text: str) -> str:
        r = _post("https://api.openai.com/v1/chat/completions", {"authorization": f"Bearer {api_key}"},
                  {"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + _messages(text)}, timeout)
        return r["choices"][0]["message"]["content"]
    return call


def make_llm_parser(complete: Callable[[str], str], cache_size: int = 256) -> Callable[[str], list[ParsedRule]]:
    """complete(text) -> 모델 원문 응답. 같은 메모는 한 번만 호출해(사전 점검과 매칭이 같은 해석을 쓰게) 캐시한다."""
    @lru_cache(maxsize=cache_size)
    def raw(text: str) -> str:
        return complete(text)

    def parse(text: str) -> list[ParsedRule]:
        if not text or not text.strip():
            return []
        return to_rules(_extract_json(raw(text.strip())), text)   # 매번 새 ParsedRule (applied를 바꿔도 캐시에 안 남음)
    parse.cache_clear = raw.cache_clear
    return parse


_DEFAULT: dict = {}


def default_llm() -> Callable[[str], list[ParsedRule]] | None:
    """환경 설정이 있으면 LLM 파서, 없으면 None (→ 규칙 기반)."""
    provider = (_env("TEAMFIT_LLM_PROVIDER") or "").lower()
    model = _env("TEAMFIT_LLM_MODEL")
    if provider not in ("anthropic", "openai") or not model:
        return None
    key = _env("ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY")
    if not key:
        return None
    timeout = float(_env("TEAMFIT_LLM_TIMEOUT") or 15)
    sig = (provider, model, key[-6:], timeout)
    if _DEFAULT.get("sig") != sig:
        maker = anthropic_complete if provider == "anthropic" else openai_complete
        _DEFAULT["sig"], _DEFAULT["parser"] = sig, make_llm_parser(maker(model, key, timeout))
    return _DEFAULT["parser"]
