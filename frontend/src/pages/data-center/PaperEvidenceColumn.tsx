import { useCallback, useEffect, useState } from 'react'
import {
  attachPaperEvidence,
  extractPaperPassage,
  getEvidenceTarget,
  listPaperEvidence,
  rollbackPaperEvidence,
  searchPaperEvidence,
  translateEvidenceText,
  type EvidencePassageInput,
  type PaperEvidenceItem,
  type PaperSearchResponse,
  type EvidenceTargetDto,
} from '../../api/endpoints'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { computeTmpCoverage } from './evidence-workbench/claimCoverage'
import { COMPONENT_LABEL, LEVEL_LABEL } from './evidence-workbench/types'

type Direction = 'supports' | 'partial' | 'contradicts' | 'mixed' | 'not_found'

export function PaperEvidenceColumn({ targetType, targetId }: { targetType: string; targetId: string }) {
  const [mode, setMode] = useState<'function' | 'existence'>('function')
  const [result, setResult] = useState<PaperSearchResponse | null>(null)
  const [selected, setSelected] = useState<PaperSearchResponse['papers'][number] | null>(null)
  const [passages, setPassages] = useState<Array<{
    key: string
    source_scope: 'abstract' | 'fulltext'
    section_title: string | null
    paragraph_index: number | null
    passage: string
    direction: Direction
    reason: string
    confidence: number
    source_locator: string | null
    source_verified: boolean
  }>>([])
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [translations, setTranslations] = useState<Record<string, string>>({})
  const [direction, setDirection] = useState<Direction>('supports')
  const [confidence, setConfidence] = useState('0.8')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [existing, setExisting] = useState<PaperEvidenceItem[]>([])
  const [detail, setDetail] = useState<PaperEvidenceItem | null>(null)
  const [rollbackTarget, setRollbackTarget] = useState<PaperEvidenceItem | null>(null)
  const [rollbackReason, setRollbackReason] = useState('')
  const [targetDto, setTargetDto] = useState<EvidenceTargetDto | null>(null)

  const refreshList = useCallback(async () => {
    try {
      const r = await listPaperEvidence({ target_type: targetType, target_id: targetId, limit: 50 })
      setExisting(r.items)
    } catch {
      setExisting([])
    }
  }, [targetType, targetId])

  useEffect(() => {
    void refreshList()
  }, [refreshList])

  const search = useCallback(async () => {
    setMessage(null)
    setBusy('search')
    try {
      const resp = await searchPaperEvidence({ target_type: targetType, target_id: targetId, mode, limit: 8 })
      setResult(resp)
      setSelected(null)
      setPassages([])
      setSelectedKeys(new Set())
    } catch (err) {
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [targetType, targetId, mode])

  const pick = useCallback((paper: PaperSearchResponse['papers'][number]) => {
    setSelected(paper)
    setPassages([])
    setSelectedKeys(new Set())
  }, [])

  const extract = useCallback(async () => {
    if (!selected) return
    setBusy('extract')
    setMessage(null)
    try {
      const r = await extractPaperPassage({
        target_type: targetType,
        target_id: targetId,
        pmid: selected.pmid,
        doi: selected.doi,
        title: selected.title,
        abstract: selected.abstract,
      })
      const mapped = r.passages.map((p, i) => ({
        key: `${selected.pmid}-${i}`,
        source_scope: p.source_scope,
        section_title: p.section_title,
        paragraph_index: p.paragraph_index,
        passage: p.passage,
        direction: p.direction as 'supports' | 'partial' | 'contradicts' | 'not_found',
        reason: p.reason,
        confidence: p.confidence,
        source_locator: p.source_locator,
        source_verified: p.source_verified,
      }))
      setPassages(mapped)
      setSelectedKeys(new Set(mapped.filter(p => p.source_verified).map(p => p.key)))
      setDirection(r.overall_direction)
      setMessage(`${mapped.filter(p => p.source_verified).length}/${mapped.length} 个片段通过原文校验`)
    } catch (err) {
      setMessage(`截取失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [selected, targetType, targetId])

  const translateOne = useCallback(async (key: string, text: string) => {
    setBusy('translate')
    try {
      const r = await translateEvidenceText({ text })
      setTranslations(t => ({ ...t, [key]: r.translated }))
    } catch (err) {
      setMessage(`翻译失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [])

  const attach = useCallback(async () => {
    if (!selected) return
    const chosen = passages.filter(p => selectedKeys.has(p.key) && p.source_verified)
    if (chosen.length === 0) {
      setMessage('请先选择至少一个通过校验的原文片段')
      return
    }
    setBusy('attach')
    setMessage(null)
    try {
      const body: EvidencePassageInput[] = chosen.map(p => ({
        source_scope: p.source_scope,
        section_title: p.section_title,
        paragraph_index: p.paragraph_index,
        passage: p.passage,
        direction: p.direction as 'supports' | 'partial' | 'contradicts' | 'not_found',
        reason: p.reason,
        confidence: p.confidence,
        source_locator: p.source_locator,
        source_verified: true,
      }))
      const resp = await attachPaperEvidence({
        target_type: targetType,
        target_id: targetId,
        pmid: selected.pmid,
        direction,
        evidence_level: 'indirect',
        reviewer_confidence: parseFloat(confidence) || 0,
        passages: body,
      })
      await refreshList()
      setMessage(`已挂接 ${resp.passage_count} 段原文，对象置信度=${resp.confidence ?? '不变'}（${resp.verification_status}）`)
    } catch (err) {
      setMessage(`挂接失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [selected, passages, selectedKeys, direction, confidence, targetType, targetId, refreshList])

  const rollback = useCallback(async () => {
    if (!rollbackTarget) return
    setBusy('rollback')
    try {
      await rollbackPaperEvidence(rollbackTarget.evidence_id, rollbackReason.trim() || '人工撤销')
      setRollbackTarget(null)
      setRollbackReason('')
      setDetail(null)
      await refreshList()
      setMessage('证据已撤销并回滚置信度')
    } catch (err) {
      setMessage(`撤销失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [rollbackTarget, rollbackReason, refreshList])

  const openDetail = useCallback(async (ev: PaperEvidenceItem) => {
    setDetail(ev)
    try {
      const dto = await getEvidenceTarget(targetType, targetId)
      setTargetDto(dto)
    } catch {
      setTargetDto(null)
    }
  }, [targetType, targetId])

  const detailCoverage = detail && targetDto
    ? computeTmpCoverage(
        targetDto.claim_components,
        (detail.passages ?? []).map(p => ({
          hash: p.id,
          source_scope: p.source_scope,
          section_title: p.section_title,
          paragraph_index: p.paragraph_index,
          paragraph_id: null,
          passage: p.passage,
          translation_zh: p.translation_zh,
          direction: p.direction === 'contradicts' ? 'contradicts' : 'supports',
          evidence_level: 'indirect',
          reason: p.reason ?? '',
          confidence: p.confidence ?? 0,
          semantic_confidence: p.confidence,
          source_locator: p.source_locator,
          source_verified: p.source_verified,
          source_verification_method: p.source_verification_method,
          supported_components: p.supported_components,
        })),
      )
    : null

  // historical snapshot takes priority over live re-computation
  const snapshotClaimText = detail?.claim_text_snapshot
  const snapshotComponents = detail?.claim_components_snapshot
  const snapshotCoverage = detail?.coverage_summary_snapshot
  const displayClaimText = snapshotClaimText ?? targetDto?.claim_text ?? null
  const displayComponents = snapshotComponents ?? targetDto?.claim_components ?? []
  const displayCoverage = (snapshotCoverage ?? detailCoverage) as (typeof detailCoverage & { overall_direction?: string }) | null
  const modelVsReviewer = detail?.model_direction && detail?.model_direction !== detail?.direction
  const coverageVsReviewer = displayCoverage && detail?.direction && displayCoverage.overall_direction !== detail.direction

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
        <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={search}>检索论文</button>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      {busy && <div className="ew-busy">处理中：{busy}</div>}
      <div className="pe-split">
        <div className="pe-list">
          <h4>检索结果</h4>
          {result && result.papers.length === 0 && <div className="ontology-empty">未检索到论文</div>}
          {result?.papers.map(paper => (
            <div key={paper.pmid} data-testid="pe-paper" className={`ontology-preview ${selected?.pmid === paper.pmid ? 'ontology-preview-selected' : ''}`} style={{ cursor: 'pointer' }} onClick={() => pick(paper)}>
              <strong>{paper.title}</strong>
              <div>{paper.authors}（{paper.year}）· {paper.journal}</div>
              <div className="ontology-form-row">
                {paper.pmid && <a href={`https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>PubMed {paper.pmid}</a>}
                {paper.doi && <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}> DOI</a>}
                {paper.is_open_access && <span className="ew-oa">OA</span>}
              </div>
            </div>
          ))}
          <h4>已有证据（{existing.length}）</h4>
          {existing.map(ev => (
            <div key={ev.evidence_id} className="ontology-preview" style={{ cursor: 'pointer' }} onClick={() => openDetail(ev)}>
              <strong>{ev.title ?? '未命名文献'}</strong>
              <div>{ev.direction ?? '—'} · {ev.verification_status ?? '—'} · 段落 {ev.passage_count ?? 0}</div>
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
              <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={extract}>AI 提取原文片段</button>
              {passages.length > 0 && (
                <div className="pe-passages">
                  {passages.map(p => {
                    const checked = selectedKeys.has(p.key)
                    return (
                      <div key={p.key} data-testid="ew-passage" className={`ew-passage ${!p.source_verified ? 'ew-passage-invalid' : ''}`}>
                        <label>
                          <input type="checkbox" checked={checked} disabled={!p.source_verified}
                            onChange={e => setSelectedKeys(prev => { const n = new Set(prev); if (e.target.checked) n.add(p.key); else n.delete(p.key); return n })} />
                          选择
                        </label>
                        <span className="ew-meta">{p.source_scope}{p.paragraph_index != null ? ` · ¶${p.paragraph_index}` : ''} · {p.direction} · {p.confidence}</span>
                        {p.source_verified ? <span className="ew-ok">已验证</span> : <span className="ew-bad">未通过校验，禁选</span>}
                        <p className="ew-passage-en">{p.passage}</p>
                        {p.source_verified && (
                          <div className="ontology-form-row">
                            <textarea className="filter-input ew-trans" value={translations[p.key] ?? ''} onChange={e => setTranslations(t => ({ ...t, [p.key]: e.target.value }))} placeholder="中文翻译（可编辑）" />
                            <button type="button" className="btn btn-xs" onClick={() => translateOne(p.key, p.passage)}>翻译</button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                  <div className="ontology-form-row">
                    <select className="filter-select" value={direction} onChange={e => setDirection(e.target.value as Direction)}>
                      <option value="supports">支持</option>
                      <option value="partial">部分支持</option>
                      <option value="contradicts">矛盾</option>
                      <option value="not_found">未找到</option>
                    </select>
                    <input className="filter-input" style={{ width: 80 }} value={confidence} onChange={e => setConfidence(e.target.value)} />
                    <button type="button" className="btn btn-sm" disabled={direction === 'not_found' || busy !== null} onClick={attach}>挂接并更新置信度</button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
      {detail && (
        <div className="ontology-drawer-overlay" onClick={() => setDetail(null)}>
          <aside className="ontology-drawer" style={{ width: 'min(560px, 94vw)' }} onClick={e => e.stopPropagation()}>
            <div className="ontology-drawer-header">
              <span className="ontology-card-title">证据详情</span>
              <button type="button" className="btn btn-xs" onClick={() => setDetail(null)}>关闭</button>
            </div>
            <div className="ontology-drawer-body">
              <div className="ontology-detail-row"><span>标题</span><strong>{detail.title ?? '—'}</strong></div>
              <div className="ontology-detail-row"><span>期刊/年份</span><span>{detail.journal ?? '—'} / {detail.year ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>PMID</span><span>{detail.pmid ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>DOI</span><span>{detail.doi ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>方向</span><span>{detail.direction ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>证据等级</span><span>{detail.evidence_level ? (LEVEL_LABEL[detail.evidence_level as keyof typeof LEVEL_LABEL] ?? detail.evidence_level) : '—'}</span></div>
              <div className="ontology-detail-row"><span>验证状态</span><span>{detail.verification_status ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>审核人</span><span>{detail.verification_by ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>入库时间</span><span>{detail.created_at ? new Date(detail.created_at).toLocaleString() : '—'}</span></div>
              <div className="ontology-detail-row"><span>建议置信度</span><span>{detail.suggested_confidence ?? '—'}（{detail.confidence_adjustment_status ?? '—'}）</span></div>
              {modelVsReviewer && (
                <div className="ew-bad">人工调整了 AI 初判：AI 初判 {detail?.model_direction} / 人工结论 {detail?.direction}</div>
              )}
              {coverageVsReviewer && (
                <div className="ew-bad">人工覆盖了系统 Coverage 判断（Coverage：{displayCoverage?.overall_direction} → 人工：{detail?.direction}）</div>
              )}
              {detail?.reviewer_note && (
                <div className="ontology-detail-row"><span>审核备注</span><span>{detail.reviewer_note}</span></div>
              )}
              {displayClaimText && (
                <>
                  <div className="ontology-detail-row"><span>Claim（{detail?.claim_version ?? '审核时快照'}）</span><strong>{displayClaimText}</strong></div>
                  {displayCoverage && (
                    <div className="ontology-detail-row">
                      <span>Coverage（{detail?.coverage_formula_version ?? 'paper_evidence_coverage_v1'}）</span>
                      <span>
                        {displayCoverage.supported_components.length}/{displayCoverage.required_components.length} 已覆盖
                        {displayCoverage.has_conflict ? ' · 存在冲突' : ''}
                      </span>
                    </div>
                  )}
                </>
              )}
              <div className="ontology-detail-row"><span>链接</span>
                <span>{detail.pmid && <a href={detail.links.pubmed ?? '#'} target="_blank" rel="noreferrer">PubMed</a>} {detail.doi && <a href={detail.links.doi ?? '#'} target="_blank" rel="noreferrer">DOI</a>}</span>
              </div>
              <section className="ontology-detail-section">
                <h4>原文段落（{detail.passage_count ?? 0}）</h4>
                {(detail.passages ?? []).filter(p => p.is_selected).map(p => (
                  <div key={p.id} className="ew-passage">
                    <span className="ew-meta">{p.source_scope}{p.section_title ? ` · ${p.section_title}` : ''}{p.paragraph_index != null ? ` · ¶${p.paragraph_index}` : ''} · {p.direction} · {p.confidence}</span>
                    <span className="ew-meta">核验：{p.source_verified ? (p.source_verification_method ?? 'exact') : '未通过'}</span>
                    {p.supported_components && p.supported_components.length > 0 && (
                      <span className="ew-meta">本段{p.direction === 'contradicts' ? '反驳' : '佐证'}：{p.supported_components.map(c => COMPONENT_LABEL[c] ?? c).join('、')}</span>
                    )}
                    <p className="ew-passage-en">{p.passage}</p>
                    {p.translation_zh && <p className="ew-passage-zh">{p.translation_zh}</p>}
                    {p.reason && <p className="ew-meta">理由：{p.reason}</p>}
                  </div>
                ))}
              </section>
              <div className="ontology-detail-row" style={{ marginTop: 12 }}>
                <button type="button" className="btn btn-sm btn-danger" onClick={() => setRollbackTarget(detail)}>撤销证据</button>
              </div>
            </div>
          </aside>
        </div>
      )}
      <ConfirmDialog
        open={rollbackTarget !== null}
        title="撤销论文证据"
        message={`确定撤销「${rollbackTarget?.title ?? ''}」？将回滚置信度调整并标记为 invalidated。`}
        onConfirm={rollback}
        onCancel={() => { setRollbackTarget(null); setRollbackReason('') }}
        confirmLabel="确认撤销"
        danger
        loading={busy === 'rollback'}
      >
        <textarea
          className="filter-input"
          style={{ width: '100%', minHeight: 64, marginTop: 8 }}
          placeholder="撤销原因（必填）"
          value={rollbackReason}
          onChange={e => setRollbackReason(e.target.value)}
        />
      </ConfirmDialog>
    </div>
  )
}
