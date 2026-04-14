"""
app-backend/main.py
Fraud Detection — Application Backend (BFF)

Sits between the Next.js frontend and the ML pipeline services.
Owns: auth, RBAC, review queue, analytics reads, SSE live feed.
Does NOT own: ML inference (that stays in the API Gateway).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import config
from db.postgres import init_db, AsyncSessionLocal, User, UserRole
from auth.jwt_handler import hash_password
from routers import auth, decisions, review_queue, analytics, users

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("app-backend")


# ---------------------------------------------------------------------------
# Seed users
# ---------------------------------------------------------------------------

SEED_USERS = [
    ("admin",    "admin2024!",   "admin@frauddetect.io",   UserRole.ADMIN),
    ("analyst1", "analyst2024!", "analyst1@frauddetect.io",UserRole.ANALYST),
    ("ops1",     "ops2024!",     "ops1@frauddetect.io",    UserRole.OPS_MANAGER),
    ("partner1", "partner2024!", "partner1@bank.example",  UserRole.BANK_PARTNER),
]


async def seed_users():
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        for username, password, email, role in SEED_USERS:
            existing = (
                await db.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if existing:
                existing.email = email
                existing.hashed_password = hash_password(password)
                existing.role = role
                existing.org_id = "bank-example" if role == UserRole.BANK_PARTNER else None
                existing.is_active = True
            else:
                db.add(User(
                    username        = username,
                    email           = email,
                    hashed_password = hash_password(password),
                    role            = role,
                    org_id          = "bank-example" if role == UserRole.BANK_PARTNER else None,
                    is_active       = True,
                ))
        await db.commit()
    logger.info("Seed users ready")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 55)
    logger.info("Fraud Detection — Application Backend")
    logger.info("  Port:     %d", config.port)
    logger.info("  Postgres: %s", config.postgres_dsn.split("@")[-1])
    logger.info("  Gateway:  %s", config.gateway_url)
    logger.info("=" * 55)

    await init_db()
    await seed_users()
    logger.info("App backend ready.")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title       = "Fraud Detection — App Backend",
    description = (
        "BFF for the fraud detection portal. "
        "Handles auth (JWT + API keys), review queue case management, "
        "analytics reads (ClickHouse), and SSE decision stream."
    ),
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = config.cors_origins,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(auth.router)
app.include_router(decisions.router)
app.include_router(review_queue.router)
app.include_router(analytics.router)
app.include_router(users.router)


@app.get("/")
async def root():
    return {
        "service": "app-backend",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "app-backend", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.host, port=config.port,
                reload=config.debug, log_level=config.log_level.lower())
