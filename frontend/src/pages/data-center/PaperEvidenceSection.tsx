import { useCallback, useState } from 'react'
import {
  attachPaperEvidence,
  searchPaperEvidence,
  type PaperSearchResponse,
} from '../../api/endpoints'

export function PaperEvidenceSection({ targetType, targetId }: { targetType: string; targetId: string }) {
  const [mode, setMode] = useState<'function' | 'existence'>('function')
  const [result, setResult] = useState<PaperSearchResponse | null>(null)
  const [selectedPmid, setSelectedPmid] = useState('')
  const [excerpt, setExcerpt] = useState('')
  const [direction, setDirection] = useState('supports')
  const [confidence, setConfidence] = useState('0.8')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const search = useCallback(async () => {
    setMessage(null)
    setBusy(true)
    try {
      const resp = await searchPaperEvidence({ target_type: targetType, target_id: targetId, mode, limit: 5 })
      setResult(resp)
      setSelectedPmid('')
      setExcerpt('')
    } catch (err) {
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [targetType, targetId, mode])

  const pick = useCallback((pmid: string, abstract: string) => {
    setSelectedPmid(pmid)
    setExcerpt(abstract.slice(0, 500))
  }, [])

  const attach = useCallback(async () => {
    if (!selectedPmid) return
    setBusy(true)
    setMessage(null)
    try {
      const resp = await attachPaperEvidence({
        target_type: targetType,
        target_id: targetId,
        pmid: selectedPmid,
        excerpt,
        direction,
        mode,
        suggested_confidence: parseFloat(confidence) || undefined,
      })
      setMessage(`已挂接：置信度=${resp.confidence ?? '不变'}（${resp.verification_status}）`)
    } catch (err) {
      setMessage(`挂接失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [selectedPmid, targetType, targetId, excerpt, direction, mode, confidence])

  return (
    <section className="ontology-detail-section">
      <h4>文献证据</h4>
      <div className="ontology-form-row">
        <select className="filter-select" value={mode} onChange={e => setMode(e.target.value as 'function' | 'existence')}>
          <option value="function">功能佐证</option>
          <option value="existence">存在性佐证</option>
        </select>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={search}>检索论文</button>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      {result && result.papers.length === 0 && <div className="ontology-empty">未检索到论文</div>}
      {result?.papers.map(paper => (
        <div key={paper.pmid} className="ontology-preview" style={{ cursor: 'pointer' }} onClick={() => pick(paper.pmid, paper.abstract)}>
          <strong>{paper.title}</strong>
          <div>{paper.authors}（{paper.year}）· {paper.journal}</div>
          <div className="ontology-form-row">
            {paper.pmid && <a href={`https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>PubMed {paper.pmid}</a>}
            {paper.doi && <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>DOI</a>}
            {selectedPmid === paper.pmid && <span className="ontology-stat-sub">已选择</span>}
          </div>
        </div>
      ))}
      {selectedPmid && (
        <>
          <textarea className="filter-input" style={{ width: '100%', minHeight: 90 }} value={excerpt} onChange={e => setExcerpt(e.target.value)} />
          <div className="ontology-form-row">
            <select className="filter-select" value={direction} onChange={e => setDirection(e.target.value)}>
              <option value="supports">支持</option>
              <option value="partial">部分支持</option>
              <option value="contradicts">矛盾</option>
              <option value="not_found">未找到</option>
            </select>
            <input className="filter-input" style={{ width: 80 }} value={confidence} onChange={e => setConfidence(e.target.value)} />
            <button type="button" className="btn btn-sm" disabled={!excerpt.trim() || busy} onClick={attach}>挂接证据</button>
          </div>
        </>
      )}
    </section>
  )
}
