import { useState } from 'react'
import { WORKFLOW_LABEL, WORKFLOW_TONE, type MacroWorkflowStatus } from './macroWorkflow'
import type { MacroCandidateReviewItem } from '../../../api/endpoints'
import type { MacroCandidateView } from './useMacroCandidates'
import './macroGovernance.css'

export function workflowClass(status: MacroWorkflowStatus): string {
  return `govw-status-${WORKFLOW_TONE[status]}`
}

/** 状态徽章(证据候选列表 / Strip 通用) */
export function MacroStatusBadge({ status }: { status: MacroWorkflowStatus }) {
  return (
    <span className={`govw-status ${workflowClass(status)}`} data-testid="govw-status">
      {WORKFLOW_LABEL[status]}
    </span>
  )
}

// ---- 规则验证卡片 ----

const RULE_NAME: Record<string, string> = {
  R1: 'region 存在性',
  R2: 'source != target',
  R3: 'connection_type 合法性',
  R4: 'direction 合法性',
  R5: 'duplicate 检查',
  R6: 'hierarchy 检查',
}

export function RuleValidationCard({ view }: { view: MacroCandidateView }) {
  const result = view.ruleResult
  if (!result) {
    return (
      <div className="govw-card" data-testid="govw-rule-card">
        <h5>Rule Validation</h5>
        <p className="govw-muted">规则检查待运行(pending_rule)</p>
      </div>
    )
  }
  const dup = result.duplicate_existing as Record<string, unknown> | null | undefined
  return (
    <div className="govw-card" data-testid="govw-rule-card">
      <h5>
        Rule Validation
        {result.blocked ? (
          <span className="govw-blocked">BLOCKED</span>
        ) : (
          <span className={result.passed ? 'govw-pass' : 'govw-fail'}>
            {result.passed ? 'PASS' : 'FAIL'}
          </span>
        )}
      </h5>
      <div className="govw-rule-grid">
        {result.rules.map(rule => (
          <div key={rule.code} className={`govw-rule${rule.passed ? ' govw-rule-ok' : ' govw-rule-bad'}`}>
            <span className="govw-rule-code">{rule.code}</span>
            <div>
              <div className="govw-rule-name">
                {RULE_NAME[rule.code] ?? rule.name}
                <span className={rule.passed ? 'govw-pass' : 'govw-fail'}>
                  {rule.passed ? 'PASS' : rule.severity === 'block' ? 'FAIL(BLOCK)' : 'FAIL'}
                </span>
              </div>
              <div className="govw-rule-detail">{rule.detail}</div>
            </div>
          </div>
        ))}
      </div>
      {dup && Boolean(dup.final || dup.canonical || dup.mirror) && (
        <div className="govw-rule-detail" style={{ marginTop: 8 }}>
          duplicate_existing: final={String(dup.final)} · canonical={String(dup.canonical)}
          {' '}· mirror={String(dup.mirror)}
          {Array.isArray(dup.mirror_pairs) && dup.mirror_pairs.length > 0
            ? `(镜像连接 ${dup.mirror_pairs.length} 条样例)` : ''}
        </div>
      )}
    </div>
  )
}

// ---- AI 科学审核卡片 ----

const DECISION_LABEL = { supported: 'SUPPORTED', uncertain: 'UNCERTAIN', not_supported: 'NOT_SUPPORTED' } as const
const DECISION_TONE = { supported: 'ok', uncertain: 'warn', not_supported: 'bad' } as const

export function AiReviewCard({ review }: { review: MacroCandidateReviewItem | null }) {
  const [rawOpen, setRawOpen] = useState(false)
  const pct = review?.confidence != null ? Math.round(review.confidence * 100) : null
  return (
    <div className="govw-card" data-testid="govw-ai-card">
      <h5>AI Scientific Review</h5>
      {review ? (
        <>
          <div className="govw-ai-row">
            <span>模型</span>
            <strong>{review.model_name}</strong>
          </div>
          <div className="govw-ai-row">
            <span>Decision</span>
            <span className={`govw-status govw-status-${DECISION_TONE[review.decision]}`}>
              {DECISION_LABEL[review.decision]}
            </span>
          </div>
          <div className="govw-ai-row">
            <span>Confidence</span>
            <strong>{pct != null ? `${pct}%` : '—'}</strong>
          </div>
          <div className="govw-ai-row">
            <span>证据强度</span>
            <strong>{review.evidence_strength}</strong>
          </div>
          <div className="govw-ai-reason">
            <b>Reason</b>
            <p>{review.reasoning || '—'}</p>
          </div>
          <button
            type="button"
            className="govw-raw-toggle"
            data-testid="govw-raw-toggle"
            onClick={() => setRawOpen(o => !o)}
          >
            {rawOpen ? '收起原始 response' : '查看原始 response'}
          </button>
          {rawOpen && (
            <pre className="govw-raw-pre" data-testid="govw-raw-response">
              {JSON.stringify(review.raw_response_json, null, 2)}
            </pre>
          )}
        </>
      ) : (
        <p className="govw-muted">AI 科学审核待运行(进入人工审核前由系统补充)</p>
      )}
    </div>
  )
}

