# Deployable Runbook (Main Things Only)

This runbook focuses only on the critical items needed to move from a working stack to a production-ready deployment.

## 1. Current Live Status (Verified)

1. Frontend login route works: `http://localhost:3005/login` (200)
2. API Gateway health works: `http://localhost:8000/health` (200)
3. App Backend health works: `http://localhost:8400/health` (200)
4. Frontend proxy auth works: `/api/backend/auth/login`
5. Protected frontend pages redirect to login when unauthenticated (expected)

## 2. Must-Do Before Production

1. Secrets and credentials
- Move all credentials from compose/env defaults into a secrets manager.
- Rotate all default passwords (Postgres, MinIO, Neo4j, Airflow, Grafana, JWT).
- Remove demo/seed users in production environments.

2. HTTPS and edge security
- Put Nginx or ingress in front of frontend and APIs with TLS enabled.
- Enforce secure cookies and strict CORS for production domain only.
- Restrict public port exposure to only required entrypoints.

3. CI/CD release pipeline
- Add pipeline stages: lint, unit tests, integration tests, image scan, deploy.
- Use immutable image tags and keep rollback to previous stable version.
- Maintain separate configs for dev/stage/prod.

4. Observability and alerts
- Add alert rules for: API 5xx, latency p95 breaches, sink write failures, queue lag.
- Define SLOs for availability and latency.
- Document incident response ownership and escalation.

5. Backup and recovery
- Enable scheduled backups for Postgres, ClickHouse, MinIO.
- Run restore drill and document Recovery Time Objective (RTO) and Recovery Point Objective (RPO).

## 3. Frontend Finalization Checklist

1. Auth and session
- Keep browser API calls on same-origin proxy path (`/api/backend`).
- Add clear UX for token expiry and network failure (retry + re-login path).
- Add logout/session-clear flow validation.

2. Route and role protection
- Verify role-based navigation for ADMIN, ANALYST, OPS_MANAGER, BANK_PARTNER.
- Add page-level guard tests for restricted routes.

3. Production UX quality
- Add fallback UI for backend unavailability.
- Add user-friendly API error messages instead of raw fetch errors.
- Add build version indicator in UI for release traceability.

4. Frontend testing
- Add E2E tests for: login, redirect, dashboard load, key actions, logout.
- Add smoke test in CI for `/login`, `/dashboard` auth redirect, and auth proxy.

## 4. Final Go-Live Gate

Ship only when all checks below are green:

1. Security review completed and secrets rotated.
2. CI/CD pipeline passing with integration + E2E tests.
3. Monitoring dashboards plus actionable alerts enabled.
4. Backup and restore drill passed.
5. Performance test meets agreed p95 latency and throughput targets.
6. Frontend auth and role-routing tests passed in stage and prod-like environment.

## 5. Daily Operations (After Go-Live)

1. Check health endpoints and critical dashboards.
2. Review alert summary and queue lag.
3. Review decision sink write health (Postgres + ClickHouse).
4. Review model drift metrics and retrain triggers.
5. Review frontend error rate and login failure rate.
