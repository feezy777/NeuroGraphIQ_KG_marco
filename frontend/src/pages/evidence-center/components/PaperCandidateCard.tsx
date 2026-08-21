import { DIRECTION_LABEL, type Direction } from './types'

/** 候选论文卡标准化数据(候选模块:任务候选 / 手动检索结果 / 手动提取结果共用) */
export interface CandidatePaperData {
  paperId: string | null
  pmid: string
  doi: string | null
  pmcid: string | null
  title: string
  journal: string
  year: string
  authors: string | null
  source: string | null
  abstract: string | null
  isOa: boolean
  abstractAvailable: boolean
  fulltextAvailable: boolean
  matchReason: string | null
  matchScore: number | null
  /** 是否已有 AI 提取结果(决定是否显示 AI 判断/覆盖度/已核验片段 + [查看证据候选]) */
  extracted: boolean
  modelDirection: string | null
  modelAssessment: string | null
  coverageSummary: Record<string, unknown> | null
  passageCount: number
  verifiedCount: number
}

interface Props {
  paper: CandidatePaperData
  /** 加入提取 checkbox(仅未提取的搜索结果可勾选) */
  selected: boolean
  onToggleSelected: (checked: boolean) => void
  onOpenDetail: () => void
  onExclude: () => void
  onReExtract: () => void
  onViewEvidence: () => void
  reExtracting: boolean
}

/** Coverage 展示:正常路径 N/M(required>0);required 为空/缺失时回退 coverage_ratio 百分比;两者皆无时返回 null */
function coverageSummaryCounts(
  coverage: Record<string, unknown> | null,
): { supported: number; required: number; ratio: number } | null {
  const c = coverage as {
    supported_components?: unknown[]
    required_components?: unknown[]
    coverage_ratio?: number
  } | null
  const required = c?.required_components?.length ?? 0
  const ratio = typeof c?.coverage_ratio === 'number' ? c.coverage_ratio : null
  if (required === 0 && ratio == null) return null
  return { supported: c?.supported_components?.length ?? 0, required, ratio: ratio ?? 0 }
}

/** 候选论文分层卡:标题 / 作者·期刊·年份 / 匹配度·理由 / PMID·DOI·摘要·OA / 操作行(+提取结果) */
export function PaperCandidateCard({
  paper,
  selected,
  onToggleSelected,
  onOpenDetail,
  onExclude,
  onReExtract,
  onViewEvidence,
  reExtracting,
}: Props) {
  const coverage = coverageSummaryCounts(paper.coverageSummary)
  const dirLabel = paper.modelDirection
    ? (DIRECTION_LABEL[paper.modelDirection as Direction] ?? paper.modelDirection)
    : null
  const citeParts = [paper.authors, paper.journal, paper.year].filter(Boolean).join(' · ')

  return (
    <div className="paper-card-candidate" data-testid="paper-card-candidate">
      <div className="paper-card-title-row">
        <a
          className="paper-card-title"
          href={paper.doi ? `https://doi.org/${paper.doi}` : paper.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/` : undefined}
          target="_blank" rel="noopener noreferrer"
          style={!(paper.doi || paper.pmid) ? { cursor: 'default', color: 'inherit', textDecoration: 'none' } : undefined}
          onClick={e => { if (!(paper.doi || paper.pmid)) e.preventDefault() }}
        >
          {paper.title || '(无标题)'}
        </a>
      </div>
      <div className="paper-card-cite-row">
        <span className="paper-card-meta">{citeParts || '—'}</span>
      </div>
      {(paper.matchScore != null || paper.matchReason) && (
        <div className="paper-card-match-row" data-testid="paper-card-match">
          {paper.matchScore != null && <span className="paper-card-match-score">匹配 {Math.round(paper.matchScore)}%</span>}
          {paper.matchReason && <span className="paper-card-match-reason">{paper.matchReason}</span>}
        </div>
      )}
{paper.abstract && (
        <div className="paper-card-abstract">{paper.abstract.slice(0, 200)}{paper.abstract.length > 200 ? '…' : ''}</div>
      )}
      <div className="paper-card-tags-row">
        {paper.source && (
          <span className={`paper-card-tag paper-card-tag-src paper-card-tag-src-${paper.source}`}>{paper.source}</span>
        )}
        {paper.pmid && (
          <a className="paper-card-tag paper-card-tag-link" href={`https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`} target="_blank" rel="noopener noreferrer">PMID {paper.pmid}</a>
        )}
        {paper.doi && (
          <a className="paper-card-tag paper-card-tag-link" href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer">DOI</a>
        )}
        {paper.abstractAvailable && <span className="paper-card-tag paper-card-tag-ok">摘要</span>}
        {paper.isOa && paper.fulltextAvailable && <span className="paper-card-tag paper-card-tag-oa">OA 全文</span>}
      </div>
      {paper.extracted && (
        <div className="paper-card-result-row" data-testid="paper-card-result">
          {dirLabel && <span className="paper-card-result-badge paper-card-result-badge-ai">AI判断：{dirLabel}</span>}
          {coverage && (
            <span className="paper-card-result-badge">
              {coverage.required > 0
                ? `AI 初始覆盖 ${coverage.supported}/${coverage.required}`
                : `AI 初始覆盖 ${Math.round(coverage.ratio * 100)}%`}
            </span>
          )}
          <span className="paper-card-result-badge paper-card-result-badge-ok">已核验片段 {paper.verifiedCount}</span>
        </div>
      )}
      <div className="paper-card-actions-row" data-testid="paper-card-actions-row">
        {!paper.extracted && (
          <label className="paper-card-select">
            <input
              type="checkbox"
              checked={selected}
              data-testid="paper-card-select"
              onChange={e => onToggleSelected(e.target.checked)}
            />
            加入提取
          </label>
        )}
        {paper.paperId && (
          <button type="button" className="btn btn-xs" onClick={onOpenDetail}>查看详情</button>
        )}
        <button type="button" className="btn btn-xs" onClick={onExclude}>排除此候选</button>
        {paper.extracted && (
          <button type="button" className="btn btn-xs btn-primary" onClick={onViewEvidence}>查看证据候选</button>
        )}
        {paper.extracted && (
          <button type="button" className="btn btn-xs" disabled={reExtracting} onClick={onReExtract}>
            {reExtracting ? '重新提取中…' : '重新提取'}
          </button>
        )}
      </div>
    </div>
  )
}
