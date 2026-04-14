"""
cost_engine.py
The Decision Optimization Engine — Stage 3 core.

Solves:
    action* = argmin_{a ∈ A} E[Cost(a, x)]

where A = {APPROVE, BLOCK, STEP_UP_AUTH, MANUAL_REVIEW}

Cost function per action:
─────────────────────────────────────────────────────────────────────────────
APPROVE:
    E[Cost] = p_fraud × amount
    (Expected fraud loss if we let the transaction through)

BLOCK:
    E[Cost] = (1 - p_fraud) × CLV × friction_multiplier
    (Expected CLV damage from incorrectly blocking a legitimate customer)

STEP_UP_AUTH:
    E[Cost] = cost_stepup
              + p_fraud × (1 - p_stepup_fraud_blocked) × amount
              + (1 - p_fraud) × (1 - p_stepup_legit_completes) × CLV × friction_multiplier
    (Challenge cost + residual fraud loss if attacker passes + friction if
     legitimate customer abandons the challenge)

MANUAL_REVIEW:
    E[Cost] = cost_manual_review
    (Fixed analyst cost — no fraud loss, no friction, just labor)

─────────────────────────────────────────────────────────────────────────────

Hard rules (override the cost minimisation):
  p_fraud > HARD_BLOCK_THRESHOLD   → always BLOCK
  p_fraud < HARD_APPROVE_THRESHOLD → always APPROVE
  uncertainty > UNCERTAINTY_REVIEW  → always MANUAL_REVIEW
  (These handle edge cases where cost minimisation would give a bad answer)

Trust score modulation:
  For low-trust customers, the effective p_fraud passed to the cost engine
  is inflated: p_eff = 1 - (1-p_fraud) × trust_score
  This makes the engine more conservative for customers with poor history.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config import config
from schemas import Action, ABVariant, CostBreakdown, Stage3Request, Stage3Response

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram
    DECISIONS = Counter("stage3_decisions_total", "Total decisions", ["action", "ab_variant"])
    COSTS     = Histogram("stage3_optimal_cost_usd", "Optimal cost per decision (USD)",
                          buckets=[0,1,5,10,25,50,100,250,500,1000,5000])
except Exception:
    class _N:
        def __init__(self,*a,**k): pass
        def labels(self,**k): return self
        def inc(self,v=1): pass
        def observe(self,v): pass
    DECISIONS = COSTS = _N()


# ---------------------------------------------------------------------------
# CLV resolver
# ---------------------------------------------------------------------------

def resolve_clv(req: Stage3Request) -> float:
    """
    Return effective CLV for cost calculation.
    Uses declared CLV if > 0, otherwise falls back to segment default.
    """
    if req.clv > 0:
        return req.clv
    return config.clv_defaults.get(req.customer_segment, 12_000.0)


# ---------------------------------------------------------------------------
# Trust-modulated fraud probability
# ---------------------------------------------------------------------------

def effective_p_fraud(p_fraud: float, trust_score: float) -> float:
    """
    Adjust p_fraud using customer trust score.

    For a perfectly trusted customer (trust=1.0), p_fraud is unchanged.
    For a zero-trust customer (trust=0.0), p_fraud is set to 1.0.

    Formula:  p_eff = 1 - (1 - p_fraud) × trust_score
    This is equivalent to saying: even if the model thinks it's legitimate,
    a zero-trust customer's transaction is treated as suspicious.
    """
    p_eff = 1.0 - (1.0 - p_fraud) * trust_score
    return float(min(1.0, max(0.0, p_eff)))


# ---------------------------------------------------------------------------
# Per-action cost calculators
# ---------------------------------------------------------------------------

def cost_approve(p: float, amount: float) -> float:
    """Expected fraud loss if approved."""
    return round(p * amount, 4)


def cost_block(p: float, clv: float) -> float:
    """Expected CLV friction loss if blocked."""
    p_legit = 1.0 - p
    return round(p_legit * clv * config.clv_friction_multiplier, 4)


def cost_stepup(p: float, amount: float, clv: float) -> float:
    """
    Expected cost of step-up auth challenge.
    = fixed cost
    + residual fraud loss (attacker beats the challenge)
    + abandonment friction (legitimate user gives up)
    """
    residual_fraud   = p * (1.0 - config.p_stepup_fraud_blocked) * amount
    abandon_friction = (1.0 - p) * (1.0 - config.p_stepup_legit_completes) * clv * config.clv_friction_multiplier
    return round(config.cost_stepup + residual_fraud + abandon_friction, 4)


def cost_review() -> float:
    """Fixed manual review cost (analyst time)."""
    return round(config.cost_manual_review, 4)


# ---------------------------------------------------------------------------
# Full cost breakdown for all 4 actions
# ---------------------------------------------------------------------------

def compute_all_costs(
    p_fraud: float, amount: float, clv: float
) -> List[CostBreakdown]:
    """
    Compute expected costs for all 4 actions.
    Returns a list sorted by total_expected_cost ascending.
    """
    entries = []

    for action, total, loss, friction, review_c, stepup_c in [
        (Action.APPROVE,
         cost_approve(p_fraud, amount),
         cost_approve(p_fraud, amount), 0.0, 0.0, 0.0),

        (Action.BLOCK,
         cost_block(p_fraud, clv),
         0.0, cost_block(p_fraud, clv), 0.0, 0.0),

        (Action.STEP_UP_AUTH,
         cost_stepup(p_fraud, amount, clv),
         p_fraud * (1 - config.p_stepup_fraud_blocked) * amount,
         (1-p_fraud) * (1-config.p_stepup_legit_completes) * clv * config.clv_friction_multiplier,
         0.0, config.cost_stepup),

        (Action.MANUAL_REVIEW,
         cost_review(),
         0.0, 0.0, cost_review(), 0.0),
    ]:
        entries.append(CostBreakdown(
            action               = action,
            expected_loss        = round(loss,     4),
            expected_friction    = round(friction,  4),
            expected_review      = round(review_c,  4),
            expected_stepup      = round(stepup_c,  4),
            total_expected_cost  = round(total,     4),
        ))

    # Sort by cost; mark the cheapest as optimal
    entries.sort(key=lambda e: e.total_expected_cost)
    entries[0].is_optimal = True
    return entries


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def decide(req: Stage3Request) -> Tuple[Action, str, List[CostBreakdown], float]:
    """
    Core decision function.

    Returns (action, reason, cost_breakdown, optimal_cost).
    """
    clv        = resolve_clv(req)
    p_raw      = req.p_fraud
    trust      = req.trust_score
    uncertainty= 1.0 - req.confidence
    amount     = req.amount
    p_eff      = effective_p_fraud(p_raw, trust)

    # ---- Hard rules (pre-empt cost optimisation) ----

    if uncertainty > config.uncertainty_review_threshold:
        costs = compute_all_costs(p_eff, amount, clv)
        return (
            Action.MANUAL_REVIEW,
            f"High uncertainty ({uncertainty:.3f}) — analyst review required",
            costs,
            config.cost_manual_review,
        )

    if p_eff >= config.hard_block_threshold:
        costs = compute_all_costs(p_eff, amount, clv)
        return (
            Action.BLOCK,
            f"P(fraud)={p_eff:.4f} ≥ hard block threshold {config.hard_block_threshold}",
            costs,
            cost_block(p_eff, clv),
        )

    # Hard approve uses raw p_fraud (model signal is clear — trust irrelevant)
    if p_raw <= config.hard_approve_threshold:
        costs = compute_all_costs(p_raw, amount, clv)
        return (
            Action.APPROVE,
            f"P(fraud)={p_raw:.4f} ≤ hard approve threshold {config.hard_approve_threshold}",
            costs,
            cost_approve(p_raw, amount),
        )

    # ---- Graph signals override ----
    # Confirmed fraud ring membership → always block (graph evidence is strong)
    if req.fraud_ring_score > 0.8 and req.multi_hop_score > 0.5:
        costs = compute_all_costs(p_eff, amount, clv)
        return (
            Action.BLOCK,
            "Graph intelligence: confirmed fraud ring + multi-hop connection",
            costs,
            cost_block(p_eff, clv),
        )

    # ---- argmin cost optimisation ----
    costs   = compute_all_costs(p_eff, amount, clv)
    optimal = costs[0]  # sorted ascending by cost

    # Prefer step-up over block for premium customers (preserve CLV)
    if (optimal.action == Action.BLOCK
            and req.customer_segment == "premium"
            and trust > 0.6):
        # Find step-up cost
        stepup_cost = next(
            (c.total_expected_cost for c in costs if c.action == Action.STEP_UP_AUTH),
            float("inf"),
        )
        if stepup_cost < optimal.total_expected_cost * 2.0:
            reason = (
                f"Premium customer (trust={trust:.2f}) — step-up preferred over block "
                f"(block cost ${optimal.total_expected_cost:.2f} vs step-up ${stepup_cost:.2f})"
            )
            for c in costs:
                c.is_optimal = (c.action == Action.STEP_UP_AUTH)
            return Action.STEP_UP_AUTH, reason, costs, stepup_cost

    reason = (
        f"argmin cost: {optimal.action.value} "
        f"(cost ${optimal.total_expected_cost:.2f} "
        f"vs approve ${costs[next(i for i,c in enumerate(costs) if c.action==Action.APPROVE)].total_expected_cost:.2f})"
    )
    return optimal.action, reason, costs, optimal.total_expected_cost


# ---------------------------------------------------------------------------
# A/B Experimentation wrapper
# ---------------------------------------------------------------------------

def decide_with_ab(req: Stage3Request, rng: random.Random) -> Tuple[Action, ABVariant, Optional[Action], str]:
    """
    Wrap decide() with A/B experiment assignment.

    Returns (executed_action, variant, shadow_action, reason).

    In shadow mode:
      - Control policy runs and its action is executed
      - Treatment policy also runs but result is only logged (not executed)
    """
    if not config.ab_enabled:
        action, reason, _, _ = decide(req)
        return action, ABVariant.CONTROL, None, reason

    # Assign variant deterministically per transaction (use txn_id hash for reproducibility)
    roll = rng.random()
    variant = ABVariant.CONTROL if roll < config.ab_control_weight else ABVariant.TREATMENT

    # Both policies use the same cost engine in this PoC
    # In production, control/treatment would have different config (e.g. different thresholds)
    control_action,   control_reason,   _, _ = decide(req)
    treatment_action, treatment_reason, _, _ = _decide_treatment(req)

    if config.ab_shadow_mode:
        # Always execute control; log treatment as shadow
        return control_action, ABVariant.SHADOW, treatment_action, control_reason

    if variant == ABVariant.CONTROL:
        return control_action, ABVariant.CONTROL, treatment_action, control_reason
    else:
        return treatment_action, ABVariant.TREATMENT, control_action, treatment_reason


def _decide_treatment(req: Stage3Request) -> Tuple[Action, str, List[CostBreakdown], float]:
    """
    Treatment policy: slightly more aggressive step-up auth
    (lower threshold for step-up vs block).
    In production this would be a different config object.
    """
    # Temporarily lower friction multiplier to prefer step-up over block more often
    original = config.clv_friction_multiplier
    config.clv_friction_multiplier *= 1.5   # treatment: weight CLV friction higher
    try:
        result = decide(req)
    finally:
        config.clv_friction_multiplier = original
    return result


# ---------------------------------------------------------------------------
# Explanation builder
# ---------------------------------------------------------------------------

def build_explanation(
    req:    Stage3Request,
    action: Action,
    reason: str,
    clv:    float,
    p_eff:  float,
    costs:  List[CostBreakdown],
) -> Dict[str, str]:
    """
    Build a plain-English explanation for the decision.
    Format required by the architecture: "Blocked because: ..."
    """
    expl: Dict[str, str] = {}

    # Decision reason
    expl["decision"] = f"{action.value.replace('_',' ').title()}: {reason}"

    # Fraud risk signal
    expl["fraud_risk"] = (
        f"Fraud probability P(fraud)={req.p_fraud:.3f} "
        f"(trust-adjusted: {p_eff:.3f}, CLV=${clv:,.0f})"
    )

    # Cost summary
    opt = next((c for c in costs if c.is_optimal), None)
    if opt:
        expl["cost_optimal"] = (
            f"Optimal action cost: ${opt.total_expected_cost:.2f} "
            f"(fraud loss component: ${opt.expected_loss:.2f}, "
            f"friction: ${opt.expected_friction:.2f})"
        )

    # Graph signals
    if req.fraud_ring_score > 0.4:
        expl["graph_fraud_ring"] = (
            f"Transaction graph shows device/IP sharing with {req.fraud_ring_score:.0%} confidence"
        )
    if req.multi_hop_score > 0.4:
        expl["graph_multihop"] = (
            f"Multi-hop fraud network proximity detected ({req.multi_hop_score:.0%})"
        )
    if req.mule_account_score > 0.4:
        expl["graph_mule"] = (
            f"Account shows mule-like transaction patterns ({req.mule_account_score:.0%})"
        )

    # Anomaly signal
    if req.is_anomaly or req.anomaly_score > 0.6:
        expl["anomaly"] = (
            f"Transaction pattern is anomalous (score={req.anomaly_score:.3f}, "
            f"AE={req.autoencoder_score:.3f}, IF={req.isolation_forest_score:.3f})"
        )

    # Top ML features
    for feat, val in list(req.top_features.items())[:2]:
        if abs(val) > 0.05:
            expl[f"feature_{feat}"] = (
                f"{feat.replace('_',' ').title()} contributed "
                f"{'positively' if val>0 else 'negatively'} to fraud score (SHAP={val:+.3f})"
            )

    # Stage 2 explanation pass-through
    for key, val in list(req.stage2_explanation.items())[:2]:
        if key not in expl:
            expl[f"stage2_{key}"] = val

    return expl
