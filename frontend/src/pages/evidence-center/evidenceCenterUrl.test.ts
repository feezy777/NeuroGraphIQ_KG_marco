import { afterEach, describe, expect, it } from 'vitest'
import {
  buildEvidenceUrl,
  parseEvidenceUrl,
  navigateToEvidenceCandidates,
  INITIAL_QUEUE_KEY,
} from './evidenceCenterUrl'

describe('evidenceCenterUrl', () => {
  it('解析 hash 中的 module/task/target/paper', () => {
    const s = parseEvidenceUrl('#/evidence-center?module=review&task_id=t1&target_type=connection&target_id=abc&paper_id=p1')
    expect(s).toEqual({ module: 'review', taskId: 't1', targetType: 'connection', targetId: 'abc', paperId: 'p1' })
  })
  it('缺省 module 为 tasks', () => {
    expect(parseEvidenceUrl('#/evidence-center').module).toBe('tasks')
  })
  it('构建 URL 与解析互逆', () => {
    const s = { module: 'candidates' as const, taskId: 't2', targetType: 'projection', targetId: 'x', paperId: null }
    const url = buildEvidenceUrl(s)
    expect(parseEvidenceUrl(url)).toEqual(s)
  })
})

describe('navigateToEvidenceCandidates(数据中心 → 候选模块交接)', () => {
  afterEach(() => {
    window.location.hash = ''
    sessionStorage.clear()
  })

  it('带 items 时写入 initial-queue 并跳转 candidates(首对象 target)', () => {
    const items = [
      { target_type: 'connection', target_id: 'a', label: 'A', confidence: 0.4 },
      { target_type: 'region_function', target_id: 'b', label: 'B', confidence: 0.6 },
    ]
    navigateToEvidenceCandidates({ items })
    expect(window.location.hash).toContain('/evidence-center')
    expect(window.location.hash).toContain('module=candidates')
    expect(window.location.hash).toContain('target_type=connection')
    expect(window.location.hash).toContain('target_id=a')
    const raw = sessionStorage.getItem(INITIAL_QUEUE_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw as string)).toEqual({ items, taskId: null })
  })

  it('taskId 透传 task_id 参数,无 items 时不写 initial-queue', () => {
    navigateToEvidenceCandidates({ taskId: 't1' })
    expect(sessionStorage.getItem(INITIAL_QUEUE_KEY)).toBeNull()
    expect(window.location.hash).toContain('module=candidates')
    expect(window.location.hash).toContain('task_id=t1')
  })
})
