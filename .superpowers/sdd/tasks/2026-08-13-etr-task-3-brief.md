# Task 3: 任务列表视图（任务卡片网格 + 全宽布局 + 上下文导航语义）

来源：`docs/superpowers/plans/2026-08-13-evidence-tasks-page-redesign.md` Task 3（BASE: 12412d8）

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`（**整体替换**为列表视图 + 详情占位）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`（`openTask` module 改 'tasks'；新增 `closeTask`；**外科式编辑,保留文件中已有内容**）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`（全宽条件扩展;**外科式编辑**）
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`（**整体替换**为列表视图用例）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`（新增 tasks 列表全宽用例,放在「papers 模块例外」测试之后）
- Modify: `frontend/src/styles.css`（文件末尾追加任务卡片网格样式）

**Interfaces:**
- Consumes: Task 2 的 `taskSortRank`、`TASK_STATUS_LABELS`、`taskStatusTone`；既有 `openTask`。
- Produces: `openTask(taskId)` 语义 = 进入 tasks 详情（`apply({ taskId, targetType: null, targetId: null, module: 'tasks' })`）；`closeTask()` = 回列表（清 taskId/target）。模块列表视图渲染 `data-testid="evidence-task-card-grid"` 与 `evidence-task-card-{id}` 卡片。

## Steps

### Step 1: 整体替换模块测试为列表视图用例

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

### Step 2: 运行测试确认失败

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: FAIL —— 旧测试与新模块不匹配（`evidence-task-card-grid` 不存在等）

### Step 3: 整体替换 EvidenceTasksModule（列表视图 + 详情占位）

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

### Step 4: 外科式修改 EvidenceCenterContext（保留文件其余内容）

在 `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`：

接口 `EvidenceCenterContextValue` 的 `openTask: (taskId: string) => void` 之后加一行：

```ts
  closeTask: () => void
```

把现有 `openTask` 实现（模块内 `const openTask = useCallback(...)` 一段,含其注释）整体替换为：

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

value useMemo 对象中 `openTarget,` 之后加 `closeTask,`；依赖数组 `[state, queue, progress, setProgress, gotoModule, openTask, openTarget, ...]` 中 `openTarget,` 之后加 `closeTask,`。

### Step 5: 外科式修改 EvidenceCenterPage（全宽条件）

把 `const isPapers = state.module === 'papers'` 改为：

```tsx
  const isPapers = state.module === 'papers'
  // tasks 列表视图(无 taskId)同论文库一样全宽,隐藏左右栏
  const isTasksList = state.module === 'tasks' && !state.taskId
  const isFullWidth = isPapers || isTasksList
```

并把该组件内其余三处 `isPapers` 替换为 `isFullWidth`（布局 className 一处 + 左栏 aside 条件一处 + 右栏 aside 条件一处）。

### Step 6: styles.css 文件末尾追加

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

### Step 7: 页面测试新增 tasks 列表全宽用例

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

### Step 8: 运行测试确认通过

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: 模块测试 5 passed；页面测试中本任务新增用例通过。页面测试仍有非 tasks 相关的基线失败(五模块接线 promotion / 其他模块左栏 ObjectQueue / initial-queue ObjectQueue candidates 等)——保持原状,不是你的问题。

## 硬约束

- **不要执行任何 git 操作（不提交、不 add、不 stash）**——提交由控制器做外科式处理(工作树中有大量其他未提交改动)。
- 只允许改动上述 6 个文件。不改后端、不改其他前端文件。
- EvidenceCenterContext.tsx / EvidenceCenterPage.tsx / styles.css 三个文件里已有其他未提交改动,必须**保留它们**,只做本任务指定的外科式修改。
- EvidenceTasksModule.tsx 与 EvidenceTasksModule.test.tsx 为整体替换,替换后文件内容必须与 brief 完全一致。
