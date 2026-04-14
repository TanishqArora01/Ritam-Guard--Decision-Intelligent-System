"""
Standalone scoring microservice.

Exposes a simple HTTP endpoint:
  POST /score
  Body: {"user_id": ..., "amount": ..., "ip_address": ...,
         "merchant": ..., "merchant_category": ...,
         "location": ..., "device_id": ...}
  Response: RiskScore JSON

Can also be imported as a library.

Usage:
  python scorer.py --port 8002
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False

# ---------------------------------------------------------------------------
# In-process velocity store
# ---------------------------------------------------------------------------
_velocity: dict[str, list[float]] = defaultdict(list)
BLACKLISTED_IPS = {"10.0.0.99", "192.168.1.254", "10.10.10.10"}
HIGH_RISK_MERCHANTS = {"CryptoExchange", "OnlineGambling", "WireTransfer"}
CAT_RISK = {
    "gambling": 0.9, "crypto": 0.85, "travel": 0.3, "retail": 0.1,
    "food": 0.05, "entertainment": 0.15, "utilities": 0.05,
    "healthcare": 0.1, "electronics": 0.35, "finance": 0.5,
}


def _velocity_score(user_id: str, ts: float) -> float:
    hist = _velocity[user_id]
    hist.append(ts)
    _velocity[user_id] = [t for t in hist if t > ts - 60]
    return min(len(_velocity[user_id]) / 10.0, 1.0)


def stage1(user_id: str, amount: float, ip: str, merchant: str, ts: float) -> tuple[float, dict]:
    f: dict[str, float] = {
        "amount_high": min(max((amount - 10_000) / 40_000, 0.0), 1.0),
        "blacklisted_ip": 1.0 if ip in BLACKLISTED_IPS else 0.0,
        "high_risk_merchant": 1.0 if merchant in HIGH_RISK_MERCHANTS else 0.0,
        "velocity": _velocity_score(user_id, ts),
        "round_amount": 1.0 if amount == int(amount) and amount % 100 == 0 else 0.0,
    }
    score = (
        0.30 * f["amount_high"]
        + 0.25 * f["blacklisted_ip"]
        + 0.20 * f["high_risk_merchant"]
        + 0.20 * f["velocity"]
        + 0.05 * f["round_amount"]
    )
    score = max(0.0, min(score + random.uniform(-0.03, 0.03), 1.0))
    return round(score, 4), f


def stage2(
    user_id: str, amount: float, cat: str, location: str, device_id: str, s1: float
) -> tuple[float, dict]:
    uh = abs(hash(user_id)) % 100 / 100.0
    geo = abs(hash(location + user_id)) % 1000 / 1000.0 * s1 * 0.5
    dev = (1.0 - abs(hash(device_id)) % 100 / 100.0) * 0.2
    cat_r = CAT_RISK.get(cat.lower(), 0.2)
    exp_amt = 50 + uh * 500
    dev_amt = min(abs(amount - exp_amt) / max(exp_amt, 1) / 10, 1.0)
    f: dict[str, float] = {
        "user_risk_baseline": round(uh * 0.3, 4),
        "geo_anomaly": round(geo, 4),
        "device_age_score": round(dev, 4),
        "merchant_category_risk": round(cat_r, 4),
        "amount_deviation": round(dev_amt, 4),
    }
    score = (
        0.25 * f["user_risk_baseline"]
        + 0.20 * f["geo_anomaly"]
        + 0.15 * f["device_age_score"]
        + 0.25 * f["merchant_category_risk"]
        + 0.15 * f["amount_deviation"]
    )
    score = max(0.0, min(score + random.uniform(-0.05, 0.05), 1.0))
    return round(score, 4), f


def score_transaction(data: dict) -> dict:
    s1, f1 = stage1(
        data["user_id"], data["amount"], data["ip_address"],
        data["merchant"], time.time()
    )
    s2, f2 = stage2(
        data["user_id"], data["amount"], data["merchant_category"],
        data["location"], data["device_id"], s1
    )
    final = round(0.45 * s1 + 0.55 * s2, 4)
    if final < 0.3:
        decision, conf = "APPROVE", round(1.0 - final / 0.3 * 0.3, 4)
    elif final < 0.7:
        decision, conf = "REVIEW", round(0.5 + abs(final - 0.5) / 0.4 * 0.4, 4)
    else:
        decision, conf = "BLOCK", round(min((final - 0.7) / 0.3 * 0.5 + 0.5, 0.99), 4)

    all_f = {**{k: v * 0.5 for k, v in f1.items()}, **{k: v * 0.5 for k, v in f2.items()}}
    total = sum(abs(v) for v in all_f.values()) or 1.0
    explanation = sorted(
        [
            {"feature": k, "contribution": round(v / total * final, 4),
             "direction": "increase" if v > 0 else "decrease"}
            for k, v in all_f.items()
        ],
        key=lambda x: abs(x["contribution"]),
        reverse=True,
    )[:10]

    return {
        "stage1_score": s1, "stage2_score": s2, "final_score": final,
        "decision": decision, "confidence": conf,
        "stage1_features": f1, "stage2_features": f2,
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------
class ScorerHandler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # type: ignore[override]
        pass

    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"status": "ok", "service": "scoring-engine"})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/score":
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            result = score_transaction(data)
            self._json(result)
        except Exception as exc:
            self._json({"error": str(exc)}, 400)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RitamGuard scoring engine")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    print(f"[scoring-engine] Listening on :{args.port}")
    HTTPServer(("0.0.0.0", args.port), ScorerHandler).serve_forever()
