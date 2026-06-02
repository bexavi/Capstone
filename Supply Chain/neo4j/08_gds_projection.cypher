// Requires Neo4j Graph Data Science library.
CALL gds.graph.drop('automotive-network', false) YIELD graphName RETURN graphName;

CALL gds.graph.project(
  'automotive-network',
  ['OEM', 'Tier1Supplier', 'Tier2Supplier', 'Facility', 'Product', 'Country'],
  {
    SUPPLIES: {orientation: 'NATURAL', properties: ['lead_time_days', 'capacity_per_period']},
    PRODUCES: {orientation: 'NATURAL'},
    CONTAINS: {orientation: 'NATURAL', properties: ['quantity_required']},
    LOCATED_IN: {orientation: 'NATURAL'}
  }
);

// PageRank (unweighted example; weight via relationship property in GDS 2.x+)
CALL gds.pageRank.stream('automotive-network')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS name,
       labels(gds.util.asNode(nodeId)) AS labels,
       score
ORDER BY score DESC
LIMIT 25;

CALL gds.louvain.stream('automotive-network')
YIELD nodeId, communityId
RETURN communityId,
       labels(gds.util.asNode(nodeId))[0] AS nodeType,
       count(*) AS members
ORDER BY members DESC;
