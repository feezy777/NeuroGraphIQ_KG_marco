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
    // 共享 hook 挂载时会预取 items,只能断言「未以继续验证参数调用」
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).not.toHaveBeenCalledWith('t1', { status: 'awaiting_review', limit: 1, sort: 'confidence' })
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

