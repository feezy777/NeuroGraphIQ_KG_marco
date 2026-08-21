import { describe, expect, it } from 'vitest'
import { buildEmbeddedUrl, buildEvidenceUrl, parseEvidenceUrl } from './evidenceCenterUrl'

const STATE = {
  module: 'tasks' as const,
  taskId: 't1',
  taskItemId: null,
  targetType: 'connection',
  targetId: 'c1',
  paperId: null,
}

describe('buildEmbeddedUrl / buildEvidenceUrl(第四步 URL 规则 + S6 task_item_id)', () => {
  it('embedded 任务 URL:tab 保留 + module=tasks 省略 + task_id', () => {
    const url = buildEmbeddedUrl({ ...STATE, targetType: null, targetId: null }, '#/validation-center?tab=paper_evidence')
    expect(url).toBe('#/validation-center?tab=paper_evidence&task_id=t1')
  })

  it('embedded 任务+对象 URL:task_id + target_type + target_id 齐全', () => {
    const url = buildEmbeddedUrl(STATE, '#/validation-center?tab=paper_evidence')
    expect(url).toBe('#/validation-center?tab=paper_evidence&task_id=t1&target_type=connection&target_id=c1')
  })

  it('embedded 任务+任务项+对象 URL:携带 task_item_id(S6 三)', () => {
    const url = buildEmbeddedUrl({ ...STATE, taskItemId: 'it-9' }, '#/validation-center?tab=paper_evidence')
    expect(url).toBe('#/validation-center?tab=paper_evidence&task_id=t1&task_item_id=it-9&target_type=connection&target_id=c1')
  })

  it('embedded 无任务对象 URL:module=candidates + target,无 task_id/task_item_id', () => {
    const url = buildEmbeddedUrl(
      { module: 'candidates', taskId: null, taskItemId: null, targetType: 'connection', targetId: 'c2', paperId: null },
      '#/validation-center?tab=paper_evidence',
    )
    expect(url).toBe('#/validation-center?tab=paper_evidence&module=candidates&target_type=connection&target_id=c2')
  })

  it('空参数不写入 URL(不产生 task_id= 空段)', () => {
    const url = buildEmbeddedUrl(
      { module: 'tasks', taskId: null, taskItemId: null, targetType: null, targetId: null, paperId: null },
      '#/validation-center?tab=paper_evidence',
    )
    expect(url).toBe('#/validation-center?tab=paper_evidence')
    expect(url).not.toContain('task_id=')
    expect(url).not.toContain('task_item_id=')
    expect(url).not.toContain('target_type=')
  })

  it('保留无关 query 参数', () => {
    const url = buildEmbeddedUrl(STATE, '#/validation-center?tab=paper_evidence&granularity=macro&foo=1')
    expect(url).toContain('granularity=macro')
    expect(url).toContain('foo=1')
    expect(url).toContain('tab=paper_evidence')
    expect(url).toContain('task_id=t1')
  })

  it('embedded 始终输出 /validation-center,不输出 /evidence-center', () => {
    const url = buildEmbeddedUrl(STATE, '#/validation-center?tab=paper_evidence')
    expect(url.startsWith('#/validation-center')).toBe(true)
    expect(url).not.toContain('/evidence-center')
  })

  it('standalone buildEvidenceUrl 保持 /evidence-center 且省略默认 module 与空参数', () => {
    expect(buildEvidenceUrl({ module: 'tasks', taskId: 't1', taskItemId: null, targetType: null, targetId: null, paperId: null }))
      .toBe('#/evidence-center?task_id=t1')
    expect(buildEvidenceUrl({ module: 'candidates', taskId: null, taskItemId: null, targetType: 'connection', targetId: 'c1', paperId: null }))
      .toBe('#/evidence-center?module=candidates&target_type=connection&target_id=c1')
  })

  it('parseEvidenceUrl 恢复 embedded 任务+任务项+对象状态', () => {
    const s = parseEvidenceUrl('#/validation-center?tab=paper_evidence&task_id=t1&task_item_id=it-9&target_type=connection&target_id=c1')
    expect(s).toEqual({
      module: 'tasks', taskId: 't1', taskItemId: 'it-9',
      targetType: 'connection', targetId: 'c1', paperId: null,
    })
  })
})
