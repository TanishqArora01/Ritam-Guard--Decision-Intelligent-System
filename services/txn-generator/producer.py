"""
producer.py
High-throughput async Kafka producer with:
  - Token bucket rate limiter for precise TPS control
  - Delivery callbacks for error tracking
  - Prometheus metrics (messages/s, errors, latency)
  - Graceful shutdown
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from confluent_kafka import Producer, KafkaException
from prometheus_client import Counter, Gauge, Histogram

from config import config
from models.transaction import TransactionEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
TXN_PRODUCED = Counter(
    "generator_txn_produced_total",
    "Total transactions produced to Kafka",
    ["topic", "is_fraud", "fraud_pattern"],
)
TXN_ERRORS = Counter(
    "generator_txn_errors_total",
    "Total Kafka delivery errors",
    ["topic"],
)
PRODUCE_LATENCY = Histogram(
    "generator_produce_latency_seconds",
    "Time spent in produce() call",
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
)
CURRENT_TPS = Gauge(
    "generator_current_tps",
    "Current measured transactions per second",
)
QUEUE_SIZE = Gauge(
    "generator_kafka_queue_size",
    "Current Kafka producer internal queue size",
)


# ---------------------------------------------------------------------------
# Token Bucket Rate Limiter
# ---------------------------------------------------------------------------
class TokenBucket:
    """
    Thread-safe token bucket for precise TPS control.
    Allows short bursts while enforcing a long-run average rate.
    """

    def __init__(self, rate: int, burst_multiplier: float = 1.5):
        self._rate      = rate            # tokens per second
        self._capacity  = max(1, int(rate * burst_multiplier))
        self._tokens    = float(self._capacity)
        self._last_refill = time.monotonic()
        self._lock      = threading.Lock()

    def acquire(self, n: int = 1) -> float:
        """
        Acquire n tokens. Blocks until available.
        Returns the time slept (seconds).
        """
        slept = 0.0
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= n:
                    self._tokens -= n
                    return slept
            sleep_for = n / max(self._rate, 1)
            time.sleep(sleep_for)
            slept += sleep_for

    def _refill(self):
        now     = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def update_rate(self, new_rate: int):
        with self._lock:
            self._rate     = new_rate
            self._capacity = max(1, int(new_rate * 1.5))


# ---------------------------------------------------------------------------
# Kafka Producer wrapper
# ---------------------------------------------------------------------------
@dataclass
class FraudProducer:
    """
    Wraps confluent-kafka Producer with delivery callbacks,
    rate limiting, and Prometheus instrumentation.
    """

    _producer: Optional[Producer]  = field(default=None, init=False)
    _bucket:   Optional[TokenBucket] = field(default=None, init=False)

    # Running stats
    _produced:  int   = field(default=0, init=False)
    _errors:    int   = field(default=0, init=False)
    _window_start: float = field(default_factory=time.monotonic, init=False)
    _window_count: int   = field(default=0, init=False)

    def connect(self):
        """Create Kafka producer. Call once at startup."""
        kafka_conf = {
            "bootstrap.servers":       config.kafka_bootstrap_servers,
            "acks":                    config.kafka_acks,
            "compression.type":        config.kafka_compression,
            "batch.size":              config.kafka_batch_size,
            "linger.ms":               config.kafka_linger_ms,
            "queue.buffering.max.messages": 500_000,
            "queue.buffering.max.kbytes":   512_000,
            "message.max.bytes":       1_048_576,
            "socket.keepalive.enable": True,
        }
        self._producer = Producer(kafka_conf)
        self._bucket   = TokenBucket(rate=config.tps) if config.tps > 0 else None
        logger.info(
            "Connected to Kafka at %s | TPS limit: %s",
            config.kafka_bootstrap_servers,
            config.tps if config.tps > 0 else "unlimited",
        )

    def produce(self, txn: TransactionEvent):
        """
        Rate-limit then produce a single transaction to Kafka.
        Non-blocking: delivery is confirmed asynchronously via callback.
        """
        if self._bucket:
            self._bucket.acquire(1)

        payload = txn.to_kafka_bytes()
        key     = txn.partition_key

        start = time.monotonic()
        try:
            self._producer.produce(
                topic     = config.kafka_topic_raw,
                key       = key,
                value     = payload,
                on_delivery = self._delivery_callback,
            )
            # Poll non-blocking to drain delivery callbacks
            self._producer.poll(0)

        except BufferError:
            # Internal queue full — poll to drain then retry once
            logger.warning("Kafka buffer full — polling to drain")
            self._producer.poll(0.1)
            self._producer.produce(
                topic       = config.kafka_topic_raw,
                key         = key,
                value       = payload,
                on_delivery = self._delivery_callback,
            )

        finally:
            PRODUCE_LATENCY.observe(time.monotonic() - start)
            QUEUE_SIZE.set(len(self._producer))
            self._update_tps_gauge()

    def _delivery_callback(self, err, msg):
        """Called by librdkafka when a message is confirmed delivered or failed."""
        pattern = "unknown"
        try:
            import json
            body    = json.loads(msg.value())
            pattern = body.get("fraud_pattern", "legitimate")
            is_fraud = str(body.get("is_fraud", False))
        except Exception:
            is_fraud = "unknown"

        if err:
            self._errors += 1
            TXN_ERRORS.labels(topic=msg.topic()).inc()
            logger.error("Delivery failed for %s: %s", msg.key(), err)
        else:
            self._produced += 1
            self._window_count += 1
            TXN_PRODUCED.labels(
                topic        = msg.topic(),
                is_fraud     = is_fraud,
                fraud_pattern= pattern,
            ).inc()

    def _update_tps_gauge(self):
        now     = time.monotonic()
        elapsed = now - self._window_start
        if elapsed >= 1.0:
            tps = self._window_count / elapsed
            CURRENT_TPS.set(tps)
            self._window_count = 0
            self._window_start = now

    def flush(self, timeout: float = 30.0):
        """Wait for all outstanding messages to be delivered."""
        if self._producer:
            remaining = self._producer.flush(timeout)
            if remaining > 0:
                logger.warning("%d messages still in queue after flush timeout", remaining)

    def close(self):
        logger.info("Flushing producer before shutdown...")
        self.flush()
        logger.info(
            "Producer closed. Produced: %d | Errors: %d",
            self._produced, self._errors,
        )

    @property
    def stats(self) -> dict:
        return {
            "produced": self._produced,
            "errors":   self._errors,
        }
