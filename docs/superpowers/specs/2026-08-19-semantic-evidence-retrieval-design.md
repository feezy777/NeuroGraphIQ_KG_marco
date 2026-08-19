# 证据片段语义化召回 设计(针对 deepseek-v4-flash)

- **日期**: 2026-08-19
- **状态**: 设计已与用户确认(方案=LLM 直接语义召回;模型=deepseek-v4-flash)
- **背景**: 当前证据片段召回依赖关键词评分(词边界匹配+词频),语义相关但未出现关键词的段落被丢弃,LLM 只看高分窗口 → 证据片段不准确。

---

## 1. 问题

- 全文段落 → 关键词评分(纯规则)→ 高分段截 500 字进 LLM → locate/judge。
- 语义相关但关键词不共现的段落:评分低、被丢弃,LLM 从未看到。
- 窗口限 50 段 × 500 字,上下文丢失严重。

## 2. 目标

把召回从「关键词硬筛」改为「LLM 语义召回」:全文分块 → LLM 高召回定位 → 命中块扩大上下文严格判定。

## 3. 非目标

- 不引入 embedding 模型/外部依赖。
- 不改检索(Europe PMC 查询)、不改审核/晋升流程。
- 不改变片段数据结构与前端展示契约。

## 4. 设计

### 4.1 语义分块(`paragraph_retrieval.py` 新增 `build_semantic_windows`)

```python
def build_semantic_windows(
    paragraphs: list[dict],
    target_chars: int = 800,
    max_windows: int = 60,
) -> list[dict]:
    """跨段合并为语义块(保持段落完整)。每块 {block_id, paragraphs: [...]}。
    摘要优先:abstract 段落总在第一块。"""
```

- 段落按序合并至 ~800 字符;块 id = 首段 paragraph_id(缺失时 `block_N`)。
- 上限 60 块(48k 字符,v4-flash 384k 上下文内安全)。

### 4.2 LLM 定位(`locate_candidates` 语义化)

- 输入:全部语义块(`<id=...> 文本`,每块完整 800 字,不截断)。
- Prompt 修订(_LOCATOR_SYSTEM/_LOCATOR_USER):
  - 核心指令:「段落与验证主张**语义相关**即可标记,不要求脑区/功能词原词共现(缩写/别名/上位词/换述也算)」。
  - 输出:命中块 id 列表 + `relevance`(0-1 语义相关度)。
- 返回:命中块(按 relevance 降序)。

### 4.3 LLM 判定(`judge_candidates` 严格化)

- 输入:命中块(取 top K=6)的**完整文本 + 前后各 1 个邻块**(上下文完整,不截断 500 字)。
- Prompt 修订(_JUDGE_USER):
  - 「主张要素逐项核对:源脑区 / 靶脑区 / 关系。**至少源+靶或源+关系同段匹配**才可给 supports/partial;仅泛泛提及不给证据」。
  - 方向:supports / partial / contradicts / mixed 如实输出;宁缺毋滥(无匹配 → not_found)。
- 输出:passage(逐字原文)+ direction + confidence + supported_components。

### 4.4 调用链

`_extract_from_paper_with_retry → extract_passage_two_stage` 一处改造:

```text
全文段落 → build_semantic_windows(块)
        → locate(LLM 语义高召回)→ 命中块
        → judge(命中块+邻块,要素核对)→ 片段
        → 无命中 → 回退:关键词评分粗筛(score_paragraphs)top 10 → 单阶段 extract_passage_from_paper
```

- 预处理(`_process_batch_item_v2`)与手动提取(`extract_candidate_for_paper`)共用此路径,同时生效。
- 关键词评分保留为**兜底**(仅 LLM 定位 0 命中时)。

### 4.5 成本与限流(针对 v4-flash)

- locate:1 次调用,输入 ~12-16k tokens(60 块),输出短 JSON。
- judge:命中块通常 2-5 块 → 输入 <8k tokens。
- locate/judge 超时沿用 120s/240s;失败重试沿用(2 次)。

## 5. 文件改动清单

| 文件 | 改动 |
|---|---|
| `backend/app/services/paragraph_retrieval.py` | 新增 `build_semantic_windows` |
| `backend/app/services/paper_evidence_service.py` | `extract_passage_two_stage` 改用语义块;`locate_candidates`/`judge_candidates` 输入与 prompt 语义化;无命中回退关键词评分 |
| 测试 | 分块单测、locate prompt 语义断言、judge 要素核对、回退路径、预处理/手动路径回归 |

## 6. 测试计划

- **分块单测**:跨段合并、块大小上限、摘要优先、60 块上限。
- **locate**:mock LLM 返回命中块 → 正确传块;prompt 含语义指令(断言 user prompt 含「语义相关」)。
- **judge**:mock LLM 要素不匹配 → not_found;匹配 → supports;方向透传。
- **回退**:locate 空 → 走 score_paragraphs 兜底单阶段。
- **回归**:预处理循环、手动提取 run、现有 evidence 测试全绿。
