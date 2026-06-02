"""Generate Neo4j-first automotive notebook in recommender-template style."""

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB_PATH = ROOT / "AAutomotive_Supply_Chain_Risk_GDS_final.ipynb"

cells = []


def _cid() -> str:
    return uuid.uuid4().hex[:12]


def md(s: str):
    cells.append({"cell_type": "markdown", "id": _cid(), "metadata": {}, "source": [line + "\n" for line in s.split("\n")]})


def code(s: str):
    cells.append({"cell_type": "code", "id": _cid(), "metadata": {}, "outputs": [], "execution_count": None, "source": [line + "\n" for line in s.split("\n")]})


md("# Automotive Supply Chain Risk GDS (Neo4j Desktop)")
md(
    """This notebook follows the same pattern as `B_Nkomo_recommender_project (1).ipynb`:

1. setup and connection
2. data load / graph verification
3. EDA questions as independent blocks
4. deeper analytical questions
5. GDS algorithms

Each EDA question has separate **Code**, **Explanation**, and **Interpretation** cells."""
)
md("---")

code(
    """import os
from pathlib import Path
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from neo4j import GraphDatabase

sns.set_theme(style="whitegrid")
plt.rcParams["figure.figsize"] = (10, 5)

ROOT = Path.cwd()
if not (ROOT / "neo4j").is_dir():
    ROOT = ROOT.parent

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def run_query(query: str, params: dict | None = None) -> pd.DataFrame:
    with driver.session() as session:
        result = session.run(query, params or {})
        return pd.DataFrame([r.data() for r in result])

print("Connected:", run_query("RETURN 1 AS ok").iloc[0]["ok"])"""
)

md("### 1. Data load reminder (Neo4j Desktop)")
md(
    """Run these files in Neo4j Browser once:

- `neo4j/01_constraints.cypher`
- `neo4j/02_load_facilities.cypher`
- `neo4j/03_load_countries.cypher`
- `neo4j/04_load_products.cypher`
- `neo4j/05_load_supplies.cypher`
- `neo4j/06_load_bom.cypher`
- `neo4j/07_load_produces.cypher`
- `neo4j/08_gds_projection.cypher`"""
)

code(
    """# Verification
df_labels = run_query(\"\"\"
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS count
ORDER BY count DESC
\"\"\")
df_rels = run_query(\"\"\"
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(*) AS count
ORDER BY count DESC
\"\"\")
display(df_labels)
display(df_rels)"""
)

md("---")
md("## 2. EDA Questions")

def add_eda_block(title: str, cypher: str, explanation: str, interpretation: str):
    md(f"### {title}")
    code(f'df = run_query("""\\n{cypher}\\n""")\ndisplay(df.head(20))')
    md(f"**Explanation**\n\n{explanation}")
    md(f"**Interpretation / Commentary**\n\n{interpretation}")


add_eda_block(
    "2.1 Total nodes and relationships by label/type",
    """MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS count
ORDER BY count DESC""",
    "Counts graph objects by label to confirm scope and completeness of ingestion.",
    "Use this as a baseline quality check. The `Product` label should dominate volume."
)

add_eda_block(
    "2.2 Product hierarchy distribution by type",
    """MATCH (p:Product)
RETURN p.type AS product_type, count(*) AS count
ORDER BY count DESC""",
    "Profiles product mix (car/system/component/part categories).",
    "A heavy tail of components/parts indicates deep assembly dependency."
)

add_eda_block(
    "2.3 Product hierarchy distribution by level",
    """MATCH (p:Product)
RETURN p.level AS level, count(*) AS count
ORDER BY level""",
    "Checks depth of BOM hierarchy encoded in product levels.",
    "Higher concentrations at deeper levels imply greater upstream risk propagation."
)

add_eda_block(
    "2.4 Top facilities by number of products produced",
    """MATCH (f:Facility)-[:PRODUCES]->(p:Product)
RETURN f.name AS facility, f.tier AS tier, count(p) AS product_count
ORDER BY product_count DESC""",
    "Measures production portfolio concentration across facilities.",
    "High-count facilities are operationally important and candidate risk hotspots."
)

add_eda_block(
    "2.5 Single-sourced products (bottlenecks)",
    """MATCH (p:Product)<-[:PRODUCES]-(f:Facility)
WITH p, count(DISTINCT f) AS supplier_count
WHERE supplier_count = 1
RETURN p.id AS product_id, p.type AS product_type, supplier_count
LIMIT 50""",
    "Detects products with only one producing facility.",
    "Single-source products are direct points of failure under disruption."
)

add_eda_block(
    "2.6 Lead-time statistics by supplier tier",
    """MATCH (f:Facility)-[s:SUPPLIES]->(:Facility)
RETURN f.tier AS tier,
       avg(s.lead_time_days) AS avg_lead_time,
       min(s.lead_time_days) AS min_lead_time,
       max(s.lead_time_days) AS max_lead_time
ORDER BY tier""",
    "Summarizes transport/production delay behavior by echelon.",
    "Longer tier lead times increase cycle-time risk and planning buffer requirements."
)

