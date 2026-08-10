import { describe, expect, it } from 'vitest'
import { computeConfidenceImpact, computeFinalConfidence, ruleCapForDirection } from './confidenceImpact'

describe('confidenceImpact', () => {
  it('Rule cap:support 0.85 / partial 0.75 / 其余方向无上限', () => {
    expect(ruleCapForDirection('supports')).toBe(0.85)
    expect(ruleCapForDirection('partial')).toBe(0.75)
    expect(ruleCapForDirection('contradicts')).toBeNull()
    expect(ruleCapForDirection('mixed')).toBeNull()
    expect(ruleCapForDirection('not_found')).toBeNull()
  })

  it('Final = min(cap, max(current, reviewer))', () => {
    // 人工推荐高于当前 → 取人工推荐
    expect(computeFinalConfidence(0.7, 0.8, 0.85)).toBe(0.8)
    // 超过 cap → 被 cap 截断
    expect(computeFinalConfidence(0.9, 0.8, 0.85)).toBe(0.85)
    // 无当前置信度 → 以人工推荐为基准
    expect(computeFinalConfidence(null, 0.8, 0.85)).toBe(0.8)
    // 无 cap 方向(矛盾/混合)→ 不截断
    expect(computeFinalConfidence(0.8, 0.85, null)).toBe(0.85)
    expect(computeFinalConfidence(null, 0.8, null)).toBe(0.8)
  })

  it('computeConfidenceImpact 组合输出 Current/Reviewer/Rule/Final', () => {
    expect(computeConfidenceImpact('supports', 0.7, 0.8)).toEqual({
      current: 0.7,
      reviewer: 0.8,
      cap: 0.85,
      final: 0.8,
    })
    // partial 方向 cap 0.75 → 0.85 被截断为 0.75
    expect(computeConfidenceImpact('partial', 0.8, 0.85)).toEqual({
      current: 0.8,
      reviewer: 0.85,
      cap: 0.75,
      final: 0.75,
    })
    // 矛盾方向无 cap → final = max
    expect(computeConfidenceImpact('contradicts', 0.7, 0.8)).toEqual({
      current: 0.7,
      reviewer: 0.8,
      cap: null,
      final: 0.8,
    })
  })
})
