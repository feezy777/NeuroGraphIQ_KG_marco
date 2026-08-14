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

function cardOrder(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('[data-testid^="evidence-task-card-"]'))
    .map(el => (el as HTMLElement).dataset.testid ?? '')
    .filter(id => id !== 'evidence-task-card-grid')
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

describe('EvidenceTasksModule(单页三栏·中栏)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('态① 无 taskId:任务卡片网格 + 进行中置顶排序', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-old', name: '旧进行中', status: 'running', created_at: '2026-08-09T00:00:00Z' }),
        makeTask({ id: 't-done', name: '已完成', status: 'completed', awaiting_review_items: 0, created_at: '2026-08-12T00:00:00Z' }),
        makeTask({ id: 't-new', name: '新进行中', status: 'running', created_at: '2026-08-13T00:00:00Z' }),
      ], total: 3,
    })
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('已完成')).toBeTruthy())
    expect(cardOrder(container)).toEqual([
      'evidence-task-card-t-new', 'evidence-task-card-t-old', 'evidence-task-card-t-done',
    ])
  })

  it('态① 空任务列表 → 空态 + 创建 CTA', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
    expect(screen.getAllByRole('button', { name: '创建批量预处理' }).length).toBeGreaterThanOrEqual(1)
  })

  it('态① 加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('boom'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/任务列表加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
  })

  it('点任务卡片 → 自动选中置信度最低(null 最前)对象,进入工作区', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-high', label: 'High', current_confidence: 0.9 }),
        makeItem({ id: 'i2', target_id: 'c-done', label: 'Done', status: 'completed', current_confidence: 0.8 }),
        makeItem({ id: 'i3', target_id: 'c-null', label: 'NoConf', current_confidence: null }),
      ],
    })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-t1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=t1'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-null'))
  })

  it('全部完成任务:不自动选中,态② 对象卡片;点对象卡片 → 态③ 工作区', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-done', label: 'DoneA', status: 'completed', current_confidence: 0.8 }),
        makeItem({ id: 'i2', target_id: 'c-done2', label: 'DoneB', status: 'completed', current_confidence: 0.6 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-task-object-c-done')).toBeTruthy())
    await waitFor(() => expect(window.location.hash).not.toContain('target_id='))
    fireEvent.click(screen.getByTestId('evidence-task-object-c-done'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-done'))
    // 刷新 items 后不得把用户从已完成对象工作区拽走
    fireEvent.click(screen.getByRole('button', { name: '刷新' }))
    await waitFor(() => expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalledTimes(3))
    await new Promise(r => setTimeout(r, 0))
    expect(window.location.hash).toContain('target_id=c-done')
  })

  it('任务无对象 → 中栏空态,无 target', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-tasks-all-done')).toBeTruthy())
    await waitFor(() => expect(window.location.hash).not.toContain('target_id='))
  })

  it('点对象卡片(未完成任务,深链带 target 不符) → 自动选中纠正', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-a', label: 'A', current_confidence: 0.5 }),
        makeItem({ id: 'i2', target_id: 'c-b', label: 'B', current_confidence: 0.3 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1&target_type=connection&target_id=stale'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    // stale target 不在 items → 自动选中纠正为置信度最低 c-b
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-b'))
    expect(window.location.hash).not.toContain('stale')
  })

  it('「← 任务列表」→ 回态①(URL 无 task_id)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-task-middle-back')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-middle-back'))
    await waitFor(() => expect(window.location.hash).not.toContain('task_id='))
    expect(screen.getByText('任务一')).toBeTruthy()
  })
})
