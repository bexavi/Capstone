# AUTOMOTIVE SUPPLY CHAIN PROJECT - ACTUAL DATA STRUCTURE
## Complete Implementation Guide with Real Column Names

**Dataset:** Mendeley Automotive Production Network  
**Format:** 12 CSV files (converted from .xlsb)  
**Total Records:** 143,959 rows across all files  
**Key Feature:** 87,059 Bill of Materials relationships! 🎯

---

## 📊 **ACTUAL DATA STRUCTURE**

### **Sheet 1: products.csv (28,049 rows)**
**What it contains:** All products in the network

**Columns:**
- `product_p`: Product ID (e.g., "64001", "DK8", "BEV")
- `group_g`: Product group/type ("car", "engine", "gear", "battery", "seat")
- `transportation_size_s`: Transportation size (0 for most)

**Product Groups Found:**
- `car`: Finished vehicles (e.g., 64001, 64002, 64003...)
- `engine`: Engine types (e.g., DN4, DG6, DK8, D83...)
- `gear`: Transmission/gears
- `battery`: Battery systems (e.g., BEV)
- `seat`: Seat assemblies

**Example:**
```
product_p  group_g  transportation_size_s
64001      car      0
DN4        engine   0
BEV        battery  0
```

---

### **Sheet 2: nodes.csv (12 rows)**
**What it contains:** All facilities/suppliers in the network

**Columns:**
- `node_n`: Node identifier

**Actual Nodes:**
1. `zp7` - Assembly Point 7 (OEM plant 1)
2. `zp8` - Assembly Point 8 (OEM plant 2 / final delivery)
3. `engine-supplier_inv` - Engine supplier inventory
4. `engine-supplier_prod` - Engine supplier production
5. `gear-supplier_inv` - Gear supplier inventory
6. `gear-supplier_prod` - Gear supplier production
7. `seat-supplier_inv` - Seat supplier inventory
8. `seat-supplier_prod` - Seat supplier production
9. `battery-supplier_inv` - Battery supplier inventory
10. `battery-supplier_prod` - Battery supplier production
11. `glass-supplier_inv` - Glass supplier inventory
12. `glass-supplier_prod` - Glass supplier production

**Node Types:**
- `*_prod`: Production facilities (Tier-2 suppliers)
- `*_inv`: Inventory/storage facilities (Tier-1 suppliers)
- `zp7`, `zp8`: OEM assembly plants

---

### **Sheet 3: arcs.csv (11 rows)**
**What it contains:** Supply chain connections between nodes

**Columns:**
- `starting_node_i`: Origin node
- `ending_node_j`: Destination node
- `process_lead_time_l_ij`: Lead time in days
- `group_g`: Product group flowing through this arc

**Example:**
```
starting_node_i         ending_node_j  process_lead_time_l_ij  group_g
gear-supplier_inv       zp7            2                       gear
engine-supplier_inv     zp7            1                       engine
zp7                     zp8            0                       car
```

**Network Flow:**
```
Production → Inventory → Assembly → Customer
(Tier-2)     (Tier-1)     (OEM)
```

---

### **Sheet 4: BOM.csv (87,059 rows) ⭐ KEY DATA**
**What it contains:** Bill of Materials - which products contain which components

**Columns:**
- `mother`: Parent product (assembly)
- `child`: Component product (part)
- `individual_input_quantity_q_mc`: Quantity of child needed per mother

**Example:**
```
mother  child  individual_input_quantity_q_mc
64001   DK8    1       # Car 64001 contains 1 DK8 engine
64001   BG2    1       # Car 64001 contains 1 BG2 gear
64002   D83    1       # Car 64002 contains 1 D83 engine
```

**This is PERFECT for Neo4j CONTAINS relationships!**

---

### **Sheet 5: demands.csv (28,000 rows)**
**What it contains:** Customer demand for finished cars

