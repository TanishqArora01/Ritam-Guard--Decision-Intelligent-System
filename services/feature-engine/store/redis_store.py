"""
store/redis_store.py
Online Feature Store backed by Redis.

Key design patterns:
  - Sliding window state → Redis Sorted Sets (ZSET)
      key:   feat:{customer_id}:txn_events:{window_name}
      score: Unix timestamp (float)
      value: JSON payload  {"amount": 99.50, "ts": 1234567890.0}

    ZREMRANGEBYSCORE prunes expired entries in O(log N + M).
    ZRANGEBYSCORE retrieves window contents in O(log N + M).
    This gives exact sliding windows without approximation.

  - Counters / scalars → Redis Hash
      key:   feat:{customer_id}:scalars
      field: feature_name
      value: serialised value

  - Device seen history → Redis Set
      key:   feat:{customer_id}:devices
      value: device_id strings

  - Country history → Redis Set
      key:   feat:{customer_id}:countries

  - Device transaction counter → Redis Hash
      key:   feat:device:{device_id}:counts
      field: "total"

  - IP 1h window → Redis ZSET
      key:   feat:ip:{ip_address}:events_1h
"""
from __future__ import annotations

import json
import logging
import time
from typing import Dict, List, Optional, Tuple

import redis

from config import config

logger = logging.getLogger(__name__)


