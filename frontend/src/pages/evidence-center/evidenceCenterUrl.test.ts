import { afterEach, describe, expect, it } from 'vitest'
import {
  buildEmbeddedUrl,
  buildEvidenceUrl,
  parseEvidenceUrl,
  navigateToEvidenceCandidates,
  INITIAL_QUEUE_KEY,
} from './evidenceCenterUrl'

const FULL_STATE = {
  module: 'review' as const,
  taskId: 't1',
  taskItemId: 'it1',
  targetType: 'connection',
  targetId: 'abc',
  paperId: 'p1',
}

describe('evidenceCenterUrl', () => {
  it('解析 hash 中的 module/task/task_item/target/paper', () => {
    const s = parseEvidenceUrl(
      '#/evidence-center?module=review&task_id=t1&task_item_id=it1&target_type=connection&target_id=abc&paper_id=p1',
    )
    expect(s).toEqual(FULL_STATE)
  })
  it('缺省 module 为 tasks,缺 task_item_id 为 null(旧 deep link 兼容)', () => {
    const s = parseEvidenceUrl('#/evidence-center?task_id=t1&target_id=abc')
    expect(s.module).toBe('tasks')
    expect(s.taskItemId).toBeNull()
    expect(s.taskId).toBe('t1')
  })
  it('构建 URL 与解析互逆(含 task_item_id)', () => {
    const url = buildEvidenceUrl(FULL_STATE)
    expect(url).toContain('task_item_id=it1')
    expect(parseEvidenceUrl(url)).toEqual(FULL_STATE)
  })
  it('embedded 构建/解析互逆(含 task_item_id),保留无关参数', () => {
    const url = buildEmbeddedUrl(FULL_STATE, '#/validation-center?tab=paper_evidence&foo=bar')
    expect(url).toContain('tab=paper_evidence')
    expect(url).toContain('task_item_id=it1')
    expect(url).toContain('foo=bar')
    expect(parseEvidenceUrl(url)).toEqual(FULL_STATE)
  })
  it('embedded URL 缺 tab 时按空态解析', () => {
    const s = parseEvidenceUrl('#/validation-center?task_id=t1')
    expect(s).toEqual({
      module: 'tasks', taskId: null, taskItemId: null, targetType: null, targetId: null, paperId: null,
    })
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
    expect(window.location.hash).toContain('/validation-center')
    expect(window.location.hash).toContain('module=candidates')
    expect(window.location.hash).toContain('target_type=connection')
    expect(window.location.hash).toContain('target_id=a')
    // S6:数据中心 standalone 候选入口不写 task_item_id(三.4)
    expect(window.location.hash).not.toContain('task_item_id')
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
