"""
dataset-pipeline/anonymiser.py
PII Anonymisation for dataset exports.

Strategy:
  customer_id  → deterministic SHA-256(salt + id) prefix "anon_"
                  deterministic so joins still work across tables
  device_id    → same SHA-256 approach → "dev_"
  ip_address   → last N octets zeroed: 192.168.1.234 → 192.168.0.0
  txn_id       → kept as-is (no PII, needed for audit joins)
  amount       → kept as-is (needed for ML training, not PII)
  lat/lng      → rounded to 2 decimal places (~1km precision)
  email        → if present: local-part hashed, domain kept
  free text    → dropped (analyst_notes, explanation stripped)

All anonymisation is deterministic within a dataset version:
  same input → same pseudonymous output → researcher can join tables
  different salt → completely different output → unlinkable across releases
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from typing import Any, Dict, Optional


class Anonymiser:
    def __init__(self, salt: str, ip_mask_octets: int = 2):
        self.salt          = salt.encode()
        self.ip_mask_octets= ip_mask_octets

    def _sha256(self, value: str) -> str:
        return hashlib.sha256(self.salt + value.encode()).hexdigest()[:16]

    # ---------------------------------------------------------------------------
    # Per-field anonymisation
    # ---------------------------------------------------------------------------

    def customer_id(self, raw: str) -> str:
        """Deterministic pseudonym: 'anon_a3f2b1c4d5e6f7a8'"""
        if not raw: return "anon_unknown"
        return f"anon_{self._sha256(raw)}"

    def device_id(self, raw: str) -> str:
        if not raw: return "dev_unknown"
        return f"dev_{self._sha256(raw)}"

    def ip_address(self, raw: str) -> str:
        """Zero last N octets: 192.168.1.234 → 192.168.0.0"""
        if not raw: return "0.0.0.0"
        try:
            addr  = ipaddress.ip_address(raw)
            parts = str(addr).split(".")
            if len(parts) == 4:
                parts[-self.ip_mask_octets:] = ["0"] * self.ip_mask_octets
                return ".".join(parts)
            return "0.0.0.0"
        except ValueError:
            return "0.0.0.0"

    def email(self, raw: str) -> str:
        """Hash local-part, keep domain: user@bank.com → a3f2b1@bank.com"""
        if not raw or "@" not in raw:
            return "anon@unknown.com"
        local, domain = raw.rsplit("@", 1)
        return f"{self._sha256(local)[:8]}@{domain}"

    def lat_lng(self, value: float) -> float:
        """Round to 2dp ≈ 1km precision."""
        return round(float(value), 2)

    def anonymise_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Anonymise a single row dict in-place (returns new dict).
        Handles both decision rows and transaction rows.
        """
        r = dict(row)

        if "customer_id" in r and r["customer_id"]:
            r["customer_id"] = self.customer_id(str(r["customer_id"]))
        if "device_id" in r and r["device_id"]:
            r["device_id"]   = self.device_id(str(r["device_id"]))
        if "ip_address" in r and r["ip_address"]:
            r["ip_address"]  = self.ip_address(str(r["ip_address"]))
        if "email" in r and r["email"]:
            r["email"]       = self.email(str(r["email"]))
        if "lat" in r:  r["lat"] = self.lat_lng(r.get("lat", 0))
        if "lng" in r:  r["lng"] = self.lat_lng(r.get("lng", 0))

        # Drop free-text fields that may contain PII
        for drop_key in ["analyst_notes", "raw_explanation", "merchant_name",
                          "cardholder_name", "billing_address"]:
            r.pop(drop_key, None)

        # Truncate explanation to key names only (no values that may contain PII)
        if "explanation" in r and isinstance(r["explanation"], dict):
            r["explanation"] = list(r["explanation"].keys())

        return r

    def anonymise_batch(self, rows: list) -> list:
        return [self.anonymise_row(r) for r in rows]
