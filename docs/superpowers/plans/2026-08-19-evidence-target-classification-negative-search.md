# 非神经靶标治理 + 自动反向检索 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 识别非神经靶标(脑室/脑脊液/脑膜/脉络丛)并直接标记「结构性不存在」,佐证任务页与证据佐证页提示治理内容;正向检索无结果时自动否定向检索,区分「证据否定」与「无证据」;晋升永久跳过治理边,并清理 final_kg 历史脏边。

**Architecture:** 新增纯函数分类器 `evidence_target_classifier.py`(中英关键词);`create_batch_task` 创建时判定靶标,非神经 item 直接标记 `preprocess_outcome='non_neural_target'` 且后台处理立即完成;`build_search_query` 加 `negative` 参数,预处理无结果时自动反向检索标记 `evidence_negated`;晋升服务跳过两类治理边;一次性脚本清理 final_kg;前端任务卡徽章 + 候选页提示条。

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL;React 18 + Vite + TS + Vitest。

**设计文档:** `docs/superpowers/specs/2026-08-18-evidence-target-classification-negative-search-design.md`(用户已确认,含「隔离+清理」治理深度)。

## Global Constraints

- **治理深度**:镜像行 + 佐证标记保留(审计);「结构性不存在(`non_neural_target`)」与「证据否定(`evidence_negated`)」两类边**永久跳过晋升**;「无证据(`no_evidence_found`)」不跳过;final_kg 历史脏边一次性清理脚本。
- **直接标记不存在**:非神经靶标对象无需人工确认页,自动标记;佐证任务页任务卡与证据佐证页**两处提示**治理内容。
- **分类器默认不误伤**:未命中 → `unknown`(按神经处理,不改变现有行为);名单/关键词中英匹配。
- **反向检索仅触发于正向无结果**:正向命中对象零开销;非神经靶标对象不触发(已跳过检索)。
- 后端测试用真实测试库(AsyncSessionLocal + patch 外部调用);前端 vitest + RTL。
- 提交信息英文 conventional commits。

---

### Task 1: 非神经靶标分类器

**Files:**
- Create: `backend/app/services/evidence_target_classifier.py`
- Test: `backend/tests/test_evidence_target_classifier.py`

**Interfaces:**
- Produces: `classify_target(region_name_cn: str | None, region_name_en: str | None) -> str`(返回 `'neural' | 'non_neural' | 'unknown'`;Task 2 使用)

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_evidence_target_classifier.py`:

```python
# -*- coding: utf-8 -*-
"""非神经靶标分类器:脑室/脑脊液/脑膜/脉络丛识别,正常脑区不误伤。"""

from app.services.evidence_target_classifier import classify_target


def test_lateral_ventricle_en():
    assert classify_target(None, "Lateral ventricle") == "non_neural"


def test_ventricle_cn():
    assert classify_target("侧脑室", None) == "non_neural"


def test_third_fourth_ventricle():
    assert classify_target("第三脑室", "Third ventricle") == "non_neural"


def test_cistern_cn_en():
    assert classify_target(None, "Suprasellar cistern") == "non_neural"
    assert classify_target("环池", None) == "non_neural"


def test_csf_subarachnoid():
    assert classify_target(None, "Cerebrospinal fluid") == "non_neural"
    assert classify_target(None, "Subarachnoid space") == "non_neural"


def test_meninges():
    assert classify_target(None, "Dura mater") == "non_neural"
    assert classify_target(None, "Pia mater") == "non_neural"
    assert classify_target("硬脑膜", None) == "non_neural"


def test_choroid_plexus():
    assert classify_target(None, "Choroid plexus") == "non_neural"
    assert classify_target("脉络丛", None) == "non_neural"


def test_falk_tentorium():
    assert classify_target(None, "Falx cerebri") == "non_neural"
    assert classify_target(None, "Tentorium cerebelli") == "non_neural"


def test_real_region_not_mistaken():
    assert classify_target("杏仁核", "Amygdala") == "unknown"
    assert classify_target("前扣带皮层", "Anterior cingulate cortex") == "unknown"
    assert classify_target(None, "Primary somatosensory area, layer 4") == "unknown"


