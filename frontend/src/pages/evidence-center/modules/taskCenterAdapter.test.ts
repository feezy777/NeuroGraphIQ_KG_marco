/**
 * Task Center 统一适配器测试（纯函数）：
 * 1. 稳定身份：taskKey = evidence_task:{id} / macro_candidate:{ranking_id}
 * 2. 母集合正确：1129 rankings 全量（200 reviews 不决定任务数）
 * 3. 统计诚实：aiReviewed/aiPending/supported/uncertain/not_supported/rule 状态
 * 4. 筛选/分页（30/页）
 */
import { describe, expect, it } from 'vitest'
import {
  STAGE_LABELS,
  computeTaskCenterStats,
  filterTaskCenterItems,
  macroStageOf,
  mergeTaskCenterItems,
  paginateTaskCenterItems,
  toMacroCandidateItem,
  TASK_CENTER_PAGE_SIZE,
} from './taskCenterAdapter'
import type { MacroCandidateView } from '../../validation-center/macro-governance/useMacroCandidates'

function macroView(id: string, over: Partial<MacroCandidateView> = {}): MacroCandidateView {
  return {
    key: `pair:${id}`,
    ranking: {
      id,
      source_region_id: `s-${id}`,
      target_region_id: `t-${id}`,
      source_name: `Region ${id}`,
      target_name: `Target ${id}`,
      paper_count: 12,
      evidence_count: 30,
      score: 45.6,
      priority_level: 'A',
      created_at: '2026-08-25T00:00:00Z',
    } as MacroCandidateView['ranking'],
    detail: null,
    review: null,
    ruleResult: null,
    status: 'ai_review_pending',
    sourceName: `Region ${id}`,
    targetName: `Target ${id}`,
    paperCount: 12,
    rankScore: 45.6,
    reversePairExists: false,
    ...over,
  }
}

describe('taskCenterAdapter（统一任务中心）', () => {
  it('稳定身份：macroscope taskKey 只用 ranking_id,与名称无关', () => {
    const it = toMacroCandidateItem(macroView('rk-1'))
    expect(it.taskKey).toBe('macro_candidate:rk-1')
    expect(it.sourceId).toBe('rk-1')
  })

  it('母集合正确：1129 rankings 生成 1129 任务（200 reviews 是状态数据,非任务数）', () => {
    const rankings = Array.from({ length: 1129 }, (_, i) => macroView(`rk-${i}`))
    const withReview = rankings.map((v, i) => i < 200
      ? {
          ...v,
          review: { decision: i < 11 ? 'supported' : i < 14 ? 'uncertain' : 'not_supported' } as unknown as MacroCandidateView['review'],
          status: 'ai_supported' as const,
        }
      : v)
    const items = mergeTaskCenterItems([], withReview)
    expect(items.length).toBe(1129)
    const stats = computeTaskCenterStats(items)
    expect(stats.macroTotal).toBe(1129)
    expect(stats.aiReviewed).toBe(200)
    expect(stats.aiPending).toBe(929)
    expect(stats.supported).toBe(11)
    expect(stats.uncertain).toBe(3)
    expect(stats.notSupported).toBe(186)
  })

  it('阶段映射（待规则/规则已过/待AI/AI已审/待人工/待晋升/已完成/已阻断）', () => {
    expect(macroStageOf('rule_pending')).toBe('rule_pending')
    expect(macroStageOf('rule_pass')).toBe('rule_passed')
    expect(macroStageOf('rule_blocked')).toBe('blocked')
    expect(macroStageOf('ai_review_pending')).toBe('ai_pending')
    expect(macroStageOf('ai_supported')).toBe('ai_reviewed')
    expect(macroStageOf('human_review')).toBe('human_review')
    expect(macroStageOf('promotion_ready')).toBe('promotion')
    expect(macroStageOf('promoted')).toBe('completed')
    expect(STAGE_LABELS.rule_pending).toBe('待规则验证')
  })

  it('来源/阶段筛选 + 分页 30 条', () => {
    const items = mergeTaskCenterItems([], Array.from({ length: 100 }, (_, i) => macroView(`p${i}`)))
    expect(filterTaskCenterItems(items, { sourceType: 'evidence_task', stage: 'all', group: '', keyword: '' }).length).toBe(0)
    expect(filterTaskCenterItems(items, { sourceType: 'paper_discovery', stage: 'ai_pending', group: '', keyword: '' }).length).toBe(100)
    const page1 = paginateTaskCenterItems(items, 1)
    expect(page1.length).toBe(TASK_CENTER_PAGE_SIZE)
    expect(new Set(page1.map(i => i.sourceId)).size).toBe(page1.length) // no dup on page
  })

  it('合并后单任务 key 唯一（同一 ranking 只一次）', () => {
    const items = mergeTaskCenterItems([], [macroView('dup'), macroView('dup')])
    expect(items).toHaveLength(1)
    expect(items[0].taskKey).toBe('macro_candidate:dup')
  })
})
