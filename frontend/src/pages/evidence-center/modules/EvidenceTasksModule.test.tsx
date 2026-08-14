import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { EvidenceTasksModule } from './EvidenceTasksModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  getEvidenceTarget: vi.fn(),
  searchPaperEvidence: vi.fn(),
  extractSelectedPaperEvidence: vi.fn(),
  listPaperEvidence: vi.fn(),
  saveTaskItemDraft: vi.fn(),
  validatePassageSelection: vi.fn(),
  translateEvidenceText: vi.fn(),
  attachPaperEvidencePreview: vi.fn(),
  attachPaperEvidence: vi.fn(),
  rollbackPaperEvidence: vi.fn(),
  createPaperEvidenceExtractionRun: vi.fn(),
  getPaperEvidenceExtractionRun: vi.fn(),
  retryFailedPaperEvidenceExtractionRun: vi.fn(),
  cancelPaperEvidenceExtractionRun: vi.fn(),
  completePaperEvidenceTaskItem: vi.fn(),
  reopenPaperEvidenceTaskItem: vi.fn(),
  createPaperEvidenceBatch: vi.fn(),
  previewEvidenceBatchScope: vi.fn(),
}))

function makeTask(overrides: Record<string, unknown>) {
  return {
    id: 't1', target_type: 'connection', name: '任务一', status: 'pending',
    total_items: 10, processed_items: 2, awaiting_review_items: 1, failed_items: 0,
    review_status: 'in_review', granularity_level: 'macro', estimated_target_count: 10,
    materialized_target_count: 10, scope: 'filter', mode: 'existence', max_papers_per_object: 3,
    created_at: '2026-08-10T00:00:00Z', created_by: null, started_at: null, finished_at: null,
    error_message: null, materialization_status: 'completed', materialization_cursor: null,
    materialization_error: null, confidence_lt: null, only_oa: false,
    stop_after_strong_support: false, summary: null, scope_type: 'filter',
    filter_snapshot: null, versions: null, ...overrides,
  }
}

function makeItem(overrides: Record<string, unknown>) {
  return {
    id: 'it', target_type: 'connection', target_id: 'conn', status: 'awaiting_review',
    pmid: null, title: null, passage: null, direction: null, confidence: null,
    evidence_id: null, error_message: null, updated_at: '2026-08-10T00:00:00Z',
    label: 'Conn', current_confidence: 0.5, attempt_count: 0, last_error_code: null,
    last_error_message: null, preprocess_outcome: null, paper_id: null, model_direction: null,
    candidate_papers: [], review_draft: null, claim_text_snapshot: null,
    claim_components_snapshot: null, passages_json: null, last_error: null, retry_count: 0,
    ...overrides,
  }
}

function objectIds(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('[data-testid^="evidence-task-object-"]'))
    .map(el => (el as HTMLElement).dataset.testid ?? '')
    .filter(id => id !== 'evidence-task-object-list')
}

describe('EvidenceTasksModule(中栏对象列表)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('全局模式:中栏直接显示所有进行中任务的对象(名称/类型/置信度/状态/任务徽章),置信度升序', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 'ta', name: '任务A', status: 'running' }),
        makeTask({ id: 'tc', name: '任务C', status: 'completed' }), // 非进行中,不取对象
      ], total: 2,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockImplementation(async (taskId: string) => ({
      items: taskId === 'ta'
        ? [
            makeItem({ id: 'a1', target_id: 'c-high', label: '杏仁核 -> 前额叶', current_confidence: 0.9 }),
            makeItem({ id: 'a2', target_id: 'c-null', label: '海马 -> 丘脑', current_confidence: null }),
          ]
        : [],
    }))
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('杏仁核 -> 前额叶')).toBeTruthy())
    // 具体连接名称 + 置信度大字 + 任务徽章
    expect(screen.getByText('海马 -> 丘脑')).toBeTruthy()
    expect(screen.getByText('0.90')).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
    // 任务徽章(两张对象卡各一个)
    expect(screen.getAllByText('任务A').length).toBe(2)
    // 置信度升序:null 最前
    expect(objectIds(container)).toEqual(['evidence-task-object-c-null', 'evidence-task-object-c-high'])
    // 未拉已完成任务 tc 的对象
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).not.toHaveBeenCalledWith('tc', { limit: 100 })
  })

  it('全局模式:点击对象 → 选中来源任务并打开工作区(URL 带 task_id 与 target)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a1', target_id: 'c-1', label: '脑桥 -> 小脑', current_confidence: 0.4 })],
    })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('脑桥 -> 小脑')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-object-c-1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=ta'))
    expect(window.location.hash).toContain('target_id=c-1')
  })

  it('任务模式(深链 task_id):中栏只显示该任务对象,工具栏带返回按钮', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'i1', target_id: 'c-1', label: 'BLA -> IL', current_confidence: 0.5 })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('BLA -> IL')).toBeTruthy())
    expect(screen.getByTestId('evidence-task-middle-back')).toBeTruthy()
    // 返回对象列表(全局)→ URL 无 task_id
    fireEvent.click(screen.getByTestId('evidence-task-middle-back'))
    await waitFor(() => expect(window.location.hash).not.toContain('task_id='))
  })

  it('点击对象 → 工作区(targetResolved);任务名缺失时用中文类型+短ID兜底', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: null })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'i1', target_id: 'c-1', label: 'BLA -> IL', current_confidence: 0.5 })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('BLA -> IL')).toBeTruthy())
    // 任务名缺失 → 「连接任务 #t1」兜底,不再裸显示 connection
    await waitFor(() => expect(screen.getByText(/连接任务 #t1/)).toBeTruthy())
    expect(screen.queryByText('connection')).toBeNull()
    fireEvent.click(screen.getByTestId('evidence-task-object-c-1'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-1'))
  })

  it('全部处理完成 → 空态', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a1', target_id: 'c-done', status: 'completed' })],
    })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-tasks-all-done')).toBeTruthy())
    expect(screen.getByText('全部处理完成')).toBeTruthy()
  })

  it('对象列表加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('boom'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/对象列表加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByTestId('evidence-tasks-all-done')).toBeTruthy())
  })
})
