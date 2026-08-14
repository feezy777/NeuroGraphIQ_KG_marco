import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { TaskPendingQueue } from './TaskPendingQueue'

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

function queueItemIds(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('[data-testid^="evidence-queue-item-"]'))
    .map(el => (el as HTMLElement).dataset.testid ?? '')
}

describe('TaskPendingQueue(左栏待处理)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockResolvedValue({ task_id: 't1', item_id: 'x', status: 'awaiting_review' })
  })

  it('置信度升序(null 最前),已完成/失败不进队列', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'c-high', label: 'High', current_confidence: 0.9 }),
        makeItem({ id: 'b', target_id: 'c-null', label: 'NoConf', current_confidence: null }),
        makeItem({ id: 'c', target_id: 'c-low', label: 'Low', current_confidence: 0.2 }),
        makeItem({ id: 'd', target_id: 'c-done', status: 'completed', current_confidence: 0.8 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterProvider><TaskPendingQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('Low')).toBeTruthy())
    expect(queueItemIds(container)).toEqual([
      'evidence-queue-item-c-null', 'evidence-queue-item-c-low', 'evidence-queue-item-c-high',
    ])
  })

  it('筛选 chips:回路/连接/功能分组过滤', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'conn-1', target_type: 'connection', label: 'C1', current_confidence: 0.5 }),
        makeItem({ id: 'b', target_id: 'cir-1', target_type: 'circuit_function', label: 'F1', current_confidence: 0.4 }),
        makeItem({ id: 'd', target_id: 'fn-1', target_type: 'region_function', label: 'R1', current_confidence: 0.2 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterProvider><TaskPendingQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('C1')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /^回路/ }))
    expect(queueItemIds(container)).toEqual(['evidence-queue-item-cir-1'])
    fireEvent.click(screen.getByRole('button', { name: /^全部/ }))
    expect(queueItemIds(container)).toHaveLength(3)
  })

  it('点击待处理对象 → 选中来源任务并打开对象(URL 带 task_id 与 target)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a', target_id: 'c-1', label: 'C1', current_confidence: 0.4 })],
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskPendingQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('C1')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-item-c-1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=ta'))
    expect(window.location.hash).toContain('target_id=c-1')
  })

  it('无待处理对象 → 空态提示去右侧已处理区', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'd', target_id: 'c-done', status: 'completed' })],
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskPendingQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-queue-empty')).toBeTruthy())
    expect(screen.getByText('全部处理完成')).toBeTruthy()
  })

  it('加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('boom'))
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskPendingQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/队列加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByTestId('evidence-queue-empty')).toBeTruthy())
  })
it('任务级 status 不作为过滤条件:completed 任务的待审对象也进队列', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 'ta', name: '任务A', status: 'completed' }),
        makeTask({ id: 'tc', name: '任务C', status: 'cancelled', total_items: 5 }),
        makeTask({ id: 'te', name: '任务E', status: 'pending', total_items: 0 }),
      ], total: 3,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockImplementation(async (taskId: string) => ({
      items: taskId === 'ta'
        ? [makeItem({ id: 'a1', target_id: 'c-1', label: 'BLA -> IL', current_confidence: 0.4 })]
        : [],
    }))
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskPendingQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('BLA -> IL')).toBeTruthy())
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalledWith('ta', { limit: 100 })
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).not.toHaveBeenCalledWith('tc', { limit: 100 })
    expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).not.toHaveBeenCalledWith('te', { limit: 100 })
  })

  it('label 为裸 UUID 时显示「类型中文 #短ID」兜底', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', name: '任务A', status: 'running' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a1', target_id: '4bd7092b-f65b-49c8-81f7-ebf8d896c152', label: '4bd7092b-f65b-49c8-81f7-ebf8d896c152', current_confidence: 0.4 }),
        makeItem({ id: 'a2', target_id: 'x1', target_type: 'circuit', label: '默认模式网络', current_confidence: 0.3 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskPendingQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('默认模式网络')).toBeTruthy())
    expect(screen.getByText('连接 #4bd7092b')).toBeTruthy()
    expect(screen.queryByText('4bd7092b-f65b-49c8-81f7-ebf8d896c152')).toBeNull()
  })
})
