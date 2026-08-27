import { useMemo, useState } from 'react'
import type { EvidenceTargetDto } from '../../../api/endpoints'
import {
  AiReviewCard,
  GovernanceTimeline,
  MacroCandidateStrip,
  MacroStatusBadge,
  RuleValidationCard,
} from './MacroGovernanceCards'
import {
  saveWorkflowRollback,
  type WorkflowRollbackRecord,
} from './macroWorkflow'
import { useMacroCandidates, useMacroViewForEvidence, type MacroCandidateView } from './useMacroCandidates'

// ---- 证据候选模块:Strip 上下文 + 展开详情(规则验证/AI 审核/时间线/回退) ----

export function MacroCandidateSection({ targetId, sourceName, targetName, sourceCanonicalId, targetCanonicalId }: {
  targetId: string
  sourceName: string | null | undefined
  targetName: string | null | undefined
  sourceCanonicalId: string | null | undefined
  targetCanonicalId: string | null | undefined
}) {
  const view = useMacroViewForEvidence(targetId, sourceName, targetName, sourceCanonicalId, targetCanonicalId)
  const [expanded, setExpanded] = useState(false)

  if (!view) return null

  return (
    <div data-testid="govw-section">
      <MacroCandidateStrip
        view={view}
        targetId={targetId}
        onOpenDetail={() => setExpanded(true)}
      />
      {expanded && <MacroDetailExpanded view={view} onClose={() => setExpanded(false)} />}
    </div>
  )
}

