# Gate 5A.1 — Namespace Migration Impact（macro96 → human-brain 影响面）

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅影响分析，未执行任何 migration**

---

## 1. 影响面结论（实测）

对代码库执行精确检索 `neurographiq.org/ontology`（含 `macro96#`、`ngiq:` 前缀）：

- **命中文件仅限 `ontology/` 目录**：正式 TTL + `ontology/review/gate_01..gate_05a` 的 review 文档。
- **backend / frontend / tests / migrations / scripts 中无任何 `neurographiq.org/ontology` 硬编码。**

> 区分：代码库中大量 `macro96` / `Macro96` 命中是 **Macro96 数据区域池**（`macro96_candidate_service`、`raw_macro96`、`Macro96` 脑区池、granularity 标签），是**领域数据**，与 ontology IRI 无关，**不受 namespace 改名影响**。

## 2. 当前 ontology 已持久化的 URI

| 项 | 数量 |
|---|---|
| Individual | 0 |
| ObjectProperty | 0 |
| DataProperty | 0 |
| external mapping | 0（无 owl:imports） |
| database persisted URI | 0 |
| Neo4j persisted URI | 0 |

**结论：无已持久化 canonical entity URI，migration 无数据迁移负担。**

## 3. 受影响文件清单（仅 TTL + review docs）

| 类别 | 文件 |
|---|---|
| 正式 TTL | `ontology/neurographiq_macro96_v1.ttl` |
| Gate 5A review（本 Gate） | 13 个 `ontology/review/gate_05a/*.md` |
| 历史 Gate docs | `gate_01/ gate_02a/ gate_02b/ gate_03a/ gate_03b/ gate_04a/` 中标注 IRI 的文档 |
| 本 Gate 5A.1 | `ontology/review/gate_05a1/*.md`（以当前 IRI 为"当前值"记录） |

## 4. 硬编码风险

- **是否发现硬编码风险**：否。代码层无 ontology IRI 硬编码；仅 TTL 与文档层引用。
- **唯一需注意**：若未来前端/后端要输出 canonical entity IRI，应在 application config 中统一维护 namespace，而非散落硬编码（当前未发生，作为 Gate 5B 落地的工程约束）。

## 5. Migration 难度与策略

- **难度等级：LOW**（0 Individual/Property，无 DB/Neo4j 持久化 URI，无代码硬编码）。
- **推荐策略**：Gate 5B 一次性重写 TTL（IRI + namespace + label + comment + versionInfo + `ngiq:*` IRI），并同步更新受影响 review 文档的"当前 IRI"标注（历史 Gate 文档可作为历史快照保留原文，仅在前言注明已迁移）。

## 6. 结论

| 项 | 值 |
|---|---|
| 影响文件数量 | 1 TTL + ~14 个 review 文档（含本 Gate） |
| 硬编码风险 | 无（代码层 0 命中） |
| 风险等级 | LOW |
| 推荐策略 | Gate 5B 单次重写 TTL + 文档同步；namespace 在 app config 统一维护 |
