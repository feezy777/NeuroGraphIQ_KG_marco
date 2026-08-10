import { useCallback, useEffect, useState } from 'react'
import { listEvidencePapers, type EvidencePaperItem } from '../../../api/endpoints'
import { PaperCard } from '../components/PaperCard'
import { PaperDetailDrawer } from '../components/PaperDetailDrawer'

const PAGE_SIZE = 20
const YEAR_START = 2015

interface PaperQuery {
  search?: string
  oa?: boolean
  year?: number
  has_fulltext?: boolean
  page: number
}

function yearOptions(): number[] {
  const current = new Date().getFullYear()
  const years: number[] = []
  for (let y = current; y >= YEAR_START; y -= 1) years.push(y)
  return years
}

export function PaperLibraryModule() {
  const [search, setSearch] = useState('')
  const [oaOnly, setOaOnly] = useState(false)
  const [year, setYear] = useState('')
  const [hasFulltext, setHasFulltext] = useState(false)
  const [papers, setPapers] = useState<EvidencePaperItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const loadPapers = useCallback(async (query: PaperQuery) => {
    setLoading(true)
    setError(null)
    try {
      const r = await listEvidencePapers({
        search: query.search || undefined,
        oa: query.oa || undefined,
        year: query.year,
        has_fulltext: query.has_fulltext || undefined,
        page: query.page,
        page_size: PAGE_SIZE,
      })
      setPapers(r.items)
      setTotal(r.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadPapers({ page: 1 })
  }, [loadPapers])

  const buildQuery = useCallback((nextPage: number): PaperQuery => ({
    search: search.trim(),
    oa: oaOnly,
    year: year ? Number(year) : undefined,
    has_fulltext: hasFulltext,
    page: nextPage,
  }), [search, oaOnly, year, hasFulltext])

  const handleSearch = useCallback(() => {
    setPage(1)
    void loadPapers(buildQuery(1))
  }, [loadPapers, buildQuery])

  const goToPage = useCallback((nextPage: number) => {
    setPage(nextPage)
    void loadPapers(buildQuery(nextPage))
  }, [loadPapers, buildQuery])

  return (
    <div className="paper-module">
      <div className="paper-toolbar">
        <div className="paper-toolbar-title">
          <h3>论文库</h3>
          <p className="evidence-module-hint">
            {total > 0 ? `共 ${total} 篇论文,点击卡片查看摘要与全文段落。` : '管理系统已获取的真实论文资源,点击卡片查看摘要与全文。'}
          </p>
        </div>
        <button type="button" className="btn btn-sm" onClick={() => void handleSearch()}>刷新</button>
      </div>

      <form className="paper-search-bar" onSubmit={e => { e.preventDefault(); handleSearch() }}>
        <input
          className="form-input paper-search-input"
          placeholder="搜索标题 / 期刊 / PMID / DOI"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <label className="paper-filter-label">
          <input type="checkbox" checked={oaOnly} onChange={e => setOaOnly(e.target.checked)} />
          仅开放获取
        </label>
        <label className="paper-filter-label">
          年份
          <select className="form-select paper-year-select" value={year} onChange={e => setYear(e.target.value)}>
            <option value="">全部年份</option>
            {yearOptions().map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </label>
        <label className="paper-filter-label">
          <input type="checkbox" checked={hasFulltext} onChange={e => setHasFulltext(e.target.checked)} />
          已解析全文
        </label>
        <button type="submit" className="btn btn-sm btn-primary">搜索</button>
      </form>

      {loading && <div className="paper-loading">加载中…</div>}
      {!loading && error && (
        <div className="paper-error">
          <p>论文加载失败:{error}</p>
          <button type="button" className="btn btn-sm" onClick={() => void handleSearch()}>重试</button>
        </div>
      )}
      {!loading && !error && papers.length === 0 && (
        <div className="paper-empty">暂无论文,先通过「佐证任务」获取并解析论文资源。</div>
      )}
      {!loading && !error && papers.length > 0 && (
        <div className="paper-list">
          {papers.map(p => (
            <PaperCard key={p.id} paper={p} onOpen={setSelectedPaperId} />
          ))}
        </div>
      )}

      {!loading && !error && total > 0 && (
        <div className="paper-pagination">
          <button
            type="button"
            className="btn btn-sm"
            disabled={page <= 1}
            onClick={() => goToPage(page - 1)}
          >
            上一页
          </button>
          <span className="paper-pagination-info">第 {page} / {totalPages} 页 · 共 {total} 篇</span>
          <button
            type="button"
            className="btn btn-sm"
            disabled={page >= totalPages}
            onClick={() => goToPage(page + 1)}
          >
            下一页
          </button>
        </div>
      )}

      {selectedPaperId && (
        <PaperDetailDrawer paperId={selectedPaperId} onClose={() => setSelectedPaperId(null)} />
      )}
    </div>
  )
}
