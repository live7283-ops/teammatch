"""Password hashing + JWT issuing/verification + auth dependencies."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import Class, User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    settings = get_settings()
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="자격 증명을 확인할 수 없습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            raise cred_exc
    except JWTError:
        raise cred_exc

    user = db.scalar(select(User).where(User.id == uuid.UUID(user_id)))
    if user is None:
        raise cred_exc
    # soft delete: 비활성(탈퇴) 계정은 유효한 토큰이어도 거부한다.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="탈퇴한 계정입니다.",
        )
    return user


def require_professor(user: User = Depends(get_current_user)) -> User:
    if user.role != "professor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="교수 권한이 필요합니다.")
    return user


def require_student(user: User = Depends(get_current_user)) -> User:
    if user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="학생 권한이 필요합니다.")
    return user


def get_owned_class(db: Session, class_id: uuid.UUID, prof: User) -> Class:
    """교수 본인이 소유한 수업만 반환하는 공용 소유 확인 함수.

    과목별 접근 제어의 단일 진실 공급원(single source of truth).
    모든 교수용 라우터가 각자 구현하지 않고 이 함수를 재사용한다.

    보안 정책: '존재하지 않는 수업'과 '남의 수업'을 구분하지 않고 404로
    통일한다. 403으로 구분하면 class_id 의 존재 여부가 외부로 노출된다.
    """
    c = db.get(Class, class_id)
    if not c or c.professor_id != prof.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="수업을 찾을 수 없습니다.")
    return c
