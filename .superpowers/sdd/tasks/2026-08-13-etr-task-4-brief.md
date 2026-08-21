# Task 4: 任务详情视图（详情条 + 嵌入候选工作区 + 自动选中首位 + 左栏返回）

来源：`docs/superpowers/plans/2026-08-13-evidence-tasks-page-redesign.md` Task 4（BASE: c6662ee）

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`（**整体替换**为列表视图 + 详情视图完整版）
- Modify: `frontend/src/pages/evidence-center/components/TaskListPanel.tsx`（**整体替换**:本地加载 + openTask 切换 + 返回按钮）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`（**外科式删除**已无消费方的 `taskList/selectedTaskId`——注意这是工作树中未提交的既有改动,只删除,不提交）
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`（追加详情视图 describe 块）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`（重写「切换任务 URL」用例 + 新增返回按钮用例）
- Modify: `frontend/src/styles.css`（文件末尾追加详情条样式）

**Interfaces:**
- Consumes: Task 2 `isUnfinishedItem/sortByConfidenceAsc`、Task 3 `openTask/closeTask`；嵌入 `EvidenceCandidatesModule`（不改动）。
- Produces: 详情视图 `data-testid="evidence-task-detail-bar"`；左栏返回按钮 `data-testid="evidence-task-list-back"`；自动选中队列首位（未完成、置信度最低）并 `openTarget(type, id, 'tasks')`。

**重要提示:buildEvidenceUrl 省略默认 module=tasks,所以 URL 中不会出现 `module=tasks` 参数——测试断言一律不要检查 `module=tasks` 字符串,以行为(详情视图渲染/其他参数)为准。**

## Steps

### Step 1: 模块测试追加详情视图用例

在 `EvidenceTasksModule.test.tsx` 末尾（describe 块内）追加，并在文件顶部 imports 的 vi.mock 工厂保持 Task 3 版本不变。makeTask 函数已存在;新增 makeItem 辅助函数与第二个 describe:

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

### Step 2: 运行测试确认失败

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: 新增 3 条失败(详情占位不渲染 detail-bar、不拉取 items、无自动选中)

### Step 3: 整体替换 EvidenceTasksModule（完整版:列表视图 + 详情视图）

用以下内容整体替换 `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`：

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

### Step 4: 整体替换 TaskListPanel

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

### Step 5: Context 删除 taskList/selectedTaskId（工作树编辑,不提交）

`frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`（此二者已无任何消费方）：

- 删除接口中的两段（`taskList/selectedTaskId` 及注释行）；
- 删除 `const [taskList, setTaskList] = useState...` 与 `const [selectedTaskId, setSelectedTaskId] = useState...`；
- value 中删除 `taskList, setTaskList, selectedTaskId, setSelectedTaskId,`；
- 依赖数组删除 `taskList, selectedTaskId`；
- 删除顶部 `import type { PaperEvidenceTask } from '../../api/endpoints'`。

### Step 6: 页面测试重写「切换任务 URL」用例 + 新增返回按钮用例

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
  })

  it('详情视图左栏返回按钮回到任务列表', async () => {
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE], total: 1 })
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=tasks&task_id=ta'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-task-list-back')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-list-back'))
    await waitFor(() => expect(window.location.hash).not.toContain('task_id='))
  })
```

### Step 7: styles.css 文件末尾追加

```css
/* ── 佐证任务详情视图:详情条 ── */
.evidence-task-detail-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 14px; margin-bottom: 10px;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-soft);
}
.evidence-task-detail-bar h3 { margin: 0; font-size: 15px; }
```

### Step 8: 运行测试确认通过

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: 模块测试 8 passed(5 列表 + 3 详情);页面测试新增/重写用例通过;页面测试仍有非 tasks 基线失败(五模块接线 promotion / 其他模块左栏 ObjectQueue / initial-queue / 右栏随 module 切换)——保持原状。

## 硬约束

- **不要执行任何 git 操作**——提交由控制器做外科式处理(工作树中有大量其他未提交改动)。
- 只允许改动上述 6 个文件。不改后端、不改候选/审核/晋升模块。
- styles.css 已有其他未提交改动,必须保留,只做本任务指定的追加。
- EvidenceTasksModule.tsx / EvidenceTasksModule.test.tsx / TaskListPanel.tsx 为整体替换,替换后必须与 brief 完全一致。
- 测试断言不要检查 `module=tasks` URL 字符串(buildEvidenceUrl 省略默认 module)。
