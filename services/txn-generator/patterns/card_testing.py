"""
patterns/card_testing.py

Card Testing Attack:
Fraudsters obtain stolen card details and run many small transactions
(typically $0.01–$5.00) to verify the card is active before making
large purchases.

Signals:
  - High velocity of very small amounts in a short window
  - Multiple merchants / merchant categories in seconds
  - New or unknown device
  - Often online/WEB channel
  - Same customer, rapid-fire from same IP
"""

from __future__ import annotations

from typing import List

from models.transaction import TransactionEvent, FraudPattern, Channel
from patterns.base import BasePattern


class CardTestingPattern(BasePattern):

    pattern_name = FraudPattern.CARD_TESTING

    # burst_size: how many micro-transactions per scenario
    BURST_MIN = 4
    BURST_MAX = 12

    def generate(self) -> List[TransactionEvent]:
        customer    = self.pool.random_customer(self.rng)
        scenario_id = self._scenario_id()
        burst_size  = self.rng.randint(self.BURST_MIN, self.BURST_MAX)

        # Attacker uses a NEW unknown device and a single IP
        attacker_device = self.pool.random_device(self.rng)
        attacker_ip     = self.pool.random_ip(self.rng)

        # New device = not in customer's known device list
        is_new_device = attacker_device not in customer.owned_devices
        is_new_ip     = attacker_ip not in customer.known_ips

        # Geo: same location for all burst txns (attacker doesn't move)
        geo = customer.home_location

        txns: List[TransactionEvent] = []
        for i in range(burst_size):
            # Micro-amounts: $0.01 – $4.99
            amount  = round(self.rng.uniform(0.01, 4.99), 2)
            # Each txn hits a different merchant to evade simple same-merchant rules
            merchant = self.pool.random_merchant(self.rng)

            txns.append(self._base_txn(
                customer          = customer,
                amount            = amount,
                channel           = Channel.WEB,
                merchant          = merchant,
                device_id         = attacker_device,
                ip_address        = attacker_ip,
                is_new_device     = is_new_device,
                is_new_ip         = is_new_ip,
                country_code      = geo["country"],
                city              = geo["city"],
                lat               = geo["lat"],
                lng               = geo["lng"],
                is_fraud          = True,
                fraud_pattern     = FraudPattern.CARD_TESTING,
                fraud_scenario_id = scenario_id,
            ))

        return txns
