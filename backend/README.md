index.html 프론트엔드를 위한 Python (FastAPI) + PostgreSQL 백엔드입니다. 현재 프론트엔드가 state에 보관하고 있는 모든 데이터를 영구적으로 저장하며, 단 하나의 핵심 비즈니스 로직인 팀 매칭을 전담합니다.   스택 (Stack)FastAPI — HTTP API 및 유효성 검사   SQLAlchemy 2.0 — ORM (app/models.py, db/schema.sql과 동일하게 구성)   PostgreSQL — 데이터 저장소   JWT (python-jose) + bcrypt (passlib) — 인증   매칭 엔진은 순수 파이썬(pure Python)으로 작성되었으며(app/matching.py), DB와 독립적으로 동작하고 단위 테스트(unit-test)를 거쳤습니다.   폴더 구조 (Layout)Plaintextbackend/
  db/schema.sql          # PostgreSQL DDL + 기본 제공 프리셋(preset) 시드 데이터
  app/
    config.py            # 환경변수 설정
    database.py          # 엔진 + 세션 + get_db 의존성
    models.py            # ORM 모델 (schema.sql과 1:1 대응)
    security.py          # 비밀번호 해싱, JWT, 인증 의존성
    schemas.py           # Pydantic 요청/응답 모델
    matching.py          # 팀 매칭 엔진 (순수 함수)
    main.py              # 앱 진입점 + CORS + 라우터 연결
    routers/
      auth.py            # 회원가입 / 로그인 / 내 정보 확인
      classes.py         # 교수용 수업 CRUD + 명단; 학생 참여 코드(join-by-code) 입력
      surveys.py         # 수업별 설문 제출 / 조회
      matching.py        # 매칭 실행, 프리셋 목록 조회
  tests/test_matching.py # 엔진 단위 테스트
  requirements.txt
  .env.example
(위 코드 블록의 구조 및 주석 내용은 원문 코드를 번역한 것입니다.)   설정 및 실행 (Setup)PowerShell# backend/ 폴더 안에서 실행
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 데이터베이스 생성 후 스키마 로드
psql -U postgres -c "CREATE DATABASE teammatch;"
psql -U postgres -d teammatch -f db/schema.sql

copy .env.example .env   # 복사 후 값 수정

uvicorn app.main:app --reload
(위 코드 블록의 명령어 주석은 원문 코드를 번역한 것입니다.)   대화형 API 문서: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)   엔진 테스트 실행: pytest (backend/ 폴더에서 실행).   프론트엔드 연동 매핑 (How it maps to the frontend)프론트엔드 (index.html)백엔드authRole 학생/교수, 로그인/회원가입   POST /api/auth/signup, POST /api/auth/login, GET /api/auth/me   state.prof.classes[], 참여 코드 c.join   POST /api/classes, GET /api/classes, POST /api/classes/join   ROSTER (학생 명단) + 제출 상태   GET /api/classes/{id}/roster   state.user 역할 / 스킬 / 성향 / 일정   PUT/GET /api/classes/{id}/survey   setup.weights + hard + 프리셋   POST /api/classes/{id}/match, GET /api/presets   "AI 팀매칭" 실행 + state.prof.result   매칭 결과는 match_runs + teams + team_members에 저장됨   데이터 모델 참고 사항하나의 users 테이블을 사용하며 role(역할)로 구분합니다. 학생 전용 및 교수 전용 컬럼은 Null 값을 허용(nullable)합니다.   설문 데이터(Survey signals)는 수강 내역(enrollment)을 기준으로 survey_responses (+ survey_skills, survey_availability)에 저장되므로, 학생은 수업마다 다르게 답변할 수 있습니다.   가용 시간(Availability)은 프론트엔드의 "day-block" 그리드를 선택된 슬롯당 한 줄씩 데이터로 저장합니다. day 0=월 .. 6=일이며, block은 프론트엔드의 BLOCKS[] 인덱스와 일치합니다.   owner_id IS NULL (is_builtin=true)인 프리셋(Presets)은 schema.sql 하단에 시드 데이터로 제공되는 공유 기본값(프론트엔드의 ps0..ps4)입니다.   매칭 엔진 (app/matching.py)   form_teams(candidates, team_size, weights, hard) 함수는 그리디(greedy) 밸런싱 휴리스틱(탐색 기법)을 사용합니다:   팀 수 = ceil(n / team_size)로 계산합니다.   가장 희귀한 역할을 먼저 각 팀에 하나씩 배정한 후(seed), 남은 학생들은 추가 시 팀을 가장 크게 개선할 수 있는 곳에 그리디 방식으로 배정합니다(가능한 한 하드 제약 조건을 준수함).   각 팀은 교수가 설정한 1~5점 가중치를 바탕으로 4가지 축을 혼합하여 0~100점의 조화도 점수(fit score)를 받습니다:   major — 전공 다양성 (또는 same_major 하드 제약 조건이 켜져 있을 경우 동일성)   role — 서로 다른 역할의 충족도   time — 가용한 일정 슬롯의 겹침 정도   trait — 팀원 간 작업 스타일(성향)의 유사도   이것은 정확한 최적화 알고리즘이 아니라 휴리스틱 탐색으로, 설명 가능하고 좋은 팀을 빠르게 구성해 줍니다. 만약 나중에 수학적으로 완벽한 최적의 배정이 필요하다면, API나 DB 계층을 건드릴 필요 없이 이 모듈 하나만 ILP(정수계획법)/제약 조건 솔버(solver)로 교체하면 됩니다. 


