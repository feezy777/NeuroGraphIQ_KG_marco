import { DIRECTION_LABEL, type Direction } from './types'

/** 候选模块推送到 Context、由右栏渲染的候选摘要数据 */
export interface CandidateSummaryData {
  claimText: string
  foundPapers: number
  extractedPapers: number
  verifiedPassages: number
  /** 当前已勾选的候选片段数(零时禁止进入人工审核) */
  selectedPassages: number
  /** 0-1;null 表示无可计算覆盖 */
  coverageRatio: number | null
  direction: Direction | null
  modelAssessment: string | null
}

interface Props {
  data: CandidateSummaryData | null
  onEnterReview: () => void
}

function formatCoverage(ratio: number | null): string {
  return ratio == null ? '—' : `${Math.round(ratio * 100)}%`
}

/** 右栏候选摘要:只读统计 + [进入人工审核];禁止 Reviewer 修改控件与 attach */
export function CandidateSummary({ data, onEnterReview }: Props) {
  return (
    <div className="evidence-candidate-summary" data-testid="evidence-candidate-summary">
      <h4>候选摘要</h4>
      {!data ? (
        <p className="evidence-module-hint">暂无候选数据，请先在「佐证任务」中打开任务。</p>
      ) : (
        <>
          <div className="evidence-summary-claim">
            <span className="evidence-summary-label">当前 Claim</span>
            <p className="evidence-summary-claim-text">{data.claimText || '—'}</p>
          </div>
          <dl className="evidence-summary-stats">
            <div className="evidence-summary-stat">
              <dt>找到论文</dt>
              <dd>{data.foundPapers}</dd>
            </div>
            <div className="evidence-summary-stat">
              <dt>AI 提取论文</dt>
              <dd>{data.extractedPapers}</dd>
            </div>
            <div className="evidence-summary-stat">
              <dt>已核验片段</dt>
              <dd>{data.verifiedPassages}</dd>
            </div>
            <div className="evidence-summary-stat">
              <dt>Coverage</dt>
              <dd>{formatCoverage(data.coverageRatio)}</dd>
            </div>
          </dl>
          {data.direction && (
            <div className="evidence-summary-model">
              <span className="evidence-summary-label">模型判断</span>
              <span className="evidence-summary-direction">
                {DIRECTION_LABEL[data.direction] ?? data.direction}
              </span>
            </div>
          )}
          {data.modelAssessment && (
            <p className="evidence-summary-assessment">模型评估: {data.modelAssessment}</p>
          )}
          <button
            type="button"
            className="btn btn-sm btn-primary evidence-summary-review"
            disabled={data.selectedPassages === 0}
            title={data.selectedPassages === 0 ? '请先勾选已核验的候选片段' : '进入人工审核'}
            onClick={onEnterReview}
          >
            进入人工审核{data.selectedPassages > 0 ? `（${data.selectedPassages}）` : ''}
          </button>
        </>
      )}
    </div>
  )
}
