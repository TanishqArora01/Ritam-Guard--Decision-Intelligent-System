"""
patterns/base.py
Abstract base class for all transaction generators (legitimate + fraud patterns).
Each pattern implements generate() and returns one or more TransactionEvents.
"""

from __future__ import annotations

import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List

from models.transaction import TransactionEvent, FraudPattern


class BasePattern(ABC):
    """
    Base class for all transaction patterns.

    Each subclass represents one fraud type (or legitimate traffic).
    generate() returns a list because some patterns (card testing, fraud ring)
    produce bursts of multiple correlated transactions.
    """

    pattern_name: FraudPattern = FraudPattern.LEGITIMATE

    def __init__(self, pool, rng: random.Random):
        self.pool = pool
        self.rng  = rng

    @abstractmethod
    def generate(self) -> List[TransactionEvent]:
        """Return one or more correlated transactions for this pattern."""
        ...

    # -------------------------------------------------------------------------
    # Shared helpers
    # -------------------------------------------------------------------------
    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _scenario_id(self) -> str:
        """Unique ID that groups related transactions in the same fraud scenario."""
        return f"SC-{uuid.uuid4().hex[:12].upper()}"

    def _base_txn(
        self,
        customer,
        amount: float,
        channel: str,
        merchant: dict,
        device_id: str,
        ip_address: str,
        country_code: str,
        city: str,
        lat: float,
        lng: float,
        is_new_device: bool = False,
        is_new_ip: bool = False,
        is_fraud: bool = False,
        fraud_pattern: FraudPattern = None,
        fraud_scenario_id: str = None,
    ) -> TransactionEvent:
        """Construct a fully populated TransactionEvent."""
        return TransactionEvent(
            customer_id       = customer.customer_id,
            customer_segment  = customer.segment,
            clv               = customer.clv,
            trust_score       = customer.trust_score,
            account_age_days  = customer.account_age_days,
            amount            = round(amount, 2),
            currency          = customer.currency,
            channel           = channel,
            merchant_id       = merchant["merchant_id"],
            merchant_category = merchant["category"],
            device_id         = device_id,
            ip_address        = ip_address,
            is_new_device     = is_new_device,
            is_new_ip         = is_new_ip,
            country_code      = country_code,
            city              = city,
            lat               = round(lat + self.rng.uniform(-0.01, 0.01), 6),
            lng               = round(lng + self.rng.uniform(-0.01, 0.01), 6),
            txn_ts            = self._now_iso(),
            ingested_at       = self._now_iso(),
            is_fraud          = is_fraud,
            fraud_pattern     = fraud_pattern,
            fraud_scenario_id = fraud_scenario_id,
        )