class RedisStore:
    """
    Thread-safe Redis client wrapper.
    Uses a connection pool — safe to share across worker threads.
    """

    def __init__(self):
        self._pool = redis.ConnectionPool(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            password=config.redis_password or None,
            max_connections=config.redis_pool_size,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=2,
        )
        self._client: Optional[redis.Redis] = None

    def connect(self):
        self._client = redis.Redis(connection_pool=self._pool)
        self._client.ping()
        logger.info("Connected to Redis at %s:%d", config.redis_host, config.redis_port)

    @property
    def r(self) -> redis.Redis:
        return self._client

    # -------------------------------------------------------------------------
    # Sliding window helpers (ZSET-based)
    # -------------------------------------------------------------------------

    def zset_add(self, key: str, score: float, value: str, ttl: int):
        """Add entry to sorted set and refresh TTL."""
        pipe = self.r.pipeline(transaction=False)
        pipe.zadd(key, {value: score})
        pipe.expire(key, ttl)
        pipe.execute()

    def zset_window_stats(
        self, key: str, window_start: float, now: float
    ) -> Tuple[int, float]:
        """
        Return (count, sum_amount) for entries in [window_start, now].
        Prunes expired entries first.
        """
        pipe = self.r.pipeline(transaction=False)
        # Remove entries older than window
        pipe.zremrangebyscore(key, "-inf", window_start - 0.001)
        # Get entries in window
        pipe.zrangebyscore(key, window_start, now, withscores=False)
        results = pipe.execute()
        entries = results[1]  # list of JSON strings

        count  = len(entries)
        amount = 0.0
        for e in entries:
            try:
                amount += json.loads(e).get("amount", 0.0)
            except (json.JSONDecodeError, AttributeError):
                pass
        return count, round(amount, 4)

    # -------------------------------------------------------------------------
    # Velocity features
    # -------------------------------------------------------------------------

    def record_transaction(
        self,
        customer_id: str,
        txn_ts: float,
        amount: float,
    ):
        """
        Record a new transaction in the customer's velocity ZSET.
        Single key covers all windows (1m, 5m, 1h, 24h).
        TTL = 25h so 24h window never expires mid-computation.
        """
        key     = f"feat:{customer_id}:txn_events"
        payload = json.dumps({"amount": amount, "ts": txn_ts})
        pipe    = self.r.pipeline(transaction=False)
        pipe.zadd(key, {payload: txn_ts})
        pipe.expire(key, config.ttl_velocity_24h + 3600)
        pipe.execute()

    def get_velocity_features(
        self, customer_id: str, now: float
    ) -> Dict[str, float]:
        """Compute all 8 velocity features from the customer's ZSET."""
        key = f"feat:{customer_id}:txn_events"

        windows = {
            "1m":  now - config.window_1m,
            "5m":  now - config.window_5m,
            "1h":  now - config.window_1h,
            "24h": now - config.window_24h,
        }

        # Fetch all entries in 24h window (superset of all smaller windows)
        raw = self.r.zrangebyscore(key, windows["24h"], now, withscores=False)

        entries: List[Tuple[float, float]] = []  # (ts, amount)
        for e in raw:
            try:
                d = json.loads(e)
                entries.append((d["ts"], d.get("amount", 0.0)))
            except Exception:
                pass

        features: Dict[str, float] = {}
        for w_name, w_start in windows.items():
            in_window = [(ts, amt) for ts, amt in entries if ts >= w_start]
            features[f"txn_count_{w_name}"]  = len(in_window)
            features[f"amount_sum_{w_name}"] = round(sum(a for _, a in in_window), 4)

        return features

    # -------------------------------------------------------------------------
    # Geography features
    # -------------------------------------------------------------------------

    def get_last_location(
        self, customer_id: str
    ) -> Optional[Tuple[float, float, float]]:
        """Return (lat, lng, timestamp) of the customer's last transaction."""
        key = f"feat:{customer_id}:last_location"
        val = self.r.get(key)
        if val:
            d = json.loads(val)
            return d["lat"], d["lng"], d["ts"]
        return None

    def set_last_location(
        self, customer_id: str, lat: float, lng: float, ts: float
    ):
        key = f"feat:{customer_id}:last_location"
        self.r.setex(key, config.ttl_geo_history, json.dumps({"lat": lat, "lng": lng, "ts": ts}))

    def get_country_set(self, customer_id: str) -> set:
        """Return set of countries seen for this customer in last 24h."""
        key = f"feat:{customer_id}:countries_24h"
        return self.r.smembers(key) or set()

    def add_country(self, customer_id: str, country_code: str):
        key = f"feat:{customer_id}:countries_24h"
        pipe = self.r.pipeline(transaction=False)
        pipe.sadd(key, country_code)
        pipe.expire(key, config.ttl_velocity_24h + 3600)
        pipe.execute()

    # -------------------------------------------------------------------------
    # Device & Network features
    # -------------------------------------------------------------------------

    def get_device_txn_count(self, customer_id: str, device_id: str) -> int:
        """Number of times this customer has used this device (lifetime)."""
        key = f"feat:{customer_id}:device:{device_id}:count"
        val = self.r.get(key)
        return int(val) if val else 0

    def increment_device_count(self, customer_id: str, device_id: str):
        key = f"feat:{customer_id}:device:{device_id}:count"
        pipe = self.r.pipeline(transaction=False)
        pipe.incr(key)
        pipe.expire(key, config.ttl_device_trust)
        pipe.execute()

    def get_unique_devices_24h(self, customer_id: str, now: float) -> int:
        """Count distinct devices used by this customer in last 24h."""
        key = f"feat:{customer_id}:devices_24h"
        # ZSET where score = timestamp, value = device_id
        self.r.zremrangebyscore(key, "-inf", now - config.window_24h)
        return max(1, self.r.zcard(key))

    def record_device_event(self, customer_id: str, device_id: str, ts: float):
        key = f"feat:{customer_id}:devices_24h"
        pipe = self.r.pipeline(transaction=False)
        pipe.zadd(key, {device_id: ts})    # ZSET deduplicates by value
        pipe.expire(key, config.ttl_velocity_24h + 3600)
        pipe.execute()

    def get_ip_txn_count_1h(self, ip_address: str, now: float) -> int:
        """Transactions from this IP address in last 1 hour (all customers)."""
        key = f"feat:ip:{ip_address}:events_1h"
        self.r.zremrangebyscore(key, "-inf", now - config.window_1h)
        return self.r.zcard(key) or 0

    def record_ip_event(self, ip_address: str, txn_id: str, ts: float):
        key = f"feat:ip:{ip_address}:events_1h"
        pipe = self.r.pipeline(transaction=False)
        pipe.zadd(key, {txn_id: ts})
        pipe.expire(key, config.window_1h + 300)
        pipe.execute()

    # -------------------------------------------------------------------------
    # Behavioral features
    # -------------------------------------------------------------------------

    def get_behavioral_state(self, customer_id: str) -> Dict:
        """
        Return persisted behavioral state for this customer.
        Stored as a Redis Hash for atomic field updates.
        """
        key = f"feat:{customer_id}:behavioral"
        data = self.r.hgetall(key)
        return {
            "avg_amount":         float(data.get("avg_amount",         "0.0")),
            "txn_count_total":    int(data.get("txn_count_total",       "0")),
            "last_txn_ts":        float(data.get("last_txn_ts",         "0.0")),
            "merchant_counts":    json.loads(data.get("merchant_counts", "{}")),
        }

    def update_behavioral_state(
        self,
        customer_id: str,
        amount: float,
        ts: float,
        merchant_id: str,
    ):
        """
        Update running average (Welford's online algorithm) and merchant counts.
        Uses a Redis Hash for O(1) field updates without loading the full state.
        """
        key = f"feat:{customer_id}:behavioral"
        state = self.get_behavioral_state(customer_id)

        n          = state["txn_count_total"] + 1
        old_avg    = state["avg_amount"]
        new_avg    = old_avg + (amount - old_avg) / n  # Welford update

        merchants  = state["merchant_counts"]
        merchants[merchant_id] = merchants.get(merchant_id, 0) + 1

        pipe = self.r.pipeline(transaction=False)
        pipe.hset(key, mapping={
            "avg_amount":      str(round(new_avg, 4)),
            "txn_count_total": str(n),
            "last_txn_ts":     str(ts),
            "merchant_counts": json.dumps(merchants),
        })
        pipe.expire(key, config.ttl_behavioral)
        pipe.execute()

    # -------------------------------------------------------------------------
    # Snapshot helper — dump all active customer states for MinIO
    # -------------------------------------------------------------------------

    def scan_all_customer_keys(self) -> List[str]:
        """Return all unique customer_ids that have feature state in Redis."""
        seen    = set()
        cursor  = 0
        pattern = "feat:*:behavioral"
        while True:
            cursor, keys = self.r.scan(cursor=cursor, match=pattern, count=500)
            for k in keys:
                # key format: feat:{customer_id}:behavioral
                parts = k.split(":")
                if len(parts) >= 3:
                    seen.add(parts[1])
            if cursor == 0:
                break
        return list(seen)
