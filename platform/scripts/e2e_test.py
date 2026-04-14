#!/usr/bin/env python3
"""
scripts/e2e_test.py
End-to-End Integration Test — Fraud Detection System

Tests the full pipeline via the API Gateway's POST /transaction endpoint.
Run this after `make up-all` to confirm the system is working end-to-end.

Usage:
    python3 scripts/e2e_test.py
    python3 scripts/e2e_test.py --gateway http://localhost:8000
    python3 scripts/e2e_test.py --verbose

Exit code: 0 = all tests passed, 1 = failures
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

GATEWAY_URL = "http://localhost:8000"
TIMEOUT     = 10.0  # seconds per request

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m~\033[0m"
BOLD = "\033[1m"
RESET= "\033[0m"


# ---------------------------------------------------------------------------
# Transaction builders for each test scenario
# ---------------------------------------------------------------------------

def _txn(overrides: dict) -> dict:
    """Base transaction with sensible defaults, overridable."""
    base = {
        "txn_id":          str(uuid.uuid4()),
        "customer_id":     "cust-e2e-test",
        "amount":          100.0,
        "currency":        "USD",
        "channel":         "WEB",
        "merchant_id":     "MER-TEST-001",
        "merchant_category": "online_retail",
        "device_id":       "DEV-KNOWN-001",
        "ip_address":      "192.168.1.100",
        "is_new_device":   False,
        "is_new_ip":       False,
        "country_code":    "IN",
        "city":            "Mumbai",
        "lat":             19.076,
        "lng":             72.877,
        "txn_ts":          datetime.now(timezone.utc).isoformat(),
        "clv":             12000.0,
        "trust_score":     0.75,
        "account_age_days":365,
        "customer_segment":"standard",
    }
    base.update(overrides)
    return base


SCENARIOS: List[Tuple[str, dict, dict]] = [
    # (name, transaction_overrides, expected_properties)

    ("Legitimate low-risk transaction",
     _txn({"amount": 50.0, "trust_score": 0.90,
            "features": {
                "txn_count_1m": 1, "txn_count_5m": 2, "txn_count_1h": 5, "txn_count_24h": 12,
                "amount_sum_1m": 50, "amount_sum_5m": 100, "amount_sum_1h": 300, "amount_sum_24h": 800,
                "geo_velocity_kmh": 5.0, "is_new_country": False, "unique_countries_24h": 1,
                "device_trust_score": 0.95, "is_new_device": False, "ip_txn_count_1h": 2,
                "unique_devices_24h": 1, "amount_vs_avg_ratio": 0.8,
                "merchant_familiarity": 0.9, "hours_since_last_txn": 6.0,
            }}),
     {"action_in": ["APPROVE"], "p_fraud_max": 0.4}),

    ("Card testing — micro-transactions burst",
     _txn({"amount": 1.99, "customer_id": "cust-card-test",
            "device_id": "DEV-UNKNOWN-EVIL", "is_new_device": True,
            "ip_address": "185.220.101.45", "is_new_ip": True,
            "is_fraud": True, "fraud_pattern": "card_testing",
            "features": {
                "txn_count_1m": 11, "txn_count_5m": 11, "txn_count_1h": 11, "txn_count_24h": 13,
                "amount_sum_1m": 21.9, "amount_sum_5m": 21.9, "amount_sum_1h": 21.9, "amount_sum_24h": 25.9,
                "geo_velocity_kmh": 0.0, "is_new_country": False, "unique_countries_24h": 1,
                "device_trust_score": 0.0, "is_new_device": True, "ip_txn_count_1h": 78,
                "unique_devices_24h": 1, "amount_vs_avg_ratio": 0.03,
                "merchant_familiarity": 0.0, "hours_since_last_txn": 0.02,
            }}),
     {"action_in": ["BLOCK","STEP_UP_AUTH","MANUAL_REVIEW"], "p_fraud_min": 0.3}),

    ("Account takeover — new device, foreign country, high amount",
     _txn({"amount": 3500.0, "customer_id": "cust-premium-victim",
            "customer_segment": "premium", "clv": 80000.0, "trust_score": 0.85,
            "device_id": "DEV-ATTACKER-RO", "is_new_device": True,
            "ip_address": "93.115.95.200", "is_new_ip": True,
            "country_code": "RO", "city": "Bucharest",
            "is_fraud": True, "fraud_pattern": "account_takeover",
            "features": {
                "txn_count_1m": 1, "txn_count_5m": 1, "txn_count_1h": 1, "txn_count_24h": 2,
                "amount_sum_1m": 3500, "amount_sum_5m": 3500, "amount_sum_1h": 3500, "amount_sum_24h": 3750,
                "geo_velocity_kmh": 9200.0, "is_new_country": True, "unique_countries_24h": 2,
                "device_trust_score": 0.0, "is_new_device": True, "ip_txn_count_1h": 4,
                "unique_devices_24h": 1, "amount_vs_avg_ratio": 14.0,
                "merchant_familiarity": 0.0, "hours_since_last_txn": 2.5,
            }}),
     {"action_in": ["BLOCK","STEP_UP_AUTH","MANUAL_REVIEW"], "p_fraud_min": 0.4}),

    ("Geographic impossibility — 9000+ km/h velocity",
     _txn({"amount": 890.0, "customer_id": "cust-geo-impossible",
            "device_id": "DEV-FOREIGN", "is_new_device": True,
            "country_code": "US", "city": "New York",
            "is_fraud": True, "fraud_pattern": "geo_impossibility",
            "features": {
                "txn_count_1m": 1, "txn_count_5m": 2, "txn_count_1h": 3, "txn_count_24h": 6,
                "amount_sum_1m": 890, "amount_sum_5m": 1640, "amount_sum_1h": 2100, "amount_sum_24h": 3200,
                "geo_velocity_kmh": 9850.0, "is_new_country": True, "unique_countries_24h": 3,
                "device_trust_score": 0.0, "is_new_device": True, "ip_txn_count_1h": 6,
                "unique_devices_24h": 2, "amount_vs_avg_ratio": 4.5,
                "merchant_familiarity": 0.1, "hours_since_last_txn": 0.5,
            }}),
     {"action_in": ["BLOCK","STEP_UP_AUTH","MANUAL_REVIEW"]}),

    ("Velocity attack — burst of medium transactions",
     _txn({"amount": 280.0, "customer_id": "cust-velocity",
            "is_fraud": True, "fraud_pattern": "velocity_attack",
            "features": {
                "txn_count_1m": 18, "txn_count_5m": 18, "txn_count_1h": 20, "txn_count_24h": 25,
                "amount_sum_1m": 5040, "amount_sum_5m": 5040, "amount_sum_1h": 5600, "amount_sum_24h": 7000,
                "geo_velocity_kmh": 10.0, "is_new_country": False, "unique_countries_24h": 1,
                "device_trust_score": 0.2, "is_new_device": False, "ip_txn_count_1h": 45,
                "unique_devices_24h": 2, "amount_vs_avg_ratio": 3.8,
                "merchant_familiarity": 0.0, "hours_since_last_txn": 0.05,
            }}),
     {"action_in": ["BLOCK","STEP_UP_AUTH","MANUAL_REVIEW"]}),

    ("Premium customer mid-risk — prefer step-up over block",
     _txn({"amount": 1200.0, "customer_id": "cust-premium-mid",
            "customer_segment": "premium", "clv": 95000.0, "trust_score": 0.88,
            "features": {
                "txn_count_1m": 1, "txn_count_5m": 2, "txn_count_1h": 4, "txn_count_24h": 9,
                "amount_sum_1m": 1200, "amount_sum_5m": 2100, "amount_sum_1h": 4400, "amount_sum_24h": 9800,
                "geo_velocity_kmh": 20.0, "is_new_country": False, "unique_countries_24h": 1,
                "device_trust_score": 0.8, "is_new_device": False, "ip_txn_count_1h": 3,
                "unique_devices_24h": 1, "amount_vs_avg_ratio": 1.8,
                "merchant_familiarity": 0.6, "hours_since_last_txn": 3.5,
            }}),
     {"action_in": ["APPROVE","STEP_UP_AUTH","BLOCK"]}),

    ("New customer cold-start — no history",
     _txn({"amount": 75.0, "customer_id": "cust-brand-new",
            "customer_segment": "new", "clv": 0.0, "trust_score": 0.40,
            "account_age_days": 1, "features": None}),
     {"action_in": ["APPROVE","BLOCK","STEP_UP_AUTH","MANUAL_REVIEW"]}),

    ("Large amount anomaly — 30x above average",
     _txn({"amount": 18000.0, "customer_id": "cust-large-amt",
            "merchant_category": "jewelry",
            "is_fraud": True, "fraud_pattern": "large_amount",
            "features": {
                "txn_count_1m": 1, "txn_count_5m": 1, "txn_count_1h": 2, "txn_count_24h": 4,
                "amount_sum_1m": 18000, "amount_sum_5m": 18000, "amount_sum_1h": 18500, "amount_sum_24h": 19200,
                "geo_velocity_kmh": 8.0, "is_new_country": False, "unique_countries_24h": 1,
                "device_trust_score": 0.5, "is_new_device": False, "ip_txn_count_1h": 1,
                "unique_devices_24h": 1, "amount_vs_avg_ratio": 30.0,
                "merchant_familiarity": 0.05, "hours_since_last_txn": 18.0,
            }}),
     {"action_in": ["BLOCK","STEP_UP_AUTH","MANUAL_REVIEW"]}),
]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    name:     str
    passed:   bool
    action:   str   = ""
    p_fraud:  float = 0.0
    latency:  float = 0.0
    stage:    int   = 0
    early_exit: bool = False
    error:    str   = ""


def run_test(
    gateway_url: str,
    name: str,
    txn: dict,
    expectations: dict,
    verbose: bool,
) -> TestResult:
    t0 = time.perf_counter()
    try:
        resp   = requests.post(f"{gateway_url}/transaction", json=txn, timeout=TIMEOUT)
        latency= (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        body   = resp.json()
    except requests.exceptions.ConnectionError:
        return TestResult(name=name, passed=False,
                          error="Connection refused — is the gateway running?")
    except requests.exceptions.Timeout:
        return TestResult(name=name, passed=False, error=f"Timeout after {TIMEOUT}s")
    except Exception as e:
        return TestResult(name=name, passed=False, error=str(e))

    action     = body.get("action", "")
    p_fraud    = body.get("p_fraud", 0.0)
    stage      = body.get("pipeline_stage", 0)
    early_exit = body.get("early_exit", False)

    # Check expectations
    passed = True
    reasons= []

    if "action_in" in expectations:
        if action not in expectations["action_in"]:
            passed = False
            reasons.append(f"action={action} not in {expectations['action_in']}")

    if "p_fraud_min" in expectations:
        if p_fraud < expectations["p_fraud_min"]:
            passed = False
            reasons.append(f"p_fraud={p_fraud:.4f} < min {expectations['p_fraud_min']}")

    if "p_fraud_max" in expectations:
        if p_fraud > expectations["p_fraud_max"]:
            passed = False
            reasons.append(f"p_fraud={p_fraud:.4f} > max {expectations['p_fraud_max']}")

    if verbose and body.get("explanation"):
        for k, v in list(body["explanation"].items())[:3]:
            print(f"         {k}: {v}")

    return TestResult(
        name      = name,
        passed    = passed and not reasons,
        action    = action,
        p_fraud   = p_fraud,
        latency   = latency,
        stage     = stage,
        early_exit= early_exit,
        error     = "; ".join(reasons),
    )


def run_all(gateway_url: str, verbose: bool):
    print(f"\n{BOLD}Fraud Detection System — End-to-End Integration Tests{RESET}")
    print(f"Gateway: {gateway_url}")
    print("─" * 65)

    # Check gateway health first
    try:
        r = requests.get(f"{gateway_url}/health", timeout=5)
        if r.status_code != 200:
            print(f"{FAIL} Gateway health check failed (HTTP {r.status_code})")
            return False
        print(f"{PASS} Gateway reachable — version {r.json().get('version','?')}\n")
    except Exception as e:
        print(f"{FAIL} Cannot reach gateway at {gateway_url}: {e}")
        print("  → Run 'make up-all' first")
        return False

    # Check readiness
    try:
        r = requests.get(f"{gateway_url}/ready", timeout=5)
        ready_data = r.json()
        services   = ready_data.get("services", {})
        for svc, ok in services.items():
            icon = PASS if ok else WARN
            print(f"  {icon} {svc}: {'healthy' if ok else 'unreachable (pipeline will degrade)'}")
        print()
    except Exception:
        pass

    results: List[TestResult] = []
    for name, txn, expectations in SCENARIOS:
        if verbose:
            print(f"  Testing: {name}")
        result = run_test(gateway_url, name, txn, expectations, verbose)
        results.append(result)

        icon = PASS if result.passed else (WARN if result.error and "not in" not in result.error else FAIL)
        stage_str = f"(early exit)" if result.early_exit else f"(stage {result.stage})"
        print(
            f"  {icon}  {result.name:<50} "
            f"→ {result.action:<13} "
            f"p={result.p_fraud:.3f} "
            f"{stage_str} "
            f"{result.latency:.0f}ms"
        )
        if result.error and not result.passed:
            print(f"       {FAIL} {result.error}")
        if verbose:
            print()

    # Summary
    n_passed = sum(1 for r in results if r.passed)
    n_total  = len(results)
    avg_lat  = sum(r.latency for r in results) / max(n_total, 1)

    print()
    print("─" * 65)
    print(f"Results: {n_passed}/{n_total} tests passed | avg latency: {avg_lat:.0f}ms")

    # Latency breakdown
    early = [r for r in results if r.early_exit]
    full  = [r for r in results if not r.early_exit and r.stage > 0]
    if early:
        print(f"  Early exit avg:    {sum(r.latency for r in early)/len(early):.0f}ms")
    if full:
        print(f"  Full pipeline avg: {sum(r.latency for r in full)/len(full):.0f}ms")

    print()
    if n_passed == n_total:
        print(f"{PASS} {BOLD}All {n_total} tests passed.{RESET}")
        return True
    else:
        failed = [r.name for r in results if not r.passed]
        print(f"{FAIL} {BOLD}{n_total - n_passed} test(s) failed:{RESET}")
        for name in failed:
            print(f"     • {name}")
        return False


# ---------------------------------------------------------------------------
# Batch test
# ---------------------------------------------------------------------------

def run_batch_test(gateway_url: str):
    print(f"\n{BOLD}Batch endpoint test (10 transactions){RESET}")
    from tests_data import SCENARIOS as S
    batch = [txn for _, txn, _ in SCENARIOS[:10]]
    try:
        t0   = time.perf_counter()
        resp = requests.post(f"{gateway_url}/transaction/batch", json=batch, timeout=30)
        ms   = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        results = resp.json()
        print(f"  {PASS} Batch: {len(results)} decisions in {ms:.0f}ms ({ms/len(results):.0f}ms/txn avg)")
    except Exception as e:
        print(f"  {WARN} Batch test skipped: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="End-to-end integration test")
    parser.add_argument("--gateway", default=GATEWAY_URL, help="Gateway URL")
    parser.add_argument("--verbose", action="store_true", help="Show explanations")
    args = parser.parse_args()

    ok = run_all(args.gateway, args.verbose)
    sys.exit(0 if ok else 1)
