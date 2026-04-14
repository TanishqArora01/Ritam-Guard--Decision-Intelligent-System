#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---env}"
ERRORS=0

ok()   { echo "  [OK] $*"; }
fail() { echo "  [FAIL] $*"; ERRORS=$((ERRORS+1)); }

FORBIDDEN=("fraud_secret_2024" "fraud_minio_2024" "fraud_neo4j_2024" "admin2024!" "change-me" "CHANGE_ME" "password" "secret")

declare -A REQUIRED=(
  [POSTGRES_PASSWORD]=12
  [JWT_SECRET]=32
  [MINIO_ROOT_PASSWORD]=12
  [NEO4J_PASSWORD]=12
  [ANON_SALT]=16
  [WEBHOOK_SECRET]=16
)

check_value() {
  local name="$1" value="$2" min_len="$3"
  if [[ -z "$value" ]]; then fail "$name is empty"; return; fi
  if [[ ${#value} -lt $min_len ]]; then fail "$name too short (${#value}/${min_len})"; return; fi
  if [[ "${ENVIRONMENT:-development}" == "production" ]]; then
    for f in "${FORBIDDEN[@]}"; do
      if [[ "$value" == "$f" ]]; then fail "$name uses forbidden default"; return; fi
    done
  fi
  ok "$name"
}

echo "=== Secret Validation (mode: $MODE) ==="

if [[ "$MODE" == "--env" ]]; then
  for name in "${!REQUIRED[@]}"; do
    check_value "$name" "${!name:-}" "${REQUIRED[$name]}"
  done
else
  fail "unsupported mode: $MODE"
fi

if [[ $ERRORS -eq 0 ]]; then
  echo "All secrets validated"
  exit 0
else
  echo "$ERRORS secret validation error(s)"
  exit 1
fi
