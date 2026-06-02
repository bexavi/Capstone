# Presentation: Why This Is a Supply Chain Project

## Slide 1 - Title
**Multi-Echelon Automotive Supply Chain Knowledge Graph**  
Using Neo4j and Graph Data Science to analyze dependency, flow, and risk.

**Team:** Bekithemba Nkomo, Masheia Dzimba, Peter Mangoro

---

## Slide 2 - Project Statement
This project models a real automotive production network as a graph, then analyzes:
- product dependencies (BOM structure)
- node-to-node movement (arcs, lead times, capacities)
- inventory and demand over time
- bottlenecks and critical failure points

Why this matters: these are core supply chain decisions, not generic data analysis.

---

## Slide 3 - Real Supply Chain Dataset
Primary dataset: Moetz, Quetschlich, Otto (Mendeley, 2020)

Key supply chain evidence in the data:
- 1 OEM, 4 first-tier suppliers, 2 second-tier suppliers
- 12 network nodes and 11 arcs
- 28,049 products with multi-level BOM dependencies
- lead times, capacities, inventories, initial flows
- customer demand over a 14-day horizon

This is a multi-echelon production network, which is a textbook supply chain structure.

---

## Slide 4 - Why It Is Multi-Echelon
Supply chain echelons are represented through:
- upstream component suppliers
- intermediate production and transformation nodes
- downstream demand nodes and fulfillment paths

The project traces how demand at downstream nodes propagates upstream through BOM and logistics links.

That upstream/downstream dependency tracing is central to supply chain planning.

---

## Slide 5 - Graph Model = Supply Chain Semantics
Core entities:
- `Node` (supplier, plant, inventory/demand point)
- `Product` and `ProductGroup`
- `Period` and `DemandFact`

Core relationships:
- `REQUIRES` (bill-of-material dependency)
- `SHIPS_TO` (movement arc with lead time/capacity context)
- `HOLDS` (inventory position)
- `HAS_DEMAND` -> `FOR_PRODUCT` -> `IN_PERIOD` (time-indexed demand)
- `TRANSFORMS` (input-output production behavior)

These are exactly the relationships supply chain managers reason about.

---

## Slide 6 - Business Problems Addressed
The project answers practical supply chain questions:
- Which products have the deepest dependency chains?
- Which nodes and arcs are most operationally critical?
- Where are bottlenecks and single points of failure?
- How does customer demand pressure move upstream?
- Where do capacity and inventory constraints threaten fulfillment?

This aligns with resilience, continuity, and service-level planning.

---

## Slide 7 - Analytical Framework
Methods used:
- Cypher graph EDA (at least 8 exploratory questions)
- Two deeper analytical Cypher questions
- Graph Data Science (Betweenness Centrality)

Why this is supply chain relevant:
- centrality identifies intermediary choke points
- path/dependency analysis quantifies disruption exposure
- flow + demand + lead-time context supports bottleneck diagnosis

---

## Slide 8 - Operational and Business Impact
**Operational impact**
- improved visibility into constrained arcs and critical nodes
- better understanding of dependency concentration

**Business impact**
- supports mitigation prioritization
- helps target capacity, inventory, and contingency investments

**Analytical impact**
- graph approach captures multi-hop interactions better than flat tables

---

## Slide 9 - Why Neo4j Is Appropriate
Traditional tabular analysis struggles with:
- deep multi-level BOM traversal
- multi-hop node dependencies
- path-based bottleneck and risk propagation

Neo4j enables:
- natural modeling of connected supply structures
- fast path/dependency queries
- GDS algorithms for network criticality

The technology choice is directly aligned with supply chain network analysis.

---

## Slide 10 - Conclusion
This is clearly a supply chain project because it models and analyzes:
- multi-tier supplier relationships
- product-component dependencies
- logistics arcs with constraints
- inventory, flow, and demand over time
- risk and bottleneck concentration in an operational network

**Bottom line:** The project moves from raw automotive operations data to actionable supply chain insight.

---

## Optional Speaker Closing (30 seconds)
"Our project is not just about storing data in a graph. It is about representing how a real multi-echelon automotive supply chain behaves under demand and capacity pressure. By combining Cypher and Graph Data Science, we identify where dependencies are concentrated, where bottlenecks are likely, and where intervention would have the highest operational value."
