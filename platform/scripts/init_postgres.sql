-- =============================================================================
-- PostgreSQL Initialization — Fraud Detection System
-- Creates: fraud_db, mlflow_db, airflow_db + schemas + core tables
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Create additional databases
-- ---------------------------------------------------------------------------
SELECT 'CREATE DATABASE mlflow_db OWNER fraud_admin'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mlflow_db')\gexec

SELECT 'CREATE DATABASE airflow_db OWNER fraud_admin'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow_db')\gexec

-- ---------------------------------------------------------------------------
-- fraud_db — main application database
-- ---------------------------------------------------------------------------
\c fraud_db;

CREATE SCHEMA IF NOT EXISTS transactions;
CREATE SCHEMA IF NOT EXISTS decisions;
CREATE SCHEMA IF NOT EXISTS customers;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS experiments;

-- ---------------------------------------------------------------------------
-- customers schema
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS customers.profiles (
    customer_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id         VARCHAR(64) UNIQUE NOT NULL,
    segment             VARCHAR(32) NOT NULL DEFAULT 'standard',
    clv                 NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
    trust_score         NUMERIC(5, 4) NOT NULL DEFAULT 0.5 CHECK (trust_score BETWEEN 0 AND 1),
    account_age_days    INTEGER NOT NULL DEFAULT 0,
    risk_region         VARCHAR(64),
    preferred_mfa       VARCHAR(32) DEFAULT 'sms',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_customers_external_id ON customers.profiles (external_id);
CREATE INDEX idx_customers_segment ON customers.profiles (segment);

-- ---------------------------------------------------------------------------
-- transactions schema
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS transactions.events (
    txn_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_txn_id     VARCHAR(128) UNIQUE NOT NULL,
    customer_id         UUID REFERENCES customers.profiles(customer_id),
    amount              NUMERIC(14, 2) NOT NULL,
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    merchant_id         VARCHAR(64),
    merchant_category   VARCHAR(64),
    channel             VARCHAR(32) NOT NULL, -- ATM, POS, MOBILE, WEB, CARD_NETWORK
    device_id           VARCHAR(128),
    ip_address          INET,
    country_code        CHAR(2),
    city                VARCHAR(128),
    lat                 NUMERIC(10, 7),
    lng                 NUMERIC(10, 7),
    txn_ts              TIMESTAMPTZ NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_txn_customer_id   ON transactions.events (customer_id);
CREATE INDEX idx_txn_ts            ON transactions.events (txn_ts DESC);
CREATE INDEX idx_txn_device_id     ON transactions.events (device_id);
CREATE INDEX idx_txn_merchant_id   ON transactions.events (merchant_id);
CREATE INDEX idx_txn_ip            ON transactions.events (ip_address);

-- ---------------------------------------------------------------------------
-- decisions schema
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS decisions.records (
    decision_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    txn_id              UUID NOT NULL,
    pipeline_stage      SMALLINT NOT NULL CHECK (pipeline_stage IN (1, 2, 3)),
    action              VARCHAR(32) NOT NULL CHECK (action IN ('APPROVE', 'BLOCK', 'STEP_UP_AUTH', 'MANUAL_REVIEW')),
    p_fraud             NUMERIC(8, 6) NOT NULL,
    uncertainty         NUMERIC(8, 6),
    graph_risk_score    NUMERIC(8, 6),
    anomaly_score       NUMERIC(8, 6),
    clv_at_decision     NUMERIC(12, 2),
    trust_score         NUMERIC(5, 4),
    expected_loss       NUMERIC(14, 2),
    expected_friction   NUMERIC(14, 2),
    expected_review_cost NUMERIC(14, 2),
    explanation         JSONB,               -- SHAP values + reason codes
    model_version       VARCHAR(64),
    ab_experiment_id    VARCHAR(64),
    ab_variant          VARCHAR(32),
    latency_ms          NUMERIC(8, 2),
    decided_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_decisions_txn_id      ON decisions.records (txn_id);
CREATE INDEX idx_decisions_action      ON decisions.records (action);
CREATE INDEX idx_decisions_decided_at  ON decisions.records (decided_at DESC);
CREATE INDEX idx_decisions_ab          ON decisions.records (ab_experiment_id, ab_variant);

-- ---------------------------------------------------------------------------
-- audit schema — immutable event log
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit.events (
    audit_id            BIGSERIAL PRIMARY KEY,
    event_type          VARCHAR(64) NOT NULL,
    entity_type         VARCHAR(64) NOT NULL,
    entity_id           UUID NOT NULL,
    actor               VARCHAR(128) NOT NULL DEFAULT 'system',
    payload             JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_entity     ON audit.events (entity_type, entity_id);
CREATE INDEX idx_audit_created_at ON audit.events (created_at DESC);

-- Analyst label table (feedback loop input)
CREATE TABLE IF NOT EXISTS audit.analyst_labels (
    label_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    txn_id              UUID NOT NULL,
    decision_id         UUID NOT NULL,
    analyst_id          VARCHAR(64) NOT NULL,
    label               VARCHAR(32) NOT NULL CHECK (label IN ('FRAUD', 'LEGITIMATE', 'UNCERTAIN')),
    confidence          NUMERIC(5, 4) CHECK (confidence BETWEEN 0 AND 1),
    notes               TEXT,
    labeled_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Chargeback events (ground truth)
CREATE TABLE IF NOT EXISTS audit.chargebacks (
    chargeback_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    txn_id              UUID NOT NULL,
    external_cb_id      VARCHAR(128) UNIQUE NOT NULL,
    reason_code         VARCHAR(32) NOT NULL,
    amount              NUMERIC(14, 2) NOT NULL,
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    reported_at         TIMESTAMPTZ NOT NULL,
    processed_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chargebacks_txn_id ON audit.chargebacks (txn_id);

-- ---------------------------------------------------------------------------
-- experiments schema — A/B testing
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS experiments.definitions (
    experiment_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(128) UNIQUE NOT NULL,
    description         TEXT,
    status              VARCHAR(32) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','RUNNING','PAUSED','COMPLETED')),
    variants            JSONB NOT NULL,  -- [{"id": "control", "weight": 0.5}, {"id": "treatment", "weight": 0.5}]
    metrics             JSONB NOT NULL,  -- metrics to track
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Seed data — customer segments
-- ---------------------------------------------------------------------------
INSERT INTO customers.profiles (external_id, segment, clv, trust_score, account_age_days)
VALUES
    ('SEED_PREMIUM_001', 'premium', 85000.00, 0.92, 1825),
    ('SEED_STANDARD_001', 'standard', 12000.00, 0.65, 365),
    ('SEED_NEW_001', 'new', 500.00, 0.40, 7)
ON CONFLICT (external_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Useful views
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW decisions.daily_summary AS
SELECT
    DATE_TRUNC('day', decided_at) AS day,
    action,
    pipeline_stage,
    COUNT(*) AS decision_count,
    AVG(p_fraud)::NUMERIC(6,4) AS avg_p_fraud,
    AVG(latency_ms)::NUMERIC(8,2) AS avg_latency_ms,
    SUM(expected_loss)::NUMERIC(14,2) AS total_expected_loss
FROM decisions.records
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 2;

-- Ensure existing deployments accept current Stage3 action names.
DO $$
BEGIN
    ALTER TABLE decisions.records DROP CONSTRAINT IF EXISTS records_action_check;
    ALTER TABLE decisions.records
        ADD CONSTRAINT records_action_check
        CHECK (action IN ('APPROVE', 'BLOCK', 'STEP_UP_AUTH', 'MANUAL_REVIEW'));
EXCEPTION WHEN undefined_table THEN
    NULL;
END$$;

COMMENT ON VIEW decisions.daily_summary IS 'Daily decision breakdown by action and pipeline stage';

-- =============================================================================
-- APP SCHEMA — Application Backend (Milestone A)
-- Created by: app-backend on first startup via SQLAlchemy
-- Included here for manual init or fresh deployments
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS app;

-- Users (analysts, ops managers, admins, bank partners)
CREATE TABLE IF NOT EXISTS app.app_users (
    id              VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    username        VARCHAR(64)  UNIQUE NOT NULL,
    email           VARCHAR(128) UNIQUE NOT NULL,
    hashed_password VARCHAR(128) NOT NULL,
    role            VARCHAR(32)  NOT NULL DEFAULT 'ANALYST'
                        CHECK (role IN ('ANALYST','OPS_MANAGER','ADMIN','BANK_PARTNER')),
    org_id          VARCHAR(64),
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_app_users_username ON app.app_users(username);

-- API keys (machine-to-machine auth)
CREATE TABLE IF NOT EXISTS app.app_api_keys (
    id           VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id      VARCHAR(36)  NOT NULL REFERENCES app.app_users(id) ON DELETE CASCADE,
    key_hash     VARCHAR(128) UNIQUE NOT NULL,
    name         VARCHAR(64)  NOT NULL,
    is_active    BOOLEAN      NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    expires_at   TIMESTAMPTZ
);

-- Review cases (MANUAL_REVIEW decisions awaiting analyst action)
CREATE TABLE IF NOT EXISTS app.app_review_cases (
    id               VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    txn_id           VARCHAR(64)  NOT NULL,
    customer_id      VARCHAR(64)  NOT NULL,
    amount           DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency         VARCHAR(8)   NOT NULL DEFAULT 'USD',
    channel          VARCHAR(32)  NOT NULL DEFAULT '',
    country_code     VARCHAR(8)   NOT NULL DEFAULT '',
    p_fraud          DOUBLE PRECISION DEFAULT 0,
    confidence       DOUBLE PRECISION DEFAULT 0,
    graph_risk_score DOUBLE PRECISION DEFAULT 0,
    anomaly_score    DOUBLE PRECISION DEFAULT 0,
    model_action     VARCHAR(32)  DEFAULT 'MANUAL_REVIEW',
    model_version    VARCHAR(64)  DEFAULT '',
    explanation      TEXT         DEFAULT '{}',
    status           VARCHAR(16)  NOT NULL DEFAULT 'OPEN'
                         CHECK (status IN ('OPEN','IN_REVIEW','RESOLVED','ESCALATED')),
    priority         INTEGER      NOT NULL DEFAULT 2 CHECK (priority IN (1,2,3)),
    assigned_to      VARCHAR(36)  REFERENCES app.app_users(id),
    verdict          VARCHAR(32)  CHECK (verdict IN ('CONFIRMED_FRAUD','FALSE_POSITIVE','INCONCLUSIVE')),
    analyst_notes    TEXT         DEFAULT '',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at      TIMESTAMPTZ,
    UNIQUE(txn_id)
);
CREATE INDEX IF NOT EXISTS idx_review_cases_status     ON app.app_review_cases(status);
CREATE INDEX IF NOT EXISTS idx_review_cases_customer   ON app.app_review_cases(customer_id);
CREATE INDEX IF NOT EXISTS idx_review_cases_created    ON app.app_review_cases(created_at);
CREATE INDEX IF NOT EXISTS idx_review_cases_assigned   ON app.app_review_cases(assigned_to);
