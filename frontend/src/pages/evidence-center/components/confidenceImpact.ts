import type { Direction } from './types'

/** Rule 上限:supports → 0.85,partial → 0.75,其余方向无公式上限(与后端 confidence_rules 一致) */
export function ruleCapForDirection(direction: Direction): number | null {
  if (direction === 'supports') return 0.85
  if (direction === 'partial') return 0.75
  return null
}

/** Final = min(cap, max(current, reviewer));无 cap 时取 max(current, reviewer) */
export function computeFinalConfidence(current: number | null, reviewer: number, cap: number | null): number {
  const base = Math.max(current ?? reviewer, reviewer)
  return cap == null ? base : Math.min(cap, base)
}

export interface ConfidenceImpact {
  current: number | null
  reviewer: number
  cap: number | null
  final: number
}

export function computeConfidenceImpact(
  direction: Direction,
  current: number | null,
  reviewer: number,
): ConfidenceImpact {
  const cap = ruleCapForDirection(direction)
  return { current, reviewer, cap, final: computeFinalConfidence(current, reviewer, cap) }
}
