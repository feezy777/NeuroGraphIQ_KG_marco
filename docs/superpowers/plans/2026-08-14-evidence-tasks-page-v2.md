# 佐证任务页 V2（单页三栏）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 V1 的两页结构改为单页三栏:中栏任务卡 ⇄ 对象卡 ⇄ 就地候选工作区,右栏常驻置信度队列(未选任务 = 全局队列)。

**Architecture:** 复用 V1 已交付的全部基础设施（queue/回退/工具/上下文/reopen）。增量改动 4 个任务:模块重写(中栏三态)→ 队列全局模式 → 页面三栏常显+删 TaskListPanel → 全量验证。

**Tech Stack:** React 18 + TypeScript + Vite + Vitest/RTL（前端）。无后端改动。

## Global Constraints

- **范围红线**:不改 EvidenceCandidatesModule / EvidenceReviewModule / EvidencePromotionModule / ValidationWorkbench / 验证中心其他 tab / 后端。工作树既有未提交改动保持原样——每次提交只 `git add` 本任务列出的文件路径。
- **提交消息**:仓库风格 `<type>(evidence-center): 中文描述`;不加 Co-Authored-By。
- **CSS**:只改 `frontend/src/styles.css`,使用现有 token,新类沿用 `evidence-*` 前缀。
- **测试命令**:`cd frontend && npx vitest run <file>`。测试不检查 `module=tasks` URL 字符串(buildEvidenceUrl 省略默认 module)。
- **已知基线失败**(非本次范围,不修不新增):promotion 10、candidates 2、PaperCandidateCard 1、page 3(五模块接线 promotion / 其他模块左栏 ObjectQueue / initial-queue)。
- 复用接口:`taskItemQueueUtils.ts`(isUnfinishedItem/sortByConfidenceAsc/TARGET_TYPE_GROUPS/groupOf)、`taskStatus.ts`(taskSortRank/TASK_STATUS_LABELS/taskStatusTone)、context(openTask/closeTask/openTarget/taskId)、`reopenPaperEvidenceTaskItem`。

---

### Task 1: EvidenceTasksModule 重写为中栏三态

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`（整体替换）
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`（整体替换）
- Modify: `frontend/src/styles.css`（追加:中栏返回条/对象卡片选中态样式）

**Interfaces:**
- Consumes: `state(taskId/targetType/targetId)`, `openTask/closeTask/openTarget`;`listPaperEvidenceTasks/listPaperEvidenceTaskItems`;`taskItemQueueUtils`;`EvidenceCandidatesModule`(不改)。
- Produces: 中栏三态;`data-testid="evidence-task-middle-back"`(返回任务列表)、`evidence-task-object-{target_id}`(对象卡片)。

- [ ] **Step 1: 重写模块测试**

用以下内容整体替换 `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`（vi.mock 工厂与 V1 完全一致,保留;`makeTask/makeItem/cardOrder` 辅助保留;用例重写为三态行为）：

