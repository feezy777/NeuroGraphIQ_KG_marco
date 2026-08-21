import { useCallback, useEffect, useState } from 'react'
import {
  addOntologySynonym,
  deprecateOntologyTerm,
  getMergePreview,
  getTermDetail,
  listOntologyTerms,
  mergeOntologyTerm,
  type MergePreview,
  type OntologyTerm,
  type TermDetail,
} from '../../../api/endpoints'
import { Modal } from './GovernanceModal'

export function TermDetailDrawer({ termId, onClose, onChanged }: { termId: string; onClose: () => void; onChanged: () => void }) {
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

export function MergeDialog({ source, onClose, onDone }: { source: OntologyTerm; onClose: () => void; onDone: () => void }) {
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

export function DeprecateDialog({ term, onClose, onDone }: { term: OntologyTerm; onClose: () => void; onDone: () => void }) {
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

export function SynonymDialog({ term, onClose, onDone }: { term: OntologyTerm; onClose: () => void; onDone: () => void }) {
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
