# Phase Q1.5 实体解析增强 — 验收报告

> 目标：让 NL 图谱查询不再依赖 canonical_name_cn 精确匹配，通过「别名表 + Atlas 名称 +
> 模糊候选」增强 Brain Region 实体解析。本阶段不修改 canonical 数据、不修改 mirror 数据、
> 不新增虚假脑区、不接入 LLM，只做脑区实体解析。
>
> 日期：2026-08-21 · 分支：codex/ontology-evidence

---

## 1. Migration

`backend/migrations/20260829_canonical_region_aliases.sql`（已应用到开发库）：

- 新表 `canonical_region_aliases`：
  - `id` UUID PK（uuid_generate_v4）
  - `region_id` UUID NOT NULL **FK → canonical_brain_regions(id) ON DELETE CASCADE**（绝不新增虚假脑区，别名随脑区删除级联）
  - `alias` TEXT NOT NULL
  - `alias_language` CHECK IN ('cn','en','abbr')
  - `source` CHECK IN ('manual_curated','atlas','ontology_synonym')（默认 manual_curated；ontology_synonym 为预留，同义词仍走实时解析）
  - `confidence` FLOAT CHECK 0..1
  - `created_at` TIMESTAMPTZ
  - **UNIQUE(region_id, alias)** + alias 索引
- 手工 seed：只覆盖 `macro` + `clinical` 粒度（52 区），禁止自动生成；每区覆盖
  canonical_name_cn 常见中文表达 / canonical_name_en 医学英文表达 / 缩写。
- Atlas seed：从 `atlas_region_resources` + `atlas_region_mappings` 已有 active
  same_species 映射自动生成别名（alias=atlas region_name/acronym，source='atlas'），
  **不复制实体只加别名**；跨物种 homology 映射被排除。

## 2. Alias 数量

| source | lang | 行数 | 覆盖脑区 |
|--------|------|------|----------|
| atlas  | en   | 611  | 611 |
| atlas  | abbr | 246  | 246 |
| manual | cn   | 45   | 44 |
| manual | en   | 45   | 44 |
| manual | abbr | 70   | 51 |
| **合计** | | **1017** | |

示例（手工 seed）：海马(海马体/海马结构 cn、Hippocampal formation en、HF/HPF/Hipp abbr)、
大脑(大脑半球 cn、Cerebral hemisphere en、Cereb/CB abbr)、小脑(Cerebellum/Cb)、
缘上回(修复旧误译「超边缘」)、距状沟周围皮层(修复旧误译「骨膜」)。
手工 seed 时校验冲突：删除 cerebellum 重复的 CB 缩写，仅保留 Cb。

## 3. 覆盖脑区数量

**52/52** — 全部 active `macro`(4) + `clinical`(48) canonical_brain_regions 均有别名。
不覆盖 subregion / fine（按规格）。

已知数据缺口：**前额叶 / PFC 未入 seed** — canonical 库中不存在 macro/clinical 级别的
「Prefrontal cortex」实体（只有 meso 粒度 dlpfc/vmpfc）。PFC→Prefrontal cortex 行为
由自建测试覆盖，后续若新增该 canonical 脑区，seed 补一条即可。

## 4. 解析优先级（resolve_region 7 级链）

```
1. canonical_name_cn exact           (0.95, source=canonical_region)
2. canonical_name_en exact           (0.95, source=canonical_region)
3. canonical_region_aliases exact    (行内 confidence：cn/en 0.95、abbr 0.85)
   + 候选池名称（兼容旧行为，0.9）    ← 多命中(如 L/R 半球同标签) → 多候选不自动选择
4. atlas 名称实时 join               (0.9, source=atlas；region_name → acronym，
                                        仅 same_species，homology 跨物种排除)
5. ontology synonym                  (0.85, source=ontology_synonym)
6. 模糊候选 fallback                 (共享前缀占比，min 2 字符、阈值 0.5、top5)
7. unresolved                        (不报错，warnings 说明 + 候选列表)
```

禁止自动猜测保持：多候选（alias 多命中 / fuzzy）一律返回 `source_entities` 候选列表，
`entity=null`、`intent=unresolved`，供前端消歧。

## 5. 响应扩展（保持兼容）

`OntologyQueryResponse` 新增（旧字段不变）：
- `source_entities`：多候选时为 `[{candidate, confidence}]`
- `entity_match_detail`：`{matched_by, alias?, source?, confidence?}`

