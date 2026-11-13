/* 프론트 실행 설정
   · API_BASE : 백엔드(FastAPI) 주소. 로컬 개발 기본값은 8000 포트
   · ENGINE   : "auto"  → http(s)로 열었을 때만 서버 AI 엔진을 쓰고, 안 되면 로컬 계산으로 대체
                "server"→ 서버 엔진 우선 (실패하면 로컬로 대체)
                "local" → 항상 브라우저 안의 로컬 계산
   주소창에 ?engine=local 또는 ?engine=server 를 붙이면 이 값을 덮어쓴다. */
window.TM_CONFIG = { API_BASE: "http://localhost:8000", ENGINE: "auto", TIMEOUT_MS: 30000 };
