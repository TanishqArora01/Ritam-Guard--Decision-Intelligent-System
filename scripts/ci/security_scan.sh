#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPORT_DIR="${SECURITY_REPORT_DIR:-$ROOT/.security-reports}"
mkdir -p "$REPORT_DIR"
ERRORS=0

ok()   { echo "  [OK] $*"; }
fail() { echo "  [FAIL] $*"; ERRORS=$((ERRORS+1)); }
skip() { echo "  [SKIP] $*"; }

echo "=== Security Scan ==="

echo "Bandit"
if command -v bandit >/dev/null 2>&1; then
  BANDIT_OUT="$REPORT_DIR/bandit.json"
  if bandit -r "$ROOT/apps/backend-api" "$ROOT/services" --skip B101,B105,B601 --format json -o "$BANDIT_OUT" >/dev/null 2>&1; then
    ok "bandit scan complete"
  else
    fail "bandit reported findings (see $BANDIT_OUT)"
  fi
else
  skip "bandit not installed"
fi

echo ""
echo "Secret defaults check"
if grep -R --line-number --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.next "change-me-in-production\|admin2024!\|fraud_secret_2024" "$ROOT" >/dev/null 2>&1; then
  fail "found weak/default secrets in repository"
else
  ok "no weak/default secrets detected"
fi

echo ""
if [[ $ERRORS -eq 0 ]]; then
  echo "Security scan passed"
  exit 0
else
  echo "$ERRORS security check(s) failed"
  exit 1
fi
