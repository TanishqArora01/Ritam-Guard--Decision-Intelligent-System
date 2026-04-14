"""routers/users.py — User + API key management (ADMIN only)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt_handler import hash_password
from auth.rbac import require_admin, get_current_user
from db.postgres import APIKey, User, UserRole, get_db

router = APIRouter(tags=["Users & API Keys"])


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    username: str
    email:    str
    password: str
    role:     UserRole
    org_id:   Optional[str] = None


class UpdateUserRequest(BaseModel):
    role:      Optional[UserRole] = None
    is_active: Optional[bool]     = None
    org_id:    Optional[str]      = None


@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users  = result.scalars().all()
    return [
        {
            "id":           u.id,
            "username":     u.username,
            "email":        u.email,
            "role":         u.role,
            "org_id":       u.org_id,
            "is_active":    u.is_active,
            "created_at":   u.created_at.isoformat() if u.created_at else "",
            "last_login_at":u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in users
    ]


@router.post("/users", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
async def create_user(req: CreateUserRequest, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(User.username == req.username))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Username already taken")

    user = User(
        username        = req.username,
        email           = req.email,
        hashed_password = hash_password(req.password),
        role            = req.role,
        org_id          = req.org_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.patch("/users/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(user_id: str, req: UpdateUserRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if req.role      is not None: user.role      = req.role
    if req.is_active is not None: user.is_active = req.is_active
    if req.org_id    is not None: user.org_id    = req.org_id
    await db.commit()
    return {"id": user.id, "username": user.username, "role": user.role, "is_active": user.is_active}


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class CreateAPIKeyRequest(BaseModel):
    name: str


@router.get("/api-keys")
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Users see their own keys; ADMINs see all."""
    if current_user.role == UserRole.ADMIN:
        result = await db.execute(select(APIKey).order_by(APIKey.created_at.desc()))
    else:
        result = await db.execute(
            select(APIKey).where(APIKey.user_id == current_user.id)
            .order_by(APIKey.created_at.desc())
        )
    keys = result.scalars().all()
    return [
        {
            "id":          k.id,
            "name":        k.name,
            "is_active":   k.is_active,
            "created_at":  k.created_at.isoformat() if k.created_at else "",
            "last_used_at":k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    req:          CreateAPIKeyRequest,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    raw_key  = f"fdk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    key_obj = APIKey(user_id=current_user.id, key_hash=key_hash, name=req.name)
    db.add(key_obj)
    await db.commit()
    # Return raw key ONCE — never stored again
    return {"id": key_obj.id, "name": req.name, "key": raw_key,
            "warning": "Store this key safely — it will not be shown again"}


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id:       str,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    key    = result.scalar_one_or_none()
    if not key:
        raise HTTPException(404, "Key not found")
    if key.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(403, "Not your key")
    key.is_active = False
    await db.commit()
