import type { ReactNode } from 'react'

interface Props {
  /** 有检索结果且未展开 → 渲染折叠条(Query 摘要 + 重新搜索 + 展开 + 提取所选) */
  collapsed: boolean
  busy: boolean
  /** 手动检索式 */
  query: string
  onQueryChange: (query: string) => void
  onSearch: () => void
  onRestoreRecommended: () => void
  /** 系统推荐关键词 chips(已应用用户清除) */
  queryTerms: string[]
  onClearTerm: (term: string) => void
  /** 折叠条 Query 摘要(手动检索式 → 推荐词 → 占位) */
  querySummary: string
  onExpand: () => void
  /** 已勾选论文数(折叠条 [提取所选论文(N)] 计数) */
  selectedCount: number
  onExtractSelected: () => void
  /** 检索过滤层(PaperSearchFilters) */
  filters?: ReactNode
  /** 批量操作层(PaperBatchActions) */
  batchActions?: ReactNode
}

/**
 * 中栏搜索面板:第一层「查找相关论文」(大搜索框 + 重新搜索/恢复系统推荐 + Query Chips)。
 * 有检索结果时整体折叠为一条(Query 摘要 + 重新搜索/展开检索/提取所选论文),filters 与 batchActions 仅展开态渲染。
 */
export function PaperSearchPanel({
  collapsed,
  busy,
  query,
  onQueryChange,
  onSearch,
  onRestoreRecommended,
  queryTerms,
  onClearTerm,
  querySummary,
  onExpand,
  selectedCount,
  onExtractSelected,
  filters,
  batchActions,
}: Props) {
  if (collapsed) {
    return (
      <div className="evidence-search evidence-search-collapsed" data-testid="evidence-search-collapsed">
        <span className="evidence-search-collapsed-label">已检索</span>
        <span
          className="evidence-search-collapsed-query"
          data-testid="evidence-search-collapsed-query"
          title={querySummary}
        >
          {querySummary}
        </span>
        <span className="evidence-search-collapsed-actions">
          <button type="button" className="btn btn-sm" disabled={busy} onClick={onSearch}>
            {busy ? '检索中…' : '重新搜索'}
          </button>
          <button type="button" className="btn btn-sm" onClick={onExpand}>
            展开检索
          </button>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            data-testid="evidence-collapsed-extract"
            disabled={busy || selectedCount === 0}
            onClick={onExtractSelected}
          >
            提取所选论文（{selectedCount}）
          </button>
        </span>
      </div>
    )
  }
  return (
    <div className="evidence-search" data-testid="evidence-search">
      <div className="evidence-search-layer">
        <h4 className="evidence-search-title">查找相关论文</h4>
        <div className="evidence-search-row">
          <input
            className="filter-input evidence-search-query"
            data-testid="evidence-search-query"
            value={query}
            onChange={e => onQueryChange(e.target.value)}
            placeholder="检索式 / 关键词（留空使用系统推荐检索式）"
          />
          <button type="button" className="btn btn-sm" disabled={busy} onClick={onSearch}>
            {busy ? '检索中…' : '重新搜索'}
          </button>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={onRestoreRecommended}>
            恢复系统推荐
          </button>
        </div>
        {queryTerms.length > 0 && (
          <div className="evidence-search-terms" data-testid="evidence-search-terms">
            {queryTerms.map(term => (
              <span key={term} className="evidence-query-term" data-testid="evidence-query-term">
                {term}
                <button
                  type="button"
                  className="evidence-query-term-clear"
                  aria-label={`清空关键词 ${term}`}
                  onClick={() => onClearTerm(term)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
      {filters}
      {batchActions}
    </div>
  )
}
