import type { EvidencePaperItem } from '../../../api/endpoints'
import { DIRECTION_LABEL, type Direction } from './types'

interface Props {
  paper: EvidencePaperItem
  onOpen: (paperId: string) => void
}

function paperIdentifiers(paper: EvidencePaperItem): string[] {
  const ids: string[] = []
  if (paper.pmid) ids.push(`PMID ${paper.pmid}`)
  if (paper.pmcid) ids.push(`PMC ${paper.pmcid}`)
  if (paper.doi) ids.push(`DOI ${paper.doi}`)
  return ids
}

/** 论文库(PaperLibraryModule)搜索卡片 */
export function PaperCard({ paper, onOpen }: Props) {
  const journalLine = [paper.journal, paper.publication_year ? `(${paper.publication_year})` : '']
    .filter(Boolean)
    .join(' ')
  const identifiers = paperIdentifiers(paper)
  return (
    <button
      type="button"
      className="paper-card"
      data-testid="paper-card"
      onClick={() => onOpen(paper.id)}
    >
      <div className="paper-card-main">
        <span className="paper-card-title">{paper.title || '(无标题)'}</span>
        <span className="paper-card-meta">{journalLine || '—'}</span>
        <span className="paper-card-ids">
          {identifiers.length > 0
            ? identifiers.map(id => <span key={id} className="paper-card-id">{id}</span>)
            : '无标识'}
        </span>
      </div>
      <div className="paper-card-chips">
        {paper.is_oa && <span className="paper-badge paper-badge-oa">OA</span>}
        {paper.abstract_available && <span className="paper-badge paper-badge-avail">摘要可用</span>}
        {paper.fulltext_available && <span className="paper-badge paper-badge-avail">全文可用</span>}
        <span className="paper-badge paper-badge-muted">{paper.paragraph_count} 段</span>
        <span className="paper-badge paper-badge-muted">{paper.evidence_count} 条证据</span>
      </div>
    </button>
  )
}

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
  isOa: boolean
  abstractAvailable: boolean
  fulltextAvailable: boolean
  matchReason: string | null
  matchScore: number | null
  /** 是否已有 AI 提取结果(决定是否显示 AI 判断/覆盖度/核验数 + [查看证据候选]) */
  extracted: boolean
  modelDirection: string | null
  modelAssessment: string | null
  coverageSummary: Record<string, unknown> | null
  passageCount: number
  verifiedCount: number
}

interface CandidatePaperCardProps {
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

function coverageRatio(coverage: Record<string, unknown> | null): number | null {
  const ratio = (coverage as { coverage_ratio?: number } | null)?.coverage_ratio
  return typeof ratio === 'number' ? ratio : null
}

/** 证据候选模块分层论文卡:标题 / 作者·期刊·年份 / 匹配信息 / 标签行 / 操作行(+提取结果) */
export function CandidatePaperCard({
  paper,
  selected,
  onToggleSelected,
  onOpenDetail,
  onExclude,
  onReExtract,
  onViewEvidence,
  reExtracting,
}: CandidatePaperCardProps) {
  const ratio = coverageRatio(paper.coverageSummary)
  const dirLabel = paper.modelDirection
    ? (DIRECTION_LABEL[paper.modelDirection as Direction] ?? paper.modelDirection)
    : null
  const citeParts = [paper.authors, paper.journal, paper.year].filter(Boolean).join(' · ')

  return (
    <div className="paper-card-candidate" data-testid="paper-card-candidate">
      <div className="paper-card-title-row">
        <strong className="paper-card-title">{paper.title || '(无标题)'}</strong>
      </div>
      <div className="paper-card-cite-row">
        <span className="paper-card-meta">{citeParts || '—'}</span>
      </div>
      {(paper.matchScore != null || paper.matchReason) && (
        <div className="paper-card-match-row" data-testid="paper-card-match">
          {paper.matchScore != null && <span className="paper-card-match-score">匹配 {Math.round(paper.matchScore * 100)}%</span>}
          {paper.matchReason && <span className="paper-card-match-reason">{paper.matchReason}</span>}
        </div>
      )}
      <div className="paper-card-tags-row">
        {paper.pmid && <span className="paper-card-tag">PMID {paper.pmid}</span>}
        {paper.doi && <span className="paper-card-tag">DOI {paper.doi}</span>}
        {paper.abstractAvailable && <span className="paper-card-tag paper-card-tag-ok">摘要</span>}
        {paper.isOa && paper.fulltextAvailable && <span className="paper-card-tag paper-card-tag-oa">OA 全文</span>}
      </div>
      {paper.extracted && (
        <div className="paper-card-result-row" data-testid="paper-card-result">
          {dirLabel && <span className="paper-card-result-badge">AI 判断 {dirLabel}</span>}
          {ratio != null && <span className="paper-card-result-badge">覆盖度 {Math.round(ratio * 100)}%</span>}
          <span className="paper-card-result-badge">片段 {paper.passageCount}</span>
          <span className="paper-card-result-badge paper-card-result-badge-ok">已核验 {paper.verifiedCount}</span>
        </div>
      )}
      <div className="paper-card-actions-row">
        {paper.paperId && (
          <button type="button" className="btn btn-xs" onClick={onOpenDetail}>查看详情</button>
        )}
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
