import { useCallback, useEffect, useState } from 'react'
import {
  attachPaperEvidence,
  listPaperEvidence,
  searchPaperEvidence,
  type PaperEvidenceItem,
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
  const [existing, setExisting] = useState<PaperEvidenceItem[]>([])
  const [detail, setDetail] = useState<PaperEvidenceItem | null>(null)

  useEffect(() => {
    listPaperEvidence({ target_type: targetType, target_id: targetId })
      .then(r => setExisting(r.items))
      .catch(() => setExisting([]))
  }, [targetType, targetId])

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
          <h4>检索结果</h4>
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
          <h4>已有证据（{existing.length}）</h4>
          {existing.map(ev => (
            <div key={ev.evidence_id} className="ontology-preview" style={{ cursor: 'pointer' }} onClick={() => setDetail(ev)}>
              <strong>{ev.title ?? '未命名文献'}</strong>
              <div>{ev.direction ?? '—'} · {ev.verification_status ?? '—'}</div>
              {ev.pmid && <a href={ev.links.pubmed ?? '#'} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>PubMed {ev.pmid}</a>}
            </div>
          ))}
          {existing.length === 0 && <div className="ontology-empty">暂无证据</div>}
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
      {detail && (
        <div className="ontology-drawer-overlay" onClick={() => setDetail(null)}>
          <aside className="ontology-drawer" style={{ width: 'min(480px, 94vw)' }} onClick={e => e.stopPropagation()}>
            <div className="ontology-drawer-header">
              <span className="ontology-card-title">证据详情</span>
              <button type="button" className="btn btn-xs" onClick={() => setDetail(null)}>关闭</button>
            </div>
            <div className="ontology-drawer-body">
              <div className="ontology-detail-row"><span>标题</span><strong>{detail.title ?? '—'}</strong></div>
              <div className="ontology-detail-row"><span>期刊/年份</span><span>{detail.journal ?? '—'} / {detail.year ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>方向</span><span>{detail.direction ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>验证状态</span><span>{detail.verification_status ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>链接</span>
                <span>{detail.pmid && <a href={detail.links.pubmed ?? '#'} target="_blank" rel="noreferrer">PubMed</a>} {detail.doi && <a href={detail.links.doi ?? '#'} target="_blank" rel="noreferrer">DOI</a>}</span>
              </div>
              <section className="ontology-detail-section">
                <h4>证据段落</h4>
                <p style={{ fontSize: 12 }}>{detail.evidence_text}</p>
              </section>
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
