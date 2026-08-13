# 佐证任务页面重设计 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把证据中心「佐证任务」页重设计为双视图 —— 任务卡片列表(中间,进行中优先) → 任务详情页(主区嵌入证据候选工作区 + 右栏置信度队列 + 已完成区可回退重审)。

**Architecture:** 双视图单模块：`EvidenceTasksModule` 按 `state.taskId` 切换列表/详情；右栏新建 `TaskItemQueue`(待处理区置信度升序 + 回路/连接/功能筛选 + 已完成折叠区回退)；详情主区直接嵌入现有 `EvidenceCandidatesModule`(不改其代码)。后端新增一个 reopen 端点支持回退。

**Tech Stack:** React 18 + TypeScript + Vite + Vitest/RTL(前端)；FastAPI + SQLAlchemy async + PostgreSQL(后端)；pytest(后端测试)。

## Global Constraints

- **范围红线**：不得修改 `EvidenceCandidatesModule` / `EvidenceReviewModule` / `EvidencePromotionModule` / `ValidationWorkbench` / 验证中心其他 tab / 后端(除 Task 1 的 reopen 端点)。工作树中既有的其他模块未提交改动保持原样 —— 每次提交只 `git add` 本任务列出的文件路径。
- **提交消息**：仓库风格 `<type>(evidence): 中文描述`（后端）或 `<type>(evidence-center): 中文描述`（前端）；不加 Co-Authored-By（项目全局禁用 attribution）。
- **CSS**：只改 `frontend/src/styles.css`，使用现有 token（`var(--primary)` / `var(--border)` / `var(--text-muted)` / `var(--white)` / `var(--bg-soft)` / `var(--danger)` / `var(--shadow)` / `var(--radius)`），新类沿用 `evidence-*` 前缀。
- **测试命令**：前端 `cd frontend && npx vitest run <file>`；后端 `cd backend && .venv/Scripts/python.exe -m pytest <file> -k <kw> -v`。
- **已知基线失败**（本次范围外，不修不新增）：`EvidencePromotionModule.test.tsx`(10)、`EvidenceCandidatesModule.test.tsx`(2)、`PaperCandidateCard.test.tsx`(1)、`EvidenceCenterPage.test.tsx` 中 3 个非 tasks 断言(五模块接线 promotion / 其他模块左栏 ObjectQueue / initial-queue ObjectQueue candidates)。计划内只修 tasks 相关断言。
- 前端 `PaperEvidenceTaskItem.target_type` 可能值为 `connection/projection/circuit/circuit_step/circuit_function/region_function/projection_function`；任务状态 `pending/running/paused/completed/failed`；item 状态 `pending/searching/fetching/retrieving/extracting/verifying/awaiting_review/completed/skipped/failed/cancelled`。

---

### Task 1: 后端回退端点（reopen）

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`（在 `complete_batch_item_reviewed` 之后插入新函数）
- Modify: `backend/app/routers/ontology.py`（在 `/evidence/batch/{task_id}/items/{item_id}/reviewed` 端点之后插入新端点）
- Test: `backend/tests/test_paper_evidence_batch_phase4.py`（文件末尾追加 3 个测试）

**Interfaces:**
- Produces: `pes.reopen_batch_item(session, task_id, item_id) -> dict`（`{"task_id", "item_id", "status": "awaiting_review"}`；不存在 → `ValueError("task item not found")`；非 completed → `ValueError("item is not completed")`）。路由 `POST /api/ontology/evidence/batch/{task_id}/items/{item_id}/reopen`，`require_role("reviewer")`，ValueError → 400 `INVALID_REQUEST`。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_paper_evidence_batch_phase4.py` 末尾追加（该文件已有 `_run/_make_task/_run_task/_cleanup`、`pytest`、`uuid`、`text`、`AsyncSessionLocal`、`pes` 的 import）：

```python
def test_reopen_completed_item_returns_to_awaiting_review():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        _run(_run_task(task_id))
        async def case():
            async with AsyncSessionLocal() as s:
                item_id = (
                    await s.execute(
                        text("SELECT id::text FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": task_id},
                    )
                ).scalar_one()
                await pes.complete_batch_item_reviewed(
                    s, task_id, item_id, evidence_id=str(uuid.uuid4()), operator_id="reviewer-1"
                )
                result = await pes.reopen_batch_item(s, task_id, item_id)
                assert result["status"] == "awaiting_review"
                row = (
                    await s.execute(
                        text(
                            "SELECT status, evidence_id IS NULL, reviewed_at IS NULL, reviewed_by IS NULL "
                            "FROM paper_evidence_task_items WHERE id::text=:iid"
                        ),
                        {"iid": item_id},
                    )
                ).first()
                assert row[0] == "awaiting_review"
                assert row[1] is True
                assert row[2] is True
                assert row[3] is True
                st = (
                    await s.execute(
                        text("SELECT review_status FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": task_id},
                    )
                ).first()
                assert st[0] == "in_review"
        _run(case())
    finally:
        _run(_cleanup(task_id))


def test_reopen_non_completed_item_raises():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        async def case():
            async with AsyncSessionLocal() as s:
                item_id = (
                    await s.execute(
                        text("SELECT id::text FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": task_id},
                    )
                ).scalar_one()
                with pytest.raises(ValueError, match="item is not completed"):
                    await pes.reopen_batch_item(s, task_id, item_id)
        _run(case())
    finally:
        _run(_cleanup(task_id))


def test_reopen_missing_item_raises():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        async def case():
            async with AsyncSessionLocal() as s:
                with pytest.raises(ValueError, match="task item not found"):
                    await pes.reopen_batch_item(s, task_id, str(uuid.uuid4()))
        _run(case())
    finally:
        _run(_cleanup(task_id))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py -k reopen -v`
Expected: FAIL —— `AttributeError: module 'app.services.paper_evidence_service' has no attribute 'reopen_batch_item'`

- [ ] **Step 3: 实现 service 函数**

在 `backend/app/services/paper_evidence_service.py` 的 `complete_batch_item_reviewed` 函数之后（约 3908 行）插入：

```python
async def reopen_batch_item(
    session: AsyncSession,
    task_id: str,
    item_id: str,
) -> dict:
    """将已完成(completed)的任务项回退为待审核(awaiting_review),支持重新审查。

    仅回退 item 状态与已记录的证据关联;已写入 paper_evidence 的记录不撤销(留痕),
    重新审核晋升时按现有流程产生新记录。
    """
    exists = (
        await session.execute(
            text(
                "SELECT 1 FROM paper_evidence_task_items "
                "WHERE task_id::text=:tid AND id::text=:iid"
            ),
            {"tid": task_id, "iid": item_id},
        )
    ).first()
    if exists is None:
        raise ValueError("task item not found")
    result = await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='awaiting_review', reviewed_by=NULL, "
            "reviewed_at=NULL, evidence_id=NULL, updated_at=now() "
            "WHERE task_id::text=:tid AND id::text=:iid AND status='completed'"
        ),
        {"tid": task_id, "iid": item_id},
    )
    await session.commit()
    if result.rowcount == 0:
        raise ValueError("item is not completed")
    await _update_task_totals(session, task_id)
    await session.commit()
    await _update_task_review_status(session, task_id)
    await session.commit()
    return {"task_id": task_id, "item_id": item_id, "status": "awaiting_review"}
```

- [ ] **Step 4: 实现路由端点**

在 `backend/app/routers/ontology.py` 的 `paper_evidence_batch_item_reviewed` 端点之后（约 1133 行）插入：

```python
@router.post("/evidence/batch/{task_id}/items/{item_id}/reopen")
async def paper_evidence_batch_item_reopen(
    task_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.reopen_batch_item(session, task_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py -k reopen -v`
