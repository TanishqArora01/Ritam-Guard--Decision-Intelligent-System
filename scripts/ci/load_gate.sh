#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENVIRONMENT="${ENVIRONMENT:-ci}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
THRESHOLDS_FILE="$ROOT/scripts/ci/thresholds.json"

python3 << PYEOF
import json, sys, urllib.request

with open(r'''$THRESHOLDS_FILE''') as f:
    cfg = json.load(f)

env = r'''$ENVIRONMENT'''
url = r'''$GATEWAY_URL'''
if env not in cfg['environments']:
    print(f'Unknown environment: {env}')
    sys.exit(1)

thr = cfg['environments'][env]
print('Load gate thresholds:', thr)

try:
    urllib.request.urlopen(f"{url}/health", timeout=8)
except Exception as e:
    print(f'Gateway unreachable: {e}')
    sys.exit(1)

print('Gateway reachable. Run platform/scripts/load_test.py for full performance validation.')
print('Gate check passed (connectivity + thresholds loaded).')
PYEOF
