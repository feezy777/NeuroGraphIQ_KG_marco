# Phase Q4 LLM 增强查询层 — 验收报告

> 目标：在 Ontology Query（规则意图分类 + 实体解析，无 LLM）之上增加医学语言回答能力——
> LLM 只读取**结构化查询结果**（Structured Query Result），生成稳定、低幻觉的医学解释。
> 不修改既有查询逻辑、不让 LLM 自主查询数据库、不改变 canonical ontology 数据。
>
> 日期：2026-08-21 · 分支：codex/ontology-evidence

---

## 1. 新增文件

### 后端

| 文件 | 说明 |
|------|------|
| `backend/app/prompts/__init__.py` | prompts 包标记 |
| `backend/app/prompts/ontology_query_prompt.py` | 固定 SYSTEM_PROMPT + JSON 输出指令 + `build_user_prompt(question, structured_result)`（`_compact_result` 最多压缩 50 项） |
| `backend/app/services/ontology_llm_service.py` | 核心服务：`generate_explanation` 确定性回退链 + `validate_hallucinated_entities` 幻觉校验器 + `_evidence_names` 确定性证据名导出 |
| `backend/tests/test_ontology_llm_service.py` | 10 个测试（规格 1-4 + 扩展） |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/pages/ontology-center/query/QueryAnswerPanel.tsx` | AI 解释面板（灰色 = AI 语言总结，与蓝色结构化证据严格区分） |
| `frontend/src/pages/ontology-center/query/QueryAnswerPanel.test.tsx` | 7 个面板测试（answer/summary/key_points/evidence chips/warning/空值/0% 置信度） |

### 修改文件

`backend/app/schemas/ontology_query.py`（OntologyLLMResponse/OntologyExplainRequest/OntologyExplainResponse）、
`backend/app/schemas/settings.py` + `backend/app/services/settings_service.py` + `backend/data/runtime/settings.local.json`
（OntologyQueryRuntimeSettings 配置）、`backend/app/routers/ontology_query.py`（`POST /api/ontology-query/explain`）、
`frontend/src/api/ontologyQueryApi.ts`（类型 + `postOntologyExplain`）、
`frontend/src/pages/ontology-center/query/OntologyQueryPage.tsx`（双轨结果渲染）、
`frontend/src/pages/ontology-center/query/OntologyQueryPage.test.tsx`（适配 explain）、
`frontend/src/styles.css`（`.oq-answer*` 灰色面板样式）。

## 2. LLM 调用流程

```
用户问题
   │  POST /api/ontology-query/explain {question}
   ▼
handle_ontology_query（既有规则链，未改动）
   │  → intent 分类 + 实体解析（7 级链）+ 结构化结果
   ▼
OntologyQueryResponse
   │
   ├─ 空结果 / unresolved / 无 results ──→ build_fallback_explanation（确定性文案，绝不调用 LLM）
   │
   ├─ runtime enabled=false ────────────→ build_fallback_explanation（确定性文案）
   │
   └─ 正常 ──→ _evidence_names(query)  ← 证据名完全从结构化结果导出（不采信 LLM 自报）
               │
               ▼
        get_llm_provider(config.provider).complete_json(
            model=config.model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(question, query.model_dump()),
            temperature=config.temperature(0.1), max_tokens=2000, timeout_seconds=60)
               │  parsed_json = {answer, summary, key_points, confidence}
               ▼
        validate_hallucinated_entities(session, [answer, summary, *key_points], evidence)
               │  DB 已知脑区名 vs 证据名：不在证据中 + 非证据子串 + 出现在回答文本 → 标记
               ▼
        OntologyLLMResponse(answer, summary, key_points, evidence_entities=证据名,
                            confidence, hallucination_warning)
   │
   ▼
