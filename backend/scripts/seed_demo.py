"""시연용 45명 학생 및 설문 데이터 자동 생성 스크립트.

실행 방법:
    docker compose exec backend python -m scripts.seed_demo
    (또는 로컬 환경: python -m scripts.seed_demo)
"""

import datetime as dt
import random
from sqlalchemy import select
from sqlalchemy.orm import Session

# 기존 임포트에 Base 추가 및 app.models 전체 임포트
import app.models  # noqa: F401 (모델들이 Base.metadata에 등록되도록 실행)
from app.models import (
    Class,
    Enrollment,
    SurveyAvailability,
    SurveyResponse,
    SurveySkill,
    User,
)

from app.database import Base, engine
from app.security import hash_password

# 1. 한국어 이름 및 기본 데이터 풀
LAST_NAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권"]
FIRST_NAMES = [
    "민준", "서연", "도현", "지우", "현우", "예은", "건우", "하은", "우진", "수아",
    "지훈", "유진", "준서", "채원", "도윤", "지민", "성민", "다은", "승우", "은지",
    "재원", "소율", "태현", "아린", "시우", "나은", "주원", "서현", "연우", "민서"
]

MAJORS = [
    "컴퓨터공학과", "인공지능학과", "소프트웨어학과", 
    "데이터사이언스학과", "경영학과", "산업디자인학과", "정보통신공학과"
]

# 기존 (수정 전)
# ROLES_POOL = ["PM", "Frontend", "Backend", "AI/ML", "UI/UX", "Data"]

# 변경 (수정 후: 프론트엔드 및 v2 엔진 규격 통일)
ROLES_POOL = ["기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표"]

# 기존 역할 태그(ROLES_POOL) 규격에 맞춰 키값 한글화
SKILLS_POOL = {
    "기획": ["Jira", "Notion", "커뮤니케이션", "일정 관리", "서비스 기획"],
    "프론트엔드": ["React", "TypeScript", "Next.js", "Vue.js", "CSS/Tailwind"],
    "백엔드": ["FastAPI", "Python", "Node.js", "PostgreSQL", "Docker", "Java/Spring"],
    "데이터": ["SQL", "Pandas", "PyTorch", "Scikit-Learn", "Tableau", "데이터 분석"],
    "디자인": ["Figma", "Adobe XD", "와이어프레임", "UI 디자인", "사용자 조사"],
    "발표": ["PPT 작성", "프레젠테이션", "스피치", "자료 구조화", "커뮤니케이션"]
}


def generate_unique_name(existing_names: set) -> str:
    while True:
        name = random.choice(LAST_NAMES) + random.choice(FIRST_NAMES)
        if name not in existing_names:
            existing_names.add(name)
            return name


