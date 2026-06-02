Here is a concise comparison of **how each notebook designs nodes and relationships** (what exists in the graph vs what is only suggested).

---

## 1. `Supply_Chain_Capstone.ipynb` — domain-first “digital twin”

**Nodes (as documented and used in Cypher)**

| Label(s) | Role |
|-----------|------|
| **`Facility`** | Base label for all 12 sites; queries also use **`Tier2Supplier`**, **`Tier1Supplier`**, **`OEM`** as more specific labels (subtype pattern). |
| **`Product`** | Every SKU (~28k); distinguished by property **`group`** (`car`, `engine`, `gear`, …). |
| **`Customer`** | A single aggregated market node for demand. |

**Relationships**

| Type | Meaning (design intent) |
|------|---------------------------|
| **`SUPPLIES`** | Logistics between facilities (`Facility` → `Facility`); carries things like **lead time** (queries use `lead_time_days`). |
| **`CONTAINS`** | BOM / assembly: **`(parent Product)-[:CONTAINS]->(child Product)`** — same direction as “car to component” in the Cypher. |
| **`PRODUCES`** | **`(Facility)-[:PRODUCES]->(Product)`** — which site builds or holds which SKU (from `nodes_inflow` style semantics). |
| **`DEMANDS`** | **`(Customer)-[:DEMANDS]->(Product)`** — demand on finished cars (with **quantity**, **period** on the relationship in the narrative). |
| **`STORES`** | **`(Facility)-[:STORES]->(Product)`** — opening inventory / stock limits (initial inventories). |

**GDS projection (explicit in notebook)**  
One in-memory graph over **`['Facility', 'Product', 'Customer']`** with **`SUPPLIES`**, **`PRODUCES`**, **`CONTAINS`**, **`DEMANDS`** all **`NATURAL`** orientation — so algorithms see facilities, products, customer, and four relationship families at once (inventory `STORES` is *not* in that projection snippet).

**Design idea:** Speak like the business (tiers, BOM, customer demand). Few node kinds, many products, **direct** demand and BOM edges.

---

## 2. `AutomotiveSupplyChain_Work.ipynb` — workbook-faithful + normalization

**Nodes**

| Label | Key property | Role |
|-------|----------------|------|
| **`Node`** | `nodeId` | The 12 supply-chain locations from `nodes.csv` (generic name; one label for all sites). |
| **`Product`** | `productId` (string) | SKUs from `products.csv` (+ BOM-driven merges for children). |
| **`ProductGroup`** | `groupName` | `car`, `engine`, etc. |
| **`Period`** | `periodId` | Discrete planning periods from demand / capacity / flow tables. |
| **`DemandFact`** | `demandKey` (composite) | One node per **(node, product, period)** demand row — demand is **not** a single edge from a customer. |

**Relationships**

| Type | Pattern | Role |
|------|---------|------|
| **`BELONGS_TO`** | `(:Product)-[:BELONGS_TO]->(:ProductGroup)` | Classification (from `products.group_g`). |
| **`REQUIRES`** | `(:Product)-[:REQUIRES {quantity}]->(:Product)` | BOM from `BOM.csv` (**mother → child**, “assembly requires input”). |
| **`SHIPS_TO`** | `(:Node)-[:SHIPS_TO {leadTime, productGroup}]->(:Node)` | Static arcs from `arcs.csv`. |
| **`HANDLES`** | `(:Node)-[:HANDLES]->(:Product)` | What a node can receive / work with (`nodes_inflow`). |
| **`HAS_DEMAND`** / **`FOR_PRODUCT`** / **`IN_PERIOD`** | `Node → DemandFact → Product` and `DemandFact → Period` | Normalized demand from `demands.csv`. |
| **`HOLDS`** | `(:Node)-[:HOLDS {…, periodId}]->(:Product)` | Initial inventory (`initial_inventories`). |
| **`TRANSFORMS`** | `(:Node)-[:TRANSFORMS {inputGroup, …}]->(:ProductGroup)` | Transformation / assembly recipe (`operations`). |
| **`CAPACITY_AT`** | `(:Node)-[:CAPACITY_AT {periodId}]->(:Node)` | Per-period arc capacity. |
| **`PLANNED_FLOW_TO`** | Arc + **period** + **productId** | From `max_flow_product_per_arc`. |
| **`GROUP_FLOW_TO`** | Arc + **period** + **productGroup** | From `max_flow_group_per_arc`. |
| **`INITIAL_FLOW_TO`** | Arc + **period** + **productId** | From `initial_flows`. |

