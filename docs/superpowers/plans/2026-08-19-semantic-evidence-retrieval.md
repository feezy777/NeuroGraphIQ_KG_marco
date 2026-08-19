# 证据片段语义化召回 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把证据片段召回从「关键词评分窗口 + 宽松判定」改为「全文语义块 + LLM 语义召回 + 要素严格核对」,针对 deepseek-v4-flash。

**Architecture:** 新增 `build_semantic_windows`(全文段落跨段合并为 800 字语义块,上限 60);`locate_candidates` 直接对语义块做 LLM 高召回定位(不依赖关键词评分);`judge_candidates` 严格化(主张要素逐项核对,共现不再自动算证据);`extract_passage_two_stage` 接入语义块,LLM 定位 0 命中时回退关键词窗口单阶段。

**Tech Stack:** FastAPI + SQLAlchemy async + DeepSeek v4-flash。

**设计文档:** `docs/superpowers/specs/2026-08-19-semantic-evidence-retrieval-design.md`(用户已确认)。

## Global Constraints

- 只改 `paragraph_retrieval.py`(新增函数)与 `paper_evidence_service.py`(locate/judge/two_stage/prompt)及测试。
- 定位与判定针对 deepseek-v4-flash:locate 输入 ≤60 块 × 800 字;judge 输入命中块 top6 + 前后邻块。
- judge 严格化:主张要素(源/靶/关系)至少两项同段匹配才给 supports/partial;**仅共现不算证据**(改为 not_found 或 confidence<0.1 且 supported_components 为空)。
- 无命中回退:LLM 定位空 → 关键词评分(score_paragraphs)top10 单阶段提取。
- 不改变片段数据结构/前端契约/审核晋升流程。
- 后端测试用真实测试库 + patch LLM。

---

### Task 1: 语义分块函数

**Files:**
- Modify: `backend/app/services/paragraph_retrieval.py`(新增 `build_semantic_windows`)
- Test: `backend/tests/test_paragraph_retrieval.py`(若存在则追加;先 grep)

**Interfaces:**
- Produces: `build_semantic_windows(paragraphs: list[dict], target_chars: int = 800, max_windows: int = 60) -> list[dict]`,每块 `{block_id, paragraphs: [...]}`;Task 2 使用。

- [ ] **Step 1: 写失败测试**

```python
# 追加到 test_paragraph_retrieval.py(不存在则新建,含 import)
from app.services.paragraph_retrieval import build_semantic_windows

def _para(pid, text, scope="body", idx=0):
    return {"paragraph_id": pid, "passage_text": text, "source_scope": scope, "paragraph_index": idx}

def test_merges_short_paragraphs_into_blocks():
    paras = [
        _para("p1", "A" * 300, "abstract", 0),
        _para("p2", "B" * 300, "body", 1),
        _para("p3", "C" * 300, "body", 2),
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    assert len(blocks) == 1
    assert blocks[0]["block_id"] == "p1"
    assert len(blocks[0]["paragraphs"]) == 3


def test_split_long_text_into_multiple_blocks():
    paras = [_para("p1", "X" * 1000, "body", 0), _para("p2", "Y" * 1000, "body", 1)]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    assert len(blocks) >= 2
    # 块内段落保序、不重复
    all_pids = [p["paragraph_id"] for b in blocks for p in b["paragraphs"]]
    assert all_pids == ["p1", "p2"]


def test_abstract_first():
    paras = [
        _para("p-body", "B" * 600, "body", 0),
        _para("p-abs", "A" * 600, "abstract", 1),
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    # 摘要优先:abstract 段落进第一块
    assert blocks[0]["paragraphs"][0]["source_scope"] == "abstract"


def test_max_windows_cap():
    paras = [_para(f"p{i}", "Z" * 800, "body", i) for i in range(80)]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    assert len(blocks) == 60
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paragraph_retrieval.py -q -k semantic`
Expected: FAIL(ImportError:`cannot import name 'build_semantic_windows'`)

- [ ] **Step 3: 实现**

`paragraph_retrieval.py` 末尾追加:

