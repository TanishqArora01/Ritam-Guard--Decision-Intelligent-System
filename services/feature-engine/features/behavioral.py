"""
features/behavioral.py
Behavioral feature computation — personalised customer baseline modelling.

Produces 3 features:
  amount_vs_avg_ratio  — how unusual is this amount relative to customer history
  merchant_familiarity — has the customer used this merchant before?
  hours_since_last_txn — recency of last transaction (session detection)

These features implement the "personalised user baseline" layer described
in the architecture. The same $10,000 transaction has very different risk
profiles for a premium customer (avg spend $5,000) vs a new customer
(avg spend $50). The ratio normalises across customers.

Welford's Online Algorithm for running mean:
  After n transactions, mean_n = mean_{n-1} + (x_n - mean_{n-1}) / n
  This updates the running average in O(1) without storing all historical values.
  Redis persists the (mean, n) state between transactions.

Merchant Familiarity Score:
  0.0 → merchant never visited by this customer
  0.5 → visited once or twice
  1.0 → visited >= MERCHANT_FAMILIAR_THRESHOLD times (default: 2)

  Score = min(1.0, merchant_visits / MERCHANT_FAMILIAR_THRESHOLD)
"""
from __future__ import annotations

import logging
import time
from typing import Dict

from store.redis_store import RedisStore
from config import config

logger = logging.getLogger(__name__)

# Maximum ratio cap — prevent extreme values from destabilising models
MAX_AMOUNT_RATIO = 100.0


class BehavioralFeatures:

    def __init__(self, store: RedisStore):
        self.store = store

    def compute(
        self,
        customer_id:     str,
        amount:          float,
        merchant_id:     str,
        txn_ts:          float,
        customer_clv_avg: float = 0.0,  # fallback from customer profile
    ) -> Dict[str, float]:
        """
        Compute behavioral features for the current transaction.

        Args:
            customer_id:      unique customer identifier
            amount:           current transaction amount
            merchant_id:      merchant identifier
            txn_ts:           current transaction Unix timestamp
            customer_clv_avg: fallback average from customer profile (used on cold start)

        Returns:
            dict with 3 behavioral features
        """
        try:
            state = self.store.get_behavioral_state(customer_id)

            # --- amount_vs_avg_ratio ---
            historical_avg = state["avg_amount"]
            if historical_avg <= 0.0:
                # Cold start: use the customer's declared average from their profile
                historical_avg = max(customer_clv_avg, 1.0)

            amount_vs_avg_ratio = round(
                min(MAX_AMOUNT_RATIO, amount / max(historical_avg, 0.01)),
                4,
            )

            # --- merchant_familiarity ---
            merchant_visits   = state["merchant_counts"].get(merchant_id, 0)
            threshold         = config.merchant_familiar_threshold
            merchant_familiarity = round(
                min(1.0, merchant_visits / max(threshold, 1)), 4
            )

            # --- hours_since_last_txn ---
            last_ts = state["last_txn_ts"]
            if last_ts > 0.0:
                hours_since_last_txn = round((txn_ts - last_ts) / 3600.0, 4)
                # Cap at 720h (30 days) to avoid extreme values for dormant accounts
                hours_since_last_txn = min(hours_since_last_txn, 720.0)
            else:
                # Cold start: assume 24h since last transaction
                hours_since_last_txn = 24.0

            # --- Update state (write after read) ---
            self.store.update_behavioral_state(
                customer_id=customer_id,
                amount=amount,
                ts=txn_ts,
                merchant_id=merchant_id,
            )

            return {
                "amount_vs_avg_ratio":  amount_vs_avg_ratio,
                "merchant_familiarity": merchant_familiarity,
                "hours_since_last_txn": hours_since_last_txn,
            }

        except Exception as e:
            logger.warning(
                "BehavioralFeatures.compute failed for %s: %s", customer_id, e
            )
            return {
                "amount_vs_avg_ratio":  1.0,
                "merchant_familiarity": 0.0,
                "hours_since_last_txn": 24.0,
            }
