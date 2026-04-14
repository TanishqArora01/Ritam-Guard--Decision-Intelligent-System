#!/bin/sh
# =============================================================================
# MinIO — Bucket Initialization Script
# Creates all required buckets for Feast offline store + MLflow artifacts
# =============================================================================

set -e

MINIO_ENDPOINT="http://minio:9000"
MINIO_USER="${MINIO_ROOT_USER:-fraud_minio}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:-fraud_minio_2024}"

echo "Configuring MinIO client..."
mc alias set fraud_minio "$MINIO_ENDPOINT" "$MINIO_USER" "$MINIO_PASS"

echo "Creating buckets..."

create_bucket() {
  local name=$1
  mc mb "fraud_minio/$name" 2>/dev/null && echo "  Created: $name" || echo "  Exists:  $name"
}

# Feast offline feature store (historical features, point-in-time joins)
create_bucket "feast-offline"

# MLflow experiment artifacts (models, plots, metrics)
create_bucket "mlflow-artifacts"

# Raw data lake
create_bucket "fraud-data"

# Feature snapshots for monitoring / drift detection
create_bucket "feature-snapshots"

# Flink checkpoints and savepoints
create_bucket "flink-checkpoints"

# Training datasets (Parquet files)
create_bucket "training-datasets"

echo ""
echo "Setting bucket policies..."
mc anonymous set download "fraud_minio/feast-offline"    2>/dev/null || true
mc anonymous set download "fraud_minio/mlflow-artifacts" 2>/dev/null || true

echo ""
echo "MinIO initialization complete."
mc ls fraud_minio
