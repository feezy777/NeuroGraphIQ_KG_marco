# 论文检索与文献佐证工作台设计（Phase B）

> 状态：设计方案（待用户更新软件后讨论确认）
> 日期：2026-08-07

## 1. 功能定位

把“找论文 + 截取文献相关部分 + 挂接证据”做成工作台内闭环：

```text
选择对象 → 自动打包信息检索论文 → 浏览论文(可点击链接)
  → LLM 截取相关段落 → 人工确认/编辑 → 写入 Mirror 证据
  → 证据方向与验证状态 → 置信度上调候选(上限0.85) → 人工/双模型确认后生效
```

## 2. 已完成的现有基础（后端已验证）

- 迁移 `20260807_paper_evidence.sql`：`mirror_evidence_records` 增加证据方向、验证状态、PMID/DOI/标题/期刊/年份、suggested_confidence、置信度调整状态等字段；
- 迁移 `20260807_paper_evidence_target_types.sql`：证据目标类型与 evidence_type 约束放宽（支持 projection_function / circuit_function / region_function / paper_verification）；
- 服务 `backend/app/services/paper_evidence_service.py`：
  - Europe PMC 检索（短语优先、拆词 AND 兜底）；
  - PMID 真实性校验；
  - 对象信息打包（术语 + 简短区域名）；
  - 证据挂接（写 mirror_evidence_records + 更新业务对象 evidence_text，附 [论文证据] 段落与 PubMed/DOI 链接）；
- 接口：`POST /api/ontology/evidence/search`、`POST /api/ontology/evidence/attach`（reviewer 权限）；
- 已验证：真实检索返回 PMID，挂接后 evidence_text 含可点击链接。

## 3. 工作台功能设计

### 3.1 入口

方案 A（推荐）：本体中心新增“文献证据”主 Tab，可从任意对象行“查论文”跳转并自动带入对象上下文。
方案 B：数据中心新增子 Tab。
方案 C：独立页面。

### 3.2 检索面板

- 自由检索框 + 对象打包检索（自动组装 query：术语 + 源/靶区域 + 类型；长区域名自动剔除，短语命中失败自动拆词）；
- 结果卡片：标题、作者、期刊、年份、PMID/DOI、摘要预览、**PubMed/DOI 可点击链接**；
- 筛选：OA 全文可用、年份范围、按相关度排序；
- 缓存检索结果，避免重复请求。

### 3.3 段落截取（LLM 辅助）

- Europe PMC 摘要始终可用；开放获取（OA）文章可拉全文 XML；
- DeepSeek（复用现有 provider/配置）阅读摘要或全文，输出闭集结构：
  - direction：supports / partial / contradicts / not_found；
  - relevant_passage：原文相关段落（可多段，截取到引用句）；
  - reason：一句话佐证理由；
  - confidence：0–1；
- Pydantic 严格校验、单篇失败不拖垮批次、保留 model/prompt_version/raw_response/parse_status/retry_count；
- 段落可人工编辑后再确认（避免 LLM 断章取义）。

### 3.4 证据挂接

- 写入 `mirror_evidence_records`（evidence_type=paper_verification、PMID/DOI/标题/期刊/年份、evidence_text=截取段落、方向、verification_status=pending）；
- 业务对象 `evidence_text` 追加 `[论文证据] 段落 (PMID:xxx, DOI:xxx)`，链接可点击；
- 只有 verification_status=verified（人工或双模型确认）后，才允许写入 suggested_confidence 并作为上调候选，上限 0.85。

### 3.5 批量任务

- 选对象集合（筛选结果 / 连接池 / 勾选行）→ 批量“检索 + 截取 + 挂接”；
- 任务面板显示：扫描数 / 成功 / 失败 / 跳过、当前进度、预算上限、限速、暂停/继续；
- 复用 DeepSeek 配置化并发/退避参数。

### 3.6 审核与置信度

- 待确认队列：direction=support/partial 且未确认的证据；
- 人工确认或双模型一致 → verified → 应用置信度调整；
- contradicts / not_found 不触发调整。

### 3.7 展示

- 数据中心对象详情“证据面板”：论文链接、方向、状态、截取段落、置信度调整记录；
- 验证中心：EV_REFERENCE_INVALID / EV_DIRECTION_INVALID / EV_VERIFICATION_PENDING / EV_EVIDENCE_MISSING 规则展示；
- 本体中心“文献证据”Tab：检索、结果、待确认队列、批量任务、覆盖率统计。

## 4. 需要新增的组件

- `paper_evidence_service`：增加全文拉取（Europe PMC fullTextXML）、LLM 段落截取（复用残差对齐的结构化输出模式）；
- 批量任务表 `paper_evidence_tasks`（可选：用现有 unified_tasks 扩展）；
- 前端：EvidenceDialog（检索→选择→截取→确认→挂接）、文献证据 Tab、待确认队列、任务面板；
- EV_* 校验规则接入 mirror_rule_validation_service。

## 5. 待确认问题（更新后讨论）

1. 入口位置：本体中心新 Tab / 数据中心子 Tab / 独立页面？
2. 全文范围：只截 OA 全文，还是摘要优先（付费文献无全文）？
3. 截取粒度：按段落返回还是只返回引用句 + 摘要？
4. 首批试点：按原 spec 从投影功能 200 条开始，还是你指定对象集合？
5. 是否需要任务成本/历史统计展示？
6. 置信度调整触发：人工确认即可，还是必须双模型一致？