**Design idea:** Mirror **tables and time** in the graph: parallel relationship **types** for static topology vs **period-scoped** capacity and flows; demand as **facts** avoids overloading one `DEMANDS` edge with a huge property set and matches wide denormalized demand rows.

---

## 3. `Automotive_Supply_Chain_Analysis.ipynb` — no single implemented Neo4j schema

This notebook **does not define one consistent loaded graph**. It:

- Builds **pandas** frames and a **NetworkX** digraph from **`arcs`** (`from_node` → `to_node`) for logistics EDA and betweenness in Python.
- In **markdown sample Cypher**, it **mixes naming conventions**:
  - Logistics: **`FLOWS_TO`** and nodes implied as **`SupplyNode`** for GDS (`gds.graph.project('supply_net', 'SupplyNode', 'FLOWS_TO')`).
  - BOM: **`(:Product)-[:REQUIRES*]->(:Product)`** with property **`group: 'car'`** and **`p.id`** (while the Python side uses `product_id` from renamed columns).

So for “node and relationship design,” this file is best read as: **“here are queries you could run if you named things this way”** — not as a committed ontology. It also mentions **`Node` / `SHIPS_TO`** in prose for GDS while the sample uses **`SupplyNode` / `FLOWS_TO`**, which are two different naming stories.

---

## Side-by-side: same real-world ideas, different graph shapes

| Concept | Capstone | Work | Analysis (intent only) |
|---------|----------|------|-------------------------|
| Facilities | **`Facility`** + tier labels | **`Node`** only | Implicit node ids in NX / `SupplyNode` in one Cypher snippet |
| BOM | **`CONTAINS`** (parent → child) | **`REQUIRES`** (parent → child) | **`REQUIRES`** in sample Cypher |
| Logistics | **`SUPPLIES`** | **`SHIPS_TO`** | **`FLOWS_TO`** (sample) / arcs in NX |
| Demand | **`Customer`–`DEMANDS`–>`Product`** | **`Node`–`HAS_DEMAND`–>`DemandFact`–`FOR_PRODUCT`–>`Product`** + **`IN_PERIOD`** | Not modeled in sample Cypher |
| Time / capacity / planned flows | Mostly on rel props in prose; not as rich as Work’s split rel types | **Separate rel types** keyed by `periodId` (and product/group) | Python merges for “arc stress” |
| Inventory | **`STORES`** | **`HOLDS`** (+ period on rel) | Python on `initial_inventories` |

---

## Direction and semantics (worth one sentence when you write this up)

- **Capstone `CONTAINS`** and **Work `REQUIRES`** are both used in the **parent → child** direction in the Cypher you have (`car`/`mother` at the tail of the relationship pointing **to** the component). Same DAG direction, different rel **name** and **surrounding** node types (`Facility` vs `Node`, `Customer` vs `DemandFact`).

If you want, next step is to pick **one** rel name pair for your write-up (`CONTAINS` vs `REQUIRES`, `SUPPLIES` vs `SHIPS_TO`) and stick to it in every diagram and query so graders never have to mentally translate between notebooks.

Here are **graph-design improvements** (nodes and relationships only) you can apply to `AutomotiveSupplyChain_Work.ipynb`, building on what you already have (`Node`, `Product`, `ProductGroup`, `Period`, `DemandFact`, `REQUIRES`, `SHIPS_TO`, time-sliced flow/capacity rels, etc.).

---

### 1. Replace or augment generic `:Node` with domain semantics

**Issue:** `Node` is accurate as a merge key but weak for queries, GDS narratives, and grading (“what is this vertex?”).

**Improvements:**

- Add **secondary labels** from `nodeId` patterns (or a small mapping table in ingest): e.g. `:OEM` for `zp7`/`zp8`, `:SupplierSite` for others, and optionally `:Production` vs `:Inventory` from `*_prod` vs `*_inv` suffixes.
- Optionally add **`kind`**, **`echelon`**, or **`displayName`** properties so Cypher does not rely on string parsing.

