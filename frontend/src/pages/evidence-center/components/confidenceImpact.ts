import type { Direction } from './types'

/** Rule 上限:supports → 0.85,partial → 0.75,其余方向无公式上限(与后端 confidence_rules 一致) */
export function ruleCapForDirection(direction: Direction): number | null {
  if (direction === 'supports') return 0.85
  if (direction === 'partial') return 0.75
  return null
}

/** 人工置信度钳制到 [0,1](与后端 confidence_rules.compute_adjustment 的 clamp 一致) */
export function clampConfidence(value: number | string | null | undefined): number {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(1, n))
}

/** Final 置信度,镜像后端 confidence_rules.compute_adjustment 语义:
 *  - contradicts/mixed/not_found → final = current(不自动修改,apply=False)
 *  - supports/partial 且 reviewer < current → final = current(弱证据不改变,apply=False)
 *  - supports → min(0.85, reviewer);partial → min(0.75, reviewer) */
export function computeFinalConfidence(direction: Direction, current: number | null, reviewer: number): number {
  const cur = current ?? 0
  const rev = clampConfidence(reviewer)
  if (direction === 'contradicts' || direction === 'mixed' || direction === 'not_found') return cur
  if (rev < cur) return cur
  const cap = ruleCapForDirection(direction)
  return cap == null ? rev : Math.min(cap, rev)
}

export interface ConfidenceImpact {
  current: number | null
  reviewer: number
  cap: number | null
  /** 公式中间值 max(current, reviewer):规则上限前的最大可达值(视觉稿 Maximum 格) */
  maximum: number
  final: number
}

export function computeConfidenceImpact(
  direction: Direction,
  current: number | null,
  reviewer: number,
): ConfidenceImpact {
  const rev = clampConfidence(reviewer)
  const cap = ruleCapForDirection(direction)
  return {
    current,
    reviewer: rev,
    cap,
    maximum: Math.max(current ?? 0, rev),
    final: computeFinalConfidence(direction, current, rev),
  }
}
