# NeuroGraphIQ KG V3 Optimization - Design Spec

> Human-readable design narrative. Machine-readable contract: `spec_lock.md`. On divergence, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | NeuroGraphIQ KG V3 — 知识图谱构建过程学术汇报（优化版） |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 15 |
| **Design Style** | B) General Consulting + 学术极简科技风 |
| **Target Audience** | 脑科学、知识工程与可信 AI 领域专家 |
| **Use Case** | 20–25 分钟学术汇报；优化自桌面 18 页原版 |
| **Created Date** | 2026-08-03 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 左右 56px，上 42px，下 34px |
| **Content Area** | 1168×644px |

---

## III. Visual Theme

### Theme Style

- **Style**: 学术极简、结论先行、图示承载结构
- **Theme**: Light theme
- **Tone**: 严谨、克制、可信、系统工程感

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#F7FAFC` | 页面主背景 |
| **Secondary bg** | `#EDF2F7` | 分区与信息带 |
| **Primary** | `#17324D` | 标题、主结构、主连接 |
| **Accent** | `#1F9FB5` | 数据流、重点强调 |
| **Secondary accent** | `#C05640` | 风险、人工闸门、警示 |
| **Body text** | `#243447` | 正文 |
| **Secondary text** | `#5A6A7A` | 注释 |
| **Tertiary text** | `#8492A0` | 页脚 |
| **Border/divider** | `#CBD5E0` | 边框分隔 |
| **Success** | `#2F855A` | 通过、晋升、Final |
| **Warning** | `#C05640` | Blocker / Conflict |

### AI Image Strategy

- **Image Rendering**: vector-illustration
- **Image Palette**: cool-corporate
- **Information rule**: AI 图只提供无文字结构底图；中文标签、连线、状态、数据一律由 SVG 叠加。

---

## IV. Typography System

**Typography direction**: 统一无衬线；标题与正文同族、靠字重区分。

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei"` | `Arial` | `sans-serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `"Microsoft YaHei"` | `Arial` | `sans-serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Microsoft YaHei, Arial, sans-serif`
- Body: `Microsoft YaHei, PingFang SC, Arial, sans-serif`
- Emphasis: `Microsoft YaHei, Arial, sans-serif`
- Code: `Consolas, Courier New, monospace`

**Baseline**: Body = 20px.

| Purpose | Size | Weight |
| ------- | ---- | ------ |
| Cover title | 56px | Bold |
| Page title | 34px | Bold |
| Hero number | 36px | Bold |
| Subtitle | 24px | SemiBold |
| Body | 20px | Regular |
| Annotation | 14px | Regular |
| Footnote | 12px | Regular |

**Formula rendering policy**: `text-only`

---

## V. Layout Principles

### Page Structure

- Header 84px；Content ~520px；Footer 32px
- 架构页优先图示；说明文字围绕图组织
- 避免每页都是多卡片网格；`breathing` 页用留白与单结论块

### Spacing

| Element | Value |
| ------- | ----- |
| Safe margin | 56 / 42 |
| Block gap | 28 |
| Icon-text gap | 12 |
| Card radius | 8 |
| Card padding | 22 |

---

## VI. Icon Usage Specification

- Library: `tabler-outline`
- Stroke width: 2
- Usage: `<use data-icon="tabler-outline/icon-name" .../>`

