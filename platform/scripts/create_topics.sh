#!/bin/bash
# =============================================================================
# Redpanda / Kafka — Topic Initialization Script
# Run once after Redpanda is healthy to create all required topics
# =============================================================================

set -e

BROKER="redpanda:9092"

echo "Creating Fraud Detection Kafka topics..."

# Helper function
create_topic() {
  local name=$1
  local partitions=$2
  local retention_ms=$3

  echo "  Creating topic: $name (partitions=$partitions)"
  rpk topic create "$name" \
    --brokers "$BROKER" \
    --partitions "$partitions" \
    --replicas 1 \
    --topic-config "retention.ms=$retention_ms" \
    --topic-config "cleanup.policy=delete" \
    2>/dev/null && echo "    OK: $name" || echo "    SKIPPED (already exists): $name"
}

# ---------------------------------------------------------------------------
# INGESTION TOPICS
# ---------------------------------------------------------------------------
# Raw transactions from all sources (ATM, POS, Mobile, Web)
create_topic "txn-raw"           8  86400000    # 1 day retention, 8 partitions (10k TPS)

# Enriched transactions after Flink stream processing
create_topic "txn-enriched"      8  86400000

# Stage 1 scored transactions (P(fraud) + uncertainty)
create_topic "txn-stage1"        4  43200000    # 12 hours

# Stage 2 deep intelligence output
create_topic "txn-stage2"        4  43200000

# ---------------------------------------------------------------------------
# DECISION TOPICS
# ---------------------------------------------------------------------------
# Final decisions from Stage 3 optimization engine
create_topic "decisions"         4  604800000   # 7 days (audit trail)

# A/B experiment decision log
create_topic "decisions-ab"      2  604800000

# ---------------------------------------------------------------------------
# ACTION TOPICS
# ---------------------------------------------------------------------------
create_topic "action-approve"    4  86400000
create_topic "action-block"      4  86400000
create_topic "action-stepup"     4  86400000
create_topic "action-review"     2  86400000

# ---------------------------------------------------------------------------
# FEEDBACK LOOP TOPICS
# ---------------------------------------------------------------------------
# Analyst label decisions from manual review
create_topic "fraud-labels"      4  2592000000  # 30 days (training data)

# Chargeback events from payment processors
create_topic "chargebacks"       4  2592000000

# Customer dispute events
create_topic "disputes"          2  2592000000

# ---------------------------------------------------------------------------
# FEATURE STORE TOPICS
# ---------------------------------------------------------------------------
# Computed features pushed to online store (Redis)
create_topic "feature-updates"   4  3600000     # 1 hour

# ---------------------------------------------------------------------------
# MONITORING TOPICS
# ---------------------------------------------------------------------------
# Decision latency + cost metrics
create_topic "metrics-decisions" 2  86400000

# Model prediction logs (for drift detection)
create_topic "model-predictions" 4  86400000

echo ""
echo "Topic creation complete. Current topics:"
rpk topic list --brokers "$BROKER"
