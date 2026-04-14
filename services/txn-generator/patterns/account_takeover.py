"""
patterns/account_takeover.py

Account Takeover (ATO) Attack:
Attacker obtains credentials (phishing, credential stuffing, data breach)
and initiates high-value transactions from a new device in a new location —
often a high-risk country different from the customer's home.

Signals:
  - Brand new device (never seen for this customer)
  - New IP address and geolocation
  - Country different from customer's home country
  - Unusually high transaction amount relative to customer's average
  - WEB or MOBILE channel
  - Often targets premium customers (higher CLV = higher reward)
"""

from __future__ import annotations

import random
from typing import List

from models.transaction import TransactionEvent, FraudPattern, Channel
from models.customer_pool import GEO_LOCATIONS, HIGH_RISK_CATEGORIES
from patterns.base import BasePattern


# Countries considered elevated-risk for ATO origin
HIGH_RISK_COUNTRIES = {"NG", "RO", "UA", "RU", "KP", "IR"}

# Locations used as ATO origin geo
ATO_GEO_POOL = [g for g in GEO_LOCATIONS if g["country"] in HIGH_RISK_COUNTRIES]
# Fallback if pool is empty for some reason
if not ATO_GEO_POOL:
    ATO_GEO_POOL = GEO_LOCATIONS[-3:]


class AccountTakeoverPattern(BasePattern):

    pattern_name = FraudPattern.ACCOUNT_TAKEOVER

    def generate(self) -> List[TransactionEvent]:
        # Prefer premium / standard customers — higher value targets
        premium_pool = (
            self.pool.customers_by_segment("premium") +
            self.pool.customers_by_segment("standard")
        )
        customer = self.rng.choice(premium_pool) if premium_pool else self.pool.random_customer(self.rng)

        scenario_id = self._scenario_id()

        # Attacker origin: different country from customer's home
        ato_geo = self.rng.choice(ATO_GEO_POOL)

        # Ensure the attacker's country differs from customer's home
        attempts = 0
        while ato_geo["country"] == customer.home_location["country"] and attempts < 5:
            ato_geo  = self.rng.choice(ATO_GEO_POOL)
            attempts += 1

        # Completely new device and IP
        attacker_device = self.pool.random_device(self.rng)
        attacker_ip     = self.pool.random_ip(self.rng)

        is_new_device = attacker_device not in customer.owned_devices
        is_new_ip     = attacker_ip not in customer.known_ips

        # High-value merchant (luxury, jewelry, electronics, wire transfer)
        risky_merchant = next(
            (m for m in self.rng.sample(self.pool.all_merchants, 20)
             if m["category"] in HIGH_RISK_CATEGORIES),
            self.pool.random_merchant(self.rng)
        )

        # Amount: 5–15x the customer's average transaction
        amount = round(customer.avg_txn_amount * self.rng.uniform(5.0, 15.0), 2)
        amount = max(amount, 500.0)

        # ATO is typically 1–2 transactions (attacker moves fast then out)
        txn = self._base_txn(
            customer          = customer,
            amount            = amount,
            channel           = self.rng.choice([Channel.WEB, Channel.MOBILE]),
            merchant          = risky_merchant,
            device_id         = attacker_device,
            ip_address        = attacker_ip,
            is_new_device     = is_new_device,
            is_new_ip         = is_new_ip,
            country_code      = ato_geo["country"],
            city              = ato_geo["city"],
            lat               = ato_geo["lat"],
            lng               = ato_geo["lng"],
            is_fraud          = True,
            fraud_pattern     = FraudPattern.ACCOUNT_TAKEOVER,
            fraud_scenario_id = scenario_id,
        )
        return [txn]
