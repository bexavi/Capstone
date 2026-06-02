# AUTOMOTIVE MULTI-ECHELON SUPPLY CHAIN PROJECT
## Complete 3-Day Implementation Plan

**Dataset:** Mendeley Multi-Echelon Automotive Supply Chain  
**Source:** https://data.mendeley.com/datasets/pr3sdy5vp3/1  
**Domain:** Automotive manufacturing (OEM + Tier 1/2 suppliers)  
**Timeline:** 3 days  
**Platform:** Neo4j Desktop + Jupyter Notebook

---

## 🎯 **PROBLEM STATEMENT**

### **The Challenge of Multi-Tier Automotive Supply Chains**

Modern automotive manufacturing operates through **multi-echelon supply networks** where:
- **OEMs** (Original Equipment Manufacturers) assemble final vehicles
- **Tier-1 suppliers** provide major systems (engines, transmissions, electronics)
- **Tier-2 suppliers** provide components (gears, sensors, raw materials)
- Products have **complex Bill of Materials** (a car contains ~30,000 parts)

This creates **three critical operational challenges**:

#### **1. Hidden Multi-Tier Dependencies**
When a Tier-2 supplier experiences disruption (e.g., gear manufacturer shutdown), it's difficult to quickly determine:
- Which Tier-1 systems are affected (engine, transmission)?
- Which final vehicles cannot be assembled?
- What customer orders will be delayed?
- Which alternative suppliers can provide substitute parts?

Traditional ERP systems track direct supplier relationships (OEM ↔ Tier-1) but struggle to answer: *"If this Tier-2 supplier fails, which car models are at risk?"*

#### **2. Bill of Materials Explosion**
Automotive products are **nested assemblies**:
```
Car → Engine → Cylinder Block → Pistons → Piston Rings
```

Understanding **full component traceability** requires traversing multiple levels:
- Which raw materials ultimately go into which finished cars?
- If we recall defective piston rings, which cars are affected?
- What's the total lead time from raw material to finished vehicle?

Relational databases require multiple joins; graph databases make this natural.

#### **3. Capacity Cascade Analysis**
Each supplier has **production capacity limits** and **inventory constraints**. When demand surges:
- Can Tier-2 suppliers produce enough components?
- Will Tier-1 suppliers have capacity to assemble systems?
- Where are the bottlenecks in the multi-tier network?
- How should we allocate scarce capacity across car models?

**Current Limitation:** Spreadsheets calculate single-tier capacity; multi-tier cascade requires graph traversal.

### **Why Graph Databases?**

Automotive supply chains are **inherently graphs**:
- **Nodes:** OEM, Tier-1 suppliers, Tier-2 suppliers, Products (cars, engines, gears)
- **Edges:** SUPPLIES relationships, CONTAINS (Bill of Materials), PRODUCES
- **Properties:** Lead time, capacity, inventory, demand

**Graph Analytics Enable:**
1. **Multi-hop traversal:** "Show me all Tier-2 suppliers for this car model"
2. **Impact analysis:** "If Supplier X fails, which products are affected?"
3. **Critical path analysis:** "What's the longest lead time path?"
4. **Centrality ranking:** "Which suppliers are most critical to overall production?"
5. **Community detection:** "Which suppliers form natural sourcing clusters?"

### **Research Objectives**

**Objective 1: Map Multi-Tier Supply Network Structure**
- Model OEM, Tier-1, Tier-2 suppliers as graph nodes
- Represent Bill of Materials as CONTAINS relationships
- Capture supply relationships with lead times and capacities
- Visualize end-to-end product assembly paths

**Objective 2: Identify Critical Suppliers**
- Apply PageRank to rank supplier importance across all tiers
- Compare simple degree centrality vs. weighted PageRank
- Identify single-source bottlenecks (products with one supplier)
- Prioritize supplier relationship management based on criticality

**Objective 3: Analyze Product Dependencies**
- Trace Bill of Materials from finished cars to raw components
- Identify products with complex (deep) vs. simple (shallow) BOM
- Calculate total lead time across multi-tier supply paths
- Detect products vulnerable to Tier-2 supply disruptions