**Columns:**
- `node_n`: Demand location (always "zp8")
- `product_p`: Product demanded (finished cars)
- `demand_d_npt`: Quantity demanded
- `period_t`: Time period (61-74 = 14 days)

**Example:**
```
node_n  product_p  demand_d_npt  period_t
zp8     64001      1             61
zp8     64001      2             62
zp8     64002      1             61
```

---

### **Sheet 6: operations.csv (15 rows)**
**What it contains:** Manufacturing operations/transformations

**Columns:**
- `node_n`: Node performing operation
- `input_product_group_x`: Input type
- `output_product_group_y`: Output type
- `input_quantity_in_nxy`: Input quantity
- `output_quantity_out_nxy`: Output quantity

**Example:**
```
node_n  input_product_group_x  output_product_group_y  input_quantity  output_quantity
zp7     engine                 car                     1               1
zp7     gear                   car                     1               1
zp7     battery                car                     1               1
```

**Meaning:** At node zp7, 1 engine + 1 gear + 1 battery → 1 car

---

### **Sheet 7: initial_inventories.csv (82 rows)**
**What it contains:** Starting inventory at each node

**Columns:**
- `node_n`: Node location
- `product_p`: Product stored
- `initial_inventory_I_np0`: Starting quantity
- `safety_stock`: Minimum inventory
- `max_inventory`: Maximum capacity

---

### **Sheet 8: capacity_at_arc.csv (154 rows)**
**What it contains:** Production/transport capacity per time period

---

## 🗺️ **GRAPH MODEL (Based on Actual Data)**

### **Nodes in Neo4j:**

**1. Facility Nodes (12 total)**
```cypher
(:Tier2Supplier {name: "engine-supplier_prod", type: "production"})
(:Tier1Supplier {name: "engine-supplier_inv", type: "inventory"})
(:OEM {name: "zp7", type: "assembly"})
(:OEM {name: "zp8", type: "final_delivery"})
```

**2. Product Nodes (28,049 total)**
```cypher
(:Product {id: "64001", group: "car", level: 0})
(:Product {id: "DK8", group: "engine", level: 1})
(:Product {id: "BEV", group: "battery", level: 1})
```

### **Relationships:**

**1. SUPPLIES (from arcs.csv)**
```cypher
(engine-supplier_inv)-[:SUPPLIES {
  lead_time: 1,
  group: "engine"
}]->(zp7)
```

**2. CONTAINS (from BOM.csv - 87,059 relationships!)**
```cypher
(car:Product {id: "64001"})-[:CONTAINS {
  quantity: 1
}]->(engine:Product {id: "DK8"})
```

**3. PRODUCES (from operations.csv + nodes_inflow.csv)**
```cypher
(engine-supplier_prod)-[:PRODUCES]->(DK8:Product)
```

**4. DEMANDS (from demands.csv)**
```cypher
(customer)-[:DEMANDS {
  quantity: 1,
  period: 61
}]->(car:Product {id: "64001"})
```

---

## 💻 **CYPHER LOAD QUERIES (With Actual Column Names)**

### **Step 1: Create Constraints**
```cypher
CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT facility_name IF NOT EXISTS FOR (f:Facility) REQUIRE f.name IS UNIQUE;
```

### **Step 2: Load Products**
```cypher
// Load all products
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
CREATE (p:Product {
  id: row.product_p,
  group: row.group_g,
  transport_size: toInteger(row.transportation_size_s)
});

// Add group-specific labels
MATCH (p:Product)
WHERE p.group = 'car'
SET p:Car;

MATCH (p:Product)
WHERE p.group = 'engine'
SET p:Engine;

MATCH (p:Product)
WHERE p.group = 'gear'
SET p:Gear;

MATCH (p:Product)
WHERE p.group = 'battery'
SET p:Battery;

MATCH (p:Product)
WHERE p.group = 'seat'
SET p:Seat;
```

