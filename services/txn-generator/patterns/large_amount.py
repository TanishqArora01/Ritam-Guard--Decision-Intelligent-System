"""
patterns/large_amount.py

Large Amount Anomaly:
A single transaction that is dramatically larger than the customer's
historical spending pattern. Typically targets high-CLV accounts.

This tests the behavioral baseline component — a $50,000 transaction is
suspicious for someone who normally spends $200/month, but normal for a
premium private banking customer.

Signals:
  - amount >> customer's avg_txn_amount (10x–50x)
  - Often high-risk merchant category (jewelry, wire transfer, crypto)
  - May use known device (to look legitimate) but unusual amount
  - CLV-relative scoring matters: same amount may be APPROVE for premium,
    BLOCK for standard customer
"""

from __future__ import annotations

from typing import List

from models.transaction import TransactionEvent, FraudPattern, Channel
from models.customer_pool import HIGH_RISK_CATEGORIES
from patterns.base import BasePattern


class LargeAmountPattern(BasePattern):

    pattern_name = FraudPattern.LARGE_AMOUNT

    def generate(self) -> List[TransactionEvent]:
        customer    = self.pool.random_customer(self.rng)
        scenario_id = self._scenario_id()

        # Prefer a high-risk merchant category
        risky_merchant = next(
            (m for m in self.rng.sample(self.pool.all_merchants, min(30, len(self.pool.all_merchants)))
             if m["category"] in HIGH_RISK_CATEGORIES),
            self.pool.random_merchant(self.rng)
        )

        # Amount: 10x–50x the customer's average (always > $5,000)
        multiplier = self.rng.uniform(10.0, 50.0)
        amount     = max(round(customer.avg_txn_amount * multiplier, 2), 5_000.0)

        # Device: may use known device to appear legitimate
        use_known = self.rng.random() < 0.6 and customer.owned_devices
        device_id = (
            self.rng.choice(customer.owned_devices) if use_known
            else self.pool.random_device(self.rng)
        )
        is_new_device = device_id not in customer.owned_devices

        ip_address = self.pool.random_ip(self.rng)
        is_new_ip  = ip_address not in customer.known_ips

        geo = customer.home_location

        txn = self._base_txn(
            customer          = customer,
            amount            = amount,
            channel           = self.rng.choice([Channel.WEB, Channel.MOBILE, Channel.CARD_NETWORK]),
            merchant          = risky_merchant,
            device_id         = device_id,
            ip_address        = ip_address,
            is_new_device     = is_new_device,
            is_new_ip         = is_new_ip,
            country_code      = geo["country"],
            city              = geo["city"],
            lat               = geo["lat"],
            lng               = geo["lng"],
            is_fraud          = True,
            fraud_pattern     = FraudPattern.LARGE_AMOUNT,
            fraud_scenario_id = scenario_id,
        )
        return [txn]