def test_none_inputs():
    assert classify_target(None, None) == "unknown"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_evidence_target_classifier.py -q`
Expected: FAIL(ImportError:`cannot import name 'classify_target'`)

- [ ] **Step 3: 实现**

创建 `backend/app/services/evidence_target_classifier.py`:

```python
"""非神经靶标分类器。

识别「脑区 → 非神经结构」(如侧脑室)这类解剖学上不可能的连接靶标。
纯函数、无 DB;未命中返回 unknown(按神经处理,不误杀)。
"""

from __future__ import annotations

# 非神经结构关键词(子串匹配,大小写不敏感;中文按原样匹配)
_NON_NEURAL_KEYWORDS: tuple[str, ...] = (
    # 脑室系统
    "ventricle", "脑室",
    # 脑脊液/蛛网膜下腔/池
    "cistern", "csf", "cerebrospinal", "subarachnoid", "脑脊液", "蛛网膜下腔", "池",
    # 脑膜
    "meninges", "dura", "pia mater", "arachnoid", "脑膜", "硬脑膜", "软脑膜",
    # 脉络丛
    "choroid plexus", "脉络丛",
    # 硬膜结构
    "falx", "tentorium", "大脑镰", "小脑幕",
)


def classify_target(region_name_cn: str | None, region_name_en: str | None) -> str:
    """判定靶标是否为非神经结构。返回 'neural' | 'non_neural' | 'unknown'。

    - 命中非神经关键词(中英任一)→ 'non_neural';
    - 未命中 → 'unknown'(按神经处理,不误杀;本版本不做神经白名单确认)。
    """
    haystacks = [region_name_en or "", region_name_cn or ""]
    for kw in _NON_NEURAL_KEYWORDS:
        lowered = kw.lower()
        for h in haystacks:
            if lowered in h.lower():
                return "non_neural"
    return "unknown"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_evidence_target_classifier.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/evidence_target_classifier.py backend/tests/test_evidence_target_classifier.py
git commit -m "feat(evidence): non-neural target classifier (ventricle/CSF/meninges/plexus)"
```

---

### Task 2: 创建任务时判定靶标,非神经直接标记

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`create_batch_task` per-object 循环,约 5670-5730 行)

**Interfaces:**
- Consumes: Task 1 的 `classify_target`
- Produces: 非神经靶标 item 写入 `preprocess_outcome='non_neural_target'`(Task 3 处理时跳过;Task 4 反向检索不触发)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_paper_evidence_batch.py` 的 `TestBatchStateMachine` 追加:

```python
    def test_non_neural_target_marked_without_search(self):
        oid = str(uuid.uuid4())
        # 靶标名含「脑室」→ 创建即标记结构性不存在
        with (
            patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=[oid])),
            patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=[oid])),
            patch.object(
                pes,
                "_batch_scope_label",
                new=AsyncMock(side_effect=lambda s, tt, o: (f"X → 侧脑室", 0.1)),
            ),
            patch.object(pes, "_classify_item_target", new=AsyncMock(return_value="non_neural")),
        ):
            result = _run(_make_task_inner(target_ids=[oid], start_paused=True))
        task_id = result["task_id"]
        try:
            items = _run(_read_task_items(task_id))
            assert len(items) == 1
            assert items[0][0].startswith("X → 侧脑室")
            # 标记结构性不存在
            outcome = _run(_read_item_outcome(task_id))
            assert outcome == "non_neural_target"
        finally:
            _run(_cleanup([task_id]))
```

并新增 helper(模块级,`_seed_items` 附近):

```python
async def _read_item_outcome(task_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text("SELECT preprocess_outcome FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                {"tid": task_id},
            )
        ).scalar_one()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q`
Expected: FAIL(AttributeError:`module 'paper_evidence_service' has no attribute '_classify_item_target'`)

- [ ] **Step 3: 实现**

`paper_evidence_service.py` 顶部 import:

```python
from app.services.evidence_target_classifier import classify_target
```

`create_batch_task` 的 per-object 循环(当前 `for oid in fresh_ids:` 内,`_batch_scope_label` 之后)插入靶标判定:

