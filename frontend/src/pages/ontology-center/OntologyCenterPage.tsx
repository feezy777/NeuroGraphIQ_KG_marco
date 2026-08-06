import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { useGlobalGranularity } from '../../hooks/useGlobalGranularity'
import {
  activateOntologyTerm,
  addOntologySynonym,
  batchAcceptExactCandidates,
  batchActivateOntologyTerms,
  deprecateOntologyTerm,
  getAlignmentStats,
  getGovernanceDashboard,
  getMergePreview,
  getTermDetail,
  getVocabularyUsage,
  listAlignmentCandidates,
  listDuplicateTerms,
  listEnumAnomalies,
  listOntologyTerms,
  listUngroundedRecords,
  manualGroundOntology,
  mergeOntologyTerm,
  proposeOntologyTerm,
  reviewAlignmentCandidate,
  runDeterministicGrounding,
  runOntologyAudit,
  skipUngroundedRecord,
  type AlignmentCandidateItem,
  type AlignmentStats,
  type GovernanceDashboard,
  type MergePreview,
  type OntologyTerm,
  type TermDetail,
  type UngroundedRecord,
  type VocabularyUsageItem,
} from '../../api/endpoints'

type TabId = 'functions' | 'regions' | 'relations'
type FunctionSubView = 'pending' | 'all' | 'ungrounded' | 'duplicates'