### **Step 3: Load Facilities/Nodes**
```cypher
// Load all nodes
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
CREATE (f:Facility {
  name: row.node_n
});

// Classify nodes by type
MATCH (f:Facility)
WHERE f.name ENDS WITH '_prod'
SET f:Tier2Supplier, f.type = 'production';

MATCH (f:Facility)
WHERE f.name ENDS WITH '_inv'
SET f:Tier1Supplier, f.type = 'inventory';

MATCH (f:Facility)
WHERE f.name IN ['zp7', 'zp8']
SET f:OEM, f.type = 'assembly';
```

### **Step 4: Load Supply Chain Arcs (SUPPLIES relationships)**
```cypher
LOAD CSV WITH HEADERS FROM 'file:///arcs.csv' AS row
MATCH (from:Facility {name: row.starting_node_i})
MATCH (to:Facility {name: row.ending_node_j})
CREATE (from)-[r:SUPPLIES]->(to)
SET r.lead_time_days = toFloat(row.process_lead_time_l_ij),
    r.group = row.group_g;
```

### **Step 5: Load Bill of Materials (CONTAINS - 87K relationships!)**
```cypher
// Load BOM in batches (87K rows)
LOAD CSV WITH HEADERS FROM 'file:///BOM.csv' AS row
CALL {
  WITH row
  MATCH (mother:Product {id: row.mother})
  MATCH (child:Product {id: row.child})
  CREATE (mother)-[r:CONTAINS]->(child)
  SET r.quantity = toFloat(row.individual_input_quantity_q_mc)
} IN TRANSACTIONS OF 5000 ROWS;
```

### **Step 6: Load Production Relationships (PRODUCES)**
```cypher
// Load which nodes produce which products
LOAD CSV WITH HEADERS FROM 'file:///nodes_inflow.csv' AS row
MATCH (facility:Facility {name: row.node_n})
MATCH (product:Product {id: row.product_p})
CREATE (facility)-[:PRODUCES]->(product);
```

### **Step 7: Load Demand Data**
```cypher
// Create customer node
CREATE (c:Customer {name: "Market"});

// Load demands
LOAD CSV WITH HEADERS FROM 'file:///demands.csv' AS row
WITH row WHERE toInteger(row.period_t) = 61  // Start with period 61
MATCH (c:Customer {name: "Market"})
MATCH (p:Product {id: row.product_p})
CREATE (c)-[r:DEMANDS]->(p)
SET r.quantity = toFloat(row.demand_d_npt),
    r.period = toInteger(row.period_t);
```

### **Step 8: Load Inventory Data (Optional)**
```cypher
LOAD CSV WITH HEADERS FROM 'file:///initial_inventories.csv' AS row
MATCH (f:Facility {name: row.node_n})
MATCH (p:Product {id: row.product_p})
CREATE (f)-[r:STORES]->(p)
SET r.initial_inventory = toFloat(row.initial_inventory_I_np0),
    r.safety_stock = toFloat(row.safety_stock),
    r.max_inventory = toFloat(row.max_inventory);
```

---

## ✅ **VERIFICATION QUERIES**

After loading, verify your data:

```cypher
// Check node counts
MATCH (n)
RETURN labels(n)[0] AS nodeType, count(*) AS count
ORDER BY count DESC;

// Expected:
// Product: 28,049
// Facility: 12
// Customer: 1

// Check relationship counts
MATCH ()-[r]->()
RETURN type(r) AS relType, count(*) AS count
ORDER BY count DESC;

// Expected:
// CONTAINS: 87,059 (BOM relationships!)
// DEMANDS: ~28,000
// SUPPLIES: 11
// PRODUCES: 44

// View sample BOM path
MATCH path = (car:Car)-[:CONTAINS*1..2]->(component)
RETURN car.id, 
       [n IN nodes(path)[1..] | n.id] AS components
LIMIT 5;

// Example output:
// car.id  components
// 64001   ["DK8", "BEV", "BG2"]
// 64002   ["D83", "BEV", "BH3"]
```

