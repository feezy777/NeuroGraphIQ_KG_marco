import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { EvidenceTasksModule } from './EvidenceTasksModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  getPaperEvidenceTask: vi.fn(),
  createPaperEvidenceBatch: vi.fn(),
  previewEvidenceBatchScope: vi.fn(),
}))

const TASK = {
  id: 't1', target_type: 'connection', name: '任务一', status: 'pending',
  total_items: 2, processed_items: 0, awaiting_review_items: 2, failed_items: 0,
  review_status: 'not_started', granularity_level: 'macro',
  estimated_target_count: 2, materialized_target_count: 2,
  scope: 'filter', mode: 'existence', max_papers_per_object: 3,
  created_at: '2026-08-10T00:00:00Z', created_by: null,
  started_at: null, finished_at: null, error_message: null, materialization_status: 'completed',
  materialization_cursor: null, materialization_error: null, confidence_lt: null,
  only_oa: false, stop_after_strong_support: false, summary: null,
  scope_type: 'filter', filter_snapshot: null, versions: null,
}

/** 匹配 "标签 <b>值</b>" 结构的统计文本(直接文本子节点不含 <b> 内数值) */
const stat = (label: string, value: number) =>
  screen.getByText((_content, el) => el?.textContent === `${label} ${value}`)

describe('EvidenceTasksModule', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [TASK], total: 1 })
    vi.mocked(endpoints.getPaperEvidenceTask).mockResolvedValue({ task: TASK, counts: {} })
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
    vi.mocked(endpoints.createPaperEvidenceBatch).mockResolvedValue({ task_id: 'new1', target_count: 2, skipped_active_targets: 0, auto_started: true })
  })

  it('渲染任务列表与状态分组', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    // 状态分组标题
    expect(screen.getByText('待处理')).toBeTruthy()
    // 任务行:对象类型 / 任务级数字(待审=2) / 佐证数(待审+已处理=2)
    expect(screen.getByText('connection')).toBeTruthy()
    expect(stat('待审', 2)).toBeTruthy()
    expect(stat('佐证数', 2)).toBeTruthy()
    expect(stat('已处理', 0)).toBeTruthy()
    expect(stat('失败数', 0)).toBeTruthy()
    // 预处理/审核状态
    expect(screen.getByText('预处理 · 待预处理')).toBeTruthy()
    expect(screen.getByText('审核 · 未开始审核')).toBeTruthy()
  })

  it('创建批量预处理打开对话框,可关闭', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('创建批量预处理')).toBeTruthy())
    fireEvent.click(screen.getByText('创建批量预处理'))
    expect(screen.getByTestId('create-batch-dialog')).toBeTruthy()
    fireEvent.click(screen.getByText('关闭'))
    expect(screen.queryByTestId('create-batch-dialog')).toBeNull()
  })

  it('多状态任务进入对应分组(待人工审核/已审核/失败)', async () => {
    const tAwaiting = { ...TASK, id: 't2', name: '任务二', status: 'completed', awaiting_review_items: 3, review_status: 'in_progress' }
    const tReviewed = { ...TASK, id: 't4', name: '任务四', status: 'completed', awaiting_review_items: 0, review_status: 'completed' }
    const tFailed = { ...TASK, id: 't3', name: '任务三', status: 'failed', failed_items: 2, awaiting_review_items: 0 }
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [TASK, tAwaiting, tReviewed, tFailed], total: 4 })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务四')).toBeTruthy())
    expect(screen.getByText('待处理')).toBeTruthy()
    expect(screen.getByText('待人工审核')).toBeTruthy()
    expect(screen.getByText('已审核')).toBeTruthy()
    expect(screen.getByText('失败')).toBeTruthy()
    // 已完成组:无任务落组(任务四被"已审核"优先吸收)
    expect(screen.queryByText('已完成')).toBeNull()
  })

  it('打开任务跳转候选模块(URL 带 task_id)', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByText('打开任务'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=t1')
  })

  it('开始人工处理跳转候选模块', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByText('开始人工处理'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=t1')
    expect(endpoints.getPaperEvidenceTask).toHaveBeenCalledWith('t1')
  })

  it('加载失败显示错误并可重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('503 backend down'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/任务加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByText('重试'))
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
  })

  it('空列表显示空态提示', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/暂无佐证任务/)).toBeTruthy())
  })
})
