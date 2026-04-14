#!/usr/bin/env bash
# =============================================================================
# System Health Check Script
# Run after starting each layer to verify all services are reachable
# Usage: ./scripts/healthcheck.sh [core|data|compute|all]
# =============================================================================

set -euo pipefail

LAYER=${1:-all}
PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RESET='\033[0m'

check() {
  local name=$1
  local cmd=$2
  printf "  %-30s" "$name"
  if eval "$cmd" > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${RESET}"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAIL${RESET}"
    FAIL=$((FAIL + 1))
  fi
}

check_http() {
  local name=$1
  local url=$2
  check "$name" "curl -sf --max-time 5 '$url'"
}

check_tcp() {
  local name=$1
  local host=$2
  local port=$3
  check "$name" "nc -z -w5 $host $port"
}

# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}=== Fraud Detection — Service Health Check ===${RESET}"
echo -e "${YELLOW}Layer: $LAYER${RESET}"
echo ""

if [[ "$LAYER" == "core" || "$LAYER" == "all" ]]; then
  echo -e "${CYAN}CORE LAYER${RESET}"
  check_tcp   "PostgreSQL (TCP)"      "localhost" "5432"
  check        "PostgreSQL (query)"   "docker exec fraud_postgres pg_isready -U fraud_admin -d fraud_db"
  check_tcp   "Redis (TCP)"           "localhost" "6379"
  check        "Redis (PING)"         "docker exec fraud_redis redis-cli ping | grep -q PONG"
  check_tcp   "Redpanda Kafka (TCP)"  "localhost" "9092"
  check_http  "Redpanda Admin"        "http://localhost:9644/v1/cluster/health"
  check_http  "Redpanda Schema Reg"   "http://localhost:8081/subjects"
  echo ""
fi

if [[ "$LAYER" == "data" || "$LAYER" == "all" ]]; then
  echo -e "${CYAN}DATA LAYER${RESET}"
  check_http  "ClickHouse (HTTP)"     "http://localhost:8123/ping"
  check_http  "MinIO (Health)"        "http://localhost:9001/minio/health/live"
  check_http  "MinIO Console"         "http://localhost:9002"
  check_http  "Neo4j Browser"         "http://localhost:7474"
  check_tcp   "Neo4j Bolt (TCP)"      "localhost" "7687"
  echo ""
fi

if [[ "$LAYER" == "compute" || "$LAYER" == "all" ]]; then
  echo -e "${CYAN}COMPUTE LAYER${RESET}"
  check_http  "Flink Web UI"          "http://localhost:8083/overview"
  check_http  "MLflow UI"             "http://localhost:5000/health"
  echo ""
fi

if [[ "$LAYER" == "orchestration" || "$LAYER" == "all" ]]; then
  echo -e "${CYAN}ORCHESTRATION LAYER${RESET}"
  check_http  "Airflow UI"            "http://localhost:8080/health"
  echo ""
fi

if [[ "$LAYER" == "monitoring" || "$LAYER" == "all" ]]; then
  echo -e "${CYAN}MONITORING LAYER${RESET}"
  check_http  "Prometheus"            "http://localhost:9090/-/healthy"
  check_http  "Grafana"               "http://localhost:3000/api/health"
  echo ""
fi

# ---------------------------------------------------------------------------
echo -e "${CYAN}=== Summary ===${RESET}"
echo -e "  ${GREEN}PASS: $PASS${RESET}"
if [ "$FAIL" -gt 0 ]; then
  echo -e "  ${RED}FAIL: $FAIL${RESET}"
  echo ""
  echo -e "${YELLOW}Tip: Some services take 30-90s to fully start after 'make up-*'${RESET}"
  echo -e "${YELLOW}Wait and retry: ./scripts/healthcheck.sh $LAYER${RESET}"
  exit 1
else
  echo -e "  FAIL: 0"
  echo ""
  echo -e "${GREEN}All checks passed.${RESET}"
fi
