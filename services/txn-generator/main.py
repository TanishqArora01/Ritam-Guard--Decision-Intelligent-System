"""
main.py
Synthetic transaction generator — main entry point.

Architecture:
  - N worker threads each run an independent generate → produce loop
  - A shared TokenBucket (inside FraudProducer) enforces the global TPS cap
  - Pattern selection uses a weighted sampler:
      fraud_rate% → pick a fraud pattern (weighted by config.fraud_pattern_weights)
      (1 - fraud_rate)% → legitimate pattern
  - Stats are logged every STATS_INTERVAL_SEC seconds
  - Prometheus metrics served on /metrics at METRICS_PORT
"""

from __future__ import annotations

import logging
import os
import random
import signal
import sys
import threading
import time
from typing import Dict, List, Type

from prometheus_client import start_http_server

from config import config
from models.customer_pool import CustomerPool
from models.transaction import FraudPattern
from producer import FraudProducer

# Pattern imports
from patterns.legitimate import LegitimatePattern
from patterns.card_testing import CardTestingPattern
from patterns.account_takeover import AccountTakeoverPattern
from patterns.velocity_attack import VelocityAttackPattern
from patterns.fraud_ring import FraudRingPattern
from patterns.geo_impossibility import GeoImpossibilityPattern
from patterns.large_amount import LargeAmountPattern
from patterns.base import BasePattern

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generator.main")

# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------
FRAUD_PATTERN_CLASSES: Dict[str, Type[BasePattern]] = {
    "card_testing":      CardTestingPattern,
    "account_takeover":  AccountTakeoverPattern,
    "velocity_attack":   VelocityAttackPattern,
    "fraud_ring":        FraudRingPattern,
    "geo_impossibility": GeoImpossibilityPattern,
    "large_amount":      LargeAmountPattern,
}


# ---------------------------------------------------------------------------
# Weighted pattern sampler
# ---------------------------------------------------------------------------
class PatternSampler:
    """
    Samples a pattern class on each call.
    Respects fraud_rate and per-pattern weights from config.
    """

    def __init__(self, rng: random.Random):
        self.rng = rng

        raw_weights = config.fraud_pattern_weights
        total       = sum(raw_weights.values())
        self._fraud_names   = list(raw_weights.keys())
        self._fraud_weights = [raw_weights[k] / total for k in self._fraud_names]

    def sample(self) -> str:
        """Return a pattern name: 'legitimate' or one of the fraud pattern names."""
        if self.rng.random() < config.fraud_rate:
            return self.rng.choices(self._fraud_names, weights=self._fraud_weights, k=1)[0]
        return "legitimate"


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------
class GeneratorWorker(threading.Thread):
    """
    One producer worker thread.
    Each worker has its own RNG (seeded from global seed + worker index)
    and its own pattern instances, making it fully independent.
    """

    def __init__(
        self,
        worker_id:  int,
        pool:       CustomerPool,
        producer:   FraudProducer,
        stop_event: threading.Event,
    ):
        super().__init__(name=f"worker-{worker_id}", daemon=True)
        self.worker_id  = worker_id
        self.pool       = pool
        self.producer   = producer
        self.stop_event = stop_event

        # Independent RNG per worker — reproducible but non-overlapping
        self.rng = random.Random(config.random_seed + worker_id * 1000)
        self.sampler = PatternSampler(self.rng)

        # Instantiate one of each pattern per worker
        self._patterns: Dict[str, BasePattern] = {
            "legitimate":      LegitimatePattern(pool, self.rng),
            "card_testing":    CardTestingPattern(pool, self.rng),
            "account_takeover":AccountTakeoverPattern(pool, self.rng),
            "velocity_attack": VelocityAttackPattern(pool, self.rng),
            "fraud_ring":      FraudRingPattern(pool, self.rng),
            "geo_impossibility":GeoImpossibilityPattern(pool, self.rng),
            "large_amount":    LargeAmountPattern(pool, self.rng),
        }

        self.produced = 0
        self.errors   = 0

    def run(self):
        logger.info("Worker %d started", self.worker_id)
        total_limit = config.total_txns  # 0 = unlimited

        while not self.stop_event.is_set():
            if total_limit > 0 and self.produced >= total_limit // config.workers:
                logger.info("Worker %d reached total_txns limit — stopping", self.worker_id)
                break

            pattern_name = self.sampler.sample()
            pattern      = self._patterns[pattern_name]

            try:
                txns = pattern.generate()
                for txn in txns:
                    self.producer.produce(txn)
                    self.produced += 1
            except Exception as exc:
                self.errors += 1
                logger.warning("Worker %d error in pattern %s: %s", self.worker_id, pattern_name, exc)

        logger.info("Worker %d done. Produced: %d | Errors: %d", self.worker_id, self.produced, self.errors)


