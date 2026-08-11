import { DIRECTION_LABEL, type Direction } from './types'

/** 候选模块中栏状态条数据(模块内从现有状态推导,页面级测试经模块渲染断言) */
export interface CandidateStats {
  /** 找到论文总数(已提取候选 + 手动检索结果) */
  foundPapers: number
  /** AI 已提取论文数 */
  extractedPapers: number
  /** 已核验片段数 */
  verifiedPassages: number
  /** 当前已勾选的候选片段数(零时禁止进入人工审核) */
  selectedPassages: number
  /** 0-1;null 表示无可计算覆盖 */
  coverageRatio: number | null
  /** Coverage 已覆盖组件数(如 1/3) */
  coverageSupported: number
  /** Coverage 必需组件总数(无组件时为 0) */
  coverageRequired: number
  direction: Direction | null
  modelAssessment: string | null
}

interface Props {
  stats: CandidateStats | null
  onEnterReview: () => void
}

function formatCoverage(stats: CandidateStats | null): string {
  if (!stats) return '—'
  if (stats.coverageRequired === 0) return stats.coverageRatio == null ? '—' : `${Math.round(stats.coverageRatio * 100)}%`
  return `${stats.coverageSupported}/${stats.coverageRequired}`
}

/** 浅蓝状态条:找到论文 / AI提取 / 已核验 / Coverage / 模型判断(加粗)+ 右侧 [进入人工审核] */
export function PaperStatusSummary({ stats, onEnterReview }: Props) {
  return (
    <div className="evidence-stats-bar" data-testid="evidence-stats-bar">
      <div className="evidence-stats-item">
        <span className="evidence-stats-label">找到论文</span>
        <span className="evidence-stats-value" data-testid="evidence-stats-found">{stats?.foundPapers ?? 0}</span>
      </div>
      <div className="evidence-stats-item">
        <span className="evidence-stats-label">AI提取</span>
        <span className="evidence-stats-value" data-testid="evidence-stats-extracted">{stats?.extractedPapers ?? 0}</span>
      </div>
      <div className="evidence-stats-item">
        <span className="evidence-stats-label">已核验</span>
        <span className="evidence-stats-value" data-testid="evidence-stats-verified">{stats?.verifiedPassages ?? 0}</span>
      </div>
      <div className="evidence-stats-item">
        <span className="evidence-stats-label">Coverage</span>
        <span className="evidence-stats-value" data-testid="evidence-stats-coverage">{formatCoverage(stats)}</span>
      </div>
      {(stats?.direction || stats?.modelAssessment) && (
        <div className="evidence-stats-model" data-testid="evidence-stats-model">
          <span className="evidence-stats-label">模型判断</span>
          {stats.direction && (
            <span className="evidence-stats-direction" data-testid="evidence-stats-direction">
              {DIRECTION_LABEL[stats.direction] ?? stats.direction}
            </span>
          )}
          {stats.modelAssessment && <span className="evidence-stats-assessment">{stats.modelAssessment}</span>}
        </div>
      )}
      <div className="evidence-stats-actions">
        <button
          type="button"
          className="btn btn-sm btn-primary"
          disabled={!stats || stats.selectedPassages === 0}
          title={!stats || stats.selectedPassages === 0 ? '请先勾选已核验的候选片段' : '进入人工审核'}
          onClick={onEnterReview}
        >
          进入人工审核{stats && stats.selectedPassages > 0 ? `（${stats.selectedPassages}）` : ''}
        </button>
      </div>
    </div>
  )
}