add_eda_block(
    "2.7 Capacity distribution by supplier tier",
    """MATCH (f:Facility)-[s:SUPPLIES]->(:Facility)
RETURN f.tier AS tier, sum(s.capacity_per_period) AS total_capacity
ORDER BY tier""",
    "Aggregates available throughput to reveal where network capacity sits.",
    "Low capacity with high dependency signals likely bottlenecks."
)

add_eda_block(
    "2.8 Inventory utilization at facilities",
    """MATCH (f:Facility)
WHERE f.inventory_max IS NOT NULL AND f.inventory_max > 0
RETURN f.name AS facility,
       f.tier AS tier,
       f.inventory_current AS current_inv,
       f.inventory_max AS max_inv,
       toFloat(f.inventory_current) / toFloat(f.inventory_max) AS utilization
ORDER BY utilization DESC""",
    "Compares current inventory to available capacity.",
    "Near-1.0 utilization suggests reduced resilience to demand or supply shocks."
)

add_eda_block(
    "2.9 Products produced by tier and type",
    """MATCH (f:Facility)-[:PRODUCES]->(p:Product)
RETURN f.tier AS tier, p.type AS product_type, count(*) AS n
ORDER BY tier, n DESC""",
    "Maps specialization across echelons.",
    "Clear specialization supports modular sourcing strategy but can increase coupling."
)

add_eda_block(
    "2.10 Highest-risk supply arcs by proxy scores",
    """MATCH (a:Facility)-[s:SUPPLIES]->(b:Facility)
RETURN a.name AS from_facility,
       b.name AS to_facility,
       s.delay_probability_proxy AS delay_proxy,
       s.disruption_likelihood_proxy AS disruption_proxy,
       s.delay_probability_proxy * s.disruption_likelihood_proxy AS risk_score
ORDER BY risk_score DESC
LIMIT 30""",
    "Ranks arcs by a composite risk proxy to prioritize monitoring.",
    "Top arcs should be first candidates for contingency planning and dual-routing."
)

md("---")
md("## 3. Deeper Analytical Questions")

md("### 3.1 Critical path style exposure (multi-hop supply)")
code(
    """df = run_query(\"\"\"
MATCH path = (t2:Tier2Supplier)-[:SUPPLIES*1..4]->(o:OEM)
WITH path,
     reduce(total = 0.0, r IN relationships(path) | total + coalesce(r.lead_time_days, 0.0)) AS total_lead_time
RETURN [n IN nodes(path) | coalesce(n.name, n.id)] AS path_nodes, total_lead_time
ORDER BY total_lead_time DESC
LIMIT 25
\"\"\")
display(df)"""
)
md("**Explanation**\n\nEvaluates cumulative lead time across multi-tier routes.")
md("**Interpretation / Commentary**\n\nLong paths with high cumulative lead time are candidates for safety stock, route redesign, or supplier diversification.")

md("### 3.2 Cars with high single-point-of-failure exposure")
code(
    """df = run_query(\"\"\"
MATCH (car:Product {type:'car'})-[:CONTAINS*1..6]->(comp:Product)
MATCH (comp)<-[:PRODUCES]-(f:Facility)
WITH car, comp, count(DISTINCT f) AS supplier_count
WHERE supplier_count = 1
RETURN car.id AS car_id, count(DISTINCT comp) AS vulnerable_components
ORDER BY vulnerable_components DESC
LIMIT 25
\"\"\")
display(df)"""
)
md("**Explanation**\n\nCounts downstream components in each car that are single-sourced.")
md("**Interpretation / Commentary**\n\nCars with larger vulnerable component counts have higher stoppage risk under localized disruptions.")

md("---")
md("## 4. GDS Workflow (Neo4j Desktop)")

md("### 4.1 PageRank: critical facilities/products")
code(
    """df = run_query(\"\"\"
CALL gds.pageRank.stream('automotive-network')
YIELD nodeId, score
RETURN coalesce(gds.util.asNode(nodeId).name, gds.util.asNode(nodeId).id) AS node,
       labels(gds.util.asNode(nodeId)) AS labels,
       score
ORDER BY score DESC
LIMIT 20
\"\"\")
display(df)"""
)
md("**Explanation**\n\nPageRank scores nodes by importance based on recursive dependency.")
md("**Interpretation / Commentary**\n\nTop-ranked suppliers and products are strategic critical nodes; they should receive stronger risk controls.")

md("### 4.2 Louvain: dependency communities")
code(
    """df = run_query(\"\"\"
CALL gds.louvain.stream('automotive-network')
YIELD nodeId, communityId
RETURN communityId,
       labels(gds.util.asNode(nodeId))[0] AS node_type,
       count(*) AS members
ORDER BY members DESC
\"\"\")
display(df.head(30))"""
)
md("**Explanation**\n\nLouvain partitions nodes into tightly connected communities.")
md("**Interpretation / Commentary**\n\nCommunity-level concentration can guide diversification strategy across independent clusters.")

md("---")
md("## 5. Closing")
md(
    """This notebook now matches the recommender-project style:

- independent question cells
- explicit explanation cells
- explicit interpretation/commentary cells
- Neo4j Desktop first workflow for Cypher and GDS."""
)

nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    "cells": cells,
}

NB_PATH.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("Wrote", NB_PATH)