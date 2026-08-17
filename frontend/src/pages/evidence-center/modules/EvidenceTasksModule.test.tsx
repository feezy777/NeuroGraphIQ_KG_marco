import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { EvidenceTasksModule } from './EvidenceTasksModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  pausePaperEvidenceTask: vi.fn(),
  resumePaperEvidenceTask: vi.fn(),
  retryPaperEvidenceTask: vi.fn(),
  previewEvidenceBatchScope: vi.fn(),
  createPaperEvidenceBatch: vi.fn(),
}))

function makeTask(overrides: Record<string, unknown>) {
  return {
    id: 't1', target_type: 'connection', target_id: 'c1', name: null, status: 'pending',
    total_items: 1, processed_items: 0, awaiting_review_items: 1, failed_items: 0,
    review_status: 'not_started', granularity_level: 'macro', estimated_target_count: 1,
    materialized_target_count: 1, scope: 'low_confidence', mode: 'function', max_papers_per_object: 3,
    created_at: '2026-08-17T00:00:00Z', created_by: null, started_at: null, finished_at: null,
    error_message: null, materialization_status: 'completed', materialization_cursor: null,
    materialization_error: null, confidence_lt: null, only_oa: false,
    stop_after_strong_support: false, summary: null, scope_type: 'filter',
    filter_snapshot: null, versions: null,
    display_name_cn: '杏仁核 → 海马', display_name_en: 'Amygdala → Hippocampus',
    display_confidence: 0.35, display_name_source: 'mirror_live', display_confidence_source: 'mirror_live',
    work_status: 'awaiting_review',
    item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 },
    capabilities: { can_continue_review: true, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false },
    ...overrides,
  }
}

function renderModule(hash = '#/evidence-center?module=tasks') {
  window.location.hash = hash
  return render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
}