**Objective 4: Discover Supply Clusters**
- Apply Louvain community detection to segment supplier network
- Characterize communities (geographic, product category, tier)
- Enable zone-based risk management (diversify across communities)
- Support scenario planning (community-level disruptions)

---

## 📊 **DATASET STRUCTURE**

### **What the Files Contain**

**Based on Mendeley description:**

1. **Nodes (12 total):**
   - 1 OEM (car assembly plant)
   - 4 Tier-1 suppliers (engine, transmission, electronics, chassis)
   - 2 Tier-2 suppliers (components, raw materials)
   - Each node has: ID, assigned products, initial inventory, max inventory

2. **Arcs (11 total):**
   - Supply relationships between nodes
   - Properties: lead time, transport capacity per period, initial flow

3. **Products (28,049 total):**
   - Hierarchical structure: Cars → Systems → Components → Parts
   - Example: Car Model A → Engine Type X → Gear Assembly Y → Gear Z

4. **Bill of Materials:**
   - Which components are needed for each assembly
   - Quantity required per unit

5. **Customer Demand:**
   - 14 days of demand data
   - Demand per car model per day

### **Expected Graph Model**

**Nodes:**
- `OEM` (1 node)
- `Tier1Supplier` (4 nodes)
- `Tier2Supplier` (2 nodes)
- `Product` (28,049 nodes - cars, systems, components, parts)

**Relationships:**
- `SUPPLIES`: Supplier → OEM/Supplier (supply flow with lead time, capacity)
- `PRODUCES`: Supplier → Product (which supplier makes which product)
- `CONTAINS`: Product → Product (Bill of Materials - car contains engine, engine contains gears)
- `DEMANDS`: Customer → Product (demand for finished cars)

**Key Properties:**
- Nodes: inventory_current, inventory_max, tier_level, location
- SUPPLIES: lead_time_days, capacity_per_period, transport_cost
- CONTAINS: quantity_required (how many components per assembly)
- PRODUCES: production_capacity

---

## 🗓️ **3-DAY IMPLEMENTATION PLAN**

### **DAY 1: SETUP & DATA MODELING (8-10 hours)**

#### **Morning Session (4-5 hours)**

**Task 1.1: Download and Inspect Dataset (1 hour)**
1. Download all files from Mendeley: https://data.mendeley.com/datasets/pr3sdy5vp3/1
2. Extract to working directory: `automotive_supply_chain/data/`
3. Inspect file formats:
   ```bash
   ls -lh data/
   # Likely files: nodes.csv, arcs.csv, products.csv, bom.csv, demand.csv
   ```
4. Quick preview:
   ```bash
   head -20 nodes.csv
   head -20 arcs.csv
   head -20 products.csv
   ```

**Task 1.2: Set Up Neo4j Desktop (1 hour)**
1. Create new project: "Automotive_Supply_Chain"
2. Create database: "automotive-network"
   - Version: 5.x
   - Memory: 2GB heap, 1GB page cache
3. Install GDS plugin
4. Start database

**Task 1.3: Design Graph Model (1 hour)**

Create notebook with graph model diagram:

```markdown
## Graph Schema

### Nodes
- `OEM` - Original Equipment Manufacturer (1 node)
  - Properties: id, name, location, inventory_capacity
- `Tier1Supplier` - Major system suppliers (4 nodes)
  - Properties: id, name, location, tier, products_produced
- `Tier2Supplier` - Component suppliers (2 nodes)
  - Properties: id, name, location, tier, products_produced
- `Product` - All products from cars to components (28,049 nodes)
  - Properties: id, name, type (car/system/component/part), level

### Relationships
- `SUPPLIES` - Supplier → Manufacturer (11 relationships)
  - Properties: lead_time_days, capacity_units, transport_cost
- `PRODUCES` - Supplier → Product
  - Properties: production_capacity_per_day
- `CONTAINS` - Product → Product (Bill of Materials)
  - Properties: quantity_required
- `DEMANDS` - Customer demand for products
  - Properties: demand_quantity, demand_date
```