| Purpose | Icon | Pages |
| ------- | ---- | ----- |
| 脑/知识 | brain | P01, P03, P05 |
| 数据层 | database | P07, P14 |
| 导入 | database-import | P08 |
| 导出 | database-export | P12 |
| 治理 | shield-check | P04, P09, P11 |
| LLM | robot | P10 |
| 图谱 | network | P07, P12 |
| 审核 | user-check | P11 |
| 流程 | git-branch | P06, P08 |
| 分层 | stack-2 | P05 |
| 校验 | checklist | P09 |
| 搜索 | search | P12 |
| 锁定 | lock | P04 |
| 路径 | route | P13 |
| 通过 | circle-check | P11, P15 |
| 警告 | alert-triangle | P09 |
| 文献 | books | P13 |
| 设置 | settings | P14 |
| 拓扑 | topology-star | P07 |
| 过滤 | filter | P09 |
| 箭头 | arrow-right | P06–P11 |

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim from `charts_index.json`) | Usage |
| ---- | -------- | ---- | ------------------------------------------------- | ----- |
| P04 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | 九项原则压缩为两组要点（前5+后4） |
| P05 | layered_architecture | `templates/charts/layered_architecture.svg` | "Pick for 3-4 horizontal architecture layers (presentation/service/data), 2-4 module cards per layer, each card = title + 1-line description (description required, even if source brief). Skip if no per-module descriptions (use icon_grid) or no horizontal layering (use module_composition)." | 七层知识体系（扩展为七行自定义） |
| P06 | funnel_chart | `templates/charts/funnel_chart.svg` | "Pick for 3-5 sequential conversion stages with monotonic drop-off. Skip if flow branches/merges (use sankey_chart) or steps don't entail loss (use process_flow)." | 五阶段质量漏斗 |
| P07 | process_flow | `templates/charts/process_flow.svg` | "Pick for 3-8 sequential steps connected by simple arrows — approval workflows, customer onboarding, request handling, lifecycle stages. Skip if cyclical (use circular_stages) or stages produce named outputs (use pipeline_with_stages)." | 全局治理流水线 |
| P08 | pipeline_with_stages | `templates/charts/pipeline_with_stages.svg` | "Pick for 3-5 horizontal pipeline stages, each = title + 1-line description + output artifact, connected by arrows (data pipelines, ETL, build pipelines). Skip if any stage lacks an artifact (use process_flow or numbered_steps)." | 导入→解析→候选 |
| P09 | numbered_steps | `templates/charts/numbered_steps.svg` | "Pick for 3-6 horizontal sequential steps with numeric emphasis — how-it-works section, getting-started guide, methodology overview, implementation phases. Skip if steps need connector arrows (use process_flow) or named output artifacts (use pipeline_with_stages)." | 规则硬校验 + Tier1/Tier2 |
| P10 | hub_spoke | `templates/charts/hub_spoke.svg` | "Pick for 1 core capability + 4-8 surrounding capabilities (platform/ecosystem); each spoke = title or title + 1-2 line description. Skip if center is a system containing parts with their own descriptions (use module_composition), or surroundings exert inward pressure on the center (use hub_inward_arrows)." | LLM 提取能力 + Mirror 缓冲 |
| P11 | chevron_process | `templates/charts/chevron_process.svg` | "Pick for 3-6 phase methodology with chunky arrow-chain progression and deliverables per phase. Skip for <=2 phases or non-linear flow (use process_flow), or chain ending in an aggregate outcome wedge (use chevron_chain_with_tail)." | 三道闸门→晋升 |
| P12 | icon_grid | `templates/charts/icon_grid.svg` | "Pick for 4-9 parallel features/capabilities/services as icon cards — feature grid, service lineup, benefits matrix, brand values, product highlights. Skip for sequential ordering (use numbered_steps) or hierarchical layers (use pyramid_chart)." | 四类知识消费入口 |
| P13 | snake_flow | `templates/charts/snake_flow.svg` | "Pick for 6-10 winding sequential steps fitting a long journey/lifecycle on one slide. Skip for <=5 steps (use numbered_steps)." | 八步反向溯源 |
| P14 | kpi_cards | `templates/charts/kpi_cards.svg` | "Pick for 4-8 standalone numeric metrics shown as overview cards (2x2 or 1x4) — exec summary opener, dashboard headline, quarterly recap, results-at-a-glance. Skip if metrics have target baselines (use bullet_chart) or single hero number (use gauge_chart)." | 工程规模指标（附口径说明） |

**Runners-up considered**:

- `pyramid_chart` | rejected for P05: seven layers exceed 3–6 range; custom ladder preferred.
- `process_flow` | rejected for P06: funnel drop-off/quality rise is the message, not plain steps.
- `module_composition` | rejected for P10: spokes radiate from Mirror/LLM hub better than parent container.

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| cover_neural_graph.png | 1536x1024 | 1.50 | 封面神经图谱氛围 | Background | #1 full-bleed background with floating title + #29 two-stop scrim | user | Existing | Neural graph atmosphere, calm left third for title | none | hero_page |
| global_architecture_atmosphere.png | 1536x1024 | 1.50 | 全局架构底图 | Diagram | #44 background image + native network/architecture diagram | user | Existing | Unlabeled multi-stage pipeline structure | none | local |
| final_kg_layers_backdrop.png | 1536x1024 | 1.50 | 知识层氛围 | Diagram | #44 background image + native network/architecture diagram | user | Existing | Stacked layer blocks without labels | none | local |
| llm_capability_backdrop.png | 1536x1024 | 1.50 | LLM 能力辐射底图 | Diagram | #44 background image + native network/architecture diagram | user | Existing | Hub with surrounding nodes, no text | none | local |
| mirror_write_backdrop.png | 1536x1024 | 1.50 | Mirror 治理底图 | Diagram | #44 background image + native network/architecture diagram | user | Existing | Buffer zone structure, no text | none | local |
| validation_gates_backdrop.png | 1536x1024 | 1.50 | 三道闸门底图 | Diagram | #39 background image + flow nodes drawn over the scene | user | Existing | Three sequential gate frames, no text | none | local |

> Source deck 48×48 icons are **not** used as page imagery. Only text-free architecture backdrops above are approved for SVG embedding.

---

## IX. Content Outline

### Part A — 开场与命题

#### Slide 01 - Cover
- **Layout**: Full-bleed atmosphere + left title block
- **Title**: NeuroGraphIQ KG V3
- **Subtitle**: 多粒度脑区知识图谱构建过程
- **Thesis**: 让 LLM 成为受控提取工具，而不是知识终审者
- **Info**: 学术汇报 · 2026年8月

