# Plan: 论文证据提取 — 召回与人工审核链路改造

**Source PRD**: `.claude/prds/paper-evidence-recall-rework.prd.md`
**Selected Milestone**: M1–M4 全部(用户确认全量一次做)
**Complexity**: Large

## Summary

改造论文证据链路的两个断点:① 提取命中率≈0 —— 原文验证从「逐字闸门」改为「exact/normalized/similarity 三级 + 模糊段落定位」,统一 HTML 清理与提取/入库同源;② 多选只送单篇 —— 前端从循环调单篇接口改为批量接口,并新增「提取前语义筛选」与「存在性佐证模式」两条能力。未验证片段保留展示,人工审核闭环不变,治理边界(置信度公式、contradicts/mixed 进验证中心)不动。

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| 验证纯函数 | `backend/app/services/paper_evidence_service.py:139-176` | `verify_passage_against_source` / `verify_and_locate_passage` 返回 `(bool, method)` 元组,无副作用,便于单测 |
| 验证测试 | `backend/tests/test_paper_evidence_v4.py` / `test_paper_evidence_integrity.py` | 对 verify/coverage/aggregate 纯函数直接断言;mock `get_llm_provider` 与 httpx |
| LLM 调用+重试 | `paper_evidence_service.py:1617-1665` | `complete_json` 优先 → 解析失败降级 `complete_text` → 3 次重试,`parse_status`/`retry_count` 返回 |
| 设置项 | `backend/app/config.py:27-37` | pydantic settings 字段,`paper_*` 前缀,`get_settings()` 读取 |
| 错误分类 | `paper_evidence_service.py:3255-3267` | `_classify_error(exc, stage)` + `BATCH_RETRYABLE_CODES` 集合 |
| schema 兼容 | `backend/app/services/ontology_residual_schemas.py` | 新字段一律 `| None = None` / 默认值,旧响应不破坏 |
| 前端候选→WorkbenchPassage 映射 | `frontend/src/pages/data-center/EvidenceReviewModal.tsx:350-372`(`loadTaskQueue`) | 候选 passages 平铺映射为 `WorkbenchPassage` 的既有转换,复用 |
| 前端 API 封装 | `frontend/src/api/endpoints.ts:5422-5433` | `extractSelectedPaperEvidence` 已封装,仅需补 `mode` 与响应字段 |

## Files to Change

| File | Action | Why |
|---|---|---|
| `backend/app/services/paper_evidence_service.py` | UPDATE | 验证分级、模糊定位、同源、语义筛选、mode 贯穿、判定维度 |
| `backend/app/services/paper_fetch_service.py` | UPDATE | HTML 实体/标签清理工具 + 应用 |
| `backend/app/services/oa_xml_parser.py` | UPDATE | 段落文本 HTML 实体解码 |
| `backend/app/services/evidence_target_adapter.py` | UPDATE | `build_retrieval_context`/`build_search_query` 加 mode |
| `backend/app/services/paragraph_retrieval.py` | UPDATE | top_k/window 参数化、abstract 段落强制入窗 |
| `backend/app/services/ontology_residual_schemas.py` | UPDATE | `PaperMultiPassageExtraction` 加可选 `evidence_dimension` |
| `backend/app/config.py` | UPDATE | 语义筛选阈值等新设置 |
| `backend/app/routers/ontology.py` | UPDATE | `/evidence/search`、`/evidence/extract`、`/evidence/extract-selected` 传 mode |
| `frontend/src/api/endpoints.ts` | UPDATE | `extractSelectedPaperEvidence` body 加 mode、响应类型 |
| `frontend/src/pages/data-center/EvidenceReviewModal.tsx` | UPDATE | `extractSelected` 切批量接口、模式切换 UI |
| `frontend/src/pages/data-center/evidence-workbench/CreateBatchTaskDialog.tsx` | UPDATE | 佐证模式选项 |
| `frontend/src/pages/data-center/evidence-workbench/PassageEvidenceCard.tsx` | UPDATE | similarity/未验证/evidence_dimension 标签 |
| `frontend/src/pages/data-center/evidence-workbench/types.ts` | UPDATE | `evidence_dimension`、`semantic_relevance` 类型 |
| `backend/tests/test_paper_evidence_v4.py` 等 | UPDATE | 新增用例;必要时新增 `test_paper_evidence_semantic.py` |

## Tasks

### M1 后端验证链路改造(分级验证 + 模糊定位 + 文本清理 + 同源)

**Task 1.1: HTML 清理与摘要规范化**
- **Action**: `paper_fetch_service.py` 新增 `clean_html_text(text)`(`html.unescape` + 标签剥离 + 空白归一),应用到 `fetch_paper_metadata` 的 abstractText;`paper_evidence_service._search`/`verify_paper` 的 abstractText 同样清理;`oa_xml_parser._node_text` 输出后 unescape。
- **Mirror**: `oa_xml_parser.py:68` 的空白归一写法;`fetch_plain_fulltext` 的标签剥离。
- **Validate**: 新增单测:含 `&amp;`/`<p>`/`<i>` 的摘要清理后与 DeepSeek 复制文本匹配。

