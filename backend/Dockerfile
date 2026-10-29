# 1. 파이썬 3.13 베이스 이미지 사용
FROM python:3.13-slim

# 2. 컨테이너 내 작업 디렉터리 설정
WORKDIR /app

# 3. 필수 시스템 패키지 설치 (PostgreSQL 연결 관련 컴파일용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. 의존성 파일 복사 및 설치 (캐시 활용을 위해 우선 복사)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 5. 백엔드 소스코드 전체 복사
COPY . .

# 6. 외부 공개 포트 지정
EXPOSE 8000

# 7. Uvicorn 서버 실행 (0.0.0.0으로 열어야 컨테이너 외부에서 접속 가능)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]