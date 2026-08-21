# V2 Task 1: EvidenceTasksModule 重写为中栏三态

来源：`docs/superpowers/plans/2026-08-14-evidence-tasks-page-v2.md` Task 1（BASE: 51b27a0）

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`（**整体替换**为中栏三态）
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`（**整体替换**）
- Modify: `frontend/src/styles.css`（文件末尾追加中栏返回条/对象卡片选中态样式;有未提交改动,只追加）

**Interfaces:**
- Consumes: `state(taskId/targetType/targetId)`, `openTask/closeTask/openTarget`(context 已有);`listPaperEvidenceTasks/listPaperEvidenceTaskItems`;`taskItemQueueUtils.ts` 的 `isUnfinishedItem/sortByConfidenceAsc`;`taskStatus.ts` 的 `taskSortRank/TASK_STATUS_LABELS/taskStatusTone`;`EvidenceCandidatesModule`(不改)。
- Produces: 中栏三态;`data-testid="evidence-task-middle-back"`(返回任务列表)、`evidence-task-object-{target_id}`(对象卡片)、`evidence-tasks-all-done`(空态)。

## Steps

### Step 1: 重写模块测试

用以下内容整体替换 `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`。注意:顶部 imports、vi.mock 工厂(20 个 endpoint mock)、`makeTask/makeItem/cardOrder` 辅助函数与当前文件一致(保留);describe 用例整体替换为下方 8 条:

```tsx
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
    await waitFor(() => expect(screen.getByTestId('evidence-task-object-c-done')).toBeTruthy())
    await waitFor(() => expect(window.location.hash).not.toContain('target_id='))
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

  it('点对象卡片(未完成任务,深链带 target 不符) → 自动选中纠正', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-a', label: 'A', current_confidence: 0.5 }),
        makeItem({ id: 'i2', target_id: 'c-b', label: 'B', current_confidence: 0.3 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1&target_type=connection&target_id=stale'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    // stale target 不在 items → 自动选中纠正为置信度最低 c-b
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-b'))
    expect(window.location.hash).not.toContain('stale')
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

### Step 2: 运行测试确认失败

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: FAIL —— 现有模块仍是两页结构,`evidence-task-object-*` 与 `evidence-task-middle-back` 不存在

### Step 3: 重写 EvidenceTasksModule

用以下内容整体替换 `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`用以下内容整体替换(逐字采用):

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

### Step 4: 运行测试确认通过

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: PASS —— 8 passed

### Step 5: styles.css 末尾追加

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

### Step 6: 运行测试确认通过(含样式后复跑)

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: PASS —— 8 passed

## 硬约束

- **不要执行任何 git 操作**——提交由控制器做外科式处理。
- 只允许改动上述 3 个文件。styles.css 已有未提交改动,必须保留,只做追加。
- 不改后端、不改候选/审核/晋升模块、不改 EvidenceCenterPage/RightPanel。
- 测试断言不要检查 `module=tasks` URL 字符串。
