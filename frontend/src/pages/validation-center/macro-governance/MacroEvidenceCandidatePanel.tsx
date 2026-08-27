import { useEffect, useState } from 'react'
import {
  getEvidenceTarget,
  type EvidenceTargetDto,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../../evidence-center/EvidenceCenterContext'
import {
  MacroCandidateSection,
} from './MacroGovernanceIntegration'

export const MACRO_EVIDENCE_TARGET_TYPES = new Set([
  'existing_connection_evidence',
  'macro_connection_candidate',
  'macro_candidate_connection',
  'macro_candidate_evidence',
])

/**
 * 证据候选页的 Macro 治理分支：
 * Macro 对象(ranking_id)无任务 item 派生,直接展示 DTO 组装数据。
 *   ① Macro Candidate 信息(strip + 规则/AI 详情,复用 MacroCandidateSection)
 *   ② 论文证据片段(ranking → candidate_pair_ids → pair → paper;标题/PMID/section/原文句)
 *   ③ 「进入人工审核」按钮(唯一 target_id = ranking_id;推进后可复用 buildReview 链路)
 * 无证据片段 → 明确空态文案,不显示空白。
 */
export function MacroEvidenceCandidatePanel({ targetType, targetId }: {
  targetType: string
  targetId: string | null
}) {
  const { openTarget } = useEvidenceCenter()
  const [dto, setDto] = useState<EvidenceTargetDto | null>(null)
  const [loadState, setLoadState] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')

  useEffect(() => {
    if (!targetId) return
    let cancelled = false
    setLoadState('loading')
    getEvidenceTarget(targetType, targetId)
      .then(d => { if (!cancelled) { setDto(d); setLoadState('ok') } })
      .catch(() => { if (!cancelled) setLoadState('error') })
    return () => { cancelled = true }
  }, [targetType, targetId])

  const papers = dto?.evidence_papers ?? []
  const aiDecision = dto?.ai_decision ?? null
  // 进入人工审核门禁:Rule PASS(或已有判定)+ AI != NOT_SUPPORTED
  const rulePassed = dto?.rule_status === 'PASS'
  const aiBlocked = aiDecision === 'not_supported'
  const canEnterReview = targetId != null && !aiBlocked

  return (
    <div data-testid="macro-evidence-panel">
      {loadState === 'loading' && <p className="evidence-module-hint">加载 Macro 候选数据…</p>}
      {loadState === 'error' && (
        <div className="evidence-task-error" data-testid="macro-panel-error">
          <p>Macro 候选数据加载失败,请重试。</p>
        </div>
      )}

      {dto && (
        <>
          {/* ① Macro Candidate 信息(strip + 详情:规则/AI/时间线;canonical id 匹配) */}
          <MacroCandidateSection
            targetId={targetId ?? ''}
            sourceName={dto.source_region}
            targetName={dto.target_region}
            sourceCanonicalId={dto.source_region_canonical_id}
            targetCanonicalId={dto.target_region_canonical_id}
          />

          {/* ② 论文证据片段 */}
          <div className="govw-card" data-testid="macro-evidence-papers">
            <h5>Evidence(论文证据片段)</h5>
            {papers.length === 0 ? (
              <p className="govw-muted" data-testid="macro-evidence-empty">
                该候选暂无可审核证据(论文共现句未落库)。
              </p>
            ) : (
              papers.map((p, i) => (
                <div key={`${p.pmid}-${i}`} className="govw-evidence-item">
                  <div className="govw-ai-row" style={{ gridTemplateColumns: '88px 1fr' }}>
                    <span>论文</span><b>{p.paper_title ?? '—'}</b>
                  </div>
                  <div className="govw-ai-row" style={{ gridTemplateColumns: '88px 1fr' }}>
                    <span>PMID</span><span>{p.pmid ?? '—'}</span>
                  </div>
                  <div className="govw-ai-row" style={{ gridTemplateColumns: '88px 1fr' }}>
                    <span>section</span><span>{p.section ?? '—'}</span>
                  </div>
                  <p className="govw-evidence-sentence">{p.sentence ?? '—'}</p>
                </div>
              ))
            )}
          </div>

          {/* ③ 进入人工审核 */}
          <div className="govw-card" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ flex: 1, fontSize: 12.5 }}>
              {dto.ai_decision && (
                <span>
                  AI judgement: <b>{dto.ai_decision}</b>
                  {dto.ai_confidence != null ? `(${Math.round(dto.ai_confidence * 100)}%)` : ''}
                  {dto.ai_model ? ` · ${dto.ai_model}` : ''}
                </span>
              )}
              {dto.ai_reasoning && <span className="govw-muted"> — {dto.ai_reasoning}</span>}
            </div>
            {canEnterReview ? (
              <button
                type="button" className="btn btn-sm btn-primary" data-testid="macro-enter-review"
                onClick={() => openTarget(targetType, targetId!, 'review')}
              >
                进入人工审核
              </button>
            ) : (
              <span className="govw-muted" data-testid="macro-enter-review-blocked">
                {rulePassed ? 'AI NOT_SUPPORTED 禁止进入人工审核' : '规则未 PASS,禁止进入人工审核'}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  )
}
