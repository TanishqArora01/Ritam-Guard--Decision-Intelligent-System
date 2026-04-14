#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ERRORS=0

ok()   { echo "  [OK] $*"; }
fail() { echo "  [FAIL] $*"; ERRORS=$((ERRORS+1)); }
skip() { echo "  [SKIP] $*"; }

echo "=== Lint ==="

echo "Python - ruff"
if command -v ruff >/dev/null 2>&1; then
  if ruff check "$ROOT" --exclude ".git,__pycache__,node_modules,.next,*.egg-info" --select E,F,W,I --ignore E501; then
    ok "ruff passed"
  else
    fail "ruff found issues"
  fi
else
  skip "ruff not installed"
fi

echo ""
echo "Python - bandit"
if command -v bandit >/dev/null 2>&1; then
  PY_DIRS=()
  for d in "$ROOT"/apps/backend "$ROOT"/services/* "$ROOT"/platform/scripts; do
    [[ -d "$d" ]] && PY_DIRS+=("$d")
  done
  if [[ ${#PY_DIRS[@]} -gt 0 ]]; then
    if bandit -r "${PY_DIRS[@]}" --skip B101,B601 --severity-level medium -q; then
      ok "bandit passed"
    else
      fail "bandit found security issues"
    fi
  else
    skip "no Python directories found"
  fi
else
  skip "bandit not installed"
fi

echo ""
echo "TypeScript - eslint"
FRONTEND="$ROOT/apps/frontend"
if [[ -d "$FRONTEND" ]] && command -v npx >/dev/null 2>&1; then
  if [[ -f "$FRONTEND/.eslintrc.json" || -f "$FRONTEND/.eslintrc.js" || -f "$FRONTEND/eslint.config.js" ]]; then
    if (cd "$FRONTEND" && npx eslint . --ext .ts,.tsx --max-warnings 0); then
      ok "eslint passed"
    else
      fail "eslint found issues"
    fi
  else
    skip "eslint config not present in apps/frontend"
  fi
else
  skip "frontend or npx not found"
fi

echo ""
if [[ $ERRORS -eq 0 ]]; then
  echo "All lint checks passed"
  exit 0
else
  echo "$ERRORS lint check(s) failed"
  exit 1
fi
