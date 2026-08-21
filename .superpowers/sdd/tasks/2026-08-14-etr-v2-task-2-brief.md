# V2 Task 2: TaskItemQueue 全局模式 + 任务过滤

来源：`docs/superpowers/plans/2026-08-14-evidence-tasks-page-v2.md` Task 2（BASE: e4d602c）

**Files:**
- Modify: `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`
- Modify: `frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx`（追加 3 用例 + vi.mock 工厂增加 listPaperEvidenceTasks + 新增 makeTask 辅助）
- Modify: `frontend/src/styles.css`（末尾追加任务徽章样式;有未提交改动,只追加）

**Interfaces:**
- Consumes: `state.taskId`;`listPaperEvidenceTasks`(新增);`listPaperEvidenceTaskItems`。
- Produces: 全局模式(无 taskId):并行拉取进行中(pending/running/paused)任务 items 合并、条目附任务名徽章(`data-testid="evidence-queue-task-badge-{taskId}"`);任务模式(有 taskId)行为不变。

## Steps

### Step 1: 追加失败测试

`TaskItemQueue.test.tsx`:
1. vi.mock 工厂增加 `listPaperEvidenceTasks: vi.fn(),`。
2. 文件末尾(describe 内)追加 makeTask 辅助与 3 个用例:

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
```

```tsx
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
    expect(screen.queryByText(/队列加载失败/)).toBeNull() // 不阻塞,静默跳过失败任务
  })

  it('任务模式:选中任务后只拉该任务 items(不显示任务徽章)', async () => {
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

注意:现有 8 条用例(待处理排序/筛选/点击/空态/错误重试/已完成区/回退/回退失败)保持不变;其中「任务模式」类用例已用 `#/evidence-center?module=tasks&task_id=t1`,天然覆盖任务模式,无需修改。

### Step 2: 运行测试确认失败

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: FAIL —— 全局模式未实现(无 taskId 时队列为空,新增 2 条失败;第 3 条任务模式应通过)

### Step 3: 实现全局模式

修改 `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`:

**3a. imports 与 state:**

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Inbox } from 'lucide-react'
import {
  listPaperEvidenceTaskItems,
  listPaperEvidenceTasks,
  reopenPaperEvidenceTaskItem,
  type PaperEvidenceTaskItem,
} from '../../../api/endpoints'
```

state 区(在 `actionError` 之后)追加:

```tsx
  const [taskNames, setTaskNames] = useState<Record<string, string>>({})
```

**3b. loadItems 拆两模式**(整体替换现有 loadItems):

```tsx
  const loadItems = useCallback(async () => {
    if (!taskId) {
      // 全局模式:拉取所有进行中任务 → 并行拉各自 items → 合并(单任务失败静默跳过)
      setLoading(true)
      setError(null)
      setItems([])
      setTaskNames({})
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
    setTaskNames({})
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

**3c. QueueItemCard 加任务徽章**(整体替换 QueueItemCard):

```tsx
function QueueItemCard({ item, selected, onOpen, taskName }: {
  item: PaperEvidenceTaskItem
  selected: boolean
  onOpen: () => void
  taskName?: string | null
}) {
  const conf = item.current_confidence
  const srcTaskId = (item as unknown as { __taskId?: string }).__taskId
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
        {taskName && (
          <span className="evidence-queue-task-badge" data-testid={`evidence-queue-task-badge-${srcTaskId}`}>{taskName}</span>
        )}
        {item.preprocess_outcome === 'no_evidence_found' && <span className="ew-meta">未找到有效证据</span>}
        {item.model_direction && <span className="ew-meta">AI:{item.model_direction}</span>}
      </div>
    </div>
  )
}
```

**3d. 待处理区渲染调用处**传 taskName:

```tsx
          {filtered.map(item => (
            <QueueItemCard
              key={item.id}
              item={item}
              selected={state.targetType === item.target_type && state.targetId === item.target_id}
              taskName={(() => {
                const srcTaskId = (item as unknown as { __taskId?: string }).__taskId
                return srcTaskId ? (taskNames[srcTaskId] ?? null) : null
              })()}
              onOpen={() => openTarget(item.target_type, item.target_id, 'tasks')}
            />
          ))}
```

**3e. handleReopen 的 taskId 兜底**(全局模式回退需真实 taskId):

把 `await reopenPaperEvidenceTaskItem(taskId ?? '', item.id)` 改为:

```tsx
      await reopenPaperEvidenceTaskItem(
        (item as unknown as { __taskId?: string }).__taskId ?? taskId ?? '',
        item.id,
      )
```

**3f. 已完成区条目**(全局模式下同样展示;无需任务徽章,保持现状)。

### Step 4: 运行测试确认通过

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: PASS —— 11 passed

### Step 5: styles.css 末尾追加

```css
/* ── 全局队列任务名徽章 ── */
.evidence-queue-task-badge {
  padding: 2px 8px; border-radius: 999px; background: var(--info-bg);
  color: var(--text-muted); font-size: 11px;
}
```

### Step 6: 复跑确认

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: PASS —— 11 passed

## 硬约束

- **不要执行任何 git 操作**——提交由控制器做外科式处理。
- 只允许改动上述 3 个文件。styles.css 已有未提交改动,必须保留,只做追加。
- 不改后端、不改候选/审核/晋升模块、不改 EvidenceTasksModule/EvidenceCenterPage/RightPanel。
- 测试断言不要检查 `module=tasks` URL 字符串。
