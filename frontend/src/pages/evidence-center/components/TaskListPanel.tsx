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
