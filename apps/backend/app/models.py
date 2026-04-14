from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class RiskScore(BaseModel):
    stage1_score: float
    stage2_score: float
    final_score: float
    decision: str  # APPROVE / REVIEW / BLOCK
    confidence: float
    stage1_features: dict
    stage2_features: dict
    explanation: list[dict]  # [{"feature": str, "contribution": float, "direction": str}]


class GraphNode(BaseModel):
    id: str
    type: str  # user / device / ip / account
    label: str
    risk_score: float
    suspicious: bool


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float
    type: str  # transaction / login / shared_device / used_device / connected_from / same_session


class Transaction(BaseModel):
    id: str
    timestamp: datetime
    user_id: str
    amount: float
    merchant: str
    merchant_category: str
    location: str
    device_id: str
    ip_address: str
    risk_score: RiskScore
    graph: dict  # {nodes: list[GraphNode], edges: list[GraphEdge]}
    status: str  # pending / approved / blocked / under_review


class Case(BaseModel):
    id: str
    transaction_id: str
    assigned_to: str
    status: str  # open / investigating / resolved / escalated
    priority: str  # low / medium / high / critical
    created_at: datetime
    updated_at: datetime
    notes: list[str]
    resolution: Optional[str] = None


class Metrics(BaseModel):
    tps: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    fraud_rate: float
    false_positive_rate: float
    total_transactions: int
    blocked_transactions: int
    approved_transactions: int
    under_review_transactions: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    username: str
    password: str


class OverrideRequest(BaseModel):
    decision: str  # APPROVE / REVIEW / BLOCK
    reason: str


class CaseCreateRequest(BaseModel):
    transaction_id: str
    assigned_to: str
    priority: str
    notes: list[str] = []


class CaseUpdateRequest(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[list[str]] = None
    resolution: Optional[str] = None