Expected: PASS —— 3 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/paper_evidence_service.py backend/app/routers/ontology.py backend/tests/test_paper_evidence_batch_phase4.py
git commit -m "feat(evidence): 任务项回退端点 reopen(completed→awaiting_review,清 reviewed 字段)"
```

---

### Task 2: 前端纯工具（队列排序/筛选分组 + 任务列表排序）

**Files:**
- Create: `frontend/src/pages/evidence-center/components/taskItemQueueUtils.ts`
- Modify: `frontend/src/pages/evidence-center/components/taskStatus.ts`（追加任务排序工具）
- Test: `frontend/src/pages/evidence-center/components/taskItemQueueUtils.test.ts`

**Interfaces:**
- Produces（Task 3/4/5 依赖）:
  - `UNFINISHED_ITEM_STATUSES: string[]`
  - `isUnfinishedItem(item: PaperEvidenceTaskItem): boolean`
  - `sortByConfidenceAsc(items: PaperEvidenceTaskItem[]): PaperEvidenceTaskItem[]`（null 置信度最前，升序，label 兜底 target_id 稳定排序）
  - `TARGET_TYPE_GROUPS: { key: 'circuit'|'connection'|'function'; label: string; types: string[] }[]`
  - `groupOf(targetType: string): 'circuit'|'connection'|'function'|'other'`
  - `taskSortRank(t: { status: string; awaiting_review_items: number }): number`（0=进行中 1=有等待审核 2=其他）

- [ ] **Step 1: 写失败测试**

```tsx
// frontend/src/pages/evidence-center/components/taskItemQueueUtils.test.ts
import { describe, expect, it } from 'vitest'
import type { PaperEvidenceTaskItem } from '../../../api/endpoints'
import { groupOf, isUnfinishedItem, sortByConfidenceAsc, TARGET_TYPE_GROUPS, UNFINISHED_ITEM_STATUSES } from './taskItemQueueUtils'
import { taskSortRank } from './taskStatus'

function makeItem(overrides: Partial<PaperEvidenceTaskItem>): PaperEvidenceTaskItem {
  return {
    id: 'i', target_type: 'connection', target_id: 't', status: 'pending', pmid: null, title: null,
    passage: null, direction: null, confidence: null, evidence_id: null, error_message: null,
    updated_at: null, label: 'L', current_confidence: null, attempt_count: 0, last_error_code: null,
    last_error_message: null, preprocess_outcome: null, paper_id: null, model_direction: null,
    candidate_papers: null, review_draft: null, claim_text_snapshot: null, claim_components_snapshot: null,
    passages_json: null, last_error: null, retry_count: 0, ...overrides,
  }
}

