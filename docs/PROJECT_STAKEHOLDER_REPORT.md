# Fraud Detection Decision Intelligence System
## Complete Project Report for Stakeholders

## 1. Executive Summary

This project is a real-time fraud decision platform built as a multi-stage intelligence system.
It ingests transactions from banking channels, computes real-time features, evaluates fraud risk in 3 stages, and outputs an action decision (`APPROVE`, `BLOCK`, `STEP_UP_AUTH`, `MANUAL_REVIEW`).

Business objective:
- Reduce fraud loss without over-blocking good customers
- Keep customer experience smooth for low-risk traffic
- Provide analyst explainability and governance for high-risk cases

## 2. Architecture (As Implemented)

### 2.1 Source Layer
Transaction sources:
- ATM
- POS terminal
- Mobile banking
- Web API
- Card network gateway

### 2.2 Data/Ingestion Layer
- Redpanda/Kafka-compatible bus for high-throughput streaming
- Core topics:
  - `txn-raw`
  - `txn-enriched`
  - `decisions`
  - `fraud-labels`
- Target capability: up to 10k TPS ingestion path

### 2.3 Stream/Feature Layer
- Apache FliSnk stateful stream processing for windowed feature computation
- Redis online feature store for sub-millisecond retrieval at scoring time
- MinIO offline feature store for historical snapshots and training datasets

### 2.4 Compute/Decision Layer
- Stage 1: Fast risk estimation (LightGBM + uncertainty), early-exit low-risk approvals
- Stage 2: Deep intelligence (XGBoost + neural network + graph + anomaly signals)
- Stage 3: Decision optimization engine using cost/risk trade-off
- Experimentation layer for A/B policy comparison and canary behavior

### 2.5 Action Layer
- Approve
- Block
- Step-up authentication (MFA challenge)
- Manual review queue for analysts

### 2.6 Feedback and Learning Loop
- Airflow DAGs orchestrate ingestion, monitoring, and retraining
- MLflow manages model runs and promotion workflow
- Analyst labels and chargebacks feed back to improve models over time

### 2.7 Monitoring Layer
- Prometheus for metrics
- Grafana for KPIs, drift/latency, and operational dashboards

## 3. Tools and Technologies Used

### 3.1 Application and ML
- Python (FastAPI services)
- Next.js frontend portal
- LightGBM, XGBoost, neural model components
- SHAP-style explainability outputs

### 3.2 Streaming and Data Infrastructure
- Redpanda (Kafka-compatible)
- Apache Flink
- Redis
- PostgreSQL
- ClickHouse
- MinIO
- Neo4j

### 3.3 Orchestration and MLOps
- Docker Compose
- Apache Airflow
- MLflow

### 3.4 Observability
- Prometheus
- Grafana

## 4. Service Access Links

| Service | URL | Purpose |
|---|---|---|
| Frontend portal | http://localhost:3005/login | End-user and analyst UI |
| API Gateway docs | http://localhost:8000/docs | Scoring APIs |
| API Gateway health | http://localhost:8000/health | Liveness |
| Backend API docs | http://localhost:8400/docs | Auth, review queue, analytics |
| Backend API health | http://localhost:8400/health | Liveness |
| Grafana | http://localhost:3000 | Dashboards |
| Prometheus | http://localhost:9090 | Metrics |
| Airflow | http://localhost:8080 | DAGs/orchestration |
| MLflow | http://localhost:5000 | Experiment tracking |
| MinIO Console | http://localhost:9002 | Object store UI |
| Neo4j Browser | http://localhost:7474 | Graph UI |

## 5. Usernames and Passwords (Current Local Stack)

### 5.1 Platform Credentials
| System | Username | Password |
|---|---|---|
| PostgreSQL | fraud_admin | fraud_secret_2024 |
| MinIO | fraud_minio | fraud_minio_2024 |
| Neo4j | neo4j | fraud_neo4j_2024 |
| Airflow | admin | fraud_admin_2024 |
| Grafana | admin | fraud_grafana_2024 |

### 5.2 Frontend Demo Users
| Role | Username | Password |
|---|---|---|
| Admin | admin | admin2024! |
| Analyst | analyst1 | analyst2024! |
| Ops Manager | ops1 | ops2024! |
| Bank Partner | partner1 | partner2024! |

Important:
- These are development credentials and must be rotated before production.

## 6. Database and Storage Explanation

### PostgreSQL (Operational System of Record)
Stores:
- Decision records
- User and role data
- Manual review workflow state

Why it matters:
- Transaction-level auditability and application state consistency

### ClickHouse (Analytical Store)
Stores:
- High-volume decision/fraud analytics data
- Aggregation-friendly metrics for dashboards

Why it matters:
- Fast analytics and KPI reporting over large datasets

### Redis (Online Feature Store)
Stores:
- Real-time feature values used during scoring
- Hot path lookups with very low latency

Why it matters:
- Keeps scoring latency within strict SLA

### MinIO (Offline Feature and Artifact Store)
Stores:
- Historical feature snapshots
- Training datasets and model-related artifacts

Why it matters:
- Enables reproducible model training and point-in-time dataset generation

### Neo4j (Graph Intelligence Store)
Stores:
- Entity relationship graph across users/devices/IPs/accounts
- Fraud ring and synthetic identity linkage patterns

Why it matters:
- Captures fraud behaviors missed by tabular-only models

### Redpanda Topics (Event Backbone)
Carries:
- Raw transactions
- Enriched transactions
- Final decisions
- Feedback labels for learning loop

Why it matters:
- Decouples services and supports throughput scalability

## 7. Major Stakeholder Talking Points

1. Business value
- Reduces fraud loss while controlling customer friction
- Supports explainable and auditable decisions

2. Speed and scalability
- Multi-stage architecture supports early-exit low-risk approvals
- Designed for sub-200ms full-path latency and high TPS scenarios

3. Risk control and governance
- Manual review path for uncertain/high-risk cases
- Explainability outputs available per decision
- Continuous learning from analyst labels and chargebacks

4. Operational transparency
- Real-time observability via Prometheus and Grafana
- Health endpoints and service-level diagnostics available

5. Extensibility
- New sources, features, policies, and models can be added with limited coupling

## 8. Current Status and Remaining Work

### Completed
- Full stack runs end-to-end in Docker Compose
- Frontend login and role-based access path working
- Gateway/backend health and docs endpoints active
- Core data stores and monitoring stack operational

### Remaining for final production deployability
1. Security hardening (secrets manager, TLS, credential rotation)
2. CI/CD with quality and security gates
3. Formal alerting and SLO ownership
4. Backup/restore automation and DR drills
5. Full E2E and load-test gating in release process

## 9. Related Project Documents

- Main project guide: `README.md`
- Deployment checklist: `docs/DEPLOYABLE_RUNBOOK.md`
- Architecture map: `docs/ARCHITECTURE_MAPPING.md`
- Execution guide: `docs/EXECUTION_GUIDE.md`