**Task 1.2: 验证分级(exact/normalized/similarity)**
- **Action**: `verify_passage_against_source` 增加 `similarity` 分支:token 级 Jaccard ≥ 阈值(默认 0.75)或 `difflib.SequenceMatcher` ratio ≥ 0.8 → 返回 `("similarity", method)`。阈值提为模块常量(可被单测覆盖),`attach_evidence` 的 `_verify_passages` 与提取共用同一函数。
- **Mirror**: 现有 `verify_passage_against_source` 签名不变,只加方法名分支。
- **Validate**: 单测:轻微改写(缩写/冠词/标点)走 similarity;无关文本不通过。

**Task 1.3: 段落定位模糊化(去 paragraph_id 硬依赖)**
- **Action**: `_verify_extraction_passages` 逻辑改为:① `paragraph_id` 精确命中 → 段落内匹配(现状);② 未命中 → 对全部段落按相似度(复用 Task 1.2 的相似度函数)定位最佳段,相似度 ≥ 阈值(默认 0.6)才记 verified(similarity);③ 低于阈值 → `source_verified=false`。`source_locator` 记录定位到的段落 locator。
- **Mirror**: `locate_passage`(paper_evidence_service.py:151)的段落定位结构。
- **Validate**: 单测:模型给出错误/编造 paragraph_id 但 passage 真实存在 → 仍 verified(similarity);无关 passage → 未验证。

**Task 1.4: 提取/入库同源**
- **Action**: `attach_evidence` 的 `_load_source(pmid)` 改为优先从 `paper_sources`/`paper_passages` 取已存段落文本(按 PMID 查 paper_source,拼接段落);无缓存才回退现逻辑(网络拉取)。确保提取时 verified 的片段在 attach 时用同一份文本验证。
- **Mirror**: `ensure_paper_cached`(paper_fetch_service.py:142)的缓存优先模式。
- **Validate**: 集成测试:先 extract 后 attach 同一 PMID,验证方法一致,不再二次拒绝。

**Task 1.5: 召回扩大**
- **Action**: `build_windows` 增加 `top_k=40, window=2` 默认(参数化);`build_windows` 调用方(router extract、`extract_candidates_for_target`、`_process_batch_item_v2`)统一传参;摘要段落(`abstract_p001`)无条件进入窗口首位(`max_input_chars=24000` 预算截断逻辑保留)。
- **Mirror**: `build_windows` 现有签名,只改默认值与调用点。
- **Validate**: 单测:摘要仅命中(低分)时窗口仍含 abstract 段落;窗口数量 = 40。

### M2 语义筛选 + 存在性模式

**Task 2.1: mode 贯穿检索与提取链路**
- **Action**: `build_retrieval_context(session, target_type, target_id, mode="function")` 与 `build_search_query` 加 mode;`mode="existence"` 时 `function_terms`/`function_synonyms` 置空(检索式、段落评分、论文排序均不用功能词),`relation_keywords` 保留。调用点全量更新:`/evidence/search`、`/evidence/extract`、`/evidence/extract-selected`(schema 已有 mode)、`extract_candidates_for_target`(新增 mode 参数)、`_process_batch_item_v2`(从 task 表读 mode,替换硬编码 `"function"` @ paper_evidence_service.py:2552)。
- **Mirror**: `pack_target_info` 的 mode 分支(service:617)作为行为参照。
- **Validate**: 单测:existence 模式下 context 无 function_terms、query 无功能词;批量任务 mode 正确传递。

**Task 2.2: 提取前语义筛选**
- **Action**: 新增 `semantic_filter_papers(papers, context)` —— DeepSeek 批量对候选论文(title+abstract)输出 `[{pmid, relevance: 0-1, reason}]`;relevance < `settings.paper_semantic_threshold`(默认 0.4;=0 关闭筛选)的论文跳过提取,记录 `semantic_relevance`/`semantic_skip_reason` 进 candidate/paper_json。接入 `extract_candidates_for_target`(筛选后仅对通过者提取)与 `_process_batch_item_v2`。复用 `extract_passage_from_paper` 的重试/解析模式(新 schema `PaperRelevanceBatch` 于 `ontology_residual_schemas.py` 新增,字段可空)。
- **Mirror**: `_extract_from_paper_with_retry`(service:2326)的重试封装;`_classify_error` 记录失败。
- **Validate**: 单测(mock provider):低相关论文被跳过且原因落库;阈值=0 时全量提取;`extract_candidates_for_target` 返回结果含 semantic_relevance。

**Task 2.3: 存在性/功能性判定维度**
- **Action**: `PaperMultiPassageExtraction` 加可选 `evidence_dimension: "existence"|"function"|"mixed"|None`;`extract_passage_from_paper` prompt 增加规则:对连接/回路类 claim,显式判断论文证明的是「对象存在」还是「功能」;response 透传,passages 亦带 `evidence_dimension`(默认取 overall)。
- **Mirror**: `_normalize_extraction_payload` 的容忍式字段规范化(service:1272)。
- **Validate**: 单测:prompt 含 dimension 要求;缺省时默认值兼容旧响应。

