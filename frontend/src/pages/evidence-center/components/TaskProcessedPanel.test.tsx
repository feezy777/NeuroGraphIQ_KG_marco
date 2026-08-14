import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { TaskProcessedPanel } from './TaskProcessedPanel'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  reopenPaperEvidenceTaskItem: vi.fn(),
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

describe('TaskProcessedPanel(右栏已处理)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockResolvedValue({ task_id: 't1', item_id: 'x', status: 'awaiting_review' })
  })

  it('展示已完成/失败/跳过对象,按完成时间倒序,待处理不进面板', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'done-old', label: 'Old', status: 'completed', updated_at: '2026-08-09T00:00:00Z' }),
        makeItem({ id: 'b', target_id: 'done-new', label: 'New', status: 'completed', updated_at: '2026-08-12T00:00:00Z' }),
        makeItem({ id: 'c', target_id: 'fail-1', label: 'Fail', status: 'failed', updated_at: '2026-08-11T00:00:00Z' }),
        makeItem({ id: 'd', target_id: 'live', label: 'Live', status: 'awaiting_review' }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('New')).toBeTruthy())
    const ids = Array.from(container.querySelectorAll('[data-testid^="evidence-processed-item-"]'))
      .map(el => (el as HTMLElement).dataset.testid ?? '')
    expect(ids).toEqual(['evidence-processed-item-done-new', 'evidence-processed-item-fail-1', 'evidence-processed-item-done-old'])
    expect(screen.queryByText('Live')).toBeNull()
    expect(screen.getByText('预处理失败')).toBeTruthy()
  })

  it('回退两步确认:第一次点击变确认态,第二次调用 reopen 并刷新', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems)
      .mockResolvedValueOnce({
        items: [makeItem({ id: 'b', target_id: 'done-1', label: 'D1', status: 'completed', updated_at: '2026-08-12T00:00:00Z' })],
      })
      .mockResolvedValueOnce({
        items: [makeItem({ id: 'b', target_id: 'done-1', label: 'D1', status: 'awaiting_review', current_confidence: 0.6 })],
      })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('D1')).toBeTruthy())
    const btn = () => screen.getByTestId('evidence-queue-reopen-done-1')
    fireEvent.click(btn())
    expect(btn().textContent).toContain('确认回退?')
    fireEvent.click(btn())
    await waitFor(() => expect(vi.mocked(endpoints.reopenPaperEvidenceTaskItem)).toHaveBeenCalledWith('ta', 'b'))
    await waitFor(() => expect(screen.getByTestId('evidence-processed-empty')).toBeTruthy())
  })

  it('回退接口失败 → 错误提示,面板不变', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'b', target_id: 'done-1', label: 'D1', status: 'completed', updated_at: '2026-08-12T00:00:00Z' })],
    })
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockRejectedValueOnce(new Error('boom'))
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('D1')).toBeTruthy())
    const btn = () => screen.getByTestId('evidence-queue-reopen-done-1')
    fireEvent.click(btn())
    fireEvent.click(btn())
    await waitFor(() => expect(screen.getByText(/回退失败/)).toBeTruthy())
    expect(screen.getByTestId('evidence-processed-item-done-1')).toBeTruthy()
  })

  it('无已处理对象 → 空态', async () => {
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-processed-empty')).toBeTruthy())
  })
})
