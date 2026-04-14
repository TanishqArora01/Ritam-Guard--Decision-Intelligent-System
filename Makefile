# =============================================================================
# Fraud Detection System — Makefile
# All commands you need to operate the system layer by layer
# =============================================================================

COMPOSE = docker compose
ENV_FILE = .env
COMPOSE_FILE = docker-compose.yml

# Colour output
GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
RESET  := \033[0m

.DEFAULT_GOAL := help

# =============================================================================
# HELP
# =============================================================================

.PHONY: help
help:
	@echo ""
	@echo "$(CYAN)Fraud Detection System — Command Reference$(RESET)"
	@echo "============================================"
	@echo ""
	@echo "$(YELLOW)Layer-by-layer startup (recommended order):$(RESET)"
	@echo "  make setup            — copy .env.example to .env, create dirs"
	@echo "  make up-core          — start Redpanda + Redis + PostgreSQL"
	@echo "  make up-data          — start ClickHouse + MinIO + Neo4j"
	@echo "  make up-compute       — start Flink + MLflow"
	@echo "  make up-orchestrate   — start Airflow (webserver + scheduler)"
	@echo "  make up-monitoring    — start Prometheus + Grafana"
	@echo ""
	@echo "$(YELLOW)Full stack:$(RESET)"
	@echo "  make up-all           — start everything at once"
	@echo "  make down             — stop all running services"
	@echo "  make down-all         — stop + remove containers (keep volumes)"
	@echo "  make clean            — stop + remove containers AND volumes (DESTRUCTIVE)"
	@echo ""
	@echo "$(YELLOW)Operations:$(RESET)"
	@echo "  make status           — show running containers + health"
	@echo "  make logs             — tail logs for all services"
	@echo "  make logs-core        — tail core layer logs only"
	@echo "  make ps               — docker compose ps"
	@echo "  make pull             — pull latest images"
	@echo ""
	@echo "$(YELLOW)Service-specific:$(RESET)"
	@echo "  make logs SERVICE=fraud_redpanda    — tail a specific container"
	@echo "  make shell SERVICE=fraud_postgres   — open shell in container"
	@echo "  make restart SERVICE=fraud_redis    — restart a specific service"
	@echo ""
	@echo "$(YELLOW)Validation:$(RESET)"
	@echo "  make validate-core    — test Redpanda + Redis + Postgres connectivity"
	@echo "  make validate-data    — test ClickHouse + MinIO + Neo4j connectivity"
	@echo "  make validate-all     — run all validation checks"
	@echo "  make ports            — show all exposed ports"
	@echo ""

# =============================================================================
# SETUP
# =============================================================================

.PHONY: setup
setup:
	@echo "$(GREEN)Setting up project...$(RESET)"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(YELLOW)Created .env from .env.example — review and adjust before first run$(RESET)"; \
	else \
		echo ".env already exists, skipping"; \
	fi
	@mkdir -p platform/orchestration/airflow/dags plugins
	@echo "$(GREEN)Setup complete. Run 'make up-core' to start the core layer.$(RESET)"

# =============================================================================
# LAYER-BY-LAYER STARTUP
# =============================================================================

.PHONY: up-core
up-core:
	@echo "$(GREEN)Starting CORE layer: Redpanda + Redis + PostgreSQL...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile core up -d
	@echo ""
	@echo "$(CYAN)Core layer services:$(RESET)"
	@echo "  Redpanda Kafka API:      localhost:9092"
	@echo "  Redpanda Admin API:      localhost:9644"
	@echo "  Redpanda Schema Reg:     localhost:8081"
	@echo "  Redis:                   localhost:6379"
	@echo "  PostgreSQL:              localhost:5432"
	@echo ""
	@echo "$(YELLOW)Waiting for health checks... (up to 60s)$(RESET)"
	@sleep 5
	@$(COMPOSE) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || $(COMPOSE) ps
	@echo ""
	@echo "$(GREEN)Next step: make up-data$(RESET)"

.PHONY: up-data
up-data:
	@echo "$(GREEN)Starting DATA layer: ClickHouse + MinIO + Neo4j...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile data up -d
	@echo ""
	@echo "$(CYAN)Data layer services:$(RESET)"
	@echo "  ClickHouse HTTP:         localhost:8123"
	@echo "  ClickHouse Native:       localhost:9000"
	@echo "  MinIO S3 API:            localhost:9001"
	@echo "  MinIO Console:           localhost:9002"
	@echo "  Neo4j Browser:           localhost:7474"
	@echo "  Neo4j Bolt:              localhost:7687"
	@echo ""
	@echo "$(YELLOW)Neo4j takes ~60s to fully start — be patient$(RESET)"
	@echo ""
	@echo "$(GREEN)Next step: make up-compute$(RESET)"

.PHONY: up-compute
up-compute:
	@echo "$(GREEN)Starting COMPUTE layer: Flink + MLflow...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile compute up -d
	@echo ""
	@echo "$(CYAN)Compute layer services:$(RESET)"
	@echo "  Flink Web UI:            localhost:8083"
	@echo "  MLflow UI:               localhost:5000"
	@echo ""
	@echo "$(GREEN)Next step: make up-orchestrate$(RESET)"

.PHONY: up-orchestrate
up-orchestrate:
	@echo "$(GREEN)Starting ORCHESTRATION layer: Airflow...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile orchestration up -d
	@echo ""
	@echo "$(CYAN)Orchestration layer services:$(RESET)"
	@echo "  Airflow UI:              localhost:8080"
	@echo "  Default login:           admin / fraud_admin_2024"
	@echo ""
	@echo "$(YELLOW)Airflow init takes ~90s on first run — DB migration in progress$(RESET)"
	@echo ""
	@echo "$(GREEN)Next step: make up-monitoring$(RESET)"

.PHONY: up-monitoring
up-monitoring:
	@echo "$(GREEN)Starting MONITORING layer: Prometheus + Grafana...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile monitoring up -d
	@echo ""
	@echo "$(CYAN)Monitoring layer services:$(RESET)"
	@echo "  Prometheus:              localhost:9090"
	@echo "  Grafana:                 localhost:3000"
	@echo "  Grafana login:           admin / fraud_grafana_2024"
	@echo ""
	@echo "$(GREEN)All layers started. Run 'make status' to verify.$(RESET)"

.PHONY: up-all
up-all:
	@echo "$(GREEN)Starting ALL layers simultaneously...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile full up -d
	@echo ""
	@echo "$(YELLOW)Full stack starting — allow 2-3 minutes for all health checks$(RESET)"
	@sleep 10
	@make status

# =============================================================================
# TEARDOWN
# =============================================================================

.PHONY: down
down:
	@echo "$(YELLOW)Stopping all services (volumes preserved)...$(RESET)"
	$(COMPOSE) --profile full --profile core --profile data --profile compute --profile orchestration --profile monitoring stop

.PHONY: down-all
down-all:
	@echo "$(YELLOW)Stopping and removing containers (volumes preserved)...$(RESET)"
	$(COMPOSE) --profile full --profile core --profile data --profile compute --profile orchestration --profile monitoring down

.PHONY: clean
clean:
	@echo "$(YELLOW)WARNING: This will delete ALL data volumes. Are you sure? [y/N]$(RESET)"
	@read -r ans && [ "$$ans" = "y" ] || (echo "Aborted." && exit 1)
	$(COMPOSE) --profile full --profile core --profile data --profile compute --profile orchestration --profile monitoring down -v
	@echo "$(GREEN)All containers and volumes removed.$(RESET)"

# =============================================================================
# STATUS & OBSERVABILITY
# =============================================================================

.PHONY: status
status:
	@echo "$(CYAN)=== Service Status ===$(RESET)"
	@$(COMPOSE) ps --format "table {{.Name}}\t{{.Service}}\t{{.Status}}\t{{.Health}}" 2>/dev/null || $(COMPOSE) ps
	@echo ""

.PHONY: ps
ps:
	$(COMPOSE) ps

.PHONY: logs
logs:
	$(COMPOSE) logs -f --tail=100

.PHONY: logs-core
logs-core:
	$(COMPOSE) logs -f --tail=50 redpanda redis postgres

.PHONY: logs-data
logs-data:
	$(COMPOSE) logs -f --tail=50 clickhouse minio neo4j

.PHONY: logs-compute
logs-compute:
	$(COMPOSE) logs -f --tail=50 flink-jobmanager flink-taskmanager mlflow

.PHONY: logs-monitoring
logs-monitoring:
	$(COMPOSE) logs -f --tail=50 prometheus grafana

logs:
ifdef SERVICE
	docker logs -f $(SERVICE) --tail=100
else
	$(COMPOSE) logs -f --tail=50
endif

.PHONY: shell
shell:
ifdef SERVICE
	docker exec -it $(SERVICE) /bin/sh || docker exec -it $(SERVICE) /bin/bash
else
	@echo "Usage: make shell SERVICE=fraud_postgres"
endif

.PHONY: restart
restart:
ifdef SERVICE
	$(COMPOSE) restart $(SERVICE)
else
	@echo "Usage: make restart SERVICE=fraud_redis"
endif

# =============================================================================
# IMAGE MANAGEMENT
# =============================================================================

.PHONY: pull
pull:
	@echo "$(GREEN)Pulling latest images...$(RESET)"
	$(COMPOSE) --profile full pull

# =============================================================================
# VALIDATION — connectivity tests
# =============================================================================

.PHONY: validate-core
validate-core:
	@echo "$(CYAN)Validating core layer...$(RESET)"
	@echo -n "  PostgreSQL: "
	@docker exec fraud_postgres pg_isready -U fraud_admin -d fraud_db 2>/dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"
	@echo -n "  Redis: "
	@docker exec fraud_redis redis-cli ping 2>/dev/null | grep -q PONG && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"
	@echo -n "  Redpanda (Kafka): "
	@docker exec fraud_redpanda rpk cluster health 2>/dev/null | grep -q "Healthy:.* true" && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"
	@echo -n "  Redpanda (topics): "
	@docker exec fraud_redpanda rpk topic list 2>/dev/null && echo "$(GREEN)Topics listed$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"

.PHONY: validate-data
validate-data:
	@echo "$(CYAN)Validating data layer...$(RESET)"
	@echo -n "  ClickHouse: "
	@curl -sf http://localhost:8123/ping 2>/dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"
	@echo -n "  MinIO: "
	@curl -sf http://localhost:9001/minio/health/live 2>/dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"
	@echo -n "  Neo4j: "
	@curl -sf http://localhost:7474 2>/dev/null | grep -q "neo4j" && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"

.PHONY: validate-compute
validate-compute:
	@echo "$(CYAN)Validating compute layer...$(RESET)"
	@echo -n "  Flink JobManager: "
	@curl -sf http://localhost:8083/overview 2>/dev/null | grep -q "flink" && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"
	@echo -n "  MLflow: "
	@curl -sf http://localhost:5000/health 2>/dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"

.PHONY: validate-all
validate-all: validate-core validate-data validate-compute
	@echo ""
	@echo "$(CYAN)Validating monitoring layer...$(RESET)"
	@echo -n "  Prometheus: "
	@curl -sf http://localhost:9090/-/healthy 2>/dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"
	@echo -n "  Grafana: "
	@curl -sf http://localhost:3000/api/health 2>/dev/null | grep -q "ok" && echo "$(GREEN)OK$(RESET)" || echo "$(YELLOW)NOT READY$(RESET)"

# =============================================================================
# UTILITY
# =============================================================================

.PHONY: ports
ports:
	@echo "$(CYAN)=== Service Port Map ===$(RESET)"
	@echo ""
	@echo "CORE LAYER"
	@echo "  Redpanda Kafka:          localhost:9092"
	@echo "  Redpanda Admin API:      localhost:9644"
	@echo "  Redpanda Schema Reg:     localhost:8081"
	@echo "  Redpanda HTTP Proxy:     localhost:8082"
	@echo "  Redis:                   localhost:6379"
	@echo "  PostgreSQL:              localhost:5432"
	@echo ""
	@echo "DATA LAYER"
	@echo "  ClickHouse HTTP:         localhost:8123"
	@echo "  ClickHouse Native:       localhost:9000"
	@echo "  MinIO S3 API:            localhost:9001"
	@echo "  MinIO Console UI:        localhost:9002"
	@echo "  Neo4j Browser:           localhost:7474"
	@echo "  Neo4j Bolt:              localhost:7687"
	@echo ""
	@echo "COMPUTE LAYER"
	@echo "  Flink Web UI:            localhost:8083"
	@echo "  MLflow Tracking UI:      localhost:5000"
	@echo ""
	@echo "ORCHESTRATION LAYER"
	@echo "  Airflow UI:              localhost:8080"
	@echo ""
	@echo "MONITORING LAYER"
	@echo "  Prometheus:              localhost:9090"
	@echo "  Grafana:                 localhost:3000"
	@echo ""
	@echo "APP MICROSERVICES (Phase 3+)"
	@echo "  API Gateway:             localhost:8000"
	@echo "  Stage 1 (Fast Risk):     localhost:8100"
	@echo "  Stage 2 (Deep Intel):    localhost:8200"
	@echo "  Stage 3 (Decision Eng):  localhost:8300"
	@echo "  Action Engine:           localhost:8400"
	@echo ""

.PHONY: topics
topics:
	@echo "$(CYAN)Redpanda / Kafka Topics:$(RESET)"
	@docker exec fraud_redpanda rpk topic list

.PHONY: topic-describe
topic-describe:
ifdef TOPIC
	docker exec fraud_redpanda rpk topic describe $(TOPIC)
else
	@echo "Usage: make topic-describe TOPIC=txn-raw"
endif

# =============================================================================
# GENERATOR — Phase 1
# =============================================================================

.PHONY: up-generator
up-generator:
	@echo "$(GREEN)Starting GENERATOR — Synthetic transaction producer...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile generator up -d --build
	@echo ""
	@echo "$(CYAN)Generator endpoints:$(RESET)"
	@echo "  Prometheus metrics:  http://localhost:9101/metrics"
	@echo ""
	@echo "$(YELLOW)Runtime overrides (set before command):$(RESET)"
	@echo "  GENERATOR_TPS=1000 make up-generator"
	@echo "  FRAUD_RATE=0.10    make up-generator"

.PHONY: generator-logs
generator-logs:
	docker logs -f fraud_generator --tail=100

.PHONY: generator-stop
generator-stop:
	$(COMPOSE) stop generator

.PHONY: generator-metrics
generator-metrics:
	@curl -s http://localhost:9101/metrics 2>/dev/null | grep "^generator_" || echo "Generator not running"

.PHONY: generator-tps
generator-tps:
ifdef TPS
	GENERATOR_TPS=$(TPS) $(COMPOSE) --env-file $(ENV_FILE) --profile generator up -d generator
else
	@echo "Usage: make generator-tps TPS=1000"
endif

.PHONY: consume-raw
consume-raw:
	@echo "$(CYAN)Consuming 5 messages from txn-raw:$(RESET)"
	docker exec fraud_redpanda rpk topic consume txn-raw --brokers redpanda:9092 -n 5

.PHONY: topic-stats
topic-stats:
	@echo "$(CYAN)Topic stats — txn-raw:$(RESET)"
	docker exec fraud_redpanda rpk topic describe txn-raw --brokers redpanda:9092

# =============================================================================
# FEATURE ENGINE — Phase 2
# =============================================================================

.PHONY: up-feature-engine
up-feature-engine:
	@echo "$(GREEN)Starting FEATURE ENGINE...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile feature-engine up -d --build
	@echo ""
	@echo "$(CYAN)Feature engine:$(RESET)"
	@echo "  Input:    txn-raw (Kafka)"
	@echo "  Output:   txn-enriched (Kafka) + Redis (online) + MinIO (offline)"
	@echo "  Metrics:  http://localhost:9102/metrics"
	@echo "  Features: 18 across velocity/geo/device/behavioral groups"

.PHONY: feature-engine-logs
feature-engine-logs:
	docker logs -f fraud_feature_engine --tail=100

.PHONY: feature-engine-metrics
feature-engine-metrics:
	@curl -s http://localhost:9102/metrics 2>/dev/null | grep "^feature_engine_" || echo "Not running"

.PHONY: consume-enriched
consume-enriched:
	@echo "$(CYAN)Consuming 3 enriched transactions from txn-enriched:$(RESET)"
	docker exec fraud_redpanda rpk topic consume txn-enriched --brokers redpanda:9092 -n 3

.PHONY: redis-inspect
redis-inspect:
ifdef CUSTOMER
	@echo "$(CYAN)Redis state for customer $(CUSTOMER):$(RESET)"
	@docker exec fraud_redis redis-cli --scan --pattern "feat:$(CUSTOMER):*" | head -20
else
	@echo "$(CYAN)Redis key count by prefix:$(RESET)"
	@docker exec fraud_redis redis-cli DBSIZE
	@docker exec fraud_redis redis-cli --scan --pattern "feat:*:behavioral" | wc -l | xargs echo "Active customers:"

endif

.PHONY: flink-submit-feature-job
flink-submit-feature-job:
	@echo "$(YELLOW)Submitting PyFlink feature job to Flink cluster...$(RESET)"
	docker cp services/feature-engine/flink/feature_job.py fraud_flink_jobmanager:/opt/flink/feature_job.py
	docker exec fraud_flink_jobmanager bash -c "cd /opt/flink && pip install redis confluent-kafka -q && flink run -py /opt/flink/feature_job.py"

# =============================================================================
# STAGE 1 — Phase 3
# =============================================================================

.PHONY: up-stage1
up-stage1:
	@echo "$(GREEN)Starting Stage 1 — Fast Risk Estimation...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile stage1 up -d --build
	@echo ""
	@echo "$(CYAN)Stage 1 endpoints:$(RESET)"
	@echo "  REST API:    http://localhost:8100/predict"
	@echo "  Swagger UI:  http://localhost:8100/docs"
	@echo "  Model info:  http://localhost:8100/model-info"
	@echo "  Metrics:     http://localhost:9103/metrics"
	@echo ""
	@echo "$(YELLOW)Note: First startup trains LightGBM (~60s)$(RESET)"

.PHONY: stage1-logs
stage1-logs:
	docker logs -f fraud_stage1 --tail=100

.PHONY: stage1-predict
stage1-predict:
	@echo "$(CYAN)Sending test transaction to Stage 1:$(RESET)"
	@curl -s -X POST http://localhost:8100/predict \
	  -H "Content-Type: application/json" \
	  -d '{"txn_id":"test-001","customer_id":"cust-999","amount":150.0,"country_code":"IN","device_id":"DEV-KNOWN","ip_address":"192.168.1.1","txn_count_1m":1,"txn_count_5m":2,"txn_count_1h":5,"txn_count_24h":12,"amount_sum_1m":150.0,"amount_sum_5m":280.0,"amount_sum_1h":650.0,"amount_sum_24h":1200.0,"geo_velocity_kmh":12.0,"is_new_country":false,"unique_countries_24h":1,"device_trust_score":0.9,"is_new_device":false,"ip_txn_count_1h":3,"unique_devices_24h":1,"amount_vs_avg_ratio":1.2,"merchant_familiarity":0.8,"hours_since_last_txn":6.5,"has_cold_start":false}' \
	  | python3 -m json.tool

.PHONY: stage1-predict-fraud
stage1-predict-fraud:
	@echo "$(CYAN)Sending FRAUD test transaction to Stage 1 (card testing pattern):$(RESET)"
	@curl -s -X POST http://localhost:8100/predict \
	  -H "Content-Type: application/json" \
	  -d '{"txn_id":"fraud-001","customer_id":"cust-evil","amount":2.99,"country_code":"RO","device_id":"DEV-NEW-UNKNOWN","ip_address":"185.220.101.1","txn_count_1m":12,"txn_count_5m":12,"txn_count_1h":12,"txn_count_24h":14,"amount_sum_1m":35.0,"amount_sum_5m":35.0,"amount_sum_1h":35.0,"amount_sum_24h":42.0,"geo_velocity_kmh":9500.0,"is_new_country":true,"unique_countries_24h":3,"device_trust_score":0.0,"is_new_device":true,"ip_txn_count_1h":85,"unique_devices_24h":1,"amount_vs_avg_ratio":0.04,"merchant_familiarity":0.0,"hours_since_last_txn":0.05,"has_cold_start":false}' \
	  | python3 -m json.tool

.PHONY: stage1-model-info
stage1-model-info:
	@curl -s http://localhost:8100/model-info | python3 -m json.tool

.PHONY: stage1-metrics
stage1-metrics:
	@curl -s http://localhost:9103/metrics 2>/dev/null | grep "^stage1_" || echo "Stage 1 not running"

# =============================================================================
# STAGE 2 — Phase 4
# =============================================================================

.PHONY: up-stage2
up-stage2:
	@echo "$(GREEN)Starting Stage 2 — Deep Intelligence...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile stage2 up -d --build
	@echo ""
	@echo "$(CYAN)Stage 2 endpoints:$(RESET)"
	@echo "  REST API:    http://localhost:8200/predict"
	@echo "  Swagger UI:  http://localhost:8200/docs"
	@echo "  Model info:  http://localhost:8200/model-info"
	@echo "  Metrics:     http://localhost:9104/metrics"
	@echo ""
	@echo "$(YELLOW)Note: First startup trains XGBoost + MLP + AE + IsoForest (~2-3 min)$(RESET)"
	@echo "$(YELLOW)      Neo4j takes ~60s to start — stage2 will wait$(RESET)"

.PHONY: stage2-logs
stage2-logs:
	docker logs -f fraud_stage2 --tail=100

.PHONY: stage2-predict
stage2-predict:
	@echo "$(CYAN)Sending legitimate transaction to Stage 2:$(RESET)"
	@curl -s -X POST http://localhost:8200/predict \
	  -H "Content-Type: application/json" \
	  -d '{"txn_id":"s2-legit-001","customer_id":"c-prem-001","amount":250.0,"device_id":"DEV-KNOWN","ip_address":"192.168.1.10","country_code":"IN","merchant_id":"MER-GROCERY","channel":"POS","account_age_days":730,"clv":45000.0,"trust_score":0.88,"customer_segment":"premium","p_fraud_stage1":0.32,"txn_count_1m":1,"txn_count_5m":2,"txn_count_1h":4,"txn_count_24h":10,"amount_sum_1m":250.0,"amount_sum_5m":400.0,"amount_sum_1h":900.0,"amount_sum_24h":2100.0,"geo_velocity_kmh":8.0,"is_new_country":false,"unique_countries_24h":1,"device_trust_score":0.95,"is_new_device":false,"ip_txn_count_1h":2,"unique_devices_24h":1,"amount_vs_avg_ratio":1.1,"merchant_familiarity":0.9,"hours_since_last_txn":8.0,"has_cold_start":false}' \
	  | python3 -m json.tool

.PHONY: stage2-predict-ring
stage2-predict-ring:
	@echo "$(CYAN)Sending FRAUD RING transaction to Stage 2:$(RESET)"
	@curl -s -X POST http://localhost:8200/predict \
	  -H "Content-Type: application/json" \
	  -d '{"txn_id":"s2-ring-001","customer_id":"c-mule-007","amount":499.0,"device_id":"DEV-SHARED-EVIL","ip_address":"10.10.10.99","country_code":"NG","merchant_id":"MER-GIFT","channel":"WEB","account_age_days":14,"clv":800.0,"trust_score":0.15,"customer_segment":"risky","p_fraud_stage1":0.78,"txn_count_1m":3,"txn_count_5m":8,"txn_count_1h":18,"txn_count_24h":42,"amount_sum_1m":1497.0,"amount_sum_5m":3992.0,"amount_sum_1h":8991.0,"amount_sum_24h":20958.0,"geo_velocity_kmh":250.0,"is_new_country":true,"unique_countries_24h":2,"device_trust_score":0.0,"is_new_device":true,"ip_txn_count_1h":67,"unique_devices_24h":1,"amount_vs_avg_ratio":3.2,"merchant_familiarity":0.0,"hours_since_last_txn":0.2,"has_cold_start":false}' \
	  | python3 -m json.tool

.PHONY: stage2-model-info
stage2-model-info:
	@curl -s http://localhost:8200/model-info | python3 -m json.tool

.PHONY: stage2-metrics
stage2-metrics:
	@curl -s http://localhost:9104/metrics 2>/dev/null | grep "^stage2_" || echo "Stage 2 not running"

.PHONY: neo4j-query
neo4j-query:
	@echo "$(CYAN)Neo4j: Counting nodes by label:$(RESET)"
	@docker exec fraud_neo4j cypher-shell -u neo4j -p fraud_neo4j_2024 \
	  "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC" 2>/dev/null || \
	  echo "Neo4j not running or no data yet"

.PHONY: neo4j-fraud-rings
neo4j-fraud-rings:
	@echo "$(CYAN)Neo4j: Customers sharing devices (potential fraud rings):$(RESET)"
	@docker exec fraud_neo4j cypher-shell -u neo4j -p fraud_neo4j_2024 \
	  "MATCH (c1:Customer)-[:USED]->(d:Device)<-[:USED]-(c2:Customer) WHERE c1.customer_id < c2.customer_id RETURN d.device_id AS shared_device, c1.customer_id AS customer1, c2.customer_id AS customer2 LIMIT 10" 2>/dev/null || \
	  echo "Neo4j not running or no data yet"

# =============================================================================
# STAGE 3 — Phase 5
# =============================================================================

.PHONY: up-stage3
up-stage3:
	@echo "$(GREEN)Starting Stage 3 — Decision Optimization Engine...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile stage3 up -d --build
	@echo ""
	@echo "$(CYAN)Stage 3 endpoints:$(RESET)"
	@echo "  REST API:   http://localhost:8300/decide"
	@echo "  Swagger UI: http://localhost:8300/docs"
	@echo "  Config:     http://localhost:8300/config"
	@echo "  Metrics:    http://localhost:9105/metrics"

.PHONY: stage3-logs
stage3-logs:
	docker logs -f fraud_stage3 --tail=100

.PHONY: stage3-decide
stage3-decide:
	@echo "$(CYAN)Sending mid-risk transaction to Stage 3:$(RESET)"
	@curl -s -X POST http://localhost:8300/decide \
	  -H "Content-Type: application/json" \
	  -d '{"txn_id":"s3-001","customer_id":"cust-premium","amount":1200.0,"currency":"USD","clv":75000.0,"trust_score":0.88,"account_age_days":1200,"customer_segment":"premium","p_fraud":0.42,"confidence":0.82,"p_fraud_stage1":0.38,"uncertainty_stage1":0.18,"xgb_score":0.45,"mlp_score":0.40,"graph_risk_score":0.1,"anomaly_score":0.05,"is_anomaly":false}' \
	  | python3 -m json.tool

.PHONY: stage3-decide-ring
stage3-decide-ring:
	@echo "$(CYAN)Sending fraud ring transaction to Stage 3:$(RESET)"
	@curl -s -X POST http://localhost:8300/decide \
	  -H "Content-Type: application/json" \
	  -d '{"txn_id":"s3-ring-001","customer_id":"cust-mule","amount":800.0,"currency":"USD","clv":1200.0,"trust_score":0.15,"account_age_days":14,"customer_segment":"risky","p_fraud":0.72,"confidence":0.85,"p_fraud_stage1":0.68,"uncertainty_stage1":0.15,"xgb_score":0.75,"mlp_score":0.70,"graph_risk_score":0.88,"fraud_ring_score":0.87,"mule_account_score":0.72,"multi_hop_score":0.65,"anomaly_score":0.55,"is_anomaly":true}' \
	  | python3 -m json.tool

.PHONY: stage3-config
stage3-config:
	@curl -s http://localhost:8300/config | python3 -m json.tool

# =============================================================================
# SINKS — Phase 6
# =============================================================================

.PHONY: up-sinks
up-sinks:
	@echo "$(GREEN)Starting Decision Sink (Kafka → PostgreSQL + ClickHouse)...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile sinks up -d --build

.PHONY: sink-logs
sink-logs:
	docker logs -f fraud_decision_sink --tail=100

.PHONY: clickhouse-fraud-rate
clickhouse-fraud-rate:
	@echo "$(CYAN)ClickHouse: fraud rate by hour (last 24h):$(RESET)"
	@docker exec fraud_clickhouse clickhouse-client \
	  --user fraud_admin --password fraud_secret_2024 \
	  --query "SELECT * FROM fraud_analytics.fraud_rate_24h LIMIT 10" 2>/dev/null || echo "ClickHouse not running"

.PHONY: pg-decisions
pg-decisions:
	@echo "$(CYAN)PostgreSQL: last 5 decisions:$(RESET)"
	@docker exec fraud_postgres psql -U fraud_admin -d fraud_db \
	  -c "SELECT txn_id, action, p_fraud, latency_ms, decided_at FROM decisions.records ORDER BY decided_at DESC LIMIT 5;" 2>/dev/null || echo "PostgreSQL not running"

# =============================================================================
# API GATEWAY + E2E TEST
# =============================================================================

.PHONY: up-gateway
up-gateway:
	@echo "$(GREEN)Starting API Gateway...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile gateway up -d --build
	@echo ""
	@echo "$(CYAN)API Gateway:$(RESET)"
	@echo "  REST API:    http://localhost:8000/transaction"
	@echo "  Swagger UI:  http://localhost:8000/docs"
	@echo "  Health:      http://localhost:8000/health"
	@echo "  Ready:       http://localhost:8000/ready"
	@echo "  Stats:       http://localhost:8000/stats"
	@echo "  Metrics:     http://localhost:9106/metrics"

.PHONY: gateway-logs
gateway-logs:
	docker logs -f fraud_api_gateway --tail=100

.PHONY: e2e-test
e2e-test:
	@echo "$(CYAN)Running end-to-end integration tests...$(RESET)"
	@python3 platform/scripts/e2e_test.py --gateway http://localhost:8000

.PHONY: e2e-test-verbose
e2e-test-verbose:
	@python3 platform/scripts/e2e_test.py --gateway http://localhost:8000 --verbose

.PHONY: demo
demo:
	@echo "$(CYAN)Demo: Legitimate transaction$(RESET)"
	@curl -s -X POST http://localhost:8000/transaction \
	  -H "Content-Type: application/json" \
	  -d '{"txn_id":"demo-legit-001","customer_id":"cust-demo","amount":85.0,"currency":"USD","channel":"POS","merchant_category":"grocery","device_id":"DEV-HOME","ip_address":"192.168.1.1","country_code":"IN","clv":12000.0,"trust_score":0.85,"account_age_days":730,"customer_segment":"standard","features":{"txn_count_1m":1,"txn_count_5m":2,"txn_count_1h":4,"txn_count_24h":10,"amount_sum_1m":85,"amount_sum_5m":160,"amount_sum_1h":380,"amount_sum_24h":920,"geo_velocity_kmh":5,"is_new_country":false,"unique_countries_24h":1,"device_trust_score":0.92,"is_new_device":false,"ip_txn_count_1h":2,"unique_devices_24h":1,"amount_vs_avg_ratio":0.85,"merchant_familiarity":0.9,"hours_since_last_txn":7}}' \
	  | python3 -m json.tool
	@echo ""
	@echo "$(CYAN)Demo: Card testing attack$(RESET)"
	@curl -s -X POST http://localhost:8000/transaction \
	  -H "Content-Type: application/json" \
	  -d '{"txn_id":"demo-fraud-001","customer_id":"cust-victim","amount":1.99,"currency":"USD","channel":"WEB","merchant_category":"online_retail","device_id":"DEV-ATTACKER","ip_address":"185.220.101.45","is_new_device":true,"is_new_ip":true,"country_code":"RO","clv":8000.0,"trust_score":0.65,"account_age_days":200,"customer_segment":"standard","features":{"txn_count_1m":12,"txn_count_5m":12,"txn_count_1h":12,"txn_count_24h":14,"amount_sum_1m":24,"amount_sum_5m":24,"amount_sum_1h":24,"amount_sum_24h":28,"geo_velocity_kmh":9200,"is_new_country":true,"unique_countries_24h":2,"device_trust_score":0.0,"is_new_device":true,"ip_txn_count_1h":82,"unique_devices_24h":1,"amount_vs_avg_ratio":0.03,"merchant_familiarity":0.0,"hours_since_last_txn":0.02}}' \
	  | python3 -m json.tool

.PHONY: gateway-stats
gateway-stats:
	@curl -s http://localhost:8000/stats | python3 -m json.tool

# =============================================================================
# LOAD TEST + NEO4J SEED + FEAST
# =============================================================================

.PHONY: load-test
load-test:
	@echo "$(CYAN)Load test: 500 TPS for 30s$(RESET)"
	python3 platform/scripts/load_test.py --tps 500 --duration 30 --gateway http://localhost:8000

.PHONY: load-test-ramp
load-test-ramp:
	@echo "$(CYAN)Load test ramp: 10 → 1000 TPS over 60s$(RESET)"
	python3 platform/scripts/load_test.py --tps 1000 --mode ramp --duration 60

.PHONY: load-test-spike
load-test-spike:
	@echo "$(CYAN)Load test spike: 200 TPS → 1000 TPS spike → recovery$(RESET)"
	python3 platform/scripts/load_test.py --tps 200 --mode spike

.PHONY: neo4j-seed
neo4j-seed:
	@echo "$(CYAN)Seeding Neo4j graph (constraints + fraud ring sample data)...$(RESET)"
	@docker exec -i fraud_neo4j cypher-shell \
	  -u neo4j -p fraud_neo4j_2024 \
	  < platform/scripts/neo4j/init_graph.cypher 2>/dev/null && \
	  echo "$(GREEN)Neo4j seeded successfully$(RESET)" || \
	  echo "$(AMBER)Neo4j not running — start with: make up-data$(RESET)"

.PHONY: feast-apply
feast-apply:
	@echo "$(CYAN)Applying Feast feature definitions...$(RESET)"
	cd platform/feature-store && feast apply || echo "$(AMBER)Install feast: pip install feast$(RESET)"

.PHONY: feast-materialize
feast-materialize:
	@echo "$(CYAN)Materializing features to Redis online store...$(RESET)"
	cd platform/feature-store && feast materialize-incremental $$(date -u +"%Y-%m-%dT%H:%M:%S")

# =============================================================================
# FULL SYSTEM MANAGEMENT
# =============================================================================

.PHONY: up-all
up-all:
	@echo "$(GREEN)Starting all 23 services...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile full up -d --build
	@echo ""
	@echo "$(CYAN)Waiting for services to be ready...$(RESET)"
	@echo "  Stage 1 trains LightGBM (~60s)"
	@echo "  Stage 2 trains XGBoost + MLP (~3 min)"
	@echo ""
	@echo "$(CYAN)Access points:$(RESET)"
	@echo "  API Gateway:  http://localhost:8000"
	@echo "  Swagger UI:   http://localhost:8000/docs"
	@echo "  Grafana:      http://localhost:3000  (admin/fraud_grafana_2024)"
	@echo "  MLflow:       http://localhost:5000"
	@echo "  Airflow:      http://localhost:8080  (admin/fraud_admin_2024)"
	@echo "  Neo4j:        http://localhost:7474  (neo4j/fraud_neo4j_2024)"
	@echo "  MinIO:        http://localhost:9002  (fraud_minio/fraud_minio_2024)"

.PHONY: validate-all
validate-all:
	@echo "$(CYAN)Checking all service health endpoints...$(RESET)"
	@for svc in "8000/health" "8100/health" "8200/health" "8300/health"; do \
	  url="http://localhost:$$svc"; \
	  status=$$(curl -s -o /dev/null -w "%{http_code}" $$url 2>/dev/null); \
	  if [ "$$status" = "200" ]; then \
	    echo "  $(GREEN)✓$(RESET) $$url"; \
	  else \
	    echo "  $(RED)✗$(RESET) $$url (HTTP $$status)"; \
	  fi; \
	done

.PHONY: status
status:
	@echo "$(CYAN)Service status:$(RESET)"
	@$(COMPOSE) --env-file $(ENV_FILE) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | head -30

.PHONY: down
down:
	@echo "$(AMBER)Stopping all services...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) down

.PHONY: clean
clean:
	@echo "$(RED)Removing all services and volumes...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) down -v --remove-orphans

# =============================================================================
# APPLICATION LAYER — Milestone A
# =============================================================================

.PHONY: up-app
up-app:
	@echo "$(GREEN)Starting Application Layer (Backend + Frontend)...$(RESET)"
	$(COMPOSE) --env-file $(ENV_FILE) --profile app up -d --build
	@echo ""
	@echo "$(CYAN)Application Portal:$(RESET)"
	@echo "  Frontend:    http://localhost:3005"
	@echo "  App Backend: http://localhost:8400"
	@echo "  API Docs:    http://localhost:8400/docs"
	@echo ""
	@echo "$(CYAN)Demo accounts:$(RESET)"
	@echo "  admin    / admin2024!    (ADMIN)"
	@echo "  analyst1 / analyst2024! (ANALYST)"
	@echo "  ops1     / ops2024!     (OPS_MANAGER)"
	@echo "  partner1 / partner2024! (BANK_PARTNER)"

.PHONY: app-backend-logs
app-backend-logs:
	docker logs -f fraud_app_backend --tail=100

.PHONY: app-frontend-logs
app-frontend-logs:
	docker logs -f fraud_frontend --tail=100

.PHONY: app-test-auth
app-test-auth:
	@echo "$(CYAN)Testing app-backend auth (admin login):$(RESET)"
	@curl -s -X POST http://localhost:8400/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"admin","password":"admin2024!"}' | python3 -m json.tool

.PHONY: app-test-analytics
app-test-analytics:
	@echo "$(CYAN)Testing analytics overview endpoint:$(RESET)"
	@TOKEN=$$(curl -s -X POST http://localhost:8400/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"ops1","password":"ops2024!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && \
	curl -s http://localhost:8400/analytics/overview \
	  -H "Authorization: Bearer $$TOKEN" | python3 -m json.tool

.PHONY: app-sync-queue
app-sync-queue:
	@echo "$(CYAN)Syncing MANUAL_REVIEW decisions into review queue...$(RESET)"
	@TOKEN=$$(curl -s -X POST http://localhost:8400/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"analyst1","password":"analyst2024!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && \
	curl -s -X POST http://localhost:8400/review-queue/sync-from-decisions \
	  -H "Authorization: Bearer $$TOKEN" | python3 -m json.tool
