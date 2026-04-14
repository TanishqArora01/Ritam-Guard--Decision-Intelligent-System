#!/bin/bash
# Fraud Detection System Architecture Validation

echo ""
echo "=================================================="
echo "  FRAUD DETECTION SYSTEM - ARCHITECTURE VALIDATION"
echo "=================================================="
echo ""

# 1. Check folders
echo "[1] VALIDATING FOLDER STRUCTURE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

folders=(
  "services/feature-engine"
  "services/risk-stage1"
  "services/risk-stage2"
  "services/decision-engine"
  "services/decision-sink"
  "services/gateway"
  "services/txn-generator"
  "apps/backend"
  "apps/frontend"
  "platform/config"
  "platform/scripts"
  "platform/feature-store"
  "platform/orchestration"
  "security/nginx"
  "dataset-pipeline"
)

passed=0
total=0
for folder in "${folders[@]}"; do
  total=$((total+1))
  if [ -d "$folder" ]; then
    echo "✓ $folder"
    passed=$((passed+1))
  else
    echo "✗ MISSING: $folder"
  fi
done
echo "Folders: $passed/$total"
echo ""

# 2. Check Dockerfiles
echo "[2] VALIDATING BUILD CONTEXTS & DOCKERFILES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

dockerfiles=(
  "services/feature-engine/Dockerfile"
  "services/risk-stage1/Dockerfile"
  "services/risk-stage2/Dockerfile"
  "services/decision-engine/Dockerfile"
  "services/decision-sink/Dockerfile"
  "services/gateway/Dockerfile"
  "services/txn-generator/Dockerfile"
  "apps/backend/Dockerfile"
  "apps/frontend/Dockerfile"
  "security/nginx/Dockerfile"
  "dataset-pipeline/Dockerfile"
)

passed=0
total=0
for dockerfile in "${dockerfiles[@]}"; do
  total=$((total+1))
  if [ -f "$dockerfile" ]; then
    echo "✓ $dockerfile"
    passed=$((passed+1))
  else
    echo "✗ MISSING: $dockerfile"
  fi
done
echo "Dockerfiles: $passed/$total"
echo ""

# 3. Check Docker Compose
echo "[3] VALIDATING DOCKER COMPOSE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if docker compose config -q 2>/dev/null; then
  echo "✓ Docker Compose configuration valid"
else
  echo "✗ Docker Compose validation failed"
fi
echo ""

# 4. Check service status
echo "[4] RUNNING SERVICES STATUS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "No services running"
echo ""

# 5. Architecture overview
echo "[5] EXPECTED ARCHITECTURE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Transaction Flow:"
echo "  API Gateway (8000)"
echo "    ↓"
echo "  Feature Engine (9102)"
echo "    ↓"
echo "  Stage 1 - Fast Risk (8100)"
echo "    ↓ (EARLY EXIT or continue)"
echo "  Stage 2 - Deep Intelligence (8200)"
echo "    ↓"
echo "  Stage 3 - Decision Engine (8300)"
echo "    ↓"
echo "  Decision Sink"
echo "    ↓"
echo "  PostgreSQL + ClickHouse"
echo ""
echo "Frontends:"
echo "  App Backend API (8400)"
echo "  Frontend Portal (3005)"
echo ""
echo "Supporting Services:"
echo "  Redpanda/Kafka (9092)"
echo "  Redis Cache (6379)"
echo "  ClickHouse Analytics (8123)"
echo "  MinIO S3 (9001)"
echo "  Neo4j Graph DB (7474)"
echo "  Airflow Orchestrator (8080)"
echo "  Prometheus Metrics (9090)"
echo "  Grafana Dashboard (3000)"
echo "  MLflow Tracking (5000)"
echo ""

echo "=================================================="
echo "Validation Complete"
echo "=================================================="
