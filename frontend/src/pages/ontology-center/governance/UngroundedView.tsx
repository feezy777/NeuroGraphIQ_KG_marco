import { useCallback, useEffect, useState } from 'react'
import {
  listOntologyTerms,
  listUngroundedRecords,
  manualGroundOntology,
  proposeOntologyTerm,
  skipUngroundedRecord,
  type OntologyTerm,
  type UngroundedRecord,
} from '../../../api/endpoints'
import { Modal } from './GovernanceModal'

export function UngroundedView({ granularity, role }: { granularity: string; role: string }) {
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
                {role !== 'viewer' && <button type="button" className="btn btn-xs" onClick={() => setAnchor({ record: r, termId: '' })}>人工锚定</button>}
                {role !== 'viewer' && (
                  <button type="button" className="btn btn-xs" onClick={() => setSkipRecord(r)}>
                    暂不处理
                  </button>
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