describe('taskItemQueueUtils', () => {
  it('未完成状态集合判定', () => {
    for (const s of UNFINISHED_ITEM_STATUSES) expect(isUnfinishedItem(makeItem({ status: s }))).toBe(true)
    for (const s of ['completed', 'skipped', 'failed', 'cancelled']) expect(isUnfinishedItem(makeItem({ status: s }))).toBe(false)
  })

  it('置信度排序:null 最前,升序,同值按 label', () => {
    const sorted = sortByConfidenceAsc([
      makeItem({ id: 'a', label: 'a', current_confidence: 0.9 }),
      makeItem({ id: 'b', label: 'b', current_confidence: null }),
      makeItem({ id: 'c', label: 'c', current_confidence: 0.4 }),
      makeItem({ id: 'd', label: 'd', current_confidence: 0.4, target_id: 'td' }),
    ])
    expect(sorted.map(i => i.id)).toEqual(['b', 'c', 'd', 'a'])
  })

  it('排序在同置信度下按 label 稳定排序,label 缺失兜底 target_id', () => {
    const sorted = sortByConfidenceAsc([
      makeItem({ id: 'x', label: 'Beta', current_confidence: 0.5 }),
      makeItem({ id: 'y', label: null, target_id: 'zzz', current_confidence: 0.5 }),
      makeItem({ id: 'z', label: 'Alpha', current_confidence: 0.5 }),
    ])
    expect(sorted.map(i => i.id)).toEqual(['z', 'x', 'y'])
  })

  it('类型分组映射:回路/连接/功能/其他', () => {
    expect(groupOf('circuit')).toBe('circuit')
    expect(groupOf('circuit_step')).toBe('circuit')
    expect(groupOf('circuit_function')).toBe('circuit')
    expect(groupOf('connection')).toBe('connection')
    expect(groupOf('projection')).toBe('connection')
    expect(groupOf('region_function')).toBe('function')
    expect(groupOf('projection_function')).toBe('function')
    expect(groupOf('unknown_type')).toBe('other')
    expect(TARGET_TYPE_GROUPS.map(g => g.label)).toEqual(['回路', '连接', '功能'])
  })

  it('任务列表排序秩:进行中 < 有等待审核 < 其他', () => {
    expect(taskSortRank({ status: 'running', awaiting_review_items: 0 })).toBe(0)
    expect(taskSortRank({ status: 'paused', awaiting_review_items: 2 })).toBe(0)
    expect(taskSortRank({ status: 'completed', awaiting_review_items: 3 })).toBe(1)
    expect(taskSortRank({ status: 'completed', awaiting_review_items: 0 })).toBe(2)
    expect(taskSortRank({ status: 'failed', awaiting_review_items: 0 })).toBe(2)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/taskItemQueueUtils.test.ts`
Expected: FAIL —— Cannot find module './taskItemQueueUtils'

- [ ] **Step 3: 实现工具文件**

```ts
// frontend/src/pages/evidence-center/components/taskItemQueueUtils.ts
import type { PaperEvidenceTaskItem } from '../../../api/endpoints'

/** 未完成(仍待处理)的任务项状态集合 —— 进入待处理队列 */
export const UNFINISHED_ITEM_STATUSES = [
  'pending', 'searching', 'fetching', 'retrieving', 'extracting', 'verifying', 'awaiting_review',
]

export function isUnfinishedItem(item: PaperEvidenceTaskItem): boolean {
  return UNFINISHED_ITEM_STATUSES.includes(item.status)
}

/** 待处理队列排序:置信度升序(低置信度最优先),null 置信度排最前,同置信度按 label(兜底 target_id)稳定排序 */
export function sortByConfidenceAsc(items: PaperEvidenceTaskItem[]): PaperEvidenceTaskItem[] {
  return [...items].sort((a, b) => {
    const ca = a.current_confidence
    const cb = b.current_confidence
    const labelA = a.label || a.target_id
    const labelB = b.label || b.target_id
    if (ca == null && cb == null) return labelA.localeCompare(labelB)
    if (ca == null) return -1
    if (cb == null) return 1
    if (ca !== cb) return ca - cb
    return labelA.localeCompare(labelB)
  })
}

export type TargetTypeGroup = 'circuit' | 'connection' | 'function' | 'other'

/** 队列类型筛选分组:回路 / 连接 / 功能(PRD R4 映射) */
export const TARGET_TYPE_GROUPS: { key: 'circuit' | 'connection' | 'function'; label: string; types: string[] }[] = [
  { key: 'circuit', label: '回路', types: ['circuit', 'circuit_step', 'circuit_function'] },
  { key: 'connection', label: '连接', types: ['connection', 'projection'] },
  { key: 'function', label: '功能', types: ['region_function', 'projection_function'] },
]

export function groupOf(targetType: string): TargetTypeGroup {
  const g = TARGET_TYPE_GROUPS.find(x => x.types.includes(targetType))
  return g ? g.key : 'other'
}
```

在 `frontend/src/pages/evidence-center/components/taskStatus.ts` 末尾追加：

```ts
/** 进行中任务状态(任务列表置顶排序第一组) */
export const IN_PROGRESS_TASK_STATUSES = ['pending', 'running', 'paused']

/** 任务列表排序秩:0=进行中,1=有等待审核,2=其他;同组内按创建时间倒序 */
export function taskSortRank(t: { status: string; awaiting_review_items: number }): number {
  if (IN_PROGRESS_TASK_STATUSES.includes(t.status)) return 0
  if (t.awaiting_review_items > 0) return 1
  return 2
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/taskItemQueueUtils.test.ts`
Expected: PASS —— 5 passed

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/evidence-center/components/taskItemQueueUtils.ts frontend/src/pages/evidence-center/components/taskItemQueueUtils.test.ts frontend/src/pages/evidence-center/components/taskStatus.ts
git commit -m "feat(evidence-center): 队列排序/类型分组与任务列表排序纯工具 + 单测"
```

---

### Task 3: 任务列表视图（任务卡片网格 + 全宽布局 + 上下文导航语义）

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`（整体重写为列表视图 + 详情占位）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`（`openTask` module 改 'tasks'；新增 `closeTask`）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`（全宽条件扩展：tasks 且无 taskId）
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`（整体重写为列表视图用例）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`（新增 tasks 列表全宽用例）
- Modify: `frontend/src/styles.css`（任务卡片网格样式）

**Interfaces:**
- Consumes: Task 2 的 `taskSortRank`、`TASK_STATUS_LABELS`、`taskStatusTone`；既有 `openTask`。
- Produces: `openTask(taskId)` 语义 = 进入 tasks 详情（`apply({ taskId, targetType: null, targetId: null, module: 'tasks' })`）；`closeTask()` = 回列表（清 taskId/target）。模块列表视图渲染 `data-testid="evidence-task-card-grid"` 与 `evidence-task-card-{id}` 卡片。

- [ ] **Step 1: 重写模块测试（列表视图用例）**

用以下内容整体替换 `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`：

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { EvidenceTasksModule } from './EvidenceTasksModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  getEvidenceTarget: vi.fn(),
  searchPaperEvidence: vi.fn(),
  extractSelectedPaperEvidence: vi.fn(),
  listPaperEvidence: vi.fn(),
  saveTaskItemDraft: vi.fn(),
  validatePassageSelection: vi.fn(),
  translateEvidenceText: vi.fn(),
  attachPaperEvidencePreview: vi.fn(),
  attachPaperEvidence: vi.fn(),
  rollbackPaperEvidence: vi.fn(),
  createPaperEvidenceExtractionRun: vi.fn(),
  getPaperEvidenceExtractionRun: vi.fn(),
  retryFailedPaperEvidenceExtractionRun: vi.fn(),
  cancelPaperEvidenceExtractionRun: vi.fn(),
  completePaperEvidenceTaskItem: vi.fn(),
  reopenPaperEvidenceTaskItem: vi.fn(),
  createPaperEvidenceBatch: vi.fn(),
  previewEvidenceBatchScope: vi.fn(),
}))

function makeTask(overrides: Record<string, unknown>) {
  return {
    id: 't1', target_type: 'connection', name: '任务一', status: 'pending',
    total_items: 10, processed_items: 2, awaiting_review_items: 1, failed_items: 0,
    review_status: 'in_review', granularity_level: 'macro', estimated_target_count: 10,
    materialized_target_count: 10, scope: 'filter', mode: 'existence', max_papers_per_object: 3,
    created_at: '2026-08-10T00:00:00Z', created_by: null, started_at: null, finished_at: null,
    error_message: null, materialization_status: 'completed', materialization_cursor: null,
    materialization_error: null, confidence_lt: null, only_oa: false,
    stop_after_strong_support: false, summary: null, scope_type: 'filter',
    filter_snapshot: null, versions: null, ...overrides,
  }
}

function cardOrder(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('[data-testid^="evidence-task-card-"]'))
    .map(el => (el as HTMLElement).dataset.testid ?? '')
}

describe('EvidenceTasksModule(任务列表视图)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('渲染任务卡片:名称/类型/状态徽章/进度/待审核/创建时间', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ name: '连接佐证A', failed_items: 2 })], total: 1,
    })
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('连接佐证A')).toBeTruthy())
    expect(screen.getByText('connection')).toBeTruthy()
    expect(screen.getByText('待预处理')).toBeTruthy()
    expect(screen.getByText(/已处理/).textContent).toContain('2')
    expect(screen.getByText(/待审核/).textContent).toContain('1')
    expect(screen.getByText(/失败/).textContent).toContain('2')
    expect(container.querySelector('.evidence-task-card-grid')).toBeTruthy()
  })

  it('排序:进行中 → 有等待审核 → 其他,同组内创建时间倒序', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-old-running', name: '旧进行中', status: 'running', created_at: '2026-08-09T00:00:00Z' }),
        makeTask({ id: 't-done', name: '已完成', status: 'completed', awaiting_review_items: 0, created_at: '2026-08-12T00:00:00Z' }),
        makeTask({ id: 't-await', name: '待审核', status: 'completed', awaiting_review_items: 3, created_at: '2026-08-11T00:00:00Z' }),
        makeTask({ id: 't-new-running', name: '新进行中', status: 'running', created_at: '2026-08-13T00:00:00Z' }),
      ], total: 4,
    })
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('已完成')).toBeTruthy())
    expect(cardOrder(container)).toEqual([
      'evidence-task-card-t-new-running', 'evidence-task-card-t-old-running',
      'evidence-task-card-t-await', 'evidence-task-card-t-done',
    ])
  })

  it('空任务列表:空态 + 创建 CTA', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
    // 工具栏 + 空态操作按钮各一个
    expect(screen.getAllByRole('button', { name: '创建批量预处理' }).length).toBeGreaterThanOrEqual(1)
  })

  it('点击任务卡片 → openTask 进入 tasks 详情(URL 带 task_id,module 保持 tasks)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-t1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=t1'))
    expect(window.location.hash).toContain('module=tasks')
    expect(window.location.hash).not.toContain('target_id=')
  })

  it('任务列表加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('boom'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/任务列表加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: FAIL —— 旧测试与新模块不匹配（`evidence-task-card-grid` 不存在等）

- [ ] **Step 3: 重写 EvidenceTasksModule（列表视图 + 详情占位）**

用以下内容整体替换 `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`：

```tsx
import { useCallback, useEffect, useState } from 'react'
import { Inbox } from 'lucide-react'
import { listPaperEvidenceTasks, type PaperEvidenceTask } from '../../../api/endpoints'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { TASK_STATUS_LABELS, taskSortRank, taskStatusTone } from '../components/taskStatus'

function fmtDate(v: string | null): string {
  if (!v) return ''
  try {
    return new Date(v).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return v
  }
}

/** 任务卡片:基本信息 + 点击进入任务详情 */
function TaskCard({ task, onOpen }: { task: PaperEvidenceTask; onOpen: () => void }) {
  const inProgress = ['pending', 'running', 'paused'].includes(task.status)
  return (
    <button
      type="button"
      className="evidence-task-card"
      data-testid={`evidence-task-card-${task.id}`}
      onClick={onOpen}
    >
      <div className="evidence-task-card-head">
        <span className="evidence-task-card-name">{task.name || task.target_type}</span>
        <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(task.status)}${inProgress ? ' evidence-task-chip-live' : ''}`}>
          {TASK_STATUS_LABELS[task.status] ?? task.status}
        </span>
      </div>
      <div className="evidence-task-card-type">{task.target_type}</div>
      <div className="evidence-task-card-stats">
        <span>已处理 <b>{task.processed_items}</b> / <b>{task.total_items}</b></span>
        <span className={task.awaiting_review_items > 0 ? 'evidence-task-card-awaiting' : undefined}>
          待审核 <b>{task.awaiting_review_items}</b>
        </span>
        {task.failed_items > 0 && (
          <span className="evidence-task-card-failed">失败 <b>{task.failed_items}</b></span>
        )}
      </div>
      {task.created_at && <div className="ew-meta">{fmtDate(task.created_at)}</div>}
    </button>
  )
}

export function EvidenceTasksModule() {
  const { state, openTask } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

  const loadTasks = useCallback(async () => {
    setTasksLoading(true)
    setTasksError(null)
    try {
      const r = await listPaperEvidenceTasks()
      setTasks(r.items)
    } catch (err) {
      setTasksError(err instanceof Error ? err.message : String(err))
    } finally {
      setTasksLoading(false)
    }
  }, [])

  useEffect(() => { void loadTasks() }, [loadTasks])

  // ── 任务列表视图(无 taskId) ──
  if (!state.taskId) {
    const sorted = [...tasks].sort((a, b) => {
      const ra = taskSortRank(a)
      const rb = taskSortRank(b)
      if (ra !== rb) return ra - rb
      return (b.created_at ?? '').localeCompare(a.created_at ?? '')
    })
    return (
      <div className="evidence-task-module">
        <div className="evidence-task-toolbar">
          <div className="evidence-task-toolbar-title">
            <h3>佐证任务</h3>
            <p className="evidence-module-hint">当前正在处理的证据佐证任务,点击任务卡片进入处理工作台。</p>
          </div>
          <div className="evidence-task-toolbar-actions">
            <button type="button" className="btn btn-sm" onClick={() => void loadTasks()}>刷新</button>
            <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
          </div>
        </div>

        {tasksLoading && <div className="evidence-task-loading">加载中…</div>}
        {!tasksLoading && tasksError && (
          <div className="evidence-task-error">
            <p>任务列表加载失败:{tasksError}</p>
            <button type="button" className="btn btn-sm" onClick={() => void loadTasks()}>重试</button>
          </div>
        )}
        {!tasksLoading && !tasksError && sorted.length === 0 && (
          <EmptyState
            icon={<Inbox size={24} />}
            title="暂无佐证任务"
            description="点击右上角「创建批量预处理」创建第一个任务。"
            actionLabel="创建批量预处理"
            onAction={() => setCreateOpen(true)}
          />
        )}
        {!tasksLoading && !tasksError && sorted.length > 0 && (
          <div className="evidence-task-card-grid" data-testid="evidence-task-card-grid">
            {sorted.map(task => (
              <TaskCard key={task.id} task={task} onOpen={() => openTask(task.id)} />
            ))}
          </div>
        )}

        <CreateBatchTaskDialog
          open={createOpen}
          granularity={granularity}
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); void loadTasks() }}
        />
      </div>
    )
  }

  // ── 任务详情视图(Task 4 接入) ──
  return (
    <div className="evidence-task-module">
      <div className="evidence-task-toolbar">
        <div className="evidence-task-toolbar-title">
          <h3>任务详情</h3>
          <p className="evidence-module-hint">详情视图将在下一任务接入。</p>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 改上下文 openTask 语义并新增 closeTask**

`frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`：

接口 `EvidenceCenterContextValue` 的 `openTask: (taskId: string) => void` 之后加一行：

```ts
  closeTask: () => void
```

替换 `openTask` 实现（原注释「打开新任务必须清除…」保留语义，module 从 'candidates' 改 'tasks'），并在其后新增 `closeTask`：

```ts
  // 打开任务 → 进入佐证任务详情视图(保持 tasks 模块;必须清除上一任务的 target,否则详情/审核会打开错误对象)
  const openTask = useCallback(
    (taskId: string) => {
      apply({ taskId, targetType: null, targetId: null, module: 'tasks' })
      setProgressState(INITIAL_OBJECT_PROGRESS)
    },
    [apply],
  )
  // 关闭任务 → 回到佐证任务列表视图
  const closeTask = useCallback(
    () => {
      apply({ taskId: null, targetType: null, targetId: null })
      setProgressState(INITIAL_OBJECT_PROGRESS)
    },
    [apply],
  )
```

value useMemo 中 `openTarget,` 之后加 `closeTask,`，依赖数组 `[state, queue, progress, setProgress, gotoModule, openTask, openTarget, selectPaper, ...]` 中 `openTarget,` 之后加 `closeTask,`。

- [ ] **Step 5: 页面全宽条件扩展**

`frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`：

把 `const isPapers = state.module === 'papers'` 改为：

```tsx
  const isPapers = state.module === 'papers'
  // tasks 列表视图(无 taskId)同论文库一样全宽,隐藏左右栏
  const isTasksList = state.module === 'tasks' && !state.taskId
  const isFullWidth = isPapers || isTasksList
```

并把后续三处 `isPapers` 替换为 `isFullWidth`（布局 className 一处 + 左栏 aside 条件一处 + 右栏 aside 条件一处）。

- [ ] **Step 6: 新增 CSS（styles.css 末尾追加）**

```css
/* ── 佐证任务列表视图:任务卡片网格 ── */
.evidence-task-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.evidence-task-card {
  display: flex; flex-direction: column; gap: 8px;
  padding: 14px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--white); text-align: left; cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
}
.evidence-task-card:hover { border-color: var(--primary); box-shadow: var(--shadow); }
.evidence-task-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.evidence-task-card-name { font-weight: 600; font-size: 14px; color: var(--text); }
.evidence-task-card-type { color: var(--text-muted); font-size: 12px; }
.evidence-task-card-stats { display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: var(--text-muted); }
.evidence-task-card-stats b { color: var(--text); }
.evidence-task-card-awaiting { color: #b7791f; }
.evidence-task-card-failed { color: var(--danger); }
.evidence-task-chip-live { border-color: var(--primary); color: var(--primary); }
```

- [ ] **Step 7: 页面测试新增 tasks 列表全宽用例**

在 `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx` 的 describe 块内（「papers 模块例外」测试之后）追加：

```tsx
  it('tasks 列表视图全宽:无左右栏,渲染任务卡片区', async () => {
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE], total: 1 })
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByText('任务A')).toBeTruthy())
    expect(container.querySelector('.evidence-center-layout-full')).toBeTruthy()
    expect(container.querySelector('.evidence-left')).toBeNull()
    expect(container.querySelector('.evidence-right')).toBeNull()
    expect(screen.getByTestId('evidence-task-card-grid')).toBeTruthy()
  })
```

- [ ] **Step 8: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: 模块测试 5 passed；页面测试中本任务新增用例通过。页面测试仍失败(基线)的是 promotion/其他模块相关 4 个 —— 保持不变。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx frontend/src/pages/evidence-center/EvidenceCenterContext.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx frontend/src/styles.css
git commit -m "feat(evidence-center): 佐证任务列表视图(任务卡片网格+全宽+openTask 进详情语义)"
```

---

### Task 4: 任务详情视图（详情条 + 嵌入候选工作区 + 自动选中首位 + 左栏返回）

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`（详情视图完整实现）
- Modify: `frontend/src/pages/evidence-center/components/TaskListPanel.tsx`（整体重写：本地加载 + openTask 切换 + 返回按钮）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`（移除已无人使用的 `taskList/selectedTaskId`）
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`（追加详情视图用例）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`（重写「切换任务 URL」用例 + 新增返回按钮用例）
- Modify: `frontend/src/styles.css`（详情条样式）

**Interfaces:**
- Consumes: Task 2 `isUnfinishedItem/sortByConfidenceAsc`、Task 3 `openTask/closeTask`；嵌入 `EvidenceCandidatesModule`（不改动）。
- Produces: 详情视图 `data-testid="evidence-task-detail-bar"`；左栏返回按钮 `data-testid="evidence-task-list-back"`；自动选中队列首位（未完成、置信度最低）并 `openTarget(type, id, 'tasks')`。

- [ ] **Step 1: 追加模块测试（详情视图用例）**

在 `EvidenceTasksModule.test.tsx` 末尾（describe 块内）追加，并在文件顶部 imports 的 vi.mock 工厂保持 Task 3 版本不变：

```tsx
function makeItem(overrides: Record<string, unknown>) {
  return {
    id: 'it', target_type: 'connection', target_id: 'conn', status: 'awaiting_review',
    pmid: null, title: null, passage: null, direction: null, confidence: null,
    evidence_id: null, error_message: null, updated_at: '2026-08-10T00:00:00Z',
    label: 'Conn', current_confidence: 0.5, attempt_count: 0, last_error_code: null,
    last_error_message: null, preprocess_outcome: null, paper_id: null, model_direction: null,
    candidate_papers: [], review_draft: null, claim_text_snapshot: null,
    claim_components_snapshot: null, passages_json: null, last_error: null, retry_count: 0,
    ...overrides,
  }
}

describe('EvidenceTasksModule(任务详情视图)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('进入详情:拉取 items + 自动选中置信度最低(null 最前)的对象', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-high', label: 'High', current_confidence: 0.9 }),
        makeItem({ id: 'i2', target_id: 'c-low', label: 'Low', current_confidence: 0.2 }),
        makeItem({ id: 'i3', target_id: 'c-null', label: 'NoConf', current_confidence: null }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalledWith('t1', { limit: 200 }))
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-null'))
    expect(window.location.hash).toContain('module=tasks')
    expect(screen.getByTestId('evidence-task-detail-bar')).toBeTruthy()
  })

  it('URL 已带本任务未完成 target 时不覆盖', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-a', label: 'A', current_confidence: 0.9 }),
        makeItem({ id: 'i2', target_id: 'c-b', label: 'B', current_confidence: null }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1&target_type=connection&target_id=c-a'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalled())
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-a'))
    expect(window.location.hash).not.toContain('target_id=c-b')
  })

  it('全部完成时不自动选中(URL 不带 target)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'i1', target_id: 'c-done', status: 'completed' })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalled())
    await new Promise(r => setTimeout(r, 0))
    expect(window.location.hash).not.toContain('target_id=')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: FAIL —— 详情占位不渲染 `evidence-task-detail-bar`、不拉取 items

- [ ] **Step 3: 实现详情视图（模块完整版）**

用以下内容整体替换 `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`（列表视图部分与 Task 3 完全相同，此处含全部内容以保证独立可读）：

```tsx
import { useCallback, useEffect, useState } from 'react'
import { Inbox } from 'lucide-react'
import {
  listPaperEvidenceTasks,
  listPaperEvidenceTaskItems,
  type PaperEvidenceTask,
  type PaperEvidenceTaskItem,
} from '../../../api/endpoints'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { TASK_STATUS_LABELS, taskSortRank, taskStatusTone } from '../components/taskStatus'
import { isUnfinishedItem, sortByConfidenceAsc } from '../components/taskItemQueueUtils'
import { EvidenceCandidatesModule } from './EvidenceCandidatesModule'

function fmtDate(v: string | null): string {
  if (!v) return ''
  try {
    return new Date(v).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return v
  }
}

/** 任务卡片:基本信息 + 点击进入任务详情 */
function TaskCard({ task, onOpen }: { task: PaperEvidenceTask; onOpen: () => void }) {
  const inProgress = ['pending', 'running', 'paused'].includes(task.status)
  return (
    <button
      type="button"
      className="evidence-task-card"
      data-testid={`evidence-task-card-${task.id}`}
      onClick={onOpen}
    >
      <div className="evidence-task-card-head">
        <span className="evidence-task-card-name">{task.name || task.target_type}</span>
        <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(task.status)}${inProgress ? ' evidence-task-chip-live' : ''}`}>
          {TASK_STATUS_LABELS[task.status] ?? task.status}
        </span>
      </div>
      <div className="evidence-task-card-type">{task.target_type}</div>
      <div className="evidence-task-card-stats">
        <span>已处理 <b>{task.processed_items}</b> / <b>{task.total_items}</b></span>
        <span className={task.awaiting_review_items > 0 ? 'evidence-task-card-awaiting' : undefined}>
          待审核 <b>{task.awaiting_review_items}</b>
        </span>
        {task.failed_items > 0 && (
          <span className="evidence-task-card-failed">失败 <b>{task.failed_items}</b></span>
        )}
      </div>
      {task.created_at && <div className="ew-meta">{fmtDate(task.created_at)}</div>}
    </button>
  )
}

export function EvidenceTasksModule() {
  const { state, openTask, openTarget } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])

  const loadTasks = useCallback(async () => {
    setTasksLoading(true)
    setTasksError(null)
    try {
      const r = await listPaperEvidenceTasks()
      setTasks(r.items)
    } catch (err) {
      setTasksError(err instanceof Error ? err.message : String(err))
    } finally {
      setTasksLoading(false)
    }
  }, [])

  useEffect(() => { void loadTasks() }, [loadTasks])

  const loadItems = useCallback(async () => {
    if (!state.taskId) { setItems([]); return }
    try {
      const r = await listPaperEvidenceTaskItems(state.taskId, { limit: 200 })
      setItems(r.items)
    } catch {
      setItems([])
    }
  }, [state.taskId])

  useEffect(() => { void loadItems() }, [loadItems])

  // 进入详情自动选中队列首位(未完成、置信度最低):URL 无 target 或 target 不在本任务未完成集合时纠正;
  // 该纠正同时抵消嵌入候选组件把 module 回写为 candidates 的副作用(本 effect 在其后执行)
  useEffect(() => {
    if (!state.taskId) return
    const unfinished = sortByConfidenceAsc(items.filter(isUnfinishedItem))
    if (unfinished.length === 0) return
    const matched = unfinished.find(it => it.target_type === state.targetType && it.target_id === state.targetId)
    if (!matched) openTarget(unfinished[0].target_type, unfinished[0].target_id, 'tasks')
  }, [state.taskId, items, state.targetType, state.targetId, openTarget])

  // ── 任务列表视图(无 taskId) ──
  if (!state.taskId) {
    const sorted = [...tasks].sort((a, b) => {
      const ra = taskSortRank(a)
      const rb = taskSortRank(b)
      if (ra !== rb) return ra - rb
      return (b.created_at ?? '').localeCompare(a.created_at ?? '')
    })
    return (
      <div className="evidence-task-module">
        <div className="evidence-task-toolbar">
          <div className="evidence-task-toolbar-title">
            <h3>佐证任务</h3>
            <p className="evidence-module-hint">当前正在处理的证据佐证任务,点击任务卡片进入处理工作台。</p>
          </div>
          <div className="evidence-task-toolbar-actions">
            <button type="button" className="btn btn-sm" onClick={() => void loadTasks()}>刷新</button>
            <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
          </div>
        </div>

        {tasksLoading && <div className="evidence-task-loading">加载中…</div>}
        {!tasksLoading && tasksError && (
          <div className="evidence-task-error">
            <p>任务列表加载失败:{tasksError}</p>
            <button type="button" className="btn btn-sm" onClick={() => void loadTasks()}>重试</button>
          </div>
        )}
        {!tasksLoading && !tasksError && sorted.length === 0 && (
          <EmptyState
            icon={<Inbox size={24} />}
            title="暂无佐证任务"
            description="点击右上角「创建批量预处理」创建第一个任务。"
            actionLabel="创建批量预处理"
            onAction={() => setCreateOpen(true)}
          />
        )}
        {!tasksLoading && !tasksError && sorted.length > 0 && (
          <div className="evidence-task-card-grid" data-testid="evidence-task-card-grid">
            {sorted.map(task => (
              <TaskCard key={task.id} task={task} onOpen={() => openTask(task.id)} />
            ))}
          </div>
        )}

        <CreateBatchTaskDialog
          open={createOpen}
          granularity={granularity}
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); void loadTasks() }}
        />
      </div>
    )
  }

  // ── 任务详情视图 ──
  const task = tasks.find(t => t.id === state.taskId) ?? null
  return (
    <div className="evidence-task-module">
      <div className="evidence-task-detail-bar" data-testid="evidence-task-detail-bar">
        <h3>{task?.name || task?.target_type || '任务详情'}</h3>
        {task && (
          <>
            <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(task.status)}`}>
              {TASK_STATUS_LABELS[task.status] ?? task.status}
            </span>
            <span className="ew-meta">
              已处理 {task.processed_items} / {task.total_items} · 待审核 {task.awaiting_review_items}
              {task.failed_items > 0 ? ` · 失败 ${task.failed_items}` : ''}
            </span>
          </>
        )}
      </div>
      <EvidenceCandidatesModule />
      <CreateBatchTaskDialog
        open={createOpen}
        granularity={granularity}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); void loadItems() }}
      />
    </div>
  )
}
```

- [ ] **Step 4: 重写 TaskListPanel（本地加载 + 切换任务 + 返回按钮）**

用以下内容整体替换 `frontend/src/pages/evidence-center/components/TaskListPanel.tsx`：

```tsx
import { useCallback, useEffect, useState } from 'react'
import { Inbox } from 'lucide-react'
import { listPaperEvidenceTasks, type PaperEvidenceTask } from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { TASK_STATUS_LABELS, taskStatusTone } from './taskStatus'

