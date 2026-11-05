# TeamMatch 백엔드

`index.html` 프론트엔드를 위한 **Python (FastAPI) + PostgreSQL** 백엔드입니다.
프론트엔드가 `state`에 들고 있던 데이터를 영구 저장하고, 핵심 비즈니스 로직인 **팀 매칭**을 맡습니다.

## 스택

| 구분 | 사용 기술 |
| --- | --- |
| API | FastAPI: HTTP API, 요청 검증 |
| ORM | SQLAlchemy 2.0: `app/models.py` (`db/schema.sql`과 1:1 대응) |
| DB | PostgreSQL (psycopg 3) |
| 인증 | JWT (python-jose) + bcrypt (passlib) |
| 매칭 | 순수 Python: 기본 엔진 `app/matching.py`, AI 엔진 `app/engine/` (DB와 독립, 단위 테스트 포함) |
| 실행 | Docker Compose (PostgreSQL 15 + Python 3.13) |

---

## 빠른 시작

### 1. Docker로 실행 (권장)

저장소 루트(`docker-compose.yaml`이 있는 폴더)에서 실행합니다.

```bash
docker compose up --build
```

- 처음 띄울 때 `db/schema.sql`이 자동으로 적용되어 테이블과 기본 프리셋이 만들어집니다.
- 스키마가 바뀌었거나 테이블 오류가 나면 DB를 초기화한 뒤 다시 띄웁니다. 기존 데이터는 삭제됩니다.

  ```bash
  docker compose down -v
  docker compose up --build
  ```

### 2. 직접 실행 (Windows PowerShell)

`backend/` 폴더에서 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 데이터베이스 생성 후 스키마 적용
psql -U postgres -c "CREATE DATABASE teammatch;"
psql -U postgres -d teammatch -f db/schema.sql

copy .env.example .env    # 복사한 뒤 값 수정