You keep **`MERGE (n:Node {nodeId})`** for stability, then **`SET n:OEM`** (etc.). Same relationships; richer patterns like `(t2:Tier2Supplier)-[:SHIPS_TO*..]->(oem:OEM)` become possible without changing the dataset.

---

### 2. Make facility–product roles explicit (`HANDLES` vs `PRODUCES`)

**Issue:** `HANDLES` reflects `nodes_inflow` but the name is vague compared to “this site **produces** or **sources** this SKU.”

**Improvements:**

- Either **rename** in docs/Cypher to something closer to the domain (**`SOURCES`**, **`PRODUCES`**, **`CAN_RECEIVE`**) *or* keep `HANDLES` but add a **`role`** or **`inflowType`** property if the model ever distinguishes make vs move.
- If you mirror the Capstone story for one course narrative, a single **`(:Site)-[:PRODUCES]->(:Product)`** (or `MAKES`) for inflow rows is easier to explain than a generic “handles.”

---

### 3. Clarify BOM semantics on the relationship (and direction in prose)

**Issue:** `REQUIRES` is good for optimization language; some readers expect `CONTAINS` or `HAS_COMPONENT`.

**Improvements:**

- Keep **`(:Product)-[:REQUIRES {quantity}]->(:Product)`** if it matches your math, but add optional properties: **`unit`**, **`bomLevel`** (if derivable), or **`source`** = `'BOM'` for provenance.
- If any BOM rows imply **alternates** or **phantom** SKUs later, reserve **`relationshipType`** or **`edgeId`** for disambiguation; for now, **`quantity`** (and default 1) is enough.

Document once: **“mother → child is modeled as mother `REQUIRES` child.”**

---

### 4. Demand modeling: simplify or enrich `DemandFact`

You currently have: **`HAS_DEMAND` → `DemandFact` → `FOR_PRODUCT` / `IN_PERIOD`**.

**Possible improvements:**

- **Simpler alternative (optional):** **`(:Node)-[:DEMANDS {periodId, quantity}]->(:Product)`** when you do not need a reified fact node. Fewer hops for EDA and GDS; fewer joins in Cypher.
- **Keep facts but tighten the model:**  
  - Ensure **`DemandFact`** represents exactly one logical row (you already use **`demandKey`**).  
  - Consider **`(:DemandFact)-[:AT_NODE]->(:Node)`** instead of only `HAS_DEMAND` direction, if you want symmetric “fact in the middle” queries — purely ergonomic.  
  - Add **`quantity`** (and **`currency`** / **`scenario`** if ever needed) as properties on the fact or on `FOR_PRODUCT`.

Pick **one** story for the rubric: either “normalized fact hub” or “direct demand edges,” and use it consistently in all EDA queries.

---

### 5. Logistics: relate `SHIPS_TO` to capacity and flows explicitly

**Issue:** You have **`SHIPS_TO`** (static) plus **`CAPACITY_AT`**, **`PLANNED_FLOW_TO`**, etc. They share endpoints but are **not** explicitly linked in the graph model (only implicitly by `(from,to[,period])`).

**Improvements:**

- **Option A — Super-node or hyper-edge (heavy):** `(:LogisticsArc {arcKey: from+'|'+to})` with **`SHIPS_TO`** replaced by **`(:Node)-[:OUTBOUND_ARC]->(:LogisticsArc)<-[:INBOUND_ARC]-(:Node)`** and all period rels attached to **`LogisticsArc`**. Great for “one place” per arc; more nodes and ingest work.
- **Option B — Lighter:** Keep parallel rels but add **`arcKey`** or **`fromNodeId`/`toNodeId`** duplicated on **`CAPACITY_AT`** / flow rels and a **uniqueness constraint** or composite logic so analytics can **`MATCH (a)-[:SHIPS_TO]->(b), (a)-[c:CAPACITY_AT {periodId}]->(b)`** without ambiguity.
- Put **`leadTime`** and **`productGroup`** only on **`SHIPS_TO`**; avoid duplicating lead time on every period rel unless the source data does.

