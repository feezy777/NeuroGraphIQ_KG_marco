import type { EvidencePaperItem } from '../../../api/endpoints'

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
