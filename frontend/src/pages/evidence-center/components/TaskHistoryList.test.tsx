import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { TaskHistoryList } from './TaskHistoryList'

vi.mock('../../../api/endpoints', () => ({
  listEvidenceTaskHistory: vi.fn(),
  rollbackReviewForRescore: vi.fn(),
}))

const HISTORY_ITEM = {
  task_id: 'ta-1111',
  target_type: 'connection',
  name: 'Thalamus proper → Precentral',
  status: 'completed',
  created_by: 'admin',
  started_at: '2026-08-25T08:00:00Z',
  finished_at: '2026-08-25T10:00:00Z',
  deleted_at: null,
  review_status: 'in_review',
  granularity_level: 'macro',
  review_brief: {
    last_reviewed_at: '2026-08-25T09:30:00Z',
    reviewer_id: 'reviewer-a',
    review_status: 'approved',
    promotion_status: 'promoted',
    latest_review_id: 'rv-1',
    has_superseded: false,
    review_count: 2,
  },
}

describe('TaskHistoryList(历史任务 + Rollback)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listEvidenceTaskHistory).mockResolvedValue({
      total: 1, limit: 100, offset: 0, items: [HISTORY_ITEM],
    })
    vi.mocked(endpoints.rollbackReviewForRescore).mockResolvedValue({} as never)
  })
  afterEach(() => { cleanup(); sessionStorage.clear() })

  it('渲染历史行:对象/最终状态/审核时间/审核人/审核次数/Final KG 状态', async () => {
    render(<TaskHistoryList />)
    const row = await screen.findByTestId('history-row-ta-1111')
    expect(row.textContent).toContain('Thalamus proper → Precentral')
    expect(row.textContent).toContain('已晋升')
    expect(row.textContent).toContain('reviewer-a')
    expect(row.textContent).toContain('已晋升 Final KG')
    expect(row.textContent).toContain('2')
  })

  it('Rollback:弹窗 → 选择原因 → 调用 rollbackReviewForRescore(review_id)', async () => {
    render(<TaskHistoryList />)
    fireEvent.click(await screen.findByTestId('history-rollback-ta-1111'))
    // 弹窗:原因枚举
    await waitFor(() => expect(screen.getByText('Rollback Reason:')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('回退原因'), { target: { value: 'Evidence insufficient' } })
    fireEvent.click(screen.getByText('确认回退'))
    await waitFor(() =>
      expect(vi.mocked(endpoints.rollbackReviewForRescore))
        .toHaveBeenCalledWith('rv-1', { reason: 'Evidence insufficient' }))
    // 回退后列表刷新(历史端点再次调用)
    await waitFor(() => expect(vi.mocked(endpoints.listEvidenceTaskHistory).mock.calls.length).toBeGreaterThanOrEqual(2))
  })

  it('已回退历史行显示「已回退」(superseded 标记)', async () => {
    vi.mocked(endpoints.listEvidenceTaskHistory).mockResolvedValue({
      total: 1, limit: 100, offset: 0,
      items: [{ ...HISTORY_ITEM, review_brief: { ...HISTORY_ITEM.review_brief, has_superseded: true } }],
    })
    render(<TaskHistoryList />)
    const row = await screen.findByTestId('history-row-ta-1111')
    expect(row.textContent).toContain('已回退')
  })
})
