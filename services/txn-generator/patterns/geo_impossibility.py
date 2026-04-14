"""
patterns/geo_impossibility.py

Geographic Impossibility:
The same customer account makes transactions in two geographically distant
locations within a timeframe that is physically impossible to travel between.

Example: Transaction in Mumbai at T=0, then transaction in New York at T+2min.
The distance (>13,000 km) divided by time implies >6,500,000 km/h — impossible.

Signals:
  - Same customer_id in two very different countries in rapid succession
  - Distance between locations implies impossible travel speed (> 1000 km/h)
  - Detectable via: geo_velocity_km_h feature computed by Flink
  - One of the two transactions is always the fraudulent one (the foreign one)

Note: We emit TWO transactions — one legitimate home transaction, then one
foreign fraudulent one. The Flink geo-velocity feature will flag the pair.
"""

from __future__ import annotations

import math
from typing import List

from models.transaction import TransactionEvent, FraudPattern, Channel
from models.customer_pool import GEO_LOCATIONS
from patterns.base import BasePattern


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in km."""
    R    = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a    = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class GeoImpossibilityPattern(BasePattern):

    pattern_name = FraudPattern.GEO_IMPOSSIBILITY

    # Minimum distance to qualify as "impossible" (km)
    MIN_DISTANCE_KM = 3_000

    def generate(self) -> List[TransactionEvent]:
        customer    = self.pool.random_customer(self.rng)
        scenario_id = self._scenario_id()

        home_geo   = customer.home_location
        home_lat   = home_geo["lat"]
        home_lng   = home_geo["lng"]

        # Find a distant location (>3000 km from home)
        distant_geo = self._find_distant_geo(home_lat, home_lng)

        # --- Transaction 1: Legitimate home transaction ---
        home_device = (
            self.rng.choice(customer.owned_devices)
            if customer.owned_devices else self.pool.random_device(self.rng)
        )
        home_ip = (
            self.rng.choice(customer.known_ips)
            if customer.known_ips else self.pool.random_ip(self.rng)
        )
        home_merchant = self.pool.random_merchant(self.rng)
        home_amount   = round(customer.avg_txn_amount * self.rng.uniform(0.5, 1.5), 2)

        txn_home = self._base_txn(
            customer          = customer,
            amount            = home_amount,
            channel           = customer.preferred_channel,
            merchant          = home_merchant,
            device_id         = home_device,
            ip_address        = home_ip,
            is_new_device     = False,
            is_new_ip         = False,
            country_code      = home_geo["country"],
            city              = home_geo["city"],
            lat               = home_lat,
            lng               = home_lng,
            is_fraud          = False,
            fraud_pattern     = FraudPattern.LEGITIMATE,
            fraud_scenario_id = scenario_id,
        )

        # --- Transaction 2: Fraudulent distant transaction (seconds later) ---
        foreign_device = self.pool.random_device(self.rng)
        foreign_ip     = self.pool.random_ip(self.rng)
        foreign_merchant = self.pool.random_merchant(self.rng)
        # Higher amount — attacker makes it count
        foreign_amount = round(customer.avg_txn_amount * self.rng.uniform(2.0, 8.0), 2)

        txn_foreign = self._base_txn(
            customer          = customer,
            amount            = foreign_amount,
            channel           = self.rng.choice([Channel.WEB, Channel.CARD_NETWORK]),
            merchant          = foreign_merchant,
            device_id         = foreign_device,
            ip_address        = foreign_ip,
            is_new_device     = True,
            is_new_ip         = True,
            country_code      = distant_geo["country"],
            city              = distant_geo["city"],
            lat               = distant_geo["lat"],
            lng               = distant_geo["lng"],
            is_fraud          = True,
            fraud_pattern     = FraudPattern.GEO_IMPOSSIBILITY,
            fraud_scenario_id = scenario_id,
        )

        return [txn_home, txn_foreign]

    def _find_distant_geo(self, home_lat: float, home_lng: float) -> dict:
        """Return a geo location at least MIN_DISTANCE_KM from home."""
        candidates = [
            g for g in GEO_LOCATIONS
            if _haversine_km(home_lat, home_lng, g["lat"], g["lng"]) >= self.MIN_DISTANCE_KM
        ]
        if not candidates:
            # Fallback: pick the farthest available
            candidates = sorted(
                GEO_LOCATIONS,
                key=lambda g: _haversine_km(home_lat, home_lng, g["lat"], g["lng"]),
                reverse=True,
            )
        return self.rng.choice(candidates[:5])
