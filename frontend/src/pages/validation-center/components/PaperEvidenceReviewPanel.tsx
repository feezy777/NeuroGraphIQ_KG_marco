import { useCallback, useEffect, useState } from 'react'
import {
  listEvidenceReviewQueue,
  listPaperEvidence,
  listConfidenceAdjustments,
  resolveEvidenceReviewRecord,
  rollbackPaperEvidence,
  type EvidenceReviewQueueItem,
  type PaperEvidenceItem,
  type ConfidenceAdjustmentItem,
} from '../../../api/endpoints'
import { ConfirmDialog } from '../../../components/ConfirmDialog'
import { DIRECTION_LABEL } from '../../evidence-center/components/types'

const PAGE_SIZE = 20

function fmt(v: number | null | undefined): string {
  return v == null ? '—' : String(v)
}

export function PaperEvidenceReviewPanel() {
  const [items, setItems] = useState<EvidenceReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<EvidenceReviewQueueItem | null>(null)
  const [evidences, setEvidences] = useState<PaperEvidenceItem[]>([])
  const [adjustments, setAdjustments] = useState<ConfidenceAdjustmentItem[]>([])
  const [rollbackTarget, setRollbackTarget] = useState<PaperEvidenceItem | null>(null)
  const [rollbackReason, setRollbackReason] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = useCallback(async (nextOffset: number) => {
    setLoading(true)
    setError(null)
    try {
      const r = await listEvidenceReviewQueue({ status: 'pending', limit: PAGE_SIZE, offset: nextOffset })
      setItems(nextOffset === 0 ? r.items : prev => [...prev, ...r.items])
      setTotal(r.total)
      setOffset(nextOffset)
    } catch (err) {
      setError(`加载失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load(0) }, [load])

  const openDetail = useCallback(async (item: EvidenceReviewQueueItem) => {
    setDetail(item)
    setMessage(null)
    setEvidences([])
    setAdjustments([])
    try {
      const [ev, adj] = await Promise.all([
        listPaperEvidence({ target_type: item.target_type, target_id: item.target_id, limit: 50 }),
        listConfidenceAdjustments({ target_type: item.target_type, target_id: item.target_id }),
      ])
      setEvidences(ev.items)
      setAdjustments(adj.items)
    } catch (err) {
      setMessage(`详情加载失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [])

  const resolve = useCallback(async () => {
    if (!detail) return
    setBusy(true)
    try {
      await resolveEvidenceReviewRecord(detail.id, note || '人工复核通过')
      setDetail(null)
      setNote('')
      await load(0)
    } catch (err) {
      setMessage(`复核失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [detail, note, load])

  const rollback = useCallback(async () => {
    if (!rollbackTarget) return
    setBusy(true)
    try {
      await rollbackPaperEvidence(rollbackTarget.evidence_id, rollbackReason || '验证中心人工撤销')
      setRollbackTarget(null)
      setRollbackReason('')
      setMessage('证据已撤销并回滚置信度')
      if (detail) await openDetail(detail)
    } catch (err) {
      setMessage(`撤销失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [rollbackTarget, rollbackReason, detail, openDetail])

  const matchedEvidence = detail ? evidences.filter(e => e.evidence_id === detail.evidence_id) : []

  return (
    <div className="pev-panel">
      <div className="ontology-card-header">
        <span className="ontology-card-title">论文证据复核</span>
        <span className="ontology-card-sub">EV_PAPER_EVIDENCE_* 规则 · 待处理 {total}</span>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      {error && <div className="ontology-page-message">{error}</div>}
      {items.length === 0 && !loading && <div className="ontology-empty">暂无待复核的论文证据记录</div>}
      <div className="pev-list">
        {items.map(it => (
          <div key={it.id} className="pev-item" onClick={() => openDetail(it)}>
            <div className="pev-item-main">
              <strong>{String(it.paper_snapshot?.title ?? '未命名论文')}</strong>
              <div className="ew-meta">
                {it.rule_code} · {it.target_type} · {it.direction ?? '—'} · PMID {String(it.paper_snapshot?.pmid ?? '—')}
              </div>
            </div>
            <span className="ew-meta">{it.created_at ? new Date(it.created_at).toLocaleString() : '—'}</span>
          </div>
        ))}
      </div>
      {items.length < total && (
        <button type="button" className="btn btn-sm" disabled={loading} onClick={() => load(offset + PAGE_SIZE)}>
          {loading ? '加载中…' : `加载更多（${items.length}/${total}）`}
        </button>
      )}

      {detail && (
        <div className="ontology-drawer-overlay" onClick={() => setDetail(null)}>
          <aside className="ontology-drawer" style={{ width: 'min(640px, 94vw)' }} onClick={e => e.stopPropagation()}>
            <div className="ontology-drawer-header">
              <span className="ontology-card-title">论文证据复核详情</span>
              <button type="button" className="btn btn-xs" onClick={() => setDetail(null)}>关闭</button>
            </div>
            <div className="ontology-drawer-body">
              <div className="ontology-detail-row"><span>规则</span><strong>{detail.rule_code}</strong></div>
              <div className="ontology-detail-row"><span>原对象</span><span>{detail.target_type} · {detail.target_id}</span></div>
              <div className="ontology-detail-row"><span>人工方向</span><span>{detail.direction ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>论文</span><strong>{String(detail.paper_snapshot?.title ?? '—')}</strong></div>
              <div className="ontology-detail-row"><span>PMID / DOI</span>
                <span>
                  {detail.paper_snapshot?.pmid ? <a href={`https://pubmed.ncbi.nlm.nih.gov/${String(detail.paper_snapshot.pmid)}/`} target="_blank" rel="noreferrer">PubMed {String(detail.paper_snapshot.pmid)}</a> : '—'}
                  {' '}
                  {detail.paper_snapshot?.doi ? <a href={`https://doi.org/${String(detail.paper_snapshot.doi)}`} target="_blank" rel="noreferrer">DOI</a> : ''}
                </span>
              </div>
              <section className="ontology-detail-section">
                <h4>原文片段（{matchedEvidence.length > 0 ? (matchedEvidence[0].passage_count ?? 0) : 0}）</h4>
                {matchedEvidence.length === 0 && <div className="ontology-empty">未找到对应证据记录</div>}
                {matchedEvidence.flatMap(ev => (ev.passages ?? []).filter(p => p.is_selected).map(p => (
                  <div key={p.id} className="ew-passage">
                    <span className="ew-meta">{p.source_scope}{p.section_title ? ` · ${p.section_title}` : ''}{p.paragraph_index != null ? ` · ¶${p.paragraph_index}` : ''} · {DIRECTION_LABEL[p.direction as keyof typeof DIRECTION_LABEL] ?? p.direction} · {fmt(p.confidence)}</span>
                    <p className="ew-passage-en">{p.passage}</p>
                    {p.translation_zh && <p className="ew-passage-zh">{p.translation_zh}</p>}
                    {p.reason && <p className="ew-meta">理由：{p.reason}</p>}
                  </div>
                )))}
              </section>
              <section className="ontology-detail-section">
                <h4>置信度调整历史（{adjustments.length}）</h4>
                {adjustments.length === 0 && <div className="ontology-empty">无调整记录</div>}
                {adjustments.map(a => (
                  <div key={a.id} className="pev-adjust">
                    <span>{fmt(a.before_confidence)} → {fmt(a.after_confidence)}（建议 {fmt(a.suggested_confidence)}）</span>
                    <span className="ew-meta">{DIRECTION_LABEL[a.direction as keyof typeof DIRECTION_LABEL] ?? a.direction} · {a.formula_version} · {a.status}{a.rolled_back_at ? ` · 已回滚 ${a.rollback_reason ?? ''}` : ''}</span>
                  </div>
                ))}
              </section>
              {matchedEvidence[0] && (
                <div className="ontology-detail-row" style={{ marginTop: 12 }}>
                  <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => setRollbackTarget(matchedEvidence[0])}>回滚证据</button>
                </div>
              )}
              <div className="ontology-form-row" style={{ marginTop: 12 }}>
                <input className="filter-input" placeholder="复核备注（可选）" value={note} onChange={e => setNote(e.target.value)} />
                <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={resolve}>标记复核完成</button>
              </div>
            </div>
          </aside>
        </div>
      )}

      <ConfirmDialog
        open={rollbackTarget !== null}
        title="回滚论文证据"
        message={`确定回滚「${rollbackTarget?.title ?? ''}」？将撤销置信度调整并重建 evidence_text。`}
        onConfirm={rollback}
        onCancel={() => { setRollbackTarget(null); setRollbackReason('') }}
        confirmLabel="确认回滚"
        danger
        loading={busy}
      >
        <textarea
          className="filter-input"
          style={{ width: '100%', minHeight: 64, marginTop: 8 }}
          placeholder="回滚原因（必填）"
          value={rollbackReason}
          onChange={e => setRollbackReason(e.target.value)}
        />
      </ConfirmDialog>
    </div>
  )
}
