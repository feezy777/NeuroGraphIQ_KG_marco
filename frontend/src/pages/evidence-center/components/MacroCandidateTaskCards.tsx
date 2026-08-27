import { useEffect, useState } from 'react'
import {
  listMacroCandidateReviewQueue,
  type MacroReviewQueueItem,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'

const AI_LABEL: Record<string, string> = {
  supported: 'SUPPORTED',
  uncertain: 'UNCERTAIN',
  not_supported: 'NOT_SUPPORTED',
}

/**
 * 佐证任务页新增「Macro 治理候选」任务来源(Phase 闭环)：
 * 原任务卡片布局不变,本组件作为独立分组追加在任务卡网格下方。
 *
 * 数据链(全部已有产物,只读):
 *   paper_connection_candidate_rankings + rule results + LLM reviews
 *   → review-queue(kind=enhancement | novel)
 *   → target_id = ranking_id(唯一,禁止名称匹配)
 * 「继续验证」→ openTarget → 证据候选 → 人工审核。
 */
export function MacroCandidateTaskCards() {
  const { openTarget, state } = useEvidenceCenter()
  const [items, setItems] = useState<MacroReviewQueueItem[]>([])

  /** 安全拉取队列(API 未定义/失败 → null;绝不向调用方抛错,不影响任务页) */
  const safeQueue = (kind: 'enhancement' | 'novel') => new Promise<Awaited<ReturnType<typeof listMacroCandidateReviewQueue>> | null>(
    resolve => {
      Promise.resolve()
        .then(() => listMacroCandidateReviewQueue(kind))
        .then(r => resolve(r), () => resolve(null))
    },
  )

  useEffect(() => {
    let cancelled = false
    Promise.all([safeQueue('enhancement'), safeQueue('novel')]).then(([en, no]) => {
      if (cancelled) return
      const merged = [
        ...(en?.items ?? []).map(it => ({ ...it, kind: 'enhancement' as const })),
        ...(no?.items ?? []).map(it => ({ ...it, kind: 'novel' as const })),
      ]
      merged.sort((a, b) => (a.kind === b.kind ? 0 : a.kind === 'enhancement' ? -1 : 1))
      setItems(merged)
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleContinue = (item: MacroReviewQueueItem) => {
    // 唯一 target_id = ranking_id(禁止名称匹配);直接进入证据候选视图
    openTarget(item.target_type, item.target_id, 'candidates')
  }

  if (items.length === 0) return null

  return (
    <div className="evidence-macro-task-group" data-testid="macro-task-cards">
      <div className="evidence-task-group-head">
        <span className="evidence-promotion-group-title">Macro 治理候选(证据增强 / 新增连接)</span>
        <span className="evidence-promotion-group-count">{items.length}</span>
      </div>
      <div className="evidence-task-card-grid">
        {items.map(item => (
          <div
            key={`${item.kind}-${item.target_id}`}
            className={`evidence-task-card evidence-task-card-clickable${
              state.targetType === item.target_type && state.targetId === item.target_id
                ? ' evidence-task-card-selected' : ''}`}
            data-testid={`macro-task-card-${item.target_id.slice(0, 8)}`}
            onClick={() => handleContinue(item)}
          >
            <div className="evidence-task-card-head">
              <span className="evidence-task-card-title">{item.label}</span>
              <span className="evidence-task-card-type">
                {item.kind === 'enhancement' ? '已有连接证据增强' : '新增连接候选'}
              </span>
            </div>
            <div className="evidence-task-card-meta">
              <span>Connection type: <b>{item.ai_connection_type ?? '—'}</b></span>
              <span>Ranking score: <b>{item.ranking_score != null ? item.ranking_score.toFixed(1) : '—'}</b></span>
              <span>Supporting papers: <b>{item.evidenceCount}</b></span>
              <span>AI review: <b>{item.ai_decision ? AI_LABEL[item.ai_decision] ?? item.ai_decision : '—'}</b></span>
              <span>Rule validation: <b>{item.rule_status ?? '—'}</b></span>
            </div>
            <div className="evidence-task-card-actions">
              <button
                type="button" className="btn btn-xs btn-primary"
                data-testid={`macro-task-continue-${item.target_id.slice(0, 8)}`}
                onClick={e => { e.stopPropagation(); handleContinue(item) }}
              >
                继续验证
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