/** 佐证任务详情左栏:任务列表(点击切换任务,顶部返回任务列表) */
export function TaskListPanel() {
  const { state, openTask, closeTask } = useEvidenceCenter()
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [loading, setLoading] = useState(!tasks.length)
  const [error, setError] = useState<string | null>(null)

  const loadTasks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await listPaperEvidenceTasks()
      setTasks(r.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadTasks() }, [loadTasks])

  return (
    <div className="evidence-task-list" data-testid="evidence-task-list">
      <div className="evidence-task-list-head">
        <button type="button" className="btn btn-xs" data-testid="evidence-task-list-back" onClick={closeTask}>← 任务列表</button>
        <span className="evidence-task-list-title">佐证任务</span>
        <button type="button" className="btn btn-xs" onClick={() => void loadTasks()}>刷新</button>
      </div>
      {loading && <div className="ew-meta">加载中…</div>}
      {!loading && error && (
        <div className="ew-meta">
          <p>加载失败:{error}</p>
          <button type="button" className="btn btn-xs" onClick={() => void loadTasks()}>重试</button>
        </div>
      )}
      {!loading && !error && tasks.length === 0 && (
        <div className="evidence-task-list-empty">
          <Inbox size={20} />
          <span className="ew-meta">暂无佐证任务</span>
        </div>
      )}
      {!loading && !error && tasks.map(task => (
        <div
          key={task.id}
          className={`evidence-task-list-item${state.taskId === task.id ? ' evidence-task-list-item-active' : ''}`}
          data-testid={`evidence-task-list-item-${task.id}`}
          onClick={() => openTask(task.id)}
        >
          <span className="evidence-task-list-name">{task.name || task.target_type}</span>
          <span className={`evidence-task-list-status evidence-task-chip-${taskStatusTone(task.status)}`}>
            {TASK_STATUS_LABELS[task.status] ?? task.status}
          </span>
          <span className="ew-meta">{task.awaiting_review_items} 待审核</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: 清理 Context 中的 taskList/selectedTaskId**

`frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`（此二者已无任何消费方）：

删除接口中的两段（`taskList/selectedTaskId` 及注释行）；删除 `const [taskList, setTaskList] = useState...` 与 `const [selectedTaskId, setSelectedTaskId] = useState...`；value 中删除 `taskList, setTaskList, selectedTaskId, setSelectedTaskId,`；依赖数组删除 `taskList, selectedTaskId`；删除顶部 `import type { PaperEvidenceTask } from '../../api/endpoints'`。

- [ ] **Step 6: 页面测试重写「切换任务 URL」用例 + 新增返回按钮用例**

替换 `EvidenceCenterPage.test.tsx` 中「切换任务后 URL 不再残留上一任务 target,候选加载后回写到新任务首个 item」整条测试为：

```tsx
  it('打开任务卡片进入详情:URL 带 task_id、无残留 target;自动回写到任务首个 item', async () => {
    const taskB = { ...TASK_FIXTURE, id: 'tb', name: '任务B' }
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE, taskB], total: 2 })
    vi.mocked(listPaperEvidenceTaskItems).mockImplementation(async (taskId: string) => ({
      items: taskId === 'tb'
        ? [makeItem({ id: 'it-b', target_type: 'region', target_id: 'rB', label: 'RB', status: 'awaiting_review', current_confidence: 0.5 })]
        : [makeItem({ id: 'it-a', target_type: 'connection', target_id: 'rA', label: 'RA', status: 'awaiting_review' })],
    }))
    window.location.hash = '#/evidence-center?module=tasks&target_type=connection&target_id=stale-target'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByText('任务B')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-tb'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=tb'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=rB'))
    expect(window.location.hash).not.toContain('stale-target')
    expect(window.location.hash).not.toContain('rA')
    expect(window.location.hash).toContain('module=tasks')
  })

  it('详情视图左栏返回按钮回到任务列表', async () => {
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE], total: 1 })
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=tasks&task_id=ta'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-task-list-back')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-list-back'))
    await waitFor(() => expect(window.location.hash).not.toContain('task_id='))
    expect(window.location.hash).toContain('module=tasks')
  })
```

- [ ] **Step 7: 新增 CSS（styles.css 末尾追加）**

```css
/* ── 佐证任务详情视图:详情条 ── */
.evidence-task-detail-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 14px; margin-bottom: 10px;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-soft);
}
.evidence-task-detail-bar h3 { margin: 0; font-size: 15px; }
```

- [ ] **Step 8: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: 模块测试 8 passed(5 列表 + 3 详情)；页面测试新增/重写用例通过；基线失败(非 tasks 的 4 个)保持原状。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx frontend/src/pages/evidence-center/components/TaskListPanel.tsx frontend/src/pages/evidence-center/EvidenceCenterContext.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx frontend/src/styles.css
git commit -m "feat(evidence-center): 佐证任务详情视图(嵌入候选工作区+自动选中置信度最低对象+左栏返回)"
```

---

### Task 5: 右栏待处理队列（TaskItemQueue + RightPanel 接入）

**Files:**
- Create: `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`（待处理区 + 筛选 chips；已完成区在 Task 6 追加）
- Create: `frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx`
- Modify: `frontend/src/pages/evidence-center/components/RightPanel.tsx`（仅 tasks 分支）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`（「右栏随 module 切换」用例更新 tasks 断言）
- Modify: `frontend/src/styles.css`（队列样式）

**Interfaces:**
- Consumes: Task 2 `isUnfinishedItem/sortByConfidenceAsc/TARGET_TYPE_GROUPS/groupOf`；context `state/openTarget`。
- Produces: `TaskItemQueue`（无 props，读 context；`data-testid="evidence-task-queue"`、筛选 `data-testid="evidence-queue-filter"`、条目 `data-testid="evidence-queue-item-{target_id}"`、空态 `data-testid="evidence-queue-empty"`）。

- [ ] **Step 1: 写失败测试**

```tsx
// frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { TaskItemQueue } from './TaskItemQueue'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTaskItems: vi.fn(),
  reopenPaperEvidenceTaskItem: vi.fn(),
}))

function makeItem(overrides: Record<string, unknown>) {
  return {
    id: 'it', target_type: 'connection', target_id: 'conn', status: 'awaiting_review',
    pmid: null, title: null, passage: null, direction: null, confidence: null,
    evidence_id: null, error_message: null, updated_at: '2026-08-10T00:00:00Z',
    label: 'Conn', current_confidence: 0.5, attempt_count: 0, last_error_code: null,
    last_error_message: null, preprocess_outcome: null, paper_id: null, model_direction: null,
    candidate_papers: [], review_draft: null, claim_text_snapshot: null,
    claim_components_snapshot: null, passages_json: null, last_error: null, retry_count: 0,
    ...overrides,
  }
}

function queueItemIds(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('[data-testid^="evidence-queue-item-"]'))
    .map(el => (el as HTMLElement).dataset.testid ?? '')
}

describe('TaskItemQueue(待处理区)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockResolvedValue({ task_id: 't1', item_id: 'x', status: 'awaiting_review' })
  })

  it('待处理队列按置信度升序渲染,null 最前;已完成/失败不进队列', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'c-high', label: 'High', current_confidence: 0.9 }),
        makeItem({ id: 'b', target_id: 'c-null', label: 'NoConf', current_confidence: null }),
        makeItem({ id: 'c', target_id: 'c-low', label: 'Low', current_confidence: 0.2 }),
        makeItem({ id: 'd', target_id: 'c-done', status: 'completed', current_confidence: 0.8 }),
        makeItem({ id: 'e', target_id: 'c-fail', status: 'failed', current_confidence: 0.1 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    const { container } = render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('Low')).toBeTruthy())
    expect(queueItemIds(container)).toEqual([
      'evidence-queue-item-c-null', 'evidence-queue-item-c-low', 'evidence-queue-item-c-high',
    ])
    expect(screen.queryByText(/^0\.90$/)).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('筛选 chips:回路/连接/功能分组过滤,计数正确', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'conn-1', target_type: 'connection', label: 'C1', current_confidence: 0.5 }),
        makeItem({ id: 'b', target_id: 'cir-1', target_type: 'circuit_function', label: 'F1', current_confidence: 0.4 }),
        makeItem({ id: 'c', target_id: 'cir-2', target_type: 'circuit_step', label: 'S1', current_confidence: 0.3 }),
        makeItem({ id: 'd', target_id: 'fn-1', target_type: 'region_function', label: 'R1', current_confidence: 0.2 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    const { container } = render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('C1')).toBeTruthy())
    expect(screen.getByRole('button', { name: /^全部/ }).textContent).toContain('4')
    fireEvent.click(screen.getByRole('button', { name: /^回路/ }))
    expect(queueItemIds(container)).toEqual(['evidence-queue-item-cir-2', 'evidence-queue-item-cir-1'])
    fireEvent.click(screen.getByRole('button', { name: /^连接/ }))
    expect(queueItemIds(container)).toEqual(['evidence-queue-item-conn-1'])
    fireEvent.click(screen.getByRole('button', { name: /^功能/ }))
    expect(queueItemIds(container)).toEqual(['evidence-queue-item-fn-1'])
    fireEvent.click(screen.getByRole('button', { name: /^全部/ }))
    expect(queueItemIds(container)).toHaveLength(4)
  })

  it('点击队列条目 → openTarget 保持 tasks 模块', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a', target_id: 'conn-1', label: 'C1', current_confidence: 0.5 })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('C1')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-item-conn-1'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=conn-1'))
    expect(window.location.hash).toContain('module=tasks')
  })

  it('全部完成 → 空态「全部处理完成」', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a', target_id: 'c-done', status: 'completed' })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-queue-empty')).toBeTruthy())
    expect(screen.getByText('全部处理完成')).toBeTruthy()
  })

  it('队列加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockRejectedValueOnce(new Error('boom'))
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/队列加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByTestId('evidence-queue-empty')).toBeTruthy())
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.ts`
Expected: FAIL —— Cannot find module './TaskItemQueue'

- [ ] **Step 3: 实现 TaskItemQueue（待处理区版本,已完成区 Task 6 追加）**

```tsx
// frontend/src/pages/evidence-center/components/TaskItemQueue.tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import { listPaperEvidenceTaskItems, type PaperEvidenceTaskItem } from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { EmptyState } from './EmptyState'
import { TASK_STATUS_LABELS, taskStatusTone } from './taskStatus'
import { TARGET_TYPE_GROUPS, groupOf, isUnfinishedItem, sortByConfidenceAsc } from './taskItemQueueUtils'

/** 队列条目卡片(待处理区):名称/类型/置信度大字/状态/AI 方向;当前对象高亮 */
function QueueItemCard({ item, selected, onOpen }: { item: PaperEvidenceTaskItem; selected: boolean; onOpen: () => void }) {
  const conf = item.current_confidence
  return (
    <div
      className={`evidence-conn-card${selected ? ' evidence-conn-card-selected' : ''}`}
      data-testid={`evidence-queue-item-${item.target_id}`}
      onClick={onOpen}
    >
      <div className="evidence-conn-card-main">
        <span className="evidence-conn-card-label">{item.label || item.target_id}</span>
        <span className="evidence-conn-card-type">{item.target_type}</span>
      </div>
      <div className="evidence-conn-card-meta">
        <div className="evidence-conn-card-conf">
          <span className="evidence-conn-card-conf-label">置信度</span>
          <b className="evidence-conn-card-conf-value">{conf != null ? conf.toFixed(2) : '—'}</b>
        </div>
        <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(item.status)}`}>
          {TASK_STATUS_LABELS[item.status] ?? item.status}
        </span>
        {item.preprocess_outcome === 'no_evidence_found' && <span className="ew-meta">未找到有效证据</span>}
        {item.model_direction && <span className="ew-meta">AI:{item.model_direction}</span>}
      </div>
    </div>
  )
}

/** 右栏待处理队列:置信度升序 + 回路/连接/功能筛选(已完成折叠区在 Task 6 追加) */
export function TaskItemQueue() {
  const { state, openTarget } = useEvidenceCenter()
  const taskId = state.taskId
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [group, setGroup] = useState<string>('all')

  const loadItems = useCallback(async () => {
    if (!taskId) { setItems([]); return }
    setLoading(true)
    setError(null)
    try {
      const r = await listPaperEvidenceTaskItems(taskId, { limit: 200 })
      setItems(r.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => { void loadItems() }, [loadItems])

  const unfinished = useMemo(() => sortByConfidenceAsc(items.filter(isUnfinishedItem)), [items])
  const filtered = useMemo(
    () => (group === 'all' ? unfinished : unfinished.filter(it => groupOf(it.target_type) === group)),
    [unfinished, group],
  )

  return (
    <div className="evidence-task-queue" data-testid="evidence-task-queue">
      <div className="evidence-task-queue-head">
        <h4>待处理队列</h4>
        <button type="button" className="btn btn-xs" onClick={() => void loadItems()}>刷新</button>
      </div>

      <div className="evidence-queue-filter" data-testid="evidence-queue-filter">
        <button
          type="button"
          className={`evidence-queue-filter-btn${group === 'all' ? ' evidence-queue-filter-btn-active' : ''}`}
          onClick={() => setGroup('all')}
        >
          全部 {unfinished.length}
        </button>
        {TARGET_TYPE_GROUPS.map(g => (
          <button
            key={g.key}
            type="button"
            className={`evidence-queue-filter-btn${group === g.key ? ' evidence-queue-filter-btn-active' : ''}`}
            onClick={() => setGroup(g.key)}
          >
            {g.label} {unfinished.filter(it => groupOf(it.target_type) === g.key).length}
          </button>
        ))}
      </div>

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>队列加载失败:{error}</p>
          <button type="button" className="btn btn-sm" onClick={() => void loadItems()}>重试</button>
        </div>
      )}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState
          compact
          icon={<Inbox size={20} />}
          title={unfinished.length === 0 ? '全部处理完成' : '该类型下暂无待处理对象'}
          description={unfinished.length === 0 ? '该任务没有待处理对象。' : '切换筛选分组查看其他类型。'}
          testId="evidence-queue-empty"
        />
      )}
      {!loading && !error && filtered.length > 0 && (
        <div className="evidence-queue-list" data-testid="evidence-queue-list">
          {filtered.map(item => (
            <QueueItemCard
              key={item.id}
              item={item}
              selected={state.targetType === item.target_type && state.targetId === item.target_id}
              onOpen={() => openTarget(item.target_type, item.target_id, 'tasks')}
            />
          ))}
          {items.length >= 200 && <div className="ew-meta">仅显示前 200 条(按优先级截断)</div>}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: RightPanel tasks 分支替换**

`frontend/src/pages/evidence-center/components/RightPanel.tsx`：

imports 中删除 `import { TaskSummary } from './TaskSummary'`，新增 `import { TaskItemQueue } from './TaskItemQueue'`；context 解构中删除 `taskSummary, taskSummaryActions, openTask,`（此三者不再使用）。

tasks 分支整体替换为：

```tsx
  if (module === 'tasks') {
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        <TaskItemQueue />
      </aside>
    )
  }
```

- [ ] **Step 5: 页面测试「右栏随 module 切换」用例更新 tasks 断言**

替换 `EvidenceCenterPage.test.tsx` 中「右栏随 module 切换:占位标题(任务/审核)与队列(candidates)」整条测试为：

```tsx
  it('右栏随 module 切换:tasks 详情渲染待处理队列,candidates 渲染待处理对象队列', () => {
    // tasks 列表视图全宽无右栏,须带 task_id 进入详情视图才有右栏队列
    window.location.hash = '#/evidence-center?module=tasks&task_id=ta'
    const { container } = render(<EvidenceCenterPage />)
    expect(screen.getByTestId('evidence-task-queue')).toBeTruthy()
    fireEvent.click(screen.getByText('证据候选'))
    const title = () => container.querySelector('.evidence-right-panel h4')?.textContent ?? ''
    expect(title()).toContain('待处理对象')
  })
```

- [ ] **Step 6: 新增 CSS（styles.css 末尾追加）**

```css
/* ── 佐证任务右栏:待处理队列 ── */
.evidence-task-queue { display: flex; flex-direction: column; gap: 10px; }
.evidence-task-queue-head { display: flex; align-items: center; justify-content: space-between; }
.evidence-task-queue-head h4 { margin: 0; font-size: 14px; }
.evidence-queue-filter { display: flex; flex-wrap: wrap; gap: 6px; }
.evidence-queue-filter-btn {
  padding: 3px 10px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--white); font-size: 12px; color: var(--text-muted); cursor: pointer;
}
.evidence-queue-filter-btn-active { border-color: var(--primary); color: var(--primary); background: var(--bg-soft); }
.evidence-queue-list { display: flex; flex-direction: column; gap: 8px; }
.evidence-conn-card-selected { border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary) inset; }
```

- [ ] **Step 7: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.ts src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: TaskItemQueue 5 passed；模块 8 passed；页面测试 tasks 相关全过（基线失败保持原状）。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/pages/evidence-center/components/TaskItemQueue.tsx frontend/src/pages/evidence-center/components/TaskItemQueue.test.ts frontend/src/pages/evidence-center/components/RightPanel.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx frontend/src/styles.css
git commit -m "feat(evidence-center): 右栏待处理队列(置信度升序+回路/连接/功能筛选)"
```

---

### Task 6: 已完成区 + 回退重新审查（含前端 API wrapper）

**Files:**
- Modify: `frontend/src/api/endpoints.ts`（新增 `reopenPaperEvidenceTaskItem`）
- Modify: `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`（已完成折叠区 + 两步确认回退）
- Modify: `frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx`（追加已完成区用例）
- Modify: `frontend/src/styles.css`（已完成区样式）

**Interfaces:**
- Consumes: Task 1 后端端点；Task 5 `TaskItemQueue`。
- Produces: `reopenPaperEvidenceTaskItem(taskId, itemId) => Promise<{ task_id; item_id; status }>`；已完成区 toggle `data-testid="evidence-queue-done-toggle"`、条目 `data-testid="evidence-queue-done-item-{target_id}"`、回退按钮 `data-testid="evidence-queue-reopen-{target_id}"`。

- [ ] **Step 1: 追加失败测试**

在 `TaskItemQueue.test.tsx` 的 describe 块内追加：

```tsx
  it('已完成折叠区:展开显示 completed 条目,按完成时间倒序', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'done-old', status: 'completed', updated_at: '2026-08-09T00:00:00Z' }),
        makeItem({ id: 'b', target_id: 'done-new', status: 'completed', updated_at: '2026-08-12T00:00:00Z' }),
        makeItem({ id: 'c', target_id: 'live', status: 'awaiting_review', current_confidence: 0.5 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    const { container } = render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('live')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-done-toggle'))
    await waitFor(() => expect(screen.getByText('done-new')).toBeTruthy())
    const doneIds = Array.from(container.querySelectorAll('[data-testid^="evidence-queue-done-item-"]'))
      .map(el => (el as HTMLElement).dataset.testid ?? '')
    expect(doneIds).toEqual(['evidence-queue-done-item-done-new', 'evidence-queue-done-item-done-old'])
  })

  it('回退两步确认:第一次点击变确认态,第二次调用 reopen 并刷新队列', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems)
      .mockResolvedValueOnce({
        items: [
          makeItem({ id: 'a', target_id: 'live', status: 'awaiting_review', current_confidence: 0.5 }),
          makeItem({ id: 'b', target_id: 'done-1', status: 'completed', updated_at: '2026-08-12T00:00:00Z' }),
        ],
      })
      .mockResolvedValueOnce({
        items: [
          makeItem({ id: 'a', target_id: 'live', status: 'awaiting_review', current_confidence: 0.5 }),
          makeItem({ id: 'b', target_id: 'done-1', status: 'awaiting_review', current_confidence: 0.6 }),
        ],
      })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('live')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-done-toggle'))
    const reopenBtn = () => screen.getByTestId('evidence-queue-reopen-done-1')
    fireEvent.click(reopenBtn())
    expect(reopenBtn().textContent).toContain('确认回退?')
    fireEvent.click(reopenBtn())
    await waitFor(() => expect(vi.mocked(endpoints.reopenPaperEvidenceTaskItem)).toHaveBeenCalledWith('t1', 'b'))
    await waitFor(() => expect(screen.getAllByTestId('evidence-queue-item-done-1')).toHaveLength(1))
  })

  it('回退接口失败 → 错误提示,已完成区不变', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'b', target_id: 'done-1', status: 'completed', updated_at: '2026-08-12T00:00:00Z' })],
    })
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockRejectedValueOnce(new Error('boom'))
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-queue-done-toggle')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-done-toggle'))
    const btn = () => screen.getByTestId('evidence-queue-reopen-done-1')
    fireEvent.click(btn())
    fireEvent.click(btn())
    await waitFor(() => expect(screen.getByText(/回退失败/)).toBeTruthy())
    expect(screen.getByTestId('evidence-queue-done-item-done-1')).toBeTruthy()
  })
