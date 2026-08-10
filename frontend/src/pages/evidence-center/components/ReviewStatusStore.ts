import type { Direction, EvidenceLevel } from './types'

/** 审核状态前端存储:session 级(sessionStorage),key = 前缀 + targetId */
export const REVIEW_STATUS_KEY_PREFIX = 'evidence-center.review-approved.'

export type ReviewStatus = 'review_approved' | 'rejected'

export interface ReviewStatusMeta {
  direction: Direction
  evidenceLevel: EvidenceLevel
  confidence: string
  note: string
  /** ISO 时间戳 */
  at: string
}

export interface ReviewStatusRecord {
  targetId: string
  status: ReviewStatus
  meta: ReviewStatusMeta
  /** 对象类型(审核模块写入;晋升模块用于 attach/退回跳转) */
  targetType?: string
}

export function saveReviewStatus(targetId: string, status: ReviewStatus, meta: ReviewStatusMeta, targetType?: string): void {
  sessionStorage.setItem(`${REVIEW_STATUS_KEY_PREFIX}${targetId}`, JSON.stringify({
    targetId,
    status,
    meta,
    ...(targetType ? { targetType } : {}),
  }))
}

export function loadReviewStatus(targetId: string): ReviewStatusRecord | null {
  const raw = sessionStorage.getItem(`${REVIEW_STATUS_KEY_PREFIX}${targetId}`)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as ReviewStatusRecord
    if (!parsed || typeof parsed.status !== 'string') return null
    return parsed
  } catch {
    return null
  }
}

export function clearReviewStatus(targetId: string): void {
  sessionStorage.removeItem(`${REVIEW_STATUS_KEY_PREFIX}${targetId}`)
}

/** 扫描前缀下全部审核状态记录(含 rejected);晋升模块用 status === 'review_approved' 过滤出待晋升列表 */
export function listReviewApproved(): ReviewStatusRecord[] {
  const out: ReviewStatusRecord[] = []
  for (let i = 0; i < sessionStorage.length; i += 1) {
    const key = sessionStorage.key(i)
    if (!key || !key.startsWith(REVIEW_STATUS_KEY_PREFIX)) continue
    const raw = sessionStorage.getItem(key)
    if (!raw) continue
    try {
      const parsed = JSON.parse(raw) as ReviewStatusRecord
      if (parsed && typeof parsed.status === 'string' && typeof parsed.targetId === 'string') {
        out.push(parsed)
      }
    } catch {
      // 损坏记录跳过,不阻断其余记录
    }
  }
  return out
}
