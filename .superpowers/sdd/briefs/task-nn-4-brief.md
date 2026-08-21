### Task 4: build_search_query negative 参数 + 自动反向检索

**Files:**
- Modify: `backend/app/services/evidence_target_adapter.py`(`build_search_query`,约 518-560 行)
- Modify: `backend/app/services/paper_evidence_service.py`(`_process_batch_item_v2` 无结果路径,约 5170-5180 行)

**Interfaces:**
- Consumes: `build_search_query(session, target_type, target_id, *, mode, abstract_only, negative=False)`
- Produces: `preprocess_outcome='evidence_negated'`(否定向检索命中时);未命中保持 `no_evidence_found`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_evidence_target_adapter.py`(若不存在则新建;先查该文件是否已有测试结构,有则追加):

```python
# -*- coding: utf-8 -*-
"""build_search_query negative 变体:否定连接词注入。"""

import asyncio
import uuid

from app.services import evidence_target_adapter as eta


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_negative_query_contains_negation_terms():
    dto = {
        "source_region": "BLA", "target_region": "IL",
        "canonical_terms": [], "function_terms": [], "function_synonyms": [],
        "display_name": "BLA → IL",
    }
    with __import__("unittest.mock").patch.object(eta, "build_target_dto", __import__("unittest.mock").AsyncMock(return_value=dto)):
        q = _run(eta.build_search_query(None, "connection", uuid.uuid4(), mode="existence", negative=True))
    assert "no projection" in q or "does not connect" in q or "absence of connection" in q
    assert "ABSTRACT:\"BLA\"" in q
    assert "ABSTRACT:\"IL\"" in q


def test_positive_query_has_no_negation_terms():
    dto = {
        "source_region": "BLA", "target_region": "IL",
        "canonical_terms": [], "function_terms": [], "function_synonyms": [],
        "display_name": "BLA → IL",
    }
    with __import__("unittest.mock").patch.object(eta, "build_target_dto", __import__("unittest.mock").AsyncMock(return_value=dto)):
        q = _run(eta.build_search_query(None, "connection", uuid.uuid4(), mode="existence"))
    assert "no projection" not in q
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_evidence_target_adapter.py -q`
Expected: FAIL(TypeError:`build_search_query() got an unexpected keyword argument 'negative'`)

- [ ] **Step 3: 实现 negative 参数**

`evidence_target_adapter.py` 的 `build_search_query`:

```python
async def build_search_query(
    session: AsyncSession,
    target_type: str,
    target_id: uuid.UUID,
    *,
    mode: str = "function",
    abstract_only: bool = True,
    negative: bool = False,
) -> str:
```

在 `if mode == "existence":` 分支前插入否定词注入(existence 与 function 都适用):

```python
    negative_terms = (
        ["no projection", "does not connect", "absence of connection", "not connected", "no connection"]
        if negative else []
    )
    if mode == "existence":
        # regions only (canonical + core term + synonym hints) — no function terms
        terms = _region_search_terms(src) + _region_search_terms(tgt) + negative_terms
    else:
        terms = list(dto["canonical_terms"]) + _region_search_terms(src) + _region_search_terms(tgt)
        if target_type in ("connection", "projection"):
            terms += _CONNECTION_EVIDENCE_TERMS
        terms += negative_terms
```

(注意:negative_terms 在 existence 分支插入后,`tokens` 组装逻辑不变;ABSTRACT 引号包裹会在 token 循环里处理——`"no projection"` 会被 strip('"') 后包成 `ABSTRACT:"no projection"` ✓)

- [ ] **Step 4: 实现自动反向检索**

`paper_evidence_service.py` `_process_batch_item_v2` 的无结果路径(当前 `if not papers:` 之后、`_set_item_stage(no_evidence_found)` 之前)插入第二轮否定向检索:

```python
            if not papers:
                # 反向验证:正向无结果时用否定向查询再搜一轮,区分「证据否定」与「无证据」
                negative_query = await build_search_query(
                    session, target_type, uuid.UUID(target_id), mode=mode, abstract_only=False, negative=True
                )
                if negative_query and negative_query != query:
                    async with sem_search:
                        papers = await _search_with_retry(negative_query, limit=max(10, max_papers * 3))
                    if papers:
                        query = negative_query
            if not papers:
                await _set_item_stage(
                    session, item_id, "awaiting_review",
                    preprocess_outcome="no_evidence_found",
                    last_error_code="EUROPE_PMC_NO_RESULT",
                    last_error_message="no papers matched the query",
                    last_error_at="SQL:now()",
                    finished_preprocessing_at="SQL:now()",
                )
                return
```

(注意:现有代码已有「wide_query 二次检索」块,反向检索放在其后、`if not papers:` 判定前;`build_search_query` 已 import——检查文件顶部 import,未导入则加 `from app.services.evidence_target_adapter import build_search_query`。)

反向检索命中后,提取流程走通用路径;`verified_any` 处(约 5312 行)设置 outcome 时,若 query 是 negative 且方向为 contradicts → 标记 `evidence_negated`:

```python
                preprocess_outcome = (
                    "evidence_negated"
                    if query_is_negative and verified_any
                    else "evidence_found" if verified_any else "no_evidence_found"
                )
```

实现:在函数开头记录 `query_is_negative = query.startswith("no projection") or "does not connect" in query`(否定查询特征),并在 outcome 赋值处使用;若提取方向均为 contradicts 才标否定(简化:query 为否定向且提取有结果 → evidence_negated;提取方向自然为 contradicts)。

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_evidence_target_adapter.py tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py -q`
Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/evidence_target_adapter.py backend/app/services/paper_evidence_service.py backend/tests/test_evidence_target_adapter.py
git commit -m "feat(evidence): negative search on no-result — auto second round distinguishes evidence_negated vs no_evidence"
```

---

