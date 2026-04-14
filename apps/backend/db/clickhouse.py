"""db/clickhouse.py — ClickHouse async client wrapper."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_client = None


def get_ch_client():
    global _client
    if _client is None:
        try:
            from clickhouse_driver import Client
            from config import config
            _client = Client(
                host=config.clickhouse_host,
                port=config.clickhouse_port,
                user=config.clickhouse_user,
                password=config.clickhouse_password,
                database=config.clickhouse_db,
                connect_timeout=5,
                send_receive_timeout=30,
            )
        except Exception as e:
            logger.warning("ClickHouse unavailable: %s", e)
    return _client


def ch_query(sql: str, params: Optional[Dict] = None) -> List[Dict]:
    """Execute a ClickHouse query and return list of dicts."""
    client = get_ch_client()
    if not client:
        return []
    try:
        result = client.execute(sql, params or {}, with_column_types=True)
        rows, columns = result[0] if result else ([], [])
        col_names = [c[0] for c in columns]
        return [dict(zip(col_names, row)) for row in rows]
    except Exception as e:
        logger.error("ClickHouse query failed: %s | sql=%s", e, sql[:120])
        return []