```tsx
// 顶部 imports 与 vi.mock 工厂、makeTask、makeItem、cardOrder 与 V1 版本一致(逐字保留)

describe('EvidenceTasksModule(单页三栏·中栏)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('态① 无 taskId:任务卡片网格 + 进行中置顶排序', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-old', name: '旧进行中', status: 'running', created_at: '2026-08-09T00:00:00Z' }),
        makeTask({ id: 't-done', name: '已完成', status: 'completed', awaiting_review_items: 0, created_at: '2026-08-12T00:00:00Z' }),
        makeTask({ id: 't-new', name: '新进行中', status: 'running', created_at: '2026-08-13T00:00:00Z' }),
      ], total: 3,
    })
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('已完成')).toBeTruthy())
    expect(cardOrder(container)).toEqual([
      'evidence-task-card-t-new', 'evidence-task-card-t-old', 'evidence-task-card-t-done',
    ])
  })

  it('态① 空任务列表 → 空态 + 创建 CTA', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
    expect(screen.getAllByRole('button', { name: '创建批量预处理' }).length).toBeGreaterThanOrEqual(1)
  })

  it('态① 加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('boom'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/任务列表加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
  })

  it('点任务卡片 → 自动选中置信度最低(null 最前)对象,进入工作区', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-high', label: 'High', current_confidence: 0.9 }),
        makeItem({ id: 'i2', target_id: 'c-done', label: 'Done', status: 'completed', current_confidence: 0.8 }),
        makeItem({ id: 'i3', target_id: 'c-null', label: 'NoConf', current_confidence: null }),
      ],
    })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-t1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=t1'))
    // 自动选中未完成中置信度最低(null 最前)→ 态③ 工作区
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-null'))
  })

  it('全部完成任务:不自动选中,态② 对象卡片;点对象卡片 → 态③ 工作区', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-done', label: 'DoneA', status: 'completed', current_confidence: 0.8 }),
        makeItem({ id: 'i2', target_id: 'c-done2', label: 'DoneB', status: 'completed', current_confidence: 0.6 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    // 无未完成 → 不自动选中,显示对象卡片(态②)
    await waitFor(() => expect(screen.getByTestId('evidence-task-object-c-done')).toBeTruthy())
    await waitFor(() => expect(window.location.hash).not.toContain('target_id='))
    // 点已完成对象卡片 → 态③ 工作区(targetResolved 门控挂载候选组件)
    fireEvent.click(screen.getByTestId('evidence-task-object-c-done'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-done'))
  })

  it('任务无对象 → 中栏空态,无 target', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-tasks-all-done')).toBeTruthy())
    await waitFor(() => expect(window.location.hash).not.toContain('target_id='))
  })

  it('「← 任务列表」→ 回态①(URL 无 task_id)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-task-middle-back')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-middle-back'))
    await waitFor(() => expect(window.location.hash).not.toContain('task_id='))
    expect(screen.getByText('任务一')).toBeTruthy()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: FAIL —— 现有模块仍是两页结构,`evidence-task-object-*` 与 `evidence-task-middle-back` 不存在

- [ ] **Step 3: 重写 EvidenceTasksModule（中栏三态）**

用以下内容整体替换 `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`：

```tsx
import { useCallback, useEffect, useRef, useState } from 'react'
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

