import { useEffect, useState } from 'react'
import { Inbox } from 'lucide-react'
import { listPaperEvidenceTasks, type PaperEvidenceTask } from '../../../api/endpoints'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { taskDisplayName } from '../components/taskStatus'
import { useEvidenceTaskItems } from '../components/useEvidenceTaskItems'
import { EvidenceCandidatesModule } from './EvidenceCandidatesModule'

/** 佐证任务中栏:选中对象后就地打开证据候选工作区;未选中时提示从左侧待处理队列选择 */
export function EvidenceTasksModule() {
  const { state, closeTask } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const { items, loading, error, reload } = useEvidenceTaskItems()
  const [createOpen, setCreateOpen] = useState(false)
  const [task, setTask] = useState<PaperEvidenceTask | null>(null)

  // 任务模式时取任务展示名(中栏标题用)
  useEffect(() => {
    if (!state.taskId) { setTask(null); return }
    let cancelled = false
    listPaperEvidenceTasks({ limit: 200 })
      .then(r => {
        if (cancelled) return
        const t = r.items.find(x => x.id === state.taskId)
        if (t) setTask(t)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [state.taskId])

  const targetResolved = Boolean(
    state.targetType && state.targetId
    && items.some(it => it.target_type === state.targetType && it.target_id === state.targetId),
  )

  return (
    <div className="evidence-task-module">
      <div className="evidence-task-toolbar">
        <div className="evidence-task-toolbar-title">
          <h3>{state.taskId && task ? taskDisplayName(task) : '佐证任务'}</h3>
          <p className="evidence-module-hint">
            {state.taskId
              ? '左侧为该任务的待处理对象,右侧为已处理数据;点击对象进入证据佐证工作区。'
              : '左侧为所有进行中任务的待处理对象(按置信度优先级),右侧为已处理数据;点击对象进入证据佐证工作区。'}
          </p>
        </div>
        <div className="evidence-task-toolbar-actions">
          {state.taskId && (
            <button type="button" className="btn btn-sm btn-outline" data-testid="evidence-task-middle-back" onClick={closeTask}>← 返回全局</button>
          )}
          <button type="button" className="btn btn-sm" onClick={reload}>刷新</button>
          <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
        </div>
      </div>

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>对象列表加载失败:{error}</p>
          <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
        </div>
      )}
      {!loading && !error && targetResolved && <EvidenceCandidatesModule />}
      {!loading && !error && !targetResolved && (
        <EmptyState
          icon={<Inbox size={24} />}
          title="未选择对象"
          description="点击左侧待处理对象(或右侧已处理对象)打开证据佐证工作区。"
          testId="evidence-tasks-no-target"
        />
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
