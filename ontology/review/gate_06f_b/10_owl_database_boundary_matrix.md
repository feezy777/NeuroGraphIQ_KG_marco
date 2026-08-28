# Gate 6F-B — OWL / DB Boundary Matrix

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

| Concept | OWL | PostgreSQL | Status |
|---|---|---|---|
| BrainRegion | YES | YES | canonical concept |
| partOf | YES | projection | anatomical hierarchy |
| subfieldOf | YES | projection | anatomical hierarchy |
| SpatialRepresentation | NO | YES | DB only V1 |
| spatiallyOverlaps | NO | future DB relation | DB only |
| adjacentTo | NO | future DB relation | DB only |
| locatedIn | NO | NO/current | REMOVE/DEFER |
| overlap_ratio | NO | DB | numeric spatial metric |
| reference_space | NO | DB | required context |
| atlas_version | NO | DB | required context |
| registration_method | NO | DB/provenance | context |
| aggregation mapping | NO OWL relation | YES | integration layer |
| RegionMapping | existing reified model | YES | external integration |