```python
    for oid in fresh_ids:
        label, conf = await _batch_scope_label(session, target_type, uuid.UUID(oid))
        # 非神经靶标(脑室/脑脊液/脑膜等):直接标记结构性不存在,不进入论文检索
        target_kind = await _classify_item_target(session, target_type, uuid.UUID(oid))
        preprocess_outcome = "non_neural_target" if target_kind == "non_neural" else None
        task_id = (
            await session.execute(
                text(
                    "INSERT INTO paper_evidence_tasks "
                    "(target_type, target_id, scope, scope_type, mode, max_papers_per_object, status, created_by, "
                    "total_items, config, name, granularity_level, only_oa, confidence_lt, "
                    "stop_after_strong_support, review_status, filter_snapshot, estimated_target_count, "
                    "materialization_status, materialized_target_count) "
                    "VALUES (:tt, :oid, :scope, :scope_type, :mode, :maxp, :status, :cb, 1, CAST(:cfg AS jsonb), "
                    ":name, :gl, :only_oa, :clt, :stop, 'not_started', CAST(:fs AS jsonb), 1, 'completed', 1) "
                    "RETURNING id::text"
                ),
                {
                    "tt": target_type,
                    "oid": uuid.UUID(oid),
                    "scope": scope,
                    "scope_type": scope_type,
                    "mode": mode,
                    "maxp": max_papers_per_object,
                    "status": status,
                    "cb": created_by,
                    "cfg": cfg_json,
                    "name": name,
                    "gl": granularity_level,
                    "only_oa": only_oa,
                    "clt": confidence_lt,
                    "stop": stop_after_strong_support,
                    "fs": json.dumps(snapshot, ensure_ascii=False),
                },
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO paper_evidence_task_items "
                "(task_id, target_type, target_id, label, current_confidence, status, preprocess_outcome) "
                "VALUES (:tid, :tt, :oid, :label, :conf, :status, :po)"
            ),
            {
                "tid": task_id, "tt": target_type, "oid": uuid.UUID(oid), "label": label, "conf": conf,
                "status": "pending", "po": preprocess_outcome,
            },
        )
        await _write_audit(
            session,
            action_type="EVIDENCE_TASK_CREATE",
            entity_type="evidence_task",
            entity_id=uuid.UUID(task_id),
            after_data={
                "target_type": target_type, "target_id": oid, "scope": scope, "mode": mode,
                **({"non_neural_target": True} if preprocess_outcome == "non_neural_target" else {}),
            },
            operator_id=created_by,
            reason=(
                "single-object evidence task created; target is non-neural structure, marked structurally non-existent"
                if preprocess_outcome == "non_neural_target"
                else "single-object evidence task created"
            ),
        )
        task_ids.append(task_id)
```

`create_batch_task` 之前新增 `_classify_item_target`(查镜像行靶标名 → classify):

```python
async def _classify_item_target(
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> str:
    """查镜像行靶标名并分类:connection/projection 取 target_region 名,其余类型返回 unknown。"""
    if target_type not in ("connection", "projection"):
        return "unknown"
    row = (
        await session.execute(
            text(
                "SELECT target_region_name_cn, target_region_name_en "
                "FROM mirror_region_connections WHERE id = :oid"
            ),
            {"oid": target_id},
        )
    ).first()
    if row is None:
        return "unknown"
    return classify_target(row[0], row[1])
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py -q`
Expected: 全部通过(原有用例不受影响:`_classify_item_target` 对 mock 的 `_batch_scope_label` 路径返回 unknown)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_batch.py
git commit -m "feat(evidence): mark non-neural target items as structurally non-existent at creation"
```

---

### Task 3: 后台处理跳过已标记 item(等效不跑检索)

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`_process_batch_item_v2` 开头,约 5093 行)

**Interfaces:**
- Consumes: Task 2 写入的 `preprocess_outcome='non_neural_target'`
- Produces: 已标记 item 处理时直接置 `awaiting_review` 完成(状态推进、无检索/LLM 调用)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_paper_evidence_batch.py` 追加(验证已标记 item 不触发检索调用):