```

注意：回退成功后条目回到待处理区，其 testid 变为 `evidence-queue-item-done-1`（待处理区前缀）；断言用 `getAllByTestId(...).toHaveLength(1)`。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.ts`
Expected: FAIL —— 找不到 `evidence-queue-done-toggle`

- [ ] **Step 3: 前端 API wrapper**

在 `frontend/src/api/endpoints.ts` 的 `completePaperEvidenceTaskItem` 定义之后追加：

```ts
export const reopenPaperEvidenceTaskItem = (taskId: string, itemId: string) =>
  postJson<{ task_id: string; item_id: string; status: string }>(
    `/api/ontology/evidence/batch/${taskId}/items/${itemId}/reopen`,
  )
```

- [ ] **Step 4: TaskItemQueue 追加已完成区**

`frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`：

imports 变更 —— lucide 改 `import { ChevronDown, ChevronRight, Inbox } from 'lucide-react'`；endpoints import 加 `reopenPaperEvidenceTaskItem`：

```tsx
import {
  listPaperEvidenceTaskItems,
  reopenPaperEvidenceTaskItem,
  type PaperEvidenceTaskItem,
} from '../../../api/endpoints'
```

组件内 state 区追加：

```tsx
  const [doneOpen, setDoneOpen] = useState(false)
  const [reopeningId, setReopeningId] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
```