```python
def build_semantic_windows(
    paragraphs: list[dict],
    target_chars: int = 800,
    max_windows: int = 60,
) -> list[dict]:
    """跨段合并为语义块(保持段落完整、保序)。每块 {block_id, paragraphs}。

    - 摘要段落总在最前(第一块起始);
    - 段落到 target_chars 上限即封块,单段超过上限单独成块;
    - 最多 max_windows 块(超出丢弃尾部,返回可处理的上限)。
    """
    ordered = list(paragraphs)
    # abstract 优先置前
    ordered.sort(key=lambda p: 0 if p.get("source_scope") == "abstract" else 1)

    blocks: list[dict] = []
    current: list[dict] = []
    current_len = 0
    for para in ordered:
        text = para.get("passage_text") or ""
        length = len(text)
        if current and current_len + length > target_chars and current_len >= 1:
            blocks.append({
                "block_id": current[0].get("paragraph_id") or f"block_{len(blocks)}",
                "paragraphs": current,
            })
            current = []
            current_len = 0
            if len(blocks) >= max_windows:
                break
        current.append(para)
        current_len += length
    if current and len(blocks) < max_windows:
        blocks.append({
            "block_id": current[0].get("paragraph_id") or f"block_{len(blocks)}",
            "paragraphs": current,
        })
    return blocks[:max_windows]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paragraph_retrieval.py -q`
Expected: 全部通过(含新增 4 例)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paragraph_retrieval.py backend/tests/test_paragraph_retrieval.py
git commit -m "feat(evidence): build_semantic_windows — paragraph blocks for LLM semantic recall"
```

---

### Task 2: locate_candidates 语义块输入

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`locate_candidates`,约 2230 行)

**Interfaces:**
- Consumes: Task 1 的 `build_semantic_windows`
- Produces: `locate_candidates(claim, blocks, title)` 对语义块高召回;Task 3 使用命中块

- [ ] **Step 1: 写失败测试(断言块输入与语义 prompt)**

在 `backend/tests/test_paper_evidence_extraction.py`(或同目录现测试文件)追加:

```python
# -*- coding: utf-8 -*-
"""locate_candidates 语义块输入:直接对块做高召回,不依赖关键词窗口。"""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_locate_uses_blocks_and_returns_hits():
    blocks = [
        {"block_id": "b1", "paragraphs": [{"paragraph_id": "p1", "passage_text": "text one", "section_title": "Results"}]},
        {"block_id": "b2", "paragraphs": [{"paragraph_id": "p2", "passage_text": "text two", "section_title": "Discussion"}]},
    ]
    claim = {"claim_text": "X projects to Y", "structured_claim": {}, "function_term": "connect"}
    with patch.object(pes, "get_llm_provider", return_value=AsyncMock()) as mock_provider:
        mock_provider.return_value.complete_json = AsyncMock(return_value=type(
            "R", (), {"raw_text": '{"candidates":[{"paragraph_id":"b2","relevance":0.9,"relation_cue":"direct_connection","reason":"相关"}]}',
                     "parsed_json": None, "model": "m"})())
        hits = _run(pes.locate_candidates(claim, blocks))
    assert len(hits) == 1
    assert hits[0]["paragraph_id"] == "b2"
    assert hits[0]["relevance"] == 0.9
    assert hits[0]["passage_text"] == "text two"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py -q -k locate_uses_blocks`
Expected: FAIL(当前实现从 windows 的 context 取段,blocks 结构不匹配 → 空结果)

- [ ] **Step 3: 实现**

`locate_candidates` 的窗口序列化段替换为块序列化(每块完整 800 字,不截断):

```python
    # Serialize semantic blocks with IDs(每块完整文本,不截断)
    window_lines = []
    window_map: dict[str, dict] = {}
    for w in windows:
        bid = w.get("block_id") or (w.get("paragraphs") or [{}])[0].get("paragraph_id") or ""
        if not bid:
            continue
        if bid in window_map:
            continue
        text = " ".join(
            (p.get("passage_text") or "") for p in (w.get("paragraphs") or [])
        )
        window_map[bid] = {"block_id": bid, "passage_text": text, "section_title": (w.get("paragraphs") or [{}])[0].get("section_title", "")}
        window_lines.append(f"<id={bid}> {text}")

    if not window_lines:
        return []