---

## 코드 파일별 기능 설명

각 파일이 실제로 어떤 역할을 하는지 정리한 것입니다. 위쪽 "폴더 구조"의 한 줄 요약을 더 자세히 풀어 쓴 내용입니다.

### 앱 기반 (app/)

#### `app/config.py` — 환경설정
- `.env` 파일에서 설정값을 읽어오는 `Settings` 클래스를 정의합니다. (pydantic-settings 사용)
- 관리하는 값: `database_url`(DB 접속 주소), `jwt_secret`/`jwt_algorithm`/`access_token_expire_minutes`(토큰 발급 설정), `cors_origins`(프론트엔드 허용 출처).
- `get_settings()`는 `@lru_cache`로 감싸져 있어 설정을 한 번만 읽고 재사용합니다.

#### `app/database.py` — DB 연결
- SQLAlchemy 엔진과 세션 팩토리(`SessionLocal`)를 생성합니다.
- 모든 ORM 모델이 상속하는 `Base` 클래스를 정의합니다.
- `get_db()`는 FastAPI 의존성으로, 요청마다 DB 세션을 열고 끝나면 닫아줍니다.

#### `app/models.py` — 데이터 모델 (ORM)
- `db/schema.sql`의 테이블과 1:1로 대응하는 SQLAlchemy 모델들을 정의합니다.
- 주요 모델: `User`(학생·교수 공용), `Class`(수업), `Enrollment`(수강), `SurveyResponse`(설문 응답), `SurveySkill`(스킬), `SurveyAvailability`(가용 시간), `MatchPreset`(프리셋), `MatchRun`(매칭 실행 기록), `Team`(팀), `TeamMember`(팀원).
- 테이블 간 관계(relationship)와 제약조건(체크, 유니크)도 여기서 선언합니다.

#### `app/security.py` — 인증·보안
- 비밀번호 해싱/검증: `hash_password()`, `verify_password()` (bcrypt).
- JWT 토큰 발급: `create_access_token()`.
- 인증 의존성: `get_current_user()`(토큰 → 사용자), `require_professor()`/`require_student()`(역할별 접근 제한). 이 부분이 학생과 교수의 권한 경계를 실제로 강제하는 지점입니다.