describe('EvidenceTasksModule(对象级任务卡:命名/跳转/排序/筛选)', () => {
  afterEach(() => { cleanup(); window.location.hash = ''; sessionStorage.clear() })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.pausePaperEvidenceTask).mockResolvedValue({ task_id: 't1', status: 'paused' })
    vi.mocked(endpoints.resumePaperEvidenceTask).mockResolvedValue({ task_id: 't1', status: 'pending' })
    vi.mocked(endpoints.retryPaperEvidenceTask).mockResolvedValue({ task_id: 't1', retried: 1 })
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('卡片标题=中文 (英文),副行类型+置信度,徽章状态', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [makeTask({})], total: 1 })
    renderModule()
    const card = await screen.findByTestId('evidence-task-card-t1')
    expect(within(card).getByText('杏仁核 → 海马 (Amygdala → Hippocampus)')).toBeTruthy()
    expect(within(card).getByText('连接')).toBeTruthy()
    expect(within(card).getByText('置信度 35%')).toBeTruthy()
    expect(within(card).getByText('待验证')).toBeTruthy()
  })

  it('中文缺失仅英文;name 备注作第三行不替换标题', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ display_name_cn: null, display_name_en: 'Amygdala → Hippocampus', name: '重新评分 · x · projection' })],
      total: 1,
    })
    renderModule()
    const card = await screen.findByTestId('evidence-task-card-t1')
    expect(within(card).getByText('Amygdala → Hippocampus')).toBeTruthy()
    expect(within(card).getByText('重新评分 · x · projection')).toBeTruthy()
    expect(screen.queryByText('重新评分 · x · projection (Amygdala → Hippocampus)')).toBeNull()
  })

  it('镜像缺失兜底「类型中文 #短ID」', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ display_name_cn: null, display_name_en: null, display_confidence: null })],
      total: 1,
    })
    renderModule()
    const card = await screen.findByTestId('evidence-task-card-t1')
    expect(within(card).getByText('连接 #c1')).toBeTruthy()
    expect(within(card).getByText('未评分')).toBeTruthy()
  })

  it('整卡点击 → 跳转 candidates(与数据中心一致)+ initial-queue 快照', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [makeTask({})], total: 1 })
    renderModule()
    fireEvent.click(await screen.findByTestId('evidence-task-card-t1'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=t1')
    expect(window.location.hash).toContain('target_type=connection')
    expect(window.location.hash).toContain('target_id=c1')
    const queued = JSON.parse(sessionStorage.getItem('evidence-center.initial-queue') ?? '{}')
    expect(queued.items?.[0]?.target_id).toBe('c1')
    expect(queued.taskId).toBe('t1')
  })

  it('卡片按钮不触发跳转(暂停/恢复/重试)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ work_status: 'processing', status: 'running', capabilities: { can_continue_review: false, can_pause: true, can_resume: false, can_retry_failed: false, can_view_results: false } })],
      total: 1,
    })
    renderModule()
    fireEvent.click(await screen.findByTestId('evidence-task-action-pause-t1'))
    await waitFor(() => expect(vi.mocked(endpoints.pausePaperEvidenceTask)).toHaveBeenCalledWith('t1'))
    expect(window.location.hash).not.toContain('module=candidates')
  })

  it('键盘 Enter 触发在按钮上时不冒泡触发整卡跳转', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ work_status: 'processing', status: 'running', capabilities: { can_continue_review: false, can_pause: true, can_resume: false, can_retry_failed: false, can_view_results: false } })],
      total: 1,
    })
    renderModule()
    const pauseBtn = await screen.findByTestId('evidence-task-action-pause-t1')
    fireEvent.keyDown(pauseBtn, { key: 'Enter' })
    expect(window.location.hash).not.toContain('module=candidates')
    // 整卡自身 Enter 仍触发跳转
    const card = screen.getByTestId('evidence-task-card-t1')
    fireEvent.keyDown(card, { key: 'Enter' })
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
  })

  it('排序:处理中→待验证→已完成→失败;组内置信度升序 null 最前', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-done', work_status: 'completed', status: 'completed', display_confidence: 0.6, capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: true } }),
        makeTask({ id: 't-await-hi', work_status: 'awaiting_review', display_confidence: 0.9 }),
        makeTask({ id: 't-proc', work_status: 'processing', status: 'running', display_confidence: 0.4, capabilities: { can_continue_review: false, can_pause: true, can_resume: false, can_retry_failed: false, can_view_results: false } }),
        makeTask({ id: 't-fail', work_status: 'failed', status: 'failed', display_confidence: 0.2, capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: true, can_view_results: true } }),
        makeTask({ id: 't-await-null', work_status: 'awaiting_review', display_confidence: null }),
      ],
      total: 5,
    })
    renderModule()
    const grid = await screen.findByTestId('evidence-task-card-grid')
    const ids = [...grid.querySelectorAll('[data-testid^="evidence-task-card-"]')].map(el => el.getAttribute('data-testid'))
    expect(ids).toEqual([
      'evidence-task-card-t-proc',
      'evidence-task-card-t-await-null',
      'evidence-task-card-t-await-hi',
      'evidence-task-card-t-done',
      'evidence-task-card-t-fail',
    ])
  })

  it('筛选 chips:回路组只显示 circuit 类型;已取消不显示', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-cn', target_type: 'connection' }),
        makeTask({ id: 't-cc', target_type: 'circuit', display_name_cn: '默认模式网络', display_name_en: 'Default Mode Network' }),
        makeTask({ id: 't-cancel', work_status: 'cancelled', status: 'cancelled', capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false } }),
      ],
      total: 3,
    })
    renderModule()
    await screen.findByTestId('evidence-task-card-t-cn')
    expect(screen.queryByTestId('evidence-task-card-t-cancel')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '回路' }))
    await waitFor(() => expect(screen.queryByTestId('evidence-task-card-t-cn')).toBeNull())
    expect(screen.getByTestId('evidence-task-card-t-cc')).toBeTruthy()
  })

  it('待验证任务「继续验证」:有 target_id 直接跳转,不查 items', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [makeTask({})], total: 1 })
    renderModule()
    fireEvent.click(await screen.findByTestId('evidence-task-action-continue-t1'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    // 共享 hook 会在挂载/URL 变更后自行取 items({limit,sort} 签名);此处仅断言「继续验证」未触发额外的待验证对象查询
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).not.toHaveBeenCalledWith(
      't1', { status: 'awaiting_review', limit: 1, sort: 'confidence' },
    )
  })

  it('失败任务「重试失败项」:确认弹窗,取消不调用,确认后调用', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ work_status: 'failed', status: 'failed', item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 0, completed: 0, skipped: 0, failed: 1, cancelled: 0 }, capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: true, can_view_results: true } })],
      total: 1,
    })
    renderModule()
    fireEvent.click(await screen.findByTestId('evidence-task-action-retry-t1'))
    await waitFor(() => expect(screen.getByText(/将重新处理 1 个失败对象/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /取消|cancel/i }))
    expect(vi.mocked(endpoints.retryPaperEvidenceTask)).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('evidence-task-action-retry-t1'))
    fireEvent.click(screen.getByRole('button', { name: /确认重试/ }))
    await waitFor(() => expect(vi.mocked(endpoints.retryPaperEvidenceTask)).toHaveBeenCalledWith('t1'))
    await waitFor(() => expect(screen.getByText('失败项已重新进入处理队列。')).toBeTruthy())
  })
})