#### Slide 02 - 问题与核心命题
- **Layout**: 左问题、右命题；底部边界硬约束
- **Title**: 多源脑图谱知识为何难以可信沉淀
- **Content**:
  - 问题：多源异构、跨粒度冲突、LLM 幻觉、审核黑盒
  - 命题：LLM 只做受控提取；Final KG 只接收经审核知识
  - 边界：LLM 不写 `final_*`；跨粒度禁止隐式合并

#### Slide 03 - 项目定位与目标
- **Layout**: 三目标列 + 底部五级粒度条
- **Title**: 项目定位：多粒度脑区知识基础设施
- **Content**:
  - 目标：多粒度图谱；任务：全链路构建与治理；架构：五级粒度扩展
  - 已落地：macro_clinical（AAL3 / Macro96）

### Part B — 方法与体系

#### Slide 04 - 九项可信原则
- **Layout**: 左 5 条 / 右 4 条（vertical_list 结构）
- **Title**: 九项硬约束：可信知识构建底线
- **Content**: LLM 隔离、统一入口、双重审核、正式库纯净、全链路溯源、粒度隔离、显式映射、输出留痕、全程日志

#### Slide 05 - 七层知识体系
- **Layout**: 纵向七层阶梯
- **Title**: 七层知识体系：从实体到可查询语义
- **Content**: 实体 → 连接 → 回路 → 功能 → 证据 → 三元组 → 映射

#### Slide 06 - 五阶段漏斗
- **Layout**: 横向五阶段漏斗 + 底部结论
- **Title**: 五阶段构建漏斗：数据收敛，质量跃升
- **Content**: 导入解析 → 候选生成 → 校验增强 → LLM 提取 → 审核晋升
- **Note**: 合并原版 Slide 7/8，消除重复

#### Slide 07 - 全局架构
- **Layout**: 架构底图 + SVG 标注流水线与治理边界
- **Title**: 系统全局架构：生产—治理—消费闭环
- **Content**: Raw/Staging → Candidate → LLM/Mirror → Review → Final → 消费侧

### Part C — 构建流程

#### Slide 08 - 导入与候选
- **Layout**: 五步流水线
- **Title**: 资源导入与候选生成
- **Content**: 资源登记、双轨文件、批次审计、单向解析、溯源候选

#### Slide 09 - 规则校验与增强
- **Layout**: 左硬校验 / 右双层增强
- **Title**: 规则校验与分层增强
- **Content**: 12 条确定性规则；质量分 0–100；Tier1 规则修复；Tier2 LLM 建议需复核

#### Slide 10 - LLM 与 Mirror
- **Layout**: 左提取能力 / 右 Mirror 治理
- **Title**: LLM 提取与 Mirror KG 预治理
- **Content**: Provider 抽象、七类关系、异步工作流；写入去重、双模型盲审、回路-投射交叉验证

#### Slide 11 - 闸门与晋升
- **Layout**: 三闸门 chevron + 晋升三步骤
- **Title**: 三道闸门与知识晋升
- **Content**: 规则 → 模型盲审 → 专家终审；预览→确认→执行；标准三元组与 12 谓词

### Part D — 应用、证据与收束

#### Slide 12 - 知识消费
- **Layout**: 2×2 入口
- **Title**: 知识消费：从图谱到可操作洞察
- **Content**: Data Center、Graph Explorer、Symptom Query、Export

#### Slide 13 - 八步溯源
- **Layout**: 八节点反向链路
- **Title**: 八步全链路溯源
- **Content**: Final fact → Promotion → Review → Validation → Extraction item → Candidate → Import batch → Resource
- **Fix**: 原版“七步”改为八节点，与实际链路一致

#### Slide 14 - 技术架构与规模
- **Layout**: 技术栈三列 + KPI；脚注口径
- **Title**: 技术架构与工程规模
- **Content**: FastAPI / React+TS / PostgreSQL Schema 隔离
  - 指标：5 粒度、AAL3 166 / Macro96 96、12 规则、7 类 LLM 提取、42 路由、88 服务、1173 测试
  - 表述修正：删除“零故障”“响应极快”等绝对化用语；注明“仓库统计口径，随迭代变化”

#### Slide 15 - 结论与 Q&A
- **Layout**: 三点结论 + Q&A
- **Title**: 结论与展望
- **Content**:
  1. 受控 LLM + Mirror 缓冲是可信构建关键
  2. 八步溯源保证来源可查、过程可溯
  3. 宏观临床层已落地，多粒度扩展可继续推进
  - Q & A

---

## X. Speaker Notes Requirements

- Filename matches SVG: `01_cover.md` …
- Style: conversational academic; total ~20–25 min
- Master file: `notes/total.md` with `#` headings per page

---

## XI. Technical Constraints Reminder

1. viewBox `0 0 1280 720`
2. No `rgba()`, `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`
3. No `<g opacity>`
4. Icons only from approved inventory
5. AI images carry no text/labels/arrows semantics
6. Chinese / numbers / predicates / schema names only in SVG text