## 6. 测试结果

**`tests/test_region_alias_resolution.py`：13/13 通过**（8 项规格 + 5 项额外）。

| # | 测试 | 结果 |
|---|------|------|
| 1 | 海马→Hippocampus（canonical_name_cn） | ✅ 真实数据 |
| 2 | 海马体→Hippocampus（manual 别名，0.95） | ✅ 真实数据 + 自建溯源断言 |
| 3 | hippocampal formation→Hippocampus（英文别名） | ✅ 自建（真实库中该名经 P2 命中 ng:br:hippocampal_formation，属正确优先级） |
| 4 | PFC→Prefrontal cortex（缩写，0.85） | ✅ 自建 |
| 5 | 大脑→Cerebrum（canonical_name_cn） | ✅ 真实数据 |
| 6 | Atlas 名称查询（source=atlas，0.9；含 acronym） | ✅ 自建 + 真实 HCP 标签对 |
| 7 | 未知词 → unresolved | ✅ |
| 8 | 多候选不自动选择（0.89 / 0.78 两候选） | ✅ |
| + | P2 canonical en 先于 alias | ✅ |
| + | P3 manual alias 先于 P4 atlas 名（同名验证） | ✅ |
| + | 真实 HCP 标签「1」→ L/R 双候选 | ✅ |

回归：`test_ontology_query.py` + `test_multiscale_ontology.py` **25/25 通过**；
全量套件在跑（改动面仅限 ontology query 域）。

## 7. 示例查询结果（真实库 smoke test）

| 问题 | entity | matched_by | 溯源 |
|------|--------|-----------|------|
| 海马有哪些亚区 | ng:br:hippocampus | canonical_name_cn | source=canonical_region, 0.95 |
| 海马体有哪些亚区 | ng:br:hippocampus | alias | alias=海马体, source=manual_curated, 0.95 |
| HF有哪些亚区 | ng:br:hippocampus | alias | alias=HF, source=manual_curated, 0.85 |
| cerebral hemisphere 有哪些亚区 | ng:br:cerebrum | alias | alias=cerebral hemisphere, source=manual_curated, 0.95 |
| 今天的天气 | — | — | unresolved（意图层拦截，不报错） |

## 8. 限制与后续

- 本阶段只做脑区实体解析；circuit/function alias 不在范围。
- 前额叶/PFC 依赖 canonical 侧新增实体（见 §3）。
- `ontology_synonym` 来源为表结构预留；同义词仍走 ontology_term_synonyms 实时层。

## 9. 收尾修复（2026-08-21）— 前额叶查询完整可用

验收后发现「前额叶有什么功能」仍 unresolved：canonical 库缺少前额叶实体（仅子区
dlpfc/vmpfc + Desikan 5 区），且模糊匹配只支持前缀，`前额叶` 是子区名的**后缀**，
无法命中。修复（`backend/migrations/20260830_prefrontal_region.sql`，已应用）：

1. **新增 canonical 实体** `ng:br:prefrontal_cortex`（前额叶/Prefrontal cortex，
   clinical 粒度，真实解剖结构非虚构）+ 4 别名（前额叶/前额叶皮层 cn 0.95、
   Prefrontal cortex en 0.95、**PFC abbr 0.85**）。
2. **7 条 part_of 层级**：上额叶/喙中额叶/尾中额叶/眶额外侧/眶额内侧（Desikan）
   + dlpfc/vmpfc（meso）→ 前额叶。「前额叶有哪些亚区」现返回 7 区。
3. **功能聚合兜底**（`canonical_region_service.get_region_functions`）：
   自身无回路时取**直接亚区**的回路功能；自身有回路的脑区行为不变
   （海马 73 条功能不变）。前额叶经聚合返回 168 条功能。

实测（真实库）：

| 问题 | 结果 |
|------|------|
| 前额叶有什么功能 | region_functions → ng:br:prefrontal_cortex（canonical_name_cn 0.95），168 条功能 |
| 前额叶有哪些亚区 | 7 个亚区（上额叶/喙中额叶/尾中额叶/眶额内/外侧/背外侧/腹内侧前额叶） |
| PFC有什么功能 | alias PFC 0.85 → 同一实体，168 条功能 |
| 海马有什么功能 | 不变（73 条，自有回路） |
