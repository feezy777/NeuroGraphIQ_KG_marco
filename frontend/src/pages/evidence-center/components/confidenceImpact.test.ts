import { describe, expect, it } from 'vitest'
import { clampConfidence, computeConfidenceImpact, computeFinalConfidence, ruleCapForDirection } from './confidenceImpact'

describe('confidenceImpact', () => {
  it('Rule cap:support 0.85 / partial 0.75 / 其余方向无上限', () => {
    expect(ruleCapForDirection('supports')).toBe(0.85)
    expect(ruleCapForDirection('partial')).toBe(0.75)
    expect(ruleCapForDirection('contradicts')).toBeNull()
    expect(ruleCapForDirection('mixed')).toBeNull()
    expect(ruleCapForDirection('not_found')).toBeNull()
  })

  it('Final 镜像后端:supports/partial 且 reviewer >= current → min(cap, reviewer)', () => {
    // 人工推荐高于当前 → 取人工推荐
    expect(computeFinalConfidence('supports', 0.7, 0.8)).toBe(0.8)
    // 超过 cap → 被 cap 截断
    expect(computeFinalConfidence('supports', 0.7, 0.9)).toBe(0.85)
    expect(computeFinalConfidence('partial', 0.8, 0.85)).toBe(0.75)
    // 无当前置信度 → 以人工推荐为基准
    expect(computeFinalConfidence('supports', null, 0.8)).toBe(0.8)
  })

  it('Final 镜像后端:弱证据(reviewer < current)→ final = current(不改变)', () => {
    expect(computeFinalConfidence('supports', 0.9, 0.8)).toBe(0.9)
    expect(computeFinalConfidence('supports', 0.95, 0.8)).toBe(0.95)
    expect(computeFinalConfidence('partial', 0.9, 0.8)).toBe(0.9)
  })

  it('Final 镜像后端:contradicts/mixed/not_found → final = current(不自动修改)', () => {
    expect(computeFinalConfidence('contradicts', 0.7, 0.8)).toBe(0.7)
    expect(computeFinalConfidence('mixed', 0.7, 0.8)).toBe(0.7)
    expect(computeFinalConfidence('not_found', 0.7, 0.8)).toBe(0.7)
  })

  it('reviewer 钳制到 [0,1](与后端 clamp 一致),越界值先钳制再入公式', () => {
    expect(clampConfidence(2)).toBe(1)
    expect(clampConfidence(-0.5)).toBe(0)
    expect(clampConfidence(NaN)).toBe(0)
    expect(clampConfidence(Infinity)).toBe(0)
    expect(clampConfidence('0.8')).toBe(0.8)
    expect(computeFinalConfidence('supports', 0.5, 2)).toBe(0.85)
    expect(computeConfidenceImpact('supports', 0.5, 2).reviewer).toBe(1)
  })

  it('computeConfidenceImpact 组合输出 Current/Reviewer/Rule/Maximum/Final', () => {
    expect(computeConfidenceImpact('supports', 0.7, 0.8)).toEqual({
      current: 0.7,
      reviewer: 0.8,
      cap: 0.85,
      maximum: 0.8,
      final: 0.8,
    })
    // partial 方向 cap 0.75 → 0.85 被截断为 0.75
    expect(computeConfidenceImpact('partial', 0.8, 0.85)).toEqual({
      current: 0.8,
      reviewer: 0.85,
      cap: 0.75,
      maximum: 0.85,
      final: 0.75,
    })
    // 矛盾方向 → final = current(不自动修改)
    expect(computeConfidenceImpact('contradicts', 0.7, 0.8)).toEqual({
      current: 0.7,
      reviewer: 0.8,
      cap: null,
      maximum: 0.8,
      final: 0.7,
    })
    // 弱证据:supports 且 reviewer < current → final = current
    expect(computeConfidenceImpact('supports', 0.95, 0.8)).toEqual({
      current: 0.95,
      reviewer: 0.8,
      cap: 0.85,
      maximum: 0.95,
      final: 0.95,
    })
  })

  it('Maximum = max(current, reviewer):规则上限前的中间值(视觉稿 Maximum 格)', () => {
    // reviewer 更高 → maximum = reviewer(后续被 cap 截断)
    expect(computeConfidenceImpact('supports', 0.7, 0.9).maximum).toBe(0.9)
    // current 更高 → maximum = current(弱证据场景)
    expect(computeConfidenceImpact('supports', 0.95, 0.8).maximum).toBe(0.95)
    // 无当前置信度 → maximum = reviewer
    expect(computeConfidenceImpact('supports', null, 0.6).maximum).toBe(0.6)
  })
})
