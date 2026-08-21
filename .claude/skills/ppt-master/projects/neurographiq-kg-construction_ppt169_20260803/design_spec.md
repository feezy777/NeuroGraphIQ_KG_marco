<!-- ppt-master-schema: design-spec/v1 -->
# NeuroGraphIQ KG V3 知识图谱构建过程 - Design Spec

## I. Project Information

| Item | Value |
| --- | --- |
| Project Name | neurographiq-kg-construction |
| Canvas Format | PPT 16:9 (1280×720) |
| Page Count | 14 |
| Primary Language | zh |
| Target Audience | 脑科学研究人员、知识图谱工程师、项目评审专家 |
| Communication Intent | 汇报 NeuroGraphIQ KG V3 多粒度脑区知识图谱的完整构建方法论与技术实现，展示从原始脑图谱资源到可探索知识图谱的全流程治理体系 |
| Desired Audience Outcome | 理解分层漏斗治理模型、LLM+人工双重质控机制、Mirror KG → Final KG 晋升体系，认可系统架构的严谨性 |
| Core Message / Ask / Action | 通过严格写边界约束 + Mirror KG 预正式中转 + 三道校验闸门 + 全链路溯源，实现了从原始脑图谱到结构化知识图谱的高质量构建 |
| Delivery Context | presenter-led（现场汇报演示），辅助阅读存档 |
| Artifact Afterlife | 技术文档存档、项目评审参考 |
| Reading Mode | presentation |
| Content Strategy | balanced — 基于技术文档重新组织为演示叙事结构，保持所有事实准确 |
| Design Style | 全览型技术汇报 — instructional 模式 × dark-tech 视觉风格 |
| Formula Policy | text-only |
| AI Image Acquisition Path | not applicable |
| Generation Mode | continuous |
| Spec Refinement | disabled |
| Speaker Notes | enabled — Stage 3 proactive policy default |
| Custom Animations | disabled — Stage 3 proactive policy default |
| Narration Audio | disabled — Stage 3 proactive policy default |
| Created Date | 2026-08-03 |

## II. Canvas Specification

| Property | Value |
| --- | --- |
| Format | PPT 16:9 |
| Dimensions | 1280 × 720 |
| viewBox | `0 0 1280 720` |
| Margins | 40px all sides |
| Content Area | 1200 × 640 |

## III. Visual Theme

### Theme Style

- **Mode**: instructional — 概念分解，逐步展开，每阶段一个核心概念
- **Visual style**: dark-tech — 深色画布，发光强调，几何精度，科技感
- **Theme**: 知识工程蓝图 — 在深色基底上用蓝色发光节点和连接线构建知识图谱的视觉隐喻
- **Tone**: 专业、严谨、科技感 — 像一篇 NeurIPS 风格的系统架构报告

### Color Scheme

| Role | HEX | Usage |
| --- | --- | --- |
| background | `#0D1117` | 主背景，深色画布 |
| secondary_bg | `#161B22` | 卡片、面板背景 |
| primary | `#58A6FF` | 标题、关键节点、主要强调 |
| accent | `#79C0FF` | 发光效果、高亮标记 |
| secondary_accent | `#FFA657` | 次级强调、警告/审核标记、暖色对比 |
| body_text | `#C9D1D9` | 正文，与深色背景高对比 |
| surface | `#1C2333` | 卡片抬高 |
| grid | `#212D40` | 细线网格 |
| scrim | `rgba(13,17,23,0.7)` | 文本覆盖层保护 |

### Visual Motif

节点-连接线的知识图谱隐喻贯穿全篇：封面用发光节点网络，章节页用横向连接线+节点标记，内容页用左侧竖线+节点标记当前章节。

## IV. Typography System

### Font Families

| Role | Stack |
| --- | --- |
| heading | Microsoft YaHei Bold |
| body | Microsoft YaHei Regular |
| annotation | Microsoft YaHei Light |
| mono | Consolas, monospace |

### Size Scale (px)

| Role | Size |
| --- | --- |
| cover_title | 100 |
| chapter_title | 56 |
| page_title | 40 |
| subtitle | 32 |
| body | 32 |
| annotation | 22 |
| footnote | 18 |

## V. Layout Principles

| Page | Rhythm |
| --- | --- |
| P01 | anchor |
| P02 | dense |
| P03 | anchor |
| P04 | dense |
| P05 | dense |
| P06 | dense |
| P07 | dense |
| P08 | anchor |
| P09 | dense |
| P10 | dense |
| P11 | dense |
| P12 | anchor |
| P13 | dense |
| P14 | anchor |

## VI. Icon Usage Specification

- **Library**: tabler-outline, stroke-width: 2
- **Style**: 线形图标，与 dark-tech 发光线条风格统一

