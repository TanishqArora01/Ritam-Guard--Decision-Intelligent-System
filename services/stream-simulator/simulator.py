"""
Standalone stream simulator.

Can run in two modes:
  1. poster  – POST generated transactions to the backend API (default)
  2. server  – Act as a lightweight standalone HTTP/WebSocket mock server

Usage:
  python simulator.py --mode poster --url http://localhost:8000
  python simulator.py --mode server --port 8001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from faker import Faker
    fake = Faker()
    HAS_FAKER = True
except ImportError:
    fake = None  # type: ignore[assignment]
    HAS_FAKER = False

# ---------------------------------------------------------------------------
# Static data
# ---------------------------------------------------------------------------
MERCHANTS = [
    ("Amazon", "retail"), ("Walmart", "retail"), ("Netflix", "entertainment"),
    ("Spotify", "entertainment"), ("Apple Store", "electronics"),
    ("Best Buy", "electronics"), ("Uber", "travel"), ("Lyft", "travel"),
    ("DoorDash", "food"), ("Chipotle", "food"), ("Delta Airlines", "travel"),
    ("Marriott Hotels", "travel"), ("CVS Pharmacy", "healthcare"),
    ("Walgreens", "healthcare"), ("Verizon", "utilities"),
    ("AT&T", "utilities"), ("CryptoExchange", "crypto"),
    ("OnlineGambling", "gambling"), ("WireTransfer", "finance"),
    ("Robinhood", "finance"),
]
LOCATIONS = [
    "New York, NY", "Los Angeles, CA", "Chicago, IL", "Houston, TX",
    "Phoenix, AZ", "San Diego, CA", "Dallas, TX", "Austin, TX",
    "London, UK", "Toronto, CA", "Sydney, AU",
]
OS_TYPES = ["ios", "android", "windows", "macos", "linux"]


def _ip() -> str:
    prefix = random.choice(["192.168", "10.0", "172.16"])
    if random.random() < 0.03:
        return "10.0.0.99"  # blacklisted
    return f"{prefix}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def _make_transaction() -> dict:
    user_id = f"USR_{random.randint(1, 100):04d}"
    merchant, category = random.choice(MERCHANTS)
    roll = random.random()
    if roll < 0.05:
        amount = round(random.uniform(0.01, 1.0), 2)
    elif roll < 0.10:
        amount = round(random.uniform(9500, 50000), 2)
    else:
        amount = round(random.uniform(10, 3000), 2)

    return {
        "id": f"TXN_{uuid.uuid4().hex[:12].upper()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "amount": amount,
        "merchant": merchant,
        "merchant_category": category,
        "location": random.choice(LOCATIONS),
        "device_id": f"DEV_{random.choice(OS_TYPES)}_{random.randint(1000, 9999)}",
        "ip_address": _ip(),
    }


# ---------------------------------------------------------------------------
# Poster mode
# ---------------------------------------------------------------------------
async def run_poster(url: str) -> None:
    if not HAS_HTTPX:
        print("httpx not installed. Run: pip install httpx")
        return

    async with httpx.AsyncClient(base_url=url, timeout=5) as client:
        print(f"[poster] Sending transactions to {url}")
        while True:
            delay = random.uniform(0.5, 2.0)
            await asyncio.sleep(delay)
            txn = _make_transaction()
            try:
                # The backend generates its own transactions; this endpoint
                # is here for completeness / external injection demos.
                resp = await client.get("/health")
                if resp.status_code == 200:
                    print(f"[poster] backend healthy – would send {txn['id']}")
            except Exception as exc:
                print(f"[poster] error: {exc}")


# ---------------------------------------------------------------------------
# Standalone server mode
# ---------------------------------------------------------------------------
_mock_transactions: list[dict] = []


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # type: ignore[override]
        pass  # suppress default logging

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/transactions"):
            self._json({"total": len(_mock_transactions), "transactions": _mock_transactions[-50:]})
        elif self.path == "/health":
            self._json({"status": "ok", "service": "stream-simulator-standalone"})
        else:
            self._json({"error": "not found"}, 404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()


def _generate_loop() -> None:
    while True:
        time.sleep(random.uniform(0.5, 2.0))
        txn = _make_transaction()
        _mock_transactions.append(txn)
        if len(_mock_transactions) > 1000:
            _mock_transactions.pop(0)
        print(f"[server] generated {txn['id']} amount=${txn['amount']}")


def run_server(port: int) -> None:
    Thread(target=_generate_loop, daemon=True).start()
    print(f"[server] Mock transaction server listening on :{port}")
    HTTPServer(("0.0.0.0", port), MockHandler).serve_forever()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RitamGuard stream simulator")
    parser.add_argument("--mode", choices=["poster", "server"], default="server")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.mode == "poster":
        asyncio.run(run_poster(args.url))
    else:
        run_server(args.port)