**Task 1.4: Load Data into Neo4j (1.5-2 hours)**

**Step 1: Create Constraints**
```cypher
CREATE CONSTRAINT oem_id IF NOT EXISTS FOR (o:OEM) REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT tier1_id IF NOT EXISTS FOR (t:Tier1Supplier) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT tier2_id IF NOT EXISTS FOR (t:Tier2Supplier) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE;
```

**Step 2: Load Nodes**
```cypher
// Load OEM
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.tier = '0' OR row.type = 'OEM'
CREATE (o:OEM {
  id: row.node_id,
  name: row.node_name,
  location: row.location,
  inventory_current: toFloat(row.initial_inventory),
  inventory_max: toFloat(row.max_inventory)
});

// Load Tier-1 Suppliers
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.tier = '1'
CREATE (t:Tier1Supplier {
  id: row.node_id,
  name: row.node_name,
  tier: 1,
  location: row.location,
  inventory_current: toFloat(row.initial_inventory),
  inventory_max: toFloat(row.max_inventory)
});

// Load Tier-2 Suppliers
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.tier = '2'
CREATE (t:Tier2Supplier {
  id: row.node_id,
  name: row.node_name,
  tier: 2,
  location: row.location,
  inventory_current: toFloat(row.initial_inventory),
  inventory_max: toFloat(row.max_inventory)
});

// Load Products
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
CREATE (p:Product {
  id: row.product_id,
  name: row.product_name,
  type: row.product_type,
  level: toInteger(row.level)
});
```

**Step 3: Load Relationships**
```cypher
// Load SUPPLIES relationships (arcs between nodes)
LOAD CSV WITH HEADERS FROM 'file:///arcs.csv' AS row
MATCH (from) WHERE from.id = row.from_node
MATCH (to) WHERE to.id = row.to_node
CREATE (from)-[r:SUPPLIES]->(to)
SET r.lead_time_days = toFloat(row.lead_time),
    r.capacity_per_period = toFloat(row.capacity),
    r.initial_flow = toFloat(row.initial_flow);

// Load Bill of Materials (CONTAINS relationships)
LOAD CSV WITH HEADERS FROM 'file:///bom.csv' AS row
MATCH (parent:Product {id: row.parent_product_id})
MATCH (component:Product {id: row.component_product_id})
CREATE (parent)-[r:CONTAINS]->(component)
SET r.quantity_required = toFloat(row.quantity);

// Load PRODUCES relationships (which supplier makes which product)
LOAD CSV WITH HEADERS FROM 'file:///node_products.csv' AS row
MATCH (node) WHERE node.id = row.node_id
MATCH (p:Product {id: row.product_id})
CREATE (node)-[:PRODUCES]->(p);
```

**Task 1.5: Verify Data Load (30 min)**
```cypher
// Check all node counts
CALL db.labels() YIELD label
CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) as count', {})
YIELD value
RETURN label, value.count AS count;

// Expected:
// OEM: 1
// Tier1Supplier: 4
// Tier2Supplier: 2
// Product: 28,049

// Check relationship counts
MATCH ()-[r]->()
RETURN type(r) AS relType, count(*) AS count
ORDER BY count DESC;

// View sample paths
MATCH path = (t2:Tier2Supplier)-[:SUPPLIES*1..3]->(oem:OEM)
RETURN path LIMIT 5;

// View BOM structure
MATCH (car:Product {type: 'car'})-[:CONTAINS*1..3]->(component:Product)
RETURN car.name, collect(component.name) AS components
LIMIT 5;
```

---

#### **Afternoon Session (4-5 hours)**

**Task 1.6: Exploratory Data Analysis - Design 10 Queries (2 hours)**

**EDA 1: Network Inventory**
```cypher
// Count nodes by type
MATCH (n)
RETURN labels(n)[0] AS nodeType, count(*) AS count
ORDER BY count DESC;

// Count relationships by type
MATCH ()-[r]->()
RETURN type(r) AS relType, count(*) AS count
ORDER BY count DESC;
```

