import { useCallback, useState } from 'react'
import {
  attachPaperEvidence,
  searchPaperEvidence,
  type PaperSearchResponse,
} from '../../api/endpoints'

const TARGET_TYPES = [
  'projection_function',
  'circuit_function',
  'region_function',
  'projection',
  'connection',
  'circuit',
  'circuit_step',
]

export function PaperEvidencePanel() {
  const [targetType, setTargetType] = useState('projection_function')
  const [targetId, setTargetId] = useState('')
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
      const resp = await searchPaperEvidence({ target_type: targetType, target_id: targetId.trim(), mode, limit: 5 })
      setResult(resp)
      setSelectedPmid('')
      setExcerpt('')
    } catch (err) {
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [targetType, targetId, mode])

  const pickPaper = useCallback((pmid: string, abstract: string) => {
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
        target_id: targetId.trim(),
        pmid: selectedPmid,
        direction: direction as 'supports' | 'partial' | 'contradicts' | 'not_found',
        evidence_level: 'indirect',
        reviewer_confidence: parseFloat(confidence) || 0,
        passages: [{
          source_scope: 'abstract' as const,
          passage: excerpt,
          direction: direction as 'supports' | 'partial' | 'contradicts' | 'not_found',
          confidence: parseFloat(confidence) || 0,
          source_verified: false,
        }],
      })
      setMessage(
        `已挂接证据，置信度=${resp.confidence ?? '不变'}（${resp.verification_status}），` +
        `PubMed：${resp.paper.links.pubmed ?? '-'}`,
      )
    } catch (err) {
      setMessage(`挂接失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }, [selectedPmid, targetType, targetId, excerpt, direction, mode, confidence])

  return (
    <div className="data-center-panel">
      <div className="card ontology-card">
        <div className="ontology-card-header">
          <span className="ontology-card-title">论文检索与证据挂接</span>
          <span className="ontology-card-sub">Europe PMC · 摘要优先 + OA 全文增强</span>
        </div>
        <div className="ontology-form-row">
          <select className="filter-select" value={targetType} onChange={e => setTargetType(e.target.value)}>
            {TARGET_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <input className="filter-input" style={{ width: 300 }} placeholder="目标 ID（UUID）" value={targetId} onChange={e => setTargetId(e.target.value)} />
          <select className="filter-select" value={mode} onChange={e => setMode(e.target.value as 'function' | 'existence')}>
            <option value="function">功能佐证</option>
            <option value="existence">存在性佐证</option>
          </select>
          <button type="button" className="btn btn-sm" disabled={!targetId.trim() || busy} onClick={search}>检索论文</button>
        </div>
      </div>

      {message && <div className="ontology-page-message">{message}</div>}

      {result && (
        <div className="card ontology-card">
          <div className="ontology-card-header">
            <span className="ontology-card-title">检索结果</span>
            <span className="ontology-card-sub">query：{result.target_info.query}</span>
          </div>
          {result.papers.length === 0 && <div className="ontology-empty">未检索到论文</div>}
          {result.papers.map(paper => (
            <div key={paper.pmid} className={`ontology-preview ${selectedPmid === paper.pmid ? 'ontology-preview-selected' : ''}`} style={{ cursor: 'pointer' }} onClick={() => pickPaper(paper.pmid, paper.abstract)}>
              <strong>{paper.title}</strong>
              <div>{paper.authors}（{paper.year}）· {paper.journal}</div>
              <div className="ontology-form-row">
                {paper.pmid && <a href={`https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>PubMed {paper.pmid}</a>}
                {paper.doi && <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>DOI {paper.doi}</a>}
                {selectedPmid === paper.pmid && <span className="ontology-stat-sub">已选择</span>}
              </div>
            </div>
          ))}
          {selectedPmid && (
            <div style={{ marginTop: 12 }}>
              <div className="ontology-form-row">
                <textarea className="filter-input" style={{ width: '100%', minHeight: 100 }} value={excerpt} onChange={e => setExcerpt(e.target.value)} />
              </div>
              <div className="ontology-form-row">
                <select className="filter-select" value={direction} onChange={e => setDirection(e.target.value)}>
                  <option value="supports">支持</option>
                  <option value="partial">部分支持</option>
                  <option value="contradicts">矛盾</option>
                  <option value="not_found">未找到</option>
                </select>
                <input className="filter-input" style={{ width: 100 }} placeholder="建议置信度" value={confidence} onChange={e => setConfidence(e.target.value)} />
                <button type="button" className="btn btn-sm" disabled={!excerpt.trim() || busy} onClick={attach}>挂接证据</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
