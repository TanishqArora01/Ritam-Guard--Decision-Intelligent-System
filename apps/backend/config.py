"""config.py — App Backend BFF configuration."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class AppConfig:
    # Service
    host:    str = os.getenv("HOST", "0.0.0.0")
    port:    int = int(os.getenv("PORT", "8400"))
    debug:   bool = os.getenv("DEBUG", "false").lower() == "true"
    disable_db_init: bool = os.getenv("DISABLE_DB_INIT", "false").lower() == "true"

    # PostgreSQL (decisions + users + review queue)
    postgres_dsn: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql+asyncpg://fraud_admin:fraud_secret_2024@postgres:5432/fraud_db"
    )

    # ClickHouse (analytics)
    clickhouse_host:     str = os.getenv("CLICKHOUSE_HOST",     "clickhouse")
    clickhouse_port:     int = int(os.getenv("CLICKHOUSE_PORT", "9000"))
    clickhouse_user:     str = os.getenv("CLICKHOUSE_USER",     "default")
    clickhouse_password: str = os.getenv("CLICKHOUSE_PASSWORD", "")
    clickhouse_db:       str = os.getenv("CLICKHOUSE_DB",       "fraud_analytics")

    # ML API Gateway (BFF proxies score requests)
    gateway_url: str = os.getenv("GATEWAY_URL", "http://api-gateway:8000")

    # JWT
    jwt_secret:    str = os.getenv("JWT_SECRET",    "change-me-in-production-fraud2024!")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes:         int = int(os.getenv("JWT_EXPIRE_MINUTES",         "60"))
    jwt_refresh_expire_minutes: int = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "10080"))  # 7 days

    # CORS — origins allowed to call the BFF
    cors_origins: List[str] = field(default_factory=lambda: [
        o.strip() for o in os.getenv(
            "CORS_ORIGINS",
            "*"
        ).split(",")
    ])

    # SSE live feed
    sse_keepalive_seconds: int = int(os.getenv("SSE_KEEPALIVE", "15"))
    sse_max_events:        int = int(os.getenv("SSE_MAX_EVENTS", "500"))

    # Seed admin credentials
    seed_admin_user: str = os.getenv("SEED_ADMIN_USER",     "admin")
    seed_admin_pass: str = os.getenv("SEED_ADMIN_PASSWORD", "admin2024!")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")


config = AppConfig()
