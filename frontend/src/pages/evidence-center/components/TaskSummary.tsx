import { TASK_REVIEW_LABELS, TASK_STATUS_LABELS, taskReviewTone, taskStatusTone } from './taskStatus'

/** 佐证任务模块经 Context 推送到右栏的选中任务摘要(与 S3 reviewDecision / S4 promotionImpact 同模式) */
export interface TaskSummaryData {
  id: string
  name: string | null
  targetType: string
  mode: string
  granularity: string | null
  status: string
  reviewStatus: string | null
  total: number
  processed: number
  awaitingReview: number
  failed: number
  createdAt: string | null
}

/** 任务模块注册到 Context 的右栏操作(对话框与列表刷新都在模块内,经回调触发) */
export interface TaskSummaryActions {
  onCreateBatch: () => void
  onRefresh: () => void
}

interface Props {
  data: TaskSummaryData | null
  /** 开始人工处理:进入证据候选模块(openTask) */
  onStartReview: () => void
  onCreateBatch: () => void
  onRefresh: () => void
}

const MODE_LABELS: Record<string, string> = {
  existence: '存在性',
  function: '功能',
  relation: '关系',
  combined: '组合',
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  // UTC 输出,避免测试与浏览器时区差异导致断言漂移
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

/** 右栏任务摘要:选中任务的状态/进度计数条/任务信息 + [开始人工处理] [创建批量预处理] [刷新] */
export function TaskSummary({ data, onStartReview, onCreateBatch, onRefresh }: Props) {
  if (!data) {
    return (
      <div className="evidence-task-summary" data-testid="evidence-task-summary">
        <h4>任务摘要</h4>
        <p className="evidence-module-hint">在左侧任务列表中选择一个任务，查看处理进度与操作。</p>
      </div>
    )
  }

  const total = data.total
  const pct = (n: number) => (total > 0 ? Math.min(100, Math.round((n / total) * 100)) : 0)
  const statusLabel = TASK_STATUS_LABELS[data.status] ?? data.status
  const reviewLabel = TASK_REVIEW_LABELS[data.reviewStatus ?? ''] ?? data.reviewStatus ?? '—'

  return (
    <div className="evidence-task-summary" data-testid="evidence-task-summary">
      <h4>任务摘要</h4>

      <div className="evidence-task-summary-name">{data.name || data.targetType}</div>
      <div className="evidence-task-summary-meta">
        <span className="evidence-task-type">{data.targetType}</span>
        <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(data.status)}`}>预处理 · {statusLabel}</span>
        <span className={`evidence-task-chip evidence-task-chip-${taskReviewTone(data.reviewStatus)}`}>审核 · {reviewLabel}</span>
      </div>

      <div className="evidence-task-summary-section">
        <span className="evidence-summary-label">处理进度</span>
        <div className="evidence-progress-bar" data-testid="evidence-progress-bar">
          <span className="evidence-progress-seg evidence-progress-ok" data-testid="evidence-progress-ok" style={{ width: `${pct(data.processed)}%` }} />
          <span className="evidence-progress-seg evidence-progress-warn" data-testid="evidence-progress-warn" style={{ width: `${pct(data.awaitingReview)}%` }} />
          <span className="evidence-progress-seg evidence-progress-bad" data-testid="evidence-progress-bad" style={{ width: `${pct(data.failed)}%` }} />
        </div>
        <div className="evidence-task-progress-stats">
          <span>已处理 <b>{data.processed}</b></span>
          <span>待审 <b>{data.awaitingReview}</b></span>
          <span>失败 <b>{data.failed}</b></span>
          <span>总数 <b>{total}</b></span>
        </div>
      </div>

      <div className="evidence-section-divider" />

      <dl className="evidence-summary-stats">
        <div className="evidence-summary-stat">
          <dt>模式</dt>
          <dd>{MODE_LABELS[data.mode] ?? data.mode}</dd>
        </div>
        <div className="evidence-summary-stat">
          <dt>粒度</dt>
          <dd>{data.granularity || '—'}</dd>
        </div>
        <div className="evidence-summary-stat">
          <dt>创建时间</dt>
          <dd>{formatDate(data.createdAt)}</dd>
        </div>
      </dl>

      <div className="evidence-task-summary-actions">
        <button type="button" className="btn btn-sm btn-primary" onClick={onStartReview}>
          开始人工处理
        </button>
        <button type="button" className="btn btn-sm" onClick={onCreateBatch}>
          创建批量预处理
        </button>
        <button type="button" className="btn btn-sm" onClick={onRefresh}>
          刷新
        </button>
      </div>
    </div>
  )
}