---

## 🎯 **YOUR 10 EDA QUERIES (Updated with Actual Data)**

### **EDA 1: Network Inventory**
```cypher
// Count all nodes
MATCH (n)
RETURN labels(n)[0] AS nodeType, count(*) AS count
ORDER BY count DESC;
```

### **EDA 2: Product Group Distribution**
```cypher
// Products by group
MATCH (p:Product)
RETURN p.group AS productGroup, count(*) AS count
ORDER BY count DESC;
```

### **EDA 3: Facility Types**
```cypher
// Facilities by type
MATCH (f:Facility)
RETURN f.type AS facilityType, count(*) AS count, 
       collect(f.name) AS facilities
ORDER BY count DESC;
```

### **EDA 4: Bill of Materials Depth**
```cypher
// Cars with most components (direct children)
MATCH (car:Car)-[:CONTAINS]->(component)
WITH car, count(component) AS componentCount
RETURN car.id, componentCount
ORDER BY componentCount DESC
LIMIT 20;

// Maximum BOM depth
MATCH path = (car:Car)-[:CONTAINS*]->(leaf:Product)
WHERE NOT (leaf)-[:CONTAINS]->()
RETURN car.id,
       max(length(path)) AS maxDepth,
       count(DISTINCT leaf) AS leafComponents
ORDER BY maxDepth DESC
LIMIT 10;
```

### **EDA 5: Critical Components (Used in Most Cars)**
```cypher
// Components used in many different car models
MATCH (car:Car)-[:CONTAINS*1..3]->(component:Product)
WITH component, count(DISTINCT car) AS carCount
WHERE carCount > 100
RETURN component.id, component.group, carCount
ORDER BY carCount DESC
LIMIT 25;
```

### **EDA 6: Lead Time Analysis**
```cypher
// Average lead time by product group
MATCH (from:Facility)-[s:SUPPLIES]->(to:Facility)
RETURN s.group AS productGroup,
       avg(s.lead_time_days) AS avgLeadTime,
       min(s.lead_time_days) AS minLeadTime,
       max(s.lead_time_days) AS maxLeadTime,
       count(*) AS arcCount
ORDER BY avgLeadTime DESC;

// Total lead time from production to final assembly
MATCH path = (prod:Tier2Supplier)-[:SUPPLIES*]->(oem:OEM {name: 'zp8'})
WITH path,
     reduce(time = 0, r IN relationships(path) | 
       time + r.lead_time_days) AS totalLeadTime
RETURN [n IN nodes(path) | n.name] AS supplyPath,
       totalLeadTime
ORDER BY totalLeadTime DESC
LIMIT 10;
```

### **EDA 7: Production Capacity by Facility**
```cypher
// Products produced per facility
MATCH (facility:Facility)-[:PRODUCES]->(product:Product)
RETURN facility.name,
       labels(facility)[1] AS tier,  // Tier2Supplier, Tier1Supplier, or OEM
       count(product) AS productCount,
       collect(DISTINCT product.group)[0..5] AS sampleProducts
ORDER BY productCount DESC;
```

### **EDA 8: Demand Analysis**
```cypher
// Total demand per car model (period 61)
MATCH (c:Customer)-[d:DEMANDS]->(car:Product)
WHERE d.period = 61
RETURN car.id,
       sum(d.quantity) AS totalDemand
ORDER BY totalDemand DESC
LIMIT 30;

// Total demand vs. supply capacity
MATCH (c:Customer)-[d:DEMANDS]->(car:Product)
WITH car, sum(d.quantity) AS totalDemand
MATCH (car)-[:CONTAINS]->(component)
MATCH (facility)-[:PRODUCES]->(component)
RETURN car.id,
       totalDemand,
       count(DISTINCT facility) AS supplierCount,
       collect(DISTINCT component.group) AS componentTypes
ORDER BY totalDemand DESC
LIMIT 20;
```

