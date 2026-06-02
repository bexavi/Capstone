LOAD CSV WITH HEADERS FROM 'file:///bom.csv' AS row
MATCH (parent:Product {id: row.parent_id})
MATCH (child:Product {id: row.child_id})
MERGE (parent)-[r:CONTAINS]->(child)
SET r.quantity_required = toFloat(row.quantity);
