# Gate 6E-A — External Database Evidence

本轮状态: **仅设计，不写 TTL**

---

## 1. 问题

Evidence 来源不一定是 Publication。curated database（HGNC / MONDO / Julich-Brain 等）可能直接提供 Connection / Gene / receptor 数据。当前 `providesEvidence Domain=Publication` 不能强制所有 Evidence 都来自 Publication。

## 2. 现状（冻结）

- `providesEvidence Domain=Publication` 已冻结，本轮不修改。

## 3. 方案（未来）

- 未来可能需要 `Source providesEvidence Evidence`（Source = 来源注册表，含 database/atlas/ontology）。
- 或 Evidence.provenance_json 记录 source_database。

## 4. Publication ≠ Source

- Publication = scientific document。
- Source = database / atlas / literature registry。
- 不要把 MONDO / HGNC / Julich-Brain 伪装成 Publication。

## 5. 结论

- 本轮不修改 providesEvidence Domain。
- 未来 external database evidence provenance 方案 DEFER（见 17_open_questions）。
- LLM 不得作为 scientific source（延续 Gate 7A 冻结）。
