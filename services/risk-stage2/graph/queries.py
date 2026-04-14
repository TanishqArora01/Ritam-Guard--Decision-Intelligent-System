"""
graph/queries.py
All 5 Neo4j fraud graph detection queries.
Each returns (score: float 0-1, evidence: dict).
Graceful degradation: returns (0.0, {}) when Neo4j unavailable.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
from config import config
logger = logging.getLogger(__name__)

import math

# ---------------------------------------------------------------------------
# 1. Fraud Ring — shared device/IP across customers
# ---------------------------------------------------------------------------
FRAUD_RING_QUERY = """
MATCH (c:Customer {customer_id: $customer_id})-[:USED]->(d:Device)<-[:USED]-(other:Customer)
WHERE other.customer_id <> $customer_id
WITH collect(DISTINCT other.customer_id) AS ring_members,
     collect(DISTINCT d.device_id)       AS shared_devs
OPTIONAL MATCH (c)-[:FROM_IP]->(ip:IPAddress)<-[:FROM_IP]-(ip_other:Customer)
WHERE ip_other.customer_id <> $customer_id
WITH ring_members, shared_devs,
     collect(DISTINCT ip_other.customer_id) AS ip_members,
     collect(DISTINCT ip.address)           AS shared_ips
RETURN size(ring_members) AS device_shared_count,
       size(ip_members)   AS ip_shared_count,
       shared_devs AS shared_devices, shared_ips AS shared_ips,
       ring_members + ip_members AS all_connected
LIMIT 1
"""

def fraud_ring_score(client, customer_id: str, device_id: str) -> Tuple[float, Dict]:
    if not client.available: return 0.0, {}
    try:
        rows = client.run(FRAUD_RING_QUERY, {"customer_id": customer_id})
        if not rows: return 0.0, {}
        r = rows[0]
        raw = max(int(r.get("device_shared_count", 0)), int(r.get("ip_shared_count", 0)))
        score = round(min(1.0, raw / (config.fraud_ring_min_shared + 3)), 4)
        return score, {
            "shared_devices":      list(r.get("shared_devices", []))[:5],
            "shared_ips":          list(r.get("shared_ips", []))[:5],
            "connected_customers": list(r.get("all_connected", []))[:10],
        }
    except Exception as e:
        logger.debug("fraud_ring_score: %s", e); return 0.0, {}

# ---------------------------------------------------------------------------
# 2. Mule Account — high in-degree transaction nodes
# ---------------------------------------------------------------------------
MULE_ACCOUNT_QUERY = """
MATCH (c:Customer {customer_id: $customer_id})<-[:SENT]-(inbound:Transaction)
WITH count(inbound) AS inbound_count
MATCH (c)-[:SENT]->(outbound:Transaction)
WITH inbound_count, count(outbound) AS outbound_count
RETURN inbound_count, outbound_count,
       CASE WHEN outbound_count = 0 THEN 999
            ELSE toFloat(inbound_count) / outbound_count END AS in_out_ratio
LIMIT 1
"""

def mule_account_score(client, customer_id: str) -> Tuple[float, Dict]:
    if not client.available: return 0.0, {}
    try:
        rows = client.run(MULE_ACCOUNT_QUERY, {"customer_id": customer_id})
        if not rows: return 0.0, {}
        r = rows[0]
        inbound  = int(r.get("inbound_count", 0))
        in_ratio = float(r.get("in_out_ratio", 0.0))
        count_s  = min(1.0, inbound / config.mule_indegree_threshold)
        ratio_s  = min(1.0, (in_ratio - 1.0) / 9.0) if in_ratio > 1 else 0.0
        score    = round(count_s * 0.6 + ratio_s * 0.4, 4)
        return score, {"inbound_txn_count": inbound,
                       "outbound_txn_count": int(r.get("outbound_count", 0)),
                       "in_out_ratio": round(float(in_ratio), 2)}
    except Exception as e:
        logger.debug("mule_account_score: %s", e); return 0.0, {}

# ---------------------------------------------------------------------------
# 3. Synthetic Identity — age vs activity mismatch
# ---------------------------------------------------------------------------
SYNTHETIC_ID_QUERY = """
MATCH (c:Customer {customer_id: $customer_id})
OPTIONAL MATCH (c)-[:SENT]->(t:Transaction)
WITH c, count(t) AS total_txns
RETURN c.account_age_days AS account_age_days, total_txns,
       CASE WHEN c.account_age_days IS NULL OR c.account_age_days = 0 THEN 1000
            ELSE toFloat(total_txns) / c.account_age_days END AS txn_per_day
LIMIT 1
"""

def synthetic_identity_score(client, customer_id: str, account_age_days: int) -> Tuple[float, Dict]:
    if not client.available: return 0.0, {}
    try:
        rows = client.run(SYNTHETIC_ID_QUERY, {"customer_id": customer_id})
        if not rows: return 0.0, {}
        r = rows[0]
        age      = int(r.get("account_age_days", account_age_days) or account_age_days)
        total    = int(r.get("total_txns", 0))
        rate     = float(r.get("txn_per_day", 0.0))
        score    = 0.0
        if age < config.synthetic_id_age_days and total > 10:
            score = min(1.0, total / 50.0)
        if rate > 5.0:
            score = max(score, min(1.0, rate / 20.0))
        return round(score, 4), {"account_age_days": age, "total_txns": total,
                                  "txn_per_day": round(rate, 3)}
    except Exception as e:
        logger.debug("synthetic_identity_score: %s", e); return 0.0, {}

# ---------------------------------------------------------------------------
# 4. Velocity Graph — burst edges in transaction graph
# ---------------------------------------------------------------------------
VELOCITY_GRAPH_QUERY = """
MATCH (c:Customer {customer_id: $customer_id})-[:SENT]->(t:Transaction)
WHERE t.ts >= $window_start
WITH count(t) AS burst_count, sum(t.amount) AS burst_amount,
     collect(DISTINCT t.country_code) AS burst_countries
