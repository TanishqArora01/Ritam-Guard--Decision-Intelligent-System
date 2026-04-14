"""
graph/neo4j_client.py — Neo4j driver pool with timeout and graceful degradation.
If Neo4j is unreachable, all graph queries return 0.0 (non-blocking fallback).
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase, basic_auth
    _NEO4J = True
except ImportError:
    _NEO4J = False
    logger.warning("neo4j driver not installed — graph intelligence disabled")


class Neo4jClient:

    def __init__(self):
        self._driver = None
        self.available = False

    def connect(self):
        from config import config
        if not _NEO4J or not config.neo4j_enabled:
            logger.info("Neo4j disabled — graph scoring will return 0.0")
            return

        try:
            self._driver = GraphDatabase.driver(
                config.neo4j_uri,
                auth=basic_auth(config.neo4j_user, config.neo4j_password),
                max_connection_pool_size=config.neo4j_pool_size,
                connection_timeout=2.0,
            )
            self._driver.verify_connectivity()
            self.available = True
            logger.info("Connected to Neo4j at %s", config.neo4j_uri)
            self._ensure_schema()
        except Exception as e:
            logger.warning("Neo4j connection failed (non-fatal): %s", e)
            self.available = False

    def _ensure_schema(self):
        """Create indexes and constraints for the fraud graph."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Customer) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (i:IPAddress) REQUIRE i.address IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Transaction) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Merchant) REQUIRE m.id IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (t:Transaction) ON (t.timestamp)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Customer) ON (c.account_age_days)",
        ]
        for q in constraints:
            try:
                self.run(q)
            except Exception:
                pass

    def run(self, query: str, params: Dict = None) -> List[Dict]:
        """Execute a Cypher query. Returns list of record dicts."""
        from config import config
        if not self.available or not self._driver:
            return []
        try:
            with self._driver.session(database=config.neo4j_database) as session:
                result = session.run(query, parameters=params or {},
                                     timeout=config.neo4j_timeout_ms / 1000)
                return [dict(r) for r in result]
        except Exception as e:
            logger.debug("Neo4j query failed: %s", e)
            return []

    def upsert_transaction(self, txn: Dict):
        """
        Write a transaction event into the graph.
        Creates/merges: Customer, Device, IPAddress, Transaction, Merchant nodes
        and the relationships between them.
        """
        query = """
        MERGE (c:Customer {id: $customer_id})
          ON CREATE SET c.segment = $segment, c.account_age_days = $account_age_days,
                        c.clv = $clv, c.created_at = datetime()

        MERGE (d:Device {id: $device_id})
        MERGE (ip:IPAddress {address: $ip_address})
        MERGE (m:Merchant {id: $merchant_id})
          ON CREATE SET m.category = $merchant_category

        CREATE (t:Transaction {
            id: $txn_id, amount: $amount, channel: $channel,
            country_code: $country_code, timestamp: datetime()
        })

        MERGE (c)-[:MADE]->(t)
        MERGE (t)-[:AT]->(m)
        MERGE (t)-[:USED]->(d)
        MERGE (t)-[:FROM]->(ip)
        MERGE (d)-[:OWNED_BY]->(c)
        MERGE (ip)-[:USED_BY]->(c)
        """
        self.run(query, txn)

    def close(self):
        if self._driver:
            self._driver.close()
