# NeuroGraphIQ KG V3 — 知识图谱构建过程 - Design Spec

> Human-readable design narrative — rationale, audience, style, color choices, content outline.
>
> Machine-readable execution contract: `spec_lock.md`. On divergence, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | NeuroGraphIQ KG V3 — 多粒度脑区知识图谱构建 |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 15 |
| **Design Style** | B) General Consulting + 学术极简；总—分—总叙事 |
| **Target Audience** | 学术答辩评委、神经科学与知识工程研究人员 |
| **Use Case** | 20–25 分钟科研汇报；解释构建方法、治理边界、技术创新与系统成果 |
| **Created Date** | 2026-08-03 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 左右 56px，上 42px，下 34px |
| **Content Area** | 1168×644px；标题区 84px，正文区 508px，页脚区 32px |

---

## III. Visual Theme

### Theme Style

- **Style**: 学术极简、工程信息图、结论清晰
- **Theme**: Light theme
- **Tone**: 严谨、克制、可信、具有系统工程感

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#FFFFFF` | 主背景与大面积留白 |
| **Secondary bg** | `#F4F7FA` | 淡蓝灰分区、表格隔行与信息带 |
| **Primary** | `#1A365D` | 标题、核心模块、主连接线 |
| **Accent** | `#3182CE` | 数据流、链接、选中状态 |
| **Secondary accent** | `#DD6B20` | 审核、风险、需要人工关注 |
| **Body text** | `#243447` | 正文 |
| **Secondary text** | `#5F6F7F` | 注释与说明 |
| **Tertiary text** | `#8492A0` | 页脚与弱标签 |
| **Border/divider** | `#CBD5DF` | 边框与分隔线 |
| **Success** | `#38A169` | 通过、晋升、Final KG |
| **Warning** | `#C05621` | Blocker、Conflict、Reject |

### AI Image Strategy

- **Image Rendering**: vector-illustration
- **Image Palette**: cool-corporate
- **Rendering rule**: clean flat vector illustration, crisp 2px-equivalent outlines, flat solid fills, no gradients inside shapes, no text, no letters, no numbers, no watermarks.
- **Palette rule**: white `#FFFFFF` carries roughly 65% as calm field; deep navy `#1A365D` anchors roughly 25%; blue `#3182CE` carries roughly 8%; orange `#DD6B20` and green `#38A169` are sparse semantic accents.
- **Information rule**: AI images provide only atmosphere and unlabeled structural anchors. Chinese labels, arrows, data, statuses, and all semantically binding relationships are native SVG overlays.

### Gradient Scheme

Only SVG overlays may use subtle gradients for legibility. AI illustrations remain flat-color.

```xml
<linearGradient id="softBlueFade" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.96"/>
  <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/>
</linearGradient>
```

---

## IV. Typography System

### Font Plan

**Typography direction**: 学术衬线标题 × 现代无衬线正文；技术标识使用等宽字体。

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `SimSun` | `Cambria` | `serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `SimSun` | `Cambria` | `serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Cambria, SimSun, serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `Cambria, SimSun, serif`
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body font size = 18px.

| Purpose | Size | Weight |
| ------- | ---- | ------ |
| Cover title | 62px | Bold |
| Page title | 34px | Bold |
| Hero number | 40px | Bold |
| Subtitle | 24px | SemiBold |
| Body content | 18px | Regular |
| Annotation / caption | 14px | Regular |
| Page number / footnote | 11px | Regular |

**Formula rendering policy**: `text-only`. Source contains no formula-worthy mathematical expressions.

---

## V. Layout Principles

### Page Structure

- **Header area**: 84px；左对齐页标题，右侧可放章节短标签。
- **Content area**: 508px；架构图优先占据 65–85% 宽度，说明文字围绕图组织。
- **Footer area**: 32px；项目简称、页码与必要来源说明。

### Layout Pattern Library

| Pattern | Usage |
| ------- | ----- |
| **Negative-space-driven** | 封面、结论与 Q&A |
| **Top-bottom split** | 主流程图 + 底部治理结论 |
| **Asymmetric split (3:7)** | 局部机制说明 + 主架构图 |
| **Layered architecture** | 七层知识体系与 Final KG 模型 |
| **Center-radiating** | LLM 七类提取能力 |
| **Z-pattern / waterfall** | 复合工作流、全链路溯源 |

