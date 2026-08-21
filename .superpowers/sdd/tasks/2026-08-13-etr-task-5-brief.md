# Task 5: 右栏待处理队列（TaskItemQueue + RightPanel 接入）

来源：`docs/superpowers/plans/2026-08-13-evidence-tasks-page-redesign.md` Task 5（BASE: f318fa9）

**Files:**
- Create: `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`（待处理区 + 筛选 chips;已完成区在 Task 6 追加）
- Create: `frontend/src/pages/evidence-center/components/TaskItemQueue.test.ts`
- Modify: `frontend/src/pages/evidence-center/components/RightPanel.tsx`（**仅 tasks 分支**,外科式:替换 TaskSummary → TaskItemQueue,删除不再使用的 imports 与解构字段）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`（「右栏随 module 切换」用例更新 tasks 断言）
- Modify: `frontend/src/styles.css`（文件末尾追加队列样式）

**Interfaces:**
- Consumes: Task 2 `isUnfinishedItem/sortByConfidenceAsc/TARGET_TYPE_GROUPS/groupOf`;context `state/openTarget`。
- Produces: `TaskItemQueue`(无 props,读 context;`data-testid="evidence-task-queue"`、筛选 `data-testid="evidence-queue-filter"`、条目 `data-testid="evidence-queue-item-{target_id}"`、空态 `data-testid="evidence-queue-empty"`)。

## Steps

### Step 1: 写失败测试

```tsx
// frontend/src/pages/evidence-center/components/TaskItemQueue.test.ts
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
    expect(window.location.hash).toContain('task_id=t1')
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

### Step 2: 运行测试确认失败

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.ts`
Expected: FAIL —— Cannot find module './TaskItemQueue'

### Step 3: 实现 TaskItemQueue（待处理区版本,已完成区 Task 6 追加）

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

### Step 4: RightPanel tasks 分支替换（外科式）

`frontend/src/pages/evidence-center/components/RightPanel.tsx`：

- imports 中删除 `import { TaskSummary } from './TaskSummary'`，新增 `import { TaskItemQueue } from './TaskItemQueue'`。
- `useEvidenceCenter()` 解构中删除 `taskSummary, taskSummaryActions, openTask,`（此三者不再使用;注意该文件工作树中有未提交的候选模块相关改动,必须保留,只删这几个字段与 tasks 分支替换）。
- tasks 分支整体替换为：

```tsx
  if (module === 'tasks') {
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        <TaskItemQueue />
      </aside>
    )
  }
```

### Step 5: 页面测试「右栏随 module 切换」用例更新

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

注意:该页面测试文件的 vi.mock 工厂没有 reopenPaperEvidenceTaskItem —— TaskItemQueue import 它但不调用,无需补 mock;若运行时报 undefined 调用错误再按实际报错补充(不要预先加)。

### Step 6: styles.css 文件末尾追加

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

### Step 7: 运行测试确认通过

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.ts src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: TaskItemQueue 5 passed;模块 9 passed;页面测试 tasks 相关全过(基线失败只剩 3 个:五模块接线 promotion / 其他模块左栏 ObjectQueue / initial-queue)。

## 硬约束

- **不要执行任何 git 操作**——提交由控制器做外科式处理。
- 只允许改动上述 5 个文件。不改后端、不改候选/审核/晋升模块。
- RightPanel.tsx 与 styles.css 已有其他未提交改动,必须保留,只做本任务指定的外科式修改。
- 测试断言不要检查 `module=tasks` URL 字符串。
