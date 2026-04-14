"""auth/rbac.py — Role-based access control dependencies."""
from __future__ import annotations

import hashlib
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt_handler import decode_token
from db.postgres import User, UserRole, APIKey, get_db

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ---------------------------------------------------------------------------
# Current user resolution
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve caller from JWT Bearer token OR X-API-Key header."""

    # --- JWT path ---
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload and payload.get("type") == "access":
            user_id = payload.get("sub")
            result  = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
            user    = result.scalar_one_or_none()
            if user:
                return user

    # --- API Key path ---
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        result   = await db.execute(
            select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True)
        )
        key_obj = result.scalar_one_or_none()
        if key_obj:
            result2 = await db.execute(select(User).where(User.id == key_obj.user_id, User.is_active == True))
            user    = result2.scalar_one_or_none()
            if user:
                return user

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


# ---------------------------------------------------------------------------
# Role guards — use as FastAPI dependencies
# ---------------------------------------------------------------------------

def require_roles(*roles: UserRole):
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role} not permitted for this action",
            )
        return current_user
    return _check


# Convenience shortcuts
require_analyst     = require_roles(UserRole.ANALYST, UserRole.OPS_MANAGER, UserRole.ADMIN)
require_ops         = require_roles(UserRole.OPS_MANAGER, UserRole.ADMIN)
require_admin       = require_roles(UserRole.ADMIN)
require_any         = require_roles(*list(UserRole))   # any authenticated user
