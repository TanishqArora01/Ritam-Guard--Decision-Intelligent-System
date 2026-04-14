"""auth/jwt_handler.py — JWT token lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = {**data, "exp": datetime.now(timezone.utc) + expires_delta}
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)


def create_access_token(user_id: str, username: str, role: str) -> str:
    return _create_token(
        {"sub": user_id, "username": username, "role": role, "type": "access"},
        timedelta(minutes=config.jwt_expire_minutes),
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id, "type": "refresh"},
        timedelta(minutes=config.jwt_refresh_expire_minutes),
    )


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algorithm])
    except JWTError:
        return None