**Narrative:**
"The automotive supply network comprises 1 OEM, 4 Tier-1 suppliers, and 2 Tier-2 suppliers, managing 28,049 products across multiple hierarchy levels. The network includes [X] supply relationships, [Y] Bill of Materials dependencies, and [Z] production assignments..."

**EDA 2: Product Hierarchy Distribution**
```cypher
// Products by type
MATCH (p:Product)
RETURN p.type AS productType, count(*) AS count
ORDER BY count DESC;

// Products by hierarchy level
MATCH (p:Product)
RETURN p.level AS hierarchyLevel, count(*) AS products
ORDER BY hierarchyLevel;
```

**Narrative:**
"Products are distributed across [N] hierarchy levels, from finished cars (level 0) to raw components (level N). The majority ([X]%) are low-level components, while only [Y] are finished vehicle models..."

**EDA 3: Supplier Production Portfolio**
```cypher
// Products per supplier
MATCH (s)-[:PRODUCES]->(p:Product)
RETURN s.name AS supplier,
       labels(s)[0] AS tier,
       count(p) AS productCount,
       collect(DISTINCT p.type) AS productTypes
ORDER BY productCount DESC;
```

**Narrative:**
"Tier-1 suppliers typically manage [X-Y] products each, focusing on major systems (engines, transmissions). Tier-2 suppliers handle [A-B] components, specializing in specific part categories..."

**EDA 4: Bill of Materials Complexity**
```cypher
// Products with deepest BOM (most components)
MATCH (product:Product)-[:CONTAINS]->(component:Product)
WITH product, count(component) AS componentCount
WHERE componentCount > 10
RETURN product.name, product.type, componentCount
ORDER BY componentCount DESC
LIMIT 20;

// Average BOM depth
MATCH path = (car:Product {type: 'car'})-[:CONTAINS*]->(leaf:Product)
WHERE NOT (leaf)-[:CONTAINS]->()
RETURN car.name,
       max(length(path)) AS maxBOMDepth,
       avg(length(path)) AS avgBOMDepth
ORDER BY maxBOMDepth DESC
LIMIT 10;
```

**Narrative:**
"Finished cars have Bill of Materials spanning [X] levels deep on average, with the most complex vehicles requiring [Y] distinct components. This hierarchical structure creates cascading dependencies where a single Tier-2 component shortage can halt final assembly..."

**EDA 5: Single-Source Products (Bottleneck Detection)**
```cypher
// Products with only one supplier
MATCH (product:Product)<-[:PRODUCES]-(supplier)
WITH product, count(supplier) AS supplierCount
WHERE supplierCount = 1
RETURN product.name, product.type, supplierCount
ORDER BY product.type, product.name
LIMIT 30;
```

**Narrative:**
"[X] products are single-sourced, creating potential bottlenecks. If the sole supplier experiences disruption, there are no alternative sources. This is especially risky for critical systems like [examples]..."

**EDA 6: Lead Time Analysis**
```cypher
// Average lead time by supplier tier
MATCH (supplier)-[s:SUPPLIES]->()
RETURN labels(supplier)[0] AS tier,
       avg(s.lead_time_days) AS avgLeadTime,
       min(s.lead_time_days) AS minLeadTime,
       max(s.lead_time_days) AS maxLeadTime
ORDER BY tier;

// Longest lead time paths
MATCH path = (t2:Tier2Supplier)-[s:SUPPLIES*]-(oem:OEM)
WITH path,
     reduce(totalTime = 0, rel IN relationships(path) | 
       totalTime + rel.lead_time_days) AS totalLeadTime
RETURN [n IN nodes(path) | n.name] AS supplyPath,
       totalLeadTime
ORDER BY totalLeadTime DESC
LIMIT 10;
```

**Narrative:**
"Tier-2 suppliers have average lead times of [X] days, while Tier-1 suppliers average [Y] days. Multi-tier paths accumulate [Z] total days from raw material to finished car, highlighting the importance of inventory buffers..."