`unfinished/filtered` memo 之后追加：

```tsx
  const doneItems = useMemo(
    () => items.filter(it => it.status === 'completed').sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '')),
    [items],
  )

  const handleReopen = useCallback(async (item: PaperEvidenceTaskItem) => {
    if (confirmId !== item.id) {
      setConfirmId(item.id)
      window.setTimeout(() => {
        setConfirmId(prev => (prev === item.id ? null : prev))
      }, 3000)
      return
    }
    setConfirmId(null)
    setReopeningId(item.id)
    setActionError(null)
    try {
      await reopenPaperEvidenceTaskItem(taskId ?? '', item.id)
      await loadItems()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setReopeningId(null)
    }
  }, [confirmId, taskId, loadItems])
```

JSX：在待处理区（`filtered.length > 0` 块）之后、根 div 结束标签之前插入：

```tsx
      <div className="evidence-queue-done" data-testid="evidence-queue-done">
        <button
          type="button"
          className="evidence-queue-done-toggle"
          data-testid="evidence-queue-done-toggle"
          onClick={() => setDoneOpen(o => !o)}
        >
          <span>已完成 {doneItems.length}</span>
          {doneOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        {doneOpen && (
          <>
            {actionError && <div className="ew-meta" style={{ color: 'var(--danger)' }}>回退失败:{actionError}</div>}
            {doneItems.length === 0 && <span className="ew-meta">暂无已完成对象</span>}
            {doneItems.map(item => (
              <div key={item.id} className="evidence-queue-done-item" data-testid={`evidence-queue-done-item-${item.target_id}`}>
                <div className="evidence-queue-done-main">
                  <span className="evidence-conn-card-label">{item.label || item.target_id}</span>
                  <span className="evidence-conn-card-type">{item.target_type}</span>
                  <span className="evidence-task-chip evidence-task-chip-ok">已完成</span>
                </div>
                <button
                  type="button"
                  className="btn btn-xs"
                  data-testid={`evidence-queue-reopen-${item.target_id}`}
                  disabled={reopeningId === item.id}
                  onClick={() => void handleReopen(item)}
                >
                  {reopeningId === item.id ? '回退中…' : (confirmId === item.id ? '确认回退?' : '回退重新审查')}
                </button>
              </div>
            ))}
          </>
        )}
      </div>
```