### Spacing Specification

| Element | Current Project |
| ------- | --------------- |
| Safe margin | 56px horizontal / 42px vertical |
| Content block gap | 28px |
| Icon-text gap | 12px |
| Card gap | 22px |
| Card padding | 22px |
| Card border radius | 8px |

Non-card architecture pages use whitespace and divider lines instead of repeated rounded-card grids. Body line-height is 1.45×.

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `tabler-outline`
- **Stroke width**: 2
- **Usage method**: `<use data-icon="tabler-outline/icon-name" .../>`

### Approved Icon Inventory

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| 脑区与神经知识 | `tabler-outline/brain` | P01, P03 |
| 数据库与知识层 | `tabler-outline/database` | P02, P11 |
| 数据导入 | `tabler-outline/database-import` | P05 |
| 数据导出 | `tabler-outline/database-export` | P12 |
| 规则与治理 | `tabler-outline/shield-check` | P06, P10 |
| LLM 能力 | `tabler-outline/robot` | P07, P09 |
| 网络与知识图谱 | `tabler-outline/network` | P04, P11 |
| 人工审核 | `tabler-outline/user-check` | P10 |

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim from `charts_index.json`) | Usage |
| ---- | -------- | ---- | ------------------------------------------------- | ----- |
| P02 | kpi_cards | `templates/charts/kpi_cards.svg` | "Pick for 4-8 standalone numeric metrics shown as overview cards (2x2 or 1x4) — exec summary opener, dashboard headline, quarterly recap, results-at-a-glance. Skip if metrics have target baselines (use bullet_chart) or single hero number (use gauge_chart)." | 展示后端、前端、数据层、测试四组规模指标 |
| P04 | process_flow | `templates/charts/process_flow.svg` | "Pick for 3-8 sequential steps connected by simple arrows — approval workflows, customer onboarding, request handling, lifecycle stages. Skip if cyclical (use circular_stages) or stages produce named outputs (use pipeline_with_stages)." | 全局六阶段治理漏斗 |
| P05 | pipeline_with_stages | `templates/charts/pipeline_with_stages.svg` | "Pick for 3-5 horizontal pipeline stages, each = title + 1-line description + output artifact, connected by arrows (data pipelines, ETL, build pipelines). Skip if any stage lacks an artifact (use process_flow or numbered_steps)." | 资源登记、批次、解析、候选池及输出物 |
| P07 | hub_spoke | `templates/charts/hub_spoke.svg` | "Pick for 1 core capability + 4-8 surrounding capabilities (platform/ecosystem); each spoke = title or title + 1-2 line description. Skip if center is a system containing parts with their own descriptions (use module_composition), or surroundings exert inward pressure on the center (use hub_inward_arrows)." | 候选脑区实体向七类提取能力发散 |
| P08 | pipeline_with_stages | `templates/charts/pipeline_with_stages.svg` | "Pick for 3-5 horizontal pipeline stages, each = title + 1-line description + output artifact, connected by arrows (data pipelines, ETL, build pipelines). Skip if any stage lacks an artifact (use process_flow or numbered_steps)." | 四步复合工作流与 Mirror 写入输出 |
| P09 | module_composition | `templates/charts/module_composition.svg` | "Pick for one parent container wrapping 3-N child module cards, each = title + 2-3 bullets — fits 'Feature X contains 3 parts, each with its own description'. Skip if source has only labels without descriptions (use numbered_steps or icon_grid)." | Mirror KG 内部三项治理机制 |
| P10 | chevron_process | `templates/charts/chevron_process.svg` | "Pick for 3-6 phase methodology with chunky arrow-chain progression and deliverables per phase. Skip for <=2 phases or non-linear flow (use process_flow), or chain ending in an aggregate outcome wedge (use chevron_chain_with_tail)." | 规则、双模型、人工三道闸门 |
| P11 | layered_architecture | `templates/charts/layered_architecture.svg` | "Pick for 3-4 horizontal architecture layers (presentation/service/data), 2-4 module cards per layer, each card = title + 1-line description (description required, even if source brief). Skip if no per-module descriptions (use icon_grid) or no horizontal layering (use module_composition)." | 实体、关系、查询与五层 Schema 的分层模型 |
| P12 | snake_flow | `templates/charts/snake_flow.svg` | "Pick for 6-10 winding sequential steps fitting a long journey/lifecycle on one slide. Skip for <=5 steps (use numbered_steps)." | Final KG 到原始资源的八步反向溯源 |
| P13 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | 六项核心创新总结 |