**EDA 7: Capacity Constraints**
```cypher
// Suppliers by capacity
MATCH (supplier)-[s:SUPPLIES]->()
RETURN supplier.name,
       labels(supplier)[0] AS tier,
       sum(s.capacity_per_period) AS totalCapacity,
       count(s) AS outboundLinks
ORDER BY totalCapacity DESC;
```

**Narrative:**
"Capacity varies significantly across suppliers. Tier-1 suppliers handling major systems have capacities of [X-Y] units/period, while Tier-2 component suppliers range [A-B]. Bottlenecks likely occur at suppliers with high product count but limited capacity..."

**EDA 8: Inventory Utilization**
```cypher
// Inventory levels vs. maximum
MATCH (node)
WHERE node.inventory_max IS NOT NULL
RETURN node.name,
       labels(node)[0] AS type,
       node.inventory_current AS current,
       node.inventory_max AS maximum,
       toFloat(node.inventory_current) / node.inventory_max AS utilizationRate
ORDER BY utilizationRate DESC;
```

**Narrative:**
"Several suppliers operate near maximum inventory ([X]% utilization), indicating potential stockout risk during demand surges. OEM inventory is at [Y]% capacity, suggesting [low/high] buffer against supply disruptions..."

**EDA 9: Product Tier Distribution**
```cypher
// Products produced per tier
MATCH (supplier)-[:PRODUCES]->(p:Product)
RETURN labels(supplier)[0] AS supplierTier,
       p.type AS productType,
       count(*) AS productCount
ORDER BY supplierTier, productCount DESC;
```

**Narrative:**
"Tier-2 suppliers focus on [component types], Tier-1 on [system types], and OEM on [final assembly]. This specialization creates natural dependencies where Tier-1 cannot produce without Tier-2 components..."

**EDA 10: Demand vs. Supply Capacity**
```cypher
// Total demand vs. production capacity (if demand data available)
MATCH (p:Product)<-[:DEMANDS]-(demand)
WITH p, sum(demand.quantity) AS totalDemand
MATCH (supplier)-[:PRODUCES]->(p)
OPTIONAL MATCH (supplier)-[s:SUPPLIES]->()
RETURN p.name,
       totalDemand,
       sum(s.capacity_per_period) AS supplierCapacity,
       CASE WHEN sum(s.capacity_per_period) < totalDemand 
            THEN 'Capacity Shortage'
            ELSE 'Adequate Capacity'
       END AS status
ORDER BY totalDemand DESC;
```

**Narrative:**
"Demand for popular car models ([examples]) may exceed current supplier capacity during peak periods. Products with 'Capacity Shortage' status require either capacity expansion or demand management..."

---

**Task 1.7: Design 2 Deeper Analytical Questions (1 hour)**

**Analytical Question 1: Multi-Tier Critical Path Analysis**
```cypher
// Find products with longest total lead time from Tier-2 to OEM
MATCH path = (t2:Tier2Supplier)-[:SUPPLIES*]->(oem:OEM)
MATCH (t2)-[:PRODUCES]->(product:Product)
WITH product, path,
     reduce(totalTime = 0, rel IN relationships(path) |
       totalTime + rel.lead_time_days) AS cumulativeLeadTime
RETURN product.name,
       product.type,
       [n IN nodes(path) | n.name] AS supplyPath,
       cumulativeLeadTime
ORDER BY cumulativeLeadTime DESC
LIMIT 25;
```

**Write full narrative:**
- Context: Why cumulative lead time matters
- Results: Which products have longest paths
- Impact: How this affects production planning
- Recommendations: Inventory buffering strategies

**Analytical Question 2: Single-Point-of-Failure Products**
```cypher
// Find finished cars vulnerable to Tier-2 single-source components
MATCH (car:Product {type: 'car'})-[:CONTAINS*]->(component:Product)
MATCH (component)<-[:PRODUCES]-(supplier:Tier2Supplier)
WITH component, car, count(DISTINCT supplier) AS supplierCount
WHERE supplierCount = 1
WITH car, count(component) AS vulnerableComponents
WHERE vulnerableComponents > 5
RETURN car.name,
       vulnerableComponents,
       'High Tier-2 Risk' AS riskLevel
ORDER BY vulnerableComponents DESC;
```