```python
    def test_non_neural_item_skips_search(self):
        oid = str(uuid.uuid4())
        with (
            patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=[oid])),
            patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=[oid])),
            patch.object(pes, "_batch_scope_label", new=AsyncMock(side_effect=lambda s, tt, o: (f"X → 侧脑室", 0.1))),
            patch.object(pes, "_classify_item_target", new=AsyncMock(return_value="non_neural")),
        ):
            result = _run(_make_task_inner(target_ids=[oid], start_paused=True))
        task_id = result["task_id"]
        try:
            with (
                patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value={})),
                patch.object(pes, "search_papers", new=AsyncMock(return_value=[])),
                patch.object(pes, "pack_target_info", new=AsyncMock(return_value={})),
            ):
                _run(_run_loop(task_id))
            # 已标记 item:不触发检索,直接 awaiting_review
            items = _run(_read_task_items(task_id))
            assert items[0][1] == "awaiting_review"
            assert pes.search_papers.await_count == 0  # type: ignore[attr-defined]
        finally:
            _run(_cleanup([task_id]))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q -k non_neural_item_skips_search`
Expected: FAIL(search_papers 被调用,await_count > 0)

- [ ] **Step 3: 实现**

`_process_batch_item_v2` 的 `stage = "search"` 之后、`build_retrieval_context` 之前插入:

```python
        stage = "search"
        try:
            # 非神经靶标:已标记结构性不存在,直接完成(不检索、不调 LLM)
            marked_row = (
                await session.execute(
                    text(
                        "SELECT preprocess_outcome FROM paper_evidence_task_items WHERE id::text = :iid"
                    ),
                    {"iid": item_id},
                )
            ).first()
            if marked_row is not None and marked_row[0] == "non_neural_target":
                await _set_item_stage(
                    session, item_id, "awaiting_review",
                    preprocess_outcome="non_neural_target",
                    finished_preprocessing_at="SQL:now()",
                )
                return
            context = await build_retrieval_context(
```

(原 `context = await build_retrieval_context(` 行保留,缩进不变。)

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_batch.py
git commit -m "feat(evidence): skip paper search for structurally-impossible items"
```

---

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

### Task 5: 晋升跳过治理边

**Files:**
- Modify: `backend/app/services/mirror_promotion_service.py`(或实际晋升入口,先 grep `promotion_status` / `awaiting_promotion` 找到晋升处理函数)

**Interfaces:**
- Consumes: item 的 `preprocess_outcome`('non_neural_target' / 'evidence_negated')
- Produces: 晋升流程跳过这两类对象(不入 final_kg)

- [ ] **Step 1: 定位晋升入口**

Run: `grep -rn "promotion_status" backend/app/services/mirror_promotion_service.py | head -5`(或实际文件名;若文件不存在,`grep -rln "awaiting_promotion" backend/app/services/` 找晋升服务)

- [ ] **Step 2: 写失败测试**

按晋升服务现有测试文件(如 `tests/test_mirror_promotion*.py`)追加:构造 `preprocess_outcome='non_neural_target'` 的对象 → 晋升调用应跳过(不产生 final 行);`evidence_negated` 同理;`no_evidence_found` 不跳过(仍可晋升?——按 spec:无证据不跳过,但晋升需要证据……实际晋升条件以现有服务为准:仅当有 review/evidence 才可晋升。测试断言:治理边即使有 review 也不晋升)。

具体测试以晋升服务实际签名为准(计划落地时按现有测试模式写)。

- [ ] **Step 3: 实现**

晋升处理函数(定位到实际函数)中,对象查询或晋升判定处加入:

```python
            if outcome in ("non_neural_target", "evidence_negated"):
                # 治理边:结构性不存在 / 证据否定 → 永久跳过晋升
                continue  # 或按现有循环结构跳过该对象
