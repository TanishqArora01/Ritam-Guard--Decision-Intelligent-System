# Architecture Mapping (Old -> Unified)

This repository uses `fraud-detection-milestone-a` as the canonical, runnable base.

## Canonical Unified Root

- `apps/` application-facing interfaces and APIs
- `services/` pipeline compute and decision stages
- `platform/` infra configs, orchestration, scripts, feature store
- `docs/` architecture and operational documentation

## Pipeline Mapping

1. Ingestion / Source
- Old: `generator/`, `source-generator/` (p8), transaction adapters in `changes`
- Unified: `services/txn-generator/`

2. Streaming
- Old: Redpanda/Kafka config spread across `config/redpanda` and compose files
- Unified: `platform/config/redpanda/` + compose wiring in `docker-compose.yml`

3. Feature Engine
- Old: `feature-engine/`
- Unified: `services/feature-engine/`

4. Stage 1 Fast Risk
- Old: `stage1-service/`, `stage1-fast-risk/` (p8)
- Unified: `services/risk-stage1/`

5. Stage 2 Deep Intelligence
- Old: `stage2-service/`, `stage2-deep-intelligence/` (p8)
- Unified: `services/risk-stage2/`

6. Stage 3 Decision
- Old: `stage3-service/`, `stage3-decision-engine/` (p8)
- Unified: `services/decision-engine/`

7. Output / Sink
- Old: `sinks/`, `decision-sinks/` (p8)
- Unified: `services/decision-sink/`

8. API / Orchestration
- Old: `api-gateway/`, `app-backend/`, `frontend/`, `dags/`, `scripts/`, `feast/`, `config/`
- Unified:
  - `services/gateway/`
  - `apps/backend-api/`
  - `apps/web-portal/`
  - `platform/orchestration/airflow/dags/`
  - `platform/scripts/`
  - `platform/feature-store/`
  - `platform/config/`

## Legacy Folder Role

- `fraud-detection p-0` to `fraud-detection p-9`: incremental evolution snapshots.
- `fraud-detection changes`: patch branch used for salvage of valid additions.
- `fraud-detection changes -2`: duplicate patch branch, now merged selectively into `fraud-detection changes`.
- `fraud-detection-milestone-b`, `fraud-detection-milestone-c`: iteration branches used as reference only.

## Ownership By Unified Stage

- Source + message production: `services/txn-generator/`
- Feature compute + stores: `services/feature-engine/`
- Stage scoring models: `services/risk-stage1/`, `services/risk-stage2/`
- Decision policy: `services/decision-engine/`
- Persistence sink: `services/decision-sink/`
- API orchestration: `services/gateway/`, `apps/backend-api/`
- UI and analyst workflows: `apps/web-portal/`
- Platform assets: `platform/*`