**Write full narrative:**
- Context: Cascading Tier-2 risk
- Results: Which cars most vulnerable
- Impact: Production halt scenarios
- Recommendations: Supplier diversification priorities

---

**Task 1.8: Study Reference Materials (1-2 hours)**

1. Read pharma demo introduction (structure template)
2. Review Mendeley paper abstract (domain context)
3. Note automotive supply chain terminology:
   - OEM, Tier-1/2/3
   - Bill of Materials (BOM)
   - Multi-echelon
   - Assembly hierarchy
   - Lead time cascade

---

### **DAY 2: ANALYSIS IMPLEMENTATION (10 hours)**

#### **Morning Session (5 hours)**

**Task 2.1: Write Introduction Section (1 hour)**
- Problem statement (use template from above)
- Research objectives
- Dataset description
- Graph schema design

**Task 2.2: Implement All 10 EDA Queries (3 hours)**
- Run each query
- Capture results in DataFrames
- Create visualizations (bar charts, distributions)
- Write narrative for each (2-3 paragraphs)

**Task 2.3: Create EDA Visualizations (1 hour)**
```python
import matplotlib.pyplot as plt
import seaborn as sns

# Example: Product hierarchy distribution
plt.figure(figsize=(10, 6))
sns.barplot(data=df, x='level', y='count')
plt.title('Product Distribution by Hierarchy Level')
plt.xlabel('BOM Level')
plt.ylabel('Product Count')
plt.tight_layout()
plt.show()

# Example: Supplier capacity comparison
plt.figure(figsize=(12, 6))
sns.barplot(data=df, x='supplier', y='capacity', hue='tier')
plt.title('Production Capacity by Supplier and Tier')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```

---

#### **Afternoon Session (5 hours)**

**Task 2.4: Implement Analytical Question 1 (2 hours)**
- Run critical path query
- Analyze results
- Write 4-section narrative:
  1. Context
  2. Query logic explanation
  3. Results interpretation
  4. Operational recommendations

**Task 2.5: Implement Analytical Question 2 (2 hours)**
- Run single-point-of-failure query
- Analyze results
- Write 4-section narrative (same structure)

**Task 2.6: Create Analytical Visualizations (1 hour)**
- Lead time distribution chart
- Risk matrix (suppliers vs. vulnerability)
- BOM depth comparison

---

### **DAY 3: GDS & FINALIZATION (10 hours)**

#### **Morning Session (5 hours)**

**Task 3.1: PageRank Analysis (2.5 hours)**

**Create Graph Projection:**
```cypher
CALL gds.graph.project(
  'automotive-network',
  ['OEM', 'Tier1Supplier', 'Tier2Supplier', 'Product'],
  {
    SUPPLIES: {orientation: 'NATURAL'},
    PRODUCES: {orientation: 'NATURAL'},
    CONTAINS: {orientation: 'NATURAL'}
  }
);
```

**Run PageRank:**
```cypher
CALL gds.pageRank.stream('automotive-network')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS name,
       labels(gds.util.asNode(nodeId))[0] AS type,
       score
ORDER BY score DESC
LIMIT 20;
```

**Write Algorithm Justification:**
```markdown
### 5.1 PageRank: Critical Supplier and Product Identification

**Algorithm Choice:**
PageRank identifies suppliers and products whose failure would cascade through the multi-tier network.

**Theoretical Foundation:**
[Use same PageRank formula and explanation as pharma demo]

**Why PageRank for Automotive Supply Chains:**
1. Multi-tier dependencies: Tier-2 → Tier-1 → OEM flows
2. BOM hierarchies: Component criticality propagates up
3. Weighted influence: High-volume components rank higher

**Results:**
[After running] Top-ranked nodes include [Tier-1 supplier X] and [component Y], confirming their strategic importance...

**Operational Insights:**
- Prioritize backup sourcing for top 10 suppliers
- Maintain safety stock for top 20 components
- Enhanced monitoring for critical paths
```

