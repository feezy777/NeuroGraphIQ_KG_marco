/**
 * Step 4:候选证据整理 + 中文辅助翻译 + 研究者选择。
 * - Evidence Candidate = Step3 SUPPORTED/PARTIAL 且通过完整性 Gate(引用 segment/review,不复制原文)。
 * - SUPPORTED/PARTIAL 自动翻译(幂等:同 version 复用 0 调用);UNCERTAIN 仅手动轻量翻译。
 * - 默认选中 SUPPORTED;[下一步:人工审核] 为占位准备态(不进入 Human Review 后端)。
 * - NOT_SUPPORTED 只保留小字计数 + [查看过滤记录] Drawer,不进主列表。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { PaperDetailDrawer } from '../../components/PaperDetailDrawer'
import {
  pewExcludeCandidate,
  pewListCandidates,
  pewListReviews,
  pewSelectCandidate,
  pewSyncCandidates,
  pewTranslateCandidates,
  type PewEvidenceCandidate,
  type PewReviewItem,
} from './pewApi'
import { notifyTaskCandidatesChanged } from './pewStore'

type CandTab = 'all' | 'supported' | 'partial_support' | 'uncertain'

const DECISION_LABEL: Record<string, string> = {
  supported: 'SUPPORTED',
  partial_support: 'PARTIAL',
  uncertain: 'UNCERTAIN',
}
const DIRECTION_LABEL: Record<string, string> = {
  source_to_target: 'source → target',
  target_to_source: 'target → source',
  bidirectional: 'bidirectional',
  undetermined: 'undetermined',
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export function EvidenceCandidatesStage({ rankingId, connectionType, onBackToAi, onNextHumanReview }: {
  rankingId: string
  connectionType: string
  onBackToAi: () => void
  onNextHumanReview: () => void
}) {
  const [candidates, setCandidates] = useState<PewEvidenceCandidate[]>([])
  const [reviews, setReviews] = useState<PewReviewItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<CandTab>('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const [rawOpen, setRawOpen] = useState<{ id: string; kind: 'raw' | 'prompt' } | null>(null)
  const [filteredOpen, setFilteredOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState<Set<string>>(new Set())
  const [msg, setMsg] = useState<string | null>(null)
  const [reviewHint, setReviewHint] = useState(false)
  const [detailPaperId, setDetailPaperId] = useState<string | null>(null)

  const load = useCallback(async () => {
    const [cr, rr] = await Promise.all([pewListCandidates(rankingId), pewListReviews(rankingId)])
    setCandidates(cr.items)
    setReviews(rr.items)
  }, [rankingId])

  // mount:同步(幂等)→ 载入 → 未译的 candidate 自动翻译(已译→后端复用 0 调用)
  useEffect(() => {
    let cancelled = false
    async function init() {
      setBusy(true)
      try {
        await pewSyncCandidates(rankingId)
        await load()
        const needTrans = (await pewListCandidates(rankingId)).items.filter(c =>
          c.candidate_status === 'candidate' && !c.translated_text &&
          (c.ai_decision === 'supported' || c.ai_decision === 'partial_support'))
        if (needTrans.length > 0) {
          await pewTranslateCandidates(rankingId, needTrans.map(c => c.segment_id))
          await load()
          notifyTaskCandidatesChanged(rankingId)
        }
      } catch (err) {
        if (!cancelled) setMsg(`候选证据加载失败:${errText(err)}`)
      } finally {
        if (!cancelled) setLoaded(true)
        setBusy(false)
      }
    }
    void init()
    return () => { cancelled = true }
  }, [rankingId, load])

  const mainCandidates = useMemo(
    () => candidates.filter(c => c.candidate_status === 'candidate'),
    [candidates],
  )
  const uncertainItems = useMemo(
    () => reviews.filter(r => !r.failed && r.decision === 'uncertain'),
    [reviews],
  )
  const filteredCount = useMemo(
    () => reviews.filter(r => !r.failed && r.decision === 'not_supported').length,
    [reviews],
  )
  const excludedCount = useMemo(
    () => candidates.filter(c => c.candidate_status === 'excluded').length,
    [candidates],
  )

  const selected = useMemo(() => mainCandidates.filter(c => c.selected_for_review), [mainCandidates])
  const supported = useMemo(() => mainCandidates.filter(c => c.ai_decision === 'supported'), [mainCandidates])
  const partial = useMemo(() => mainCandidates.filter(c => c.ai_decision === 'partial_support'), [mainCandidates])
  const paperIds = useMemo(() => new Set(mainCandidates.map(c => c.paper_id)), [mainCandidates])
  const directCount = useMemo(() => selected.filter(c => c.evidence_type === 'direct').length, [selected])
  const indirectCount = useMemo(() => selected.filter(c => c.evidence_type === 'indirect').length, [selected])

  const visible = useMemo(() => {
    if (tab === 'uncertain') return null
    const list = tab === 'all' ? mainCandidates : mainCandidates.filter(c => c.ai_decision === tab)
    return list
  }, [tab, mainCandidates])

  const toggleSelected = useCallback(async (c: PewEvidenceCandidate) => {
    setBusy(true)
    try {
      await pewSelectCandidate(rankingId, c.segment_id, !c.selected_for_review)
      await load()
      notifyTaskCandidatesChanged(rankingId)
    } catch (err) {
      setMsg(`选择失败:${errText(err)}`)
    } finally {
      setBusy(false)
    }
  }, [rankingId, load])

  const selectAllSupported = useCallback(async () => {
    setBusy(true)
    try {
      await load() // 保证 supported 为最新选择态
      for (const c of supported) {
        if (!c.selected_for_review) await pewSelectCandidate(rankingId, c.segment_id, true)
      }
      await load()
      notifyTaskCandidatesChanged(rankingId)
    } finally {
      setBusy(false)
    }
  }, [rankingId, supported, load])

  const excludeCandidate = useCallback(async (c: PewEvidenceCandidate) => {
    setMenuOpenId(null)
    try {
      await pewExcludeCandidate(rankingId, c.segment_id)
      await load()
      notifyTaskCandidatesChanged(rankingId)
    } catch (err) {
      setMsg(`排除失败:${errText(err)}`)
    }
  }, [rankingId, load])

  const reTranslateOne = useCallback(async (c: PewEvidenceCandidate) => {
    setMenuOpenId(null)
    try {
      await pewTranslateCandidates(rankingId, [c.segment_id], true)
      await load()
    } catch (err) {
      setMsg(`重新翻译失败:${errText(err)}`)
    }
  }, [rankingId, load])

  const translateUncertain = useCallback(async (r: PewReviewItem) => {
    // UNCERTAIN 轻量翻译:临时放 review 级别(仅展示,不入候选表);以内存状态显示
    setBusy(true)
    try {
      await pewTranslateCandidates(rankingId, [r.segment_id])
      setMsg('翻译请求已提交(结果仅在候选层生效;UNCERTAIN 不进入候选集合)')
    } catch (err) {
      setMsg(`翻译失败:${errText(err)}`)
    } finally {
      setBusy(false)
    }
  }, [rankingId])

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }
  const toggleDetails = (id: string) => {
    setDetailsOpen(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const paperShort = (p: string) => p.slice(0, 8)

  return (
    <div className="edw-stage" data-testid="edw-stage-4">
      {/* 标题 + 右上角:返回AI审核 + 主流程[下一步:人工审核] */}
      <div className="edw-stage-head edw-stage-head-row">
        <div>
          <h3 className="edw-stage-title">候选证据</h3>
          <p className="edw-stage-desc">
            以下证据已经经过文本规则筛选和 AI 科学语义审核,可由研究者进一步确认并送入人工审核。
          </p>
        </div>
        <div className="edw-head-actions">
          <button type="button" className="btn" data-testid="edw-back-to-ai-btn" onClick={onBackToAi}>
            返回AI审核
          </button>
          <button
            type="button" className="btn btn-primary"
            disabled={selected.length === 0}
            title={selected.length === 0 ? '请至少选择一条候选证据。' : undefined}
            data-testid="edw-next-human-btn"
            onClick={() => setReviewHint(h => !h)}
          >
            下一步:人工审核
          </button>
        </div>
      </div>
      {reviewHint && selected.length > 0 && (
        <div className="edw-feedback" data-testid="edw-human-hint">
          候选证据已准备({selected.length} 条)。人工审核链路将在下一阶段接入(本阶段仅记录准备态)。
        </div>
      )}
      {msg && <div className="edw-feedback" data-testid="edw-stage4-msg">{msg}</div>}

      {/* 顶部统计 */}
      <div className="edw-stats edw-stats-results" data-testid="edw-stage4-stats">
        <div className="edw-stat"><div className="edw-stat-value">{mainCandidates.length}</div><div className="edw-stat-label">有效候选证据</div></div>
        <div className="edw-stat"><div className="edw-stat-value edw-stat-created">{supported.length}</div><div className="edw-stat-label">SUPPORTED</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{partial.length}</div><div className="edw-stat-label">PARTIAL</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{uncertainItems.length}</div><div className="edw-stat-label">UNCERTAIN</div></div>
        <div className="edw-stat"><div className="edw-stat-value edw-stat-found">{selected.length}</div><div className="edw-stat-label">已选择</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{paperIds.size}</div><div className="edw-stat-label">论文数</div></div>
      </div>
      <div className="edw-muted-hint" style={{ marginBottom: 10 }}>
        已过滤无支持片段:{filteredCount}{excludedCount > 0 ? ` · 已排除 ${excludedCount}` : ''}
        {' '}<button type="button" className="edw-link-btn" data-testid="edw-show-filtered-btn" onClick={() => setFilteredOpen(o => !o)}>查看过滤记录</button>
      </div>

      {/* tabs:全部/Supported/Partial/待确认(不再以 Strong/Medium/Weak 为主要筛选) */}
      <div className="edw-lvl-tabs" data-testid="edw-stage4-tabs">
        {(['all', 'supported', 'partial_support', 'uncertain'] as CandTab[]).map(t => (
          <button key={t} type="button" className={`btn btn-sm ${tab === t ? 'btn-primary' : ''}`} data-testid={`edw-candtab-${t}`} onClick={() => setTab(t)}>
            {t === 'all' ? `全部(${mainCandidates.length})`
              : t === 'uncertain' ? `待确认(${uncertainItems.length})`
              : `${DECISION_LABEL[t]}(${t === 'supported' ? supported.length : partial.length})`}
          </button>
        ))}
        {supported.length > 0 && (
          <button type="button" className="btn btn-sm" data-testid="edw-select-all-supported" onClick={() => void selectAllSupported()}>
            全选 Supported
          </button>
        )}
      </div>

      {/* 主候选卡片(研究者视角;引用原文+辅助翻译) */}
      {visible && visible.length > 0 && (
        <div className="edw-frag-list" data-testid="edw-cand-list">
          {visible.map(c => (
            <div className={`edw-frag-card ${c.ai_decision === 'supported' ? 'edw-dec-supported' : 'edw-dec-partial'}`} key={c.segment_id} data-testid={`edw-cand-${c.segment_id}`}>
              <div className="edw-frag-head">
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input type="checkbox" checked={c.selected_for_review} disabled={busy}
                    data-testid={`edw-cand-select-${c.segment_id}`}
                    onChange={() => void toggleSelected(c)} />
                  选择
                </label>
                <span className="edw-frag-title">{c.paper_title || '(未命名)'}</span>
                <span className={`edw-dec-badge ${c.ai_decision === 'supported' ? 'edw-dec-supported' : 'edw-dec-partial'}`} data-testid={`edw-cand-dec-${c.segment_id}`}>
                  {DECISION_LABEL[c.ai_decision]}
                  {c.ai_confidence != null ? ` ${Math.round(c.ai_confidence * 100)}%` : ''}
                </span>
                <span style={{ flex: 1 }} />
                <div className="edw-menu-wrap">
                  <button type="button" className="btn btn-sm edw-card-menu-btn" data-testid={`edw-cand-menu-${c.segment_id}`}
                    onClick={() => setMenuOpenId(prev => (prev === c.segment_id ? null : c.segment_id))}>
                    ⋯
                  </button>
                  {menuOpenId === c.segment_id && (
                    <div className="edw-menu" data-testid={`edw-cand-menu-list-${c.segment_id}`} onClick={() => setMenuOpenId(null)}>
                      <button type="button" className="edw-menu-item" data-testid={`edw-cand-exclude-${c.segment_id}`} onClick={() => void excludeCandidate(c)}>排除此证据</button>
                      <button type="button" className="edw-menu-item" data-testid={`edw-cand-retranslate-${c.segment_id}`} onClick={() => void reTranslateOne(c)}>重新翻译</button>
                      <button type="button" className="edw-menu-item" data-testid={`edw-cand-raw-${c.segment_id}`} onClick={() => setRawOpen({ id: c.segment_id, kind: 'raw' })}>查看原始模型响应</button>
                      <button type="button" className="edw-menu-item" data-testid={`edw-cand-prompt-${c.segment_id}`} onClick={() => setRawOpen({ id: c.segment_id, kind: 'prompt' })}>查看 Prompt</button>
                    </div>
                  )}
                </div>
              </div>
              <div className="edw-muted-hint">
                {c.paper_journal ? `${c.paper_journal} · ` : ''}{c.paper_year ?? ''} · PMID {c.paper_pmid || '—'}
                {c.paper_doi ? ` · DOI ${c.paper_doi}` : ''} · Section:{c.section || '—'}
              </div>
              <div className="edw-ai-review">
                <div className="edw-ai-row"><span>Evidence Type:</span><b>{c.evidence_type ?? '—'}</b></div>
                <div className="edw-ai-row"><span>Connection Type Supported:</span><b>{c.connection_type_supported ?? '—'}</b></div>
                <div className="edw-ai-row"><span>Direction:</span><b>{c.direction_support ? (DIRECTION_LABEL[c.direction_support] ?? c.direction_support) : '—'}</b></div>
              </div>
              <p className="edw-frag-title-sub" data-testid={`edw-cand-en-${c.segment_id}`}>【论文英文原文】</p>
              <p className="edw-frag-sentence">{c.sentence}</p>
              <p className="edw-frag-title-sub" data-testid={`edw-cand-zh-${c.segment_id}`}>
                【中文辅助翻译】
                {c.translation_id && (
                  <span className="edw-muted-hint" style={{ fontWeight: 400 }}
                    title="该译文已保存在翻译资产库,可在后续审核流程复用。">
                    [已缓存]
                  </span>
                )}
              </p>
              <p className="edw-frag-sentence">{c.translated_text || '（尚未生成）'}</p>
              <p className="edw-muted-hint" style={{ fontSize: 11 }}>
                中文仅供辅助阅读,科研证据依据以英文原文为准。
              </p>
              <div className="edw-ai-review">
                <div className="edw-ai-row"><span>AI判断理由:</span><span>{c.reason || '—'}</span></div>
                {c.contradiction_reason && <div className="edw-ai-row"><span>Contradiction:</span><span>{c.contradiction_reason}</span></div>}
              </div>
              {/* 证据来源详情(折叠;检索技术细节弱化) */}
              <button type="button" className="edw-link-btn" data-testid={`edw-cand-details-${c.segment_id}`} onClick={() => toggleDetails(c.segment_id)}>
                {detailsOpen.has(c.segment_id) ? '收起证据来源详情' : '证据来源详情'}
              </button>
              {detailsOpen.has(c.segment_id) && (
                <div className="edw-frag-tags" data-testid={`edw-cand-details-box-${c.segment_id}`}>
                  <span className="edw-chip">Function Retrieval:{c.candidate_level ?? '—'}</span>
                  <span className="edw-chip">Rule Score:{c.rule_score != null ? c.rule_score.toFixed(2) : '—'}</span>
                  <span className="edw-chip">Matched:{c.matched_source ?? '—'} / {c.matched_target ?? '—'}</span>
                  {(c.relation_terms ?? []).slice(0, 3).map(w => <span className="edw-chip" key={w}>{w}</span>)}
                  <span className="edw-chip">{c.proximity}</span>
                  <span className="edw-chip">{c.source_type}</span>
                </div>
              )}
              {rawOpen?.id === c.segment_id && (
                <pre className="edw-raw-pre">
                  {rawOpen.kind === 'raw'
                    ? JSON.stringify({ decision: c.ai_decision, confidence: c.ai_confidence, evidence_type: c.evidence_type, reason: c.reason, connection_type_supported: c.connection_type_supported, direction_support: c.direction_support, supporting_phrase: c.supporting_phrase }, null, 2)
                    : '[stage4 prompt: zh v1] SYSTEM 翻译原则(忠实/不增删/保留术语与方向) + 原文句 + 必要上下文'}
                </pre>
              )}
              <div className="edw-frag-actions">
                <button type="button" className="btn btn-sm" data-testid={`edw-cand-context-${c.segment_id}`} onClick={() => toggleExpand(c.segment_id)}>
                  {expanded.has(c.segment_id) ? '收起上下文' : '查看上下文'}
                </button>
                <button type="button" className="btn btn-sm" data-testid={`edw-cand-paper-${c.segment_id}`} onClick={() => setDetailPaperId(c.paper_id)}>
                  查看论文
                </button>
              </div>
              {expanded.has(c.segment_id) && (
                <div className="edw-frag-context">
                  {c.context_before && <p className="edw-muted-hint">上一句:{c.context_before}</p>}
                  {c.context_after && <p className="edw-muted-hint">下一句:{c.context_after}</p>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 待确认(UNCERTAIN):只看原文+AI reason+confidence;默认不可选择送审 */}
      {tab === 'uncertain' && (
        <div className="edw-frag-list" data-testid="edw-uncertain-list">
          {uncertainItems.length === 0 ? (
            <p className="edw-muted-hint">暂无待确认片段。</p>
          ) : uncertainItems.map(r => (
            <div className="edw-frag-card edw-dec-uncertain" key={r.segment_id} data-testid={`edw-uncertain-${r.segment_id}`}>
              <div className="edw-frag-head">
                <span className="edw-frag-title">{r.paper_title}</span>
                <span className="edw-dec-badge edw-dec-uncertain">UNCERTAIN {r.confidence != null ? `${Math.round(r.confidence * 100)}%` : ''}</span>
              </div>
              <div className="edw-muted-hint">PMID {r.paper_pmid || '—'} · Section:{r.section || '—'}</div>
              <p className="edw-frag-sentence">{r.sentence}</p>
              <div className="edw-ai-review">
                <div className="edw-ai-row"><span>AI reason:</span><span>{r.reason || '—'}</span></div>
                <div className="edw-ai-row"><span>中文翻译:</span><span>尚未生成</span></div>
              </div>
              <div className="edw-frag-actions">
                <button type="button" className="edw-link-btn" data-testid={`edw-uncertain-translate-${r.segment_id}`} onClick={() => { void translateUncertain(r) }}>
                  生成中文翻译
                </button>
              </div>
              <p className="edw-muted-hint" style={{ fontSize: 11 }}>
                UNCERTAIN 默认不能进入已选候选证据;可通过重新 AI 审核或后续人工确认处理。
              </p>
            </div>
          ))}
        </div>
      )}

      {/* 已过滤无支持片段 Drawer */}
      {filteredOpen && (
        <div className="edw-modal-backdrop" onClick={() => setFilteredOpen(false)}>
          <div className="edw-modal" onClick={e => e.stopPropagation()}>
            <h4 className="edw-modal-title">已过滤无支持片段({filteredCount})</h4>
            <div className="edw-picker-list">
              {reviews.filter(r => !r.failed && r.decision === 'not_supported').map(r => (
                <div key={r.segment_id} className="govw-evidence-item">
                  <div className="govw-rule-detail"><b>{r.paper_title}</b> · PMID {r.paper_pmid || '—'} · {r.section}</div>
                  <p className="govw-evidence-sentence" style={{ fontSize: 12 }}>{r.sentence}</p>
                  {r.reason && <p className="edw-muted-hint">{r.reason}</p>}
                </div>
              ))}
              {filteredCount === 0 && <p className="edw-muted-hint">无可展示过滤记录。</p>}
            </div>
            <div className="edw-picker-actions" style={{ justifyContent: 'flex-end' }}>
              <button type="button" className="btn btn-sm" onClick={() => setFilteredOpen(false)}>关闭</button>
            </div>
          </div>
        </div>
      )}

      <div className="edw-meta" data-testid="edw-stage4-meta">
        NOT_SUPPORTED {filteredCount} 条仅保留 AI Review 历史;本页不展示其红卡列表。
      </div>

      {detailPaperId && <PaperDetailDrawer paperId={detailPaperId} onClose={() => setDetailPaperId(null)} />}
    </div>
  )
}

// 侧栏【已选候选证据】数据下标(避免重复计算)
export function selectedCandidatesOf(candidates: PewEvidenceCandidate[]): PewEvidenceCandidate[] {
  return candidates.filter(c => c.candidate_status === 'candidate' && c.selected_for_review)
}

// 供侧栏复用的 paper 摘要非导出组件内部使用
export function paperLabelPN(c: PewEvidenceCandidate): string {
  return `${paperShortOf(c.paper_title)} — PMID ${c.paper_pmid || '—'}`
}
function paperShortOf(t: string): string {
  const s = t || ''
  return s.length > 42 ? `${s.slice(0, 42)}…` : s
}