OntologyExplainResponse {question, query_result, explanation}  ← 双轨返回，结构化结果与 AI 解释并存
```

**失败安全**：provider 异常 / JSON 解析失败 → 回退到确定性文案「LLM 解释暂不可用，
以下为知识图谱原始结果摘要」，结构化结果永远不受影响。

## 3. Prompt 设计

**SYSTEM_PROMPT（固定，不可被注入覆盖）：**

> 你是 NeuroGraphIQ 医学知识解释助手。用户会先进行自然语言图谱查询，
> 然后你会看到结构化查询结果（JSON）。你的任务是基于这些结果撰写医学解释。
> 规则：
> 1. 不能添加结果中不存在的实体。
> 2. 不能创造新的连接。
> 3. 不能改变脑区关系。
> 4. 所有结论必须来自 evidence。
> 5. 如果信息不足，明确说明「当前知识图谱暂无相关信息」。

**JSON 输出指令**：`answer`（医学解释段落）、`summary`（一句话摘要）、
`key_points`（要点数组）、`confidence`（0-1，回答对证据的忠实度）。

**user_prompt**：问题原文 + 压缩后的结构化结果 JSON（`_compact_result` 最多 50 项，
防止超长上下文；entity/items 的 name/code 均保留）。

**防幻觉双保险**：
1. prompt 层面——只允许引用结果中的实体；
2. 校验层面——`validate_hallucinated_entities` 用 DB 中 active canonical cn/en + aliases
   比对回答文本，标记「未见于证据」的名称到 `hallucination_warning`（前端黄色警示但不阻断展示）。
   `_is_substring_of_evidence` 排除「海马」⊂「Q15测试海马」这类证据子串误报。

## 4. 支持的问题类型

| 问题类型 | 示例 | 行为 |
|----------|------|------|
| 亚区查询 | 「海马有哪些亚区」 | 结构化亚区列表 + LLM 解释 |
| 连接查询 | 「连接海马的脑区有哪些」 | 传入/传出连接 + LLM 解释 |
| 回路/功能/多尺度查询 | 「海马参与哪些功能」 | 同 |
| 同义词/别名/缩写 | 「Q15PFC 有哪些亚区」 | 别名解析后同上 |
| 模糊匹配 | 「前额叶有什么功能」 | 模糊候选解析后同上 |
| 未识别实体 | 「今天的天气怎么样」 | 确定性回退文案（绝不调用 LLM） |
| 识别但无数据 | 「XX 有哪些连接」（无连接） | 确定性回退文案「当前知识图谱未发现相关连接」 |

所有问题类型都在 `POST /api/ontology-query/explain` 下统一处理——查询逻辑零改动，
LLM 只负责「翻译结构化结果」。

## 5. 模型配置方式

运行时可配置（`backend/data/runtime/settings.local.json`，也可经 PATCH `/api/settings/runtime` 热更新）：

```json
{
  "ontology_query": {
    "enabled": true,
    "provider": "deepseek",
    "model": "deepseek-v4",
    "temperature": 0.1
  }
}
```

- **不硬编码模型**：provider/model 走 `llm_providers/factory.py` 抽象 + runtime settings，
  可切换 kimi 等任意已注册 provider。
- **temperature 固定低值 0.1**（schema 约束 0.0-1.0），保证医学回答稳定。
- `enabled=false` → 完全关闭 LLM 层，接口退化为纯结构化结果 + 确定性文案，不影响既有查询。

## 6. 测试结果

### 后端（`backend/tests/test_ontology_llm_service.py`，10/10 通过）

| # | 用例 | 验证点 |
|---|------|--------|
| 1 | 正常解释 | answer/prompt 含 question+results、temperature==0.1、model==deepseek-v4、evidence_entities 确定性 |
| 2 | 幻觉检测 | hallucination_warning 含「Q15幻影海马」但排除证据子串「海马」 |
| 2b | 无误报 | 无幻影数据时 warning 为空 |
| 3 | 空结果 | 「暂无相关信息」，confidence==0.95，**不调用 provider** |
| 3b | unresolved | mock provider **assert_not_called** |
| 3c | 连接为空 | 「未发现相关连接」 |
| 3d | disabled | enabled=false 不调用 provider |
| 3e | provider 异常 | 回退「LLM 解释暂不可用」 |
| 4 | API /explain | unresolved 返回双轨结构 |
| 4b | 真实「海马有哪些功能」 | mock provider 下 explanation 写入、证据含 ng:br:hippocampus |

**Ontology 域完整回归**：`test_ontology_query.py` + `test_region_alias_resolution.py` +
`test_settings.py` + `test_ontology_llm_service.py` = **49/49 通过**（含 Q1.5 别名回归修复：
fixture 别名 PFC→Q15PFC，避免与真实 20260830 别名数据冲突）。

### 前端

| 项 | 结果 |
|----|------|
| `QueryAnswerPanel.test.tsx` | 7/7（answer/summary/points/evidence chips/warning alert/空值/0%） |
| `OntologyQueryPage.test.tsx` | 8/8（双轨渲染/实体卡/连接流向/未识别回退/幻觉警示/URL 跳转/tab 切换） |
| 全量 vitest | 58 文件 504 passed / 1 skipped |
| `tsc --noEmit` | 0 错误 |
| `npm run build` | 通过（仅既有 chunk >500kB 提示，与本次无关） |

### 验收规格对照

| 规格 | 落实 |
|------|------|
| 不修改已有查询逻辑 | ✅ `handle_ontology_query` 原样复用 |
| LLM 不自主查询数据库 | ✅ LLM 只见结构化结果 JSON（`build_user_prompt`） |
| 不改变 canonical 数据 | ✅ 零写入；幻觉校验只读 DB |
| 不删除规则查询 / 不生成新实体 / 不联动 Graph Explorer | ✅ |
| 不硬编码模型 + 低温度 | ✅ runtime 配置 + temperature 0.1 |
| 输出 6 节验收报告 | ✅ 本文档 |
