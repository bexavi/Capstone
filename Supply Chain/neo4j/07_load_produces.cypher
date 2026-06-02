LOAD CSV WITH HEADERS FROM 'file:///node_products.csv' AS row
MATCH (f:Facility {id: row.node_id})
MATCH (p:Product {id: row.product_id})
MERGE (f)-[:PRODUCES]->(p);
