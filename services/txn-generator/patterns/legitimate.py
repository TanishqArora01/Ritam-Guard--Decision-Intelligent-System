"""
patterns/legitimate.py
Generates realistic legitimate transactions.
Amount drawn from a log-normal distribution matching real banking data.
"""

from __future__ import annotations

import math
from typing import List

from models.transaction import TransactionEvent, FraudPattern
from patterns.base import BasePattern


class LegitimatePattern(BasePattern):

    pattern_name = FraudPattern.LEGITIMATE

    def generate(self) -> List[TransactionEvent]:
        customer = self.pool.random_customer(self.rng)
        merchant = self.pool.random_merchant(self.rng)

        # Amount: log-normal centred on customer's average spend
        mu    = math.log(max(customer.avg_txn_amount, 1.0))
        sigma = 0.8  # realistic spread
        amount = min(self.rng.lognormvariate(mu, sigma), customer.clv * 0.05)
        amount = max(amount, 0.50)

        # Customer uses one of their known devices + IPs
        device_id  = self.rng.choice(customer.owned_devices) if customer.owned_devices else self.pool.random_device(self.rng)
        ip_address = self.rng.choice(customer.known_ips) if customer.known_ips else self.pool.random_ip(self.rng)

        # Slight geo drift from home — same city mostly
        home = customer.home_location
        lat  = home["lat"] + self.rng.gauss(0, 0.05)
        lng  = home["lng"] + self.rng.gauss(0, 0.05)

        return [self._base_txn(
            customer      = customer,
            amount        = amount,
            channel       = customer.preferred_channel,
            merchant      = merchant,
            device_id     = device_id,
            ip_address    = ip_address,
            country_code  = home["country"],
            city          = home["city"],
            lat           = lat,
            lng           = lng,
            is_fraud      = False,
            fraud_pattern = FraudPattern.LEGITIMATE,
        )]
