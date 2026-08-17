# 佐证任务一对一 + 对象命名 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 佐证任务中心改为「一个任务 = 一个知识对象」,任务卡片按对象中英文名+置信度命名,点击卡片直达证据佐证页(与数据中心入口一致)。

**Architecture:** `paper_evidence_tasks` 增加 `target_id` 列,`create_batch_task` 从「1 任务 N item」改为「N 任务 × 1 item」;任务列表接口批量 JOIN 镜像表返回 `display_name_cn/display_name_en/display_confidence`;前端中栏任务卡重写(标题中英文+置信度、整卡跳转 candidates、状态组排序、筛选 chips);存量多对象任务用一次性幂等脚本拆分迁移。

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL(原始 SQL);React 18 + Vite + TypeScript + Vitest + React Testing Library。

**设计文档:** `docs/superpowers/specs/2026-08-17-evidence-tasks-1to1-object-tasks-design.md`(用户已确认)。

## Global Constraints

- **一对一不变量**:每个 `paper_evidence_tasks` 行恰好 1 个 `paper_evidence_task_items` 行,且二者 `target_id` 一致(新代码保证;存量靠迁移)。
- **命名兜底链**:镜像行实时(中英)→ item 快照 label(非 UUID)→「类型中文 #短ID」;置信度:实时 → 快照 → null(前端显示「未评分」)。0.0 是合法置信度,必须用 nullish 判断保留。
- **跳转 URL 与数据中心一致**:`#/validation-center?tab=paper_evidence&module=candidates&task_id=X&target_type=T&target_id=I` + sessionStorage `evidence-center.initial-queue`(用现成的 `navigateToEvidenceCandidates`)。
- **任务 `name` 不再作为卡片标题**,有值时作第三行小字备注。
- **卡片排序**:处理中 → 已暂停 → 待验证 → 已完成 → 部分失败 → 失败;组内置信度升序(null 最前);已取消/空任务不显示。
- **筛选分组**(PRD V4 R4):回路=circuit/circuit_step/circuit_function;连接=connection/projection;功能=region_function/projection_function。
- 后端测试用 `AsyncSessionLocal`(真实测试库);前端测试 vitest + RTL,API 走 `vi.mock('../../../api/endpoints')`。
- 提交信息:英文 conventional commits;backend 与 frontend 改动可同任务提交。

---

### Task 1: 迁移 SQL — paper_evidence_tasks 增加 target_id

**Files:**
- Create: `backend/migrations/20260817_evidence_tasks_target_id.sql`

**Interfaces:**
- Produces: `paper_evidence_tasks.target_id UUID NULL`(Task 3/5/7 使用)

- [ ] **Step 1: 写迁移文件**

```sql
-- 佐证任务一对一:任务行即对象。
-- target_id = 对象身份;新建任务必填,旧行为 NULL(由拆分迁移回填)。
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS target_id UUID;
CREATE INDEX IF NOT EXISTS idx_paper_evidence_tasks_target ON paper_evidence_tasks (target_type, target_id);
```

- [ ] **Step 2: 应用迁移(当前开发库)**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal
async def main():
    sql = open('migrations/20260817_evidence_tasks_target_id.sql', encoding='utf-8').read()
    async with AsyncSessionLocal() as s:
        await s.execute(text(sql))
        await s.commit()
    print('migration applied')
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
"
```

Expected: prints `migration applied`(重跑也安全,`IF NOT EXISTS`)。

- [ ] **Step 3: 验证列存在**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal
async def main():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='paper_evidence_tasks' AND column_name='target_id'\"))
        print('target_id column:', r.scalar_one_or_none())
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
"
```

Expected: `target_id column: target_id`

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/20260817_evidence_tasks_target_id.sql
git commit -m "feat(evidence): add paper_evidence_tasks.target_id for 1:1 object tasks"
```

---

### Task 2: `mirror_live_display_name_parts` 中英双名解析

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(在 `mirror_live_display_name` 函数之后新增)
- Test: `backend/tests/test_paper_evidence_display_parts.py`(新建)

**Interfaces:**
- Produces: `mirror_live_display_name_parts(target_type: str, get) -> tuple[str | None, str | None]` — `get` 为列名取值回调(ORM 行 `getattr`,SQL 行 `mapping.get`);中文缺失仅英文、英文缺失仅中文、皆缺 `(None, None)`。Task 5/7 使用。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_paper_evidence_display_parts.py`:

```python
# -*- coding: utf-8 -*-
"""mirror_live_display_name_parts:中英文双名解析(纯函数,不触库)。"""

from app.services.paper_evidence_service import mirror_live_display_name_parts as parts


def _get(mapping):
    return lambda c: mapping.get(c)


def test_connection_both_languages():
    get = _get({
        "source_region_name_cn": "杏仁核", "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": "Hippocampus",
        "connection_type": "projection",
    })
    cn, en = parts("connection", get)
    assert cn == "杏仁核 → 海马"
    assert en == "Amygdala → Hippocampus"


def test_connection_cn_missing_keeps_en():
    get = _get({
        "source_region_name_cn": None, "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": "Hippocampus",
    })
    cn, en = parts("connection", get)
    assert cn is None
    assert en == "Amygdala → Hippocampus"


def test_connection_en_missing_keeps_cn():
    get = _get({
        "source_region_name_cn": "杏仁核", "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": None,
    })
    cn, en = parts("connection", get)
    assert cn == "杏仁核 → 海马"
    assert en is None


def test_connection_all_missing():
    get = _get({"source_region_name_cn": "", "source_region_name_en": None,
                "target_region_name_cn": "", "target_region_name_en": ""})
    assert parts("connection", get) == (None, None)


def test_circuit_cn_en():
    get = _get({"name_cn": "默认模式网络", "circuit_name": "Default Mode Network"})
    assert parts("circuit", get) == ("默认模式网络", "Default Mode Network")


def test_circuit_cn_only():
    get = _get({"name_cn": "默认模式网络", "circuit_name": None})
    assert parts("circuit", get) == ("默认模式网络", None)


def test_circuit_step_en_only():
    get = _get({"step_name": "input step", "role": "relay"})
    cn, en = parts("circuit_step", get)
    assert cn is None
    assert en == "input step · relay"


def test_circuit_function_cn_en():
    get = _get({"function_term_cn": "记忆巩固", "function_term_en": "memory consolidation"})
    assert parts("circuit_function", get) == ("记忆巩固", "memory consolidation")


def test_region_function_cn_en():
    get = _get({"function_term": "memory consolidation",
                "region_name_cn": "海马", "region_name_en": "Hippocampus"})
    cn, en = parts("region_function", get)
    assert cn == "memory consolidation · 海马"
    assert en == "memory consolidation · Hippocampus"


def test_projection_function_cn_en():
    get = _get({"function_term_cn": "恐惧消退", "function_term": "fear extinction"})
    assert parts("projection_function", get) == ("恐惧消退", "fear extinction")


def test_unknown_type_returns_none_pair():
    assert parts("unknown_type", _get({})) == (None, None)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_display_parts.py -q`
Expected: FAIL(ImportError:`cannot import name 'mirror_live_display_name_parts'`)

- [ ] **Step 3: 实现**

在 `paper_evidence_service.py` 的 `mirror_live_display_name`(约 727 行)之后新增:

```python
def mirror_live_display_name_parts(target_type: str, get) -> tuple[str | None, str | None]:
    """镜像行中英文双名解析:(cn, en)。各自独立缺失为 None;无法解析返回 (None, None)。

    get 为列名取值回调(ORM 行 getattr / SQL 行 mapping.get),与 mirror_live_display_name 共用规则。
    """
    if target_type in ("connection", "projection"):
        src_cn = _pick_cn_en(get, "source_region_name_cn", "source_region_name_en")
        tgt_cn = _pick_cn_en(get, "target_region_name_cn", "target_region_name_en")
        src_en = _clean_text(get("source_region_name_en"))
        tgt_en = _clean_text(get("target_region_name_en"))
        cn = f"{src_cn} → {tgt_cn}" if src_cn and tgt_cn else None
        en = f"{src_en} → {tgt_en}" if src_en and tgt_en else None
        return cn, en
    if target_type == "circuit":
        return _clean_text(get("name_cn")) or None, _clean_text(get("circuit_name")) or None
    if target_type == "circuit_step":
        parts_ = [_clean_text(get("step_name")), _clean_text(get("role"))]
        en = " · ".join(p for p in parts_ if p) or None
        return None, en
    if target_type == "circuit_function":
        return _clean_text(get("function_term_cn")) or None, _clean_text(get("function_term_en")) or None
    if target_type == "region_function":
        term = _clean_text(get("function_term"))
        region_cn = _pick_cn_en(get, "region_name_cn", "region_name_en")
        region_en = _clean_text(get("region_name_en"))
        cn = f"{term} · {region_cn}" if term and region_cn else None
        en = f"{term} · {region_en}" if term and region_en else (term or None)
        return cn, en
    if target_type == "projection_function":
        return _clean_text(get("function_term_cn")) or None, _clean_text(get("function_term")) or None
    return None, None
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_display_parts.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_display_parts.py
git commit -m "feat(evidence): mirror_live_display_name_parts cn/en pair resolver"
```

---

### Task 3: `create_batch_task` 一对一重写 + 更新状态机测试

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(替换 5605 行的 `create_batch_task`;删除 2511 与 2762 行的两个旧同名定义)
- Test: `backend/tests/test_paper_evidence_batch.py`

**Interfaces:**
- Consumes: `_resolve_scope_ids`、`_resolve_scope_ids_low_confidence`、`_build_filter_clause`、`_batch_scope_label`、`_write_audit`、`get_settings`(均已在模块内)
- Produces: `create_batch_task(...) -> {"task_id": <首个>, "task_ids": [<全部>], "target_count": int, "skipped_active_targets": int}`(Task 4/7 使用)

- [ ] **Step 1: 定位三处同名定义并删除前两处**

Run: `grep -n "async def create_batch_task" backend/app/services/paper_evidence_service.py`
Expected: 三处(约 2511 / 2762 / 5605)。

删除前两处:
- 2511 行版本:从 `async def create_batch_task(` 起到 `return {"task_id": task_id, "target_count": len(ids)}`(其后的 `async def run_batch_step` 保留)。
- 2762 行版本:从 `async def create_batch_task(` 起到 `return {"task_id": task_id, "target_count": len(fresh_ids), "skipped_active_targets": len(busy)}`(其后的 `async def _update_task_totals` 保留)。

