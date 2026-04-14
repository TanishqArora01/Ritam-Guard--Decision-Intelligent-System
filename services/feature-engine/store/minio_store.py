"""
store/minio_store.py
Offline Feature Store backed by MinIO (S3-compatible).

Writes hourly Parquet snapshots of the current feature state for:
  1. Feast point-in-time joins (training dataset generation)
  2. Model retraining pipelines (Airflow reads these)
  3. Feature drift monitoring (compare snapshots over time)

Partition layout in MinIO:
  feast-offline/
  └── customer_features/
      └── year=2024/month=03/day=15/hour=14/
          └── snapshot_20240315_1400.parquet

  feature-snapshots/
  └── hourly/
      └── 2024-03-15T14:00:00Z.parquet   ← full feature dump
"""
from __future__ import annotations

import io
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    _ARROW_AVAILABLE = True
except ImportError:
    _ARROW_AVAILABLE = False
    logger.warning("pyarrow not available — MinIO snapshots will use JSON fallback")

try:
    from minio import Minio
    from minio.error import S3Error
    _MINIO_AVAILABLE = True
except ImportError:
    _MINIO_AVAILABLE = False
    logger.warning("minio client not available — offline store disabled")

from config import config


class MinIOStore:
    """
    Writes feature snapshots to MinIO as Parquet files.
    Falls back to newline-delimited JSON if pyarrow is unavailable.
    """

    def __init__(self):
        self._client: Optional[Any] = None
        self._enabled = _MINIO_AVAILABLE

    def connect(self):
        if not _MINIO_AVAILABLE:
            logger.warning("MinIO client not installed — offline snapshots disabled")
            return

        endpoint = config.minio_endpoint.replace("http://", "").replace("https://", "")
        self._client = Minio(
            endpoint=endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            secure=config.minio_secure,
        )

        # Ensure buckets exist
        for bucket in [config.minio_bucket_offline, config.minio_bucket_snapshots]:
            try:
                if not self._client.bucket_exists(bucket):
                    self._client.make_bucket(bucket)
                    logger.info("Created MinIO bucket: %s", bucket)
            except Exception as e:
                logger.warning("Could not verify bucket %s: %s", bucket, e)

        logger.info("Connected to MinIO at %s", config.minio_endpoint)

    def write_snapshot(self, feature_vectors: List[Dict]) -> bool:
        """
        Write a snapshot of all current feature vectors to MinIO.

        Args:
            feature_vectors: list of dicts, one per active customer

        Returns:
            True if successful, False otherwise
        """
        if not self._enabled or not self._client or not feature_vectors:
            return False

        now       = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")

        # ---- Path 1: feast-offline (partitioned by date for point-in-time joins) ----
        feast_path = (
            f"customer_features/"
            f"year={now.year}/month={now.month:02d}/"
            f"day={now.day:02d}/hour={now.hour:02d}/"
            f"snapshot_{timestamp}.parquet"
        )

        # ---- Path 2: feature-snapshots (flat, for drift monitoring) ----
        snapshot_path = f"hourly/{now.isoformat()}.parquet"

        data = self._enrich_snapshot(feature_vectors, now)

        if _ARROW_AVAILABLE:
            success = self._write_parquet(data, config.minio_bucket_offline, feast_path)
            self._write_parquet(data, config.minio_bucket_snapshots, snapshot_path)
        else:
            success = self._write_json_fallback(data, config.minio_bucket_offline, feast_path.replace(".parquet", ".jsonl"))

        if success:
            logger.info(
                "Snapshot written: %d records → %s/%s",
                len(feature_vectors), config.minio_bucket_offline, feast_path,
            )
        return success

    def _enrich_snapshot(
        self, feature_vectors: List[Dict], snapshot_ts: datetime
    ) -> List[Dict]:
        """Add snapshot timestamp for Feast point-in-time join key."""
        enriched = []
        for fv in feature_vectors:
            row = dict(fv)
            row["event_timestamp"]    = snapshot_ts.isoformat()
            row["created_timestamp"]  = snapshot_ts.isoformat()
            enriched.append(row)
        return enriched

    def _write_parquet(
        self, data: List[Dict], bucket: str, path: str
    ) -> bool:
        """Convert to Arrow table and upload as Parquet."""
        try:
            # Build Arrow schema dynamically from data
            table = pa.Table.from_pylist(data)

            buf = io.BytesIO()
            pq.write_table(
                table, buf,
                compression="snappy",
                row_group_size=10_000,
                use_dictionary=True,
            )
            buf.seek(0)
            size = buf.getbuffer().nbytes

            self._client.put_object(
                bucket_name  = bucket,
                object_name  = path,
                data         = buf,
                length       = size,
                content_type = "application/octet-stream",
            )
            return True
        except Exception as e:
            logger.error("Parquet upload failed to %s/%s: %s", bucket, path, e)
            return False

    def _write_json_fallback(
        self, data: List[Dict], bucket: str, path: str
    ) -> bool:
        """Write newline-delimited JSON when pyarrow is unavailable."""
        try:
            content = "\n".join(json.dumps(row) for row in data).encode("utf-8")
            buf     = io.BytesIO(content)
            self._client.put_object(
                bucket_name  = bucket,
                object_name  = path,
                data         = buf,
                length       = len(content),
                content_type = "application/x-ndjson",
            )
            return True
        except Exception as e:
            logger.error("JSON fallback upload failed to %s/%s: %s", bucket, path, e)
            return False

    def list_snapshots(self, prefix: str = "hourly/") -> List[str]:
        """List all snapshot objects under a prefix (for Airflow DAGs)."""
        if not self._client:
            return []
        try:
            objects = self._client.list_objects(
                config.minio_bucket_snapshots, prefix=prefix, recursive=True
            )
            return [obj.object_name for obj in objects]
        except Exception as e:
            logger.warning("list_snapshots failed: %s", e)
            return []
