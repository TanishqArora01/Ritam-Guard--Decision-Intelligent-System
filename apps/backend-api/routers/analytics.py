"""routers/analytics.py — Analytics endpoints backed by ClickHouse."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth.rbac import require_ops, require_any, get_current_user
from db.clickhouse import ch_query
from db.postgres import User, UserRole

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
async def overview(current_user: User = Depends(require_any)):
    """KPI tiles for the dashboard: total decisions, fraud rate, avg latency, action counts."""
    rows = ch_query("""
        SELECT
            count()                                          AS total_decisions,
            countIf(action = 'BLOCK')                        AS blocked,
            countIf(action = 'APPROVE')                      AS approved,
            countIf(action = 'STEP_UP_AUTH')                 AS step_up,
            countIf(action = 'MANUAL_REVIEW')                AS manual_review,
            round(avg(p_fraud), 4)                           AS avg_p_fraud,
            round(countIf(action='BLOCK')/count()*100, 2)    AS block_rate_pct,
            round(avg(latency_ms), 1)                        AS avg_latency_ms,
            round(quantile(0.95)(latency_ms), 1)             AS p95_latency_ms
        FROM fraud_analytics.decisions
        WHERE decided_at >= now() - INTERVAL 24 HOUR
    """)
    if not rows:
        return {
            "total_decisions": 0, "blocked": 0, "approved": 0,
            "step_up": 0, "manual_review": 0,
            "avg_p_fraud": 0, "block_rate_pct": 0,
            "avg_latency_ms": 0, "p95_latency_ms": 0,
        }
    return rows[0]


@router.get("/fraud-rate")
async def fraud_rate_trend(
    hours:        int           = Query(24, ge=1, le=168),
    granularity:  str           = Query("hour", regex="^(minute|hour|day)$"),
    current_user: User          = Depends(require_any),
):
    """Fraud rate (block %) over time — for the time series chart."""
    trunc_map = {"minute": "toStartOfMinute", "hour": "toStartOfHour", "day": "toStartOfDay"}
    trunc_fn  = trunc_map.get(granularity, "toStartOfHour")

    rows = ch_query(f"""
        SELECT
            {trunc_fn}(decided_at)                           AS bucket,
            count()                                          AS total,
            countIf(action = 'BLOCK')                        AS blocked,
            countIf(action = 'APPROVE')                      AS approved,
            countIf(action = 'STEP_UP_AUTH')                 AS step_up,
            countIf(action = 'MANUAL_REVIEW')                AS manual_review,
            round(countIf(action='BLOCK')/count()*100, 2)    AS block_rate_pct,
            round(avg(p_fraud), 4)                           AS avg_p_fraud,
            round(avg(latency_ms), 1)                        AS avg_latency_ms
        FROM fraud_analytics.decisions
        WHERE decided_at >= now() - INTERVAL {hours} HOUR
        GROUP BY bucket
        ORDER BY bucket ASC
    """)
    return {"data": rows, "hours": hours, "granularity": granularity}


@router.get("/actions")
async def action_distribution(
    hours:        int  = Query(24, ge=1, le=168),
    current_user: User = Depends(require_any),
):
    """Action distribution breakdown for pie/donut chart."""
    rows = ch_query(f"""
        SELECT action, count() AS count,
               round(count()/sum(count()) over ()*100, 1) AS pct
        FROM fraud_analytics.decisions
        WHERE decided_at >= now() - INTERVAL {hours} HOUR
        GROUP BY action
        ORDER BY count DESC
    """)
    return {"data": rows, "hours": hours}


@router.get("/latency")
async def latency_percentiles(
    hours:        int  = Query(1, ge=1, le=24),
    current_user: User = Depends(require_any),
):
    """Latency percentile breakdown (p50/p95/p99) by pipeline stage."""
    rows = ch_query(f"""
        SELECT
            round(quantile(0.50)(latency_ms), 1) AS p50,
            round(quantile(0.90)(latency_ms), 1) AS p90,
            round(quantile(0.95)(latency_ms), 1) AS p95,
            round(quantile(0.99)(latency_ms), 1) AS p99,
            round(avg(latency_ms), 1)             AS avg,
            min(latency_ms)                       AS min,
            max(latency_ms)                       AS max,
            count()                               AS total
        FROM fraud_analytics.decisions
        WHERE decided_at >= now() - INTERVAL {hours} HOUR
    """)
    return rows[0] if rows else {}


@router.get("/top-risk")
async def top_risk_transactions(
    hours:        int  = Query(1, ge=1, le=24),
    limit:        int  = Query(10, ge=1, le=50),
    current_user: User = Depends(require_any),
):
    """Highest P(fraud) transactions in the last N hours."""
    # BANK_PARTNER scoping
    org_filter = ""
    if current_user.role == UserRole.BANK_PARTNER and current_user.org_id:
        org_filter = f"AND customer_id LIKE '{current_user.org_id}%'"

    rows = ch_query(f"""
        SELECT txn_id, customer_id, amount, currency, action,
               p_fraud, graph_risk_score, anomaly_score, latency_ms, decided_at
        FROM fraud_analytics.decisions
        WHERE decided_at >= now() - INTERVAL {hours} HOUR
          {org_filter}
        ORDER BY p_fraud DESC
        LIMIT {limit}
    """)
    return {"data": rows}


@router.get("/ab-comparison")
async def ab_comparison(
    hours:        int  = Query(24, ge=1, le=168),
    current_user: User = Depends(require_ops),   # ops + admin only
):
    """A/B experiment comparison: control vs treatment action rates."""
    rows = ch_query(f"""
        SELECT
            ab_variant,
            count()                                         AS total,
            countIf(action='BLOCK')                         AS blocked,
            countIf(action='APPROVE')                       AS approved,
            countIf(action='STEP_UP_AUTH')                  AS step_up,
            round(countIf(action='BLOCK')/count()*100, 2)   AS block_rate_pct,
            round(avg(p_fraud), 4)                          AS avg_p_fraud,
            round(avg(latency_ms), 1)                       AS avg_latency_ms
        FROM fraud_analytics.decisions
        WHERE decided_at >= now() - INTERVAL {hours} HOUR
          AND ab_variant != ''
        GROUP BY ab_variant
        ORDER BY ab_variant
    """)
    return {"data": rows, "hours": hours}
