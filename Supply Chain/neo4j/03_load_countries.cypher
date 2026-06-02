LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH DISTINCT trim(row.country) AS country
WHERE country IS NOT NULL AND country <> ''
MERGE (c:Country {name: country});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE trim(row.country) <> ''
MATCH (f:Facility {id: row.node_id})
MATCH (c:Country {name: trim(row.country)})
MERGE (f)-[:LOCATED_IN]->(c);
