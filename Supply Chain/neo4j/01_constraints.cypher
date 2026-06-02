// Neo4j 5.x — run before bulk load. Product and facility ids are strings (e.g. zp7, 64001).

CREATE CONSTRAINT oem_id IF NOT EXISTS FOR (o:OEM) REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT tier1_id IF NOT EXISTS FOR (t:Tier1Supplier) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT tier2_id IF NOT EXISTS FOR (t:Tier2Supplier) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT facility_id IF NOT EXISTS FOR (f:Facility) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT country_name IF NOT EXISTS FOR (c:Country) REQUIRE c.name IS UNIQUE;
