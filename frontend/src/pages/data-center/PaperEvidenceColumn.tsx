import { useCallback, useState } from 'react'
import {
  attachPaperEvidence,
  searchPaperEvidence,
  type PaperSearchResponse,
} from '../../api/endpoints'

export function PaperEvidenceColumn({ targetType, targetId }: { targetType: string; targetId: string }) {
  const [mode, setMode] = useState<'function' | 'existence'>('function')
  const [result, setResult] = useState<PaperSearchResponse | null>(null)
  const [selected, setSelected] = useState<PaperSearchResponse['papers'][number] | null>(null)
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
      setSelected(null)
      setExcerpt('')
    } catch (err) {
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [targetType, targetId, mode])

  const pick = useCallback((paper: PaperSearchResponse['papers'][number]) => {
    setSelected(paper)
    setExcerpt(paper.abstract.slice(0, 500))
  }, [])

  const attach = useCallback(async () => {
    if (!selected) return
    setBusy(true)
    setMessage(null)
    try {
      const resp = await attachPaperEvidence({
        target_type: targetType,
        target_id: targetId,
        pmid: selected.pmid,
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
  }, [selected, targetType, targetId, excerpt, direction, mode, confidence])

  return (
    <div className="pe-column">
      <div className="ontology-card-header">
        <span className="ontology-card-title">文献证据</span>
        <span className="ontology-card-sub">{targetType} · {targetId.slice(0, 8)}</span>
      </div>
      <div className="ontology-form-row">
        <select className="filter-select" value={mode} onChange={e => setMode(e.target.value as 'function' | 'existence')}>
          <option value="function">功能佐证</option>
          <option value="existence">存在性佐证</option>
        </select>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={search}>检索论文</button>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      <div className="pe-split">
        <div className="pe-list">
          <h4>检索结果 / 已有证据</h4>
          {result && result.papers.length === 0 && <div className="ontology-empty">未检索到论文</div>}
          {result?.papers.map(paper => (
            <div key={paper.pmid} className={`ontology-preview ${selected?.pmid === paper.pmid ? 'ontology-preview-selected' : ''}`} style={{ cursor: 'pointer' }} onClick={() => pick(paper)}>
              <strong>{paper.title}</strong>
              <div>{paper.authors}（{paper.year}）· {paper.journal}</div>
              <div>
                {paper.pmid && <a href={`https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>PubMed {paper.pmid}</a>}
                {paper.doi && <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}> DOI</a>}
              </div>
            </div>
          ))}
        </div>
        <div className="pe-detail">
          <h4>论文详情</h4>
          {!selected && <div className="ontology-empty">从左侧选择一篇论文</div>}
          {selected && (
            <>
              <strong>{selected.title}</strong>
              <div>{selected.authors}（{selected.year}）· {selected.journal}</div>
              <div className="pe-links">
                {selected.pmid && <a href={`https://pubmed.ncbi.nlm.nih.gov/${selected.pmid}/`} target="_blank" rel="noreferrer">PubMed 原文</a>}
                {selected.doi && <a href={`https://doi.org/${selected.doi}`} target="_blank" rel="noreferrer">DOI 链接</a>}
              </div>
              <details open>
                <summary>摘要</summary>
                <p className="pe-abstract">{selected.abstract || '无摘要'}</p>
              </details>
              <textarea className="filter-input pe-excerpt" value={excerpt} onChange={e => setExcerpt(e.target.value)} placeholder="证据段落（可编辑）" />
              <div className="ontology-form-row">
                <select className="filter-select" value={direction} onChange={e => setDirection(e.target.value)}>
                  <option value="supports">支持</option>
                  <option value="partial">部分支持</option>
                  <option value="contradicts">矛盾</option>
                  <option value="not_found">未找到</option>
                </select>
                <input className="filter-input" style={{ width: 80 }} value={confidence} onChange={e => setConfidence(e.target.value)} />
                <button type="button" className="btn btn-sm" disabled={!excerpt.trim() || busy} onClick={attach}>挂接并更新置信度</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
