"""db/postgres.py — SQLAlchemy async engine + ORM models."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    String, Text, Float, Integer, text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from config import config


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
engine = create_async_engine(
    config.postgres_dsn,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=config.debug,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    ANALYST      = "ANALYST"
    OPS_MANAGER  = "OPS_MANAGER"
    ADMIN        = "ADMIN"
    BANK_PARTNER = "BANK_PARTNER"


class CaseStatus(str, enum.Enum):
    OPEN       = "OPEN"
    IN_REVIEW  = "IN_REVIEW"
    RESOLVED   = "RESOLVED"
    ESCALATED  = "ESCALATED"


class CaseVerdict(str, enum.Enum):
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"
    FALSE_POSITIVE  = "FALSE_POSITIVE"
    INCONCLUSIVE    = "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "app_users"
    __table_args__ = {"schema": "app"}

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username      = Column(String(64), unique=True, nullable=False, index=True)
    email         = Column(String(128), unique=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    role          = Column(Enum(UserRole), nullable=False, default=UserRole.ANALYST)
    org_id        = Column(String(64), nullable=True)   # for BANK_PARTNER scoping
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    api_keys  = relationship("APIKey",    back_populates="user", cascade="all, delete")
    cases     = relationship("ReviewCase", back_populates="assigned_to_user",
                             foreign_keys="ReviewCase.assigned_to")


class APIKey(Base):
    __tablename__ = "app_api_keys"
    __table_args__ = {"schema": "app"}

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String(36), ForeignKey("app.app_users.id"), nullable=False)
    key_hash    = Column(String(128), unique=True, nullable=False)
    name        = Column(String(64), nullable=False)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True),
                          default=lambda: datetime.now(timezone.utc))
    last_used_at= Column(DateTime(timezone=True), nullable=True)
    expires_at  = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")


class ReviewCase(Base):
    """Every MANUAL_REVIEW decision creates a ReviewCase row."""
    __tablename__ = "app_review_cases"
    __table_args__ = {"schema": "app"}

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    txn_id       = Column(String(64), nullable=False, index=True)
    customer_id  = Column(String(64), nullable=False, index=True)
    amount       = Column(Float, nullable=False)
    currency     = Column(String(8), default="USD")
    channel      = Column(String(32), default="")
    country_code = Column(String(8),  default="")

    # ML signals at decision time
    p_fraud          = Column(Float, default=0.0)
    confidence       = Column(Float, default=0.0)
    graph_risk_score = Column(Float, default=0.0)
    anomaly_score    = Column(Float, default=0.0)
    model_action     = Column(String(32), default="MANUAL_REVIEW")
    model_version    = Column(String(64), default="")
    explanation      = Column(Text, default="{}")

    # Case management
    status      = Column(Enum(CaseStatus),  default=CaseStatus.OPEN, nullable=False, index=True)
    priority    = Column(Integer, default=2)   # 1=HIGH 2=MEDIUM 3=LOW
    assigned_to = Column(String(36), ForeignKey("app.app_users.id"), nullable=True, index=True)
    verdict     = Column(Enum(CaseVerdict), nullable=True)
    analyst_notes = Column(Text, default="")

    created_at  = Column(DateTime(timezone=True),
                          default=lambda: datetime.now(timezone.utc), index=True)
    updated_at  = Column(DateTime(timezone=True),
                          default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    assigned_to_user = relationship("User", back_populates="cases",
                                    foreign_keys=[assigned_to])


# ---------------------------------------------------------------------------
# DDL helper — create app schema + tables
# ---------------------------------------------------------------------------
async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
        await conn.run_sync(Base.metadata.create_all)