## VIII. Image Resource List

No image resources required — all visuals use native SVG (charts, architecture diagrams, flow diagrams). `image_usage: none`.

## IX. Content Outline

---

### Slide 1: Cover
- **Layout**: 全屏深色画布 + 发光节点网络背景 + 居中标题
- **Title**: NeuroGraphIQ KG V3
- **Subtitle**: 多粒度脑区知识图谱构建
- **Tagline**: 从脑图谱资源到可探索知识图谱的全流程自动化系统
- **Core Message**: 一句话定义项目
- **Audience move**: 建立项目定位认知
- **Data class**: scenario

---

### Slide 2: 问题、动机与规模
- **Layout**: 左半部分三个问题卡片（红色警示），右半部分项目规模数字矩阵
- **Title**: 问题、动机与规模
- **Core Message**: 脑图谱资源分散、缺乏结构化连接、LLM需治理 — 解决方案：分层漏斗治理
- **Key points**:
  - 6+ 脑图谱资源（AAL3/Brainnetome/HCP-MMP/Julich/Allen），格式各异
  - 不同粒度脑区之间缺乏统一语义关联
  - LLM 能提取但需要治理框架防止错误传播
  - 项目规模: 42路由 · 88服务 · 14页面 · 5 Schema · 1173测试
- **Audience move**: 理解为什么需要这个系统
- **Fact IDs**: (from source document — all facts sourced from project codebase)

---

### Slide 3: 知识体系架构
- **Layout**: 左侧七层堆叠架构图，右侧五层粒度隔离表
- **Title**: 七层知识体系 × 五层粒度隔离
- **Core Message**: Final KG 形成七层结构化知识，按五个粒度 schema 物理隔离
- **Key points**:
  - 七层: 脑区实体 → 连接 → 回路 → 功能 → 证据 → 三元组 → 映射
  - 五层: macro_clinical / meso_anatomical / sub_connectivity / fine_cyto / molecular_attr
  - 跨粒度显式 Mapping (exact_match/part_of/overlaps)，禁止名称相似度合并
- **Audience move**: 建立知识图谱的整体认知框架

---

### Slide 4: 构建流水线总览
- **Layout**: 水平五阶段漏斗流程图 + 底部写边界矩阵表
- **Title**: 构建流水线与治理约束
- **Core Message**: 五阶段漏斗（导入→候选→校验增强→LLM提取→审核晋升），每层严格写边界
- **Key points**:
  - 流水线: 资源登记 → 批次导入 → 原始解析 → 候选生成 → 规则校验 → LLM提取 → Mirror KG → 校验中心 → 人工审核 → 晋升 → Final KG
  - 核心约束: LLM不写final_* / 人工审核是唯一闸门 / Promotion只写final_*
- **Audience move**: 理解端到端数据流和治理边界

---

### Slide 5: 资源导入与候选生成
- **Layout**: 左右双列 — AAL3 链路 (XML→166ROI) 和 Macro96 链路 (XLSX→96脑区)
- **Title**: 第一阶段：资源导入与候选生成
- **Core Message**: 双链路独立导入，幂等解析，完整溯源
- **Key points**:
  - AAL3: XML → raw_aal3_region_labels (166) → generate-candidates
  - Macro96: XLSX → raw_macro96_region_rows (96) → generate-macro96-candidates
  - 导入批次为核心追踪单元，解析器兼容性检查，回滚机制
- **Audience move**: 理解数据如何进入系统

---

### Slide 6: 规则校验与数据增强
- **Layout**: 左上 12 规则校验表 + 右上 Quality Score 加权图 + 底部 Tier1/Tier2 增强流程
- **Title**: 规则校验与数据增强引擎
- **Core Message**: 确定性规则 + 自动质量评分 + 分层增强修复
- **Key points**:
  - 12条电路校验规则 (Blocker/Warning)
  - Quality Score 0-100: 完整性30% + 溯源20% + 拓扑20% + 证据20% + 关联10%
  - Tier 1: 确定性自动修复（零LLM成本） / Tier 2: DeepSeek增强 + 人工approve
- **Audience move**: 理解质量控制的第一道防线

---

### Slide 7: LLM 知识提取
- **Layout**: 顶部双LLM架构图 + 中部7种提取能力树状图 + 底部复合工作流
- **Title**: LLM 知识提取：双模型驱动的知识关系构建
- **Core Message**: DeepSeek+Kimi 双模型，7种提取能力，复合工作流编排
- **Key points**:
  - Provider 抽象层: API Key 前端不可见，运行时切换
  - 7种提取: 连接/功能/回路/回路步骤/投射功能/回路功能/三元组整合
  - 复合工作流: Pack机制 → DryRun预览 → SkipExisting → 暂停/恢复
  - 同粒度操作，跨粒度需Mapping表
