import { useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import type { PaperEvidenceTask } from '../../../api/endpoints'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { deriveTaskWorkStatus, TARGET_TYPE_LABELS, taskDisplayName } from '../components/taskStatus'
import { useEvidenceTaskItems, type EvidenceQueueItem } from '../components/useEvidenceTaskItems'
import { EvidenceCandidatesModule } from './EvidenceCandidatesModule'

/** 任务卡片:统一状态体系(状态由该任务对象推导)+ 计数;点击选中任务(左栏队列过滤到该任务) */
function TaskCard({ task, items, selected, onOpen }: {
  task: PaperEvidenceTask
  items: EvidenceQueueItem[]
  selected: boolean
  onOpen: () => void
}) {
  const st = deriveTaskWorkStatus(items)
  const pending = items.filter(it => ['pending', 'searching', 'fetching', 'retrieving', 'extracting', 'verifying', 'awaiting_review'].includes(it.status)).length
  const done = items.length - pending
  const failed = items.filter(it => it.status === 'failed').length
  return (
    <button
      type="button"
      className={`evidence-task-card${selected ? ' evidence-task-card-selected' : ''}`}
      data-testid={`evidence-task-card-${task.id}`}
      onClick={onOpen}
    >
      <div className="evidence-task-card-head">
        <span className="evidence-task-card-name">{taskDisplayName(task)}</span>
        <span className={`evidence-task-chip evidence-task-chip-${st.tone}`}>{st.label}</span>
      </div>
      <div className="evidence-task-card-type">{TARGET_TYPE_LABELS[task.target_type] ?? task.target_type}</div>
      <div className="evidence-task-card-stats">
        <span>待处理 <b>{pending}</b></span>
        <span>已处理 <b>{done}</b></span>
        {failed > 0 && <span className="evidence-task-card-failed">失败 <b>{failed}</b></span>}
      </div>
    </button>
  )
}

/** 佐证任务中栏:任务卡片列表(统一状态体系);选中对象后就地打开证据候选工作区 */
export function EvidenceTasksModule() {
  const { state, openTask } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const { items, tasks, loading, error, reload } = useEvidenceTaskItems()
  const [createOpen, setCreateOpen] = useState(false)

  const targetResolved = Boolean(
    state.targetType && state.targetId
    && items.some(it => it.target_type === state.targetType && it.target_id === state.targetId),
  )

  // 对象按来源任务分组(任务卡片的统一状态推导用)
  const itemsByTask = useMemo(() => {
    const map: Record<string, EvidenceQueueItem[]> = {}
    for (const it of items) {
      if (!it.__taskId) continue
      ;(map[it.__taskId] ??= []).push(it)
    }
    return map
  }, [items])

  const sortedTasks = useMemo(() => {
    return [...tasks].sort((a, b) => {
      const ra = deriveTaskWorkStatus(itemsByTask[a.id] ?? []).rank
      const rb = deriveTaskWorkStatus(itemsByTask[b.id] ?? []).rank
      if (ra !== rb) return ra - rb
      return (b.created_at ?? '').localeCompare(a.created_at ?? '')
    })
  }, [tasks, itemsByTask])

  // 选中对象 → 工作区
  if (!loading && !error && targetResolved) {
    return (
      <div className="evidence-task-module">
        <EvidenceCandidatesModule />
      </div>
    )
  }

  return (
    <div className="evidence-task-module">
      <div className="evidence-task-toolbar">
        <div className="evidence-task-toolbar-title">
          <h3>佐证任务</h3>
          <p className="evidence-module-hint">
            任务状态由对象状态统一推导(进行中/待审核/部分失败/已完成);点击任务卡片筛选左栏队列,点击左/右对象进入工作区。
          </p>
        </div>
        <div className="evidence-task-toolbar-actions">
          <button type="button" className="btn btn-sm" onClick={reload}>刷新</button>
          <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
        </div>
      </div>

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
              items={itemsByTask[t.id] ?? []}
              selected={state.taskId === t.id}
              onOpen={() => openTask(t.id)}
            />
          ))}
        </div>
      )}

      <CreateBatchTaskDialog
        open={createOpen}
        granularity={granularity}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); reload() }}
      />
    </div>
  )
}