**No-template matches**:

- P03: 七层知识体系超过 `layered_architecture` 的 3–4 层适用范围，采用自定义七层纵向阶梯。
- P06: 分支阈值与 Tier 1/Tier 2 结构采用自定义决策树。
- P14: “已实现 / 规划中”采用非对称双区，不套用定价或密集比较模板。

**Runners-up considered**:

- `pyramid_chart` | rejected for P03: source has seven layers, exceeding the template's 3–6 layer range.
- `numbered_steps` | rejected for P04: the global governance funnel requires explicit arrows and stage boundaries.
- `icon_grid` | rejected for P07: extraction capabilities radiate from one candidate entity rather than forming unrelated parallel cards.
- `process_flow` | rejected for P10: the three gates need stronger phase bodies and per-gate deliverables.
- `timeline` | rejected for P12: traceability is a dependency chain, not time-based milestones.

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | ---------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| cover_neural_graph.png | 1536×1024 | 1.50 | 封面脑区知识网络氛围图 | Background | #1 Full-bleed background with floating title + #29 Two-stop scrim — opaque on text side, transparent on focal side + #65 Image with NO text — labels added as native SVG | ai | Generated | Abstract multi-granularity brain-region network; calm left-center space reserved for title; denser connected nodes toward the right and lower edge | none | hero_page |
| global_architecture_atmosphere.png | 1536×1024 | 1.50 | P04 全局架构视觉底层 | Diagram | #44 Background image + native network/architecture diagram + #65 Image with NO text — labels added as native SVG | ai | Generated | Wide six-stage knowledge construction landscape; source resources on left, governed knowledge core in center, exploration applications on right; clear horizontal flow zones | none | local |
| llm_capability_backdrop.png | 1536×1024 | 1.50 | P07 双 LLM 能力辐射底图 | Diagram | #44 Background image + native network/architecture diagram + #65 Image with NO text — labels added as native SVG | ai | Generated | Central candidate brain-region object with seven empty peripheral capability anchors; balanced radial composition and generous whitespace between spokes | none | local |
| mirror_write_backdrop.png | 1536×1024 | 1.50 | P08 复合工作流与 Mirror 写入底图 | Diagram | #44 Background image + native network/architecture diagram + #65 Image with NO text — labels added as native SVG | ai | Generated | Four-stage orchestration lane feeding a protected mirror knowledge store; visible batch packets and deterministic conversion boundary; no labels | none | local |
| validation_gates_backdrop.png | 1536×1024 | 1.50 | P10 三道闸门底图 | Diagram | #44 Background image + native network/architecture diagram + #65 Image with NO text — labels added as native SVG | ai | Generated | Three sequential validation gates converging toward a trusted final knowledge repository; distinct rule, model, and human-review visual motifs without text | none | local |
| final_kg_layers_backdrop.png | 1536×1024 | 1.50 | P11 Final KG 分层底图 | Diagram | #44 Background image + native network/architecture diagram + #65 Image with NO text — labels added as native SVG | ai | Generated | Layered knowledge architecture with entity, relation, query, and five isolated database partitions; explicit empty slots for editable labels | none | local |

All six rows use image-as-canvas coverage. Architecture semantics are native SVG overlays; AI output is not treated as authoritative data.

---

## IX. Content Outline

### Part 1: 问题与总体方法

#### Slide 01 - Cover

- **Layout**: Full-bleed AI background + left-aligned title in calm region
- **Title**: NeuroGraphIQ KG V3
- **Subtitle**: 多粒度脑区知识图谱构建
- **Info**: 从脑图谱资源到可探索知识图谱的全流程自动化系统 · 2026 年 8 月

#### Slide 02 - 问题、动机与项目规模

- **Layout**: Upper problem statement + 1×4 KPI strip + bottom solution thesis
- **Title**: 分散资源、粒度断裂与 LLM 风险共同阻碍脑区知识整合
- **Visualization**: kpi_cards
- **Content**:
  - 6+ 种脑图谱资源，XML / XLSX / CSV / OWL 等异构格式
  - 不同粒度脑区之间缺乏显式结构化连接
  - 项目规模：42 路由、88 服务、14 前端页面、5 Schema、59 迁移、1,173 测试函数
  - 解决方案：候选 → 校验 → LLM → Mirror → Human Review → Final 的治理漏斗

