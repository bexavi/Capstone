LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE toInteger(trim(row.tier)) = 0
MERGE (o:OEM:Facility {id: row.node_id})
SET o.name = row.name,
    o.inventory_current = toFloat(row.initial_inventory),
    o.inventory_max = toFloat(row.max_inventory),
    o.lat = toFloat(row.lat),
    o.lon = toFloat(row.lon);

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE toInteger(trim(row.tier)) = 1
MERGE (t:Tier1Supplier:Facility {id: row.node_id})
SET t.name = row.name,
    t.tier = 1,
    t.inventory_current = toFloat(row.initial_inventory),
    t.inventory_max = toFloat(row.max_inventory),
    t.lat = toFloat(row.lat),
    t.lon = toFloat(row.lon);

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE toInteger(trim(row.tier)) = 2
MERGE (t:Tier2Supplier:Facility {id: row.node_id})
SET t.name = row.name,
    t.tier = 2,
    t.inventory_current = toFloat(row.initial_inventory),
    t.inventory_max = toFloat(row.max_inventory),
    t.lat = toFloat(row.lat),
    t.lon = toFloat(row.lon);

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE toInteger(trim(row.tier)) > 2
MERGE (f:Facility {id: row.node_id})
SET f.name = row.name,
    f.tier = toInteger(trim(row.tier)),
    f.inventory_current = toFloat(row.initial_inventory),
    f.inventory_max = toFloat(row.max_inventory),
    f.lat = toFloat(row.lat),
    f.lon = toFloat(row.lon);