uvicorn app.main:app --reload
```

macOS / Linux는 가상환경 부분만 다릅니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

### 3. 확인

| 항목 | 주소 / 명령 |
| --- | --- |
| API 문서 (Swagger) | http://127.0.0.1:8000/docs |
| 상태 확인 | http://127.0.0.1:8000/health → `{"status": "ok"}` |
| 단위 테스트 | `backend/`에서 `python -m pytest -q` (DB 불필요) |
| 전체 흐름 점검 | 서버를 띄운 뒤 `python scripts/e2e_match_flow.py --n 45` |

Docker로 띄웠다면 컨테이너 안에서 실행할 수 있습니다.

```bash
docker compose exec backend python -m pytest -q
docker compose exec backend python scripts/e2e_match_flow.py --n 45
```

자세한 테스트 시나리오는 [TESTING.md](TESTING.md)를 참고하세요.

---

## 폴더 구조

```text
backend/
├── db/
│   └── schema.sql             # PostgreSQL DDL + 기본 프리셋(ps0~ps4) 시드
├── app/
│   ├── config.py              # 환경변수 설정
│   ├── database.py            # DB 엔진 + 세션 + get_db 의존성
│   ├── models.py              # ORM 모델 (schema.sql과 1:1)
│   ├── security.py            # 비밀번호 해싱, JWT, 인증 의존성
│   ├── schemas.py             # Pydantic 요청/응답 모델
│   ├── errors.py              # 공통 에러 응답 형식
│   ├── matching.py            # 기본 매칭 엔진 (그리디, 순수 함수)
│   ├── main.py                # 앱 진입점 + CORS + 에러 핸들러 + 라우터 연결
│   ├── engine/                # AI 엔진 v1.1 (아래 "AI 엔진" 참고)
│   └── routers/
│       ├── auth.py            # 회원가입 / 로그인 / 내 정보 / 탈퇴
│       ├── classes.py         # 수업 CRUD + 명단 + 참여 코드
│       ├── surveys.py         # 수업별 설문 제출 / 조회
│       ├── matching.py        # 기본 매칭 실행, 프리셋, 결과·이력·팀 상세 조회
│       ├── matching_v2.py     # 사전 점검, AI 엔진 매칭
│       └── teams.py           # 팀원 이동·교체·역할 수정, 확정·해제
├── scripts/
│   ├── engine_demo.py         # 합성 수강생으로 AI 엔진 실행 (DB 불필요)
│   ├── eval_memo_parser.py    # 교수 메모 해석 정확도 평가
│   └── e2e_match_flow.py      # 실제 서버 + DB로 가입→매칭→수정→확정 전체 점검
├── tests/                     # 단위 테스트 (아래 "테스트" 참고)
├── Dockerfile
├── requirements.txt
├── pytest.ini
├── .env.example
├── TESTING.md                 # 테스트 가이드
└── SECURITY_CHECKLIST.md      # 보안 점검 체크리스트
```

---

## API 목록

`[교수]`, `[학생]`은 해당 역할만 호출할 수 있고, `[로그인]`은 역할에 상관없이 로그인이 필요합니다.

### 인증 `routers/auth.py`

| 메서드 | 경로 | 권한 | 설명 |
| --- | --- | --- | --- |
| POST | `/api/auth/signup` | | 회원가입 (학생/교수). 이메일 중복·학번 누락 검사 후 토큰 발급 |
| POST | `/api/auth/login` | | 로그인 후 JWT 발급 (form: `username`=이메일, `password`) |
| GET | `/api/auth/me` | 로그인 | 내 정보 조회 |
| PUT | `/api/auth/me` | 로그인 | 내 프로필 수정 (보낸 필드만 변경) |
| DELETE | `/api/auth/me` | 로그인 | 회원 탈퇴 (soft delete: `is_active=false`, 이후 로그인 403) |

### 수업 `routers/classes.py`

| 메서드 | 경로 | 권한 | 설명 |
| --- | --- | --- | --- |
| POST | `/api/classes` | 교수 | 수업 생성 (참여 코드 자동 생성) |
| GET | `/api/classes` | 로그인 | 교수는 내 수업, 학생은 수강 중인 수업 목록 |
| PUT | `/api/classes/{id}` | 교수 | 수업 수정 (본인 수업만) |
| DELETE | `/api/classes/{id}` | 교수 | 수업 삭제 (본인 수업만) |
| GET | `/api/classes/{id}/roster` | 교수 | 수강생 명단 + 설문 제출 현황 |
| GET | `/api/classes/{id}/candidates` | 교수 | 매칭 대상 학생과 분포 미리 보기 |
| POST | `/api/classes/join` | 학생 | 참여 코드로 수업 등록 (중복 참여 방지) |

### 설문 `routers/surveys.py`

| 메서드 | 경로 | 권한 | 설명 |
| --- | --- | --- | --- |
| PUT | `/api/classes/{id}/survey` | 학생 | 설문 제출/수정 (역할·스킬·성향·가능 시간·매칭 준비). 스킬과 가능 시간은 통째로 교체 |
| GET | `/api/classes/{id}/survey` | 학생 | 내가 제출한 설문 조회 |

### 매칭 `routers/matching.py`, `routers/matching_v2.py`

| 메서드 | 경로 | 권한 | 설명 |
| --- | --- | --- | --- |
| POST | `/api/classes/{id}/precheck` | 교수 | 실행 전 점검: 편성 가능 여부 + 완화안 |
| POST | `/api/classes/{id}/match-v2` | 교수 | AI 엔진 매칭 (목적함수 J 최적화, 팀 설명·조건 충족 포함) |
| POST | `/api/classes/{id}/match` | 교수 | 기본 엔진(그리디) 매칭 |
| GET | `/api/presets` | 교수 | 기본 프리셋 + 내 프리셋 목록 |

### 결과 조회·수정·확정 `routers/matching.py`, `routers/teams.py`

| 메서드 | 경로 | 권한 | 설명 |
| --- | --- | --- | --- |
| GET | `/api/classes/{id}/result` | 교수 | 가장 최근 매칭 결과 |
| GET | `/api/classes/{id}/runs` | 교수 | 매칭 실행 이력 목록 (요약) |
| GET | `/api/runs/{run_id}` | 교수 | 특정 실행 상세 |
| GET | `/api/teams/{team_id}` | 교수 | 팀 상세: 팀원 정보, 각자의 가능 시간, 팀 공통 가능 시간 |
| PATCH | `/api/runs/{run_id}/move` | 교수 | 학생 한 명을 다른 팀으로 이동 |
| PATCH | `/api/runs/{run_id}/swap` | 교수 | 두 학생의 팀 맞바꾸기 |
| PATCH | `/api/runs/{run_id}/role` | 교수 | 팀원의 배정 역할 수정 |
| POST | `/api/runs/{run_id}/confirm` | 교수 | 결과 확정 (이후 수정하면 409) |
| POST | `/api/runs/{run_id}/unconfirm` | 교수 | 확정 해제 |

- `match-v2`로 만든 결과는 이동·교체 후 AI 엔진이 팀 점수(`fit_score`)와 평균(`avg_score`)을 다시 계산합니다.
- 상태 확인: `GET /health`

---

## 프론트엔드 연동

현재 `index.html`은 아직 API를 호출하지 않습니다. 아래는 연결할 때 화면 데이터와 엔드포인트의 대응표입니다.

| 프론트엔드 (`index.html`) | 백엔드 |
| --- | --- |
| `authRole` 학생/교수, 로그인/회원가입 | `POST /api/auth/signup`, `POST /api/auth/login`, `GET /api/auth/me` |
| `state.prof.classes[]`, 참여 코드 `c.join` | `POST /api/classes`, `GET /api/classes`, `POST /api/classes/join` |
| `ROSTER` (학생 명단) + 제출 상태 | `GET /api/classes/{id}/roster` |
| `state.user` 역할 / 스킬 / 성향 / 일정 | `PUT`·`GET /api/classes/{id}/survey` |
| `setup.weights` + `hard` + 프리셋 | `POST /api/classes/{id}/precheck`, `GET /api/presets` |
| "AI 팀매칭" 실행 + `state.prof.result` | `POST /api/classes/{id}/match-v2` (기본 엔진은 `/match`) → `match_runs` + `teams` + `team_members`에 저장 |
| 결과 화면, 팀 카드, 팀원 이동 | `GET /api/classes/{id}/result`, `GET /api/teams/{id}`, `PATCH /api/runs/{id}/move`·`swap`·`role` |
| 결과 확정 | `POST /api/runs/{id}/confirm`, `unconfirm` |

---

## 데이터 모델 참고

- **사용자**: `users` 테이블 하나를 `role`(student / professor)로 구분합니다. 학생 전용·교수 전용 컬럼은 NULL을 허용합니다. 탈퇴는 행을 지우지 않고 `is_active=false`로 바꿉니다.
- **설문**: 수강(enrollment) 단위로 `survey_responses`(+ `survey_skills`, `survey_availability`)에 저장하므로, 학생은 수업마다 다르게 답할 수 있습니다.
- **가능 시간**: 프론트엔드의 day-block 그리드를 선택된 칸당 한 행으로 저장합니다. `day`는 0=월 … 6=일, `block`은 프론트엔드 `BLOCKS[]`의 인덱스입니다.
- **프리셋**: `owner_id IS NULL`(`is_builtin=true`)인 프리셋은 `schema.sql` 아래쪽 시드로 들어가는 공용 기본값(프론트엔드 ps0~ps4)입니다.
- **매칭 결과**: `match_runs`에 실행 조건과 점수를 저장합니다. `hard_detail`(JSON)에는 AI 엔진 세부 하드 조건이, `confirmed_at`에는 확정 시각(NULL이면 검토 중)이 들어갑니다.
- **ENUM 컬럼**: `users.role`, `classes.status`, `survey_availability.state`는 PostgreSQL ENUM 타입이라 ORM에서도 `sqlalchemy.Enum`으로 매핑합니다.

## 공통 에러 형식 (`app/errors.py`)

모든 에러는 아래 한 가지 형식으로 응답합니다.

```json
{
  "error": {
    "code": 409,
    "message": "사람이 읽을 메시지",
    "detail": null,
    "path": "/api/runs/..."
  }
}
```

| 상황 | 코드 | `detail` |
| --- | --- | --- |
| `HTTPException` (404, 409 등) | 해당 코드 | `null` |
| 요청 검증 실패 | 422 | 어떤 필드가 틀렸는지 목록 |
| 예상 못 한 서버 오류 | 500 | `null` (스택은 서버 로그에만 남김) |

---

## 매칭 엔진

### 기본 엔진 (`app/matching.py`, `/match`)

`form_teams(candidates, team_size, weights, hard)`는 그리디 밸런싱 휴리스틱입니다.

1. 팀 수 = `ceil(n / team_size)`
2. 가장 드문 역할을 팀마다 하나씩 먼저 배정한 뒤, 나머지 학생은 팀 점수를 가장 많이 올리는 팀에 배정합니다 (가능한 한 하드 조건을 지킴).
3. 각 팀은 교수가 정한 1~5 가중치로 아래 4개 축을 합쳐 0~100점의 조화도 점수(fit score)를 받습니다.

| 축 | 의미 |
| --- | --- |
| `major` | 전공 다양성 (`same_major` 하드 조건이 켜지면 동일성) |
| `role` | 서로 다른 역할을 얼마나 채웠는지 |
| `time` | 가능 시간이 겹치는 정도 |
| `trait` | 팀원 간 작업 성향이 비슷한 정도 |

### AI 엔진 v1.1 (`app/engine/`, `/precheck`·`/match-v2`)

기본 엔진은 그대로 두고, 더 정교한 최적화 엔진을 별도 엔드포인트로 제공합니다. 자세한 내용은 [app/engine/README.md](app/engine/README.md)에 있습니다.

| 파일 | 역할 |
| --- | --- |
| `constraints.py` | 점수 축 4개, 태그 어휘, 하드 조건 위반 계산, 목적함수 J |
| `scoring.py` | 팀 점수를 캐시하고 바뀐 팀만 다시 계산하는 빠른 채점기 |
| `precheck.py` | 팀 크기 규칙, 개수 기반 사전 점검 + 완화안 |
| `optimizer.py` | 초기 배치 → 국소 탐색 → 담금질 → 마무리, 여러 번 시작해 최선 선택 |
| `explain.py` | 팀 카드 설명(하위 점수·공통 시간·경고·역할 배정), 조건 충족 표, 수정 후 재채점 |
| `nl_rules.py` | 교수 메모 해석 (규칙 기반) |
| `llm_rules.py` | 교수 메모 LLM 해석기 (선택, 설정이 있을 때만 사용) |

**점수와 목적함수**

- 팀 조화도 = `Σ(wₖ · sₖ) / Σ(wₖ) × 100`
  - `sₖ`: 축별 0~1 점수 (전공 다양성 / 역할 균형 / 공통 시간 / 협업 성향)
  - `wₖ`: 교수가 정한 1~5 가중치
- 목적함수 **J = 평균 조화도 + 최저 팀 점수 − 1000 × 하드 위반 수**
  - 평균뿐 아니라 가장 약한 팀까지 끌어올리는 방향으로 최적화합니다.
  - 하드 위반 1건에 1,000점을 빼므로 사실상 금지입니다.

**축별 점수 규칙**

| 축 | 계산 |
| --- | --- |
| 전공 | 팀 안 서로 다른 학과 수 ÷ min(팀 인원, 수업 전체 학과 수) |
| 역할 | 희망 순위 반영 (1지망 1.0 · 2지망 0.6 · 3지망 이하 0.3), 서로 다른 역할을 최대한 배정 |
| 시간 | 팀 공통 가능 시간 ÷ 주 6시간 (6시간 이상이면 만점) |
| 성향 | 작업 페이스·의사결정·소통 빈도가 비슷한 정도 + 리더 성향(`lead` ≥ 4) 보유 여부 |

**최적화 단계**

1. **팀 크기 결정**: 팀 수 = `floor(n / team_size)`, 남는 학생은 앞 팀부터 1명씩 (46명·4명 → 5명×2 + 4명×9)
2. **초기 배치**: 발표·개발 경험처럼 드문 조건을 가진 학생을 팀마다 먼저 나누고, 나머지는 점수가 가장 오르는 팀에 배치
3. **국소 탐색**: 두 학생을 맞바꾸거나 옮겨서 J가 오를 때만 채택
4. **담금질(SA)**: 학생 1명당 400번 시도, 온도 1.5 → 0.02. 점수가 잠깐 내려가는 교환도 확률적으로 받아들여 막다른 해에서 벗어나고, 30%는 최저 팀을 골라 집중 개선
5. **마무리**: 국소 탐색으로 다시 다듬고, 서로 다른 시작점에서 `starts`번(기본 3) 실행해 J가 가장 큰 결과를 채택. 전체 계산은 20초를 넘지 않음 (45명 약 1~2초)

**하드 조건** (`MatchV2Request.hard`)

| 필드 | 의미 |
| --- | --- |
| `same_major_max` | 팀당 같은 학과 최대 인원 |
| `separate_pairs` | 다른 팀에 넣을 학생 쌍 |
| `fixed_pairs` | 같은 팀에 넣을 학생 쌍 |
| `spread_tags` | 팀마다 고르게 나눌 태그 (예: `4학년`) |
| `role_minimums` | 팀마다 최소 인원이 필요한 태그 (예: `{"발표": 1}`) |

태그는 역할(기획·프론트엔드·백엔드·데이터·디자인·발표), `개발`(프론트엔드·백엔드·데이터 중 하나), `N학년`, 학과 이름, `리더`를 쓸 수 있습니다.

**교수 메모 해석** (`note`)

- 기본은 규칙 기반 해석이라 API 키 없이 동작합니다.
  - "각 팀에 발표 경험 최소 1명" → `role_minimums`
  - "4학년은 한 팀에 몰리지 않게" → `spread_tags`
  - "전공이 다양하게" → 전공 가중치 +1
- `.env`에 `TEAMFIT_LLM_PROVIDER`(anthropic / openai), `TEAMFIT_LLM_MODEL`, API 키를 넣으면 LLM 해석을 먼저 쓰고, 실패하면 규칙 기반으로 돌아갑니다 (`.env.example` 참고).
- 엔진이 처리할 수 없는 요구(특정 학생, 성적 등)는 "적용 안 됨"으로 표시해 교수에게 보여 줍니다.

**`match-v2` 응답**에는 목적함수 J, 평균 조화도, 최저 팀 점수, 하드 위반 수, 교환 횟수, 팀별 결과(최저 팀 표시, 팀원별 배정 역할), 조화도 추이(그래프용), 메모 해석 결과가 담깁니다.

**한계**: 두 엔진 모두 휴리스틱이라 최적해를 보장하지 않습니다. 정확한 최적해가 필요하면 API·DB는 그대로 두고 `optimizer.py`만 ILP/제약 솔버로 바꾸면 됩니다.

---

## 코드 파일별 기능

라우터별 엔드포인트는 위 [API 목록](#api-목록)을 참고하세요.

| 파일 | 기능 |
| --- | --- |
| `app/config.py` | `.env`에서 설정을 읽는 `Settings` (pydantic-settings). `database_url`, `jwt_secret`·`jwt_algorithm`·`access_token_expire_minutes`, `cors_origins`. `get_settings()`는 `@lru_cache`로 한 번만 읽음 |
| `app/database.py` | SQLAlchemy 엔진과 `SessionLocal`, 모든 모델의 `Base`, 요청마다 세션을 열고 닫는 `get_db()` |
| `app/models.py` | `schema.sql`과 1:1인 ORM 모델: `User`, `Class`, `Enrollment`, `SurveyResponse`, `SurveySkill`, `SurveyAvailability`, `MatchPreset`, `MatchRun`, `Team`, `TeamMember`. 관계와 제약조건 선언 |
| `app/security.py` | `hash_password()`·`verify_password()` (bcrypt), `create_access_token()`, `get_current_user()`, `require_professor()`·`require_student()`(역할별 접근 제한), `get_owned_class()`(본인 수업 확인) |
| `app/schemas.py` | 요청/응답 형식과 검증 규칙 (예: `SignupRequest`, `ClassCreate`, `SurveySubmit`, `MatchV2Request`). 가중치 1~5, 성향 범위 등을 자동 검증 |
| `app/errors.py` | 공통 에러 응답 형식 등록 (`register_error_handlers`) |
| `app/matching.py` | 기본 매칭 엔진. `Candidate` 등 입력 구조, `form_teams()`, 축별 점수 `_major_score`·`_role_score`·`_time_score`·`_trait_score`, 합산 `team_fit()`, 역할 배정 `assign_roles()` |
| `app/main.py` | FastAPI 앱 생성, CORS, 에러 핸들러, 라우터 6개 연결, `GET /health` |
| `db/schema.sql` | PostgreSQL 테이블 정의(DDL), ENUM 타입, 인덱스, 기본 프리셋(ps0~ps4) 시드 |
| `requirements.txt` | 필요한 패키지. `bcrypt==4.0.1` 고정 (passlib 1.7.4와 호환, 5.0이면 가입 시 500 에러) |
| `.env.example` | 환경변수 예시. 복사해서 `.env`로 만든 뒤 값을 채움 (`.env`는 커밋하지 않음) |

---

## 테스트

`backend/`에서 `python -m pytest -q`로 전부 실행합니다 (현재 60개). 모두 DB 없이 돕니다.

| 파일 | 검증 내용 |
| --- | --- |
| `tests/test_matching.py` | 기본 엔진: 팀 수·배정, 점수 범위(0~100), `same_major`·역할 가중치, 빈 후보 |
| `tests/test_match_guards.py` | 매칭 라우터 안전망 (중복 배정 검사) |
| `tests/test_engine_v2.py` | AI 엔진 계약: 점수 범위, J 패널티, 전원 배정, 시드 결정성, 사전 점검, 메모 해석 |
| `tests/test_engine_port.py` | AI 엔진 v1.1: 팀 크기 규칙, 태그 별칭, 희망 순위 역할 배정, 빠른 채점기, 위반 없는 편성·재현성, 완화안, 재채점 |
| `tests/test_llm_rules.py` | LLM 메모 해석기 (실제 LLM 없이 가짜 응답으로) |
| `tests/test_rescore.py` | 팀원 이동·교체 후 점수 재계산, 빈 팀·명단에 없는 학생 처리 |
| `tests/test_api_auth.py` | 인증 없을 때 401, 요청 검증 422, 공통 에러 형식 |

실제 DB까지 포함한 흐름(가입 → 수업 → 설문 → 매칭 → 수정 → 확정)은 서버를 띄운 뒤 `scripts/e2e_match_flow.py`로 확인합니다.

---

## 인코딩·줄바꿈 규칙

- 모든 파일은 **UTF-8 (BOM 없음)**, 줄바꿈은 **LF**로 저장합니다.
- Windows에서 한글이 깨져 보이면 대부분 보는 도구가 CP949로 읽어서입니다.
  - VS Code: 오른쪽 아래 인코딩이 UTF-8인지 확인
  - cmd / PowerShell: `chcp 65001` 후 `git diff`·`git log`
  - Python: `setx PYTHONUTF8 1`을 한 번 실행하면 Windows에서도 UTF-8로 동작

## 관련 문서

| 문서 | 내용 |
| --- | --- |
| [TESTING.md](TESTING.md) | 처음부터 끝까지 테스트하는 방법 |
| [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) | 보안 점검 결과 |
| [app/engine/README.md](app/engine/README.md) | AI 엔진 상세 (라우터 연결법, 바뀐 동작, LLM 설정) |