**Create Visualizations:**
- PageRank vs Degree scatter
- Top 20 suppliers/products bar chart

**Task 3.2: Louvain Community Detection (2.5 hours)**

**Run Louvain:**
```cypher
CALL gds.louvain.stream('automotive-network')
YIELD nodeId, communityId
RETURN communityId,
       labels(gds.util.asNode(nodeId))[0] AS nodeType,
       count(*) AS memberCount
ORDER BY memberCount DESC;
```

**Characterize Communities:**
```cypher
CALL gds.louvain.stream('automotive-network')
YIELD nodeId, communityId
WITH gds.util.asNode(nodeId) AS node, communityId
WHERE 'Tier1Supplier' IN labels(node) OR 'Tier2Supplier' IN labels(node)
RETURN communityId,
       collect(node.name) AS suppliers,
       count(*) AS size
ORDER BY size DESC;
```

**Write Algorithm Justification:**
[Same structure as PageRank - theory, why it fits, interpretation]

**Create Visualizations:**
- Community size distribution
- Network graph colored by community

---

#### **Afternoon Session (5 hours)**

**Task 3.3: Write Executive Summary (1 hour)**
- Summarize key findings from EDA
- Highlight PageRank insights
- Note Louvain communities
- State operational recommendations

**Task 3.4: Write Conclusions Section (1 hour)**
- Key findings summary
- Operational impact
- Value delivered
- Future work

**Task 3.5: Final Quality Check (1.5 hours)**
- [ ] All contractions removed
- [ ] Figure captions added (all charts)
- [ ] Table captions added
- [ ] Spelling checked
- [ ] Code cells clean
- [ ] All queries execute
- [ ] Narratives complete

**Task 3.6: Polish Visualizations (1.5 hours)**
- Increase font sizes
- Add figure captions
- Ensure consistent styling
- Export final charts

---

## 📚 **REFERENCE MAPPING**

### **Pharma Demo → Automotive Translation**

| Pharma Concept | Automotive Equivalent |
|----------------|----------------------|
| Suppliers | Tier-2 Suppliers |
| Raw Materials (RM) | Components/Parts |
| API | Major Systems (engines, transmissions) |
| BULK, DP, FG stages | Assembly stages |
| Distributor | OEM (final assembler) |
| Batch traceability | BOM traceability |
| disruption_likelihood | lead_time, capacity_shortage |
| SUPPLIES_RM | SUPPLIES (tier relationships) |
| PRODUCT_FLOW | CONTAINS (BOM) |

---

## ✅ **DELIVERABLES CHECKLIST**

**By End of Day 3:**
- [ ] Neo4j Desktop database with all data loaded
- [ ] Jupyter notebook with complete analysis
- [ ] 10 EDA queries with narratives
- [ ] 2 deeper analytical questions
- [ ] PageRank analysis with justification
- [ ] Louvain analysis with justification
- [ ] 5+ visualizations with captions
- [ ] Introduction section
- [ ] Executive summary
- [ ] Conclusions section
- [ ] All quality standards met

---

## 🎯 **YOUR UNIQUE PROJECT**

**What Makes This Different from Pharma:**
- ✅ Automotive domain (not pharmaceutical)
- ✅ Multi-tier supplier hierarchy (not bipartite)
- ✅ Bill of Materials focus (not batch tracing)
- ✅ Assembly complexity (not ingredient flow)
- ✅ Capacity constraints (not contamination risk)

**Same Professional Quality:**
- ✅ Same algorithm justifications
- ✅ Same narrative structure
- ✅ Same visualization standards
- ✅ Same academic rigor

**Result:**
Your own unique automotive supply chain analysis using Neo4j GDS! 🚀

---

**END OF AUTOMOTIVE MULTI-ECHELON PLAN**