/** 展开详情:规则卡 + AI 卡 + 时间线 + 回退操作 */
export function MacroDetailExpanded({ view, onClose }: { view: MacroCandidateView; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const [rolledBack, setRolledBack] = useState(false)
  const [reviewHint, setReviewHint] = useState(false)
  const { refresh } = useMacroCandidates()

  const canRollback = view.status !== 'rollback'
  // 进入人工审核门禁:Rule PASS + AI review != NOT_SUPPORTED
  const rulePassed = Boolean(view.ruleResult?.passed && !view.ruleResult?.blocked)
  const aiNotSupported = view.review?.decision === 'not_supported'
  const canEnterHumanReview = rulePassed && !aiNotSupported

  const handleRollback = () => {
    if (!reason.trim()) return
    const rec: WorkflowRollbackRecord = {
      targetId: view.ranking?.target_region_id ?? view.key,
      reason: reason.trim(),
      actor: 'admin',
      at: new Date().toISOString(),
      from: view.status,
    }
    saveWorkflowRollback(rec)
    setReason('')
    setRolledBack(true)
    refresh()
  }

  return (
    <div className="govw-detail" data-testid="govw-detail">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <b style={{ fontSize: 13.5 }}>Macro 候选连接详细</b>
        <MacroStatusBadge status={view.status} />
        <span style={{ flex: 1 }} />
        {canEnterHumanReview && (
          <button
            type="button" className="btn btn-sm btn-primary" data-testid="govw-enter-review"
            onClick={() => setReviewHint(true)}
          >
            进入人工审核
          </button>
        )}
        <button type="button" className="btn btn-sm" data-testid="govw-close-detail" onClick={onClose}>收起</button>
      </div>
      {reviewHint && (
        <div className="ontology-page-message" data-testid="govw-review-hint">
          门禁通过(Rule PASS + AI 非 NOT_SUPPORTED)✦ 人工审核入口将在下一阶段接入现有
          「人工审核」页(本阶段仅建立规则层,未进入审核)。
        </div>
      )}
      {!canEnterHumanReview && (
        <div className="govw-muted" style={{ marginBottom: 8 }}>
          进入人工审核条件: Rule PASS{!rulePassed ? '(规则未通过)' : ''}
          {aiNotSupported ? ' + AI decision = NOT_SUPPORTED 禁止进入' : ''}
        </div>
      )}
      <RuleValidationCard view={view} />
      <AiReviewCard review={view.review} />
      <GovernanceTimeline view={view} targetId={view.ranking?.target_region_id ?? ''} />
      {canRollback && (
        <div className="govw-card">
          <h5>Rollback(回退)</h5>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <input
              className="filter-input"
              style={{ flex: 1 }}
              placeholder="回退原因(必填)"
              value={reason}
              onChange={e => setReason(e.target.value)}
              aria-label="回退原因"
            />
            <button
              type="button" className="btn btn-sm btn-primary"
              disabled={!reason.trim()}
              data-testid="govw-rollback-btn"
              onClick={handleRollback}
            >
              回退
            </button>
          </div>
          <p className="govw-muted" style={{ margin: '6px 0 0' }}>
            回退仅追加 rollback 记录(原因/操作者/时间),不覆盖既有审核记录;流程回到「待人工审核」重评。
          </p>
          {rolledBack && <p className="govw-pass" data-testid="govw-rolledback-hint">已回退 ✓</p>}
        </div>
      )}
    </div>
  )
}

// ---- 人工审核模块:上下文条(规则 + AI 意见 + 论文证据片段;不改现有审核交互) ----

export function MacroReviewContext({ targetId, sourceName, targetName, sourceCanonicalId, targetCanonicalId, dto }: {
  targetId: string
  sourceName: string | null | undefined
  targetName: string | null | undefined
  sourceCanonicalId: string | null | undefined
  targetCanonicalId: string | null | undefined
  /** 权威 DTO(build_target_dto 响应):evidence_papers/AI/rule 直接从后端来 */
  dto: EvidenceTargetDto | null | undefined
}) {
  const view = useMacroViewForEvidence(targetId, sourceName, targetName, sourceCanonicalId, targetCanonicalId)
  const [rawOpen, setRawOpen] = useState(false)
  // 无 view(未匹配 ranking)且无 DTO → 不占用空间
  if (!view && !(dto?.review_kind || dto?.evidence_papers?.length)) return null
  const review = view?.review ?? null
  const aiDecision = review?.decision ?? dto?.ai_decision ?? null
  const aiConfidence = review?.confidence ?? dto?.ai_confidence ?? null
  const aiReasoning = review?.reasoning ?? dto?.ai_reasoning ?? null
  const aiModel = review?.model_name ?? dto?.ai_model ?? null
  const evidencePapers = dto?.evidence_papers ?? []
  return (
    <div className="govw-review-context" data-testid="govw-review-context">
      <div className="govw-review-context-head">
        <b>{view?.sourceName ?? dto?.source_region} → {view?.targetName ?? dto?.target_region}</b>
        <span className="govw-muted">Macro 候选上下文(供裁决参考)</span>
      </div>
      <div style={{ display: 'grid', gap: 8 }}>
        <div>
          <b style={{ fontSize: 12 }}>规则验证:</b>
          {view?.ruleResult ? (
            <span className={view.ruleResult.passed ? 'govw-pass' : 'govw-fail'}>
              {view.ruleResult.passed ? 'PASS' : 'FAIL'} ({view.ruleResult.rules.filter(r => r.passed).length}/{view.ruleResult.rules.length})
            </span>
          ) : (
            <span className="govw-muted">{dto?.rule_status ?? '—'}</span>
          )}
        </div>
        <div>
          <b style={{ fontSize: 12 }}>AI 科学审核:</b>
          {aiDecision ? (
            <>
              <span className="govw-chip">{aiModel ?? '—'}</span>
              <span className={`govw-status ${
                aiDecision === 'supported' ? 'govw-status-ok'
                  : aiDecision === 'uncertain' ? 'govw-status-warn' : 'govw-status-bad'}`}>
                {aiDecision}
              </span>
              <span className="govw-muted"> 置信 {aiConfidence != null ? Math.round(aiConfidence * 100) : '—'}%</span>
              <button
                type="button" className="govw-raw-toggle" data-testid="govw-review-raw-toggle"
                onClick={() => setRawOpen(o => !o)}
              >
                {rawOpen ? '收起' : 'reason'}
              </button>
              <p className="govw-muted" style={{ margin: '4px 0 0' }}>{aiReasoning || '—'}</p>
            </>
          ) : (
            <span className="govw-muted">暂无可展示结果(规则通过后进入 AI 审核)</span>
          )}
        </div>
        <div>
          <b style={{ fontSize: 12 }}>论文证据片段:</b>
          {evidencePapers.length === 0 ? (
            <span className="govw-muted" data-testid="macro-review-evidence-empty">
              该候选暂无可审核证据
            </span>
          ) : (
            evidencePapers.map((p, i) => (
              <div key={`${p.pmid}-${i}`} className="govw-evidence-item">
                <div className="govw-rule-detail">
                  <b>论文</b> {p.paper_title ?? '—'} · PMID {p.pmid ?? '—'}
                  {p.section ? ` · section ${p.section}` : ''}
                </div>
                <p className="govw-evidence-sentence">{p.sentence ?? '—'}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

// ---- 晋升模块:晋升条件门禁(Rule PASS + Human Approved + Evidence 存在) ----

export function MacroPromotionGate({ targetId, sourceName, targetName, sourceCanonicalId, targetCanonicalId, evidenceCount }: {
  targetId: string
  sourceName: string | null | undefined
  targetName: string | null | undefined
  sourceCanonicalId: string | null | undefined
  targetCanonicalId: string | null | undefined
  evidenceCount: number
}) {
  const view = useMacroViewForEvidence(targetId, sourceName, targetName, sourceCanonicalId, targetCanonicalId)
  const items = useMemo(() => {
    if (!view) return null
    return [
      { label: 'Rule PASS', ok: Boolean(view.ruleResult?.passed) },
      { label: 'Human Approved', ok: view.status === 'promotion_ready' || view.status === 'promoted' },
      { label: 'Evidence 存在', ok: evidenceCount > 0 },
    ] as const
  }, [view, evidenceCount])

  if (!items) return null
  const allOk = items.every(i => i.ok)
  return (
    <div className="govw-gate" data-testid="govw-promotion-gate">
      {items.map(item => (
        <span key={item.label} className="govw-gate-item">
          {item.ok ? '✓' : '✗'}
          <b>{item.label}</b>
          <span className={item.ok ? 'govw-pass' : 'govw-fail'}>{item.ok ? '通过' : '未通过'}</span>
        </span>
      ))}
      {!allOk && <span className="govw-muted">晋升条件未全部满足,请处理后重试。</span>}
    </div>
  )
}

/** 供 EvidenceCandidatesModule 的 dto.source_region/target_region 使用 */
export function useMacroPlainList() {
  return useMacroCandidates().candidates
}
