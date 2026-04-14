"""
patterns/fraud_ring.py

Fraud Ring (Organised Crime / Mule Network):
Multiple distinct customer accounts (often synthetic identities or mule
accounts) transact using the SAME shared device or IP address, indicating
they are operated by a single attacker or criminal group.

This is the pattern that Graph Intelligence (Neo4j) is specifically designed
to detect — the entity linkage between customers via shared devices/IPs.

Signals:
  - Multiple different customer IDs sharing the same device_id
  - Multiple different customer IDs sharing the same ip_address
  - Transactions spread across many merchants in a short window
  - Each individual account appears normal in isolation
  - Detectable ONLY through graph traversal (shared-device edges)
"""

from __future__ import annotations

from typing import List

from models.transaction import TransactionEvent, FraudPattern, Channel
from patterns.base import BasePattern


class FraudRingPattern(BasePattern):

    pattern_name = FraudPattern.FRAUD_RING

    RING_SIZE_MIN = 3   # minimum number of accounts in the ring
    RING_SIZE_MAX = 8   # maximum number of accounts in the ring

    def generate(self) -> List[TransactionEvent]:
        scenario_id = self._scenario_id()
        ring_size   = self.rng.randint(self.RING_SIZE_MIN, self.RING_SIZE_MAX)

        # The shared infrastructure — one device and one IP used across all ring members
        shared_device = self.pool.random_device(self.rng)
        shared_ip     = self.pool.random_ip(self.rng)

        # Select ring_size distinct customers (preferably "risky" or "new" — mule profiles)
        risky_pool = (
            self.pool.customers_by_segment("risky") +
            self.pool.customers_by_segment("new")
        )
        if len(risky_pool) >= ring_size:
            ring_members = self.rng.sample(risky_pool, ring_size)
        else:
            ring_members = self.rng.sample(self.pool.customers, ring_size)

        txns: List[TransactionEvent] = []

        for customer in ring_members:
            # Each ring member makes 1–3 transactions using the shared device/IP
            n_txns = self.rng.randint(1, 3)
            for _ in range(n_txns):
                merchant = self.pool.random_merchant(self.rng)

                # Amounts: moderate — not suspicious individually
                amount = round(
                    self.rng.uniform(
                        customer.avg_txn_amount * 0.8,
                        customer.avg_txn_amount * 2.5,
                    ), 2
                )

                # Geo: use the shared device's implied location
                geo = self.rng.choice([
                    customer.home_location,
                    customer.home_location,  # weight home 2x
                    self.pool.random_merchant(self.rng),  # sometimes a merchant geo
                ])
                if isinstance(geo, dict) and "lat" in geo:
                    country = geo.get("country_code", geo.get("country", "US"))
                    city    = geo.get("city", "Unknown")
                    lat     = geo["lat"]
                    lng     = geo["lng"]
                else:
                    country = customer.home_location["country"]
                    city    = customer.home_location["city"]
                    lat     = customer.home_location["lat"]
                    lng     = customer.home_location["lng"]

                is_new_device = shared_device not in customer.owned_devices
                is_new_ip     = shared_ip not in customer.known_ips

                txns.append(self._base_txn(
                    customer          = customer,
                    amount            = amount,
                    channel           = self.rng.choice([Channel.WEB, Channel.MOBILE, Channel.POS]),
                    merchant          = merchant,
                    device_id         = shared_device,
                    ip_address        = shared_ip,
                    is_new_device     = is_new_device,
                    is_new_ip         = is_new_ip,
                    country_code      = country,
                    city              = city,
                    lat               = lat,
                    lng               = lng,
                    is_fraud          = True,
                    fraud_pattern     = FraudPattern.FRAUD_RING,
                    fraud_scenario_id = scenario_id,
                ))

        return txns