- [ ] **Step 5: 新增 CSS（styles.css 末尾追加）**

```css
/* ── 佐证任务右栏:已完成折叠区 ── */
.evidence-queue-done { border-top: 1px dashed var(--border); padding-top: 8px; display: flex; flex-direction: column; gap: 8px; }
.evidence-queue-done-toggle {
  display: flex; align-items: center; gap: 4px; border: none; background: none;
  color: var(--text-muted); font-size: 12px; cursor: pointer; padding: 0;
}
.evidence-queue-done-item {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--white);
}
.evidence-queue-done-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.ts`
Expected: PASS —— 8 passed

- [ ] **Step 7: 提交**

```bash
git add frontend/src/api/endpoints.ts frontend/src/pages/evidence-center/components/TaskItemQueue.tsx frontend/src/pages/evidence-center/components/TaskItemQueue.test.ts frontend/src/styles.css
git commit -m "feat(evidence-center): 已完成区折叠展示 + 两步确认回退重新审查(reopen 端点接线)"
```

---

### Task 7: 全量验证与收尾

**Files:** 无新增；如验证发现问题，按最小修复原则修改对应文件并追加测试。

- [ ] **Step 1: 前端全量测试**

Run: `cd frontend && npx vitest run`
Expected: 佐证任务相关全部通过。允许的既有失败(与本次改动前一致,不新增不修复):`EvidencePromotionModule.test.tsx`(10)、`EvidenceCandidatesModule.test.tsx`(2)、`PaperCandidateCard.test.tsx`(1)、`EvidenceCenterPage.test.tsx` 中非 tasks 断言 3 个。若出现其他失败,按 systematic-debugging 修复。

