# Gate 3B — Circuit 正式语义摘要

Ontology IRI: `https://neurographiq.org/ontology/macro96`
Version: `0.3.0-gate3b`（draft）
本文件总结 Gate 3B 正式写入 `ngiq:Circuit` 的 rdfs:comment 的科学定义与边界。

---

## 1. Circuit 定义

**Circuit（神经回路）**：由多个 BrainRegion 及其有组织关系的 Connection 构成、具有生物学/结构/功能意义的统一神经单元。

写入 TTL 的核心语义（@en + @zh comment）：

| # | 语义点 | 写入内容 |
|---|---|---|
| 1 | 概念性质 | Circuit 是 biological / functional 概念，**不是 graph-theoretical 概念** |
| 2 | closed loop | General Circuit **不要求 closed loop** |
| 3 | direction | Connection **不要求全部有已知方向**；direction 只在科学语义需要且证据支持时记录 |
| 4 | graph cycle | **graph cycle ≠ biological Circuit**（A→B→C→A 图论闭合不构成 Circuit） |
| 5 | Connection 集合 | **Connection 集合本身 ≠ Circuit**；多条 Connection 仅在具有组织关系 + circuit-level biological meaning/evidence 时才可能形成 Circuit |
| 6 | confirmed 门槛 | confirmed / canonical Circuit 必须具有 **reported circuit evidence** 或 **人工认可的权威 circuit-level evidence** |
| 7 | 晋升边界 | Connection + topology + function reasoning 只能先是 **composed / inferred / hypothesis**，不能自动晋升 confirmed |

## 2. Macro96 curation policy（写入 comment，非 OWL restriction）

- Macro96 V1 默认要求：**≥3 Macro96 BrainRegion + ≥2 Connection**（避免普通脑区对被误收为 Circuit）。
- 允许 **literature-reported exception**：权威文献明确将双区域 reciprocal system 报道为 circuit 时，可进入人工审核。
- **未写成** owl:minCardinality / owl:qualifiedCardinality / OWL restriction / SHACL constraint。

## 3. Circuit → Connection 反向推理边界（写入 comment）

- 若 circuit-level evidence 表明 A→B→C→A，但数据库缺少 C→A，缺失边只能进入 **ConnectionCandidate / hypothesis / targeted-search target**，**不得**直接生成 confirmed Connection。
- 本轮只写语义说明，未新增 InferenceRule / Property / SHACL / 自动推理代码。

## 4. Circuit 层级

- `ngiq:Circuit` 保持 `owl:Class`，**未改变层级**（仍隐式 `owl:Thing` 直接子类，无显式 subClassOf 变化）。
- 英文 label：`Circuit`；中文 label：`回路`。