# ---------------------------------------------------------------------------
# Stats reporter
# ---------------------------------------------------------------------------
def stats_reporter(producer: FraudProducer, stop_event: threading.Event):
    """Periodic stats log — runs in its own daemon thread."""
    start = time.monotonic()
    while not stop_event.is_set():
        time.sleep(config.stats_interval_sec)
        elapsed = time.monotonic() - start
        stats   = producer.stats
        tps     = stats["produced"] / max(elapsed, 1)
        logger.info(
            "STATS | produced=%d | errors=%d | elapsed=%.1fs | avg_tps=%.1f",
            stats["produced"], stats["errors"], elapsed, tps,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    logger.info("=" * 60)
    logger.info("Fraud Detection — Synthetic Transaction Generator")
    logger.info("=" * 60)
    logger.info("Config:")
    logger.info("  TPS target    : %s", config.tps if config.tps > 0 else "unlimited")
    logger.info("  Workers       : %d", config.workers)
    logger.info("  Fraud rate    : %.1f%%", config.fraud_rate * 100)
    logger.info("  Customers     : %d", config.num_customers)
    logger.info("  Kafka broker  : %s", config.kafka_bootstrap_servers)
    logger.info("  Topic         : %s", config.kafka_topic_raw)
    logger.info("  Total txns    : %s", config.total_txns if config.total_txns > 0 else "unlimited")
    logger.info("  Metrics port  : %d", config.metrics_port)
    logger.info("")

    # --- Start Prometheus metrics server ---
    start_http_server(config.metrics_port)
    logger.info("Prometheus metrics at http://0.0.0.0:%d/metrics", config.metrics_port)

    # --- Build customer pool ---
    logger.info("Building customer pool (%d customers)...", config.num_customers)
    pool_rng = random.Random(config.random_seed)
    pool     = CustomerPool().build(config, pool_rng)
    logger.info(
        "Pool ready: %d customers | %d devices | %d merchants | %d IPs",
        len(pool.customers), len(pool.all_devices),
        len(pool.all_merchants), len(pool.all_ips),
    )

    # --- Connect Kafka producer ---
    producer = FraudProducer()
    producer.connect()

    # --- Shutdown coordination ---
    stop_event = threading.Event()

    def _shutdown(signum, frame):
        logger.info("Shutdown signal received — stopping workers...")
        stop_event.set()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # --- Start stats reporter ---
    stats_thread = threading.Thread(
        target=stats_reporter, args=(producer, stop_event), daemon=True, name="stats"
    )
    stats_thread.start()

    # --- Start worker threads ---
    workers: List[GeneratorWorker] = []
    for i in range(config.workers):
        w = GeneratorWorker(i, pool, producer, stop_event)
        w.start()
        workers.append(w)

    logger.info("All %d workers running. Press Ctrl+C to stop.", config.workers)

    # --- Wait for all workers ---
    for w in workers:
        w.join()

    # --- Flush and close ---
    logger.info("All workers finished. Flushing Kafka producer...")
    producer.close()

    total_produced = sum(w.produced for w in workers)
    total_errors   = sum(w.errors for w in workers)
    logger.info("Final: produced=%d | errors=%d", total_produced, total_errors)
    logger.info("Generator shutdown complete.")


if __name__ == "__main__":
    main()