```

同时 `_LOCATOR_USER` 的「段落窗口」说明改为「语义块」,并保留语义导向指令(已符合);命中解析处 `window_map[pid]` 取 passage_text/section 不变。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py -q`
Expected: 全部通过(语义块序列化兼容旧 windows 结构?——检查调用方:two_stage 传入的 windows 由 Task 4 改为 blocks;旧测试若仍传 windows(context 结构)会空——Task 2 仅改序列化,保留对两种结构的兼容:`w.get("context")` 旧结构时走旧逻辑)

**兼容要求**:序列化逻辑同时支持 `{context: [...]}`(旧)与 `{paragraphs: [...]}`/`{block_id, paragraphs}`(新),避免 Task 2 单独落地时破坏现有调用。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_extraction.py
git commit -m "feat(evidence): locate_candidates accepts semantic blocks (full text, no 500-char truncation)"
```

---

### Task 3: judge_candidates 严格化(要素核对,共现不算证据)

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`_JUDGE_USER` prompt + `judge_candidates` 输入与输出处理,约 2290-2400 行)

**Interfaces:**
- Consumes: Task 2 命中块(带 passage_text/section)
- Produces: judge 仅对要素匹配段落给证据;共现降级为 not_found 或空 supported_components

- [ ] **Step 1: 写失败测试(断言新 prompt 指令与严格判定)**

追加到 `tests/test_paper_evidence_extraction.py`:

```python
def test_judge_user_prompt_requires_component_match():
    # prompt 必须包含要素核对与「共现不算证据」指令
    assert "至少" in pes._JUDGE_USER and "supported_components" in pes._JUDGE_USER
    assert "共现" in pes._JUDGE_USER  # 或等价表述「仅同时出现」
```

(prompt 是常量,直接断言指令存在;同时按新 prompt 语义验证 mock LLM 输出 not_found 时 judge 返回 not_found。)

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py -q -k judge_user_prompt`
Expected: FAIL(当前 prompt 无严格指令)

- [ ] **Step 3: 实现**

`_JUDGE_USER` 替换为严格版(核心变化:要素至少两项匹配才给证据;共现不算):

```python
_JUDGE_USER = """待验证的知识主张："{claim}"
结构化主张：{structured}
主张要素：{components}

以下是从论文中筛选出的候选段落。请严格判断，只有段落**实质支持/反对**该主张时才作为证据返回。

规则：
1. passage 逐字复制原文。
2. **要素核对**：对每段检查源脑区(source_region)、靶脑区(target_region)、关系(relation)是否出现（含同义词/缩写/上位结构）。
   - source_region 与 target_region 同段且存在连接/功能描述 → supports/partial
   - 仅出现单个脑区+功能描述 → partial（source_match/target_match 只标匹配项）
   - **仅两个脑区名称共现、无任何连接/功能/临床关联 → 不算证据**（passages 不返回该段，或在 assessment 说明）
3. direction：明确支持=supports；部分关联=partial；明确反对=contradicts；正反混杂=mixed。
4. evidence_level：direct（实验直接证明）/ indirect（合理推断）/ interpretive（Discussion 解读）/ background（Introduction 背景）。
5. evidence_pattern：direct_statement/tracing/tractography/functional_connectivity/anatomical_description/clinical_analysis。
6. not_found：当没有段落实质支持或反对该主张时使用（仅共现不算实质）。
7. supported_components 只列实际匹配的要素。

只返回一个纯JSON：
{{"overall_direction":"supports|partial|contradicts|mixed|not_found","paper_relevance":0.5,
 "assessment":"<1-2句中文>","evidence_dimension":"function|existence|mixed",
 "not_found_reason":"<仅not_found时填写>",
 "passages":[{{"paragraph_id":"<id>","section":"<section>","passage":"<英文原文>",
 "direction":"partial","evidence_level":"background","reason":"<中文>",
 "confidence":0.4,"semantic_confidence":0.4,
 "supported_components":["source_region","target_region"],
 "evidence_dimension":"function","evidence_pattern":"functional_connectivity",
 "source_match":true,"target_match":true,"relation_match":true,
 "direction_match":true,"species_match":true}}]}}

论文标题：{title}
候选段落：
{candidates}"""
```

`judge_candidates` 输入:改为「命中块(完整文本) + 前后邻块」——调用方(Task 4)传 `candidates` 为块列表;judge 内序列化块全文(不做 500 截断,但每块 ≤800 字天然受限):

