"""
patterns/velocity_attack.py

Velocity Attack:
Fraudster rapidly fires many medium-to-large transactions in a very short
window before the account is flagged or blocked — draining available credit
as fast as possible.

Signals:
  - Unusually high transaction count in 1-minute / 5-minute window
  - Total spend in window far exceeds customer's normal daily spend
  - Mix of channels (WEB + MOBILE) to evade single-channel rules
  - Same device, different merchants
  - Amounts in a consistent mid-to-high band (not micro like card testing)
"""

from __future__ import annotations

from typing import List

from models.transaction import TransactionEvent, FraudPattern, Channel
from patterns.base import BasePattern


class VelocityAttackPattern(BasePattern):

    pattern_name = FraudPattern.VELOCITY_ATTACK

    BURST_MIN = 5
    BURST_MAX = 20

    def generate(self) -> List[TransactionEvent]:
        customer    = self.pool.random_customer(self.rng)
        scenario_id = self._scenario_id()
        burst_size  = self.rng.randint(self.BURST_MIN, self.BURST_MAX)

        # May use customer's own device (compromised) or a new one
        use_known_device = self.rng.random() < 0.5 and customer.owned_devices
        device_id   = (
            self.rng.choice(customer.owned_devices) if use_known_device
            else self.pool.random_device(self.rng)
        )
        is_new_device = device_id not in customer.owned_devices

        attacker_ip = self.pool.random_ip(self.rng)
        is_new_ip   = attacker_ip not in customer.known_ips

        geo = customer.home_location

        # Amount band: mid-to-high relative to customer average
        amount_min = customer.avg_txn_amount * 1.5
        amount_max = customer.avg_txn_amount * 4.0

        txns: List[TransactionEvent] = []
        channels = [Channel.WEB, Channel.MOBILE, Channel.CARD_NETWORK]

        for _ in range(burst_size):
            amount   = round(self.rng.uniform(amount_min, amount_max), 2)
            merchant = self.pool.random_merchant(self.rng)
            channel  = self.rng.choice(channels)

            txns.append(self._base_txn(
                customer          = customer,
                amount            = amount,
                channel           = channel,
                merchant          = merchant,
                device_id         = device_id,
                ip_address        = attacker_ip,
                is_new_device     = is_new_device,
                is_new_ip         = is_new_ip,
                country_code      = geo["country"],
                city              = geo["city"],
                lat               = geo["lat"],
                lng               = geo["lng"],
                is_fraud          = True,
                fraud_pattern     = FraudPattern.VELOCITY_ATTACK,
                fraud_scenario_id = scenario_id,
            ))

        return txns
