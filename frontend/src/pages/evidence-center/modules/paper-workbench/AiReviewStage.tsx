/**
 * Step 3:AI 语义审核(批量 LLM;仅判段片段是否支持当前知识)。
 * - 只发送 Step 2 局部 context(事实+论文元数据+片段+信号),不整篇论文、不流式输出。
 * - 同 prompt_version 已审 → 复用(0 调用);「重新 AI 审核」才重调。
 * - 完成显示摘要 + [下一步:候选证据](Step 4 不在本轮)。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  pewListReviews,
  pewListSegments,
  pewRunReviews,
  type PewReviewItem,
  type PewSegment,
} from './pewApi'
import { notifyTaskReviewsChanged } from './pewStore'

type EvidenceTab = 'all' | 'supported' | 'partial_support' | 'uncertain' | 'not_supported'
type LevelTab = 'all' | 'strong' | 'medium' | 'weak'

const DECISION_LABEL: Record<string, string> = {
  supported: 'SUPPORTED',
  partial_support: 'PARTIAL',
  uncertain: 'UNCERTAIN',
  not_supported: 'NOT SUPPORTED',
}
const DECISION_TONE: Record<string, string> = {
  supported: 'edw-dec-supported',
  partial_support: 'edw-dec-partial',
  uncertain: 'edw-dec-uncertain',
  not_supported: 'edw-dec-notsupported',
}
const SOURCE_LABEL: Record<string, string> = { fulltext: '全文', abstract: '摘要', title: '标题' }
const PROXIMITY_LABEL: Record<string, string> = {
  same_sentence: 'Same sentence',
  adjacent_sentence: 'Adjacent sentence',
  same_paragraph: 'Same paragraph',
  same_section: 'Same section',
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export function AiReviewStage({ rankingId, connectionType, onBackToScreen, onNextStep4 }: {
  rankingId: string
  connectionType: string
  onBackToScreen: () => void
  onNextStep4: () => void
}) {
  const [segments, setSegments] = useState<PewSegment[]>([])
  const [reviews, setReviews] = useState<PewReviewItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number }>({ done: 0, total: 0 })
  const [summary, setSummary] = useState<{ byDecision: Record<string, number>; failed: number; tokens: number; model: string | null } | null>(null)
  const [evTab, setEvTab] = useState<EvidenceTab>('all')
  const [lvTab, setLvTab] = useState<LevelTab>('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const [rawOpen, setRawOpen] = useState<{ id: string; kind: 'raw' | 'prompt' } | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [step4Hint, setStep4Hint] = useState(false)

  const load = useCallback(async () => {
    try {
      const [sr, rr] = await Promise.all([pewListSegments(rankingId), pewListReviews(rankingId)])
      setSegments(sr.items)
      setReviews(rr.items)
    } catch (err) {
      setMsg(`审核数据加载失败:${errText(err)}`)
    } finally {
      setLoaded(true)
    }
  }, [rankingId])

  useEffect(() => { void load() }, [load])

  // 未审核 segment_ids(同 prompt_version 已审由后端跳过;前端亦不发已审的)
  const pendingSegments = useMemo(
    () => segments.filter(s => s.decision == null).map(s => s.segment_id),
    [segments],
  )

  const reviewCounts = useMemo(() => {
    const c: Record<string, number> = { supported: 0, partial_support: 0, uncertain: 0, not_supported: 0 }
    let failed = 0
    for (const r of reviews) {
      if (r.failed) failed += 1
      else c[r.decision] += 1
    }
    return {
      supported: c.supported,
      partial_support: c.partial_support,
      uncertain: c.uncertain,
      not_supported: c.not_supported,
      failed,
    }
  }, [reviews])

  const listLoaded = summary != null || (loaded && pendingSegments.length === 0)

  const runReview = useCallback(async (force = false) => {
    if (running) return
    const targets = force ? segments.map(s => s.segment_id) : pendingSegments
    if (targets.length === 0) return
    setRunning(true)
    setMsg(null)
    setProgress({ done: 0, total: targets.length })
    // 分批提交(每批 24,便于进度展示;后端单条 retry+失败记录)
    const acc: Record<string, number> = { supported: 0, partial_support: 0, uncertain: 0, not_supported: 0 }
    let failed = 0
    let tokens = 0
    let model: string | null = null
    let lastSummary: Awaited<ReturnType<typeof pewRunReviews>>['summary'] | null = null
    try {
      for (let i = 0; i < targets.length; i += 24) {
        const chunk = targets.slice(i, i + 24)
        const r = await pewRunReviews(rankingId, chunk, connectionType, force)
        lastSummary = r.summary
        model = r.model ?? model
        for (const x of r.results) {
          if (x.failed) failed += 1
          else acc[x.decision] = (acc[x.decision] ?? 0) + 1
        }
        tokens += r.summary.total_tokens.total_tokens
        setProgress({ done: Math.min(i + chunk.length, targets.length), total: targets.length })
        await load()
        notifyTaskReviewsChanged(rankingId)
      }
      setSummary({ byDecision: { ...acc }, failed, tokens, model })
      setMsg('AI语义审核完成')
    } catch (err) {
      setMsg(`AI 语义审核失败:${errText(err)}`)
    } finally {
      setRunning(false)
    }
  }, [running, segments, pendingSegments, rankingId, connectionType, load])

  // 单条重新审核(÷ 后端按新写入覆盖)
  const reReviewOne = useCallback(async (segmentId: string) => {
    setMenuOpenId(null)
    try {
      await pewRunReviews(rankingId, [segmentId], connectionType, true)
      await load()
      notifyTaskReviewsChanged(rankingId)
      setMsg(null)
    } catch (err) {
      setMsg(`重新审核失败:${errText(err)}`)
    }
  }, [rankingId, connectionType, load])

  const reviewOf = (segmentId: string): PewReviewItem | undefined =>
    reviews.find(r => r.segment_id === segmentId)

  const visible = useMemo(() => {
    const withReview = segments.map(s => ({ s, r: reviewOf(s.segment_id) }))
    return withReview.filter(({ s, r }) => {
      if (evTab !== 'all' && (r?.decision ?? null) !== evTab) return false
      if (lvTab !== 'all' && s.candidate_level !== lvTab) return false
      return true
    })
  }, [segments, reviews, evTab, lvTab])

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0

  return (
    <div className="edw-stage" data-testid="edw-stage-3">
      <div className="edw-stage-head">
        <h3 className="edw-stage-title">AI 语义审核</h3>
        <p className="edw-stage-desc">
          DeepSeek 将仅根据论文原文及上下文判断疑似片段是否真正支持当前知识事实。AI 不负责搜索论文,也不会生成证据。
        </p>
      </div>

      <div className="edw-querybar">
        <button type="button" className="btn" disabled={running} data-testid="edw-back-to-screen-btn" onClick={onBackToScreen}>
          返回片段筛选
        </button>
        <button type="button" className="btn" disabled={running} data-testid="edw-run-review-btn" onClick={() => void runReview(pendingSegments.length === 0)}>
          {running ? 'AI语义审核中…' : pendingSegments.length === 0 ? '重新AI审核' : '开始 AI 语义审核'}
        </button>
        <span style={{ flex: 1 }} />
        <button type="button" className="btn btn-primary" data-testid="edw-next-stage4-btn" onClick={onNextStep4}>
          下一步:候选证据
        </button>
        <span className="edw-muted-hint">
          批量审核({pendingSegments.length} 条未审) · 同版本已审直接复用(0 调用) · 并发 5 · 单条失败不中断
        </span>
      </div>

      {msg && <div className="edw-feedback" data-testid="edw-review-msg">{msg}</div>}

      {/* 刷新/再次进入:已全部审核 → 直接恢复,不自动调用模型 */}
      {loaded && !running && pendingSegments.length === 0 && reviews.length > 0 && !summary && (
        <div className="edw-feedback" data-testid="edw-review-done">
          AI语义审核已完成 {reviews.length} / {segments.length} · 进入页面零模型调用;如需重新判定请使用「重新AI审核」。
        </div>
      )}

      {/* 顶部统计 */}
      <div className="edw-stats edw-stats-results" data-testid="edw-review-stats">
        <div className="edw-stat"><div className="edw-stat-value">{pendingSegments.length}</div><div className="edw-stat-label">待审核</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{reviews.length}</div><div className="edw-stat-label">已审核</div></div>
        <div className="edw-stat"><div className="edw-stat-value edw-stat-created">{reviewCounts.supported}</div><div className="edw-stat-label">Supported</div></div>
        <div className="edw-stat"><div className="edw-stat-value edw-stat-warn">{reviewCounts.partial_support}</div><div className="edw-stat-label">Partial</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{reviewCounts.uncertain}</div><div className="edw-stat-label">Uncertain</div></div>
        <div className="edw-stat"><div className="edw-stat-value edw-stat-bad">{reviewCounts.not_supported}</div><div className="edw-stat-label">Not Supported</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{reviewCounts.failed}</div><div className="edw-stat-label">Failed</div></div>
      </div>

      {/* 进度(运行中) */}
      {running && (
        <div className="edw-screen-progress" data-testid="edw-review-progress">
          <span>AI语义审核中 {progress.done} / {progress.total}</span>
          <span className="edw-progress-bar"><span className="edw-progress-fill" style={{ width: `${pct}%` }} /></span>
          <span>Supported {reviewCounts.supported}</span>
          <span>Partial {reviewCounts.partial_support}</span>
          <span>Uncertain {reviewCounts.uncertain}</span>
          <span>Not Supported {reviewCounts.not_supported}</span>
          <span>Failed {reviewCounts.failed}</span>
        </div>
      )}
      {summary && !running && (
        <div className="edw-feedback" data-testid="edw-review-summary">
          AI语义审核完成 · Supported {summary.byDecision.supported ?? 0} · Partial {summary.byDecision.partial_support ?? 0}
          {' '}· Uncertain {summary.byDecision.uncertain ?? 0} · Not Supported {summary.byDecision.not_supported ?? 0}
          {summary.failed > 0 ? ` · Failed ${summary.failed}` : ''}
          {' '}· 当前模型:{summary.model ?? '—'} · tokens ≈ {summary.tokens}
        </div>
      )}

      {/* 筛选:证据维度 + 等级维度(可组合) */}
      <div className="edw-lvl-tabs" data-testid="edw-review-tabs">
        {(['all', 'supported', 'partial_support', 'uncertain', 'not_supported'] as EvidenceTab[]).map(t => (
          <button key={t} type="button" className={`btn btn-sm ${evTab === t ? 'btn-primary' : ''}`} data-testid={`edw-evtab-${t}`} onClick={() => setEvTab(t)}>
            {t === 'all' ? `全部(${segments.length})` : `${DECISION_LABEL[t]}(${reviewCounts[t]})`}
          </button>
        ))}
      </div>
      <div className="edw-lvl-tabs" data-testid="edw-review-level-tabs">
        {(['all', 'strong', 'medium', 'weak'] as LevelTab[]).map(t => (
          <button key={t} type="button" className={`btn btn-sm ${lvTab === t ? 'btn-primary' : ''}`} data-testid={`edw-lvtab-${t}`} onClick={() => setLvTab(t)}>
            {t === 'all' ? '全部等级' : `${t[0].toUpperCase()}${t.slice(1)}`}
          </button>
        ))}
      </div>

      {/* 片段卡(复用 Step2 卡片 + AI Review 区) */}
      {segments.length > 0 && (
        <div className="edw-frag-list" data-testid="edw-review-list">
          {visible.map(({ s, r }) => {
            const tone = r && !r.failed ? DECISION_TONE[r.decision] : 'edw-dec-uncertain'
            return (
              <div className={`edw-frag-card ${tone}`} key={s.segment_id} data-testid={`edw-review-${s.segment_id}`}>
                <div className="edw-frag-head">
                  <span className="edw-frag-title">{s.paper_title || '(未命名)'}</span>
                  <span className="edw-badge edw-badge-content">{s.candidate_level ?? '—'}</span>
                  {r && !r.failed && (
                    <span className={`edw-dec-badge ${tone}`} data-testid={`edw-dec-${s.segment_id}`}>
                      {DECISION_LABEL[r.decision]}
                      {r.confidence != null ? ` ${Math.round(r.confidence * 100)}%` : ''}
                    </span>
                  )}
                  {r?.failed && <span className="edw-dec-badge edw-dec-failed">FAILED</span>}
                  <span style={{ flex: 1 }} />
                  <div className="edw-menu-wrap">
                    <button type="button" className="btn btn-sm edw-card-menu-btn" data-testid={`edw-review-menu-${s.segment_id}`}
                      onClick={() => setMenuOpenId(prev => prev === s.segment_id ? null : s.segment_id)}>
                      ⋯
                    </button>
                    {menuOpenId === s.segment_id && (
                      <div className="edw-menu" data-testid={`edw-review-menu-list-${s.segment_id}`} onClick={() => setMenuOpenId(null)}>
                        <button type="button" className="edw-menu-item" data-testid={`edw-re-review-${s.segment_id}`} onClick={() => void reReviewOne(s.segment_id)}>
                          重新 AI 审核
                        </button>
                        <button type="button" className="edw-menu-item" data-testid={`edw-view-raw-${s.segment_id}`} onClick={() => setRawOpen({ id: s.segment_id, kind: 'raw' })}>
                          查看原始模型响应
                        </button>
                        <button type="button" className="edw-menu-item" data-testid={`edw-view-prompt-${s.segment_id}`} onClick={() => setRawOpen({ id: s.segment_id, kind: 'prompt' })}>
                          查看 Prompt
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                <div className="edw-muted-hint">
                  PMID {s.paper_pmid || '—'}{s.paper_doi ? ` · DOI ${s.paper_doi}` : ''} · Section {s.section || '—'}
                </div>
                <p className="edw-frag-sentence">{s.sentence}</p>

                {/* AI Review 区 */}
                {r && (
                  <div className="edw-ai-review" data-testid={`edw-ai-review-${s.segment_id}`}>
                    {!r.failed && (
                      <>
                        <div className="edw-ai-row"><span>Evidence Type:</span>
                          <b>{r.evidence_type ?? '—'}</b></div>
                        <div className="edw-ai-row"><span>Direction:</span>
                          <b>{r.direction_support ?? '—'}</b></div>
                        <div className="edw-ai-row"><span>Connection Type (supported):</span>
                          <b>{r.connection_type_supported ?? '—'}</b></div>
                        <div className="edw-ai-row"><span>Reason:</span>
                          <span>{r.reason || '—'}</span></div>
                        {r.contradiction_reason && (
                          <div className="edw-ai-row"><span>Contradiction:</span>
                            <span>{r.contradiction_reason}</span></div>
                        )}
                        {r.decision === 'supported' && r.supporting_phrase && (
                          <div className="edw-ai-row"><span>Supporting Phrase:</span>
                            <span style={{ fontStyle: 'italic' }}>“{r.supporting_phrase}”</span></div>
                        )}
                      </>
                    )}
                    {r.failed && <div className="edw-ai-row"><span>Failed:</span><span>{r.reason || 'transient'}</span></div>}
                  </div>
                )}

                {rawOpen?.id === s.segment_id && (
                  <pre className="edw-raw-pre" data-testid="edw-raw-pre">
                    {rawOpen.kind === 'raw'
                      ? JSON.stringify({ parsed: { decision: r?.decision, confidence: r?.confidence, evidence_type: r?.evidence_type, reason: r?.reason, connection_type_supported: r?.connection_type_supported, direction_support: r?.direction_support, supporting_phrase: r?.supporting_phrase, contradiction_reason: r?.contradiction_reason } }, null, 2)
                      : `[stage3 prompt: stage3_v1]\nSYSTEM 原则见服务端 REVIEW_SYSTEM(仅依据原文/ROI枚举≠连接/不臆测方向/支持短语必须原文)\nUSER 事实+论文元数据+局部上下文+检索信号`}
                  </pre>
                )}

                {expanded.has(s.segment_id) && (
                  <div className="edw-frag-context">
                    {s.context_before && <p className="edw-muted-hint">上一句:{s.context_before}</p>}
                    {s.context_after && <p className="edw-muted-hint">下一句:{s.context_after}</p>}
                  </div>
                )}
                <div className="edw-frag-tags">
                  <span className="edw-chip">Source ✓ {s.matched_source ?? '—'}</span>
                  <span className="edw-chip">Target ✓ {s.matched_target ?? '—'}</span>
                  {(s.relation_terms ?? []).slice(0, 3).map(w => <span className="edw-chip" key={w}>{w}</span>)}
                  <span className="edw-chip">{PROXIMITY_LABEL[s.proximity] ?? s.proximity}</span>
                  <span className="edw-chip">{SOURCE_LABEL[s.source_type] ?? s.source_type}</span>
                  <span className="edw-chip">Rule Score {s.rule_score != null ? s.rule_score.toFixed(2) : '—'}</span>
                </div>
                <div className="edw-frag-actions">
                  <button type="button" className="btn btn-sm" data-testid={`edw-review-toggle-${s.segment_id}`} onClick={() => toggleExpand(s.segment_id)}>
                    {expanded.has(s.segment_id) ? '收起上下文' : '查看上下文'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {loaded && segments.length === 0 && (
        <div className="edw-noresult">
          <p className="edw-noresult-title">当前任务无疑似片段,请先完成 Step 2 片段筛选。</p>
        </div>
      )}

      {/* 完成 → Step 4 占位 */}
      {!running && pendingSegments.length === 0 && reviews.length > 0 && (
        <div className="edw-papers-head" style={{ marginTop: 12 }}>
          <span style={{ flex: 1 }} />
          <button type="button" className="btn btn-sm btn-primary" data-testid="edw-next-step4-btn" onClick={() => setStep4Hint(h => !h)}>
            下一步:候选证据
          </button>
        </div>
      )}
      {step4Hint && (
        <p className="edw-muted-hint" data-testid="edw-step4-hint" style={{ marginTop: 6 }}>
          Evidence Candidate 正式整理在 Step 4 实现(本轮不生成;当前仅完成 AI 语义判定)。
        </p>
      )}
    </div>
  )
}
