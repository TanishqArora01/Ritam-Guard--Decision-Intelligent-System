from __future__ import annotations

import random
from app.models import GraphNode, GraphEdge


def generate_graph(
    user_id: str,
    device_id: str,
    ip_address: str,
    merchant: str,
    risk_score: float,
) -> dict:
    """
    Build an entity graph for a transaction.

    Nodes: user, device, ip, merchant-account
    Edges: used_device, connected_from, same_session, (optionally) shared_device
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    user_risk = round(risk_score * (0.8 + random.uniform(0, 0.4)), 4)
    user_risk = min(user_risk, 1.0)

    device_risk = round(risk_score * (0.6 + random.uniform(0, 0.5)), 4)
    device_risk = min(device_risk, 1.0)

    ip_risk = round(risk_score * (0.5 + random.uniform(0, 0.6)), 4)
    ip_risk = min(ip_risk, 1.0)

    merchant_risk = round(random.uniform(0, 0.4), 4)

    nodes.append(
        GraphNode(
            id=user_id,
            type="user",
            label=user_id,
            risk_score=user_risk,
            suspicious=user_risk > 0.6,
        )
    )
    nodes.append(
        GraphNode(
            id=device_id,
            type="device",
            label=device_id,
            risk_score=device_risk,
            suspicious=device_risk > 0.6,
        )
    )
    nodes.append(
        GraphNode(
            id=ip_address,
            type="ip",
            label=ip_address,
            risk_score=ip_risk,
            suspicious=ip_risk > 0.6,
        )
    )
    merchant_id = f"MERCH_{merchant.replace(' ', '_').upper()}"
    nodes.append(
        GraphNode(
            id=merchant_id,
            type="account",
            label=merchant,
            risk_score=merchant_risk,
            suspicious=merchant_risk > 0.7,
        )
    )

    edges.append(
        GraphEdge(
            source=user_id,
            target=device_id,
            weight=round(random.uniform(0.5, 1.0), 3),
            type="used_device",
        )
    )
    edges.append(
        GraphEdge(
            source=user_id,
            target=ip_address,
            weight=round(random.uniform(0.4, 1.0), 3),
            type="connected_from",
        )
    )
    edges.append(
        GraphEdge(
            source=device_id,
            target=ip_address,
            weight=round(random.uniform(0.3, 1.0), 3),
            type="same_session",
        )
    )
    edges.append(
        GraphEdge(
            source=user_id,
            target=merchant_id,
            weight=round(random.uniform(0.2, 1.0), 3),
            type="transaction",
        )
    )

    # Simulate shared-device fraud: sometimes a device is linked to another user
    if risk_score > 0.5 and random.random() < 0.3:
        alt_user = f"USR_{random.randint(1, 9999):04d}"
        nodes.append(
            GraphNode(
                id=alt_user,
                type="user",
                label=alt_user,
                risk_score=round(random.uniform(0.4, 0.9), 4),
                suspicious=True,
            )
        )
        edges.append(
            GraphEdge(
                source=alt_user,
                target=device_id,
                weight=round(random.uniform(0.6, 1.0), 3),
                type="shared_device",
            )
        )

    return {
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
    }
