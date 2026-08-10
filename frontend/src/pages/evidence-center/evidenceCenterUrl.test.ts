import { describe, expect, it } from 'vitest'
import { buildEvidenceUrl, parseEvidenceUrl } from './evidenceCenterUrl'

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
