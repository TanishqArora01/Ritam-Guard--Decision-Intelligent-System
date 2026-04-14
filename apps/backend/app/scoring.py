from __future__ import annotations

import random
import math
from app.models import RiskScore


BLACKLISTED_IPS = {"10.0.0.99", "192.168.1.254", "10.10.10.10"}
HIGH_RISK_MERCHANTS = {"CryptoExchange", "OnlineGambling", "WireTransfer"}

# Simulated velocity tracker: user_id -> list of recent timestamps (in-memory)
_velocity_store: dict[str, list[float]] = {}


def _velocity_score(user_id: str, timestamp: float) -> float:
    """Return a 0-1 score based on transaction frequency in last 60 s."""
    history = _velocity_store.setdefault(user_id, [])
    history.append(timestamp)
    # keep only last 60 seconds
    cutoff = timestamp - 60
    _velocity_store[user_id] = [t for t in history if t > cutoff]
    count = len(_velocity_store[user_id])
    # >5 txns/min is suspicious
    return min(count / 10.0, 1.0)


def stage1_score(
    user_id: str,
    amount: float,
    ip_address: str,
    merchant: str,
    timestamp: float,
) -> tuple[float, dict]:
    """Rule-based pre-screening. Returns (score 0-1, feature dict)."""
    features: dict[str, float] = {}

    # Amount feature
    if amount > 10_000:
        features["amount_high"] = min((amount - 10_000) / 40_000, 1.0)
    elif amount < 1:
        features["amount_high"] = 0.0
        features["amount_suspicious_low"] = 0.8
    else:
        features["amount_high"] = 0.0

    # Blacklisted IP
    features["blacklisted_ip"] = 1.0 if ip_address in BLACKLISTED_IPS else 0.0

    # High-risk merchant
    features["high_risk_merchant"] = 1.0 if merchant in HIGH_RISK_MERCHANTS else 0.0

    # Velocity
    features["velocity"] = _velocity_score(user_id, timestamp)

    # Round-number amounts (card-testing signal)
    features["round_amount"] = 1.0 if amount == int(amount) and amount % 100 == 0 else 0.0

    score = (
        0.30 * features["amount_high"]
        + 0.25 * features["blacklisted_ip"]
        + 0.20 * features["high_risk_merchant"]
        + 0.20 * features["velocity"]
        + 0.05 * features["round_amount"]
    )
    # add slight noise
    score = min(score + random.uniform(-0.03, 0.03), 1.0)
    score = max(score, 0.0)
    return round(score, 4), features


def stage2_score(
    user_id: str,
    amount: float,
    merchant_category: str,
    location: str,
    device_id: str,
    stage1: float,
) -> tuple[float, dict]:
    """Behavioural ML simulation. Returns (score 0-1, feature dict)."""
    features: dict[str, float] = {}

    # Simulate user baseline (deterministic from user hash)
    user_hash = abs(hash(user_id)) % 100 / 100.0
    features["user_risk_baseline"] = round(user_hash * 0.3, 4)  # max 0.3

    # Geo anomaly: random but weighted by stage1
    geo_seed = abs(hash(location + user_id)) % 1000 / 1000.0
    features["geo_anomaly"] = round(geo_seed * stage1 * 0.5, 4)

    # Device age (new device = higher risk)
    device_seed = abs(hash(device_id)) % 100 / 100.0
    features["device_age_score"] = round((1.0 - device_seed) * 0.2, 4)

    # Merchant category risk
    cat_risk = {
        "gambling": 0.9,
        "crypto": 0.85,
        "travel": 0.3,
        "retail": 0.1,
        "food": 0.05,
        "entertainment": 0.15,
        "utilities": 0.05,
        "healthcare": 0.1,
        "electronics": 0.35,
        "finance": 0.5,
    }
    features["merchant_category_risk"] = cat_risk.get(merchant_category.lower(), 0.2)

    # Amount vs user baseline deviation
    expected_amount = 50 + user_hash * 500
    deviation = abs(amount - expected_amount) / max(expected_amount, 1)
    features["amount_deviation"] = round(min(deviation / 10, 1.0), 4)

    score = (
        0.25 * features["user_risk_baseline"]
        + 0.20 * features["geo_anomaly"]
        + 0.15 * features["device_age_score"]
        + 0.25 * features["merchant_category_risk"]
        + 0.15 * features["amount_deviation"]
    )
    score = min(score + random.uniform(-0.05, 0.05), 1.0)
    score = max(score, 0.0)
    return round(score, 4), features


def _generate_explanation(
    stage1_features: dict,
    stage2_features: dict,
    final_score: float,
) -> list[dict]:
    """Generate SHAP-like feature contribution list."""
    contributions = []
    all_features = {
        **{k: v * 0.5 for k, v in stage1_features.items()},
        **{k: v * 0.5 for k, v in stage2_features.items()},
    }
    total = sum(abs(v) for v in all_features.values()) or 1.0
    for feature, raw_value in all_features.items():
        contribution = raw_value / total * final_score
        contributions.append(
            {
                "feature": feature,
                "contribution": round(contribution, 4),
                "direction": "increase" if contribution > 0 else "decrease",
            }
        )
    contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return contributions[:10]


def compute_risk_score(
    user_id: str,
    amount: float,
    ip_address: str,
    merchant: str,
    merchant_category: str,
    location: str,
    device_id: str,
    timestamp: float,
) -> RiskScore:
    s1, s1_features = stage1_score(user_id, amount, ip_address, merchant, timestamp)
    s2, s2_features = stage2_score(user_id, amount, merchant_category, location, device_id, s1)

    # Ensemble: weighted combination
    final = round(0.45 * s1 + 0.55 * s2, 4)

    if final < 0.3:
        decision = "APPROVE"
        confidence = round(1.0 - final / 0.3 * 0.3, 4)
    elif final < 0.7:
        decision = "REVIEW"
        confidence = round(0.5 + abs(final - 0.5) / 0.4 * 0.4, 4)
    else:
        decision = "BLOCK"
        confidence = round(min((final - 0.7) / 0.3 * 0.5 + 0.5, 0.99), 4)

    explanation = _generate_explanation(s1_features, s2_features, final)

    return RiskScore(
        stage1_score=s1,
        stage2_score=s2,
        final_score=final,
        decision=decision,
        confidence=confidence,
        stage1_features=s1_features,
        stage2_features=s2_features,
        explanation=explanation,
    )
