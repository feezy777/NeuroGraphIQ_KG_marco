import { afterEach, describe, expect, it } from 'vitest'
import {
  REVIEW_STATUS_KEY_PREFIX,
  clearReviewStatus,
  listReviewApproved,
  loadReviewStatus,
  saveReviewStatus,
  type ReviewStatusMeta,
} from './ReviewStatusStore'

const META: ReviewStatusMeta = {
  direction: 'supports',
  evidenceLevel: 'direct',
  confidence: '0.8',
  note: '原文充分支持',
  at: '2026-08-10T08:00:00.000Z',
}

describe('ReviewStatusStore', () => {
  afterEach(() => {
    sessionStorage.clear()
  })

  it('saveReviewStatus 写入 sessionStorage 并可 load(含 at 时间戳)', () => {
    saveReviewStatus('r1-r2', 'review_approved', META)
    expect(sessionStorage.getItem(`${REVIEW_STATUS_KEY_PREFIX}r1-r2`)).toBeTruthy()
    const record = loadReviewStatus('r1-r2')
    expect(record).not.toBeNull()
    expect(record!.targetId).toBe('r1-r2')
    expect(record!.status).toBe('review_approved')
    expect(record!.meta).toEqual(META)
  })

  it('loadReviewStatus 无记录返回 null', () => {
    expect(loadReviewStatus('missing-target')).toBeNull()
  })

  it('loadReviewStatus 损坏 JSON 返回 null 而不抛错', () => {
    sessionStorage.setItem(`${REVIEW_STATUS_KEY_PREFIX}bad`, '{oops')
    expect(loadReviewStatus('bad')).toBeNull()
  })

  it('clearReviewStatus 删除指定记录', () => {
    saveReviewStatus('r1-r2', 'review_approved', META)
    clearReviewStatus('r1-r2')
    expect(loadReviewStatus('r1-r2')).toBeNull()
    expect(sessionStorage.getItem(`${REVIEW_STATUS_KEY_PREFIX}r1-r2`)).toBeNull()
  })

  it('listReviewApproved 扫描前缀返回全部记录(含 rejected,供晋升模块过滤)', () => {
    saveReviewStatus('a', 'review_approved', META)
    saveReviewStatus('b', 'rejected', { ...META, direction: 'contradicts' })
    const all = listReviewApproved()
    expect(all).toHaveLength(2)
    const approved = all.filter(r => r.status === 'review_approved')
    expect(approved.map(r => r.targetId)).toEqual(['a'])
    const rejected = all.filter(r => r.status === 'rejected')
    expect(rejected.map(r => r.targetId)).toEqual(['b'])
  })

  it('listReviewApproved 不干扰其他前缀的 sessionStorage 数据', () => {
    saveReviewStatus('a', 'review_approved', META)
    sessionStorage.setItem('evidence-center.review-draft.a', '{"passages":[]}')
    sessionStorage.setItem('unrelated.key', '{}')
    expect(listReviewApproved()).toHaveLength(1)
  })

  it('listReviewApproved 跳过损坏记录', () => {
    sessionStorage.setItem(`${REVIEW_STATUS_KEY_PREFIX}bad`, '{oops')
    saveReviewStatus('a', 'review_approved', META)
    expect(listReviewApproved()).toHaveLength(1)
  })
})