- **Audience move**: 理解 LLM 如何参与知识构建

---

### Slide 8: Mirror KG 治理
- **Layout**: 三大治理机制卡片 — 去重合并 / 双模型盲审 / 交叉验证
- **Title**: Mirror KG：预正式知识中转层
- **Core Message**: 写入时去重合并 + 双模型独立盲审 + 确定性交叉验证
- **Key points**:
  - Canonical Key 体系: 6类实体各有合并key，高置信度胜出，双溯源保留
  - 双模型盲审: DeepSeek+Kimi独立审核，consensus→加速，conflict→人工裁决
  - 交叉验证: 回路↔投射双向确定性验证（不调LLM）
- **Audience move**: 理解 Mirror KG 的核心治理价值

---

### Slide 9: 校验中心
- **Layout**: 三列并行闸门图 + 底部汇聚到 Final KG
- **Title**: 校验中心：数据进入正式库前的三道闸门
- **Core Message**: 规则校验→大模型校验→人工审核，三道全过才可晋升
- **Key points**:
  - 闸门1: 12规则 + Tier1自动修复 + Tier2 LLM增强
  - 闸门2: DeepSeek+Kimi双模型盲审
  - 闸门3: 专家终审 (approve/reject/request_changes)
  - 设计原则: 前两道自动化 + 最后一道人工 = 效率与质量平衡
- **Audience move**: 理解质量保障的多层防御体系

---

### Slide 10: 晋升与 Final KG
- **Layout**: 左侧 Mirror→Final 映射表 + 右侧三元组三层模型图 + 底部12谓词表
- **Title**: 晋升与 Final KG：唯一事实库
- **Core Message**: Mirror→Final 晋升 + Triple Consolidation → 三元组统一查询面
- **Key points**:
  - 8表一一映射，强确认机制（预览→确认→执行）
  - 三层模型: 实体层→关系层(12谓词)→统一查询层(final_kg_triples)
  - Triple Consolidation 为确定性转换（不调LLM）
- **Audience move**: 理解最终知识图谱的数据模型

---

### Slide 11: 知识消费与全链路溯源
- **Layout**: 上半部四个消费面卡片 + 下半部7步溯源链
- **Title**: 知识消费与全链路溯源
- **Core Message**: 图谱探索/症状查询/数据中心/离线导出 + 7步回溯到原始出处
- **Key points**:
  - 消费: Graph Explorer / 症状查询 / DataCenter / 离线导出(JSONL+CSV+Neo4j)
  - 溯源: Final KG → promotion → review → rule_validation → llm_item(raw_response) → llm_run → candidate_pool → import_batch → resource
- **Audience move**: 理解知识的可消费性和可追溯性

---

### Slide 12: 核心创新点
- **Layout**: 2×3 六卡片网格
- **Title**: 核心创新点
- **Core Message**: 六大创新构筑系统核心竞争力
- **Key points**:
  - 分层漏斗治理 (6阶段，写边界明确)
  - Mirror KG中转层 (去重合并+双溯源)
  - 双模型盲审 (DeepSeek+Kimi独立审核)
  - 数据增强引擎 (Tier1零成本+Tier2 LLM)
  - 全链路溯源 (7步回溯)
  - 五层粒度隔离 (PostgreSQL schema级)
- **Audience move**: 记住系统的核心差异化价值

---

### Slide 13: 当前状态与规划
- **Layout**: 左侧已完成清单(绿色) + 右侧规划中清单(橙色) + 底部指标条
- **Title**: 当前状态与下一步规划
- **Core Message**: 已完成端到端闭环，规划更多粒度和能力扩展
- **Key points**:
  - 已完成: 端到端闭环 · 7种LLM提取 · 12规则+增强 · 双模型盲审 · 14页工作台 · 1173测试
  - 规划中: 更多粒度接入 · Neo4j同步 · 跨粒度映射自动化 · Graph Explorer增强
- **Audience move**: 了解项目当前进度和未来方向

---

### Slide 14: 感谢关注
- **Layout**: 深色画布 + 微光节点背景 + 居中文字
- **Title**: 感谢关注
- **Subtitle**: 欢迎提问与交流
- **Core Message**: 结束页
- **Audience move**: 自然结束，开放问答

## X. Speaker Notes Plan

- **Generation**: enabled
- **Content strategy**: 每页核心观点的展开说明，帮助演讲者脱稿讲解
- **Filename policy**: `notes/<slide_number>_<title_slug>.md`
- **Notes style**: 要点式备注，每条不超过2行，面向现场演讲节奏
