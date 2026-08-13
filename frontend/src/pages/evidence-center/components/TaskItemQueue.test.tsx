import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { TaskItemQueue } from './TaskItemQueue'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTaskItems: vi.fn(),
  reopenPaperEvidenceTaskItem: vi.fn(),
}))

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

describe('TaskItemQueue(待处理区)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockResolvedValue({ task_id: 't1', item_id: 'x', status: 'awaiting_review' })
  })

  it('待处理队列按置信度升序渲染,null 最前;已完成/失败不进队列', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'c-high', label: 'High', current_confidence: 0.9 }),
        makeItem({ id: 'b', target_id: 'c-null', label: 'NoConf', current_confidence: null }),
        makeItem({ id: 'c', target_id: 'c-low', label: 'Low', current_confidence: 0.2 }),
        makeItem({ id: 'd', target_id: 'c-done', status: 'completed', current_confidence: 0.8 }),
        makeItem({ id: 'e', target_id: 'c-fail', status: 'failed', current_confidence: 0.1 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    const { container } = render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('Low')).toBeTruthy())
    expect(queueItemIds(container)).toEqual([
      'evidence-queue-item-c-null', 'evidence-queue-item-c-low', 'evidence-queue-item-c-high',
    ])
    expect(screen.queryByText(/^0\.90$/)).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('筛选 chips:回路/连接/功能分组过滤,计数正确', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'conn-1', target_type: 'connection', label: 'C1', current_confidence: 0.5 }),
        makeItem({ id: 'b', target_id: 'cir-1', target_type: 'circuit_function', label: 'F1', current_confidence: 0.4 }),
        makeItem({ id: 'c', target_id: 'cir-2', target_type: 'circuit_step', label: 'S1', current_confidence: 0.3 }),
        makeItem({ id: 'd', target_id: 'fn-1', target_type: 'region_function', label: 'R1', current_confidence: 0.2 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    const { container } = render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('C1')).toBeTruthy())
    expect(screen.getByRole('button', { name: /^全部/ }).textContent).toContain('4')
    fireEvent.click(screen.getByRole('button', { name: /^回路/ }))
    expect(queueItemIds(container)).toEqual(['evidence-queue-item-cir-2', 'evidence-queue-item-cir-1'])
    fireEvent.click(screen.getByRole('button', { name: /^连接/ }))
    expect(queueItemIds(container)).toEqual(['evidence-queue-item-conn-1'])
    fireEvent.click(screen.getByRole('button', { name: /^功能/ }))
    expect(queueItemIds(container)).toEqual(['evidence-queue-item-fn-1'])
    fireEvent.click(screen.getByRole('button', { name: /^全部/ }))
    expect(queueItemIds(container)).toHaveLength(4)
  })

  it('点击队列条目 → openTarget 保持 tasks 模块', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a', target_id: 'conn-1', label: 'C1', current_confidence: 0.5 })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('C1')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-item-conn-1'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=conn-1'))
    expect(window.location.hash).toContain('task_id=t1')
  })

  it('全部完成 → 空态「全部处理完成」', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'a', target_id: 'c-done', status: 'completed' })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-queue-empty')).toBeTruthy())
    expect(screen.getByText('全部处理完成')).toBeTruthy()
  })

  it('队列加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockRejectedValueOnce(new Error('boom'))
    // 显式设置重试后的成功响应(不依赖前序测试遗留的 mock 实现)
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'r', target_id: 'c-done', status: 'completed' })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/队列加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByTestId('evidence-queue-empty')).toBeTruthy())
  })
})