#### Slide 03 - 七层知识体系

- **Layout**: Custom seven-layer vertical stair with a right-side design principle
- **Title**: 七层知识体系把脑区事实组织为可治理、可查询、可映射的结构
- **Content**:
  - 脑区实体层 → 连接层 → 回路层 → 功能层 → 证据层 → 三元组层 → 映射层
  - 每层有明确实体边界、关系语义和溯源要求
  - 同粒度内构建，跨粒度依赖显式 Mapping

#### Slide 04 - 全局构建架构

- **Layout**: AI image-as-canvas + native six-stage process overlay + bottom write-boundary band
- **Title**: 全局架构以 Mirror KG 为安全中转，隔离自动提取与正式知识
- **Visualization**: process_flow
- **Content**:
  - 资源登记 → 批次导入 → 候选与规则校验 → LLM 提取 → Mirror 治理 → 审核晋升
  - Final KG 向图谱探索、症状查询、数据中心和离线导出供给知识
  - LLM 严禁直接写 `final_*`、自动审核或自动晋升

### Part 2: 构建与治理机制

#### Slide 05 - 数据导入与候选生成

- **Layout**: Dual-source lanes merging into Candidate Pool
- **Title**: Import Batch 统一追踪异构图谱，同时保留独立解析链路
- **Visualization**: pipeline_with_stages
- **Content**:
  - AAL3：XML、166 ROI、`aal3_xml`
  - Macro96：Excel、96 脑区、`macro96_xlsx`
  - 幂等解析、唯一索引与完整溯源字段
  - Candidate Pool 跨批次汇总，为 LLM 批处理提供基础

#### Slide 06 - 规则校验与数据增强

- **Layout**: Left 12-rule matrix + right Quality Score decision tree
- **Title**: 确定性规则先拦截硬错误，再将疑难问题交给受控增强
- **Content**:
  - 12 条规则覆盖完整性、语义 ID、唯一性、拓扑、溯源与证据
  - Quality Score：完整性 30%、溯源 20%、拓扑 20%、证据 20%、关联 10%
  - `score ≥ 80` 通过；低分进入 Tier 1 确定性修复或 Tier 2 DeepSeek 建议
  - Tier 2 仅产生 suggestions，由人工 approve / reject

#### Slide 07 - 双 LLM 与七类提取能力

- **Layout**: AI radial backdrop + native hub-and-spoke labels
- **Title**: Provider 抽象层统一 DeepSeek 与 Kimi，七类能力均受粒度边界约束
- **Visualization**: hub_spoke
- **Content**:
  - 连接、功能、回路、投射功能、回路功能、回路步骤、三元组整合
  - 三元组整合为确定性过程，不调用 LLM
  - API Key 仅在后端，前端不可见
  - 跨粒度关系必须使用显式 Mapping 表

#### Slide 08 - 复合工作流与 Mirror 写入

- **Layout**: AI pipeline backdrop + native four-step orchestration + write-chain footer
- **Title**: Pack 化编排控制成本与可恢复性，确定性转换负责写入 Mirror
- **Visualization**: pipeline_with_stages
- **Content**:
  - 连接+功能 → 回路+步骤 → 投射提取 → 三元组整合
  - `pairs_per_pack` 默认 20；Dry Run 预估 pack、token 与费用
  - Skip Existing、暂停、取消与恢复
  - `llm_extraction_runs/items` 保留 raw_response，经 `llm_to_mirror` 写入 8 张 Mirror 表

#### Slide 09 - Mirror KG 治理机制

- **Layout**: Parent container around three unequal modules
- **Title**: Mirror KG 在正式知识之前完成去重、模型共识与结构交叉验证
- **Visualization**: module_composition
- **Content**:
  - Canonical Key 写入时去重：高置信度胜出、双溯源保留
  - 已审核、已晋升、跨 atlas、跨粒度数据永不自动合并
  - DeepSeek + Kimi 双模型盲审：consensus 加速，conflict 升级
  - 回路→步骤→投射与投射→回路双向交叉验证

#### Slide 10 - 校验中心三道闸门

