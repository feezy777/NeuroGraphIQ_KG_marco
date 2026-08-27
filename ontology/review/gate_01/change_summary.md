# Gate 1 Change Summary — NeuroGraphIQ Macro96 Ontology V1.0

## 本轮新增

- `ontology/neurographiq_macro96_v1.ttl`
  - Ontology declaration（IRI `https://neurographiq.org/ontology/macro96`）
  - Namespace/prefix（`ngiq:` → `https://neurographiq.org/ontology/macro96#`；另声明 rdf/rdfs/owl/xsd）
  - 版本元信息：`owl:versionInfo "0.1.0-gate1"`，status = draft
  - 24 个核心 Class（全部为 owl:Thing 直接子类，暂无层级）
  - 每个 Class 的英文 label（@en）与中文 label（@zh）及一条简短 rdfs:comment
- `ontology/review/gate_01/` 人工审查包（5 个文件）

## 本轮没有做

- 没有建立任何 ObjectProperty / DataProperty / 自定义 AnnotationProperty
- 没有展开 ConnectionType / CircuitType / EvidenceType 子类层级
- 没有 Function hierarchy、BrainRegion hierarchy、SHACL constraints
- 没有 Individuals（含 Macro96 96 个 BrainRegion 实例、9120 ConnectionAssessment 等）
- 没有 HBAO / Uberon / NeuroNames mapping
- 没有 owl:imports（保持为空）
- 没有修改 backend ontology 业务代码、PostgreSQL、migration、API、frontend、Neo4j
- 没有 commit / push

## 未进入的后续 Gate

- Gate 2（ConnectionType 层级）：未开始，等待本 Gate 人工确认
- Gate 3（CircuitType 层级）：未开始
- EvidenceType 层级 Gate、BrainRegion hierarchy、SHACL、实例层、数据库 Schema 等：均未开始
