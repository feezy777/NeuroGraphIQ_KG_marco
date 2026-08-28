# Gate 5A.1 — Impact Matrix（删除 Type Class 的影响矩阵）

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅影响分析，未执行任何修改**

---

## 1. 删除 ConnectionType / CircuitType / EvidenceType 的影响

| 维度 | ConnectionType → REMOVE | CircuitType → REMOVE | EvidenceType → REMOVE |
|---|---|---|---|
| OWL reasoning | 更直接（subClassOf 链） | 无影响（本为空占位） | 无影响（本为空占位） |
| PostgreSQL schema | `connection_type` 字段保留（app-level），≠ OWL Class | 无 connection_type 式字段；future topology 用字段/属性 | `evidence` 多轴维度用字段表达，非单一 type |
| API | `connection_type` 枚举字段保留 | 无 CircuitType 资源 | evidence 维度字段取代单一 type |
| Frontend | 显示 connection_type 标签不变 | 无 CircuitType 筛选 | 多轴筛选取代单一 type 筛选 |
| Neo4j | `rdf:type` 直接投影 | 无 CircuitType 节点 | 多轴属性投影 |
| Import/Export | connection_type ↔ rdf:type 映射 | 无 | evidence 维度序列化 |
| Backward compatibility | connection_type 字段值不变，仅上层语义从 OWL Class 改为 app 枚举 | 无历史 CircuitType 数据 | 无历史 EvidenceType 数据 |
| Existing Gate docs | Gate 2B hierarchy 需在 Gate 5B 改为 Connection subtype | Gate 3B "reserved" 记录需标注 REMOVE | Gate 4A 已倾向多轴，需标注 EvidenceType REMOVE |

## 2. 关键澄清（防误解）

- **删除 OWL ConnectionType ≠ 数据库不能有 `connection_type`**。
- **删除 CircuitType ≠ 未来 Circuit 不能有 `topology_type` / `construction_mode`**。
- **删除 EvidenceType ≠ Evidence 没有分类维度**（多轴仍在）。

## 3. namespace migration 影响（macro96 → human-brain）

| 维度 | 影响 |
|---|---|
| OWL | TTL 全文 IRI/namespace 重写（无 Individuals/Properties，风险低） |
| PostgreSQL | 无持久化 URI（0 数据迁移） |
| API / Frontend / Neo4j | 无硬编码 IRI（代码层 0 命中） |
| Import/Export | 未来序列化 canonical IRI 时需用新 namespace（app config 统一维护） |
| Backward compatibility | 旧 review 文档保留历史 IRI 快照 |
| Existing Gate docs | Gate 5B 同步更新"当前 IRI"标注 |

## 4. Governance 移出 core ontology 的影响

| 维度 | 影响 |
|---|---|
| OWL | core ontology 更干净（纯科学 + 整合层） |
| PostgreSQL | governance schema 承载 workflow 类 |
| API / Frontend | 不变（governance 已走 DB/API 路径） |
| Neo4j | governance 不入图或作为独立投影 |
| Backward compatibility | governance 类从 OWL 移除但 DB/API 保留 |
