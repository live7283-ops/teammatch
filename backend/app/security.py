"""Password hashing + JWT issuing/verification + auth dependencies."""
from __future__ import annotations

import datetime as dt
import uuid

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import Class, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(raw: str) -> str:
    pwd_bytes = raw.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


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
    c = db.get(Class, class_id)
    if not c or c.professor_id != prof.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="수업을 찾을 수 없습니다.")
    return c