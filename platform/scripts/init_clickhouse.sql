-- =============================================================================
-- ClickHouse Initialization — Fraud Analytics OLAP Store
-- All tables use MergeTree family engines for high-speed ingestion + queries
-- =============================================================================

CREATE DATABASE IF NOT EXISTS fraud_analytics;

USE fraud_analytics;

-- ---------------------------------------------------------------------------
-- Decision event log — core analytics table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fraud_analytics.decisions
(
    decided_at           DateTime64(3, 'UTC'),
    decision_id          UUID,
    txn_id               UUID,
    customer_id          UUID,
    pipeline_stage       UInt8,
    action               LowCardinality(String),
    p_fraud              Float32,
    uncertainty          Float32,
    graph_risk_score     Float32,
    anomaly_score        Float32,
    amount               Decimal(14, 2),
    currency             FixedString(3),
    channel              LowCardinality(String),
    merchant_category    LowCardinality(String),
    country_code         FixedString(2),
    clv_at_decision      Decimal(12, 2),
    trust_score          Float32,
    expected_loss        Decimal(14, 2),
    expected_friction    Decimal(14, 2),
    expected_review_cost Decimal(14, 2),
    latency_ms           Float32,
    model_version        LowCardinality(String),
    ab_experiment_id     String,
    ab_variant           LowCardinality(String),
    explanation          String
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(decided_at)
ORDER BY (decided_at, action, pipeline_stage)
TTL toDateTime(decided_at) + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;

-- ---------------------------------------------------------------------------
-- Hourly summary destination table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fraud_analytics.decisions_hourly_mv_dest
(
    hour                DateTime,
    action              LowCardinality(String),
    pipeline_stage      UInt8,
    channel             LowCardinality(String),
    country_code        FixedString(2),
    decision_count      UInt64,
    total_amount        Decimal(18, 2),
    avg_p_fraud         Float32,
    avg_latency_ms      Float32,
    avg_uncertainty     Float32,
    total_expected_loss Decimal(18, 2)
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, action, pipeline_stage, channel, country_code);

-- ---------------------------------------------------------------------------
-- Materialized view: auto-aggregate on insert
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS fraud_analytics.decisions_hourly_mv
TO fraud_analytics.decisions_hourly_mv_dest
AS
SELECT
    toStartOfHour(decided_at)  AS hour,
    action,
    pipeline_stage,
    channel,
    country_code,
    count()                    AS decision_count,
    sum(amount)                AS total_amount,
    avg(p_fraud)               AS avg_p_fraud,
    avg(latency_ms)            AS avg_latency_ms,
    avg(uncertainty)           AS avg_uncertainty,
    sum(expected_loss)         AS total_expected_loss
FROM fraud_analytics.decisions
GROUP BY hour, action, pipeline_stage, channel, country_code;

-- ---------------------------------------------------------------------------
-- Enriched transaction store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fraud_analytics.transactions
(
    txn_ts               DateTime64(3, 'UTC'),
    txn_id               UUID,
    customer_id          UUID,
    amount               Decimal(14, 2),
    currency             FixedString(3),
    merchant_id          String,
    merchant_category    LowCardinality(String),
    channel              LowCardinality(String),
    device_id            String,
    ip_address           IPv4,
    country_code         FixedString(2),
    city                 String,
    txn_count_1h         UInt32,
    txn_count_24h        UInt32,
    amount_sum_1h        Decimal(14, 2),
    amount_sum_24h       Decimal(14, 2),
    unique_merchants_24h UInt16,
    unique_countries_24h UInt8,
    geo_velocity_km_h    Float32,
    is_new_device        UInt8,
    is_new_country       UInt8
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(txn_ts)
ORDER BY (txn_ts, customer_id)
TTL toDateTime(txn_ts) + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- ---------------------------------------------------------------------------
-- Model predictions — for drift detection
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fraud_analytics.model_predictions
(
    predicted_at    DateTime64(3, 'UTC'),
    txn_id          UUID,
    model_name      LowCardinality(String),
    model_version   LowCardinality(String),
    p_fraud         Float32,
    uncertainty     Float32,
    features_hash   String,
    latency_ms      Float32
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(predicted_at)
ORDER BY (predicted_at, model_name, model_version)
TTL toDateTime(predicted_at) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- ---------------------------------------------------------------------------
-- A/B experiment results
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fraud_analytics.ab_experiment_results
(
    logged_at       DateTime64(3, 'UTC'),
    experiment_id   String,
    variant         LowCardinality(String),
    txn_id          UUID,
    action          LowCardinality(String),
    p_fraud         Float32,
    amount          Decimal(14, 2),
    expected_loss   Decimal(14, 2),
    expected_friction Decimal(14, 2),
    latency_ms      Float32,
    outcome         LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(logged_at)
ORDER BY (logged_at, experiment_id, variant)
TTL toDateTime(logged_at) + INTERVAL 1 YEAR;

-- ---------------------------------------------------------------------------
-- Chargeback analytics
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fraud_analytics.chargebacks
(
    reported_at         DateTime64(3, 'UTC'),
    chargeback_id       UUID,
    txn_id              UUID,
    amount              Decimal(14, 2),
    currency            FixedString(3),
    reason_code         LowCardinality(String),
    action_taken        LowCardinality(String),
    p_fraud_at_decision Float32,
    model_version       LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(reported_at)
ORDER BY (reported_at, reason_code)
TTL toDateTime(reported_at) + INTERVAL 3 YEAR;

-- ---------------------------------------------------------------------------
-- Dashboard views
-- ---------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS fraud_analytics.fraud_rate_24h AS
SELECT
    toStartOfHour(decided_at)                           AS hour,
    countIf(action = 'BLOCK')                           AS blocked,
    countIf(action = 'APPROVE')                         AS approved,
    countIf(action = 'STEP_UP_AUTH' OR action = 'STEP_UP') AS step_up,
    countIf(action = 'MANUAL_REVIEW' OR action = 'REVIEW') AS manual_review,
    count()                                             AS total,
    round(countIf(action = 'BLOCK') / count() * 100, 2) AS block_rate_pct,
    round(avg(latency_ms), 2)                           AS avg_latency_ms,
    round(quantile(0.95)(latency_ms), 2)                AS p95_latency_ms
FROM fraud_analytics.decisions
WHERE decided_at >= now() - INTERVAL 24 HOUR
GROUP BY hour
ORDER BY hour DESC;

CREATE VIEW IF NOT EXISTS fraud_analytics.pipeline_stage_distribution AS
SELECT
    toStartOfHour(decided_at) AS hour,
    pipeline_stage,
    count()                   AS count,
    round(avg(latency_ms), 2) AS avg_latency_ms
FROM fraud_analytics.decisions
WHERE decided_at >= now() - INTERVAL 24 HOUR
GROUP BY hour, pipeline_stage
ORDER BY hour DESC, pipeline_stage;
