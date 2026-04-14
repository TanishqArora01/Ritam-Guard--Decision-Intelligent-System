#!/usr/bin/env python3
"""
scripts/load_test.py
Load Test — Fraud Detection System

Validates the system can sustain the target throughput (1k–10k TPS).
Uses concurrent async HTTP requests against POST /transaction.

Modes:
  --mode ramp     Gradually ramp from 10 → target TPS over 60s
  --mode constant Sustain a constant TPS for --duration seconds
  --mode spike    10s baseline → 5s spike to 5x target → 10s recovery

Usage:
  python3 scripts/load_test.py --tps 500 --duration 30
  python3 scripts/load_test.py --tps 1000 --mode ramp --duration 60
  python3 scripts/load_test.py --tps 200 --mode spike
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

GATEWAY_URL = "http://localhost:8000"

BOLD  = "\033[1m"
GREEN = "\033[92m"
RED   = "\033[91m"
AMBER = "\033[93m"
CYAN  = "\033[96m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Transaction factory
# ---------------------------------------------------------------------------

CHANNELS  = ["WEB", "MOBILE", "POS", "ATM", "CARD_NETWORK"]
COUNTRIES = ["IN", "US", "GB", "AE", "DE", "FR"]
SEGMENTS  = ["standard", "premium", "new", "risky"]
MERCHANTS = ["grocery", "electronics", "restaurants", "fuel", "online_retail", "jewelry"]

_FRAUD_PATTERNS = [
    # (probability_weight, overrides)
    (0.92, {}),   # legitimate
    (0.02, {"amount": 1.99,   "is_new_device": True,  "fraud_pattern": "card_testing"}),
    (0.02, {"amount": 3500.0, "is_new_device": True,  "fraud_pattern": "account_takeover",
             "country_code": "NG"}),
    (0.02, {"amount": 280.0,  "fraud_pattern": "velocity_attack"}),
    (0.02, {"amount": 12000.0,"fraud_pattern": "large_amount"}),
]
_WEIGHTS = [p[0] for p in _FRAUD_PATTERNS]


def make_transaction(rng: random.Random) -> dict:
    """Generate a realistic synthetic transaction for load testing."""
    idx = rng.choices(range(len(_FRAUD_PATTERNS)), weights=_WEIGHTS, k=1)[0]
    overrides = _FRAUD_PATTERNS[idx][1]

    base = {
        "txn_id":          str(uuid.uuid4()),
        "customer_id":     f"lt-cust-{rng.randint(1, 2000):05d}",
        "amount":          round(rng.lognormvariate(4.5, 0.8), 2),
        "currency":        "USD",
        "channel":         rng.choice(CHANNELS),
        "merchant_id":     f"MER-{rng.randint(1, 500):04d}",
        "merchant_category": rng.choice(MERCHANTS),
        "device_id":       f"DEV-{rng.randint(1, 3000):05d}",
        "ip_address":      f"{rng.randint(1,254)}.{rng.randint(0,254)}.{rng.randint(0,254)}.{rng.randint(1,254)}",
        "is_new_device":   rng.random() < 0.05,
        "is_new_ip":       rng.random() < 0.08,
        "country_code":    rng.choice(COUNTRIES),
        "clv":             round(rng.uniform(500, 50000), 2),
        "trust_score":     round(rng.uniform(0.2, 0.99), 3),
        "account_age_days":rng.randint(1, 1825),
        "customer_segment":rng.choice(SEGMENTS),
        # Pre-computed features (avoids Redis round-trip in load test)
        "features": {
            "txn_count_1m":   rng.randint(0, 15),
            "txn_count_5m":   rng.randint(0, 20),
            "txn_count_1h":   rng.randint(0, 30),
            "txn_count_24h":  rng.randint(0, 50),
            "amount_sum_1m":  round(rng.uniform(0, 500), 2),
            "amount_sum_5m":  round(rng.uniform(0, 1000), 2),
            "amount_sum_1h":  round(rng.uniform(0, 3000), 2),
            "amount_sum_24h": round(rng.uniform(0, 8000), 2),
            "geo_velocity_kmh":     round(rng.exponential(30), 2),
            "is_new_country":       rng.random() < 0.04,
            "unique_countries_24h": rng.randint(1, 3),
            "device_trust_score":   round(rng.uniform(0, 1), 3),
            "is_new_device":        rng.random() < 0.05,
            "ip_txn_count_1h":      rng.randint(0, 10),
            "unique_devices_24h":   rng.randint(1, 3),
            "amount_vs_avg_ratio":  round(rng.lognormvariate(0, 0.5), 3),
            "merchant_familiarity": round(rng.uniform(0, 1), 3),
            "hours_since_last_txn": round(rng.uniform(0, 72), 2),
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class RunStats:
    latencies_ms: List[float] = field(default_factory=list)
    errors:       int = 0
    successes:    int = 0
    early_exits:  int = 0
    actions:      dict = field(default_factory=dict)
    start:        float = field(default_factory=time.monotonic)

    def record(self, latency_ms: float, body: Optional[dict], error: bool):
        if error:
            self.errors += 1
        else:
            self.latencies_ms.append(latency_ms)
            self.successes += 1
            if body:
                action = body.get("action", "UNKNOWN")
                self.actions[action] = self.actions.get(action, 0) + 1
                if body.get("early_exit"):
                    self.early_exits += 1

    def summary(self) -> dict:
        lats = sorted(self.latencies_ms)
        n    = max(len(lats), 1)
        elapsed = max(time.monotonic() - self.start, 0.001)
        return {
            "total":         self.successes + self.errors,
            "successes":     self.successes,
            "errors":        self.errors,
            "error_rate_pct":round(self.errors / max(self.successes + self.errors, 1) * 100, 2),
            "tps":           round(self.successes / elapsed, 1),
            "elapsed_s":     round(elapsed, 1),
            "early_exit_pct":round(self.early_exits / max(self.successes, 1) * 100, 1),
            "p50_ms":        round(lats[int(n * 0.50)] if lats else 0, 1),
            "p90_ms":        round(lats[int(n * 0.90)] if lats else 0, 1),
            "p95_ms":        round(lats[int(n * 0.95)] if lats else 0, 1),
            "p99_ms":        round(lats[int(n * 0.99)] if lats else 0, 1),
            "avg_ms":        round(statistics.mean(lats) if lats else 0, 1),
            "actions":       self.actions,
        }


# ---------------------------------------------------------------------------
# Async worker
# ---------------------------------------------------------------------------

async def worker(
    client:     httpx.AsyncClient,
    gateway:    str,
    run_stats:  RunStats,
    rng:        random.Random,
    stop_event: asyncio.Event,
    target_interval: float,   # seconds between requests for this worker
):
    while not stop_event.is_set():
        txn = make_transaction(rng)
        t0  = time.perf_counter()
        try:
            resp = await client.post(
                f"{gateway}/transaction",
                json    = txn,
                timeout = 2.0,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                run_stats.record(latency_ms, resp.json(), error=False)
            else:
                run_stats.record(latency_ms, None, error=True)
        except Exception:
            latency_ms = (time.perf_counter() - t0) * 1000
            run_stats.record(latency_ms, None, error=True)

        if target_interval > 0:
            await asyncio.sleep(target_interval)


# ---------------------------------------------------------------------------
# Load test runner
# ---------------------------------------------------------------------------

async def run_constant(gateway: str, tps: int, duration: int, concurrency: int) -> RunStats:
    """Sustain a constant TPS for duration seconds."""
    run_stats   = RunStats()
    stop_event  = asyncio.Event()
    interval    = concurrency / tps   # each worker's sleep between requests

    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=concurrency + 50,
                            max_keepalive_connections=concurrency),
    ) as client:
        workers = [
            asyncio.create_task(worker(
                client, gateway, run_stats,
                random.Random(i * 1000),
                stop_event,
                target_interval=interval,
            ))
            for i in range(concurrency)
        ]

        # Progress reporting
        async def reporter():
            last_count = 0
            t_last = time.monotonic()
            for _ in range(duration):
                await asyncio.sleep(1)
                now_count = run_stats.successes
                elapsed   = time.monotonic() - t_last
                instant_tps = (now_count - last_count) / elapsed
                p95 = sorted(run_stats.latencies_ms)[int(len(run_stats.latencies_ms)*0.95)] \
                      if len(run_stats.latencies_ms) > 10 else 0
                print(f"\r  t={time.monotonic()-run_stats.start:5.0f}s  "
                      f"TPS={instant_tps:6.0f}  "
                      f"ok={run_stats.successes:6d}  "
                      f"err={run_stats.errors:4d}  "
                      f"p95={p95:5.0f}ms  "
                      f"early_exit={run_stats.early_exits:4d}",
                      end="", flush=True)
                last_count = now_count
                t_last     = time.monotonic()

        reporter_task = asyncio.create_task(reporter())
        await asyncio.sleep(duration)
        stop_event.set()
        reporter_task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    print()
    return run_stats


async def run_ramp(gateway: str, target_tps: int, duration: int, concurrency: int) -> RunStats:
    """Ramp from 10 TPS to target over duration seconds."""
    print(f"  Ramping 10 → {target_tps} TPS over {duration}s")
    run_stats  = RunStats()
    stop_event = asyncio.Event()

    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=concurrency + 50,
                            max_keepalive_connections=concurrency),
    ) as client:
        ramp_start = time.monotonic()

        async def adaptive_worker(worker_id: int):
            rng = random.Random(worker_id * 1000)
            while not stop_event.is_set():
                elapsed_frac = min(1.0, (time.monotonic() - ramp_start) / duration)
                current_tps  = 10 + (target_tps - 10) * elapsed_frac
                interval     = concurrency / current_tps
                txn = make_transaction(rng)
                t0  = time.perf_counter()
                try:
                    resp = await client.post(f"{gateway}/transaction", json=txn, timeout=2.0)
                    ms   = (time.perf_counter() - t0) * 1000
                    run_stats.record(ms, resp.json() if resp.status_code == 200 else None,
                                     error=resp.status_code != 200)
                except Exception:
                    run_stats.record((time.perf_counter()-t0)*1000, None, error=True)
                if interval > 0:
                    await asyncio.sleep(interval)

        workers = [asyncio.create_task(adaptive_worker(i)) for i in range(concurrency)]
        for elapsed in range(duration):
            await asyncio.sleep(1)
            frac = elapsed / duration
            cur  = int(10 + (target_tps - 10) * frac)
            print(f"\r  t={elapsed:3d}s  target={cur:5d} TPS  actual={run_stats.successes/(elapsed+1):5.0f} TPS  "
                  f"err={run_stats.errors}", end="", flush=True)
        stop_event.set()
        await asyncio.gather(*workers, return_exceptions=True)

    print()
    return run_stats


async def run_spike(gateway: str, base_tps: int, concurrency: int) -> RunStats:
    """10s baseline → 5s spike at 5x → 10s recovery."""
    print(f"  Spike test: {base_tps} TPS → {base_tps*5} TPS → {base_tps} TPS")
    run_stats  = RunStats()
    stop_event = asyncio.Event()

    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=concurrency * 6,
                            max_keepalive_connections=concurrency * 5),
    ) as client:
        spike_schedule = [(10, base_tps), (5, base_tps*5), (10, base_tps)]
        t_start = time.monotonic()

        async def spike_worker(worker_id: int):
            rng = random.Random(worker_id * 1000)
            phase_start = time.monotonic()
            phase_idx   = 0
            phases      = spike_schedule
            while not stop_event.is_set():
                elapsed = time.monotonic() - phase_start
                if phase_idx < len(phases) - 1 and elapsed >= phases[phase_idx][0]:
                    phase_idx  += 1
                    phase_start = time.monotonic()
                _, cur_tps = phases[phase_idx]
                interval   = concurrency / max(cur_tps, 1)
                txn = make_transaction(rng)
                t0  = time.perf_counter()
                try:
                    resp = await client.post(f"{gateway}/transaction", json=txn, timeout=2.0)
                    ms   = (time.perf_counter() - t0) * 1000
                    run_stats.record(ms, resp.json() if resp.status_code == 200 else None,
                                     error=resp.status_code != 200)
                except Exception:
                    run_stats.record((time.perf_counter()-t0)*1000, None, error=True)
                if interval > 0:
                    await asyncio.sleep(interval)

        total = sum(d for d, _ in spike_schedule)
        workers = [asyncio.create_task(spike_worker(i)) for i in range(concurrency * 6)]
        for t in range(total):
            await asyncio.sleep(1)
            phase_elapsed = t
            phase, label  = "baseline", base_tps
            if phase_elapsed >= 10 and phase_elapsed < 15:
                phase, label = "SPIKE", base_tps * 5
            elif phase_elapsed >= 15:
                phase, label = "recovery", base_tps
            print(f"\r  t={t:3d}s [{phase:<8}] target={label:5d} TPS  "
                  f"actual={run_stats.successes/(t+1):5.0f} TPS  err={run_stats.errors}",
                  end="", flush=True)
        stop_event.set()
        await asyncio.gather(*workers, return_exceptions=True)

    print()
    return run_stats


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(s: dict, target_tps: int):
    print()
    print(f"{'─'*55}")
    print(f"{BOLD}Load Test Results{RESET}")
    print(f"{'─'*55}")
    print(f"  Total requests : {s['total']:,}")
    print(f"  Successes      : {s['successes']:,}")
    error_color = RED if s['error_rate_pct'] > 1 else GREEN
    print(f"  Errors         : {s['errors']:,} ({error_color}{s['error_rate_pct']}%{RESET})")
    print(f"  Elapsed        : {s['elapsed_s']}s")
    tps_color = GREEN if s['tps'] >= target_tps * 0.9 else (AMBER if s['tps'] >= target_tps * 0.7 else RED)
    print(f"  Actual TPS     : {tps_color}{s['tps']:,.1f}{RESET}  (target: {target_tps})")
    print(f"  Early exits    : {s['early_exit_pct']}% of decisions")
    print()
    print(f"  Latency percentiles:")
    p50_color  = GREEN if s['p50_ms'] < 50   else AMBER
    p95_color  = GREEN if s['p95_ms'] < 200  else (AMBER if s['p95_ms'] < 500  else RED)
    p99_color  = GREEN if s['p99_ms'] < 1000 else RED
    print(f"    p50 = {p50_color}{s['p50_ms']:6.1f}ms{RESET}   (SLO: < 50ms)")
    print(f"    p90 = {s['p90_ms']:6.1f}ms")
    print(f"    p95 = {p95_color}{s['p95_ms']:6.1f}ms{RESET}   (SLO: < 200ms)")
    print(f"    p99 = {p99_color}{s['p99_ms']:6.1f}ms{RESET}   (SLO: < 1000ms)")
    print(f"    avg = {s['avg_ms']:6.1f}ms")
    print()
    print(f"  Action distribution:")
    for action, count in sorted(s['actions'].items(), key=lambda x: -x[1]):
        pct = count / max(s['successes'], 1) * 100
        bar = "█" * int(pct / 2)
        print(f"    {action:<16} {count:6,}  ({pct:5.1f}%)  {bar}")
    print()
    passed = s['tps'] >= target_tps * 0.8 and s['error_rate_pct'] < 2.0
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  SLO result: {status}")
    print(f"{'─'*55}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Fraud detection load test")
    parser.add_argument("--gateway",     default=GATEWAY_URL, help="Gateway URL")
    parser.add_argument("--tps",         type=int,   default=200,      help="Target TPS")
    parser.add_argument("--duration",    type=int,   default=30,       help="Duration (seconds)")
    parser.add_argument("--concurrency", type=int,   default=0,        help="Concurrent workers (0=auto)")
    parser.add_argument("--mode",        default="constant",
                        choices=["constant", "ramp", "spike"], help="Test mode")
    args = parser.parse_args()

    concurrency = args.concurrency or max(10, args.tps // 20)

    print(f"\n{BOLD}Fraud Detection — Load Test{RESET}")
    print(f"  Gateway     : {args.gateway}")
    print(f"  Mode        : {args.mode}")
    print(f"  Target TPS  : {args.tps}")
    print(f"  Duration    : {args.duration}s")
    print(f"  Concurrency : {concurrency} workers")
    print()

    # Health check
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{args.gateway}/health", timeout=5)
            r.raise_for_status()
        print(f"  {GREEN}✓{RESET} Gateway healthy\n")
    except Exception as e:
        print(f"  {RED}✗{RESET} Gateway unreachable: {e}")
        print("  → Run 'make up-all' and wait for all services to be healthy")
        sys.exit(1)

    print(f"  Starting {args.mode} test...\n")

    if args.mode == "constant":
        run_stats = await run_constant(args.gateway, args.tps, args.duration, concurrency)
    elif args.mode == "ramp":
        run_stats = await run_ramp(args.gateway, args.tps, args.duration, concurrency)
    else:
        run_stats = await run_spike(args.gateway, args.tps, concurrency)

    print_report(run_stats.summary(), args.tps)


if __name__ == "__main__":
    asyncio.run(main())