- **Layout**: AI gate backdrop + native three-chevron process + final convergence
- **Title**: 三道闸门缺一不可：规则提效、模型复核、专家终审
- **Visualization**: chevron_process
- **Content**:
  - 闸门 1：12 条规则；Blocker 修复，Warning 标记
  - 闸门 2：双模型盲审；consensus 绿色通道，conflict 升级
  - 闸门 3：专家终审；approve / reject / request_changes
  - 全部通过后才进入晋升队列

### Part 3: 正式知识、消费与成果

#### Slide 11 - Promotion、Final KG 与五层粒度

- **Layout**: AI layered backdrop + native entity/relation/query layers + five-schema base
- **Title**: Promotion 是唯一正式写入口，Final KG 以 Schema 级隔离保护粒度语义
- **Visualization**: layered_architecture
- **Content**:
  - 预览 → 强确认 → 执行；Mirror 8 表映射到 Final 8 表并写审计
  - 实体：BrainRegion、Function、Circuit、Step、Projection
  - 关系：12 种标准谓词；查询：`final_kg_triples`
  - 五层 Schema：macro、meso、sub、fine、molecular
  - 跨粒度仅允许 `exact_match` / `part_of` / `overlaps`

#### Slide 12 - 知识消费与全链路溯源

- **Layout**: Upper four consumption capabilities + lower eight-step snake trace
- **Title**: 每个 Final KG 事实都能沿八步链路回到原始脑图谱资源
- **Visualization**: snake_flow
- **Content**:
  - 图谱探索、症状查询、四阶段数据中心、JSONL/CSV/Neo4j 导出
  - Final fact → promotion → review → validation → extraction item → run → candidate → import/resource
  - 原始响应、模型、Prompt、批次与资源标识完整保留

#### Slide 13 - 核心创新点

- **Layout**: Six numbered takeaways with one highlighted thesis
- **Title**: 六项创新共同把 LLM 从“知识裁判”降级为“受控提取工具”
- **Visualization**: vertical_list
- **Content**:
  - 分层漏斗治理
  - Mirror KG 中转与 Canonical Key
  - 双模型盲审
  - Tier 1 + Tier 2 数据增强
  - 八步全链路溯源
  - 五层粒度隔离与显式映射

#### Slide 14 - 当前成果与下一步

- **Layout**: 7:3 asymmetric split; implemented evidence on left, roadmap on right
- **Title**: 端到端闭环已经形成，下一阶段聚焦更多粒度与图数据库协同
- **Content**:
  - 已实现：7 类提取、12 规则、增强引擎、双模型盲审、交叉验证、晋升与三元组整合
  - 已实现：14 页工作台与 1,173 测试函数
  - 下一步：更多粒度接入、图数据库同步、跨粒度映射自动化、Graph Explorer 增强

#### Slide 15 - Q&A

- **Layout**: Negative-space closing page with subtle network motif
- **Title**: 谢谢
- **Subtitle**: 欢迎围绕数据治理、LLM 可信性与多粒度映射交流

---

## X. Speaker Notes Requirements

- One note file per page, filename matching SVG basename.
- Total duration: 20–25 minutes.
- Style: formal academic defense, conclusion-first, precise technical language.
- Purpose: inform and persuade; emphasize why write boundaries and human review are necessary.
- Each note includes: timing cue, opening thesis, 2–4 explanation points, transition sentence, likely defense question where relevant.
- `notes/total.md` uses `#` headings; split note files contain no heading lines.

---

## XI. Technical Constraints Reminder

1. SVG `viewBox="0 0 1280 720"`; backgrounds are `<rect>`.
2. Text wrapping uses `<tspan>`; `<foreignObject>` is forbidden.
3. Use `fill-opacity` / `stroke-opacity`; `rgba()` is forbidden.
4. Forbidden: `<style>`, `class`, `textPath`, `animate*`, `script`, `iframe`, group opacity.
5. Chinese labels, arrows, data, statuses, and architecture semantics are native SVG, never baked into AI images.
6. AI image references use `#44` image-as-canvas and `#65` native-label overlays.
7. Use only approved colors, fonts, icons, and image assets from `spec_lock.md`.
8. XML reserved characters must be escaped; HTML named entities are forbidden.
9. Top-level visual groups require stable IDs for PowerPoint entrance animations.
