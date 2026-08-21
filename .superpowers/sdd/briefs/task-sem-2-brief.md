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

