import { useCallback, useEffect, useState } from 'react'
import {
  activateOntologyTerm,
  batchActivateOntologyTerms,
  listOntologyTerms,
  type OntologyTerm,
} from '../../../api/endpoints'
import { DeprecateDialog, MergeDialog, SynonymDialog, TermDetailDrawer } from './TermDialogs'

export function TermsTable({ status = 'proposed', role }: { status?: 'proposed' | 'all'; role: string }) {
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
      {selected.size > 0 && role === 'ontology_admin' && (
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
                {term.status === 'proposed' && role !== 'viewer' && (
                  <button type="button" className="btn btn-xs" onClick={() => activateOntologyTerm(term.id).then(load).catch(err => setMessage(String(err)))}>激活</button>
                )}
                {term.status === 'active' && role === 'ontology_admin' && (
                  <button type="button" className="btn btn-xs" onClick={() => setDeprecateTerm(term)}>弃用</button>
                )}
                {role === 'ontology_admin' && <button type="button" className="btn btn-xs" onClick={() => setMergeSource(term)}>合并</button>}
                {role === 'ontology_admin' && <button type="button" className="btn btn-xs" onClick={() => setSynonymTerm(term)}>同义词</button>}
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