保留第三处(5605 行版本)待 Step 3 重写。

- [ ] **Step 2: 写失败测试(先改测试,验证新协议)**

`backend/tests/test_paper_evidence_batch.py` 的 `TestBatchStateMachine._make_task` 改为(删除 `_seed_items` 调用,items 由创建路径写入):

```python
    def _make_task(self, target_ids=None, start_paused=False):
        target_ids = target_ids or _ids(3)
        with (
            patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=target_ids)),
            patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=target_ids)),
            patch.object(
                pes,
                "_batch_scope_label",
                new=AsyncMock(side_effect=lambda s, tt, oid: (f"target-{oid}", 0.4)),
            ),
        ):
            return _run(_make_task_inner(target_ids=target_ids, start_paused=start_paused))
```

`test_create_task_creates_items_with_labels` 整体替换为:

```python
    def test_create_task_creates_one_task_per_object_with_labels(self):
        ids = _ids(2)
        result = self._make_task(ids)
        task_ids = result["task_ids"]
        try:
            assert len(task_ids) == 2
            assert result["target_count"] == 2
            assert result["task_id"] == task_ids[0]
            for tid in task_ids:
                row = _run(_read_task_row(tid))
                assert row[0] == "pending"
                assert row[1] == 1  # total_items = 1
                items = _run(_read_task_items(tid))
                assert len(items) == 1
                assert items[0][1] == "pending"
                assert items[0][0].startswith("target-")
        finally:
            _run(_cleanup(task_ids))
```

`test_batch_loop_preprocesses_to_awaiting_review_without_formal_attach` 整体替换为:

```python
    def test_batch_loop_preprocesses_to_awaiting_review_without_formal_attach(self):
        ids = _ids(2)
        result = self._make_task(ids)
        task_ids = result["task_ids"]
        try:
            with (
                patch.object(pes, "pack_target_info", new=AsyncMock(return_value={
                    "function_term": "memory consolidation",
                    "query": '"memory consolidation"',
                    "info": {},
                })),
                patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value={
                    "claim_text": "memory consolidation",
                    "structured_claim": {},
                    "object_type": "connection",
                    "granularity": "macro",
                    "source_region": "Hippocampus",
                    "target_region": "Prefrontal cortex",
                    "source_region_synonyms": [],
                    "target_region_synonyms": [],
                    "function_terms": ["memory consolidation"],
                    "function_synonyms": [],
                    "relation_keywords": ["projection"],
                })),
                patch.object(pes, "search_papers", new=AsyncMock(return_value=[_paper()])),
                patch.object(pes, "fetch_fulltext", new=AsyncMock(return_value="")),
                patch.object(pes, "verify_paper", new=AsyncMock(return_value=_paper())),
                patch.object(pes.pfs, "fetch_oa_fulltext_xml", new=AsyncMock(return_value="")),
                patch.object(pes, "build_search_query", new=AsyncMock(return_value='"memory consolidation"')),
                patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value=_extraction())),
                patch.object(pes, "semantic_filter_papers", new=AsyncMock(side_effect=lambda papers, ctx: (papers, []))),
            ):
                for tid in task_ids:
                    _run(_run_loop(tid))
            for tid in task_ids:
                task = _run(_read_task_row(tid))
                assert task[0] == "completed"
                assert task[1] == 1
                assert task[2] == 1
                items = _run(_read_task_items(tid))
                assert all(i[1] == "awaiting_review" for i in items)
                assert all(i[2] and i[3] and i[4] for i in items)
            ev_count = _run(_count_evidence(ids))
            assert ev_count == 0
        finally:
            _run(_cleanup(task_ids))
            _run(_cleanup_batch_paper())
```

`test_pause_resume_cancel` 改为单对象任务:

```python
    def test_pause_resume_cancel(self):
        result = self._make_task(_ids(1))
        task_id = result["task_id"]
        try:
            _run(_pause(task_id))
            assert _run(_read_status(task_id)) == "paused"
            _run(_resume(task_id))
            assert _run(_read_status(task_id)) == "pending"
            _run(_cancel(task_id))
            assert _run(_read_status(task_id)) == "cancelled"
            assert _run(_count_skipped(task_id)) == 1
        finally:
            _run(_cleanup([task_id]))
```

删除模块级 `_seed_items` 函数(约 239 行,已无调用方)。

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q`
Expected: FAIL(`result["task_ids"]` 不存在 / KeyError)

- [ ] **Step 4: 重写 create_batch_task(5605 行版本)**

将 5605 行的 `create_batch_task` 整体替换为:

```python
async def create_batch_task(
    session: AsyncSession,
    *,
    target_type: str,
    scope: str,
    mode: str,
    max_papers_per_object: int,
    created_by: str | None = None,
    limit: int = 200,
    start_paused: bool = False,
    name: str | None = None,
    granularity_level: str | None = None,
    only_oa: bool = False,
    confidence_lt: float | None = None,
    stop_after_strong_support: bool = False,
    target_ids: list[str] | None = None,
    filter_snapshot: dict | None = None,
) -> dict:
    """一对一佐证任务创建:每个对象生成一个独立任务(1 任务 = 1 item)。

    - 圈选(selected / low_confidence / filter)与单任务最大守卫语义不变;
    - busy 去重统一在创建时完成:跳过已有活动任务的对象并计数返回;
    - item 创建时直接写入实时 label/current_confidence 快照,不依赖物化流程。
    """
    if target_type not in TARGET_MODELS:
        raise ValueError(f"unsupported target_type: {target_type}")
    cfg = get_settings()
    scope_type = "selected" if scope == "selected" else "filter"
    snapshot = (
        {
            "target_type": target_type,
            "granularity_level": granularity_level,
            "target_ids": target_ids or [],
        }
        if scope == "selected"
        else filter_snapshot
        or {
            "target_type": target_type,
            "granularity_level": granularity_level,
            "confidence_lt": confidence_lt if scope == "low_confidence" else None,
        }
    )
    if target_ids:
        ids = target_ids
    elif scope == "low_confidence":
        ids = await _resolve_scope_ids_low_confidence(session, target_type, confidence_lt, limit)
    else:
        where, params = _build_filter_clause(target_type, snapshot)
        rows = (
            await session.execute(
                text(
                    f"SELECT id::text FROM {TARGET_MODELS[target_type].__tablename__} "
                    f"WHERE {where} ORDER BY created_at DESC LIMIT :lim"
                ),
                {**params, "lim": limit},
            )
        ).all()
        ids = [str(r[0]) for r in rows]
    if not ids:
        raise ValueError("no targets matched scope")
    if len(ids) > cfg.paper_evidence_max_task_items:
        raise ValueError(
            f"当前筛选结果共 {len(ids)} 条，单任务最大 {cfg.paper_evidence_max_task_items} 条，"
            "请进一步筛选或拆分任务。"
        )
    busy = set(
        (
            await session.execute(
                text(
                    "SELECT target_id::text FROM paper_evidence_task_items "
                    "WHERE target_type = :tt AND target_id::text = ANY(:ids) "
                    "AND status IN ('pending','searching','paper_found','extracting','awaiting_review')"
                ),
                {"tt": target_type, "ids": ids},
            )
        ).scalars().all()
    )
    fresh_ids = [oid for oid in ids if oid not in busy]
    if not fresh_ids:
        raise ValueError("all matched targets already have an active evidence task")
    cfg_json = json.dumps(
        {"deepseek_concurrency": DEEPSEEK_CONCURRENCY, "europepmc_concurrency": EUROPE_PMC_CONCURRENCY},
        ensure_ascii=False,
    )
    status = "paused" if start_paused else "pending"
    task_ids: list[str] = []
    for oid in fresh_ids:
        label, conf = await _batch_scope_label(session, target_type, uuid.UUID(oid))
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
                "(task_id, target_type, target_id, label, current_confidence, status) "
                "VALUES (:tid, :tt, :oid, :label, :conf, 'pending')"
            ),
            {"tid": task_id, "tt": target_type, "oid": uuid.UUID(oid), "label": label, "conf": conf},
        )
        await _write_audit(
            session,
            action_type="EVIDENCE_TASK_CREATE",
            entity_type="evidence_task",
            entity_id=uuid.UUID(task_id),
            after_data={"target_type": target_type, "target_id": oid, "scope": scope, "mode": mode},
            operator_id=created_by,
            reason="single-object evidence task created",
        )
        task_ids.append(task_id)
    await session.commit()
    return {
        "task_id": task_ids[0],
        "task_ids": task_ids,
        "target_count": len(task_ids),
        "skipped_active_targets": len(busy),
    }
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q`
Expected: 5 passed(`TestBatchStateMachine` 4 个 + `TestReviewQueueStatsAudit` 1 个)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_batch.py
git commit -m "feat(evidence): 1:1 object tasks — create_batch_task emits one task per object"
```

---

### Task 4: 路由调度适配 + phase4/scale/live_fields 测试更新

**Files:**
- Modify: `backend/app/routers/ontology.py`(POST /evidence/batch,约 979-1010 行)
- Modify: `backend/app/services/paper_evidence_service.py`(新增 `execute_paper_evidence_batch_background_many`)
- Test: `backend/tests/test_paper_evidence_batch_phase4.py`、`backend/tests/test_paper_evidence_batch_scale.py`、`backend/tests/test_paper_evidence_live_fields.py`

**Interfaces:**
- Consumes: Task 3 的 `create_batch_task` 新返回(`task_ids`)
- Produces: `execute_paper_evidence_batch_background_many(task_ids: list[str]) -> None`

- [ ] **Step 1: 新增批量执行入口**

在 `execute_paper_evidence_batch_background`(约 3699 行)之后新增:

```python
async def execute_paper_evidence_batch_background_many(task_ids: list[str]) -> None:
    """逐个执行对象任务(单任务内部已有异常兜底,循环保证一个失败不阻断其余)。"""
    for tid in task_ids:
        await execute_paper_evidence_batch_background(tid)
```

- [ ] **Step 2: 修改路由**

`backend/app/routers/ontology.py` 的 `paper_evidence_batch_create` 中,将:

```python
        background_tasks.add_task(pes.materialize_task_items_background, result["task_id"])
        if not body.start_paused:
            background_tasks.add_task(pes.execute_paper_evidence_batch_background, result["task_id"])
        return {**result, "auto_started": not body.start_paused}
```

替换为:

```python
        if result["task_ids"] and not body.start_paused:
            background_tasks.add_task(pes.execute_paper_evidence_batch_background_many, result["task_ids"])
        return {**result, "auto_started": not body.start_paused}
```

(create 已同步写入 item,不再调度物化;execute 内部对已存在 item 幂等。)

- [ ] **Step 3: 更新 phase4 测试**

`backend/tests/test_paper_evidence_batch_phase4.py` 的 `_make_task` 改为(删除 create 后的补插 item 循环):

```python
async def _make_task(ids, scope="low_confidence", limit=10):
    with (
        patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=ids)),
        patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=ids)),
        patch.object(pes, "_batch_scope_label", new=AsyncMock(side_effect=lambda s, tt, oid: (f"t-{oid}", 0.2))),
    ):
        async with AsyncSessionLocal() as s:
            return await pes.create_batch_task(
                s, target_type="connection", scope=scope, mode="function",
                max_papers_per_object=3, created_by="test", limit=limit, name="Phase4 task",
                granularity_level="macro", confidence_lt=0.5,
                target_ids=ids if scope == "selected" else None,
            )
```

`test_batch_preprocessing_never_attaches_and_keeps_confidence` 改为单对象口径:

```python
def test_batch_preprocessing_never_attaches_and_keeps_confidence():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        _run(_run_task(task_id))

        async def check():
            async with AsyncSessionLocal() as s:
                items = (
                    await s.execute(
                        text(
                            "SELECT status, preprocess_outcome, attempt_count, candidate_papers IS NOT NULL "
                            "FROM paper_evidence_task_items WHERE task_id::text=:tid"
                        ),
                        {"tid": task_id},
                    )
                ).all()
                assert len(items) == 1
                assert items[0][0] == "awaiting_review"
                assert items[0][1] == "evidence_found"
                assert items[0][2] == 1
                assert items[0][3]
                dp = (
                    await s.execute(
                        text(
                            "SELECT COUNT(*) FROM paper_evidence_task_item_passages pp "
                            "JOIN paper_evidence_task_items t ON t.id=pp.task_item_id "
                            "WHERE t.task_id::text=:tid"
                        ),
                        {"tid": task_id},
                    )
                ).scalar_one()
                assert dp == 1
                st = (
                    await s.execute(
                        text("SELECT status, review_status, awaiting_review_items FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": task_id},
                    )
                ).first()
                assert st[0] == "completed"
                assert st[1] == "in_review"
                assert st[2] == 1
        _run(check())
    finally:
        _run(_cleanup(task_id))
```

其余 phase4 用例均为单对象(`ids = [str(uuid.uuid4())]`),逻辑不变;仅 `_make_task` 变化使其通过。

- [ ] **Step 4: 更新 scale 测试**

`test_filter_snapshot_and_preview_and_max_limit` 的 create 断言消息不变(新实现保留「单任务最大」文案),无需改。

`test_large_scope_materialization_checkpoint_and_idempotency` 整体替换为(物化被创建时快照取代):

```python
def test_1to1_create_writes_snapshot_and_materialize_is_noop():
    cids = _run(_insert_connections(6))
    try:
        async def case():
            cfg = pes.get_settings()
            old = cfg.paper_evidence_max_task_items
            cfg.paper_evidence_max_task_items = 100000
            async with AsyncSessionLocal() as s:
                task = await pes.create_batch_task(
                    s, target_type="connection", scope="low_confidence", mode="function",
                    max_papers_per_object=3, confidence_lt=0.5, limit=200,
                    filter_snapshot={"confidence_lt": 0.001},
                )
                task_ids = task["task_ids"]
                assert len(task_ids) >= 6
                first = task_ids[0]
                await pes.materialize_task_items_background(first)
                for tid in task_ids:
                    row = (
                        await s.execute(
                            text(
                                "SELECT total_items, materialized_target_count, target_id IS NOT NULL "
                                "FROM paper_evidence_tasks WHERE id::text=:tid"
                            ),
                            {"tid": tid},
                        )
                    ).first()
                    assert row[0] == 1
                    assert row[1] == 1
                    assert row[2] is True
                    count = (
                        await s.execute(
                            text("SELECT COUNT(*) FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                            {"tid": tid},
                        )
                    ).scalar_one()
                    assert count == 1
                    await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
                await s.commit()
            cfg.paper_evidence_max_task_items = old
        _run(case())
    finally:
        _run(_cleanup_connections(cids))
```

`test_materialization_cancel_stops_and_keeps_generated` 整体替换为:

```python
def test_cancel_single_object_task():
    cids = _run(_insert_connections(4))
    try:
        async def case():
            cfg = pes.get_settings()
            old = cfg.paper_evidence_max_task_items
            cfg.paper_evidence_max_task_items = 100000
            async with AsyncSessionLocal() as s:
                task = await pes.create_batch_task(
                    s, target_type="connection", scope="low_confidence", mode="function",
                    max_papers_per_object=3, confidence_lt=0.5, limit=200,
                    filter_snapshot={"confidence_lt": 0.001},
                )
                task_ids = task["task_ids"]
                assert len(task_ids) >= 4
                first = task_ids[0]
                await pes.cancel_batch_task(s, first)
                st = (
                    await s.execute(
                        text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": first},
                    )
                ).first()
                assert st[0] == "cancelled"
                for tid in task_ids:
                    await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
                await s.commit()
            cfg.paper_evidence_max_task_items = old
        _run(case())
    finally:
        _run(_cleanup_connections(cids))
```

`test_versions_written_on_items`、`test_draft_revision_optimistic_concurrency`、`test_dual_worker_skip_locked_no_overlap` 的 create 后补插 item 循环已被创建路径取代,删除其 INSERT 循环即可;三者的清理段改为删除全部 task_ids:

```python
                for tid in task["task_ids"]:
                    await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
```

- [ ] **Step 5: 更新 live_fields 测试取数解耦**

`backend/tests/test_paper_evidence_live_fields.py` 的 `_make_task` 整体替换为直接 SQL 建任务(该文件测试列表/物化逻辑,不再依赖 create):

```python
async def _make_task(session, ids: list[str]) -> str:
    tid = (
        await session.execute(
            text(
                "INSERT INTO paper_evidence_tasks "
                "(target_type, scope, mode, max_papers_per_object, status, total_items) "
                "VALUES ('connection', 'selected', 'existence', 3, 'paused', :n) RETURNING id::text"
            ),
            {"n": len(ids)},
        )
    ).scalar_one()
    return tid
```

删除该文件中未再使用的 `from unittest.mock import patch`(若 `count_scope_targets` patch 随之消失)。

- [ ] **Step 6: 运行确认通过**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py tests/test_paper_evidence_batch_scale.py tests/test_paper_evidence_live_fields.py -q
```

Expected: 全部通过(phase4 10 个、scale 6 个、live_fields 11 个)。

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/ontology.py backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_batch_phase4.py backend/tests/test_paper_evidence_batch_scale.py backend/tests/test_paper_evidence_live_fields.py
git commit -m "feat(evidence): route batch create through per-task execution; adapt phase4/scale/live tests"
```

---

### Task 5: 任务列表/详情接口补 display 字段(中英名+置信度)

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`list_paper_evidence_tasks`、`get_batch_task`、新增 `_enrich_task_display`)
- Test: `backend/tests/test_paper_evidence_task_display.py`(新建)

**Interfaces:**
- Consumes: Task 2 的 `mirror_live_display_name_parts`;`TARGET_MODELS`、`_LIVE_NAME_COLUMNS`、`mirror_live_confidence`、`_UUID_RE`、`TARGET_TYPE_LABELS_CN`(均已在模块内)
- Produces: 任务列表/详情每个任务新增 `target_id`、`display_name_cn`、`display_name_en`、`display_confidence`、`display_name_source`('mirror_live'|'task_snapshot'|'fallback'|'missing')、`display_confidence_source`('mirror_live'|'task_snapshot'|'missing')。Task 6/前端使用。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_paper_evidence_task_display.py`:

```python
# -*- coding: utf-8 -*-
"""任务列表/详情 display 字段:中英名+置信度、兜底链、无 N+1。"""

from __future__ import annotations

import asyncio
import json
import uuid

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _insert_task(tt, oid, *, label, conf, summary_counts=True):
    async with AsyncSessionLocal() as s:
        tid = (
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_tasks "
                    "(target_type, target_id, scope, mode, max_papers_per_object, status, total_items, summary) "
                    "VALUES (:tt, :oid, 'selected', 'function', 3, 'pending', 1, :sm) RETURNING id::text"
                ),
                {
                    "tt": tt,
                    "oid": uuid.UUID(oid),
                    "sm": json.dumps({"counts": {"pending": 1}}) if summary_counts else None,
                },
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO paper_evidence_task_items "
                "(task_id, target_type, target_id, label, current_confidence, status) "
                "VALUES (:tid, :tt, :oid, :lbl, :conf, 'pending')"
            ),
            {"tid": tid, "tt": tt, "oid": uuid.UUID(oid), "lbl": label, "conf": conf},
        )
        await s.commit()
        return tid


async def _insert_connection(oid, *, src_cn="杏仁核", src_en="Amygdala", tgt_cn="海马", tgt_en="Hippocampus", confidence=0.35):
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO mirror_region_connections "
                "(id, source_region_name_cn, source_region_name_en, target_region_name_cn, target_region_name_en, "
                "connection_type, confidence, granularity_level, source_atlas) "
                "VALUES (:id, :sc, :se, :tc, :te, 'projection', :conf, 'macro', 'AAL3')"
            ),
            {"id": uuid.UUID(oid), "sc": src_cn, "se": src_en, "tc": tgt_cn, "te": tgt_en, "conf": confidence},
        )
        await s.commit()


async def _cleanup(task_ids, conn_ids):
    async with AsyncSessionLocal() as s:
        for tid in task_ids:
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
        for cid in conn_ids:
            await s.execute(text("DELETE FROM mirror_region_connections WHERE id::text=:cid"), {"cid": cid})
        await s.commit()