#### `app/schemas.py` — 요청/응답 형식 (Pydantic)
- API가 주고받는 데이터의 형태와 유효성 규칙을 정의합니다.
- 예: `SignupRequest`, `TokenResponse`, `ClassCreate`, `SurveySubmit`, `MatchRequest`, `MatchResultOut` 등.
- 가중치는 1~5, 성향/스킬 레벨 범위 등 입력 검증이 여기서 자동으로 이뤄집니다.

#### `app/matching.py` — 팀 매칭 엔진 (핵심 로직)
- DB에 의존하지 않는 순수 함수 모듈이라 단독으로 테스트할 수 있습니다.
- `Candidate`/`Weights`/`Hard` 등 입력용 데이터 구조와, 팀을 구성하는 `form_teams()`를 제공합니다.
- 조화도 점수 계산 함수: `_major_score`(전공), `_role_score`(역할), `_time_score`(일정), `_trait_score`(성향)를 가중치로 합산하는 `team_fit()`.
- `assign_roles()`는 팀원 각자에게 서로 겹치지 않는 역할을 배정합니다.

#### `app/main.py` — 앱 진입점
- FastAPI 앱을 생성하고 CORS 미들웨어를 설정합니다.
- 라우터 4개(auth, classes, surveys, matching)를 앱에 연결합니다.
- 상태 확인용 `GET /health` 엔드포인트를 제공합니다.

### 라우터 (app/routers/)

#### `routers/auth.py` — 인증
- `POST /api/auth/signup`: 회원가입(학생/교수). 이메일 중복·학번 누락을 검사하고 가입 후 토큰을 발급합니다.
- `POST /api/auth/login`: 로그인 후 JWT 토큰 발급.
- `GET /api/auth/me`: 현재 로그인한 사용자 정보 조회.

#### `routers/classes.py` — 수업·수강
- `POST /api/classes`: 교수가 수업 생성(참여 코드 자동 생성).
- `GET /api/classes`: 교수는 자기 수업, 학생은 수강 중인 수업 목록 조회.
- `GET /api/classes/{id}/roster`: 교수용 수강생 명단 + 설문 제출 현황.
- `POST /api/classes/join`: 학생이 참여 코드로 수업에 등록(중복 참여 방지).

#### `routers/surveys.py` — 설문
- `PUT /api/classes/{id}/survey`: 수업별 설문 제출/수정(역할·스킬·성향·가용시간·매칭 준비 여부). 스킬과 가용시간은 전체 교체 방식으로 저장합니다.
- `GET /api/classes/{id}/survey`: 본인이 제출한 설문 조회.

#### `routers/matching.py` — 매칭
- `POST /api/classes/{id}/match`: 매칭 준비된 설문들을 모아 엔진을 실행하고, 결과를 `match_runs`/`teams`/`team_members`에 저장합니다. (교수 전용)
- `GET /api/presets`: 기본 제공 프리셋 + 본인 프리셋 목록 조회.

### 기타

#### `db/schema.sql` / `db/schema.mysql.sql` — DB 스키마
- `schema.sql`: PostgreSQL용 테이블 정의(DDL)와 기본 프리셋(ps0~ps4) 시드 데이터.
- `schema.mysql.sql`: 같은 스키마의 MySQL 8.0+ 버전. UUID는 `CHAR(36)`, 배열 대신 `survey_roles` 테이블, 인라인 `ENUM` 사용 등 MySQL 문법에 맞춰 이식한 것입니다. (현재 앱 코드는 PostgreSQL 기준이라, MySQL로 실제 구동하려면 모델·드라이버 수정이 추가로 필요합니다.)

#### `tests/test_matching.py` — 매칭 엔진 단위 테스트
- DB 없이 순수하게 매칭 엔진만 검증합니다: 팀 수·배정 정확성, 점수 범위(0~100), `same_major`/역할 가중치 동작, 빈 후보 처리 등.

#### `requirements.txt` / `.env.example`
- `requirements.txt`: 필요한 파이썬 패키지 목록(FastAPI, SQLAlchemy, psycopg, JWT/bcrypt 등).
- `.env.example`: 환경변수 예시 파일. 복사해서 `.env`로 만든 뒤 값을 채웁니다.
