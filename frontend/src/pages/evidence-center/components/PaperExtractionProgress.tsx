import type { PaperEvidenceExtractionRun } from '../../../api/endpoints'

const STAGE_LABELS: Record<string, string> = {
  queued: '等待中',
  fetching: '获取全文',
  parsing: '解析全文',
  retrieving: '召回段落',
  locating: '定位候选',
  judging: '严格判定',
  verifying: '原文核验',
  completed: '已命中',
  no_evidence: '未发现证据',
  failed: '失败',
  cancelled: '已取消',
}

const TERMINAL = new Set(['completed', 'partially_failed', 'failed', 'cancelled'])

export interface PaperExtractionProgressProps {
  run: PaperEvidenceExtractionRun
  onCancel: () => void
  onRetryFailed: () => void
  busy?: boolean
}

function itemLabel(status: string, resultJson?: Record<string, unknown> | null): string {
  if (status === 'completed') {
    const passages = Array.isArray(resultJson?.passages) ? resultJson.passages.length : 0
    return passages > 0 ? `已命中 ${passages} 个片段` : STAGE_LABELS.completed
  }
  return STAGE_LABELS[status] ?? status
}

export function PaperExtractionProgress({
  run,
  onCancel,
  onRetryFailed,
  busy = false,
}: PaperExtractionProgressProps) {
  const running = !TERMINAL.has(run.status)
  const processing = run.items.filter(i =>
    !['completed', 'no_evidence', 'failed', 'cancelled', 'queued'].includes(i.status),
  ).length
  const queued = run.items.filter(i => i.status === 'queued').length
  const width = Math.max(0, Math.min(100, run.progress_percent))

  return (
    <div className="evidence-extraction-progress" data-testid="evidence-extraction-progress">
      <div className="evidence-extraction-progress-summary">
        <div
          className="evidence-extraction-progress-bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(width)}
          aria-label="论文提取进度"
        >
          <div className="evidence-extraction-progress-fill" style={{ width: `${width}%` }} />
        </div>
        <div className="evidence-extraction-progress-meta" data-testid="evidence-extraction-progress-meta">
          已完成 {run.completed_items}/{run.total_items} · {Math.round(width)}%
          {' · '}
          命中 {run.evidence_hit_items}
          {' · '}
          无证据 {run.no_evidence_items}
          {' · '}
          失败 {run.failed_items}
          {' · '}
          处理中 {processing + (running ? queued : 0)}
        </div>
      </div>
      <div className="evidence-extraction-progress-actions">
        {running && (
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            disabled={busy || run.cancel_requested}
            onClick={onCancel}
            data-testid="evidence-extraction-cancel"
          >
            {run.cancel_requested ? '取消中…' : '取消'}
          </button>
        )}
        {!running && run.failed_items > 0 && (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={busy}
            onClick={onRetryFailed}
            data-testid="evidence-extraction-retry-failed"
          >
            仅重试失败论文
          </button>
        )}
      </div>
      <ul className="evidence-extraction-progress-list" data-testid="evidence-extraction-item-list">
        {run.items.map(item => (
          <li key={item.id} data-status={item.status} data-testid={`evidence-extraction-item-${item.item_index}`}>
            <span className="evidence-extraction-progress-title">
              {item.title || item.pmid || item.doi || item.pmcid || `论文 #${item.item_index + 1}`}
            </span>
            <span className="evidence-extraction-progress-stage">
              {itemLabel(item.status, item.result_json)}
              {item.error_message ? ` — ${item.error_message}` : ''}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