def test_list_tasks_returns_cn_en_and_confidence():
    oid = str(uuid.uuid4())
    task_ids: list[str] = []
    try:
        _run(_insert_connection(oid, confidence=0.35))
        task_ids.append(_run(_insert_task("connection", oid, label=str(uuid.uuid4()), conf=None)))

        async def case():
            async with AsyncSessionLocal() as s:
                resp = await pes.list_paper_evidence_tasks(s, limit=10)
                task = next(t for t in resp["items"] if t["id"] == task_ids[0])
                assert task["target_id"] == oid
                assert task["display_name_cn"] == "杏仁核 → 海马"
                assert task["display_name_en"] == "Amygdala → Hippocampus"
                assert task["display_confidence"] == 0.35
                assert task["display_name_source"] == "mirror_live"
                assert task["display_confidence_source"] == "mirror_live"
        _run(case())
    finally:
        _run(_cleanup(task_ids, [oid]))


def test_get_task_returns_display_fields():
    oid = str(uuid.uuid4())
    task_ids: list[str] = []
    try:
        _run(_insert_connection(oid, confidence=0.35))
        task_ids.append(_run(_insert_task("connection", oid, label=str(uuid.uuid4()), conf=None)))

        async def case():
            async with AsyncSessionLocal() as s:
                resp = await pes.get_batch_task(s, task_ids[0])
                task = resp["task"]
                assert task["display_name_cn"] == "杏仁核 → 海马"
                assert task["display_confidence"] == 0.35
        _run(case())
    finally:
        _run(_cleanup(task_ids, [oid]))


def test_missing_mirror_row_falls_back_to_snapshot_then_short_id():
    ghost = str(uuid.uuid4())
    task_ids: list[str] = []
    try:
        # 快照 label 非 UUID → task_snapshot
        task_ids.append(_run(_insert_task("connection", ghost, label="BLA → IL", conf=0.7)))
        # 快照 label 为 UUID → 类型中文 #短ID
        ghost2 = str(uuid.uuid4())
        task_ids.append(_run(_insert_task("connection", ghost2, label=str(uuid.uuid4()), conf=None)))

        async def case():
            async with AsyncSessionLocal() as s:
                resp = await pes.list_paper_evidence_tasks(s, limit=10)
                t1 = next(t for t in resp["items"] if t["id"] == task_ids[0])
                assert t1["display_name_cn"] == "BLA → IL"
                assert t1["display_name_source"] == "task_snapshot"
                assert t1["display_confidence"] == 0.7
                assert t1["display_confidence_source"] == "task_snapshot"
                t2 = next(t for t in resp["items"] if t["id"] == task_ids[1])
                assert t2["display_name_cn"] == f"连接 #{ghost2[:8]}"
                assert t2["display_name_source"] == "fallback"
                assert t2["display_confidence"] is None
                assert t2["display_confidence_source"] == "missing"
        _run(case())
    finally:
        _run(_cleanup(task_ids, []))


def test_list_tasks_no_n1():
    conn_ids = []
    task_ids: list[str] = []
    try:
        async def seed():
            async with AsyncSessionLocal() as s:
                for _ in range(5):
                    cid = str(uuid.uuid4())
                    conn_ids.append(cid)
                    await s.execute(
                        text(
                            "INSERT INTO mirror_region_connections "
                            "(id, source_region_name_en, target_region_name_en, connection_type, confidence, "
                            "granularity_level, source_atlas) "
                            "VALUES (:id, 'A', 'B', 'projection', 0.1, 'macro', 'AAL3')"
                        ),
                        {"id": uuid.UUID(cid)},
                    )
                    tid = (
                        await s.execute(
                            text(
                                "INSERT INTO paper_evidence_tasks "
                                "(target_type, target_id, scope, mode, max_papers_per_object, status, total_items, summary) "
                                "VALUES ('connection', :oid, 'selected', 'function', 3, 'pending', 1, "
                                "'{\"counts\":{\"pending\":1}}'::jsonb) RETURNING id::text"
                            ),
                            {"oid": uuid.UUID(cid)},
                        )
                    ).scalar_one()
                    task_ids.append(tid)
                    await s.execute(
                        text(
                            "INSERT INTO paper_evidence_task_items "
                            "(task_id, target_type, target_id, label, status) "
                            "VALUES (:tid, 'connection', :oid, 'x', 'pending')"
                        ),
                        {"tid": tid, "oid": uuid.UUID(cid)},
                    )
                await s.commit()
        _run(seed())

        class CountingSession:
            def __init__(self, inner):
                self.inner = inner
                self.selects = 0

            async def execute(self, stmt, params=None):
                if str(stmt).lstrip().upper().startswith("SELECT"):
                    self.selects += 1
                return await self.inner.execute(stmt, params)

            def __getattr__(self, name):
                return getattr(self.inner, name)

        async def case():
            async with AsyncSessionLocal() as s:
                proxy = CountingSession(s)
                await pes.list_paper_evidence_tasks(proxy, limit=10)
                # 任务列表 + COUNT + 镜像表批量 JOIN(仅 1 种 target_type)= 3 次 SELECT
                assert proxy.selects == 3, f"expected 3 SELECT, got {proxy.selects}"
        _run(case())
    finally:
        _run(_cleanup(task_ids, conn_ids))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_task_display.py -q`
Expected: FAIL(KeyError: 'target_id' / 'display_name_cn')

- [ ] **Step 3: 实现 `_enrich_task_display`**

在 `_build_capabilities` 之后新增:

```python
async def _enrich_task_display(session: AsyncSession, tasks: list[dict]) -> list[dict]:
    """为任务字典补充 display_name_cn/display_name_en/display_confidence 与来源标记(批量,无 N+1)。

    - target_id 为 NULL 的旧任务:从其 items 取唯一对象的 target_id 与快照;
    - 按 target_type 分组批量 JOIN 镜像表取实时中英名与置信度;
    - 兜底:镜像行缺失 → 非 UUID 快照 label → 「类型中文 #短ID」;置信度实时 → 快照 → None。
    """
    if not tasks:
        return tasks
    snap: dict[str, dict] = {}
    need_item = [t["id"] for t in tasks if not t.get("target_id")]
    if need_item:
        rows = (
            await session.execute(
                text(
                    "SELECT DISTINCT ON (task_id) task_id::text, target_id::text, label, current_confidence "
                    "FROM paper_evidence_task_items WHERE task_id::text = ANY(:ids) "
                    "ORDER BY task_id, updated_at DESC"
                ),
                {"ids": need_item},
            )
        ).all()
        for r in rows:
            snap[r[0]] = {
                "target_id": r[1],
                "label": r[2],
                "confidence": float(r[3]) if r[3] is not None else None,
            }
    by_type: dict[str, list[str]] = {}
    for t in tasks:
        oid = t.get("target_id") or snap.get(t["id"], {}).get("target_id")
        if oid and t["target_type"] in TARGET_MODELS:
            by_type.setdefault(t["target_type"], []).append(oid)
    live: dict[tuple[str, str], dict] = {}
    for tt, oids in by_type.items():
        table = TARGET_MODELS[tt]
        name_cols = _LIVE_NAME_COLUMNS.get(tt, "")
        sel = ", ".join(f"m.{c}" for c in name_cols.split(", ")) if name_cols else ""
        sel = (sel + ", " if sel else "") + "m.confidence AS live_confidence"
        if tt == "circuit_function":
            sel += ", m.confidence_score"
        rows = (
            await session.execute(
                text(
                    f"SELECT m.id, {sel} FROM {table.__tablename__} m WHERE m.id = ANY(:ids)"
                ),
                {"ids": [uuid.UUID(o) for o in oids]},
            )
        ).all()
        for r in rows:
            live[(tt, str(r._mapping["id"]))] = r._mapping
    out: list[dict] = []
    for t in tasks:
        tt = t["target_type"]
        oid = t.get("target_id") or snap.get(t["id"], {}).get("target_id")
        m = live.get((tt, oid)) if oid else None
        cn = en = None
        conf = None
        name_src = "missing"
        if m is not None:
            cn, en = mirror_live_display_name_parts(tt, m.get)
            conf = mirror_live_confidence(tt, m.get)
            if cn is not None or en is not None:
                name_src = "mirror_live"
        if cn is None and en is None:
            lbl = snap.get(t["id"], {}).get("label")
            if lbl and not _UUID_RE.fullmatch(str(lbl)):
                cn, name_src = str(lbl), "task_snapshot"
            elif oid:
                cn = f"{TARGET_TYPE_LABELS_CN.get(tt, tt)} #{oid[:8]}"
                name_src = "fallback"
        if conf is None:
            sn = snap.get(t["id"], {}).get("confidence")
            if sn is not None:
                conf, conf_src = sn, "task_snapshot"
            else:
                conf_src = "mirror_live" if m is not None else "missing"
        else:
            conf_src = "mirror_live"
        out.append(
            {
                **t,
                "display_name_cn": cn,
                "display_name_en": en,
                "display_confidence": conf,
                "display_name_source": name_src,
                "display_confidence_source": conf_src,
            }
        )
    return out
```

- [ ] **Step 4: 接入两个接口**

`list_paper_evidence_tasks`(约 3923 行):
1. SELECT 列表末尾追加 `, target_id`(在 `confidence_lt` 之后)→ `r[23]`。
2. 字典构造中追加 `"target_id": r[23],`。
3. 在 `return {"items": items, "total": total}` 前改为 `return {"items": await _enrich_task_display(session, items), "total": total}`。

`get_batch_task`(约 4007 行):
1. SELECT 末尾(`materialization_error` 之后)追加 `, target_id` → `task[29]`。
2. 任务字典中追加 `"target_id": task[29],`。
3. `return` 前,将 `"task"` 值改为 `(await _enrich_task_display(session, [task_dict]))[0]`(先组字典、后 enrich、再返回)。

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_task_display.py -q`
Expected: 4 passed

- [ ] **Step 6: 回归**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py tests/test_paper_evidence_live_fields.py tests/test_paper_evidence_work_status.py -q`
Expected: 全部通过

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_task_display.py
git commit -m "feat(evidence): task list/detail display fields (cn/en name + confidence, no N+1)"
```

---

### Task 6: 统一任务端点 label 改用对象名

**Files:**
- Modify: `backend/app/routers/unified_tasks.py`(`_paper_evidence`,约 228-258 行)

**Interfaces:**
- Consumes: Task 5 的 `display_name_cn/display_name_en`

- [ ] **Step 1: 修改 label**

将 `_paper_evidence` 中的:

```python
                    label=f"论文佐证 · {item['target_type']}",
```

替换为:

```python
                    label=(
                        item.get("display_name_cn")
                        or item.get("display_name_en")
                        or f"论文佐证 · {item['target_type']}"
                    ),
```

