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
  listEvidenceReviews: vi.fn(),
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

describe('EvidenceTasksModule(中栏任务卡片·统一状态)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('任务卡片显示统一状态(由对象推导):进行中/待审核/已完成,排序按统一状态', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-await', name: '待审核任务', status: 'completed', created_at: '2026-08-13T00:00:00Z' }),
        makeTask({ id: 't-run', name: '进行中任务', status: 'pending', created_at: '2026-08-09T00:00:00Z' }),
        makeTask({ id: 't-done', name: '已完成任务', status: 'pending', created_at: '2026-08-12T00:00:00Z' }),
      ], total: 3,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockImplementation(async (taskId: string) => ({
      items: taskId === 't-await'
        ? [makeItem({ id: 'a1', target_id: 'x1', status: 'awaiting_review' })]
        : taskId === 't-run'
          ? [makeItem({ id: 'b1', target_id: 'x2', status: 'extracting' })]
          : [makeItem({ id: 'c1', target_id: 'x3', status: 'completed' })],
    }))
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('待审核任务')).toBeTruthy())
    // 统一状态徽章:任务级 status(completed/pending)被忽略,由对象推导
    expect(screen.getByText('待审核')).toBeTruthy()
    expect(screen.getByText('进行中')).toBeTruthy()
    expect(screen.getByText('已完成')).toBeTruthy()
    // 排序:进行中 → 待审核 → 已完成
    const cards = Array.from(container.querySelectorAll('[data-testid^="evidence-task-card-"]'))
      .map(el => (el as HTMLElement).dataset.testid ?? '')
      .filter(id => id !== 'evidence-task-card-grid')
    expect(cards).toEqual(['evidence-task-card-t-run', 'evidence-task-card-t-await', 'evidence-task-card-t-done'])
    // 计数:三张卡各有一个「待处理」计数
    expect(screen.getAllByText(/待处理/).length).toBe(3)
  })

  it('任务名缺失 → 中文类型+短ID 兜底', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: null, status: 'pending' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a1', target_id: 'x1', status: 'awaiting_review' })],
    })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('连接任务 #t1')).toBeTruthy())
    expect(screen.queryByText('connection')).toBeNull()
  })

  it('点击任务卡片 → 选中任务(URL 带 task_id)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一', status: 'pending' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a1', target_id: 'x1', status: 'awaiting_review' })],
    })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-t1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=t1'))
  })

  it('选中对象(深链 target) → 中栏工作区,任务卡片隐藏', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一', status: 'pending' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a1', target_id: 'x1', label: 'BLA -> IL', status: 'awaiting_review' })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1&target_type=connection&target_id=x1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.queryByTestId('evidence-task-card-grid')).toBeNull())
  })

  it('无任务 → 空态 + 创建 CTA', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
    expect(screen.getAllByRole('button', { name: '创建批量预处理' }).length).toBeGreaterThanOrEqual(1)
  })

  it('加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('boom'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/任务列表加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
  })
})
