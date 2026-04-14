"""
features/geography.py
Geography feature computation.

Produces 3 features:
  geo_velocity_kmh     — speed between last and current location
  is_new_country       — country code never seen before for this customer
  unique_countries_24h — distinct countries in last 24 hours

The geo_velocity_kmh feature is the single most powerful signal for
geographic impossibility fraud: a value > 800 km/h between consecutive
transactions is physically impossible for ground/air travel.

Formula:
  speed = distance_km / time_hours
  distance = haversine(last_lat, last_lng, cur_lat, cur_lng)
  time      = (cur_ts - last_ts) / 3600
"""
from __future__ import annotations

import logging
import math
import time
from typing import Dict, Optional, Tuple

from store.redis_store import RedisStore
from config import config

logger = logging.getLogger(__name__)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Great-circle distance in km between two (lat, lng) points.
    Uses the Haversine formula — accurate to within ~0.3% for Earth.
    """
    R    = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a    = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2.0 * R * math.asin(math.sqrt(max(0.0, a)))


class GeographyFeatures:

    def __init__(self, store: RedisStore):
        self.store = store

    def compute(
        self,
        customer_id:  str,
        country_code: str,
        lat:          float,
        lng:          float,
        txn_ts:       float,
    ) -> Dict[str, object]:
        """
        Compute geography features for the current transaction.

        Args:
            customer_id:  unique customer identifier
            country_code: ISO-2 country code of current transaction
            lat, lng:     GPS coordinates of current transaction
            txn_ts:       transaction Unix timestamp

        Returns:
            dict with 3 geography features
        """
        try:
            geo_velocity_kmh     = 0.0
            is_new_country       = False
            unique_countries_24h = 1

            # --- geo_velocity_kmh ---
            last = self.store.get_last_location(customer_id)
            if last is not None:
                last_lat, last_lng, last_ts = last
                distance_km = haversine_km(last_lat, last_lng, lat, lng)
                elapsed_sec = max(txn_ts - last_ts, 1.0)  # avoid div/0
                elapsed_h   = elapsed_sec / 3600.0
                geo_velocity_kmh = round(distance_km / elapsed_h, 2)

            # --- is_new_country ---
            known_countries = self.store.get_country_set(customer_id)
            is_new_country  = country_code not in known_countries

            # --- unique_countries_24h ---
            unique_countries_24h = max(1, len(known_countries) + (1 if is_new_country else 0))

            # --- Update state ---
            self.store.set_last_location(customer_id, lat, lng, txn_ts)
            self.store.add_country(customer_id, country_code)

            return {
                "geo_velocity_kmh":     geo_velocity_kmh,
                "is_new_country":       is_new_country,
                "unique_countries_24h": unique_countries_24h,
            }

        except Exception as e:
            logger.warning("GeographyFeatures.compute failed for %s: %s", customer_id, e)
            return {
                "geo_velocity_kmh":     0.0,
                "is_new_country":       False,
                "unique_countries_24h": 1,
            }