- [ ] **Step 2: 运行相关测试确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q -k "unified or tasks_runs"`
Expected: 无失败(若环境无该关键字测试,0 收集也算通过;随后跑 Task 12 全量回归兜底)

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/unified_tasks.py
git commit -m "feat(evidence): unified task label uses object display name"
```

---

### Task 7: 存量拆分迁移(migrate_tasks_to_1to1 + 脚本 + 测试)

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(新增 `migrate_tasks_to_1to1`)
- Create: `backend/scripts/migrate_evidence_tasks_1to1.py`
- Test: `backend/tests/test_paper_evidence_migrate_1to1.py`(新建)

**Interfaces:**
- Consumes: `_batch_scope_label`、`_UUID_RE`(模块内)
- Produces: `migrate_tasks_to_1to1(session) -> {"tasks_scanned": int, "tasks_split": int, "objects_migrated": int, "labels_backfilled": int, "target_ids_backfilled": int}`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_paper_evidence_migrate_1to1.py`:

```python
# -*- coding: utf-8 -*-
"""存量拆分迁移:拆分/幂等/审计标记/快照回填。"""

from __future__ import annotations

import asyncio
import json
import uuid

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _insert_legacy_multi_task(n=3) -> tuple[str, list[str]]:
    oids = [str(uuid.uuid4()) for _ in range(n)]
    async with AsyncSessionLocal() as s:
        tid = (
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_tasks "
                    "(target_type, scope, mode, max_papers_per_object, status, total_items) "
                    "VALUES ('connection', 'low_confidence', 'function', 3, 'pending', :n) RETURNING id::text"
                ),
                {"n": n},
            )
        ).scalar_one()
        for oid in oids:
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                    "VALUES (:tid, 'connection', :oid, :lbl, 'pending')"
                ),
                {"tid": tid, "oid": oid, "lbl": str(uuid.uuid4())},
            )
        await s.commit()
        return tid, oids


async def _migrate():
    async with AsyncSessionLocal() as s:
        return await pes.migrate_tasks_to_1to1(s)


async def _cleanup(ids: list[str]):
    async with AsyncSessionLocal() as s:
        for tid in ids:
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
        await s.commit()


def test_split_multi_object_task_and_idempotent():
    tid, oids = _run(_insert_legacy_multi_task(3))
    new_ids: list[str] = []
    try:
        stats = _run(_migrate())
        assert stats["tasks_split"] >= 1
        assert stats["objects_migrated"] >= 3

        async def check():
            nonlocal new_ids
            async with AsyncSessionLocal() as s:
                old = (
                    await s.execute(
                        text("SELECT status, summary FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": tid},
                    )
                ).first()
                assert old[0] == "cancelled"
                assert isinstance(old[1], dict) and old[1].get("migrated_to")
                new_ids = old[1]["migrated_to"]
                assert len(new_ids) == 3
                for nid in new_ids:
                    row = (
                        await s.execute(
                            text(
                                "SELECT target_id IS NOT NULL, total_items, scope, mode "
                                "FROM paper_evidence_tasks WHERE id::text=:nid"
                            ),
                            {"nid": nid},
                        )
                    ).first()
                    assert row[0] is True
                    assert row[1] == 1
                    assert row[2] == "low_confidence"
                    assert row[3] == "function"
                    items = (
                        await s.execute(
                            text("SELECT COUNT(*) FROM paper_evidence_task_items WHERE task_id::text=:nid"),
                            {"nid": nid},
                        )
                    ).scalar_one()
                    assert items == 1
        _run(check())
        # 幂等:旧任务已 cancelled,不在扫描范围,不再产生新拆分
        stats2 = _run(_migrate())
        async def verify_idempotent():
            async with AsyncSessionLocal() as s:
                rows = (
                    await s.execute(
                        text("SELECT id::text FROM paper_evidence_tasks WHERE summary->>'migrated_to' IS NOT NULL"),
                    )
                ).scalars().all()
                assert tid in set(rows)
        _run(verify_idempotent())
    finally:
        _run(_cleanup([tid, *new_ids]))


def test_single_object_task_gets_target_id_backfilled():
    oid = str(uuid.uuid4())
    tid: str | None = None
    try:
        async def seed():
            nonlocal tid
            async with AsyncSessionLocal() as s:
                tid = (
                    await s.execute(
                        text(
                            "INSERT INTO paper_evidence_tasks "
                            "(target_type, scope, mode, max_papers_per_object, status, total_items) "
                            "VALUES ('connection', 'low_confidence', 'function', 3, 'pending', 1) RETURNING id::text"
                        ),
                    )
                ).scalar_one()
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                        "VALUES (:tid, 'connection', :oid, :lbl, 'pending')"
                    ),
                    {"tid": tid, "oid": oid, "lbl": str(uuid.uuid4())},
                )
                await s.commit()
        _run(seed())
        _run(_migrate())

        async def check():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text("SELECT target_id::text, status FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": tid},
                    )
                ).first()
                assert row[0] == oid
                assert row[1] == "pending"  # 不拆分、不取消
        _run(check())
    finally:
        _run(_cleanup([tid]))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_migrate_1to1.py -q`
Expected: FAIL(AttributeError:`module 'paper_evidence_service' has no attribute 'migrate_tasks_to_1to1'`)

- [ ] **Step 3: 实现迁移函数**

在 `paper_evidence_service.py` 的 `recover_interrupted_batch_tasks` 之后新增:

```python
async def migrate_tasks_to_1to1(session: AsyncSession) -> dict:
    """存量拆分迁移(幂等):多对象任务按对象拆成一对一任务;旧任务标记 cancelled + migrated_to。

    - 单对象任务:回填任务 target_id 与 item 快照(label 为 UUID/空、置信度 NULL 时实时取);
    - 多对象任务:每 item 生成一个新任务(复制配置与状态),item 挂接过去,旧任务 cancelled;
    - 仅扫描 status <> 'cancelled' 的任务,已拆任务自然跳过(幂等)。
    """
    rows = (
        await session.execute(
            text(
                "SELECT id::text, target_type, scope, mode, max_papers_per_object, status, name, "
                "granularity_level, only_oa, confidence_lt, stop_after_strong_support, config, created_by "
                "FROM paper_evidence_tasks WHERE status <> 'cancelled' ORDER BY created_at"
            )
        )
    ).all()
    stats = {
        "tasks_scanned": len(rows),
        "tasks_split": 0,
        "objects_migrated": 0,
        "labels_backfilled": 0,
        "target_ids_backfilled": 0,
    }
    for r in rows:
        tid, tt, scope, mode, maxp, status, name, gl, only_oa, clt, stop, config, created_by = r
        items = (
            await session.execute(
                text(
                    "SELECT id::text, target_id::text, label, current_confidence FROM paper_evidence_task_items "
                    "WHERE task_id::text = :tid ORDER BY updated_at"
                ),
                {"tid": tid},
            )
        ).all()
        if not items:
            continue
        if len(items) == 1:
            oid = uuid.UUID(items[0][1])
            label, conf = await _batch_scope_label(session, tt, oid)
            if str(label) == str(oid):
                label = None
            if (not items[0][2] or _UUID_RE.fullmatch(str(items[0][2]))) or items[0][3] is None:
                await session.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET label=COALESCE(:lbl, label), "
                        "current_confidence=COALESCE(:conf, current_confidence) WHERE id::text=:iid"
                    ),
                    {"lbl": label, "conf": conf, "iid": items[0][0]},
                )
                stats["labels_backfilled"] += 1
            await session.execute(
                text("UPDATE paper_evidence_tasks SET target_id=:oid, total_items=1 WHERE id::text=:tid"),
                {"oid": oid, "tid": tid},
            )
            stats["target_ids_backfilled"] += 1
            continue
        new_ids: list[str] = []
        for iid, oid_s, lbl, conf in items:
            oid = uuid.UUID(oid_s)
            label, live_conf = await _batch_scope_label(session, tt, oid)
            if str(label) == str(oid):
                label = None
            new_id = (
                await session.execute(
                    text(
                        "INSERT INTO paper_evidence_tasks "
                        "(target_type, target_id, scope, mode, max_papers_per_object, status, name, "
                        "granularity_level, only_oa, confidence_lt, stop_after_strong_support, config, "
                        "created_by, total_items, review_status, materialization_status, materialized_target_count) "
                        "VALUES (:tt, :oid, :scope, :mode, :maxp, :status, :name, :gl, :only_oa, :clt, :stop, "
                        "COALESCE(:config, '{}'::jsonb), :cb, 1, 'not_started', 'completed', 1) RETURNING id::text"
                    ),
                    {
                        "tt": tt,
                        "oid": oid,
                        "scope": scope,
                        "mode": mode,
                        "maxp": maxp,
                        "status": status,
                        "name": name,
                        "gl": gl,
                        "only_oa": only_oa,
                        "clt": clt,
                        "stop": stop,
                        "config": config,
                        "cb": created_by,
                    },
                )
            ).scalar_one()
            if not lbl or _UUID_RE.fullmatch(str(lbl)):
                await session.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET task_id=:new, label=COALESCE(:lbl, label), "
                        "current_confidence=COALESCE(:conf, current_confidence) WHERE id::text=:iid"
                    ),
                    {"new": uuid.UUID(new_id), "lbl": label, "conf": live_conf, "iid": iid},
                )
                stats["labels_backfilled"] += 1
            else:
                await session.execute(
                    text("UPDATE paper_evidence_task_items SET task_id=:new WHERE id::text=:iid"),
                    {"new": uuid.UUID(new_id), "iid": iid},
                )
            new_ids.append(new_id)
        await session.execute(
            text(
                "UPDATE paper_evidence_tasks SET status='cancelled', "
                "summary=jsonb_set(COALESCE(summary, '{}'::jsonb), '{migrated_to}', CAST(:ids AS jsonb)) "
                "WHERE id::text=:tid"
            ),
            {"ids": json.dumps(new_ids), "tid": tid},
        )
        stats["tasks_split"] += 1
        stats["objects_migrated"] += len(new_ids)
    await session.commit()
    return stats
