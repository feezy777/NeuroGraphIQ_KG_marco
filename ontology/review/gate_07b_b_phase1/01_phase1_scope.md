# Gate 7B-B Phase 1 — 范围与边界

## 1. 本阶段定位

Phase 1 是 Identity Foundation：落地冻结 32 张科学表的第一批 4 张身份基础表。

## 2. 允许（授权范围）

| 表 | 职责 |
|---|---|
| `kg_entities` | 全局身份注册表（shared-PK identity truth） |
| `entity_aliases` | 别名 / 同义词 / 历史名 |
| `entity_xrefs` | 外部数据库/ontology ID 交叉引用 |
| `sources` | 科学来源注册表 |

另含一个 DB helper：`infra.next_ngiq_id(text)`（public ID 发号）。

## 3. 禁止（红线）

- ❌ 建第 5 张科学表。
- ❌ 提前建 BrainRegion / Function / Connection / Circuit / Gene / Disease / Evidence / Atlas / ExternalRegion / RegionMapping 等 subtype 表。
- ❌ 从 legacy `neurographiq_kg_v3_wb` backfill。
- ❌ 插入真实科学数据。
- ❌ 修改本体 TTL。
- ❌ 大规模改 backend API / frontend / Neo4j。
- ❌ commit / push（等待人工验收）。

## 4. 规范来源（实施前已重读）

- `gate_07a_data_dictionary/18_complete_data_dictionary.md`
- `gate_07a_data_dictionary/19_er_model.md`
- `gate_07a_data_dictionary/23_gate_07a_freeze_candidate.md`（§D/§E/§F/§K 权威）
- `gate_07a_data_dictionary/27_gate_07a_consistency_audit.md`
- `gate_07a_data_dictionary/16_controlled_vocabularies.md`
- `gate_07b_a1/05_ngiq_prefix_registry.md`
- `gate_06g_b/05_frozen_ontology_manifest.md`

## 5. 产出

| 类型 | 路径 |
|---|---|
| 迁移 | `backend/migrations/gate7b_002_identity_foundation.sql` |
| 测试 | `backend/tests/test_gate7b_phase1_identity.py`（22 用例） |
| runner 修复 | `backend/scripts/gate7b_migrate.py`（checksum 换行归一化） |
| 测试修复 | `backend/tests/test_gate7b_phase0.py`（sha256 归一化断言） |
| review | `ontology/review/gate_07b_b_phase1/`（20 文件） |