// ---- 审核历史时间线 ----

export function GovernanceTimeline({ view, targetId }: { view: MacroCandidateView; targetId: string }) {
  const { ranking, review } = view
  const created = ranking?.created_at ?? null
  return (
    <div className="govw-card" data-testid="govw-timeline">
      <h5>Review History</h5>
      <div className="govw-timeline">
        <div className="govw-tl-item">
          <span className="govw-tl-dot govw-tl-dot-neu" />
          <div>
            <b>创建候选</b>
            <div className="govw-tl-meta">论文发现 · {created ? new Date(created).toLocaleString('zh-CN', { hour12: false }) : '—'}</div>
            <div>{ranking ? `同论文共现(paper_count=${ranking.paper_count}, score=${ranking.score ?? '—'})` : ''}</div>
          </div>
        </div>
        <div className="govw-tl-item">
          <span className={`govw-tl-dot ${view.ruleResult?.passed ? 'govw-tl-dot-ok' : 'govw-tl-dot-bad'}`} />
          <div>
            <b>规则验证</b>
            <div className="govw-tl-meta">{view.ruleResult?.passed ? 'PASS' : 'FAIL'}(全部规则由当前数据派生)</div>
          </div>
        </div>
        {review ? (
          <div className="govw-tl-item">
            <span className={`govw-tl-dot ${
              review.decision === 'supported' ? 'govw-tl-dot-ok'
                : review.decision === 'uncertain' ? 'govw-tl-dot-warn' : 'govw-tl-dot-bad'}`} />
            <div>
              <b>AI 科学审核</b>
              <div className="govw-tl-meta">{review.model_name} · {review.created_at ? new Date(review.created_at).toLocaleString('zh-CN', { hour12: false }) : '—'}</div>
              <div>{review.reasoning || '—'}</div>
            </div>
          </div>
        ) : (
          <div className="govw-tl-item">
            <span className="govw-tl-dot govw-tl-dot-warn" />
            <div>
              <b>AI 科学审核(待运行)</b>
              <div className="govw-tl-meta">规则通过后进入</div>
            </div>
          </div>
        )}
        <div className="govw-tl-item">
          <span className={`govw-tl-dot ${
            view.status === 'approved' || view.status === 'promotion_ready' || view.status === 'promoted'
              ? 'govw-tl-dot-ok'
              : view.status === 'rejected' ? 'govw-tl-dot-bad' : 'govw-tl-dot-warn'}`} />
          <div>
            <b>人工审核</b>
            <div className="govw-tl-meta">裁决入口: 见「人工审核」页 · 状态 {WORKFLOW_LABEL[view.status]}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---- 证据候选页 Strip(连接/来源/评分/论文数/规则/AI/人工 状态行) ----

export const DECISION_LABEL_SHORT = { supported: 'SUPPORTED', uncertain: 'UNCERTAIN', not_supported: 'NOT_SUPPORTED' } as const

export function MacroCandidateStrip({ view, targetId, onOpenDetail }: {
  view: MacroCandidateView
  targetId: string
  onOpenDetail: (view: MacroCandidateView) => void
}) {
  return (
    <div className="govw-strip" data-testid="govw-strip">
      <div className="govw-strip-title">Macro Candidate</div>
      <div className="govw-strip-pair">
        <b>{view.sourceName}</b>
        <span className="govw-arrow">→</span>
        <b>{view.targetName}</b>
      </div>
      <span className="govw-chip">Paper Discovery</span>
      <span className="govw-strip-cell">Canonical: <b>{view.sourceName} → {view.targetName}</b></span>
      <span className="govw-strip-cell">Ranking score: <b>{view.rankScore?.toFixed(1) ?? '—'}</b></span>
      <span className="govw-strip-cell">Supporting papers: <b>{view.paperCount ?? '—'}</b></span>
      <span className="govw-strip-cell">规则 <b>{view.ruleResult?.passed ? 'PASS' : 'FAIL'}</b></span>
      <span className="govw-strip-cell">AI review: <b>{view.review ? DECISION_LABEL_SHORT[view.review.decision] : '待运行'}</b></span>
      {view.review && view.review.confidence != null && (
        <span className="govw-strip-cell">Confidence: <b>{Math.round(view.review.confidence * 100)}%</b></span>
      )}
      <span className="govw-strip-cell">人工 <b>{WORKFLOW_LABEL[view.status]}</b></span>
      <button type="button" className="btn btn-sm govw-detail-btn" data-testid="govw-open-detail" onClick={() => onOpenDetail(view)}>
        节点详情
      </button>
    </div>
  )
}