- [ ] **Step 2: TypeScript 检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: 前端构建**

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 4: 后端 reopen 相关测试**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py tests/test_paper_evidence.py tests/test_paper_evidence_api.py -q`
Expected: 全绿(包含 Task 1 的 3 个 reopen 测试)

- [ ] **Step 5: 对照 PRD 验收清单核对**

- [ ] 任务列表页中间卡片(进行中优先排序、基本信息、空态、错误重试)
- [ ] 点击卡片 → 详情(URL 带 task_id;三栏:左任务列表+返回、主区候选工作区、右栏队列)
- [ ] 右栏待处理:未完成 items 置信度升序、null 最前、200 截断提示
- [ ] 筛选:全部/回路/连接/功能(circuit_function 归回路)
- [ ] 点击队列项 → 主区加载该对象(module 保持 tasks)
- [ ] 进入详情自动选中置信度最低对象
- [ ] 已完成折叠区(倒序)+ 两步确认回退 → 回到待处理区
- [ ] 回退失败/非 completed 的错误处理
- [ ] 未改动候选/审核/晋升模块、ValidationWorkbench、验证中心其他 tab

- [ ] **Step 6: 手动走查(可选,后端/前端服务运行中)**

1. `http://localhost:5173/#/evidence-center?module=tasks` → 列表卡片
2. 点击任务 → 详情;观察自动选中、队列排序、筛选
3. 点队列项 → 主区加载对象证据
4. 已完成区展开 → 回退 → 对象回到待处理区
5. 返回列表

---

## Self-Review Notes(计划作者自检记录)

- **Spec 覆盖**:R1=Task 3;R2=Task 4+5;R3=Task 5+6;R4=Task 2+5;R5=Task 3(openTask/closeTask)+4(自动选中);R6=Task 4/5(进入刷新、手动刷新,hashchange 由既有 context hashchange 监听覆盖);R7=Task 1+6。§7 测试计划全部落位。
- **一致性**:`openTask` 新语义在 Task 3 落地并更新其唯一调用点(旧 RightPanel TaskSummary 按钮在 Task 5 随分支替换消失);context 的 `taskList/selectedTaskId` 清理放在 Task 4(TaskListPanel 重写之后,消除依赖)。
- **已知遗留**:Task 3 之后、Task 5 之前,右栏 tasks 分支仍渲染 TaskSummary(数据恒为 null,显示占位文案),为中间态,Task 5 替换。
