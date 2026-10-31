# 보안 점검 체크리스트 (백엔드1 9번)

현재 백엔드 코드를 기준으로 보안 항목을 점검한 결과입니다.
[v] 되어 있음 · [~] 부분적 · [ ] 안 되어 있음(과제 범위 밖이거나 TODO)

---

## 인증 (Authentication)
- [v] 비밀번호 평문 저장 안 함 — bcrypt 해싱 (security.py: hash_password)
- [v] 로그인 시 비밀번호 검증 (verify_password)
- [v] JWT 토큰 발급 + 만료(exp) 설정 (기본 24시간, config.access_token_expire_minutes)
- [v] 토큰 서명 검증 (jose.jwt.decode, 실패 시 401)
- [v] 탈퇴(비활성) 계정은 로그인·인증에서 차단 (is_active 검사)
- [~] JWT 시크릿키 — config 기본값이 placeholder("change-me-in-production").
      운영 전 반드시 .env 의 JWT_SECRET 를 긴 랜덤값으로 교체할 것.
- [ ] 토큰 갱신(refresh token) 없음 — 만료되면 재로그인. (과제 범위상 허용)
- [ ] 토큰 폐기(로그아웃 시 서버측 무효화) 없음 — stateless JWT 특성. (허용)

## 인가 / 접근 제어 (Authorization)
- [v] 역할 분리 강제 — require_professor / require_student (403)
- [v] 과목별 소유 확인 공용화 — security.get_owned_class
      (없는 수업/남의 수업 모두 404로 통일 → 존재 여부 노출 방지)
- [v] 매칭/결과/팀 조회·수정 모두 담당 교수만 가능하도록 소유 확인 적용
- [v] 확정된 편성은 수정 잠금(409), force 플래그로만 재편성

## 입력 검증 (Input Validation)
- [v] Pydantic 스키마로 타입·범위 검증 (가중치 1~5, team_size 2~8 등)
- [v] 이메일 형식 검증 (EmailStr)
- [v] 비밀번호 최소 길이 8자
- [v] 경로 UUID 형식 검증 (잘못된 형식 → 422)
- [v] 검증 실패 시 일관된 에러 형식 반환 (errors.py)

## 데이터 노출 (Data Exposure)
- [v] 비밀번호 해시는 응답 스키마(UserOut)에 포함 안 됨
- [v] 서버 내부 오류(500) 시 스택/민감정보 미노출 — 로그로만 남김 (errors.py)
- [v] 에러 메시지에 다른 사용자 정보 노출 안 함
- [~] 매칭 후보/결과에 학생 이메일 포함 — 교수만 접근 가능하나,
      필요 최소 정보만 내보내는지 추가 검토 여지 있음

## SQL / 쿼리 안전성
- [v] SQLAlchemy ORM 사용 → SQL 인젝션 방어 (파라미터 바인딩)
- [v] 원시 문자열 쿼리(raw SQL) 없음
- [v] 자주 쓰는 조회에 인덱스 존재 (class_id, run_id, (class_id, created_at) 등)

## 전송 / 인프라 (Transport / Infra)
- [v] CORS 출처 제한 설정 (config.cors_origins) — 와일드카드(*) 아님
- [ ] HTTPS 강제 — 배포 계층(리버스 프록시)에서 처리할 사항. 앱 코드 범위 밖.
- [~] DB 비밀번호 — docker-compose 는 로컬용 기본값(teammatch/teammatch).
      운영 배포 시 반드시 환경변수/시크릿으로 분리.
- [ ] Rate limiting(요청 횟수 제한) 없음 — 과제 범위 밖.

## 자동 테스트로 검증한 항목 (tests/test_api_auth.py)
- [v] 인증 없이 보호 엔드포인트 접근 → 401
- [v] 잘못된 입력(짧은 비번/이메일 형식) → 422
- [v] 에러 응답이 통일 형식({"error":{code,message,detail,path}})

---

## 운영 전 반드시 할 것 (요약)
1. JWT_SECRET 를 긴 랜덤값으로 교체 (.env)
2. DB 비밀번호를 기본값에서 변경 (환경변수/시크릿)
3. HTTPS 적용 (배포 프록시 레벨)
4. (여유되면) rate limiting, refresh token 도입 검토

## 미검증 (환경 제약)
- 실제 HTTP+DB 통합 흐름(가입→매칭→조회→확정)은 PostgreSQL 필요.
  Docker(docker compose up)로 DB를 띄운 뒤 Swagger/통합테스트로 확인 요망.
  (현재 자동 테스트는 DB 불필요한 인증·검증·에러형식 범위까지만 커버)
