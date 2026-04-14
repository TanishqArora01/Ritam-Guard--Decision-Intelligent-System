#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ERRORS=0
SUITE="${TEST_SUITE:-all}"

ok()   { echo "  [OK] $*"; }
fail() { echo "  [FAIL] $*"; ERRORS=$((ERRORS+1)); }
skip() { echo "  [SKIP] $*"; }

echo "=== Tests (suite: $SUITE) ==="

if [[ "$SUITE" == "all" || "$SUITE" == "unit" ]]; then
  echo "Unit tests - pytest"
  if command -v pytest >/dev/null 2>&1; then
    if pytest "$ROOT" --ignore="$ROOT/apps/web-portal" --ignore="$ROOT/platform" -q --tb=short -m "not integration"; then
      ok "pytest unit tests passed"
    else
      fail "pytest unit tests failed"
    fi
  else
    skip "pytest not installed"
  fi
fi

if [[ "$SUITE" == "all" || "$SUITE" == "integration" ]]; then
  echo ""
  echo "Integration tests"
  if [[ -f "$ROOT/tests/integration/test_pipeline_contracts.py" ]]; then
    if command -v pytest >/dev/null 2>&1; then
      if pytest "$ROOT/tests/integration/test_pipeline_contracts.py" -q --tb=short; then
        ok "integration contracts passed"
      else
        fail "integration contracts failed"
      fi
    else
      skip "pytest not installed"
    fi
  else
    skip "integration tests not found"
  fi
fi

if [[ "$SUITE" == "all" || "$SUITE" == "e2e" ]]; then
  echo ""
  echo "E2E smoke test script presence"
  if [[ -f "$ROOT/platform/scripts/e2e_test.py" ]]; then
    ok "platform/scripts/e2e_test.py exists"
  else
    fail "platform/scripts/e2e_test.py missing"
  fi
fi

echo ""
if [[ $ERRORS -eq 0 ]]; then
  echo "All tests passed"
  exit 0
else
  echo "$ERRORS test suite(s) failed"
  exit 1
fi
