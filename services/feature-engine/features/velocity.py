"""
features/velocity.py
Velocity feature computation using Redis sorted-set sliding windows.

Produces 8 features:
  txn_count_1m, txn_count_5m, txn_count_1h, txn_count_24h
  amount_sum_1m, amount_sum_5m, amount_sum_1h, amount_sum_24h

Design: single ZSET per customer holds all events for the 24h window.
        All smaller windows are derived by filtering on score (timestamp).
        This gives exact counts with O(log N) complexity per window.
"""
from __future__ import annotations

import logging
import time
from typing import Dict

from store.redis_store import RedisStore

logger = logging.getLogger(__name__)


class VelocityFeatures:

    def __init__(self, store: RedisStore):
        self.store = store

    def compute(
        self,
        customer_id: str,
        amount: float,
        txn_ts: float,
    ) -> Dict[str, float]:
        """
        Record the current transaction and compute all velocity features.

        Args:
            customer_id: unique customer identifier
            amount:      transaction amount in USD
            txn_ts:      transaction Unix timestamp (float seconds)

        Returns:
            dict with 8 velocity features
        """
        try:
            # 1. Record this transaction in the ZSET (write-first, then read)
            self.store.record_transaction(customer_id, txn_ts, amount)

            # 2. Compute all windows in one Redis call
            features = self.store.get_velocity_features(customer_id, txn_ts)

            # txn_count windows include the current transaction (just inserted)
            # This is the correct behaviour — we want the state AFTER this txn.
            return features

        except Exception as e:
            logger.warning("VelocityFeatures.compute failed for %s: %s", customer_id, e)
            # Return safe defaults on Redis failure (cold start / outage)
            return {
                "txn_count_1m":  1,
                "txn_count_5m":  1,
                "txn_count_1h":  1,
                "txn_count_24h": 1,
                "amount_sum_1m":  amount,
                "amount_sum_5m":  amount,
                "amount_sum_1h":  amount,
                "amount_sum_24h": amount,
            }