```python
    candidate_lines = []
    for i, c in enumerate(candidates[:6]):
        text = (c.get("passage_text") or "")
        candidate_lines.append(f"<id={c.get('paragraph_id') or c.get('block_id')}> {text}")
```

(judge 命中块 passage_text 来自 Task 2 的 locate 返回——locate 返回 block_id + 块全文;为给 judge 邻块上下文,调用方拼接。)

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py tests/test_paper_evidence_batch_phase4.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_extraction.py
git commit -m "feat(evidence): strict judge — component match required, co-occurrence is not evidence"
```

---

### Task 4: extract_passage_two_stage 接入语义块 + 回退

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`extract_passage_two_stage`,约 2402 行;`_extract_from_paper_with_retry` 调用链)

**Interfaces:**
- Consumes: Task 1 的 `build_semantic_windows`、Task 2/3 的 locate/judge
- Produces: 全文语义块 → locate → judge;0 命中回退关键词窗口单阶段

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_paper_evidence_extraction.py`:

```python
def test_two_stage_uses_semantic_blocks_and_falls_back():
    from app.services.paragraph_retrieval import build_semantic_windows
    claim = {"claim_text": "X projects to Y", "structured_claim": {}, "function_term": "connect",
             "claim_components": [], "claim_version": "v1"}
    paras = [
        {"paragraph_id": "p1", "passage_text": "X terminates in Y as shown by tracing.", "section_title": "Results", "paragraph_index": 0, "source_scope": "body"},
        {"paragraph_id": "p2", "passage_text": "Unrelated cell culture methods.", "section_title": "Methods", "paragraph_index": 1, "source_scope": "body"},
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    with patch.object(pes, "locate_candidates", new=AsyncMock(return_value=[
        {"paragraph_id": "b_p1", "relevance": 0.9, "passage_text": "X terminates in Y as shown by tracing.", "section": "Results"},
    ])):
        with patch.object(pes, "judge_candidates", new=AsyncMock(return_value={
            "overall_direction": "supports", "paper_relevance": 0.9,
            "assessment": "支持", "evidence_dimension": "existence",
            "passages": [{"paragraph_id": "p1", "passage": "X terminates in Y as shown by tracing.", "direction": "supports", "confidence": 0.8}],
        })):
            result = _run(pes.extract_passage_two_stage(claim=claim, title="t", windows=blocks))
    assert result["overall_direction"] == "supports"
    assert len(result["passages"]) == 1


def test_two_stage_falls_back_when_locate_empty():
    from app.services.paragraph_retrieval import build_semantic_windows
    claim = {"claim_text": "X projects to Y", "structured_claim": {}, "function_term": "connect",
             "claim_components": [], "claim_version": "v1"}
    paras = [
        {"paragraph_id": "p1", "passage_text": "X projects to Y in macaque.", "section_title": "Abstract", "paragraph_index": 0, "source_scope": "abstract"},
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    with patch.object(pes, "locate_candidates", new=AsyncMock(return_value=[])):
        with patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value={
            "overall_direction": "partial", "paper_relevance": 0.4, "assessment": "a",
            "passages": [{"paragraph_id": "p1", "passage": "X projects to Y in macaque.", "direction": "partial", "confidence": 0.3}],
        })):
            result = _run(pes.extract_passage_two_stage(claim=claim, title="t", windows=blocks))
    assert result["overall_direction"] == "partial"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py -q -k two_stage`
Expected: FAIL(locate 对 blocks 结构返回空或序列化失败)

- [ ] **Step 3: 实现**

`extract_passage_two_stage` 改造:

```python
async def extract_passage_two_stage(
    *,
    claim: dict,
    title: str = "",
    windows: list[dict],
    on_stage: ExtractionStageCallback | None = None,
) -> dict:
    """Semantic recall:全文语义块 → LLM 定位 → 命中块严格判定。

    无命中时回退关键词评分窗口(top10)单阶段提取。
    """
    # Stage 1: LLM 语义高召回(对全文语义块)
    await _emit_extraction_stage(on_stage, "locating")
    candidates = await locate_candidates(claim, windows, title)

    if not candidates:
        # 回退:关键词评分窗口 top10 单阶段
        await _emit_extraction_stage(on_stage, "judging")
        result = await extract_passage_from_paper(
            claim=claim, title=title, windows=windows
        )
        result.setdefault("llm_model", get_settings().ontology_residual_model)
        return result

    # Stage 2: 命中块 + 邻块上下文,严格判定
    await _emit_extraction_stage(on_stage, "judging")
    # 构造 judge 输入:命中块全文(含邻块拼接)
    judge_candidates_input = _build_judge_input(windows, candidates)
    result = await judge_candidates(claim, judge_candidates_input, title)

    if result["overall_direction"] == "not_found" and candidates:
        result["_stage1_candidates"] = len(candidates)
        result["_stage1_top_relevance"] = candidates[0]["relevance"] if candidates else 0

    result["_two_stage"] = True
    result["_stage1_candidates"] = len(candidates)
    return result
```

