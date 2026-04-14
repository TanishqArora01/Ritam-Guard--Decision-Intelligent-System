"""
main.py
Feature Engineering Service — entry point.

Runs:
  N consumer worker threads → each owns one Kafka consumer + RedisStore
  1 snapshot scheduler thread → hourly MinIO Parquet dumps
  1 Prometheus HTTP server
"""
from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from dataclasses import asdict
from typing import List

from prometheus_client import start_http_server

from config import config
from processor import FeatureProcessor
from store.redis_store import RedisStore
from store.minio_store import MinIOStore
from features.registry import FeatureVector, FEATURE_NAMES

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("feature-engine.main")


# ---------------------------------------------------------------------------
# Snapshot scheduler
# ---------------------------------------------------------------------------

def snapshot_scheduler(
    redis_store: RedisStore,
    minio_store: MinIOStore,
    stop_event:  threading.Event,
):
    """
    Runs in a daemon thread.
    Every SNAPSHOT_INTERVAL_SEC: scans all active customers in Redis,
    reads their current feature state, and writes a Parquet snapshot to MinIO.
    """
    logger.info(
        "Snapshot scheduler started — interval=%ds", config.snapshot_interval_sec
    )
    next_run = time.monotonic() + config.snapshot_interval_sec

    while not stop_event.is_set():
        remaining = next_run - time.monotonic()
        if remaining > 0:
            time.sleep(min(remaining, 5.0))
            continue

        logger.info("Snapshot run starting...")
        t_start = time.monotonic()

        try:
            customer_ids = redis_store.scan_all_customer_keys()
            logger.info("Snapshot: found %d active customers", len(customer_ids))

            if customer_ids:
                snapshots = []
                for cid in customer_ids:
                    try:
                        state = redis_store.get_behavioral_state(cid)
                        vel   = redis_store.get_velocity_features(cid, time.time())
                        row   = {
                            "customer_id":         cid,
                            "avg_amount":          state["avg_amount"],
                            "txn_count_total":     state["txn_count_total"],
                            "last_txn_ts":         state["last_txn_ts"],
                            **vel,
                        }
                        snapshots.append(row)
                    except Exception as e:
                        logger.debug("Snapshot: skip %s: %s", cid, e)

                ok = minio_store.write_snapshot(snapshots)
                elapsed = time.monotonic() - t_start
                logger.info(
                    "Snapshot complete: %d records | %s | %.1fs",
                    len(snapshots), "OK" if ok else "FAILED", elapsed,
                )

        except Exception as e:
            logger.error("Snapshot scheduler error: %s", e)

        next_run = time.monotonic() + config.snapshot_interval_sec


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("=" * 62)
    logger.info("Fraud Detection — Feature Engineering Service")
    logger.info("=" * 62)
    logger.info("Config:")
    logger.info("  Workers          : %d",    config.num_workers)
    logger.info("  Input topic      : %s",    config.kafka_topic_raw)
    logger.info("  Output topic     : %s",    config.kafka_topic_enriched)
    logger.info("  Consumer group   : %s",    config.kafka_consumer_group)
    logger.info("  Redis            : %s:%d", config.redis_host, config.redis_port)
    logger.info("  MinIO            : %s",    config.minio_endpoint)
    logger.info("  Snapshot interval: %ds",   config.snapshot_interval_sec)
    logger.info("  Metrics port     : %d",    config.metrics_port)
    logger.info("  Features (18)    : %s",    ", ".join(FEATURE_NAMES[:6]) + " ...")
    logger.info("")

    # --- Prometheus metrics ---
    start_http_server(config.metrics_port)
    logger.info("Prometheus metrics at http://0.0.0.0:%d/metrics", config.metrics_port)

    # --- Shared Redis store (connection pool, thread-safe) ---
    redis_store = RedisStore()
    redis_store.connect()

    # --- MinIO store (snapshot writer) ---
    minio_store = MinIOStore()
    minio_store.connect()

    # --- Shutdown coordination ---
    stop_event = threading.Event()

    def _shutdown(signum, frame):
        logger.info("Shutdown signal received")
        stop_event.set()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # --- Snapshot scheduler thread ---
    snap_thread = threading.Thread(
        target=snapshot_scheduler,
        args=(redis_store, minio_store, stop_event),
        daemon=True,
        name="snapshot-scheduler",
    )
    snap_thread.start()

    # --- Worker threads ---
    workers: List[threading.Thread] = []
    processors: List[FeatureProcessor] = []

    for i in range(config.num_workers):
        proc = FeatureProcessor(worker_id=i, redis_store=redis_store)
        proc.connect()
        processors.append(proc)

        t = threading.Thread(
            target=proc.run,
            args=(stop_event,),
            daemon=True,
            name=f"feature-worker-{i}",
        )
        t.start()
        workers.append(t)

    logger.info("All %d workers running.", config.num_workers)
    logger.info("Consuming from '%s' → publishing to '%s'",
                config.kafka_topic_raw, config.kafka_topic_enriched)

    # --- Wait ---
    for t in workers:
        t.join()

    logger.info("Feature engine shutdown complete.")


if __name__ == "__main__":
    main()
