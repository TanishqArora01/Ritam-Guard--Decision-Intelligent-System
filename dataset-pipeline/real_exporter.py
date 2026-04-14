"""
dataset-pipeline/real_exporter.py
Real Data Exporter

Pulls production decisions from PostgreSQL + ClickHouse,
applies anonymisation, and exports curated Parquet + CSV files.

Pipeline:
  1. Pull decisions from decisions.records (PostgreSQL)
  2. Pull analytics enrichment from fraud_analytics.decisions (ClickHouse)
  3. Join on txn_id
  4. Apply anonymiser (customer_id SHA-256, IP mask, etc.)
  5. Join analyst verdicts from app.app_review_cases
  6. Export: real_decisions.parquet + real_decisions.csv

Note: Only exports decisions older than 24h to ensure all chargeback
labels have had time to arrive (reduces label noise).
"""
from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple

from config import config
from anonymiser import Anonymiser

logger = logging.getLogger(__name__)


def _pg_connect():
    try:
        import psycopg2
        import psycopg2.extras
        dsn = config.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
        return psycopg2.connect(dsn)
    except Exception as e:
        logger.warning("PostgreSQL unavailable: %s", e)
        return None


def _ch_client():
    try:
        from clickhouse_driver import Client
        return Client(
            host     = config.clickhouse_host,
            port     = config.clickhouse_port,
            user     = config.clickhouse_user,
            password = config.clickhouse_password,
            database = config.clickhouse_db,
        )
    except Exception as e:
        logger.warning("ClickHouse unavailable: %s", e)
        return None


def _fetch_decisions_pg(since: datetime, until: datetime, limit: int) -> List[Dict]:
    """Pull core decision records from PostgreSQL."""
    conn = _pg_connect()
    if not conn:
        return []
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                txn_id, customer_id, action, p_fraud, uncertainty,
                graph_risk_score, anomaly_score, clv_at_decision,
                trust_score, expected_loss, expected_friction,
                expected_review_cost, latency_ms, model_version,
                ab_experiment_id, ab_variant, decided_at
            FROM decisions.records
            WHERE decided_at BETWEEN %(since)s AND %(until)s
            ORDER BY decided_at DESC
            LIMIT %(limit)s
        """, {"since": since, "until": until, "limit": limit})
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        logger.info("PostgreSQL: fetched %d decision rows", len(rows))
        return rows
    except Exception as e:
        logger.error("PG fetch failed: %s", e)
        conn.close()
        return []


def _fetch_verdicts_pg() -> Dict[str, Dict]:
    """Fetch analyst verdicts from review queue."""
    conn = _pg_connect()
    if not conn:
        return {}
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT txn_id, verdict, status, resolved_at
            FROM app.app_review_cases
            WHERE verdict IS NOT NULL
        """)
        rows = {r["txn_id"]: dict(r) for r in cur.fetchall()}
        conn.close()
        logger.info("PostgreSQL: fetched %d analyst verdicts", len(rows))
        return rows
    except Exception as e:
        logger.warning("Verdict fetch failed (app schema may not exist yet): %s", e)
        if conn: conn.close()
        return {}


def _fetch_chargebacks_pg() -> Dict[str, bool]:
    """Map txn_id → is_fraud based on chargebacks."""
    conn = _pg_connect()
    if not conn:
        return {}
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT txn_id FROM audit.chargebacks")
        result = {r["txn_id"]: True for r in cur.fetchall()}
        conn.close()
        logger.info("PostgreSQL: fetched %d chargeback labels", len(result))
        return result
    except Exception as e:
        logger.warning("Chargeback fetch failed: %s", e)
        if conn: conn.close()
        return {}


def export_real(output_dir: str) -> Tuple[Dict[str, str], List[Dict]]:
    """
    Export real anonymised decisions.
    Returns (paths_dict, rows_list).
    """
    until = datetime.now(timezone.utc) - timedelta(hours=24)
    since = until - timedelta(days=config.real_export_days)

    logger.info("Exporting real decisions: %s → %s (max %d rows)",
                since.date(), until.date(), config.real_max_rows)

    rows      = _fetch_decisions_pg(since, until, config.real_max_rows)
    verdicts  = _fetch_verdicts_pg()
    chargebacks = _fetch_chargebacks_pg()

    if not rows:
        logger.warning("No real decision rows found — PostgreSQL may be empty")
        return {}, []

    # Enrich with labels (priority: chargeback > analyst verdict > unlabeled)
    for r in rows:
        txn_id = r.get("txn_id", "")
        r["confidence"] = round(1.0 - float(r.pop("uncertainty", 0) or 0), 4)
        r["optimal_cost_usd"] = float(r.pop("expected_loss", 0) or 0)

        if txn_id in chargebacks:
            r["is_fraud"]     = True
            r["label_source"] = "CHARGEBACK"
        elif txn_id in verdicts:
            v = verdicts[txn_id]
            r["is_fraud"]     = v["verdict"] == "CONFIRMED_FRAUD"
            r["label_source"] = "ANALYST_FRAUD" if r["is_fraud"] else "ANALYST_LEGIT"
        else:
            r["is_fraud"]     = None
            r["label_source"] = None

    # Anonymise
    anon = Anonymiser(config.anon_salt)
    rows = anon.anonymise_batch(rows)

    labeled  = sum(1 for r in rows if r.get("is_fraud") is not None)
    fraud_ct = sum(1 for r in rows if r.get("is_fraud") is True)
    logger.info("Real export: %d rows, %d labeled, %d fraud (%.1f%%)",
                len(rows), labeled, fraud_ct, fraud_ct/max(labeled,1)*100)

    os.makedirs(output_dir, exist_ok=True)
    paths: Dict[str, str] = {}

    # Parquet
    parquet_path = os.path.join(output_dir, "real_decisions.parquet")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, parquet_path, compression="snappy")
        paths["real_parquet"] = parquet_path
        logger.info("Real Parquet written: %s (%d KB)",
                    parquet_path, os.path.getsize(parquet_path)//1024)
    except ImportError:
        logger.warning("pyarrow not available — skipping Parquet")

    # CSV
    csv_path = os.path.join(output_dir, "real_decisions.csv")
    if rows:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        paths["real_csv"] = csv_path

    return paths, rows