### M3 前端多选接线 + 模式切换 UI

**Task 3.1: 多选提取切批量接口**
- **Action**: `EvidenceReviewModal.extractSelected` 改用 `extractSelectedPaperEvidence`(body 加 `mode`,响应 `results` 数组逐篇映射 `paperExtractResults[pmid]`,复用 `loadTaskQueue` 的候选→`WorkbenchPassage` 转换;`error_code`/`error_message` 展示于论文卡片;移除循环内 `abortRef` 竞态)。保留单篇「AI 提取原文」走 `extractPaperPassage`。
- **Mirror**: `loadTaskQueue`(EvidenceReviewModal.tsx:350)的映射。
- **Validate**: 前端单测(mock API):多选 3 篇 → 1 次批量请求,3 个结果卡片渲染;`npm run build` 通过。

**Task 3.2: 佐证模式切换 UI**
- **Action**: 工作台论文搜索区加「佐证模式」select(`function`/`existence`),重搜索/批量提取时传递;`CreateBatchTaskDialog` 增加模式选项(后端 `BatchTaskCreateRequest.mode` 已支持)。
- **Mirror**: `PaperEvidencePanel.tsx:93` 的 mode select 样式。
- **Validate**: 前端测试:模式切换触发带 mode 的请求。

**Task 3.3: 片段标签(核验等级 + 判定维度 + 未验证原因)**
- **Action**: `PassageEvidenceCard` 展示 `source_verification_method`(exact/normalized/similarity,similarity 高亮「近似匹配,请核对原文」)、`evidence_dimension`(存在性/功能)、未验证片段显示失败原因;`attach_evidence` 对含 similarity 片段且无 `reviewer_note` 的请求要求备注(复用现有 direction 覆盖检查模式,service:711)。
- **Mirror**: `DIRECTION_LABEL`/`LEVEL_LABEL`(types.ts)的标签常量模式。
- **Validate**: 前端测试:similarity 片段渲染警示标签;attach 无 note 被拒。

### M4 未验证片段保留 + 人工确认闭环

**Task 4.1: 未验证片段保留展示与人工确认**
- **Action**: 确认 `extractSelected`/`loadPaperResult` 结果映射不过滤 `source_verified=false` 片段(现状已保留展示,补原因标注);人工 reselect(`validate_passage_selection`)后升为 verified 的片段可选中入库。
- **Mirror**: `reselect`(EvidenceReviewModal.tsx:602)既有闭环。
- **Validate**: 前端测试:未验证片段可见且带原因;reselect 后可选。

**Task 4.2: attach 溯源**
- **Action**: 确认 `MirrorEvidencePassage.source_verification_method` 写入 similarity 方法名;`list_paper_evidence` 响应已透传(service:1251) — 补前端展示。
- **Mirror**: 现有 `list_paper_evidence` 字段透传。
- **Validate**: 集成测试:attach similarity 片段后记录 method="similarity"。

## Validation

```bash
# 后端(9 个 evidence 测试文件 + 新增用例)
cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_evidence.py tests/test_paper_evidence_v4.py tests/test_paper_evidence_batch.py tests/test_paper_evidence_api.py tests/test_paper_evidence_integrity.py tests/test_paper_evidence_e2e.py -q

# 前端类型与构建
cd frontend && npm run build

# 前端单测(如配置 vitest)
cd frontend && npx vitest run src/pages/data-center/evidence-workbench src/pages/data-center/PaperEvidenceColumn.test.tsx
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| 模糊定位误匹配无关段落 | Medium | 相似度阈值下限 0.6,低于则标未验证;similarity 片段 UI 高亮 + 人工确认 |
| 语义筛选误杀相关论文 | Medium | 阈值保守(0.4)+ 可关闭(阈值=0)+ 跳过原因落库展示;「筛选精准率 ≥80%」指标监控 |
| 语义筛选/窗口扩大增加 DeepSeek token | Medium | 筛选仅对检索结果执行;跳过节省提取调用;`max_input_chars` 预算保留 |
| schema/响应兼容破坏旧前端 | Low | 新字段全部可空默认;`_normalize_extraction_payload` 兜底 |
| mode 改动波及既有 `function` 行为 | Medium | 默认 mode="function" 保持现状;测试覆盖两种 mode |

## Acceptance

- [ ] M1:提取结果出现 similarity/verified 片段而非全部失败;attach 不再二次拒绝
- [ ] M2:语义筛选按阈值跳过低相关论文且原因可查;existence 模式贯穿检索-提取-判定
- [ ] M3:多选 N 篇一次批量请求逐篇返回;模式切换 UI 可用
- [ ] M4:未验证片段保留展示可 reselect;attach 记录 verification_method 溯源
- [ ] 9 个既有 evidence 测试 + 新增用例全绿;`npm run build` 通过
- [ ] 治理边界未变:置信度仅 supports/partial 公式、contradicts/mixed 进验证中心、DeepSeek confidence 不直接落库
