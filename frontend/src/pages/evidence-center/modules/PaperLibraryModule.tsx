import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileSearch, Plus } from 'lucide-react'
import {
  addPaperToLibrary,
  deletePaperSoft,
  getEvidencePaperDetail,
  listEvidencePapers,
  type EvidencePaperDetail,
  type EvidencePaperItem,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { ConfirmDialog } from '../../../components/ConfirmDialog'
import { EmptyState } from '../components/EmptyState'

const PAGE_SIZE = 50
const YEAR_START = 2015

interface PaperQuery {
  search?: string
  oa?: boolean
  year?: number
  has_fulltext?: boolean
  journal?: string
  evidence_min?: number
  page: number
}

function yearOptions(): number[] {
  const current = new Date().getFullYear()
  const years: number[] = []
  for (let y = current; y >= YEAR_START; y -= 1) years.push(y)
  return years
}

function fulltextLabel(p: EvidencePaperItem): { text: string; tone: string } {
  if (p.fulltext_available) return { text: '全文可用', tone: 'ok' }
  if (p.abstract_available) return { text: '仅摘要', tone: 'warn' }
  return { text: '待解析', tone: 'muted' }
}

function evidenceLabel(p: EvidencePaperItem): { text: string; tone: string } {
  return p.evidence_count > 0
    ? { text: `已生成 ${p.evidence_count} 条证据`, tone: 'ok' }
    : { text: '未生成证据', tone: 'muted' }
}

/**
 * 论文库 = 系统论文资产中心(三栏: 列表 / 详情 / 资产关系)。
 * 全部复用既有只读 API(list/get detail)+ 新增添加/软删端点;数据模型零改动。
 */
export function PaperLibraryModule() {
  const { openTarget } = useEvidenceCenter()
  const [search, setSearch] = useState('')
  const [oaOnly, setOaOnly] = useState(false)
  const [year, setYear] = useState('')
  const [hasFulltext, setHasFulltext] = useState(false)
  const [journal, setJournal] = useState('')
  const [evidenceMin, setEvidenceMin] = useState('')
  const [papers, setPapers] = useState<EvidencePaperItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null)
  const [detail, setDetail] = useState<EvidencePaperDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  // 添加论文
  const [addOpen, setAddOpen] = useState(false)
  const [addPmid, setAddPmid] = useState('')
  const [addDoi, setAddDoi] = useState('')
  const [addUrl, setAddUrl] = useState('')
  const [addBusy, setAddBusy] = useState(false)
  const [addMsg, setAddMsg] = useState<string | null>(null)
  // 删除(软删)
  const [deleteTarget, setDeleteTarget] = useState<EvidencePaperItem | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

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
        journal: query.journal || undefined,
        evidence_min: query.evidence_min || undefined,
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

  // 详情加载(点击论文即中栏展示)
  useEffect(() => {
    if (!selectedPaperId) { setDetail(null); return }
    let cancelled = false
    setDetailLoading(true)
    getEvidencePaperDetail(selectedPaperId)
      .then(d => { if (!cancelled) setDetail(d) })
      .catch(() => { if (!cancelled) setDetail(null) })
      .finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selectedPaperId])

  const buildQuery = useCallback((nextPage: number): PaperQuery => ({
    search: search.trim(),
    oa: oaOnly,
    year: year ? Number(year) : undefined,
    has_fulltext: hasFulltext,
    journal: journal.trim(),
    evidence_min: evidenceMin ? Number(evidenceMin) : undefined,
    page: nextPage,
  }), [search, oaOnly, year, hasFulltext, journal, evidenceMin])

  const handleSearch = useCallback(() => {
    setPage(1)
    void loadPapers(buildQuery(1))
  }, [loadPapers, buildQuery])

  const goToPage = useCallback((nextPage: number) => {
    setPage(nextPage)
    void loadPapers(buildQuery(nextPage))
  }, [loadPapers, buildQuery])

  const handleSelect = useCallback((paperId: string) => {
    setSelectedPaperId(paperId)
  }, [])

  const handleAdd = useCallback(async () => {
    if (!addPmid.trim() && !addDoi.trim() && !addUrl.trim()) return
    setAddBusy(true)
    setAddMsg(null)
    try {
      const r = await addPaperToLibrary({
        pmid: addPmid.trim() || null,
        doi: addDoi.trim() || null,
        url: addUrl.trim() || null,
      })
      setAddMsg(r.created
        ? `已添加论文(自动获取元数据)。`
        : '论文已存在(PMID/DOI 去重),未重复创建。')
      setAddPmid(''); setAddDoi(''); setAddUrl('')
      void loadPapers(buildQuery(1))
    } catch (err) {
      setAddMsg(`添加失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setAddBusy(false)
    }
  }, [addPmid, addDoi, addUrl, loadPapers, buildQuery])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return
    setDeleteBusy(true)
    try {
      await deletePaperSoft(deleteTarget.id)
      setMessage(`论文已删除(软删除,历史数据保留)。`)
      if (selectedPaperId === deleteTarget.id) setSelectedPaperId(null)
      setDeleteTarget(null)
      void loadPapers(buildQuery(page))
    } catch (err) {
      setMessage(`删除失败：${err instanceof Error ? err.message : String(err)}`)
      setDeleteTarget(null)
    } finally {
      setDeleteBusy(false)
    }
  }, [deleteTarget, selectedPaperId, loadPapers, buildQuery, page])

  // 详情分章节(paragraphs group by section_title)
  const sections = useMemo(() => {
    if (!detail) return []
    const map = new Map<string, Array<{ index: number; text: string; scope: string }>>()
    for (const p of detail.paragraphs) {
      const key = p.section_title || (p.source_scope === 'abstract' ? 'Abstract' : 'Body')
      const list = map.get(key) ?? []
      list.push({ index: p.paragraph_index, text: p.passage_text, scope: p.source_scope })
      map.set(key, list)
    }
    return [...map.entries()].map(([title, paragraphs]) => ({
      title,
      paragraphs: paragraphs.sort((a, b) => a.index - b.index),
    }))
  }, [detail])

  // 资产统计(右栏: 从 detail 派生)
  const relationStats = useMemo(() => {
    if (!detail) return null
    const byType: Record<string, number> = {}
    for (const t of detail.targets) byType[t.target_type] = (byType[t.target_type] ?? 0) + 1
    return {
      evidence: detail.evidence_count,
      connections: byType.connection ?? 0,
      circuits: (byType.circuit ?? 0) + (byType.circuit_function ?? 0),
      reviews: detail.paper.review_count ?? 0,
      targets: detail.targets,
    }
  }, [detail])

  return (
    <div className="paper-module paper-library-container" data-testid="paper-library-v2">
      <div className="paper-toolbar">
        <div className="paper-toolbar-title">
          <h3>论文库</h3>
          <p className="evidence-module-hint">
            系统论文资产中心 · LLM Discovery → Paper Deduplication(PMID/DOI) → Paper Library · 共 {total} 篇
          </p>
        </div>
        <button type="button" className="btn btn-sm btn-primary" data-testid="paper-add-btn"
          onClick={() => { setAddOpen(true); setAddMsg(null) }}>
          <Plus size={14} style={{ verticalAlign: -2, marginRight: 4 }} />添加论文
        </button>
        <button type="button" className="btn btn-sm" onClick={() => void handleSearch()}>刷新</button>
      </div>

      <div className="paper-library-body">
        {/* ─── 左栏:搜索 + 筛选 + 卡片列表 ─── */}
        <aside className="paper-library-sidebar">
          <form className="paper-search-bar paper-library-search" onSubmit={e => { e.preventDefault(); handleSearch() }}>
            <input
              className="form-input paper-search-input"
              placeholder="搜索标题 / author / PMID / DOI"
              value={search}
              onChange={e => setSearch(e.target.value)}
              data-testid="paper-search-input"
            />
            <div className="paper-library-filters">
              <select className="form-select paper-year-select" value={year} onChange={e => setYear(e.target.value)} aria-label="年份筛选">
                <option value="">全部年份</option>
                {yearOptions().map(y => (<option key={y} value={y}>{y}</option>))}
              </select>
              <input className="form-input" placeholder="期刊" value={journal}
                onChange={e => setJournal(e.target.value)} aria-label="期刊筛选" />
              <select className="form-select" value={hasFulltext ? 'full' : ''} onChange={e => setHasFulltext(e.target.value === 'full')} aria-label="全文状态筛选">
                <option value="">全文:全部</option>
                <option value="full">有全文</option>
                <option value="none">仅摘要/待解析</option>
              </select>
              <select className="form-select" value={evidenceMin} onChange={e => setEvidenceMin(e.target.value)} aria-label="证据状态筛选">
                <option value="">证据:全部</option>
                <option value="1">已生成证据</option>
                <option value="3">≥3 条证据</option>
              </select>
              <label className="paper-filter-label">
                <input type="checkbox" checked={oaOnly} onChange={e => setOaOnly(e.target.checked)} />
                仅开放获取
              </label>
              <button type="submit" className="btn btn-sm btn-primary">搜索</button>
            </div>
          </form>

          {loading && <div className="paper-loading">加载中…</div>}
          {!loading && error && (
            <div className="paper-error">
              <p>论文加载失败:{error}</p>
              <button type="button" className="btn btn-sm" onClick={() => void handleSearch()}>重试</button>
            </div>
          )}
          {!loading && !error && papers.length === 0 && (
            <EmptyState icon={<FileSearch size={24} />} title="暂无论文"
              description="通过「添加论文」或「佐证任务」获取论文资源。" />
          )}
          {!loading && !error && papers.length > 0 && (
            <div className="paper-card-list">
              {papers.map(p => {
                const ft = fulltextLabel(p)
                const ev = evidenceLabel(p)
                return (
                  <div key={p.id}
                    className={`paper-card paper-library-card${selectedPaperId === p.id ? ' paper-library-card-selected' : ''}`}
                    data-testid={`paper-card-${p.id.slice(0, 8)}`}
                    onClick={() => handleSelect(p.id)}
                    data-menu-paper={p.id}
                  >
                    <div className="paper-library-card-title" title={p.title ?? ''}>{p.title ?? '—'}</div>
                    <div className="paper-library-card-meta">
                      {p.journal && <span>{p.journal}</span>}
                      {p.publication_year && <span>{p.publication_year}</span>}
                    </div>
                    <div className="paper-library-card-ids">
                      <span>PMID: {p.pmid ?? '—'}</span>
                      <span>DOI: {p.doi ?? '—'}</span>
                    </div>
                    <div className="paper-library-card-tags">
                      {p.is_oa && <span className="paper-card-oa">OA</span>}
                      <span className={`govw-chip govw-chip-${ft.tone}`}>Full Text · {ft.text}</span>
                      <span className={`govw-chip govw-chip-${ev.tone}`}>Evidence Count · {ev.text}</span>
                    </div>
                    <div className="paper-library-card-actions">
                      <button type="button" className="btn btn-xs" onClick={e => { e.stopPropagation(); setSelectedPaperId(p.id) }}>查看详情</button>
                      <button type="button" className="btn btn-xs btn-danger"
                        data-testid={`paper-delete-${p.id.slice(0, 8)}`}
                        onClick={e => { e.stopPropagation(); setDeleteTarget(p) }}>删除(软)</button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {!loading && !error && total > PAGE_SIZE && (
            <div className="paper-pagination">
              <button type="button" className="btn btn-sm" disabled={page <= 1} onClick={() => goToPage(page - 1)}>上一页</button>
              <span className="paper-pagination-info">第 {page} / {totalPages} 页 · 共 {total} 篇</span>
              <button type="button" className="btn btn-sm" disabled={page >= totalPages} onClick={() => goToPage(page + 1)}>下一页</button>
            </div>
          )}
        </aside>

        {/* ─── 中栏:论文详情 ─── */}
        <main className="paper-detail-panel" data-testid="paper-library-center">
          {!selectedPaperId && (
            <div className="paper-detail-empty">
              <EmptyState icon={<FileSearch size={24} />} title="请选择论文查看详情"
                description="点击左侧论文卡片,此处显示 Paper Information / Abstract / Full Text / Evidence Preview。" />
            </div>
          )}
          {selectedPaperId && detailLoading && <div className="paper-loading">加载论文详情…</div>}
          {selectedPaperId && detail && (
            <>
              <section className="paper-detail-section">
                <h4>Paper Information</h4>
                <dl className="paper-detail-kv">
                  <dt>Title</dt><dd>{detail.paper.title ?? '—'}</dd>
                  <dt>Authors</dt><dd>{detail.paper.authors ?? '—'}</dd>
                  <dt>Journal</dt><dd>{detail.paper.journal ?? '—'}</dd>
                  <dt>Year</dt><dd>{detail.paper.publication_year ?? '—'}</dd>
                  <dt>PMID / DOI</dt><dd>{detail.paper.pmid ?? '—'} / {detail.paper.doi ?? '—'}</dd>
                </dl>
              </section>

              <section className="paper-detail-section">
                <h4>Abstract</h4>
                {detail.paper.abstract || sections.find(s => s.title === 'Abstract')
                  ? <p className="paper-detail-abstract">
                      {detail.paper.abstract
                        ?? sections.find(s => s.title === 'Abstract')?.paragraphs.map(p => p.text).join(' ')}
                    </p>
                  : <p className="evidence-module-hint">摘要待入库(可用「添加论文」重新抓取)。</p>}
              </section>

              <section className="paper-detail-section">
                <h4>Full Text</h4>
                {sections.filter(s => s.title !== 'Abstract').length === 0 ? (
                  <p className="evidence-module-hint" data-testid="paper-fulltext-empty">
                    {detail.paper.abstract_available ? '摘要可用 · 等待全文解析' : '等待全文解析'}
                  </p>
                ) : (
                  sections.filter(s => s.title !== 'Abstract').map(s => (
                    <details key={s.title} className="paper-detail-section-block">
                      <summary>{s.title}({s.paragraphs.length})</summary>
                      {s.paragraphs.map(p => <p key={p.index} className="paper-detail-para">{p.text}</p>)}
                    </details>
                  ))
                )}
              </section>

              <section className="paper-detail-section">
                <h4>Evidence Preview</h4>
                <div className="paper-detail-evidence-count">
                  Evidence Candidates: <b>{detail.evidence_count}</b> · Reviews: <b>{detail.paper.review_count ?? 0}</b>
                </div>
                {detail.targets.length === 0 ? (
                  <p className="evidence-module-hint">该论文暂无关联证据候选。</p>
                ) : (
                  <div className="paper-detail-targets">
                    {detail.targets.slice(0, 12).map((t, i) => (
                      <div key={`${t.target_type}-${t.target_id}-${i}`} className="paper-detail-target-row">
                        <span className="govw-chip">{t.target_type}</span>
                        <span className="paper-detail-target-id">{t.target_id.slice(0, 12)}…</span>
                        <button type="button" className="btn btn-xs"
                          data-testid={`paper-target-open-${i}`}
                          onClick={() => openTarget(t.target_type, t.target_id, 'candidates')}>
                          进入证据候选
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </main>

        {/* ─── 右栏:论文资产关系面板 ─── */}
        <aside className="paper-relation-panel paper-library-right" data-testid="paper-library-right">
          <div className="paper-relation-card">
            <h4>论文统计</h4>
            {relationStats ? (
              <div className="paper-relation-stats">
                <div className="paper-relation-stat"><b>{relationStats.evidence}</b><span>Evidence</span></div>
                <div className="paper-relation-stat"><b>{relationStats.connections}</b><span>Connections</span></div>
                <div className="paper-relation-stat"><b>{relationStats.circuits}</b><span>Circuits</span></div>
                <div className="paper-relation-stat"><b>{relationStats.reviews}</b><span>Reviews</span></div>
              </div>
            ) : (
              <p className="evidence-module-hint">选择论文后显示统计。</p>
            )}
          </div>
          <div className="paper-relation-card">
            <h4>Knowledge Graph Links</h4>
            {detail && relationStats && relationStats.targets.length > 0 ? (
              <div className="paper-relation-links">
                {['region', 'connection', 'circuit'].map(type => {
                  const items = relationStats.targets.filter(t => t.target_type === type)
                  if (items.length === 0) return null
                  return (
                    <div key={type} className="paper-relation-group">
                      <div className="paper-relation-group-label">{type} ({items.length})</div>
                      {items.slice(0, 5).map((t, i) => (
                        <div key={`${type}-${t.target_id}-${i}`} className="paper-relation-link">
                          <span className="paper-relation-link-id">{t.target_id.slice(0, 10)}…</span>
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="evidence-module-hint">暂无关联对象(Region / Connection / Circuit)。</p>
            )}
          </div>
        </aside>
      </div>

      {message && <div className="ontology-page-message">{message}</div>}

      {/* 添加论文弹窗 */}
      <ConfirmOrDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="添加论文"
        busy={addBusy}
        onConfirm={() => void handleAdd()}
        confirmDisabled={!addPmid.trim() && !addDoi.trim() && !addUrl.trim()}
        confirmLabel={addBusy ? '抓取中…' : '添加'}
      >
        <div className="paper-add-form">
          <input className="form-input" placeholder="PMID" value={addPmid}
            onChange={e => setAddPmid(e.target.value)} aria-label="PMID" />
          <input className="form-input" placeholder="DOI(如 10.xxx/xxx)" value={addDoi}
            onChange={e => setAddDoi(e.target.value)} aria-label="DOI" />
          <input className="form-input" placeholder="URL(自动提取 DOI)" value={addUrl}
            onChange={e => setAddUrl(e.target.value)} aria-label="URL" />
          <p className="evidence-module-hint">提交后自动获取 title/authors/journal/year/abstract 并保存;PMID/DOI 已存在时禁止重复创建。</p>
          {addMsg && <div className="ontology-page-message" data-testid="paper-add-msg">{addMsg}</div>}
        </div>
      </ConfirmOrDialog>

      {/* 软删除确认 */}
      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除论文"
        message={deleteTarget
          ? `确认删除「${deleteTarget.title ?? '无标题'}」？删除为软删除,历史证据/引用全部保留。`
          : undefined}
        confirmLabel="删除"
        danger
        loading={deleteBusy}
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}

/** 添加论文弹窗(非 ConfirmDialog 语义的轻量表单壳:自由内容 + 确认) */
function ConfirmOrDialog({ open, onClose, title, busy, confirmDisabled, confirmLabel, onConfirm, children }: {
  open: boolean
  onClose: () => void
  title: string
  busy: boolean
  confirmDisabled?: boolean
  confirmLabel: string
  onConfirm: () => void
  children: React.ReactNode
}) {
  if (!open) return null
  return (
    <div className="evidence-drawer-overlay" onClick={onClose}>
      <div className="evidence-drawer" role="dialog" aria-label={title}
        onClick={e => e.stopPropagation()}>
        <header className="evidence-drawer-head">
          <h4 className="evidence-drawer-title">{title}</h4>
          <button type="button" className="evidence-drawer-close" aria-label="关闭" onClick={onClose}>×</button>
        </header>
        <div className="evidence-drawer-body">
          {children}
          <div className="paper-add-actions">
            <button type="button" className="btn btn-sm" onClick={onClose}>取消</button>
            <button type="button" className="btn btn-sm btn-primary" disabled={busy || confirmDisabled}
              data-testid="paper-add-confirm" onClick={onConfirm}>
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
