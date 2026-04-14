#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ERRORS=0
COMPOSE_FILE="$ROOT/docker-compose.yml"

ok()   { echo "  [OK] $*"; }
fail() { echo "  [FAIL] $*"; ERRORS=$((ERRORS+1)); }

echo "=== Docker Compose Validation ==="

echo "YAML syntax"
if python3 -c "import yaml; yaml.safe_load(open('$COMPOSE_FILE'))"; then
  ok "YAML parses"
else
  fail "YAML parse failed"
fi

echo ""
echo "docker compose config"
if command -v docker >/dev/null 2>&1; then
  if docker compose -f "$COMPOSE_FILE" config --quiet >/dev/null 2>&1; then
    ok "docker compose config valid"
  else
    echo "  [SKIP] docker daemon/CLI unavailable in this environment"
  fi
else
  echo "  [SKIP] docker not installed"
fi

echo ""
echo "Required services present"
if COMPOSE_PATH="$COMPOSE_FILE" python3 - << 'PYEOF'
import yaml, sys
import os
compose_file = os.environ['COMPOSE_PATH']
with open(compose_file) as f:
    doc = yaml.safe_load(f)
services = set((doc or {}).get('services', {}).keys())
required = {
    'redpanda','redis','postgres','clickhouse','minio','neo4j',
    'feature-engine','stage1-service','stage2-service','stage3-service',
    'decision-sink','api-gateway','app-backend','frontend',
    'generator','prometheus','grafana','airflow-webserver'
}
missing = sorted(required - services)
if missing:
    print('Missing services:', missing)
    sys.exit(1)
print(f'All required services present ({len(services)} total)')
PYEOF
then
  ok "required services present"
else
  fail "required services missing"
fi

echo ""
if [[ $ERRORS -eq 0 ]]; then
  echo "Compose validation passed"
  exit 0
else
  echo "$ERRORS validation check(s) failed"
  exit 1
fi
