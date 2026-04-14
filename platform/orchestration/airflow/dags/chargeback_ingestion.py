"""
dags/chargeback_ingestion.py
Airflow DAG — Chargeback Ingestion Pipeline

Schedule: every 30 minutes
Purpose:
  1. Query PostgreSQL for new chargeback events (since last run)
  2. Join with decisions.records to get model predictions at decision time
  3. Produce ground-truth fraud labels to the fraud-labels Kafka topic
  4. Write processed chargebacks to ClickHouse for analytics
  5. Update customer trust scores based on confirmed fraud

Why this matters:
  Chargebacks are the highest-quality ground truth signal we have.
  A chargeback = the bank confirmed fraud AFTER the fact.
  This closes the feedback loop: model made a decision → customer disputed →
  bank confirmed fraud → label written back → next training round uses it.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

default_args = {
    "owner":            "fraud-ml-team",
    "depends_on_past":  False,
    "retries":          3,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------

def extract_new_chargebacks(**context) -> list:
    """
    Pull chargebacks from PostgreSQL that haven't been processed yet.
    Uses Airflow's execution date for incremental extraction.
    """
    hook      = PostgresHook(postgres_conn_id="fraud_postgres")
    exec_date = context["execution_date"]
    prev_date = exec_date - timedelta(minutes=30)

    sql = """
    SELECT
        cb.chargeback_id,
        cb.txn_id,
        cb.amount,
        cb.currency,
        cb.reason_code,
        cb.reported_at,
        -- Join decision context at time of transaction
        dr.action             AS model_action,
        dr.p_fraud            AS model_p_fraud,
        dr.uncertainty        AS model_uncertainty,
        dr.model_version,
        dr.ab_experiment_id,
        dr.ab_variant,
        -- Original transaction
        te.customer_id,
        te.channel,
        te.merchant_category,
        te.country_code,
        te.amount             AS original_amount
    FROM audit.chargebacks cb
    LEFT JOIN decisions.records dr ON dr.txn_id = cb.txn_id
    LEFT JOIN transactions.events te ON te.external_txn_id = cb.txn_id
    WHERE cb.processed_at >= %(prev_date)s
      AND cb.processed_at <  %(exec_date)s
    ORDER BY cb.reported_at DESC
    LIMIT 10000
    """

    rows = hook.get_records(sql, parameters={
        "prev_date": prev_date,
        "exec_date": exec_date,
    })

    context["task_instance"].xcom_push(key="chargeback_count", value=len(rows))
    print(f"Extracted {len(rows)} new chargebacks")
    return rows


def produce_fraud_labels(rows: list, **context) -> int:
    """
    Publish ground-truth fraud labels to the fraud-labels Kafka topic.
    Each label contains: txn_id, true_label=FRAUD, source=CHARGEBACK,
    model_p_fraud (was the model right?), and metadata.
    """
    import json, os
    from datetime import timezone

    if not rows:
        print("No chargebacks to process")
        return 0

    try:
        from confluent_kafka import Producer
        producer = Producer({
            "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092"),
            "acks": "1",
        })
    except ImportError:
        print("confluent-kafka not installed — skipping Kafka publish")
        return 0

    published = 0
    for row in rows:
        label = {
            "txn_id":             str(row[1]),
            "chargeback_id":      str(row[0]),
            "true_label":         "FRAUD",
            "label_source":       "CHARGEBACK",
            "chargeback_reason":  str(row[4]),
            "reported_at":        str(row[5]),
            "model_action":       str(row[6] or "UNKNOWN"),
            "model_p_fraud":      float(row[7] or 0.0),
            "model_uncertainty":  float(row[8] or 0.0),
            "model_version":      str(row[9] or ""),
            "ab_experiment_id":   str(row[10] or ""),
            "ab_variant":         str(row[11] or ""),
            "customer_id":        str(row[12] or ""),
            "amount":             float(row[14] or 0.0),
            "labeled_at":         datetime.now(timezone.utc).isoformat(),
        }
        producer.produce(
            topic = "fraud-labels",
            key   = label["customer_id"].encode(),
            value = json.dumps(label).encode(),
        )
        published += 1

    producer.flush(30)
    print(f"Published {published} chargeback labels to fraud-labels topic")
    context["task_instance"].xcom_push(key="labels_published", value=published)
    return published


def update_trust_scores(rows: list, **context):
    """
    Decrease trust scores for customers with confirmed fraud chargebacks.
    Approved transactions that resulted in chargebacks → lower trust.
    """
    if not rows:
        return

    hook = PostgresHook(postgres_conn_id="fraud_postgres")

    # Find customers where model approved but fraud happened (false negatives)
    false_negatives = [
        row for row in rows
        if row[6] == "APPROVE"  # model_action
    ]

    if not false_negatives:
        print("No false negatives in this batch")
        return

    for row in false_negatives:
        customer_id = row[12]
        if not customer_id:
            continue
        # Decrease trust score by 0.1, floor at 0.05
        hook.run("""
            UPDATE customers.profiles
            SET trust_score = GREATEST(0.05, trust_score - 0.10),
                updated_at  = NOW()
            WHERE customer_id = %(customer_id)s
        """, parameters={"customer_id": customer_id})

    print(f"Updated trust scores for {len(false_negatives)} false-negative customers")


def write_chargeback_analytics(rows: list, **context):
    """Write chargeback records to ClickHouse for model performance analytics."""
    if not rows:
        return

    import json, os
    try:
        from clickhouse_driver import Client
        client = Client(
            host     = os.getenv("CLICKHOUSE_HOST",     "clickhouse"),
            user     = os.getenv("CLICKHOUSE_USER",     "default"),
            password = os.getenv("CLICKHOUSE_PASSWORD", ""),
            database = os.getenv("CLICKHOUSE_DB",       "fraud_analytics"),
        )
    except ImportError:
        print("clickhouse-driver not installed — skipping analytics write")
        return

    ch_rows = []
    for row in rows:
        try:
            ch_rows.append((
                row[5],                         # reported_at
                str(row[0]),                    # chargeback_id
                str(row[1]),                    # txn_id
                float(row[2] or 0),             # amount
                str(row[3] or "USD"),           # currency
                str(row[4] or ""),              # reason_code
                str(row[6] or "UNKNOWN"),       # action_taken
                float(row[7] or 0.0),           # p_fraud_at_decision
                str(row[9] or ""),              # model_version
            ))
        except Exception:
            pass

    if ch_rows:
        client.execute(
            "INSERT INTO fraud_analytics.chargebacks VALUES",
            ch_rows
        )
    print(f"Wrote {len(ch_rows)} chargeback records to ClickHouse")


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id            = "chargeback_ingestion",
    default_args      = default_args,
    description       = "Ingest chargeback events → fraud-labels topic + analytics",
    schedule_interval = "*/30 * * * *",   # every 30 minutes
    start_date        = datetime(2024, 1, 1),
    catchup           = False,
    tags              = ["fraud-detection", "feedback-loop", "phase7"],
) as dag:

    extract = PythonOperator(
        task_id         = "extract_new_chargebacks",
        python_callable = extract_new_chargebacks,
    )

    produce = PythonOperator(
        task_id         = "produce_fraud_labels",
        python_callable = produce_fraud_labels,
        op_args         = ["{{ task_instance.xcom_pull(task_ids='extract_new_chargebacks') }}"],
    )

    update_trust = PythonOperator(
        task_id         = "update_trust_scores",
        python_callable = update_trust_scores,
        op_args         = ["{{ task_instance.xcom_pull(task_ids='extract_new_chargebacks') }}"],
    )

    write_analytics = PythonOperator(
        task_id         = "write_chargeback_analytics",
        python_callable = write_chargeback_analytics,
        op_args         = ["{{ task_instance.xcom_pull(task_ids='extract_new_chargebacks') }}"],
    )

    extract >> [produce, update_trust, write_analytics]
