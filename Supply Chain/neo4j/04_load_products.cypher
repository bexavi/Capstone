LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
MERGE (p:Product {id: row.product_id})
SET p.name = row.name,
    p.type = row.product_type,
    p.level = CASE
      WHEN row.level IS NULL OR trim(toString(row.level)) = '' THEN -1
      ELSE toInteger(trim(toString(row.level)))
    END;
