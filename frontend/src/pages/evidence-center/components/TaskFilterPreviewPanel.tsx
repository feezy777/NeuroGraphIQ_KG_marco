import { useMemo } from 'react'
import { Eye, History, Info } from 'lucide-react'
import type { PaperEvidenceTask } from '../../../api/endpoints'
import { useEvidenceCenter, type TaskFilterGroup } from '../EvidenceCenterContext'
import { navigateToEvidenceCandidates } from '../evidenceCenterUrl'
import { useEvidenceTaskItems } from './useEvidenceTaskItems'
import {
  PREPROCESS_OUTCOME_LABELS,
  TARGET_TYPE_LABELS,
  WORK_STATUS_LABELS,
  formatConfidencePercent,
  objectCardTitle,
  workStatusTone,
} from './taskStatus'

const FILTER_GROUPS: { key: TaskFilterGroup; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'connection', label: '连接' },
  { key: 'circuit', label: '回路' },
  { key: 'function', label: '功能' },
]

const GROUP_TYPES: Record<TaskFilterGroup, string[] | null> = {
  all: null,
  connection: ['connection', 'projection'],
  circuit: ['circuit', 'circuit_step', 'circuit_function'],
  function: ['region_function', 'projection_function'],
}

/** 任务证据进度:完成数 / 总数 */
export function taskEvidenceProgress(t: PaperEvidenceTask): { done: number; total: number } {
  const c = t.item_counts ?? {
    total: 0, processing: 0, pending: 0, awaiting_review: 0, completed: 0, skipped: 0, failed: 0, cancelled: 0,
  }
  return { done: c.completed + c.skipped, total: c.total }
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/** 佐证任务左栏:任务筛选 + 任务预览(选中卡片后实时展示完整信息;「继续验证」才跳转) */
export function TaskFilterPreviewPanel() {
  const { selectedTaskId, taskFilterGroup, setTaskFilterGroup } = useEvidenceCenter()
  const { tasks } = useEvidenceTaskItems()

  const selected = useMemo(
    () => tasks.find(t => t.id === selectedTaskId) ?? null,
    [tasks, selectedTaskId],
  )

  const handleContinue = (t: PaperEvidenceTask) => {
    if (!t.target_id) return
    navigateToEvidenceCandidates({
      items: [{
        target_type: t.target_type,
        target_id: t.target_id,
        label: t.display_name_cn ?? t.display_name_en ?? '',
        confidence: t.display_confidence ?? null,
      }],
      taskId: t.id,
    })
  }

  return (
    <div className="task-filter-preview" data-testid="task-filter-preview">
      <div className="task-filter-section" data-testid="task-filter-group">
        <div className="task-filter-section-title">任务筛选</div>
        <div className="task-filter-pills">
          {FILTER_GROUPS.map(g => (
            <button
              key={g.key}
              type="button"
              className={`task-filter-pill${taskFilterGroup === g.key ? ' task-filter-pill-active' : ''}`}
              onClick={() => setTaskFilterGroup(g.key)}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>

      <div className="task-preview-section" data-testid="task-preview">
        <div className="task-filter-section-title">任务预览</div>
        {!selected ? (
          <div className="task-preview-hint" data-testid="task-preview-hint">
            点击任务卡片查看验证事实
          </div>
        ) : (
          <div className="task-preview-card" data-testid="task-preview-card">
            <div className="task-preview-title">{objectCardTitle(
              selected.display_name_cn,
              selected.display_name_en,
              `${TARGET_TYPE_LABELS[selected.target_type] ?? selected.target_type} #${(selected.target_id ?? selected.id).slice(0, 8)}`,
            )}</div>
            <div className="task-preview-row">
              <span className={`evidence-task-chip evidence-task-chip-${workStatusTone(selected.work_status)}`}>
                {WORK_STATUS_LABELS[selected.work_status] ?? selected.work_status}
              </span>
            </div>
            <div className="task-preview-detail">
              <span>对象类型</span><b>{TARGET_TYPE_LABELS[selected.target_type] ?? selected.target_type}</b>
            </div>
            <div className="task-preview-detail">
              <span>当前置信度</span><b>{formatConfidencePercent(selected.display_confidence)}</b>
            </div>
            <div className="task-preview-detail">
              <span>证据进度</span>
              <b>{taskEvidenceProgress(selected).done} / {taskEvidenceProgress(selected).total}</b>
            </div>
            <div className="task-preview-detail">
              <span>创建时间</span><b>{fmtTime(selected.created_at)}</b>
            </div>
            <div className="task-preview-detail">
              <span>最近处理</span><b>{fmtTime(selected.finished_at ?? selected.created_at)}</b>
            </div>
            <div className="task-preview-detail">
              <span>任务 ID</span><b className="task-preview-id">{selected.id.slice(0, 8)}</b>
            </div>
            {selected.preprocess_outcome && PREPROCESS_OUTCOME_LABELS[selected.preprocess_outcome] && (
              <div className="task-preview-detail">
                <span>预处理</span>
                <b className="task-preview-outcome">{PREPROCESS_OUTCOME_LABELS[selected.preprocess_outcome]}</b>
              </div>
            )}
            <div className="task-preview-actions">
              <button
                type="button"
                className="btn btn-sm btn-primary task-preview-primary"
                data-testid="task-preview-continue"
                onClick={() => handleContinue(selected)}
              >
                {selected.work_status === 'completed' ? '查看结果' : '继续验证'}
              </button>
              <button type="button" className="btn btn-sm" title="查看历史" data-testid="task-preview-history">
                <History size={13} />
              </button>
              <button type="button" className="btn btn-sm" title="查看详情" data-testid="task-preview-detail-btn">
                <Eye size={13} />
              </button>
            </div>
          </div>
        )}
        <div className="task-preview-foot" data-testid="task-preview-foot">
          <Info size={12} /> 点击卡片查看详情,「继续验证」进入处理流程
        </div>
      </div>
    </div>
  )
}

export { GROUP_TYPES }
