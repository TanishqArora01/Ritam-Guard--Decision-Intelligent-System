"""
features/device_network.py
Device and Network feature computation.

Produces 4 features:
  device_trust_score  — 0.0 (new/unknown) to 1.0 (fully trusted device)
  is_new_device       — device never seen before for this customer
  ip_txn_count_1h     — how many transactions came from this IP in last 1 hour
  unique_devices_24h  — how many distinct devices this customer used today

Device Trust Score Formula:
  trust = min(1.0,  device_txn_count / TRUSTED_THRESHOLD)
    where TRUSTED_THRESHOLD = 5 (configurable)

  A device seen 0 times → trust = 0.0  (brand new)
  A device seen 5+ times → trust = 1.0  (established)

  This creates a continuous 0→1 ramp that ML models can use directly,
  rather than a binary is_new_device flag.

IP Velocity:
  Counts ALL transactions through this IP in the last 1 hour,
  regardless of which customer they belong to.
  A single IP processing 100+ transactions/hour is a strong fraud ring signal.
"""
from __future__ import annotations

import logging
import time
from typing import Dict

from store.redis_store import RedisStore
from config import config

logger = logging.getLogger(__name__)


class DeviceNetworkFeatures:

    def __init__(self, store: RedisStore):
        self.store = store

    def compute(
        self,
        customer_id: str,
        device_id:   str,
        ip_address:  str,
        txn_id:      str,
        txn_ts:      float,
    ) -> Dict[str, object]:
        """
        Compute device and network features for the current transaction.

        Args:
            customer_id: unique customer identifier
            device_id:   device fingerprint / ID
            ip_address:  source IP address
            txn_id:      unique transaction ID (for IP ZSET deduplication)
            txn_ts:      transaction Unix timestamp

        Returns:
            dict with 4 device/network features
        """
        try:
            # --- Device transaction history ---
            device_past_count = self.store.get_device_txn_count(customer_id, device_id)
            is_new_device     = device_past_count == 0

            # Device trust: ramp 0→1 over TRUSTED_THRESHOLD transactions
            threshold         = config.device_trusted_txn_threshold
            device_trust_score = round(
                min(1.0, device_past_count / max(threshold, 1)), 4
            )

            # --- IP velocity ---
            ip_txn_count_1h = self.store.get_ip_txn_count_1h(ip_address, txn_ts)

            # --- Device diversity ---
            unique_devices_24h = self.store.get_unique_devices_24h(customer_id, txn_ts)

            # --- Update state (write after read for consistency) ---
            self.store.increment_device_count(customer_id, device_id)
            self.store.record_device_event(customer_id, device_id, txn_ts)
            self.store.record_ip_event(ip_address, txn_id, txn_ts)

            return {
                "device_trust_score": device_trust_score,
                "is_new_device":      is_new_device,
                "ip_txn_count_1h":    ip_txn_count_1h,
                "unique_devices_24h": unique_devices_24h,
            }

        except Exception as e:
            logger.warning(
                "DeviceNetworkFeatures.compute failed for customer=%s device=%s: %s",
                customer_id, device_id, e,
            )
            return {
                "device_trust_score": 0.5,
                "is_new_device":      False,
                "ip_txn_count_1h":    0,
                "unique_devices_24h": 1,
            }