def run_seed():
    with Session(engine) as db:
        Base.metadata.create_all(bind=engine)
        print("🌱 [Seed] 시연용 데이터 시딩 시작...")
        
        # 1) 데모 교수 계정 생성 또는 조회
        prof = db.scalar(select(User).where(User.email == "prof_demo@teammatch.ai"))
        if not prof:
            prof = User(
                role="professor",
                email="prof_demo@teammatch.ai",
                password_hash=hash_password("password123"),
                name="김철수 교수",
                dept="컴퓨터공학부",
                school="한국대학교",
            )
            db.add(prof)
            db.flush()
            print("  ✅ 교수 계정 생성: prof_demo@teammatch.ai")
        else:
            print("  ℹ️ 기존 교수 계정 사용: prof_demo@teammatch.ai")

        # 2) 데모 수업 생성 또는 조회 (45명 수강)
        klass = db.scalar(select(Class).where(Class.join_code == "DEMO45"))
        if not klass:
            klass = Class(
                professor_id=prof.id,
                name="2026 캡스톤디자인 1분반 (시연용)",
                code="CS401-01",
                term="2026-1",
                capacity=50,
                join_code="DEMO45",
                survey_deadline=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=14),
                kind="캡스톤디자인",
                status="설문 진행 중",
            )
            db.add(klass)
            db.flush()
            print("  ✅ 시연용 수업 생성: DEMO45 (캡스톤디자인 1분반)")
        else:
            print("  ℹ️ 기존 시연용 수업 사용: DEMO45")

        # 3) 45명 학생 및 설문 데이터 생성
        created_count = 0
        existing_names = set()

        for i in range(1, 46):
            email = f"student{i:02d}@teammatch.ai"
            student_id_num = f"2024{i:04d}"

            # 기존 학생 확인
            student = db.scalar(select(User).where(User.email == email))
            if not student:
                name = generate_unique_name(existing_names)
                student = User(
                    role="student",
                    email=email,
                    password_hash=hash_password("password123"),
                    name=name,
                    major=random.choice(MAJORS),
                    year=random.randint(2, 4),
                    student_id=student_id_num,
                    bio=f"안녕하세요, {name}입니다. 즐겁게 프로젝트하고 싶습니다!",
                )
                db.add(student)
                db.flush()

            # 수강 등록(Enrollment) 확인
            enrollment = db.scalar(
                select(Enrollment).where(
                    Enrollment.class_id == klass.id,
                    Enrollment.student_id == student.id,
                )
            )

            now = dt.datetime.now(dt.timezone.utc)
            if not enrollment:
                enrollment = Enrollment(
                    class_id=klass.id,
                    student_id=student.id,
                    survey_submitted=True,
                    submitted_at=now,
                )
                db.add(enrollment)
                db.flush()
            else:
                enrollment.survey_submitted = True
                enrollment.submitted_at = now

            # 설문 응답(SurveyResponse) 생성/업데이트
            survey = db.scalar(
                select(SurveyResponse).where(SurveyResponse.enrollment_id == enrollment.id)
            )

            # 희망 역할 1~3개 무작위 선택
            assigned_roles = random.sample(ROLES_POOL, k=random.randint(1, 3))

            if not survey:
                survey = SurveyResponse(
                    enrollment_id=enrollment.id,
                    roles=assigned_roles,
                    trait_pace=random.randint(1, 5),
                    trait_prep=random.randint(1, 5),
                    trait_lead=random.randint(1, 5),
                    trait_comm=random.randint(1, 5),
                    match_ready=True,
                )
                db.add(survey)
                db.flush()
            else:
                survey.roles = assigned_roles
                survey.trait_pace = random.randint(1, 5)
                survey.trait_prep = random.randint(1, 5)
                survey.trait_lead = random.randint(1, 5)
                survey.trait_comm = random.randint(1, 5)
                survey.match_ready = True

            # 스킬(SurveySkill) 주입 (기존 데이터 초기화 후 재추가)
            db.query(SurveySkill).filter(SurveySkill.survey_id == survey.id).delete()
            
            # 선택한 역할 기반 스킬 2~4개 선택
            skill_candidates = []
            for role in assigned_roles:
                skill_candidates.extend(SKILLS_POOL.get(role, []))
            
            selected_skills = random.sample(
                list(set(skill_candidates)), k=min(len(set(skill_candidates)), random.randint(2, 4))
            )

            for s_name in selected_skills:
                db.add(
                    SurveySkill(
                        survey_id=survey.id,
                        name=s_name,
                        level=random.randint(2, 5),
                    )
                )

            # 가능 시간대(SurveyAvailability) 주입 (월~일, 0~3블록)
            db.query(SurveyAvailability).filter(SurveyAvailability.survey_id == survey.id).delete()
            for day in range(7):  # 0=월 ~ 6=일
                for block in range(12):  # 프론트엔드 12개 시간대 블록 규격에 맞춤(09시~21시)
                    # 약 70% 확률로 가능(y), 30% 확률로 불가능(n)
                    is_available = "y" if random.random() < 0.7 else "n"
                    db.add(
                        SurveyAvailability(
                            survey_id=survey.id,
                            day=day,
                            block=block,
                            state=is_available,
                        )
                    )

            created_count += 1

        db.commit()
        print(f"🎉 [Complete] {created_count}명의 시연용 학생/설문 데이터 주입 완료!")
        print("\n🔑 테스트용 접속 계정 정보:")
        print("  - 교수 계정: prof_demo@teammatch.ai / password123 (수업 코드: DEMO45)")
        print("  - 학생 계정: student01@teammatch.ai ~ student45@teammatch.ai / password123")


if __name__ == "__main__":
    run_seed()