```

(`outcome` 来自 item.preprocess_outcome;查询已含该列。)

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_mirror_promotion*.py -q`
Expected: 全部通过(含新增用例)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/<晋升服务>.py backend/tests/<晋升测试>.py
git commit -m "feat(evidence): promotion skips structurally-impossible and negated edges"
```

---

### Task 6: final_kg 历史脏边清理脚本

**Files:**
- Create: `backend/scripts/clean_final_non_neural_edges.py`

**Interfaces:**
- Consumes: Task 1 的 `classify_target`
- Produces: 删除 final_region_connections 中靶标为非神经结构的行(镜像留痕);打印统计

- [ ] **Step 1: 写脚本**

创建 `backend/scripts/clean_final_non_neural_edges.py`:

```python
"""一次性清理:final_kg 中靶标为非神经结构(脑室/脑脊液/脑膜/脉络丛)的连接。

靶标判定:优先 JOIN mirror_region_connections(source_mirror_connection_id)取 target_region 名;
镜像行缺失时回退 raw_payload_json 中的 target 名称字段(如 target_region_name_en/cn)。
仅删除 final 行,镜像数据保留(审计留痕)。

用法: backend/.venv/Scripts/python.exe backend/scripts/clean_final_non_neural_edges.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.evidence_target_classifier import classify_target  # noqa: E402


async def main() -> None:
    if AsyncSessionLocal is None:
        print("AsyncSessionLocal 未初始化,退出。")
        return
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT f.id, m.target_region_name_cn, m.target_region_name_en, f.raw_payload_json "
                    "FROM final_region_connections f "
                    "LEFT JOIN mirror_region_connections m ON m.id = f.source_mirror_connection_id"
                )
            )
        ).all()
        doomed: list[str] = []
        for rid, tgt_cn, tgt_en, raw in rows:
            if tgt_cn or tgt_en:
                kind = classify_target(tgt_cn, tgt_en)
            else:
                payload = raw or {}
                kind = classify_target(
                    payload.get("target_region_name_cn") or payload.get("target_name_cn"),
                    payload.get("target_region_name_en") or payload.get("target_name_en"),
                )
            if kind == "non_neural":
                doomed.append(str(rid))
        if doomed:
            await s.execute(
                text("DELETE FROM final_region_connections WHERE id::text = ANY(:ids)"),
                {"ids": doomed},
            )
            await s.commit()
        print(f"scanned {len(rows)} final connections; deleted {len(doomed)} non-neural-target edges")


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
```

- [ ] **Step 2: 干跑验证(只读统计,不删除)**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services.evidence_target_classifier import classify_target
async def main():
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text(
            'SELECT m.target_region_name_cn, m.target_region_name_en '
            'FROM final_region_connections f LEFT JOIN mirror_region_connections m ON m.id = f.source_mirror_connection_id'
        ))).all()
        n = sum(1 for r in rows if r[0] or r[1] and classify_target(r[0], r[1]) == 'non_neural')
        print('final connections:', len(rows), '| non-neural target (via mirror):', n)
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
"
```

Expected: 打印 final 总数与非神经数(数字按实际库)。

- [ ] **Step 3: 执行清理**

Run: `cd backend && ./.venv/Scripts/python.exe scripts/clean_final_non_neural_edges.py`
Expected: 打印 `scanned N final connections; deleted M non-neural-target edges`(M 为干跑统计数;若 M=0 也正常,说明 final 库无脏边)。

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/clean_final_non_neural_edges.py
git commit -m "feat(evidence): one-off cleanup script for final-KG non-neural-target edges"
```

---

### Task 7: 前端任务卡徽章 + 证据佐证页提示条

**Files:**
- Modify: `frontend/src/pages/evidence-center/components/taskStatus.ts`(状态徽章)
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`(任务卡徽章)
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`(提示条,替换候选工作区)
- Modify: `frontend/src/styles.css`(chip 样式)

**Interfaces:**
- Consumes: item 的 `preprocess_outcome`(前端通过 `listPaperEvidenceTaskItems` 的 `preprocess_outcome` 字段获得;任务卡则需后端任务列表带该字段——若任务列表不含,任务卡徽章可用 `display_name` 兜底判断?不——任务列表需要新增字段。检查 `PaperEvidenceTask` 是否有 `preprocess_outcome`;无则列表接口补上,或任务卡徽章仅在有该字段时显示)

- [ ] **Step 1: 确认数据通路**

Run: `grep -n "preprocess_outcome" frontend/src/api/endpoints.ts | head -3`(item 类型已有);`grep -n "preprocess_outcome" backend/app/services/paper_evidence_service.py | grep list_paper_evidence_tasks -A3`(任务列表是否返回该字段;若否,Task 2 的 item 标记需经列表接口暴露——`list_paper_evidence_tasks` 的 enrich 已查 items(snap),可在输出补 `preprocess_outcome`)。

若任务列表接口未返回 `preprocess_outcome`:在 `_enrich_task_display` 的 items 查询(snap 查询)追加该列并输出到任务字典。

- [ ] **Step 2: 写失败测试(前端)**

`frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` 追加:

```tsx
  it('非神经靶标任务卡显示「结构性不存在」徽章', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't-nn', target_id: 'c1', display_name_cn: '右旁中央 → 右侧脑室', work_status: 'awaiting_review', preprocess_outcome: 'non_neural_target' })],
      total: 1,
    })
    renderModule()
    const card = await screen.findByTestId('evidence-task-card-t-nn')
    expect(within(card).getByText(/结构性不存在/)).toBeTruthy()
  })
```

(若任务列表不返回 preprocess_outcome,则此测试揭示字段缺失 → Step 1 补后端。)

- [ ] **Step 3: 实现(前端)**

`taskStatus.ts` 增加:

```typescript
/** 预处理结果中文标签(对象卡/任务卡徽章) */
export const PREPROCESS_OUTCOME_LABELS: Record<string, string> = {
  non_neural_target: '结构性不存在:靶标为非神经结构',
  evidence_negated: '证据否定',
  no_evidence_found: '无证据',
}
```

`EvidenceTasksModule.tsx` TaskCard:在 meta 行后、有 `task.preprocess_outcome` 且为治理类时渲染徽章:

```tsx
      {(task.preprocess_outcome === 'non_neural_target' || task.preprocess_outcome === 'evidence_negated') && (
        <div className="evidence-task-chip evidence-task-chip-bad" data-testid={`evidence-task-outcome-${task.id}`}>
          {PREPROCESS_OUTCOME_LABELS[task.preprocess_outcome]}
        </div>
      )}
```

`EvidenceCandidatesModule.tsx`:current 存在且 `preprocess_outcome === 'non_neural_target'` 时,替代候选工作区渲染提示条:

```tsx
  const nonNeuralTarget = current?.preprocess_outcome === 'non_neural_target'
  // …在渲染候选工作区的条件处:
  {nonNeuralTarget ? (
    <div className="ontology-page-message evidence-non-neural-banner" data-testid="evidence-non-neural-banner">
      该对象靶标为非神经结构(脑室/脑脊液等),解剖学上不存在投射连接,已标记为不存在。
    </div>
  ) : manualTarget ? ( /* 原候选工作区 */ ) : ( /* 原空态 */ )}
```

(具体插入点以实际 JSX 结构为准:在 `manualTarget && (<PaperSearchPanel …>` 之前拦截,或在外层条件分支。)

`styles.css` 追加:

```css
.evidence-non-neural-banner {
  margin-bottom: 12px;
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: 全部通过(含新增用例)

- [ ] **Step 5: 类型与构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npm run build`
Expected: 0 错误

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/evidence-center/components/taskStatus.ts frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx frontend/src/styles.css frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx
git commit -m "feat(evidence-ui): structurally-impossible badge on task cards + banner on evidence page"
```

---

### Task 8: 全量验收

**Files:**
- 无新文件

**Interfaces:**
- Consumes: 全部前序任务

- [ ] **Step 1: 后端全量**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部通过(含 6 个既有无关失败)

- [ ] **Step 2: 前端全量 + 构建**

Run: `cd frontend && npx vitest run && npm run build`
Expected: 通过(仅既有无关 WIP 失败)+ 0 错误

- [ ] **Step 3: 端到端冒烟**

1. 后端已重启(`cd backend && ./.venv/Scripts/python.exe run_server.py` 后台)。
2. 前端 dev server 运行中(`cd frontend && npm run dev` 后台)。
3. 打开佐证任务页:含「脑室/脑脊液」靶标的任务卡显示「结构性不存在」徽章;点击进入证据佐证页显示提示条,不自动搜索。
4. 创建一个普通连接任务:正常流程;选一个无结果对象,观察反向检索日志(后端日志出现 negative query)。
5. 干跑清理脚本统计(不删除),确认 final 库状态。

- [ ] **Step 4: 提交(如有冒烟修复)**

```bash
git add <修复文件>
git commit -m "fix(evidence): smoke-test fixes"
```