```

- [ ] **Step 4: 写运行脚本**

创建 `backend/scripts/migrate_evidence_tasks_1to1.py`:

```python
"""一次性存量迁移:多对象佐证任务 → 一对一对象任务(幂等,可重复执行)。

用法: backend/.venv/Scripts/python.exe backend/scripts/migrate_evidence_tasks_1to1.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services import paper_evidence_service as pes  # noqa: E402


async def main() -> None:
    if AsyncSessionLocal is None:
        print("AsyncSessionLocal 未初始化(数据库未配置),退出。")
        return
    async with AsyncSessionLocal() as session:
        stats = await pes.migrate_tasks_to_1to1(session)
    print("迁移完成:", stats)


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_migrate_1to1.py -q`
Expected: 2 passed

- [ ] **Step 6: 对开发库执行迁移(真实数据)**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe scripts/migrate_evidence_tasks_1to1.py
```

Expected: 打印 `迁移完成: {'tasks_scanned': N, 'tasks_split': M, ...}`(M ≥ 1,现库有多对象任务)。重复执行一遍确认幂等(第二次 `tasks_split` 为 0 或仅剩漏网之鱼)。

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/scripts/migrate_evidence_tasks_1to1.py backend/tests/test_paper_evidence_migrate_1to1.py
git commit -m "feat(evidence): idempotent 1:1 split migration for legacy batch tasks"
```

---

### Task 8: 前端 API 类型(endpoints.ts)

**Files:**
- Modify: `frontend/src/api/endpoints.ts`(`PaperEvidenceTask`,约 5677-5711 行;`createPaperEvidenceBatch` 返回类型,约 5713-5730 行)

**Interfaces:**
- Produces: `PaperEvidenceTask` 新字段(前端 Task 9/10 使用);`createPaperEvidenceBatch` 返回 `task_ids`

- [ ] **Step 1: 修改类型**

`PaperEvidenceTask` 接口在 `confidence_lt: number | null` 之后追加:

```typescript
  /** 对象身份(一对一任务);旧任务迁移前为 null */
  target_id: string | null
  /** 任务级对象展示名(中文;镜像行实时,缺失回退快照/兜底) */
  display_name_cn: string | null
  /** 任务级对象展示名(英文;仅镜像行实时) */
  display_name_en: string | null
  /** 任务级展示置信度(实时 → 快照 → null=未评分) */
  display_confidence: number | null
  display_name_source: 'mirror_live' | 'task_snapshot' | 'fallback' | 'missing'
  display_confidence_source: 'mirror_live' | 'task_snapshot' | 'missing'
```

`createPaperEvidenceBatch` 返回类型改为:

```typescript
) => postJson<{ task_id: string; task_ids: string[]; target_count: number; skipped_active_targets: number; auto_started: boolean }>(
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: 0 errors(仅类型扩展,无调用方受影响)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/endpoints.ts
git commit -m "feat(evidence-ui): task display fields + task_ids types"
```

---

### Task 9: taskStatus 卡片标题工具 + 测试

**Files:**
- Modify: `frontend/src/pages/evidence-center/components/taskStatus.ts`
- Test: `frontend/src/pages/evidence-center/components/taskStatus.test.ts`(新建)

**Interfaces:**
- Produces: `objectCardTitle(cn: string | null | undefined, en: string | null | undefined, fallback: string): string`(Task 10 使用)

- [ ] **Step 1: 写失败测试**

创建 `taskStatus.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { objectCardTitle } from './taskStatus'

describe('objectCardTitle(中文为主+英文括号)', () => {
  it('中英皆有:中文 (英文)', () => {
    expect(objectCardTitle('杏仁核 → 海马', 'Amygdala → Hippocampus', '兜底')).toBe('杏仁核 → 海马 (Amygdala → Hippocampus)')
  })
  it('仅中文:只显示中文', () => {
    expect(objectCardTitle('默认模式网络', null, '兜底')).toBe('默认模式网络')
  })
  it('仅英文:只显示英文', () => {
    expect(objectCardTitle(null, 'Amygdala → Hippocampus', '兜底')).toBe('Amygdala → Hippocampus')
  })
  it('中英相同:不重复括号', () => {
    expect(objectCardTitle('R1→R2', 'R1→R2', '兜底')).toBe('R1→R2')
  })
  it('皆空/空白:回退兜底', () => {
    expect(objectCardTitle(null, null, '连接 #abc12345')).toBe('连接 #abc12345')
    expect(objectCardTitle('  ', '', '连接 #abc12345')).toBe('连接 #abc12345')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/taskStatus.test.ts`
Expected: FAIL(`objectCardTitle is not a function`)

- [ ] **Step 3: 实现**

在 `taskStatus.ts` 的 `taskTitle` 函数之后新增:

```typescript
/** 对象卡片标题:中文 (英文);中文缺失只用英文;中英相同不重复;皆空回退兜底名 */
export function objectCardTitle(
  cn: string | null | undefined,
  en: string | null | undefined,
  fallback: string,
): string {
  const c = cn?.trim() || ''
  const e = en?.trim() || ''
  if (!c && !e) return fallback
  if (!c) return e
  if (!e || e === c) return c
  return `${c} (${e})`
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/taskStatus.test.ts`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/evidence-center/components/taskStatus.ts frontend/src/pages/evidence-center/components/taskStatus.test.ts
git commit -m "feat(evidence-ui): objectCardTitle cn-first-with-en-parens helper"
```

---

### Task 10: EvidenceTasksModule 重写(对象卡+跳转+排序+筛选)+ 测试重写

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`(整文件重写)
- Test: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`(整文件重写)

**Interfaces:**
- Consumes: Task 8 类型、Task 9 `objectCardTitle`、现有 `navigateToEvidenceCandidates`(`evidenceCenterUrl.ts`)、`useEvidenceTaskItems`、`useTaskItemsRefresh`、`CreateBatchTaskDialog`、`ConfirmDialog`
- Produces: 中栏任务卡列表(整卡跳转 candidates);不导出新符号

- [ ] **Step 1: 重写测试**

`EvidenceTasksModule.test.tsx` 整体替换为:

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { EvidenceTasksModule } from './EvidenceTasksModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  pausePaperEvidenceTask: vi.fn(),
  resumePaperEvidenceTask: vi.fn(),
  retryPaperEvidenceTask: vi.fn(),
  previewEvidenceBatchScope: vi.fn(),
  createPaperEvidenceBatch: vi.fn(),
}))

function makeTask(overrides: Record<string, unknown>) {
  return {
    id: 't1', target_type: 'connection', target_id: 'c1', name: null, status: 'pending',
    total_items: 1, processed_items: 0, awaiting_review_items: 1, failed_items: 0,
    review_status: 'not_started', granularity_level: 'macro', estimated_target_count: 1,
    materialized_target_count: 1, scope: 'low_confidence', mode: 'function', max_papers_per_object: 3,
    created_at: '2026-08-17T00:00:00Z', created_by: null, started_at: null, finished_at: null,
    error_message: null, materialization_status: 'completed', materialization_cursor: null,
    materialization_error: null, confidence_lt: null, only_oa: false,
    stop_after_strong_support: false, summary: null, scope_type: 'filter',
    filter_snapshot: null, versions: null,
    display_name_cn: '杏仁核 → 海马', display_name_en: 'Amygdala → Hippocampus',
    display_confidence: 0.35, display_name_source: 'mirror_live', display_confidence_source: 'mirror_live',
    work_status: 'awaiting_review',
    item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 },
    capabilities: { can_continue_review: true, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false },
    ...overrides,
  }
}

function renderModule(hash = '#/evidence-center?module=tasks') {
  window.location.hash = hash
  return render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
}

describe('EvidenceTasksModule(对象级任务卡:命名/跳转/排序/筛选)', () => {
  afterEach(() => { cleanup(); window.location.hash = ''; sessionStorage.clear() })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.pausePaperEvidenceTask).mockResolvedValue({ task_id: 't1', status: 'paused' })
    vi.mocked(endpoints.resumePaperEvidenceTask).mockResolvedValue({ task_id: 't1', status: 'pending' })
    vi.mocked(endpoints.retryPaperEvidenceTask).mockResolvedValue({ task_id: 't1', retried: 1 })
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('卡片标题=中文 (英文),副行类型+置信度,徽章状态', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [makeTask({})], total: 1 })
    renderModule()
    const card = await screen.findByTestId('evidence-task-card-t1')
    expect(within(card).getByText('杏仁核 → 海马 (Amygdala → Hippocampus)')).toBeTruthy()
    expect(within(card).getByText('连接')).toBeTruthy()
    expect(within(card).getByText('置信度 35%')).toBeTruthy()
    expect(within(card).getByText('待验证')).toBeTruthy()
  })

  it('中文缺失仅英文;name 备注作第三行不替换标题', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ display_name_cn: null, display_name_en: 'Amygdala → Hippocampus', name: '重新评分 · x · projection' })],
      total: 1,
    })
    renderModule()
    const card = await screen.findByTestId('evidence-task-card-t1')
    expect(within(card).getByText('Amygdala → Hippocampus')).toBeTruthy()
    expect(within(card).getByText('重新评分 · x · projection')).toBeTruthy()
    expect(screen.queryByText('重新评分 · x · projection (Amygdala → Hippocampus)')).toBeNull()
  })

  it('镜像缺失兜底「类型中文 #短ID」', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ display_name_cn: null, display_name_en: null, display_confidence: null })],
      total: 1,
    })
    renderModule()
    const card = await screen.findByTestId('evidence-task-card-t1')
    expect(within(card).getByText('连接 #c1')).toBeTruthy()
    expect(within(card).getByText('未评分')).toBeTruthy()
  })

  it('整卡点击 → 跳转 candidates(与数据中心一致)+ initial-queue 快照', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [makeTask({})], total: 1 })
    renderModule()
    fireEvent.click(await screen.findByTestId('evidence-task-card-t1'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=t1')
    expect(window.location.hash).toContain('target_type=connection')
    expect(window.location.hash).toContain('target_id=c1')
    const queued = JSON.parse(sessionStorage.getItem('evidence-center.initial-queue') ?? '{}')
    expect(queued.items?.[0]?.target_id).toBe('c1')
    expect(queued.taskId).toBe('t1')
  })

  it('卡片按钮不触发跳转(暂停/恢复/重试)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ work_status: 'processing', status: 'running', capabilities: { can_continue_review: false, can_pause: true, can_resume: false, can_retry_failed: false, can_view_results: false } })],
      total: 1,
    })
    renderModule()
    fireEvent.click(await screen.findByTestId('evidence-task-action-pause-t1'))
    await waitFor(() => expect(vi.mocked(endpoints.pausePaperEvidenceTask)).toHaveBeenCalledWith('t1'))
    expect(window.location.hash).not.toContain('module=candidates')
  })

  it('排序:处理中→待验证→已完成→失败;组内置信度升序 null 最前', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-done', work_status: 'completed', status: 'completed', display_confidence: 0.6, capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: true } }),
        makeTask({ id: 't-await-hi', work_status: 'awaiting_review', display_confidence: 0.9 }),
        makeTask({ id: 't-proc', work_status: 'processing', status: 'running', display_confidence: 0.4, capabilities: { can_continue_review: false, can_pause: true, can_resume: false, can_retry_failed: false, can_view_results: false } }),
        makeTask({ id: 't-fail', work_status: 'failed', status: 'failed', display_confidence: 0.2, capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: true, can_view_results: true } }),
        makeTask({ id: 't-await-null', work_status: 'awaiting_review', display_confidence: null }),
      ],
      total: 5,
    })
    renderModule()
    const grid = await screen.findByTestId('evidence-task-card-grid')
    const ids = [...grid.querySelectorAll('[data-testid^="evidence-task-card-"]')].map(el => el.getAttribute('data-testid'))
    expect(ids).toEqual([
      'evidence-task-card-t-proc',
      'evidence-task-card-t-await-null',
      'evidence-task-card-t-await-hi',
      'evidence-task-card-t-done',
      'evidence-task-card-t-fail',
    ])
  })

  it('筛选 chips:回路组只显示 circuit 类型;已取消不显示', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-cn', target_type: 'connection' }),
        makeTask({ id: 't-cc', target_type: 'circuit', display_name_cn: '默认模式网络', display_name_en: 'Default Mode Network' }),
        makeTask({ id: 't-cancel', work_status: 'cancelled', status: 'cancelled', capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false } }),
      ],
      total: 3,
    })
    renderModule()
    await screen.findByTestId('evidence-task-card-t-cn')
    expect(screen.queryByTestId('evidence-task-card-t-cancel')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '回路' }))
    await waitFor(() => expect(screen.queryByTestId('evidence-task-card-t-cn')).toBeNull())
    expect(screen.getByTestId('evidence-task-card-t-cc')).toBeTruthy()
  })

  it('待验证任务「继续验证」:有 target_id 直接跳转,不查 items', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [makeTask({})], total: 1 })
    renderModule()
    fireEvent.click(await screen.findByTestId('evidence-task-action-continue-t1'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).not.toHaveBeenCalled()
  })

  it('失败任务「重试失败项」:确认弹窗,取消不调用,确认后调用', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ work_status: 'failed', status: 'failed', item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 0, completed: 0, skipped: 0, failed: 1, cancelled: 0 }, capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: true, can_view_results: true } })],
      total: 1,
    })
    renderModule()
    fireEvent.click(await screen.findByTestId('evidence-task-action-retry-t1'))
    await waitFor(() => expect(screen.getByText(/将重新处理 1 个失败对象/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /取消|cancel/i }))
    expect(vi.mocked(endpoints.retryPaperEvidenceTask)).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('evidence-task-action-retry-t1'))
    fireEvent.click(screen.getByRole('button', { name: /确认重试/ }))
    await waitFor(() => expect(vi.mocked(endpoints.retryPaperEvidenceTask)).toHaveBeenCalledWith('t1'))
    await waitFor(() => expect(screen.getByText('失败项已重新进入处理队列。')).toBeTruthy())
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: FAIL(旧实现无 `display_name_cn` 渲染 / 点击仍走 openTask)

- [ ] **Step 3: 重写组件**

`EvidenceTasksModule.tsx` 整体替换为:

```tsx
import { useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import {
  listPaperEvidenceTaskItems,
  pausePaperEvidenceTask,
  resumePaperEvidenceTask,
  retryPaperEvidenceTask,
  type PaperEvidenceTask,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/client'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { navigateToEvidenceCandidates } from '../evidenceCenterUrl'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { ConfirmDialog } from '../../../components/ConfirmDialog'
import {
  TARGET_TYPE_LABELS,
  WORK_STATUS_LABELS,
  formatConfidencePercent,
  objectCardTitle,
  workStatusTone,
} from '../components/taskStatus'
import { useEvidenceTaskItems } from '../components/useEvidenceTaskItems'
import { useTaskItemsRefresh } from '../components/taskItemsRefreshContext'

type CardAction = 'resume' | 'pause' | 'retry' | 'continue' | 'view'

const BUSY_LABELS: Record<string, string> = {
  resume: '正在恢复…',
  pause: '正在暂停…',
  retry: '正在重试…',
  continue: '正在查找…',
}

/** 中栏排序:处理中 → 已暂停 → 待验证 → 已完成 → 部分失败 → 失败;组内置信度升序(null 最前) */
const STATUS_GROUP_ORDER: Record<string, number> = {
  processing: 0, paused: 1, awaiting_review: 2, completed: 3, partially_failed: 4, failed: 5,
}

const GROUP_FILTERS: { key: string; label: string; types: string[] | null }[] = [
  { key: 'all', label: '全部', types: null },
  { key: 'connection', label: '连接', types: ['connection', 'projection'] },
  { key: 'circuit', label: '回路', types: ['circuit', 'circuit_step', 'circuit_function'] },
  { key: 'function', label: '功能', types: ['region_function', 'projection_function'] },
]

/** 对象级任务卡片:标题=对象中英文名;整卡点击跳转证据佐证页(与数据中心入口一致) */
function TaskCard({ task, busy, onJump, onResume, onPause, onRetry }: {
  task: PaperEvidenceTask
  busy: CardAction | null
  onJump: () => void
  onResume: () => void
  onPause: () => void
  onRetry: () => void
}) {
  const ws = task.work_status
  const cap = task.capabilities ?? {
    can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false,
  }
  const typeLabel = TARGET_TYPE_LABELS[task.target_type] ?? task.target_type
  const fallback = `${typeLabel} #${(task.target_id ?? task.id).slice(0, 8)}`
  const title = objectCardTitle(task.display_name_cn, task.display_name_en, fallback)

  let primary: { key: CardAction; label: string; handler: () => void } | null = null
  let secondary: { key: CardAction; label: string; handler: () => void } | null = null
  if (ws === 'paused') {
    primary = { key: 'resume', label: '继续任务', handler: onResume }
  } else if (ws === 'awaiting_review' || (cap.can_continue_review && ws === 'partially_failed')) {
    primary = { key: 'continue', label: '继续验证', handler: onJump }
    if (ws === 'partially_failed' && cap.can_retry_failed) {
      secondary = { key: 'retry', label: '重试失败项', handler: onRetry }
    }
  } else if (ws === 'processing') {
    primary = { key: 'view', label: '查看进度', handler: onJump }
    if (cap.can_pause) secondary = { key: 'pause', label: '暂停', handler: onPause }
  } else if (ws === 'partially_failed' || ws === 'failed') {
    primary = { key: 'retry', label: '重试失败项', handler: onRetry }
  } else if (ws === 'completed') {
    primary = { key: 'view', label: '查看结果', handler: onJump }
  }

  const button = (a: { key: CardAction; label: string; handler: () => void }) => (
    <button
      type="button"
      className="btn btn-xs"
      data-testid={`evidence-task-action-${a.key}-${task.id}`}
      disabled={busy !== null}
      onClick={e => {
        e.stopPropagation()
        if (busy === null) a.handler()
      }}
    >
      {busy === a.key ? BUSY_LABELS[a.key] : a.label}
    </button>
  )

  return (
    <div
      role="button"
      tabIndex={0}
      className="evidence-task-card evidence-task-card-clickable"
      data-testid={`evidence-task-card-${task.id}`}
      onClick={onJump}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onJump()
        }
      }}
    >
      <div className="evidence-task-card-head">
        <span className="evidence-task-card-title">{title}</span>
        <span className={`evidence-task-chip evidence-task-chip-${workStatusTone(ws)}`}>
          {WORK_STATUS_LABELS[ws] ?? ws}
        </span>
      </div>
      <div className="evidence-task-card-meta">
        <span className="evidence-task-card-type">{typeLabel}</span>
        <span className="evidence-task-card-confidence">{formatConfidencePercent(task.display_confidence)}</span>
      </div>
      {task.name && <div className="evidence-task-card-remark">{task.name}</div>}
      {(primary || secondary) && (
        <div className="evidence-task-card-actions">
          {primary && button(primary)}
          {secondary && button(secondary)}
        </div>
      )}
    </div>
  )
}

/** 佐证任务中栏:对象级任务卡列表(整卡跳转证据佐证页) */
export function EvidenceTasksModule() {
  const { granularity } = useGlobalGranularity()
  const { tasks, loading, error, reload } = useEvidenceTaskItems()
  const { refresh } = useTaskItemsRefresh()
  const [createOpen, setCreateOpen] = useState(false)
  const [busy, setBusy] = useState<{ taskId: string; action: CardAction } | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [retryTarget, setRetryTarget] = useState<PaperEvidenceTask | null>(null)
  const [group, setGroup] = useState('all')

  const sortedTasks = useMemo(() => {
    const groupTypes = GROUP_FILTERS.find(g => g.key === group)?.types ?? null
    return [...tasks]
      .filter(t => t.work_status !== 'cancelled' && t.work_status !== 'empty')
      .filter(t => !groupTypes || groupTypes.includes(t.target_type))
      .sort((a, b) => {
        const ga = STATUS_GROUP_ORDER[a.work_status] ?? 9
        const gb = STATUS_GROUP_ORDER[b.work_status] ?? 9
        if (ga !== gb) return ga - gb
        const ca = a.display_confidence
        const cb = b.display_confidence
        if (ca === null && cb === null) return 0
        if (ca === null) return -1
        if (cb === null) return 1
        return ca - cb
      })
  }, [tasks, group])

  const jumpToCandidates = (task: PaperEvidenceTask) => {
    if (!task.target_id) return
    navigateToEvidenceCandidates({
      items: [{
        target_type: task.target_type,
        target_id: task.target_id,
        label: task.display_name_cn ?? task.display_name_en ?? '',
        confidence: task.display_confidence ?? null,
      }],
      taskId: task.id,
    })
  }

  const handleOpError = (err: unknown, action: string) => {
    if (err instanceof ApiError) {
      if (err.status === 403) {
        setMessage(`操作失败(${action}):无权限`)
        return
      }
      if (err.status === 400 || err.status === 409) {
        setMessage('任务状态已变化,已刷新。')
        reload()
        return
      }
    }
    setMessage(`操作失败(${action}):${err instanceof Error ? err.message : String(err)}`)
  }

  const handleResume = async (task: PaperEvidenceTask) => {
    setBusy({ taskId: task.id, action: 'resume' })
    setMessage(null)
    try {
      await resumePaperEvidenceTask(task.id)
      setMessage('任务已恢复。')
      refresh()
    } catch (err) {
      handleOpError(err, '恢复')
    } finally {
      setBusy(null)
    }
  }

  const handlePause = async (task: PaperEvidenceTask) => {
    setBusy({ taskId: task.id, action: 'pause' })
    setMessage(null)
    try {
      await pausePaperEvidenceTask(task.id)
      setMessage('任务已暂停。')
      refresh()
    } catch (err) {
      handleOpError(err, '暂停')
    } finally {
      setBusy(null)
    }
  }

  const handleRetry = async (task: PaperEvidenceTask) => {
    setRetryTarget(null)
    setBusy({ taskId: task.id, action: 'retry' })
    setMessage(null)
    try {
      await retryPaperEvidenceTask(task.id)
      setMessage('失败项已重新进入处理队列。')
      refresh()
    } catch (err) {
      handleOpError(err, '重试')
    } finally {
      setBusy(null)
    }
  }

  const handleContinueReview = async (task: PaperEvidenceTask) => {
    if (task.target_id) {
      jumpToCandidates(task)
      return
    }
    // 旧任务兜底:查一条待验证对象再跳转
    setBusy({ taskId: task.id, action: 'continue' })
    setMessage(null)
    try {
      const r = await listPaperEvidenceTaskItems(task.id, {
        status: 'awaiting_review', limit: 1, sort: 'confidence',
      })
      const item = r.items[0]
      if (item && item.target_id) {
        navigateToEvidenceCandidates({
          items: [{
            target_type: item.target_type,
            target_id: item.target_id,
            label: item.display_name ?? '',
            confidence: item.display_confidence ?? null,
          }],
          taskId: task.id,
        })
      } else {
        reload()
        setMessage('当前没有待验证对象。')
      }
    } catch (err) {
      handleOpError(err, '继续验证')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="evidence-task-module">
      <div className="evidence-task-toolbar">
        <div className="evidence-task-toolbar-title">
          <h3>佐证任务</h3>
          <p className="evidence-module-hint">
            一个任务 = 一个知识对象;点击卡片进入证据佐证页,卡片按钮执行对应操作。
          </p>
        </div>
        <div className="evidence-task-toolbar-actions">
          <button type="button" className="btn btn-sm" onClick={reload}>刷新</button>
          <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
        </div>
      </div>

      <div className="evidence-task-filter-chips" data-testid="evidence-task-filter-chips">
        {GROUP_FILTERS.map(g => (
          <button
            key={g.key}
            type="button"
            className={`btn btn-xs${group === g.key ? ' btn-primary' : ''}`}
            onClick={() => setGroup(g.key)}
          >
            {g.label}
          </button>
        ))}
      </div>

      {message && <div className="ontology-page-message" data-testid="evidence-task-message">{message}</div>}

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>{error}</p>
          <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
        </div>
      )}
      {!loading && !error && sortedTasks.length === 0 && (
        <EmptyState
          icon={<Inbox size={24} />}
          title="暂无佐证任务"
          description="点击右上角「创建批量预处理」创建第一个任务。"
          actionLabel="创建批量预处理"
          onAction={() => setCreateOpen(true)}
        />
      )}
      {!loading && !error && sortedTasks.length > 0 && (
        <div className="evidence-task-card-grid" data-testid="evidence-task-card-grid">
          {sortedTasks.map(t => (
            <TaskCard
              key={t.id}
              task={t}
              busy={busy && busy.taskId === t.id ? busy.action : null}
              onJump={() => {
                if (t.target_id) jumpToCandidates(t)
                else void handleContinueReview(t)
              }}
              onResume={() => void handleResume(t)}
              onPause={() => void handlePause(t)}
              onRetry={() => setRetryTarget(t)}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={retryTarget !== null}
        title="重试失败项"
        message={retryTarget ? `将重新处理 ${retryTarget.item_counts?.failed ?? 0} 个失败对象。` : undefined}
        confirmLabel="确认重试"
        danger
        loading={busy?.action === 'retry'}
        onConfirm={() => retryTarget && void handleRetry(retryTarget)}
        onCancel={() => setRetryTarget(null)}
      />

      <CreateBatchTaskDialog
        open={createOpen}
        granularity={granularity}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); reload() }}
      />
    </div>
  )
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx
git commit -m "feat(evidence-ui): object-named task cards with jump-to-candidates navigation"
```

---

### Task 11: 创建对话框消息 + 左栏 Claim 面板 + 页面测试更新

**Files:**
- Modify: `frontend/src/pages/evidence-center/components/CreateBatchTaskDialog.tsx`(成功消息)
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`(tasks 左栏改 ClaimSummaryPanel + 空态提示;删除 TaskPendingQueue import)
- Test: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`

**Interfaces:**
- Consumes: Task 8 的 `task_ids`

- [ ] **Step 1: 对话框消息**

`CreateBatchTaskDialog.tsx` 中:

```typescript
      setMessage(`任务已创建（${r.target_count} 个对象）`)
```

替换为:

```typescript
      setMessage(`任务已创建（${r.task_ids?.length ?? r.target_count} 个对象任务）`)
```

- [ ] **Step 2: 左栏改 Claim 面板**

`EvidenceCenterPage.tsx`:
1. 删除 `import { TaskPendingQueue } from './components/TaskPendingQueue'`。
2. 将 tasks 左栏分支(约 94-96 行):

```tsx
            {state.module === 'tasks' ? (
              <TaskPendingQueue />
            ) : state.module === 'review' || state.module === 'promotion' ? (
```

替换为:

```tsx
            {state.module === 'tasks' ? (
              <>
                {!candidateClaim && (
                  <div className="evidence-left-hint" data-testid="evidence-left-hint">
                    点击任务卡片查看验证事实
                  </div>
                )}
                <ClaimSummaryPanel
                  claimText={candidateClaim?.claimText ?? ''}
                  components={candidateClaim?.components ?? []}
                  targetType={candidateClaim?.targetType ?? ''}
                  granularity={candidateClaim?.granularity ?? null}
                />
              </>
            ) : state.module === 'review' || state.module === 'promotion' ? (
```

(TaskPendingQueue 组件文件保留,不再被页面引用。)

- [ ] **Step 3: 更新页面测试**

`EvidenceCenterPage.test.tsx`:

1. `TASK_FIXTURE` 补字段:

```typescript
  target_id: 'r1-r2', display_name_cn: 'R1→R2', display_name_en: 'R1→R2',
  display_confidence: 0.2, display_name_source: 'mirror_live', display_confidence_source: 'mirror_live',
  work_status: 'awaiting_review',
  item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 },
  capabilities: { can_continue_review: true, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false },
```

2. 「tasks 布局」用例(`it('tasks 布局:左栏待处理队列…')`)替换为:

```tsx
  it('tasks 布局:左栏 Claim 面板(空态提示),右栏已处理面板', async () => {
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-processed-panel')).toBeTruthy())
    expect(screen.getByTestId('evidence-left-hint')).toBeTruthy()
    expect(screen.getByText('点击任务卡片查看验证事实')).toBeTruthy()
    fireEvent.click(screen.getByText('证据候选'))
    await waitFor(() => expect(screen.getByTestId('evidence-queue-panel')).toBeTruthy())
    const title = () => container.querySelector('.evidence-right-panel h4')?.textContent ?? ''
    expect(title()).toContain('待处理对象')
  })
```

3. 「中栏对象点击 → 选中来源任务并打开工作区」用例替换为(卡片点击跳转在模块测试已覆盖,页面级验证接线):

```tsx
  it('任务卡点击 → 页面切换到 candidates 模块并带 task/target 参数', async () => {
    const taskA = { ...TASK_FIXTURE, id: 'ta' }
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [taskA], total: 1 })
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-task-card-ta')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-ta'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=ta')
    expect(window.location.hash).toContain('target_id=r1-r2')
  })
```

4. 「tasks 三栏常显」用例中 `getAllByText('R1→R2')` 的断言保留(标题来自卡片),其余不动。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/evidence-center/components/CreateBatchTaskDialog.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx
git commit -m "feat(evidence-ui): tasks left column Claim panel; batch dialog counts object tasks"
```

---

### Task 12: 样式 + 全量验收

**Files:**
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 10/11 的 `evidence-task-card-title`、`evidence-task-card-meta`、`evidence-task-card-confidence`、`evidence-task-card-remark`、`evidence-task-filter-chips`、`evidence-left-hint`

- [ ] **Step 1: 追加样式**

`frontend/src/styles.css` 末尾追加:

```css
/* ── 佐证任务对象卡(一对一)── */
.evidence-task-card-title {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-task-card-meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 4px;
}
.evidence-task-card-confidence {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--color-accent, #1a6fb0);
}
.evidence-task-card-remark {
  margin-top: 4px;
  font-size: 0.8rem;
  color: var(--color-text-muted, #8a94a6);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-task-filter-chips {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.evidence-left-hint {
  padding: 12px;
  margin-bottom: 10px;
  border-radius: 8px;
  background: var(--color-surface-muted, #f3f6fa);
  color: var(--color-text-muted, #8a94a6);
  font-size: 0.85rem;
}
```

- [ ] **Step 2: 前端全量测试**

Run: `cd frontend && npx vitest run`
Expected: 全部通过(含新增 14 个用例)

- [ ] **Step 3: 前端构建**

Run: `cd frontend && npm run build`
Expected: 0 TypeScript 错误

- [ ] **Step 4: 后端全量回归**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部通过(约 294 个用例)

- [ ] **Step 5: 手工验收(启动中的前后端)**

1. 打开 http://localhost:5173 → 验证中心 → 佐证任务:
   - 卡片标题为「中文 (英文)」,副行类型+置信度,状态徽章;
   - 排序:处理中→待验证→已完成→失败,组内置信度升序;
   - 点卡片 → 跳到证据候选页,URL 含 `module=candidates&task_id=…&target_*`,左栏显示 Claim;
   - 「已取消」「空任务」卡片不再出现。
2. 创建批量预处理 → 消息「任务已创建(N 个对象任务)」,列表出现 N 张对象卡。
3. 数据中心「论文佐证」入口行为不变。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles.css
git commit -m "style(evidence-ui): object task card + filter chips + left hint styles"
```
