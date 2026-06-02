LOAD CSV WITH HEADERS FROM 'file:///arcs.csv' AS row
MATCH (a:Facility {id: row.from_node})
MATCH (b:Facility {id: row.to_node})
MERGE (a)-[r:SUPPLIES]->(b)
SET r.lead_time_days = toFloat(row.lead_time_days),
    r.capacity_per_period = toFloat(row.capacity_per_period),
    r.initial_flow = toFloat(row.initial_flow),
    r.delay_probability_proxy = toFloat(row.delay_probability_proxy),
    r.disruption_likelihood_proxy = toFloat(row.disruption_likelihood_proxy);
