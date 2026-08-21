import { FileText } from 'lucide-react'
import { DIRECTION_LABEL, type Direction } from './types'
import { EmptyState } from './EmptyState'

/** 候选模块推送至右栏的提取片段摘要条目 */
export interface CandidatePassageItem {
  hash: string
  passage: string
  direction: string
  evidenceLevel: string
  paperTitle: string
  pmid: string
  paperId: string | null
  confidence: number | null
  sourceVerified: boolean
}

interface PassageSummaryProps {
  passages: CandidatePassageItem[]
  /** 点击片段后打开中间区域的论文证据视图 */
  onViewPaper: (paperId: string) => void
  /** 多选模式：勾选的 passage hash 集合 */
  selectedHashes?: Set<string>
  onToggleSelect?: (hash: string, checked: boolean) => void
  /** 已选 N 条 → 进入人工审核 */
  onEnterReview?: () => void
  /** 全选 / 取消全选 */
  onSelectAll?: (checked: boolean) => void
}

function directionBadgeClass(direction: string): string {
  if (direction === 'supports') return 'passage-summary-badge-support'
  if (direction === 'partial') return 'passage-summary-badge-partial'
  if (direction === 'contradicts') return 'passage-summary-badge-contradict'
  return ''
}

/**
 * 右栏候选佐证原文片段聚合面板:标题 + 简介 + 紧凑片段卡片列表。
 * 候选人模块执行批量提取后,所有已核验片段在此集中展示。
 */
export function PassageSummary({ passages, onViewPaper, selectedHashes, onToggleSelect, onEnterReview, onSelectAll }: PassageSummaryProps) {
  const verified = passages.filter(p => p.sourceVerified)
  const selectedCount = selectedHashes ? verified.filter(p => selectedHashes.has(p.hash)).length : 0
  const allSelected = verified.length > 0 && verified.every(p => selectedHashes?.has(p.hash))

  if (passages.length === 0) {
    return (
      <section className="passage-summary" data-testid="passage-summary">
        <div className="passage-summary-head">
          <h4 className="passage-summary-title">候选佐证原文</h4>
        </div>
        <EmptyState
          icon={<FileText size={20} />}
          title="暂无提取片段"
          description="执行「提取所选论文」后,已核验的候选佐证原文片段将在此聚合展示。"
        />
      </section>
    )
  }

  const unverified = passages.filter(p => !p.sourceVerified)

  return (
    <section className="passage-summary" data-testid="passage-summary">
      <div className="passage-summary-head">
        <h4 className="passage-summary-title">候选佐证原文</h4>
        <span className="passage-summary-count" data-testid="passage-summary-count">{passages.length}</span>
        {onSelectAll && verified.length > 0 && (
          <label className="passage-summary-selectall">
            <input type="checkbox" checked={allSelected} onChange={e => onSelectAll(e.target.checked)} />全选
          </label>
        )}
        {onEnterReview && selectedCount > 0 && (
          <button type="button" className="btn btn-xs btn-primary" onClick={onEnterReview}>
            进入人工审核({selectedCount})
          </button>
        )}
      </div>
      {verified.length > 0 && (
        <div className="passage-summary-section">
          <span className="passage-summary-section-label">
            已核验 ({verified.length})
          </span>
          {verified.map(item => (
            <PassageCard
              key={item.hash}
              item={item}
              onViewPaper={onViewPaper}
            />
          ))}
        </div>
      )}
      {unverified.length > 0 && (
        <div className="passage-summary-section">
          <span className="passage-summary-section-label">
            待核验 ({unverified.length})
          </span>
          {unverified.map(item => (
            <PassageCard
              key={item.hash}
              item={item}
              onViewPaper={onViewPaper}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function PassageCard({
  item,
  onViewPaper,
  selected,
  onToggleSelect,
}: {
  item: CandidatePassageItem
  onViewPaper: (paperId: string) => void
  selected?: boolean
  onToggleSelect?: (hash: string, checked: boolean) => void
}) {
  const dirLabel = DIRECTION_LABEL[item.direction as Direction] ?? item.direction
  const snippet = item.passage.length > 120 ? item.passage.slice(0, 120) + '…' : item.passage
  const titleShort = item.paperTitle.length > 60 ? item.paperTitle.slice(0, 60) + '…' : item.paperTitle

  return (
    <div className="passage-summary-card" data-testid="passage-summary-card">
      <div className="passage-summary-card-meta">
        <span className="passage-summary-card-title" title={item.paperTitle}>{titleShort}</span>
        <span className={`passage-summary-card-badge ${directionBadgeClass(item.direction)}`}>
          {dirLabel}
        </span>
        <span className="passage-summary-card-badge passage-summary-card-badge-level">
          {item.evidenceLevel}
        </span>
      </div>
      <div className="passage-summary-card-text">{snippet}</div>
      <div className="passage-summary-card-actions">
        {onToggleSelect && item.sourceVerified && (
          <label className="passage-summary-check">
            <input type="checkbox" checked={selected ?? false}
              onChange={e => onToggleSelect(item.hash, e.target.checked)} />选择
          </label>
        )}
        <button type="button" className="btn btn-xs"
          onClick={() => { if (item.paperId) onViewPaper(item.paperId) }}>查看详情</button>
      </div>
    </div>
  )
}
