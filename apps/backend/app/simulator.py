from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from app.models import Transaction
from app.scoring import compute_risk_score
from app.graph import generate_graph

BroadcastCallback = Callable[[str, str], Awaitable[None]]

# ---------------------------------------------------------------------------
# Global in-memory stores (shared with routes)
# ---------------------------------------------------------------------------
transactions: deque[Transaction] = deque(maxlen=1000)
cases: dict[str, dict] = {}
metrics_history: deque[dict] = deque(maxlen=60)

# WebSocket broadcast callback – injected by the WS manager at startup
_broadcast_callback: Optional[BroadcastCallback] = None

# ---------------------------------------------------------------------------
# Static mock data
# ---------------------------------------------------------------------------
MERCHANTS = [
    ("Amazon", "retail"),
    ("Walmart", "retail"),
    ("Netflix", "entertainment"),
    ("Spotify", "entertainment"),
    ("Apple Store", "electronics"),
    ("Best Buy", "electronics"),
    ("Uber", "travel"),
    ("Lyft", "travel"),
    ("DoorDash", "food"),
    ("Chipotle", "food"),
    ("Delta Airlines", "travel"),
    ("Marriott Hotels", "travel"),
    ("CVS Pharmacy", "healthcare"),
    ("Walgreens", "healthcare"),
    ("Verizon", "utilities"),
    ("AT&T", "utilities"),
    ("CryptoExchange", "crypto"),
    ("OnlineGambling", "gambling"),
    ("WireTransfer", "finance"),
    ("Robinhood", "finance"),
]

LOCATIONS = [
    "New York, NY",
    "Los Angeles, CA",
    "Chicago, IL",
    "Houston, TX",
    "Phoenix, AZ",
    "Philadelphia, PA",
    "San Antonio, TX",
    "San Diego, CA",
    "Dallas, TX",
    "San Jose, CA",
    "Austin, TX",
    "Jacksonville, FL",
    "London, UK",
    "Toronto, CA",
    "Sydney, AU",
]

OS_TYPES = ["ios", "android", "windows", "macos", "linux"]

_transaction_count = 0
_blocked_count = 0
_approved_count = 0
_review_count = 0
_latencies: deque[float] = deque(maxlen=200)


def _random_ip() -> str:
    prefixes = ["192.168", "10.0", "172.16", "10.10"]
    prefix = random.choice(prefixes)
    # occasionally inject blacklisted IP
    if random.random() < 0.03:
        return "10.0.0.99"
    return f"{prefix}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def _random_device() -> str:
    os_type = random.choice(OS_TYPES)
    num = random.randint(1000, 9999)
    return f"DEV_{os_type}_{num}"


def _generate_transaction() -> Transaction:
    """Create a single realistic mock transaction through the scoring pipeline."""
    global _transaction_count, _blocked_count, _approved_count, _review_count

    user_id = f"USR_{random.randint(1, 100):04d}"
    device_id = _random_device()
    ip_address = _random_ip()
    merchant_name, merchant_category = random.choice(MERCHANTS)
    location = random.choice(LOCATIONS)

    # Occasionally simulate fraud patterns
    roll = random.random()
    if roll < 0.05:
        # velocity attack: tiny amounts
        amount = round(random.uniform(0.01, 1.0), 2)
    elif roll < 0.10:
        # large suspicious transfer
        amount = round(random.uniform(9_500, 50_000), 2)
    else:
        amount = round(random.uniform(10, 3_000), 2)

    t0 = time.perf_counter()
    risk = compute_risk_score(
        user_id=user_id,
        amount=amount,
        ip_address=ip_address,
        merchant=merchant_name,
        merchant_category=merchant_category,
        location=location,
        device_id=device_id,
        timestamp=time.time(),
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    _latencies.append(latency_ms)

    graph = generate_graph(user_id, device_id, ip_address, merchant_name, risk.final_score)

    status_map = {"APPROVE": "approved", "REVIEW": "under_review", "BLOCK": "blocked"}
    status = status_map[risk.decision]

    txn = Transaction(
        id=f"TXN_{uuid.uuid4().hex[:12].upper()}",
        timestamp=datetime.now(timezone.utc),
        user_id=user_id,
        amount=amount,
        merchant=merchant_name,
        merchant_category=merchant_category,
        location=location,
        device_id=device_id,
        ip_address=ip_address,
        risk_score=risk,
        graph=graph,
        status=status,
    )

    _transaction_count += 1
    if status == "blocked":
        _blocked_count += 1
    elif status == "approved":
        _approved_count += 1
    else:
        _review_count += 1

    return txn


def compute_metrics() -> dict:
    return _compute_metrics()


def _compute_metrics() -> dict:
    latency_list = sorted(_latencies)
    n = len(latency_list)

    def percentile(p: float) -> float:
        if not latency_list:
            return 0.0
        idx = int(n * p / 100)
        return round(latency_list[min(idx, n - 1)], 2)

    fraud_rate = round(_blocked_count / max(_transaction_count, 1), 4)
    fpr = round(_review_count / max(_transaction_count, 1) * 0.15, 4)

    return {
        "tps": round(random.uniform(1.5, 3.5), 2),
        "latency_p50": percentile(50),
        "latency_p95": percentile(95),
        "latency_p99": percentile(99),
        "fraud_rate": fraud_rate,
        "false_positive_rate": fpr,
        "total_transactions": _transaction_count,
        "blocked_transactions": _blocked_count,
        "approved_transactions": _approved_count,
        "under_review_transactions": _review_count,
    }


async def run_simulator() -> None:
    """Asyncio background task: continuously generates transactions."""
    while True:
        delay = random.uniform(0.5, 2.0)
        await asyncio.sleep(delay)

        txn = _generate_transaction()
        transactions.appendleft(txn)

        # Broadcast transaction to WebSocket clients
        if _broadcast_callback is not None:
            try:
                await _broadcast_callback("transactions", txn.model_dump_json())
            except Exception:
                pass

        # Every ~10 transactions snapshot metrics
        if _transaction_count % 10 == 0:
            snap = _compute_metrics()
            metrics_history.appendleft(snap)
            if _broadcast_callback is not None:
                try:
                    import json
                    await _broadcast_callback("metrics", json.dumps(snap))
                except Exception:
                    pass


def set_broadcast_callback(cb) -> None:
    global _broadcast_callback
    _broadcast_callback = cb