/** 任务卡片:基本信息 + 点击进入任务(态①) */
function TaskCard({ task, selected, onOpen }: { task: PaperEvidenceTask; selected: boolean; onOpen: () => void }) {
  const inProgress = ['pending', 'running', 'paused'].includes(task.status)
  return (
    <button
      type="button"
      className={`evidence-task-card${selected ? ' evidence-task-card-selected' : ''}`}
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

/** 任务对象卡片(态②):未完成优先 + 置信度升序 */
function ObjectCard({ item, selected, onOpen }: { item: PaperEvidenceTaskItem; selected: boolean; onOpen: () => void }) {
  const conf = item.current_confidence
  return (
    <div
      className={`evidence-conn-card${selected ? ' evidence-conn-card-selected' : ''}`}
      data-testid={`evidence-task-object-${item.target_id}`}
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

/** 中栏对象排序:未完成优先(置信度升序),已完成/其他按状态排后 */
function sortObjects(items: PaperEvidenceTaskItem[]): PaperEvidenceTaskItem[] {
  const unfinished = sortByConfidenceAsc(items.filter(isUnfinishedItem))
  const rest = items.filter(it => !isUnfinishedItem(it))
  return [...unfinished, ...rest]
}

export function EvidenceTasksModule() {
  const { state, openTask, closeTask, openTarget } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])
  const [itemsLoading, setItemsLoading] = useState(true)
  const [itemsError, setItemsError] = useState<string | null>(null)
  const latestTaskIdRef = useRef(state.taskId)
  useEffect(() => { latestTaskIdRef.current = state.taskId }, [state.taskId])

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
    const requestedTaskId = state.taskId
    setItemsLoading(true)
    setItemsError(null)
    setItems([])
    try {
      const r = await listPaperEvidenceTaskItems(requestedTaskId, { limit: 100 })
      if (latestTaskIdRef.current !== requestedTaskId) return
      setItems(r.items)
    } catch (err) {
      if (latestTaskIdRef.current !== requestedTaskId) return
      setItems([])
      setItemsError(err instanceof Error ? err.message : String(err))
    } finally {
      if (latestTaskIdRef.current === requestedTaskId) setItemsLoading(false)
    }
  }, [state.taskId])

  useEffect(() => { void loadItems() }, [loadItems])

  // 选中任务自动选中队列首位(未完成、置信度最低):deps 不含 target(防点击/回退后旧快照抢回)
  useEffect(() => {
    if (!state.taskId) return
    const unfinished = sortByConfidenceAsc(items.filter(isUnfinishedItem))
    if (unfinished.length === 0) return
    const matched = unfinished.find(it => it.target_type === state.targetType && it.target_id === state.targetId)
    if (!matched) openTarget(unfinished[0].target_type, unfinished[0].target_id, 'tasks')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.taskId, items, openTarget])

  const task = tasks.find(t => t.id === state.taskId) ?? null
  const targetResolved = Boolean(
    state.targetType && state.targetId
    && items.some(it => it.target_type === state.targetType && it.target_id === state.targetId),
  )

  // ── 态①:任务卡片网格 ──
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
            <p className="evidence-module-hint">当前正在处理的证据佐证任务;右栏为全局置信度优先级队列。</p>
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
            {sorted.map(t => (
              <TaskCard key={t.id} task={t} selected={false} onOpen={() => openTask(t.id)} />
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

  // ── 态②/③:任务对象卡片 ⇄ 就地证据工作区 ──
  const sortedObjects = sortObjects(items)
  return (
    <div className="evidence-task-module">
      <div className="evidence-task-middle-bar">
        <button type="button" className="btn btn-xs" data-testid="evidence-task-middle-back" onClick={closeTask}>← 任务列表</button>
        <h3>{task?.name || task?.target_type || '任务详情'}</h3>
        {task && (
          <span className="ew-meta">
            已处理 {task.processed_items} / {task.total_items} · 待审核 {task.awaiting_review_items}
            {task.failed_items > 0 ? ` · 失败 ${task.failed_items}` : ''}
          </span>
        )}
        <span style={{ marginLeft: 'auto' }}>
          <button type="button" className="btn btn-xs" onClick={() => void loadItems()}>刷新</button>
        </span>
      </div>

      {itemsLoading && <div className="evidence-task-loading">加载中…</div>}
      {!itemsLoading && itemsError && (
        <div className="evidence-task-error">
          <p>对象列表加载失败:{itemsError}</p>
          <button type="button" className="btn btn-sm" onClick={() => void loadItems()}>重试</button>
        </div>
      )}
      {!itemsLoading && !itemsError && targetResolved && <EvidenceCandidatesModule />}
      {!itemsLoading && !itemsError && !targetResolved && sortedObjects.length > 0 && (
        <div className="evidence-conn-list" data-testid="evidence-task-object-list">
          {sortedObjects.map(item => (
            <ObjectCard
              key={item.id}
              item={item}
              selected={state.targetType === item.target_type && state.targetId === item.target_id}
              onOpen={() => openTarget(item.target_type, item.target_id, 'tasks')}
            />
          ))}
        </div>
      )}
      {!itemsLoading && !itemsError && !targetResolved && sortedObjects.length === 0 && (
        <EmptyState
          icon={<Inbox size={24} />}
          title={items.length > 0 && (task?.failed_items ?? 0) > 0 ? '无待处理对象' : '全部处理完成'}
          description={items.length > 0 && (task?.failed_items ?? 0) > 0
            ? '该任务存在失败对象,可回到任务列表查看或重试失败项。'
            : '该任务没有待处理对象。可在右栏已完成区回退对象重新审查。'}
          testId="evidence-tasks-all-done"
        />
      )}

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

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: PASS —— 8 passed（态①×3 + 自动选中 + 全部完成对象卡片 + 空态 + 点对象卡片 + 返回）

- [ ] **Step 5: CSS 追加**

```css
/* ── 佐证任务中栏:返回条/对象卡片选中态 ── */
.evidence-task-middle-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 14px; margin-bottom: 10px;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-soft);
}
.evidence-task-middle-bar h3 { margin: 0; font-size: 15px; }
.evidence-task-card-selected { border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary) inset; }
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx frontend/src/styles.css
git commit -m "feat(evidence-center): 佐证任务中栏三态(任务卡⇄对象卡⇄就地候选工作区+自动选中)"
```

**硬约束**:styles.css 有未提交改动,先由控制器做外科式快照/回退/追加/提交/恢复(实现者不执行 git 操作);只改本任务 3 个文件。

---

### Task 2: TaskItemQueue 全局模式 + 任务过滤

**Files:**
- Modify: `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`
- Modify: `frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx`（追加 3 用例）

**Interfaces:**
- Consumes: `state.taskId`;`listPaperEvidenceTasks`(新增);`listPaperEvidenceTaskItems`。
- Produces: 全局模式(无 taskId):并行拉取进行中任务 items 合并、条目附任务名徽章(`data-testid="evidence-queue-task-badge-{taskId}"`);任务模式(有 taskId)行为不变。

- [ ] **Step 1: 追加失败测试**

在 `TaskItemQueue.test.tsx` 追加(vi.mock 工厂增加 `listPaperEvidenceTasks`):

```tsx
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

  it('全局模式:未选任务时并行拉取进行中任务 items,合并置信度升序,条目带任务徽章', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 'ta', name: '任务A', status: 'running' }),
        makeTask({ id: 'tb', name: '任务B', status: 'paused' }),
        makeTask({ id: 'tc', name: '任务C', status: 'completed' }), // 非进行中,不拉 items
      ], total: 3,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockImplementation(async (taskId: string) => ({
      items: taskId === 'ta'
        ? [makeItem({ id: 'a1', target_id: 'a-high', label: 'AHigh', current_confidence: 0.9 })]
        : [makeItem({ id: 'b1', target_id: 'b-null', label: 'BNull', current_confidence: null })],
    }))
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('BNull')).toBeTruthy())
    // null 最前:tb 的 BNull 排在 ta 的 AHigh 前
    expect(queueItemIds(container)).toEqual(['evidence-queue-item-b-null', 'evidence-queue-item-a-high'])
    // 只拉了进行中任务,未拉 tc
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalledWith('ta', { limit: 100 })
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalledWith('tb', { limit: 100 })
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).not.toHaveBeenCalledWith('tc', { limit: 100 })
    // 任务名徽章
    expect(screen.getByText('任务A')).toBeTruthy()
    expect(screen.getByText('任务B')).toBeTruthy()
  })

  it('全局模式:单任务 items 失败不影响其他任务', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' }), makeTask({ id: 'tb', name: '任务B', status: 'running' })], total: 2,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({ items: [makeItem({ id: 'b1', target_id: 'b-1', label: 'B1', current_confidence: 0.3 })] })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('B1')).toBeTruthy())
    expect(screen.queryByText(/部分任务/)).toBeNull() // 不阻塞,静默跳过失败任务
  })

  it('任务模式:选中任务后只拉该任务 items(徽章不显示)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一', status: 'pending' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a', target_id: 'c-1', label: 'C1', current_confidence: 0.5 })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('C1')).toBeTruthy())
    expect(screen.queryByText('任务一')).toBeNull()
  })
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: FAIL —— 全局模式未实现（无 taskId 时队列为空）

- [ ] **Step 3: 实现全局模式**

修改 `TaskItemQueue.tsx`:

1. imports 增加 `listPaperEvidenceTasks, type PaperEvidenceTask`（endpoints）与 `Promise.allSettled` 用法;state 增加 `taskNames: Record<string, string>`。
2. `loadItems` 拆为两个模式:

```tsx
  const [taskNames, setTaskNames] = useState<Record<string, string>>({})

  const loadItems = useCallback(async () => {
    if (!taskId) {
      // 全局模式:拉取所有进行中任务 → 并行拉各自 items → 合并
      setLoading(true)
      setError(null)
      setItems([])
      try {
        const r = await listPaperEvidenceTasks()
        const active = r.items.filter(t => ['pending', 'running', 'paused'].includes(t.status))
        setTaskNames(Object.fromEntries(active.map(t => [t.id, t.name || t.target_type])))
        const settled = await Promise.allSettled(
          active.map(t => listPaperEvidenceTaskItems(t.id, { limit: 100 })),
        )
        const merged = settled.flatMap((s, i) =>
          s.status === 'fulfilled'
            ? s.value.items.map(it => ({ ...it, __taskId: active[i].id }))
            : [],
        )
        setItems(merged as PaperEvidenceTaskItem[])
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setLoading(false)
      }
      return
    }
    // 任务模式(原逻辑,保留 latestTaskIdRef 守卫)
    const requestedTaskId = taskId
    setLoading(true)
    setError(null)
    setItems([])
    try {
      const r = await listPaperEvidenceTaskItems(requestedTaskId, { limit: 100 })
      if (latestTaskIdRef.current !== requestedTaskId) return
      setItems(r.items)
    } catch (err) {
      if (latestTaskIdRef.current !== requestedTaskId) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (latestTaskIdRef.current === requestedTaskId) setLoading(false)
    }
  }, [taskId])
```

3. 合并结果去重按 id（后端 items 唯一,跨任务合并后同 target 不冲突）;条目卡片渲染任务徽章（仅全局模式,item 带 `__taskId` 时显示任务名）:

```tsx
function QueueItemCard({ item, selected, onOpen, taskName }: { item: PaperEvidenceTaskItem; selected: boolean; onOpen: () => void; taskName?: string | null }) {
  ...
  {taskName && <span className="evidence-queue-task-badge" data-testid={`evidence-queue-task-badge-${(item as any).__taskId}`}>{taskName}</span>}
```

（`__taskId` 用类型断言读取:`const srcTaskId = (item as unknown as { __taskId?: string }).__taskId`;taskName 来自 `srcTaskId ? taskNames[srcTaskId] : undefined`;全局模式条目卡片据此显示任务名徽章。）

4. 空态/筛选/已完成区/回退逻辑保持（全局模式同样适用;回退时 `reopenPaperEvidenceTaskItem(taskId ?? '', item.id)` 需要真实 taskId——全局模式下用 `__taskId` 兜底:`reopenPaperEvidenceTaskItem((item as unknown as { __taskId?: string }).__taskId ?? taskId ?? '', item.id)`）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: PASS —— 11 passed

- [ ] **Step 5: CSS 追加**

```css
/* ── 全局队列任务名徽章 ── */
.evidence-queue-task-badge {
  padding: 2px 8px; border-radius: 999px; background: var(--info-bg);
  color: var(--text-muted); font-size: 11px;
}
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/evidence-center/components/TaskItemQueue.tsx frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx frontend/src/styles.css
git commit -m "feat(evidence-center): 右栏队列全局模式(并行拉进行中任务合并+任务徽章)"
```

**硬约束**:styles.css 外科式处理同上;vi.mock 工厂必须增加 `listPaperEvidenceTasks: vi.fn()`。

---

### Task 3: 页面三栏常显 + 左栏 Claim + 删除 TaskListPanel

**Files:**
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`（tasks 布局断言更新）
- Delete: `frontend/src/pages/evidence-center/components/TaskListPanel.tsx`

**Interfaces:**
- Produces: tasks 模块始终三栏;左栏 = ClaimSummaryPanel(与候选模块一致);`isTasksList/isFullWidth` 移除。

- [ ] **Step 1: 更新页面测试断言**

`EvidenceCenterPage.test.tsx`:
- 删除「tasks 列表视图全宽:无左右栏,渲染任务卡片区」测试。
- 删除「详情视图左栏返回按钮回到任务列表」测试（返回按钮已移入中栏,由模块测试覆盖）。
- 「右栏随 module 切换」测试改回列表态断言:

```tsx
  it('右栏随 module 切换:tasks 渲染待处理队列,candidates 渲染待处理对象队列', () => {
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    expect(screen.getByTestId('evidence-task-queue')).toBeTruthy()
    fireEvent.click(screen.getByText('证据候选'))
    const title = () => container.querySelector('.evidence-right-panel h4')?.textContent ?? ''
    expect(title()).toContain('待处理对象')
  })
```

- 新增:

```tsx
  it('tasks 三栏常显:左栏 Claim 面板,中栏任务区,右栏队列', async () => {
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE], total: 1 })
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByText('任务A')).toBeTruthy())
    expect(container.querySelector('.evidence-left')).toBeTruthy()
    expect(container.querySelector('.evidence-right')).toBeTruthy()
    expect(container.querySelector('.evidence-center-layout-full')).toBeNull()
  })
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: FAIL —— 左栏仍渲染 TaskListPanel/全宽条件仍在

- [ ] **Step 3: 页面改动**

`EvidenceCenterPage.tsx`:

1. 删除 `import { TaskListPanel } from './components/TaskListPanel'`。
2. 删除 `isTasksList` 与 `isFullWidth` 三行,全部还原为 `isPapers`（布局 className、左右栏条件三处）。
3. 左栏分支改为:

```tsx
        {!isPapers && (
          <aside className="evidence-left">
            <ClaimSummaryPanel
              claimText={candidateClaim?.claimText ?? ''}
              components={candidateClaim?.components ?? []}
              targetType={candidateClaim?.targetType ?? ''}
              granularity={candidateClaim?.granularity ?? null}
            />
          </aside>
        )}
```

4. 删除 `frontend/src/pages/evidence-center/components/TaskListPanel.tsx` 文件。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: 三文件全绿（页面测试基线失败只剩 3 个:promotion 接线/ObjectQueue 左栏/initial-queue）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/evidence-center/EvidenceCenterPage.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx
git rm frontend/src/pages/evidence-center/components/TaskListPanel.tsx
git commit -m "refactor(evidence-center): 佐证任务页三栏常显(左栏Claim)+删除TaskListPanel"
```

---

### Task 4: 全量验证

- [ ] **Step 1: 前端全量**

Run: `cd frontend && npx vitest run`
Expected: 佐证任务相关全绿;既有失败 = 基线 16 个(其他模块)不变。

- [ ] **Step 2: tsc + build**

Run: `cd frontend && npx tsc --noEmit` → 0 错误;`npm run build` → 成功

- [ ] **Step 3: 后端回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py tests/test_paper_evidence.py tests/test_paper_evidence_api.py tests/test_paper_evidence_reviews.py -q`
Expected: 52 passed

- [ ] **Step 4: PRD V2 验收清单**

- [ ] 单页三栏常显(左栏 Claim、中栏三态、右栏队列)
- [ ] 未选任务:全局队列(进行中任务合并、置信度升序、任务徽章)
- [ ] 点任务卡片 → 对象卡片(未完成优先+置信度升序)+ 自动选中最低置信度
- [ ] 点对象卡片/队列项 → 中栏就地候选工作区(module 保持 tasks)
- [ ] 「← 任务列表」→ 回任务卡片 + 全局队列
- [ ] 筛选三组 + 已完成区回退重审(全局/任务模式均可用)
- [ ] 未改动候选/审核/晋升模块、ValidationWorkbench、验证中心其他 tab、后端
