# Unification Changelog

## Scope

- Base preserved: `fraud-detection-milestone-a`
- Patch source reviewed: `fraud-detection changes` and `fraud-detection changes -2`

## Applied Integrations

1. Merged safe package improvements into `fraud-detection changes`:
- Added missing package markers (`__init__.py`) for:
  - `app-backend/auth`, `app-backend/db`, `app-backend/routers`, `app-backend/services`
  - `contracts`
  - `feature-engine/features`, `feature-engine/store`
  - `feedback-service`, `mlops-service`
  - `transaction-adapters`, `transaction-adapters/batch`, `transaction-adapters/iso8583`, `transaction-adapters/webhook`
  - `vault`

2. Merged safe environment additions into `fraud-detection changes/.env.example`:
- Feedback service, MLOps, transaction adapter, and Vault environment blocks.

## Rejected Regressions (Not Merged)

- `changes -2` duplicated service blocks in `docker-compose.yml` (high risk of parse/runtime issues).
- `changes -2` frontend reverted from port 3013 to 3001 and inlined auth context changes that conflict with existing structure.
- `changes -2` README/Makefile were expanded but included formatting corruption and assumed an unverified 31-service state.

## Runtime Baseline

- Canonical runtime remains `fraud-detection-milestone-a`.
- Main UI target remains `http://localhost:3005/login`.
