// =============================================================================
// Neo4j Graph Initialization — Fraud Detection System
// Run via: docker exec fraud_neo4j cypher-shell -u neo4j -p fraud_neo4j_2024 -f /init_graph.cypher
// Or paste into Neo4j Browser at http://localhost:7474
// =============================================================================

// ---------------------------------------------------------------------------
// 1. Schema constraints + indexes (idempotent)
// ---------------------------------------------------------------------------

CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE;

CREATE CONSTRAINT device_id_unique IF NOT EXISTS
FOR (d:Device) REQUIRE d.device_id IS UNIQUE;

CREATE CONSTRAINT ip_unique IF NOT EXISTS
FOR (i:IPAddress) REQUIRE i.address IS UNIQUE;

CREATE CONSTRAINT merchant_unique IF NOT EXISTS
FOR (m:Merchant) REQUIRE m.merchant_id IS UNIQUE;

CREATE CONSTRAINT txn_unique IF NOT EXISTS
FOR (t:Transaction) REQUIRE t.txn_id IS UNIQUE;

CREATE INDEX customer_segment IF NOT EXISTS
FOR (c:Customer) ON (c.segment);

CREATE INDEX customer_trust IF NOT EXISTS
FOR (c:Customer) ON (c.trust_score);

CREATE INDEX txn_ts IF NOT EXISTS
FOR (t:Transaction) ON (t.ts);

CREATE INDEX txn_amount IF NOT EXISTS
FOR (t:Transaction) ON (t.amount);

// ---------------------------------------------------------------------------
// 2. Seed data — legitimate customers
// ---------------------------------------------------------------------------

MERGE (c1:Customer {customer_id: 'seed-premium-001'})
  ON CREATE SET c1.segment = 'premium', c1.clv = 85000,
               c1.trust_score = 0.92, c1.account_age_days = 1825,
               c1.created_at = datetime();

MERGE (c2:Customer {customer_id: 'seed-standard-001'})
  ON CREATE SET c2.segment = 'standard', c2.clv = 12000,
               c2.trust_score = 0.68, c2.account_age_days = 540,
               c2.created_at = datetime();

MERGE (c3:Customer {customer_id: 'seed-new-001'})
  ON CREATE SET c3.segment = 'new', c3.clv = 800,
               c3.trust_score = 0.42, c3.account_age_days = 14,
               c3.created_at = datetime();

// ---------------------------------------------------------------------------
// 3. Seed data — fraud ring (3 customers sharing 1 device + 1 IP)
// ---------------------------------------------------------------------------

MERGE (mule1:Customer {customer_id: 'seed-mule-001'})
  ON CREATE SET mule1.segment = 'risky', mule1.clv = 500,
               mule1.trust_score = 0.12, mule1.account_age_days = 7;

MERGE (mule2:Customer {customer_id: 'seed-mule-002'})
  ON CREATE SET mule2.segment = 'risky', mule2.clv = 450,
               mule2.trust_score = 0.10, mule2.account_age_days = 9;

MERGE (mule3:Customer {customer_id: 'seed-mule-003'})
  ON CREATE SET mule3.segment = 'risky', mule3.clv = 600,
               mule3.trust_score = 0.15, mule3.account_age_days = 5;

// Shared infrastructure
MERGE (shared_device:Device {device_id: 'DEV-FRAUD-RING-SHARED'})
  ON CREATE SET shared_device.fingerprint = 'ring-device-001';

MERGE (shared_ip:IPAddress {address: '185.220.101.99'})
  ON CREATE SET shared_ip.country = 'NG', shared_ip.asn = 'AS209650';

// Connect all 3 mules to the same device and IP
MERGE (mule1)-[:USED {count: 8,  first_seen: datetime()}]->(shared_device);
MERGE (mule2)-[:USED {count: 5,  first_seen: datetime()}]->(shared_device);
MERGE (mule3)-[:USED {count: 12, first_seen: datetime()}]->(shared_device);
MERGE (mule1)-[:FROM_IP {count: 8}]->(shared_ip);
MERGE (mule2)-[:FROM_IP {count: 5}]->(shared_ip);
MERGE (mule3)-[:FROM_IP {count: 12}]->(shared_ip);

// ---------------------------------------------------------------------------
// 4. Seed data — sample transactions for graph queries
// ---------------------------------------------------------------------------

MERGE (t1:Transaction {txn_id: 'seed-txn-001'})
  ON CREATE SET t1.amount = 199.99, t1.currency = 'USD',
               t1.channel = 'WEB', t1.ts = datetime(),
               t1.country_code = 'NG', t1.is_fraud = true;

MERGE (t2:Transaction {txn_id: 'seed-txn-002'})
  ON CREATE SET t2.amount = 249.50, t2.currency = 'USD',
               t2.channel = 'MOBILE', t2.ts = datetime(),
               t2.country_code = 'NG', t2.is_fraud = true;

MERGE (merchant_risk:Merchant {merchant_id: 'MER-GIFT-CARD-001'})
  ON CREATE SET merchant_risk.category = 'gift_cards',
               merchant_risk.risk_tier = 'high';

// Wire up sample transactions
MERGE (mule1)-[:SENT]->(t1);
MERGE (mule2)-[:SENT]->(t2);
MERGE (t1)-[:AT]->(merchant_risk);
MERGE (t2)-[:AT]->(merchant_risk);
MERGE (t1)-[:VIA]->(shared_device);
MERGE (t2)-[:VIA]->(shared_device);
MERGE (t1)-[:FROM]->(shared_ip);
MERGE (t2)-[:FROM]->(shared_ip);

// ---------------------------------------------------------------------------
// 5. Verification queries (uncomment to test)
// ---------------------------------------------------------------------------

// Count all nodes by label
// MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC;

// Find fraud ring (customers sharing a device)
// MATCH (c1:Customer)-[:USED]->(d:Device)<-[:USED]-(c2:Customer)
// WHERE c1.customer_id < c2.customer_id
// RETURN c1.customer_id, c2.customer_id, d.device_id;

// Trust score distribution
// MATCH (c:Customer) RETURN c.segment, avg(c.trust_score) AS avg_trust ORDER BY avg_trust;