export function OntologyCenterPage() {
  const { granularity } = useGlobalGranularity()
  const [tab, setTab] = useState<TabId>('functions')

  return (
    <div className="data-center-page">
      <div className="data-center-header-static">
        <PageHeader title="本体中心" description="本体治理工作台 · 跟随顶部颗粒度切换" readonly />
      </div>
      <div className="ontology-page ontology-page-scroll">
        <div className="ontology-page-tabs">
          {(
            [
              ['functions', '功能'],
              ['regions', '脑区'],
              ['relations', '关系'],
            ] as Array<[TabId, string]>
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`ontology-page-tab ${tab === key ? 'ontology-page-tab-active' : ''}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
          <span className="ontology-page-granularity">当前颗粒度：{granularity}</span>
        </div>
        <GovernanceOverview granularity={granularity} onNavigate={setTab} />
        {tab === 'functions' && <FunctionsTab granularity={granularity} />}
        {tab === 'regions' && <RegionsTab granularity={granularity} />}
        {tab === 'relations' && <RelationsTab granularity={granularity} />}
      </div>
    </div>
  )
}

function GovernanceOverview({
  granularity,
  onNavigate,
}: {
  granularity: string
  onNavigate: (tab: TabId) => void
}) {
  const [data, setData] = useState<GovernanceDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [runResults, setRunResults] = useState<string[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await getGovernanceDashboard({ granularity_level: granularity }))
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [granularity])

  useEffect(() => {
    load()
  }, [load])

  const runDeterministic = useCallback(async () => {
    setBusy('deterministic')
    setRunResults([])
    const results: string[] = []
    for (const targetType of ['circuit_function', 'projection_function', 'region_function']) {
      try {
        const r = await runDeterministicGrounding({ target_type: targetType, limit: 2000 })
        results.push(`${targetType}: 扫描 ${r.processed} · 成功 ${r.grounded} · 未命中 ${r.ungrounded}`)
      } catch (err) {
        results.push(`${targetType}: 失败 ${err instanceof Error ? err.message : String(err)}`)
      }
    }
    setRunResults(results)
    setBusy(null)
    await load()
  }, [load])

  const runAudit = useCallback(async () => {
    setBusy('audit')
    setRunResults([])
    try {
      const r = await runOntologyAudit({ granularity_level: granularity })
      setRunResults([`本体审计完成（${r.status}）：未锚定 ${r.summary.term_ungrounded} · 脑区待对齐 ${r.summary.region_unaligned} · 枚举异常 ${r.summary.enum_invalid}`])
    } catch (err) {
      setRunResults([`本体审计失败：${err instanceof Error ? err.message : String(err)}`])
    }
    setBusy(null)
    await load()
  }, [granularity, load])

  const cards = [
    { key: 'rate', label: '功能术语锚定率', value: data ? `${Math.round(data.function_anchor_rate * 100)}%` : '—', sub: data ? `${data.function_grounded}/${data.function_total}` : '', tab: 'functions' as TabId },
    { key: 'proposed', label: '待审核术语', value: data?.proposed_terms ?? '—', sub: 'proposed', tab: 'functions' as TabId },
    { key: 'ungrounded', label: '未锚定记录', value: data?.ungrounded_records ?? '—', sub: '需处理', tab: 'functions' as TabId },
    { key: 'region', label: '脑区待对齐', value: data?.region_unaligned ?? '—', sub: '候选审核', tab: 'regions' as TabId },
    { key: 'enum', label: '枚举/关系异常', value: data?.enum_anomalies ?? '—', sub: '异常值', tab: 'relations' as TabId },
    { key: 'audit', label: '最近审计', value: data?.last_audit_at ? new Date(data.last_audit_at).toLocaleString() : '未运行', sub: '本体审计', tab: 'relations' as TabId },
  ]

  return (
    <div className="card ontology-overview">
      <div className="ontology-overview-header">
        <span className="ontology-card-title">本体治理总览</span>
        <div className="ontology-overview-actions">
          <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={runDeterministic}>
            {busy === 'deterministic' ? '运行中…' : '运行确定性锚定'}
          </button>
          <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={runAudit}>
            {busy === 'audit' ? '审计中…' : '运行本体审计'}
          </button>
          <button type="button" className="btn btn-sm" onClick={load}>刷新数据</button>
        </div>
      </div>
      {loading && <div className="ontology-empty">加载中…</div>}
      {!loading && (
        <div className="ontology-overview-grid">
          {cards.map(card => (
            <button key={card.key} type="button" className="ontology-stat-card" onClick={() => onNavigate(card.tab)}>
              <span className="ontology-stat-label">{card.label}</span>
              <span className="ontology-stat-value">{card.value}</span>
              <span className="ontology-stat-sub">{card.sub}</span>
            </button>
          ))}
        </div>
      )}
      {runResults.length > 0 && (
        <div className="ontology-run-results">
          {runResults.map((line, i) => (
            <div key={i} className="ontology-run-line">{line}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function FunctionsTab({ granularity }: { granularity: string }) {
  const [subView, setSubView] = useState<FunctionSubView>('pending')
  return (
    <div>
      <div className="ontology-subview-tabs">
        {(
          [
            ['pending', '待审核术语'],
            ['all', '全部术语'],
            ['ungrounded', '未锚定记录'],
            ['duplicates', '合并建议'],
          ] as Array<[FunctionSubView, string]>
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`ontology-subview-tab ${subView === key ? 'ontology-subview-tab-active' : ''}`}
            onClick={() => setSubView(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {subView === 'pending' && <PendingTermsTable />}
      {subView === 'all' && <PendingTermsTable status="all" />}
      {subView === 'ungrounded' && <UngroundedSubView granularity={granularity} />}
      {subView === 'duplicates' && <DuplicatesSubView />}
    </div>
  )
}

function PendingTermsTable({ status = 'proposed' }: { status?: 'proposed' | 'all' }) {
  const [terms, setTerms] = useState<OntologyTerm[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState<string | null>(null)
  const [detailTerm, setDetailTerm] = useState<OntologyTerm | null>(null)
  const [mergeSource, setMergeSource] = useState<OntologyTerm | null>(null)
  const [deprecateTerm, setDeprecateTerm] = useState<OntologyTerm | null>(null)
  const [synonymTerm, setSynonymTerm] = useState<OntologyTerm | null>(null)
  const pageSize = 50

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await listOntologyTerms({
        status: status === 'all' ? undefined : status,
        q: q || undefined,
        limit: pageSize,
        offset,
      })
      setTerms(resp.items)
      setTotal(resp.total)
    } catch {
      setTerms([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [status, q, offset])

  useEffect(() => {
    load()
  }, [load])

  const toggle = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    setSelected(prev => {
      if (prev.size === terms.length && terms.length > 0) return new Set()
      return new Set(terms.map(t => t.id))
    })
  }, [terms])

  const batchActivate = useCallback(async () => {
    if (selected.size === 0) return
    setMessage(null)
    try {
      const r = await batchActivateOntologyTerms({ term_ids: [...selected] })
      setMessage(`批量激活完成：成功 ${r.activated} · 跳过 ${r.skipped} · 失败 ${r.failed}`)
      setSelected(new Set())
      await load()
    } catch (err) {
      setMessage(`批量激活失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [selected, load])

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">{status === 'proposed' ? '待审核术语' : '全部术语'}</span>
        <div className="ontology-page-filters">
          <input className="filter-input" placeholder="搜索术语" value={q} onChange={e => { setQ(e.target.value); setOffset(0) }} />
          <button type="button" className="btn btn-sm" onClick={load}>刷新</button>
        </div>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      {selected.size > 0 && (
        <div className="ontology-batch-bar">
          已选 {selected.size} 条
          <button type="button" className="btn btn-sm" onClick={batchActivate}>批量激活</button>
          <button type="button" className="btn btn-sm" onClick={() => setSelected(new Set())}>取消选择</button>
        </div>
      )}
      <table className="data-table ontology-term-table">
        <thead>
          <tr>
            <th><input type="checkbox" checked={selected.size === terms.length && terms.length > 0} onChange={toggleAll} /></th>
            <th>英文名</th><th>中文名</th><th>代码</th><th>来源</th><th>状态</th><th>创建时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={8} className="ontology-empty">加载中…</td></tr>}
          {!loading && terms.length === 0 && <tr><td colSpan={8} className="ontology-empty">暂无术语</td></tr>}
          {terms.map(term => (
            <tr key={term.id} className="ontology-row-clickable" onClick={() => setDetailTerm(term)}>
              <td onClick={e => e.stopPropagation()}><input type="checkbox" checked={selected.has(term.id)} onChange={() => toggle(term.id)} /></td>
              <td>{term.canonical_term_en}</td>
              <td>{term.canonical_term_cn ?? '—'}</td>
              <td className="ontology-term-code">{term.term_code}</td>
              <td>{term.created_by}</td>
              <td><span className={`ontology-status ontology-status-${term.status}`}>{term.status}</span></td>
              <td>{new Date(term.created_at).toLocaleDateString()}</td>
              <td className="ontology-term-actions" onClick={e => e.stopPropagation()}>
                {term.status === 'proposed' && (
                  <button type="button" className="btn btn-xs" onClick={() => activateOntologyTerm(term.id).then(load).catch(err => setMessage(String(err)))}>激活</button>
                )}
                {term.status === 'active' && (
                  <button type="button" className="btn btn-xs" onClick={() => setDeprecateTerm(term)}>弃用</button>
                )}
                <button type="button" className="btn btn-xs" onClick={() => setMergeSource(term)}>合并</button>
                <button type="button" className="btn btn-xs" onClick={() => setSynonymTerm(term)}>同义词</button>
                <button type="button" className="btn btn-xs" onClick={() => setDetailTerm(term)}>详情</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="ontology-page-pager">
        <button type="button" className="btn btn-xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>上一页</button>
        <span>{offset + 1}-{Math.min(offset + pageSize, total)} / {total}</span>
        <button type="button" className="btn btn-xs" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>下一页</button>
      </div>
      {detailTerm && <TermDetailDrawer termId={detailTerm.id} onClose={() => setDetailTerm(null)} onChanged={load} />}
      {mergeSource && <MergeDialog source={mergeSource} onClose={() => setMergeSource(null)} onDone={() => { setMergeSource(null); load() }} />}
      {deprecateTerm && <DeprecateDialog term={deprecateTerm} onClose={() => setDeprecateTerm(null)} onDone={() => { setDeprecateTerm(null); load() }} />}
      {synonymTerm && <SynonymDialog term={synonymTerm} onClose={() => setSynonymTerm(null)} onDone={() => { setSynonymTerm(null); load() }} />}
    </div>
  )
}

function TermDetailDrawer({ termId, onClose, onChanged }: { termId: string; onClose: () => void; onChanged: () => void }) {
  const [detail, setDetail] = useState<TermDetail | null>(null)
  useEffect(() => {
    getTermDetail(termId).then(setDetail).catch(() => setDetail(null))
  }, [termId])
  return (
    <div className="ontology-drawer-overlay" onClick={onClose}>
      <aside className="ontology-drawer" onClick={e => e.stopPropagation()}>
        <div className="ontology-drawer-header">
          <span className="ontology-card-title">术语详情</span>
          <button type="button" className="btn btn-xs" onClick={onClose}>关闭</button>
        </div>
        {!detail && <div className="ontology-empty">加载中…</div>}
        {detail && (
          <div className="ontology-drawer-body">
            <div className="ontology-detail-row"><span>英文标准名</span><strong>{detail.term.canonical_term_en}</strong></div>
            <div className="ontology-detail-row"><span>中文标准名</span><strong>{detail.term.canonical_term_cn ?? '—'}</strong></div>
            <div className="ontology-detail-row"><span>term_code</span><code>{detail.term.term_code}</code></div>
            <div className="ontology-detail-row"><span>类型 / 状态</span><span>{detail.term.term_type} · <b>{detail.term.status}</b></span></div>
            <div className="ontology-detail-row"><span>来源</span><span>{detail.term.created_by}</span></div>
            <div className="ontology-detail-row"><span>创建/更新时间</span><span>{new Date(detail.term.created_at).toLocaleString()} / {new Date(detail.term.updated_at).toLocaleString()}</span></div>
            <section className="ontology-detail-section">
              <h4>同义词（{detail.synonyms.length}）</h4>
              <ul>{detail.synonyms.map(s => <li key={s.id}>{s.synonym_text} <span className="ontology-term-meta">({s.lang}/{s.match_type})</span></li>)}</ul>
            </section>
            <section className="ontology-detail-section">
              <h4>外部映射（{detail.external_mappings.length}）</h4>
              <ul>{detail.external_mappings.map(m => <li key={m.id}>{m.external_system}: <a href={m.external_iri} target="_blank" rel="noreferrer">{m.external_iri}</a></li>)}</ul>
            </section>
            <section className="ontology-detail-section">
              <h4>业务引用（{detail.references.total}）</h4>
              <table className="data-table ontology-term-table">
                <thead><tr><th>类型</th><th>术语</th><th>颗粒度</th></tr></thead>
                <tbody>
                  {detail.references.items.map(ref => (
                    <tr key={`${ref.target_type}-${ref.target_id}`}>
                      <td>{ref.target_type}</td><td>{ref.function_term}</td><td>{ref.granularity_level}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="ontology-detail-section">
              <h4>变更记录（{detail.change_logs.length}）</h4>
              <ul>{detail.change_logs.map(log => <li key={log.id}>{log.action_type} · {log.operator_id ?? 'system'} · {new Date(log.created_at).toLocaleString()}</li>)}</ul>
            </section>
          </div>
        )}
      </aside>
    </div>
  )
}

function MergeDialog({ source, onClose, onDone }: { source: OntologyTerm; onClose: () => void; onDone: () => void }) {
  const [q, setQ] = useState('')
  const [targets, setTargets] = useState<OntologyTerm[]>([])
  const [targetId, setTargetId] = useState('')
  const [preview, setPreview] = useState<MergePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const search = useCallback(async () => {
    if (!q.trim()) return
    try {
      const resp = await listOntologyTerms({ q: q.trim(), status: 'active', limit: 10 })
      setTargets(resp.items.filter(t => t.id !== source.id))
    } catch {
      setTargets([])
    }
  }, [q, source.id])

  const loadPreview = useCallback(async (id: string) => {
    setBusy(true)
    try {
      setPreview(await getMergePreview(source.id, id))
    } catch (err) {
      setMessage(`预览失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [source.id])

  const doMerge = useCallback(async () => {
    if (!targetId) return
    setBusy(true)
    try {
      await mergeOntologyTerm(source.id, targetId)
      setMessage('合并完成')
      onDone()
    } catch (err) {
      setMessage(`合并失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [source.id, targetId, onDone])

  return (
    <Modal title={`合并术语：${source.canonical_term_en}`} onClose={onClose} busy={busy}>
      {message && <div className="ontology-page-message">{message}</div>}
      <div className="ontology-form-row">
        <input className="filter-input" placeholder="搜索目标 active 术语" value={q} onChange={e => setQ(e.target.value)} />
        <button type="button" className="btn btn-sm" onClick={search}>搜索</button>
      </div>
      <select className="filter-select ontology-form-select" value={targetId} onChange={e => { setTargetId(e.target.value); loadPreview(e.target.value) }}>
        <option value="">选择目标术语</option>
        {targets.map(t => <option key={t.id} value={t.id}>{t.canonical_term_en}（{t.term_code}）</option>)}
      </select>
      {preview && (
        <div className="ontology-preview">
          <div className="ontology-preview-title">影响预览</div>
          <div>同义词迁移：{preview.synonyms_to_move}（冲突 {preview.synonym_conflicts}）</div>
          <div>外部映射迁移：{preview.external_mappings_to_move}（冲突 {preview.external_mapping_conflicts}）</div>
          <div>grounding 更新：{preview.groundings_to_update}</div>
          <div>业务表更新：回路功能 {preview.business_rows_to_update.circuit_function ?? 0} · 投影功能 {preview.business_rows_to_update.projection_function ?? 0} · 区域功能 {preview.business_rows_to_update.region_function ?? 0}</div>
          <div>源术语合并后状态：{preview.source_status_after}</div>
        </div>
      )}
      <div className="ontology-modal-actions">
        <button type="button" className="btn btn-sm" disabled={!targetId || busy} onClick={doMerge}>确认合并</button>
        <button type="button" className="btn btn-sm" onClick={onClose}>取消</button>
      </div>
    </Modal>
  )
}

function DeprecateDialog({ term, onClose, onDone }: { term: OntologyTerm; onClose: () => void; onDone: () => void }) {
  const [mode, setMode] = useState<'migrate' | 'keep'>('migrate')
  const [q, setQ] = useState('')
  const [targets, setTargets] = useState<OntologyTerm[]>([])
  const [targetId, setTargetId] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const search = useCallback(async () => {
    if (!q.trim()) return
    const resp = await listOntologyTerms({ q: q.trim(), status: 'active', limit: 10 })
    setTargets(resp.items.filter(t => t.id !== term.id))
  }, [q, term.id])

  const submit = useCallback(async () => {
    setBusy(true)
    try {
      if (mode === 'migrate') {
        if (!targetId) throw new Error('请选择替代术语')
        await mergeOntologyTerm(term.id, targetId)
      } else {
        await deprecateOntologyTerm(term.id)
      }
      setMessage('操作完成')
      onDone()
    } catch (err) {
      setMessage(`操作失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [mode, targetId, term.id, onDone])

  return (
    <Modal title={`弃用术语：${term.canonical_term_en}`} onClose={onClose} busy={busy}>
      {message && <div className="ontology-page-message">{message}</div>}
      <div className="ontology-form-row">
        <label><input type="radio" checked={mode === 'migrate'} onChange={() => setMode('migrate')} /> 迁移到替代术语</label>
        <label><input type="radio" checked={mode === 'keep'} onChange={() => setMode('keep')} /> 仅禁止新增引用，保留历史引用</label>
      </div>
      {mode === 'migrate' && (
        <div className="ontology-form-row">
          <input className="filter-input" placeholder="搜索替代 active 术语" value={q} onChange={e => setQ(e.target.value)} />
          <button type="button" className="btn btn-sm" onClick={search}>搜索</button>
          <select className="filter-select ontology-form-select" value={targetId} onChange={e => setTargetId(e.target.value)}>
            <option value="">选择替代术语</option>
            {targets.map(t => <option key={t.id} value={t.id}>{t.canonical_term_en}</option>)}
          </select>
        </div>
      )}
      <div className="ontology-modal-actions">
        <button type="button" className="btn btn-sm" disabled={busy} onClick={submit}>确认</button>
        <button type="button" className="btn btn-sm" onClick={onClose}>取消</button>
      </div>
    </Modal>
  )
}

function SynonymDialog({ term, onClose, onDone }: { term: OntologyTerm; onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  return (
    <Modal title={`添加同义词：${term.canonical_term_en}`} onClose={onClose} busy={busy}>
      {message && <div className="ontology-page-message">{message}</div>}
      <input className="filter-input ontology-form-select" placeholder="同义词文本" value={text} onChange={e => setText(e.target.value)} />
      <div className="ontology-modal-actions">
        <button
          type="button"
          className="btn btn-sm"
          disabled={!text.trim() || busy}
          onClick={async () => {
            setBusy(true)
            try {
              await addOntologySynonym(term.id, { synonym_text: text.trim() })
              onDone()
            } catch (err) {
              setMessage(`添加失败：${err instanceof Error ? err.message : String(err)}`)
            } finally {
              setBusy(false)
            }
          }}
        >
          添加
        </button>
        <button type="button" className="btn btn-sm" onClick={onClose}>取消</button>
      </div>
    </Modal>
  )
}

function Modal({ title, children, onClose, busy }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  return (
    <div className="ontology-modal-overlay" onClick={onClose}>
      <div className="ontology-modal" onClick={e => e.stopPropagation()}>
        <div className="ontology-modal-header">
          <span className="ontology-card-title">{title}</span>
          <button type="button" className="btn btn-xs" onClick={onClose}>关闭</button>
        </div>
        <div className="ontology-modal-body">{children}</div>
        {busy && <div className="ontology-empty">处理中…</div>}
      </div>
    </div>
  )
}

function UngroundedSubView({ granularity }: { granularity: string }) {
  const [records, setRecords] = useState<UngroundedRecord[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<string | null>(null)
  const [anchor, setAnchor] = useState<{ record: UngroundedRecord; termId: string } | null>(null)
  const [skipRecord, setSkipRecord] = useState<UngroundedRecord | null>(null)
  const pageSize = 20

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await listUngroundedRecords({ granularity_level: granularity, limit: pageSize, offset })
      setRecords(resp.items)
      setTotal(resp.total)
    } catch {
      setRecords([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [granularity, offset])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">未锚定记录</span>
        <button type="button" className="btn btn-sm" onClick={load}>刷新</button>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      <table className="data-table ontology-term-table">
        <thead>
          <tr><th>原始术语</th><th>类型</th><th>颗粒度</th><th>原因</th><th>推荐候选</th><th>操作</th></tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={6} className="ontology-empty">加载中…</td></tr>}
          {!loading && records.length === 0 && <tr><td colSpan={6} className="ontology-empty">没有未锚定记录</td></tr>}
          {records.map(r => (
            <tr key={`${r.target_type}-${r.target_id}`}>
              <td>{r.function_term}</td>
              <td>{r.target_type}</td>
              <td>{r.granularity_level}</td>
              <td>{r.reason}</td>
              <td>
                {r.recommendations.length > 0
                  ? r.recommendations.map(rec => (
                      <span key={rec.term_id} className="ontology-recommend">
                        {rec.canonical_term_en}（{Math.round(rec.confidence * 100)}%）
                        <button type="button" className="btn btn-xs" onClick={() => setAnchor({ record: r, termId: rec.term_id })}>锚定</button>
                      </span>
                    ))
                  : '—'}
              </td>
              <td className="ontology-term-actions">
                <button type="button" className="btn btn-xs" onClick={() => setAnchor({ record: r, termId: '' })}>人工锚定</button>
                <button
                  type="button"
                  className="btn btn-xs"
                  onClick={() => setSkipRecord(r)}
                >
                  暂不处理
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="ontology-page-pager">
        <button type="button" className="btn btn-xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>上一页</button>
        <span>{offset + 1}-{Math.min(offset + pageSize, total)} / {total}</span>
        <button type="button" className="btn btn-xs" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>下一页</button>
      </div>
      {anchor && <AnchorDialog record={anchor.record} initialTermId={anchor.termId} onClose={() => setAnchor(null)} onDone={() => { setAnchor(null); load() }} />}
      {skipRecord && <SkipDialog record={skipRecord} onClose={() => setSkipRecord(null)} onDone={() => { setSkipRecord(null); load() }} />}
    </div>
  )
}

function SkipDialog({ record, onClose, onDone }: { record: UngroundedRecord; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  return (
    <Modal title={`标记暂不处理：${record.function_term}`} onClose={onClose} busy={busy}>
      {message && <div className="ontology-page-message">{message}</div>}
      <input
        className="filter-input ontology-form-select"
        placeholder="暂不处理原因"
        value={reason}
        onChange={e => setReason(e.target.value)}
      />
      <div className="ontology-modal-actions">
        <button
          type="button"
          className="btn btn-sm"
          disabled={!reason.trim() || busy}
          onClick={async () => {
            setBusy(true)
            try {
              await skipUngroundedRecord({
                target_type: record.target_type,
                target_id: record.target_id,
                reason: reason.trim(),
              })
              onDone()
            } catch (err) {
              setMessage(`失败：${err instanceof Error ? err.message : String(err)}`)
            } finally {
              setBusy(false)
            }
          }}
        >
          确认
        </button>
        <button type="button" className="btn btn-sm" onClick={onClose}>取消</button>
      </div>
    </Modal>
  )
}

function AnchorDialog({ record, initialTermId, onClose, onDone }: { record: UngroundedRecord; initialTermId: string; onClose: () => void; onDone: () => void }) {
  const [termId, setTermId] = useState(initialTermId)
  const [q, setQ] = useState('')
  const [terms, setTerms] = useState<OntologyTerm[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const search = useCallback(async () => {
    if (!q.trim()) return
    const resp = await listOntologyTerms({ q: q.trim(), limit: 10 })
    setTerms(resp.items)
  }, [q])

  const submit = useCallback(async (createProposed: boolean) => {
    setBusy(true)
    try {
      let tid = termId
      if (createProposed) {
        const created = await listOntologyTerms({ q: record.function_term, limit: 5 })
        let found = created.items.find(t => t.canonical_term_en.toLowerCase() === record.function_term.toLowerCase())
        if (!found) {
          found = await proposeOntologyTerm({
            canonical_term_en: record.function_term,
            created_by: 'manual',
          })
        }
        tid = found.id
      }
      if (!tid) throw new Error('请选择术语')
      await manualGroundOntology({ target_type: record.target_type, target_id: record.target_id, term_id: tid })
      onDone()
    } catch (err) {
      setMessage(`失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [termId, record, onDone])

  return (
    <Modal title={`人工锚定：${record.function_term}`} onClose={onClose} busy={busy}>
      {message && <div className="ontology-page-message">{message}</div>}
      <div className="ontology-form-row">
        <input className="filter-input" placeholder="搜索 active 术语" value={q} onChange={e => setQ(e.target.value)} />
        <button type="button" className="btn btn-sm" onClick={search}>搜索</button>
      </div>
      <select className="filter-select ontology-form-select" value={termId} onChange={e => setTermId(e.target.value)}>
        <option value="">选择术语</option>
        {terms.map(t => <option key={t.id} value={t.id}>{t.canonical_term_en}（{t.status}）</option>)}
      </select>
      <div className="ontology-modal-actions">
        <button type="button" className="btn btn-sm" disabled={!termId || busy} onClick={() => submit(false)}>锚定</button>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => submit(true)}>创建 proposed 并锚定</button>
        <button type="button" className="btn btn-sm" onClick={onClose}>取消</button>
      </div>
    </Modal>
  )
}

function DuplicatesSubView() {
  const [groups, setGroups] = useState<Array<{ basis: string; term_ids: string[] }>>([])
  const [total, setTotal] = useState(0)
  useEffect(() => {
    listDuplicateTerms({ limit: 50 }).then(r => { setGroups(r.items); setTotal(r.total) }).catch(() => undefined)
  }, [])
  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">合并建议（疑似重复）</span>
        <span className="ontology-card-sub">共 {total} 组</span>
      </div>
      <table className="data-table ontology-term-table">
        <thead><tr><th>依据</th><th>术语 ID</th></tr></thead>
        <tbody>
          {groups.map((g, i) => (
            <tr key={i}><td>{g.basis}</td><td>{g.term_ids.join(', ')}</td></tr>
          ))}
          {groups.length === 0 && <tr><td colSpan={2} className="ontology-empty">暂无疑似重复</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

function RegionsTab({ granularity }: { granularity: string }) {
  const [status, setStatus] = useState('pending')
  const [stats, setStats] = useState<AlignmentStats | null>(null)
  const [items, setItems] = useState<AlignmentCandidateItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<string | null>(null)
  const pageSize = 30

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, l] = await Promise.all([
        getAlignmentStats({ granularity_level: granularity }),
        listAlignmentCandidates({ status, granularity_level: granularity, limit: pageSize, offset }),
      ])
      setStats(s)
      setItems(l.items)
      setTotal(l.total)
    } catch {
      setStats(null)
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [granularity, status, offset])

  useEffect(() => {
    load()
  }, [load])

  const review = useCallback(async (candidateId: string, action: 'accept' | 'reject') => {
    setMessage(null)
    try {
      await reviewAlignmentCandidate(candidateId, { action })
      setMessage(action === 'accept' ? '已接受候选' : '已拒绝候选')
      await load()
    } catch (err) {
      setMessage(`操作失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [load])

  const batchAccept = useCallback(async () => {
    setMessage(null)
    try {
      const r = await batchAcceptExactCandidates()
      setMessage(`已批量接受 ${r.accepted} 个 exact 候选`)
      await load()
    } catch (err) {
      setMessage(`操作失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [load])

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">脑区外部标识对齐</span>
        <span className="ontology-card-sub">
          {stats ? `总数 ${stats.total} · 待确认 ${stats.by_status.pending ?? 0} · 已接受 ${stats.by_status.accepted ?? 0} · 已拒绝 ${stats.by_status.rejected ?? 0} · exact ${stats.by_match_type.exact ?? 0} / close ${stats.by_match_type.close ?? 0} / weak ${stats.by_match_type.weak ?? 0} / not_found ${stats.by_match_type.not_found ?? 0}` : ''}
        </span>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      <div className="ontology-subview-tabs">
        {(['pending', 'accepted', 'rejected'] as const).map(key => (
          <button key={key} type="button" className={`ontology-subview-tab ${status === key ? 'ontology-subview-tab-active' : ''}`} onClick={() => { setStatus(key); setOffset(0) }}>
            {key === 'pending' ? '待确认' : key === 'accepted' ? '已对齐' : '已拒绝'}
          </button>
        ))}
        <button type="button" className="btn btn-sm" onClick={batchAccept}>批量接受 exact</button>
        <button type="button" className="btn btn-sm" onClick={load}>刷新</button>
      </div>
      <table className="data-table ontology-term-table">
        <thead>
          <tr><th>脑区</th><th>图谱</th><th>候选标签</th><th>IRI</th><th>匹配</th><th>得分</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={8} className="ontology-empty">加载中…</td></tr>}
          {!loading && items.length === 0 && <tr><td colSpan={8} className="ontology-empty">当前无候选</td></tr>}
          {items.map(c => (
            <tr key={c.candidate_id}>
              <td>{c.en_name}{c.cn_name ? <span className="ontology-term-meta">（{c.cn_name}）</span> : null}</td>
              <td>{c.source_atlas}</td>
              <td>{c.external_label ?? '—'}</td>
              <td><a href={c.external_iri} target="_blank" rel="noreferrer">{c.external_iri}</a></td>
              <td>{c.match_type}</td>
              <td>{c.match_score != null ? Math.round(c.match_score * 100) : '—'}%</td>
              <td><span className={`ontology-status ontology-status-${c.status}`}>{c.status}</span></td>
              <td className="ontology-term-actions">
                {c.status === 'pending' && (
                  <>
                    <button type="button" className="btn btn-xs" onClick={() => review(c.candidate_id, 'accept')}>接受</button>
                    <button type="button" className="btn btn-xs" onClick={() => review(c.candidate_id, 'reject')}>拒绝</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="ontology-page-pager">
        <button type="button" className="btn btn-xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>上一页</button>
        <span>{offset + 1}-{Math.min(offset + pageSize, total)} / {total}</span>
        <button type="button" className="btn btn-xs" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>下一页</button>
      </div>
    </div>
  )
}

function RelationsTab({ granularity }: { granularity: string }) {
  const [subView, setSubView] = useState<'registry' | 'anomalies' | 'constraints'>('registry')
  const [usage, setUsage] = useState<VocabularyUsageItem[]>([])
  const [field, setField] = useState('category')
  const [anomalies, setAnomalies] = useState<Array<{ target_type: string; target_id: string; field: string; value: string; granularity_level: string | null }>>([])
  const [anomalyTotal, setAnomalyTotal] = useState(0)
  const [message, setMessage] = useState<string | null>(null)

  const loadUsage = useCallback(async () => {
    const resp = await getVocabularyUsage()
    setUsage(resp.items)
  }, [])
  const loadAnomalies = useCallback(async () => {
    const resp = await listEnumAnomalies({ field, granularity_level: granularity, limit: 50 })
    setAnomalies(resp.items)
    setAnomalyTotal(resp.total)
  }, [field, granularity])

  useEffect(() => {
    if (subView === 'registry') loadUsage()
    if (subView === 'anomalies') loadAnomalies()
  }, [subView, loadUsage, loadAnomalies])

  const grouped = useMemo(() => {
    const map = new Map<string, VocabularyUsageItem[]>()
    for (const item of usage) {
      const list = map.get(item.vocab_type) ?? []
      list.push(item)
      map.set(item.vocab_type, list)
    }
    return [...map.entries()]
  }, [usage])

  const domainLabels: Record<string, string> = {
    connection_type: '连接类型与方向',
    directionality: '连接方向',
    circuit_type: '回路类型',
    circuit_region_role: '回路角色',
    step_type: '步骤类型',
    step_role: '步骤角色',
    projection_role: '投影角色',
    triple_subject_type: '三元组 subject 类型',
    triple_object_type: '三元组 object 类型',
    triple_scope: '三元组范围',
    category: '功能分类',
    relation_type: '功能关系',
    predicate: '谓词',
  }

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">关系与枚举</span>
        <span className="ontology-card-sub">共 {usage.length} 条词汇</span>
      </div>
      <div className="ontology-subview-tabs">
        {(
          [
            ['registry', '注册表'],
            ['anomalies', '异常值'],
            ['constraints', '约束说明'],
          ] as Array<['registry' | 'anomalies' | 'constraints', string]>
        ).map(([key, label]) => (
          <button key={key} type="button" className={`ontology-subview-tab ${subView === key ? 'ontology-subview-tab-active' : ''}`} onClick={() => setSubView(key)}>{label}</button>
        ))}
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      {subView === 'registry' && grouped.map(([type, items]) => (
        <details key={type} className="ontology-vocab-group" open>
          <summary>{domainLabels[type] ?? type}（{items.length}）</summary>
          <table className="data-table ontology-term-table">
            <thead><tr><th>code</th><th>中文</th><th>英文</th><th>状态</th><th>使用量</th><th>排序</th></tr></thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id}>
                  <td className="ontology-term-code">{item.code}</td>
                  <td>{item.label_cn ?? '—'}</td>
                  <td>{item.label_en ?? '—'}</td>
                  <td>{item.status}</td>
                  <td>{item.usage_count}</td>
                  <td>{item.seq}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
      {subView === 'anomalies' && (
        <div>
          <div className="ontology-form-row">
            <select className="filter-select" value={field} onChange={e => setField(e.target.value)}>
              {Object.keys(domainLabels).map(f => <option key={f} value={f}>{domainLabels[f]}</option>)}
            </select>
            <button type="button" className="btn btn-sm" onClick={loadAnomalies}>查询（{anomalyTotal}）</button>
          </div>
          <table className="data-table ontology-term-table">
            <thead><tr><th>类型</th><th>ID</th><th>字段</th><th>异常值</th><th>颗粒度</th></tr></thead>
            <tbody>
              {anomalies.map(a => (
                <tr key={`${a.target_type}-${a.target_id}`}>
                  <td>{a.target_type}</td><td>{a.target_id}</td><td>{a.field}</td><td className="ontology-anomaly-value">{a.value}</td><td>{a.granularity_level ?? '—'}</td>
                </tr>
              ))}
              {anomalies.length === 0 && <tr><td colSpan={5} className="ontology-empty">没有异常值</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {subView === 'constraints' && (
        <div className="ontology-constraints">
          {Object.entries(domainLabels).map(([type, label]) => (
            <div key={type} className="ontology-constraint-item">
              <strong>{label}</strong>
              <span>允许值见注册表；非法值由校验规则 ONT_ENUM_INVALID / ONT_PREDICATE_UNKNOWN 拦截（blocker），可在“异常值”视图批量替换为合法 code。</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
