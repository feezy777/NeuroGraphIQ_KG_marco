import { describe, expect, it } from 'vitest'
import type { PaperEvidenceTaskItem } from '../../../api/endpoints'
import { groupOf, isUnfinishedItem, sortByConfidenceAsc, TARGET_TYPE_GROUPS, UNFINISHED_ITEM_STATUSES } from './taskItemQueueUtils'
import { workStatusRank } from './taskStatus'

function makeItem(overrides: Partial<PaperEvidenceTaskItem>): PaperEvidenceTaskItem {
  return {
    id: 'i', target_type: 'connection', target_id: 't', status: 'pending', pmid: null, title: null,
    passage: null, direction: null, confidence: null, evidence_id: null, error_message: null,
    updated_at: null, label: 'L', current_confidence: null, attempt_count: 0, last_error_code: null,
    last_error_message: null, preprocess_outcome: null, paper_id: null, model_direction: null,
    candidate_papers: null, review_draft: null, claim_text_snapshot: null, claim_components_snapshot: null,
    passages_json: null, last_error: null, retry_count: 0, ...overrides,
  }
}

describe('taskItemQueueUtils', () => {
  it('未完成状态集合判定', () => {
    for (const s of UNFINISHED_ITEM_STATUSES) expect(isUnfinishedItem(makeItem({ status: s }))).toBe(true)
    for (const s of ['completed', 'skipped', 'failed', 'cancelled']) expect(isUnfinishedItem(makeItem({ status: s }))).toBe(false)
  })

  it('置信度排序:null 最前,升序,同值按 label', () => {
    const sorted = sortByConfidenceAsc([
      makeItem({ id: 'a', label: 'a', current_confidence: 0.9 }),
      makeItem({ id: 'b', label: 'b', current_confidence: null }),
      makeItem({ id: 'c', label: 'c', current_confidence: 0.4 }),
      makeItem({ id: 'd', label: 'd', current_confidence: 0.4, target_id: 'td' }),
    ])
    expect(sorted.map(i => i.id)).toEqual(['b', 'c', 'd', 'a'])
  })

  it('排序在同置信度下按 label 稳定排序,label 缺失兜底 target_id', () => {
    const sorted = sortByConfidenceAsc([
      makeItem({ id: 'x', label: 'Beta', current_confidence: 0.5 }),
      makeItem({ id: 'y', label: null, target_id: 'zzz', current_confidence: 0.5 }),
      makeItem({ id: 'z', label: 'Alpha', current_confidence: 0.5 }),
    ])
    expect(sorted.map(i => i.id)).toEqual(['z', 'x', 'y'])
  })

  it('类型分组映射:回路/连接/功能/其他', () => {
    expect(groupOf('circuit')).toBe('circuit')
    expect(groupOf('circuit_step')).toBe('circuit')
    expect(groupOf('circuit_function')).toBe('circuit')
    expect(groupOf('connection')).toBe('connection')
    expect(groupOf('projection')).toBe('connection')
    expect(groupOf('region_function')).toBe('function')
    expect(groupOf('projection_function')).toBe('function')
    expect(groupOf('unknown_type')).toBe('other')
    expect(TARGET_TYPE_GROUPS.map(g => g.label)).toEqual(['回路', '连接', '功能'])
  })

  it('任务工作状态排序秩:处理中 → 待验证 → 已暂停 → 部分失败 → 失败 → 已完成 → 空 → 已取消', () => {
    expect(workStatusRank('processing')).toBeLessThan(workStatusRank('awaiting_review'))
    expect(workStatusRank('awaiting_review')).toBeLessThan(workStatusRank('paused'))
    expect(workStatusRank('paused')).toBeLessThan(workStatusRank('partially_failed'))
    expect(workStatusRank('partially_failed')).toBeLessThan(workStatusRank('failed'))
    expect(workStatusRank('failed')).toBeLessThan(workStatusRank('completed'))
    expect(workStatusRank('completed')).toBeLessThan(workStatusRank('empty'))
    expect(workStatusRank('empty')).toBeLessThan(workStatusRank('cancelled'))
    expect(workStatusRank('unknown_status')).toBe(9)
  })
})