RETURN burst_count, burst_amount, size(burst_countries) AS unique_countries
LIMIT 1
"""

def velocity_graph_score(client, customer_id: str) -> Tuple[float, Dict]:
    if not client.available: return 0.0, {}
    try:
        window_start = (datetime.now(timezone.utc) -
                        timedelta(minutes=config.velocity_burst_window_min)).isoformat()
        rows = client.run(VELOCITY_GRAPH_QUERY,
                          {"customer_id": customer_id, "window_start": window_start})
        if not rows: return 0.0, {}
        r = rows[0]
        burst     = int(r.get("burst_count", 0))
        countries = int(r.get("unique_countries", 1))
        count_s   = min(1.0, burst / config.velocity_burst_threshold)
        country_s = min(1.0, (countries - 1) / 3.0)
        score     = round(count_s * 0.7 + country_s * 0.3, 4)
        return score, {"burst_txn_count": burst,
                       "burst_amount": float(r.get("burst_amount", 0) or 0),
                       "unique_burst_countries": countries}
    except Exception as e:
        logger.debug("velocity_graph_score: %s", e); return 0.0, {}

# ---------------------------------------------------------------------------
# 5. Multi-Hop Fraud Propagation — indirect network connections
# ---------------------------------------------------------------------------
MULTI_HOP_QUERY = """
MATCH path = (c:Customer {customer_id: $customer_id})
             -[:USED|FROM_IP*1..3]->(shared)
             <-[:USED|FROM_IP*1..3]-(suspect:Customer)
WHERE suspect.customer_id <> $customer_id
  AND suspect.trust_score < $trust_threshold
WITH suspect, length(path) AS hops,
     [n IN nodes(path) | labels(n)[0] + ':' +
      coalesce(n.customer_id, n.device_id, n.address, '?')] AS path_nodes
ORDER BY suspect.trust_score ASC, hops ASC
LIMIT $max_results
RETURN collect(suspect.customer_id) AS suspect_ids,
       min(hops)                    AS min_hops,
       min(suspect.trust_score)     AS min_trust,
       path_nodes
"""

def multi_hop_score(client, customer_id: str) -> Tuple[float, Dict]:
    if not client.available: return 0.0, {}
    try:
        rows = client.run(MULTI_HOP_QUERY, {
            "customer_id":     customer_id,
            "trust_threshold": 0.30,
            "max_results":     10,
        })
        if not rows: return 0.0, {}
        r        = rows[0]
        suspects = list(r.get("suspect_ids", []))
        min_hops = int(r.get("min_hops", 999) or 999)
        min_trust= float(r.get("min_trust", 1.0) or 1.0)
        if not suspects: return 0.0, {}
        hop_decay    = {1: 1.0, 2: 0.6, 3: 0.3}.get(min_hops, 0.0)
        trust_signal = 1.0 - min_trust
        score        = round(min(1.0, hop_decay * trust_signal * len(suspects) / 3.0), 4)
        path_nodes   = list(r.get("path_nodes", []))
        summary      = " → ".join(path_nodes[:6]) if path_nodes else ""
        return score, {"suspect_customers": suspects[:5], "min_hops": min_hops,
                       "min_suspect_trust": round(min_trust, 3), "hop_path_summary": summary}
    except Exception as e:
        logger.debug("multi_hop_score: %s", e); return 0.0, {}

# ---------------------------------------------------------------------------
# Orchestrator — run all 5 and return a combined dict
# ---------------------------------------------------------------------------

def run_all_graph_queries(client, customer_id: str,
                          device_id: str, account_age_days: int) -> Dict:
    """Run all 5 graph queries. Gracefully returns zeros if Neo4j unavailable."""
    base = {"neo4j_available": client.available,
            "shared_devices": [], "shared_ips": [],
            "connected_customers": [], "hop_path_summary": ""}

    if not client.available:
        return {"graph_risk_score": 0.0, "fraud_ring_score": 0.0,
                "mule_account_score": 0.0, "synthetic_identity_score": 0.0,
                "velocity_graph_score": 0.0, "multi_hop_score": 0.0, **base}

    ring_s,  ring_ev  = fraud_ring_score(client, customer_id, device_id)
    mule_s,  mule_ev  = mule_account_score(client, customer_id)
    synth_s, synth_ev = synthetic_identity_score(client, customer_id, account_age_days)
    vel_s,   vel_ev   = velocity_graph_score(client, customer_id)
    hop_s,   hop_ev   = multi_hop_score(client, customer_id)

    combined = round(min(1.0,
        ring_s*0.30 + mule_s*0.20 + synth_s*0.15 + vel_s*0.15 + hop_s*0.20), 4)

    base["shared_devices"]      = ring_ev.get("shared_devices", [])
    base["shared_ips"]          = ring_ev.get("shared_ips", [])
    base["connected_customers"] = ring_ev.get("connected_customers", [])
    base["hop_path_summary"]    = hop_ev.get("hop_path_summary", "")

    return {"graph_risk_score": combined, "fraud_ring_score": ring_s,
            "mule_account_score": mule_s, "synthetic_identity_score": synth_s,
            "velocity_graph_score": vel_s, "multi_hop_score": hop_s, **base}