---

### 6. Time modeling: align `Period` usage everywhere

**Issue:** Some state lives on **`(:Period)`** nodes; **`periodId`** also appears on relationships (`HOLDS`, capacity/flows). That is fine, but easy to query inconsistently.

**Improvements:**

- Rule: **“Anything time-varying references `periodId` as int; optional `[:IN_PERIOD]` only when a node represents a row that spans entities.”**  
- For **`HOLDS`**, decide if inventory is **`(Node)-[:HOLDS {periodId}]->(Product)`** only, or also **`->(Product)-[:IN_PERIOD]->(Period)`** — usually **one** is enough.

---

### 7. `TRANSFORMS`: connect to products, not only groups

**Issue:** **`(:Node)-[:TRANSFORMS]->(:ProductGroup)`** matches `operations` but misses “this line outputs **this** product family’s SKUs” at product granularity unless you traverse **`BELONGS_TO`**.

**Improvements:**

- If the workbook allows, add derived edges **`(:Node)-[:OUTPUTS_GROUP {…}]->(:ProductGroup)`** (rename from `TRANSFORMS` if clearer) **and** optional **`[:USES_INPUT {group: gx}]`** for symmetry.
- Or add **`(:Node)-[:TRANSFORMS]->(:Product)`** for representative BOM parents in that group (only if you can define a safe rule — otherwise keep group-level and document the hop through `BELONGS_TO`).

---

### 8. Customer / market boundary

**Issue:** Demand is anchored on **`Node`** (e.g. OEM). There is no **`Customer`**, which is fine for this dataset, but risk story “customer → car” is less literal.

**Improvements:**

- Add a single **`(:Market)` or `(:Customer)`** node and **`(:Customer)-[:ORDERS]->(:DemandFact)`** or **`->(:Product)`** if you want Capstone-style language with minimal extra structure.
- If you keep facts only under OEM nodes, rename mentally to **“demand at node”** and state that **“Customer is implicit in the dataset.”**

---

### 9. Product catalog completeness

**Issue:** BOM introduces children that may not appear in **`products.csv`**; you already `MERGE` endpoints — good. For analytics, you may want to tag **`(:Product {catalogSource: 'BOM_only'})`** vs **`'products_sheet'`** so EDA can separate “catalog SKUs” from “BOM-only leaves.”

---

### 10. Relationship types for GDS (design ahead)

**Issue:** Many relationship types make **one** GDS projection harder to justify.

**Improvements:**

- Define **two analytical layers** in the docs (not necessarily two DBs):  
  - **Topology graph:** `Node` + `SHIPS_TO` (and maybe `PRODUCES`/`HANDLES` only).  
  - **BOM graph:** `Product` + `REQUIRES`.  
  - **Integrated risk graph:** curated subset (e.g. expand `REQUIRES` to facilities via `HANDLES` in a **virtual** projection using `gds.graph.project` with multiple rels, or use **Cypher projection**).

Stating this in the notebook prevents “kitchen sink” projections that mix `REQUIRES` with `CAPACITY_AT` without a clear interpretation.

---

### 11. Small hygiene: synonyms and direction

- Avoid having both **`FLOWS_TO`** (other notebooks) and **`SHIPS_TO`** (this one) in prose; pick **`SHIPS_TO`** and document it as **directed logistics**.
- If **`REQUIRES`** ever conflicts with mental “requirements planning,” an alias relationship type is **not** worth it in Neo4j — better a one-line glossary in markdown.

---

**Summary:** The strongest structural upgrades for *this* notebook are **(1)** secondary facility labels / properties on `Node`, **(2)** clearer naming or properties for facility–product links, **(3)** an explicit rule for how **`SHIPS_TO`** relates to **period** rels (lightweight `arcKey` vs heavy `LogisticsArc`), **(4)** simplifying or documenting **`DemandFact`**, and **(5)** layering **BOM vs logistics vs temporal** for GDS and capstone narrative. None of that requires changing the underlying CSVs — mostly ingest `SET`/`MERGE` patterns and documentation.

I can map each item to a specific Phase 3.x cell in the notebook if you switch to Agent mode and want it implemented.