新增 helper `_build_judge_input(blocks, hits)`(拼接命中块 + 前后邻块全文):

```python
def _build_judge_input(blocks: list[dict], hits: list[dict]) -> list[dict]:
    """命中块全文 + 前后各 1 个邻块,供 judge 严格判定。"""
    bid_hit = {h.get("paragraph_id") or h.get("block_id"): h for h in hits}
    ordered = list(blocks)
    idx_of = {b.get("block_id"): i for i, b in enumerate(ordered) if b.get("block_id")}
    out: list[dict] = []
    seen: set[str] = set()
    for b in blocks:
        bid = b.get("block_id")
        if bid not in bid_hit:
            continue
        span_ids = [bid]
        i = idx_of.get(bid)
        if i is not None:
            for nb in (ordered[i - 1], ordered[i + 1]) if i > 0 and i + 1 < len(ordered) else ([ordered[i - 1]] if i > 0 else [ordered[i + 1]]):
                if nb is not None and nb.get("block_id") not in seen:
                    span_ids.append(nb.get("block_id"))
        text = " ".join((p.get("passage_text") or "") for b2 in ordered if b2.get("block_id") in span_ids for p in (b2.get("paragraphs") or []))
        out.append({"paragraph_id": bid, "passage_text": text, "section_title": (b.get("paragraphs") or [{}])[0].get("section_title", "")})
        seen.update(span_ids)
        if len(out) >= 6:
            break
    return out
```

注意:Task 3 的 judge 已改用 `candidates[:6]` + `passage_text`;locate 返回的 passage_text 是块全文,此处用邻块拼接。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py tests/test_paper_evidence_batch_phase4.py tests/test_paper_evidence.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_extraction.py
git commit -m "feat(evidence): two-stage extraction on semantic blocks with keyword-window fallback"
```

---

### Task 5: 回归验证

**Files:**
- 无新文件

**Interfaces:**
- Consumes: 全部前序任务

- [ ] **Step 1: 后端全量**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部通过(仅既有 6 个基线失败)

- [ ] **Step 2: 实测一篇提取(计时 + 片段质量)**

Run(临时脚本,调 `extract_candidate_for_paper` 对一篇真实论文计时):

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import asyncio, time
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes
async def main():
    sem_fetch = asyncio.Semaphore(2); sem_llm = asyncio.Semaphore(2)
    async with AsyncSessionLocal() as s:
        row = (await s.execute(text(\"SELECT id, target_id::text FROM paper_evidence_task_items WHERE status='awaiting_review' AND jsonb_array_length(COALESCE(candidate_papers,'[]'::jsonb))>0 ORDER BY updated_at DESC LIMIT 1\"))).first()
        cp = (await s.execute(text('SELECT candidate_papers FROM paper_evidence_task_items WHERE id=:iid'), {'iid': row[0]})).first()[0]
        ctx = await pes.build_retrieval_context(s, 'connection', row[1], mode='existence')
        t0 = time.monotonic()
        env = await pes.extract_candidate_for_paper(s, context=ctx, paper=cp[0], sem_fetch=sem_fetch, sem_deepseek=sem_llm, mode='existence')
        print('TOTAL %.1fs status=%s passages=%d dir=%s' % (time.monotonic()-t0, env.get('status'), len((env.get('candidate') or {}).get('passages') or []), (env.get('candidate') or {}).get('model_direction')))
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
"
```

Expected: 完成且 passage 方向/内容合理(相对旧流程,共现噪声段应减少)。

- [ ] **Step 3: 冒烟**

前后端 dev 服务运行中;佐证任务页创建/手动提取一个对象,确认无报错。