### **EDA 9: Single-Source Components (Bottlenecks)**
```cypher
// Components produced by only one facility
MATCH (component:Product)<-[:PRODUCES]-(facility:Facility)
WITH component, count(facility) AS supplierCount
WHERE supplierCount = 1
MATCH (component)<-[:PRODUCES]-(onlySupplier)
MATCH (car:Car)-[:CONTAINS*1..3]->(component)
WITH component, onlySupplier, count(DISTINCT car) AS affectedCars
WHERE affectedCars > 10
RETURN component.id,
       component.group,
       onlySupplier.name AS onlySupplier,
       affectedCars
ORDER BY affectedCars DESC
LIMIT 25;
```

### **EDA 10: Supply Chain Paths (Multi-Tier)**
```cypher
// Complete supply chain for a specific car
MATCH path = (prod:Tier2Supplier)-[:SUPPLIES*]->
             (inv:Tier1Supplier)-[:SUPPLIES]->
             (oem:OEM)
WHERE oem.name = 'zp7'
RETURN [n IN nodes(path) | n.name] AS supplyChain,
       reduce(time = 0, r IN relationships(path) | 
         time + r.lead_time_days) AS totalLeadTime
ORDER BY totalLeadTime DESC;
```

---

## 🔬 **YOUR 2 DEEPER ANALYTICAL QUESTIONS**

### **Analytical Question 1: Critical Component Cascade Analysis**
```cypher
// Find components whose shortage would affect the most car models
// considering full BOM hierarchy

MATCH (component:Product)<-[:PRODUCES]-(supplier:Facility)
WITH component, count(supplier) AS supplierCount
WHERE supplierCount = 1  // Single-sourced

MATCH (car:Car)-[:CONTAINS*1..3]->(component)
WITH component, 
     collect(DISTINCT car.id)[0..10] AS affectedCars,
     count(DISTINCT car) AS carCount
WHERE carCount > 50

MATCH (component)<-[:PRODUCES]-(onlySupplier)
MATCH (onlySupplier)<-[:SUPPLIES]-(tierAbove)

RETURN component.id AS criticalComponent,
       component.group AS componentType,
       onlySupplier.name AS singleSupplier,
       tierAbove.name AS dependentOn,
       carCount AS vehiclesAtRisk,
       affectedCars AS sampleVehicles
ORDER BY carCount DESC
LIMIT 20;
```

**Narrative to Write:**
- Context: Why single-sourced components with wide usage are critical
- Results: Which components are most vulnerable
- Impact: How many car models would be affected
- Recommendations: Supplier diversification priorities

### **Analytical Question 2: Longest Lead Time Paths**
```cypher
// Find car models with longest cumulative lead time from
// Tier-2 production to final assembly

MATCH (car:Car)
MATCH (car)-[:CONTAINS]->(component:Product)
MATCH path = (prod:Tier2Supplier)-[:SUPPLIES*]-(oem:OEM {name: 'zp8'})
WHERE (prod)-[:PRODUCES]->(component)

WITH car, path,
     reduce(time = 0, r IN relationships(path) | 
       time + r.lead_time_days) AS pathLeadTime

WITH car,
     max(pathLeadTime) AS longestPath,
     avg(pathLeadTime) AS avgPath,
     collect(pathLeadTime) AS allPaths

RETURN car.id,
       longestPath,
       avgPath,
       size(allPaths) AS componentPaths
ORDER BY longestPath DESC
LIMIT 25;
```

---

## 🎯 **NEXT STEPS**

**TODAY:**
1. ✅ CSVs are ready in `/mnt/user-data/outputs/`
2. Download all 12 CSV files to your computer
3. Read this updated plan

**TOMORROW (Day 1):**
1. Set up Neo4j Desktop
2. Copy CSVs to Neo4j import folder
3. Run the load queries above
4. Verify data loaded correctly

**Ready to start!** 🚀

---

**END OF ACTUAL DATA STRUCTURE GUIDE**
