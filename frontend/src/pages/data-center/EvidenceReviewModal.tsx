import { useCallback, useEffect, useState } from 'react'
import {
  attachPaperEvidence,
  extractPaperPassage,
  getEvidenceQueue,
  searchPaperEvidence,
  translateEvidenceText,
  type PaperSearchResponse,
} from '../../api/endpoints'

interface QueueItem {
  target_type: string
  target_id: string
  label: string
  confidence: number | null
}

export function EvidenceReviewModal({ open, onClose, initialItems }: {
  open: boolean
  onClose: () => void
  initialItems?: QueueItem[]
}) {
  const [targetType, setTargetType] = useState('connection')
  const [scope, setScope] = useState('low_confidence')
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [idx, setIdx] = useState(0)
  const [result, setResult] = useState<PaperSearchResponse | null>(null)
  const [selectedPmid, setSelectedPmid] = useState('')
  const [passage, setPassage] = useState('')
  const [translated, setTranslated] = useState('')
  const [direction, setDirection] = useState('supports')
  const [confidence, setConfidence] = useState('0.8')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [doneCount, setDoneCount] = useState(0)

  useEffect(() => {
    if (open && initialItems && initialItems.length > 0) {
      setQueue(initialItems)
      setIdx(0)
      setDoneCount(0)
    }
  }, [open, initialItems])

  const current = queue[idx]

  const loadQueue = useCallback(async () => {
    setBusy(true)
    setMessage(null)
    try {
      const resp = await getEvidenceQueue({ target_type: targetType, scope, limit: 50 })
      setQueue(resp.items)
      setIdx(0)
      setDoneCount(0)
    } catch (err) {
      setMessage(`加载队列失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [targetType, scope])

  const searchForCurrent = useCallback(async (item: QueueItem) => {
    setBusy(true)
    setMessage(null)
    setTranslated('')
    try {
      const resp = await searchPaperEvidence({ target_type: item.target_type, target_id: item.target_id, limit: 5 })
      setResult(resp)
      setSelectedPmid(resp.papers[0]?.pmid ?? '')
      setPassage('')
    } catch (err) {
      setResult(null)
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    if (open && current) void searchForCurrent(current)
  }, [open, current, searchForCurrent])

  const selectedPaper = result?.papers.find(p => p.pmid === selectedPmid)

  const extract = useCallback(async () => {
    if (!current || !selectedPaper) return
    setBusy(true)
    setMessage(null)
    try {
      const r = await extractPaperPassage({
        target_type: current.target_type,
        target_id: current.target_id,
        pmid: selectedPaper.pmid,
        title: selectedPaper.title,
        abstract: selectedPaper.abstract,
      })
      setPassage(r.passage)
      setDirection(r.direction)
      setConfidence(String(r.confidence))
      setTranslated('')
      setMessage(`AI 截取完成（${r.direction}，置信度 ${r.confidence}）`)
    } catch (err) {
      setMessage(`截取失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [current, selectedPaper])

  const translate = useCallback(async () => {
    if (!passage.trim()) return
    setBusy(true)
    try {
      const r = await translateEvidenceText({ text: passage })
      setTranslated(r.translated)
      setMessage('翻译完成，可编辑后入库')
    } catch (err) {
      setMessage(`翻译失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [passage])

  const attach = useCallback(async () => {
    if (!current || !selectedPmid) return
    setBusy(true)
    setMessage(null)
    try {
      await attachPaperEvidence({
        target_type: current.target_type,
        target_id: current.target_id,
        pmid: selectedPmid,
        excerpt: translated || passage,
        direction,
        suggested_confidence: parseFloat(confidence) || undefined,
      })
      setDoneCount(c => c + 1)
      setMessage('已入库 ✓')
    } catch (err) {
      setMessage(`入库失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [current, selectedPmid, translated, passage, direction, confidence])

  if (!open) return null

  return (
    <div className="evidence-review-panel">
      <div className="ontology-card-header">
        <span className="ontology-card-title">论文佐证审核（{doneCount}/{queue.length}）</span>
        <div className="ontology-overview-actions">
          <select className="filter-select" value={targetType} onChange={e => setTargetType(e.target.value)}>
            {['connection', 'projection_function', 'circuit_function', 'circuit_step', 'circuit'].map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="filter-select" value={scope} onChange={e => setScope(e.target.value)}>
            <option value="low_confidence">低置信</option>
            <option value="all">全部</option>
            <option value="all_ungrounded">未锚定</option>
          </select>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={loadQueue}>加载队列</button>
          <button type="button" className="btn btn-sm" onClick={onClose}>关闭</button>
        </div>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      {queue.length === 0 && <div className="ontology-empty">点击“加载队列”开始</div>}
      {current && (
        <div className="evidence-review-body">
          <div className="pe-list">
            <h4>当前对象（{idx + 1}/{queue.length}）</h4>
            <div className="ontology-preview">
              <strong>{current.label}</strong>
              <div>{current.target_type} · {current.target_id.slice(0, 8)} · 置信度 {current.confidence ?? '—'}</div>
            </div>
            <h4>候选论文</h4>
            {result?.papers.map(p => (
              <div key={p.pmid} className="ontology-preview" style={{ cursor: 'pointer' }} onClick={() => { setSelectedPmid(p.pmid); setPassage(''); setTranslated('') }}>
                <strong>{p.title}</strong>
                <div>{p.year} · {p.journal}</div>
                {p.pmid && <a href={`https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>PubMed {p.pmid}</a>}
              </div>
            ))}
            {selectedPaper && (
              <div className="ontology-form-row">
                <button type="button" className="btn btn-sm" disabled={busy} onClick={extract}>AI 截取段落</button>
                <button type="button" className="btn btn-sm" disabled={busy || !passage.trim()} onClick={translate}>翻译</button>
                <button type="button" className="btn btn-sm" disabled={busy || !selectedPmid} onClick={attach}>入库</button>
                <button type="button" className="btn btn-sm" disabled={busy || idx + 1 >= queue.length} onClick={() => { setIdx(i => i + 1) }}>下一条</button>
                <button type="button" className="btn btn-sm" disabled={busy || idx === 0} onClick={() => setIdx(i => i - 1)}>上一条</button>
              </div>
            )}
          </div>
          <div className="pe-detail">
            <h4>证据审核</h4>
            {selectedPaper && <div className="ontology-preview"><strong>{selectedPaper.title}</strong><div>{selectedPaper.abstract.slice(0, 300)}…</div></div>}
            <textarea className="filter-input pe-excerpt" value={passage} onChange={e => setPassage(e.target.value)} placeholder="AI 截取的英文段落（可编辑）" />
            {translated && <textarea className="filter-input pe-excerpt" value={translated} onChange={e => setTranslated(e.target.value)} placeholder="中文译文（可编辑）" />}
            <div className="ontology-form-row">
              <select className="filter-select" value={direction} onChange={e => setDirection(e.target.value)}>
                <option value="supports">支持</option><option value="partial">部分支持</option>
                <option value="contradicts">矛盾</option><option value="not_found">未找到</option>
              </select>
              <input className="filter-input" style={{ width: 80 }} value={confidence} onChange={e => setConfidence(e.target.value)} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
