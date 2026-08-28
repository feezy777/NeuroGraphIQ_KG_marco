# Gate 6G-A — OWL / Database / Neo4j Projection Matrix

---

| Concept | OWL Core | PostgreSQL | Neo4j Projection |
|---|---|---|---|
| BrainRegion | YES | YES | node |
| Connection | YES（Class+entity model） | connections | node |
| Circuit | YES | circuits | node |
| Function | YES | functions | node |
| Evidence | YES | evidence | node |
| KnowledgeAssertion | NO | knowledge_assertions | — |
| RegionMapping | YES（reified） | region_mappings | node |
| AggregationMapping | NO | brain_region_aggregation_mappings | — |
| SpatialRepresentation | NO | brain_region_spatial_representations | — |
| partOf | YES | projection | edge |
| subfieldOf | YES | projection | edge |
| subFunctionOf | YES | projection | edge |
| projectsTo | YES（derived） | projection | edge |
| hasConnection | YES（derived） | projection | edge |
| mapsTo | YES（derived） | projection | edge |
| EvidenceLink | NO | evidence_links | — |
| spatial relation | NO | future DB | — |
