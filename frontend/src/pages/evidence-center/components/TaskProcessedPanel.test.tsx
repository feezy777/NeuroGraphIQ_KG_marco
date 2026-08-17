import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { ApiError } from '../../../api/client'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { TaskItemsRefreshProvider, useTaskItemsRefresh } from './taskItemsRefreshContext'
import { TaskProcessedPanel } from './TaskProcessedPanel'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  reopenPaperEvidenceTaskItem: vi.fn(),
  listEvidenceReviews: vi.fn(),
  rollbackReviewForRescore: vi.fn(),
  getReviewHistory: vi.fn(),
}))

/** 一对一任务 fixture:任务即对象(item_id/target_id/display/work_status 由列表接口返回) */
function makeTask(overrides: Record<string, unknown>) {
  return {
    id: 't1', target_type: 'connection', target_id: 'conn', item_id: 'it', name: null, status: 'pending',
    total_items: 1, processed_items: 1, awaiting_review_items: 0, failed_items: 0,
    review_status: 'not_started', granularity_level: 'macro', estimated_target_count: 1,
    materialized_target_count: 1, scope: 'filter', mode: 'existence', max_papers_per_object: 3,
    created_at: '2026-08-10T00:00:00Z', created_by: null, started_at: null, finished_at: '2026-08-12T00:00:00Z',
    error_message: null, materialization_status: 'completed', materialization_cursor: null,
    materialization_error: null, confidence_lt: null, only_oa: false,
    stop_after_strong_support: false, summary: null, scope_type: 'filter',
    filter_snapshot: null, versions: null,
    display_name_cn: null, display_name_en: null, display_confidence: 0.5,
    display_name_source: 'mirror_live', display_confidence_source: 'mirror_live',
    work_status: 'completed',
    item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 0, completed: 1, skipped: 0, failed: 0, cancelled: 0 },
    capabilities: { can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: true },
    ...overrides,
  }
}

function makeReview(overrides: Record<string, unknown>) {
  return {
    id: 'r1', target_type: 'connection', target_id: 'tgt-1', paper_id: null,
    task_id: null, task_item_id: null, reviewer_id: null,
    review_status: 'approved', promotion_status: 'not_ready', claim_version: null,
    claim_text_snapshot: null,
    claim_components_snapshot: [
      { component_type: 'source_region', statement: '', required: true, metadata: { name_cn: '右丘脑本体', name_en: 'right thalamus proper' } },
      { component_type: 'target_region', statement: '', required: true, metadata: { name_cn: '右壳核', name_en: 'right putamen' } },
    ],
    model_direction: null, model_assessment: null, reviewer_direction: null,
    reviewer_evidence_level: null, reviewer_confidence: 0.8, reviewer_note: null,
    coverage_summary_snapshot: null, coverage_formula_version: null,
    reviewed_at: '2026-08-12T10:00:00Z', approved_at: '2026-08-12T11:00:00Z',
    rejected_at: null, promoted_at: null, promoted_by: null,
    returned_at: null, returned_by: null, return_reason: null,
    evidence_id: null, created_at: '2026-08-12T09:00:00Z', updated_at: '2026-08-12T11:00:00Z',
    draft_revision: 0,
    // S7B 版本链与派生字段
    revision_no: 1, supersedes_review_id: null, superseded_at: null,
    superseded_by: null, rollback_reason: null, is_current: true,
    effective_promotion_status: 'not_promoted',
    can_rollback_rescore: true, rollback_block_reason: null,
    ...overrides,
  }
}

describe('TaskProcessedPanel(右栏已处理:任务即对象,数据来自任务列表)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockResolvedValue({ task_id: 't1', item_id: 'x', status: 'awaiting_review' })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.rollbackReviewForRescore).mockResolvedValue({
      source_review_id: 'r1', new_review_id: null, task_id: 'ta', task_item_id: 'a1',
      target_type: 'connection', target_id: 'tgt-1', revision_no: 2,
      promotion_rollback: 'not_needed',
      navigation: { module: 'tasks', task_id: 'ta', task_item_id: 'a1', target_type: 'connection', target_id: 'tgt-1' },
    })
    vi.mocked(endpoints.getReviewHistory).mockResolvedValue({ source_review_id: 'r1', items: [] })
  })

  it('展示已完成/失败对象,按完成时间倒序,待处理不进面板', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 'ta', target_id: 'done-old', item_id: 'a', display_name_cn: 'Old', finished_at: '2026-08-09T00:00:00Z' }),
        makeTask({ id: 'tb', target_id: 'done-new', item_id: 'b', display_name_cn: 'New', finished_at: '2026-08-12T00:00:00Z' }),
        makeTask({ id: 'tc', target_id: 'fail-1', item_id: 'c', display_name_cn: 'Fail', work_status: 'failed', item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 0, completed: 0, skipped: 0, failed: 1, cancelled: 0 }, finished_at: '2026-08-11T00:00:00Z' }),
        makeTask({ id: 'td', target_id: 'live', item_id: 'd', display_name_cn: 'Live', work_status: 'awaiting_review', item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 } }),
      ], total: 4,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('New')).toBeTruthy())
    const ids = Array.from(container.querySelectorAll('[data-testid^="evidence-processed-item-"]'))
      .map(el => (el as HTMLElement).dataset.testid ?? '')
    expect(ids).toEqual(['evidence-processed-item-done-new', 'evidence-processed-item-fail-1', 'evidence-processed-item-done-old'])
    expect(screen.queryByText('Live')).toBeNull()
    expect(screen.getByText('失败')).toBeTruthy()
  })

  it('「重新打开任务项」两步确认:第二次调用 reopen 并刷新(无终态 review 才开放)', async () => {
    // 挂载一次(reopen 前)+ reload 一次(reopen 后任务消失 → 空态)
    vi.mocked(endpoints.listPaperEvidenceTasks)
      .mockResolvedValueOnce({ items: [makeTask({ id: 'ta', target_id: 'done-1', item_id: 'b', display_name_cn: 'D1' })], total: 1 })
      .mockResolvedValueOnce({ items: [], total: 0 })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('D1')).toBeTruthy())
    const btn = () => screen.getByTestId('evidence-queue-reopen-done-1')
    expect(btn().textContent).toContain('重新打开任务项')
    fireEvent.click(btn())
    expect(btn().textContent).toContain('确认重新打开?')
    fireEvent.click(btn())
    await waitFor(() => expect(vi.mocked(endpoints.reopenPaperEvidenceTaskItem)).toHaveBeenCalledWith('ta', 'b'))
    await waitFor(() => expect(screen.getByTestId('evidence-processed-empty')).toBeTruthy())
  })

  it('重新打开接口失败 → 错误提示,面板不变', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'done-1', item_id: 'b', display_name_cn: 'D1' })], total: 1,
    })
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockRejectedValueOnce(new Error('boom'))
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('D1')).toBeTruthy())
    const btn = () => screen.getByTestId('evidence-queue-reopen-done-1')
    fireEvent.click(btn())
    fireEvent.click(btn())
    await waitFor(() => expect(screen.getByText(/重新打开失败/)).toBeTruthy())
    expect(screen.getByTestId('evidence-processed-item-done-1')).toBeTruthy()
  })

  it('无已处理对象 → 空态', async () => {
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-processed-empty')).toBeTruthy())
  })

  it('任务审核:review 带 task_item_id 精确关联 item,显示真实中文名/结论/关联类型/审核时间', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1', review_status: 'approved', promotion_status: 'promoted' })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    expect(screen.getByText('已晋升')).toBeTruthy()
    expect(screen.getByTestId('evidence-processed-item-tgt-1-link-kind').textContent).toBe('任务审核')
    expect(screen.getByTestId('evidence-processed-item-tgt-1-review-time').textContent).toContain('审核时间')
    // 终态 review 关联的 completed item 不显示旧 reopen 入口(十一.3)
    expect(screen.queryByTestId('evidence-queue-reopen-tgt-1')).toBeNull()
    // S7B:capability=true → 显示「回退并重新评分」按钮
    expect(screen.getByTestId('evidence-rollback-rescore-r1')).toBeTruthy()
  })

  it('历史未关联:review 缺 task_item_id 但有 task_id → task_id+target 兼容关联并标记', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: null, review_status: 'rejected' })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    expect(screen.getByTestId('evidence-processed-item-tgt-1-link-kind').textContent).toBe('历史未关联')
    expect(screen.getByTestId('evidence-processed-item-tgt-1-review-status').textContent).toBe('已驳回')
    // 历史未关联也有终态 review → 不开放旧 reopen(十一.3/9)
    expect(screen.queryByTestId('evidence-queue-reopen-tgt-1')).toBeNull()
  })

  it('独立审核:task_id/task_item_id 均为空的 review 以 review.id 单独成卡,不归属任何任务', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1', work_status: 'awaiting_review', item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 } })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r1', target_id: 'tgt-1', task_id: null, task_item_id: null, review_status: 'approved', promotion_status: 'promoted' })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    expect(screen.getByTestId('evidence-standalone-review-r1')).toBeTruthy()
    expect(screen.getByTestId('evidence-standalone-review-r1-link-kind').textContent).toBe('独立审核')
    expect(screen.getByText('已晋升')).toBeTruthy()
  })

  it('同 target 多 review 不互相覆盖:任务只取自身 item_id 的 review', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 'ta', target_id: 'same-tgt', item_id: 'a1', display_name_cn: 'ItemA', finished_at: '2026-08-11T00:00:00Z' }),
        makeTask({ id: 'tb', target_id: 'same-tgt', item_id: 'b1', display_name_cn: 'ItemB', finished_at: '2026-08-12T00:00:00Z' }),
      ], total: 2,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [
        makeReview({ id: 'r-a', target_id: 'same-tgt', task_id: 'ta', task_item_id: 'a1', review_status: 'approved', claim_components_snapshot: null }),
        makeReview({ id: 'r-b', target_id: 'same-tgt', task_id: 'tb', task_item_id: 'b1', review_status: 'rejected', claim_components_snapshot: null }),
      ],
      total: 2,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('ItemA')).toBeTruthy())
    // 每个对象只显示自己的结论,不互相套用(九.8)
    const linkKinds = screen.getAllByTestId(/evidence-processed-item-same-tgt-link-kind/)
    expect(linkKinds).toHaveLength(2)
    linkKinds.forEach(el => expect(el.textContent).toBe('任务审核'))
    const reviewStatuses = screen.getAllByTestId(/evidence-processed-item-same-tgt-review-status/)
    expect(reviewStatuses).toHaveLength(2)
    expect(reviewStatuses[0].textContent).not.toBe(reviewStatuses[1].textContent)
    expect(screen.getByText('已审核')).toBeTruthy()
    expect(screen.getByText('已驳回')).toBeTruthy()
  })

  it('同 item 多条 review:默认最新终态 + 历史数量提示', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [
        makeReview({ id: 'r-old', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1', review_status: 'rejected', approved_at: null, rejected_at: '2026-08-10T10:00:00Z' }),
        makeReview({ id: 'r-new', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1', review_status: 'approved', rejected_at: null, approved_at: '2026-08-12T10:00:00Z' }),
      ],
      total: 2,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    expect(screen.getByTestId('evidence-processed-item-tgt-1-review-status').textContent).toBe('已审核')
    expect(screen.getByTestId('evidence-processed-item-tgt-1-review-time').textContent).toContain('另有 1 条历史审核')
  })

  it('点击已处理对象 → 携带其真实 task_item_id 与来源任务(不猜测其他任务)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 'ta', target_id: 'done-1', item_id: 'a', display_name_cn: 'D1' }),
        makeTask({ id: 'tb', target_id: 'other', item_id: 'b2', display_name_cn: 'Other', work_status: 'awaiting_review', item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 } }),
      ], total: 2,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('D1')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-processed-item-done-1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=ta'))
    expect(window.location.hash).toContain('target_id=done-1')
    expect(window.location.hash).toContain('task_item_id=a')
    expect(window.location.hash).not.toContain('task_id=tb')
  })

  // ─── S7B:回退并重新评分 ───

  function RefreshProbe() {
    const { version } = useTaskItemsRefresh()
    return <span data-testid="refresh-version">{version}</span>
  }

  function renderWithRefresh() {
    return render(
      <TaskItemsRefreshProvider>
        <EvidenceCenterProvider>
          <TaskProcessedPanel />
          <RefreshProbe />
        </EvidenceCenterProvider>
      </TaskItemsRefreshProvider>,
    )
  }

  it('capability 门控:can_rollback_rescore=false 不显示回退按钮,显示 block reason 文案', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({
        id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1',
        review_status: 'approved', can_rollback_rescore: false, rollback_block_reason: 'NO_TASK_ITEM',
      })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    expect(screen.queryByTestId('evidence-rollback-rescore-r1')).toBeNull()
    expect(screen.getByTestId('evidence-processed-item-tgt-1-rollback-hint').textContent).toContain('找不到关联的任务项')
  })

  it('回退弹窗:内容齐全;空原因不能提交;填原因提交调 API 并携带 idempotency_key', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1', review_status: 'approved' })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-rollback-rescore-r1'))
    await waitFor(() => expect(screen.getByTestId('rollback-rescore-dialog')).toBeTruthy())
    expect(screen.getByText('第 1 次评分')).toBeTruthy()
    expect(screen.getByText(/已审核通过/)).toBeTruthy()
    // 空原因提交 → 不调 API + 明确错误
    fireEvent.click(within(screen.getByTestId('rollback-rescore-dialog')).getByRole('button', { name: '回退并重新评分' }))
    fireEvent.click(screen.getByTestId('rollback-reason-input'))
    fireEvent.click(within(screen.getByTestId('rollback-rescore-dialog')).getByRole('button', { name: '回退并重新评分' }))
    await waitFor(() => expect(screen.getByTestId('rollback-reason-error')).toBeTruthy())
    expect(endpoints.rollbackReviewForRescore).not.toHaveBeenCalled()
    // 填原因提交
    fireEvent.change(screen.getByTestId('rollback-reason-input'), { target: { value: '结论有误' } })
    fireEvent.click(within(screen.getByTestId('rollback-rescore-dialog')).getByRole('button', { name: '回退并重新评分' }))
    await waitFor(() =>
      expect(endpoints.rollbackReviewForRescore).toHaveBeenCalledWith('r1', {
        reason: '结论有误',
        idempotency_key: expect.any(String),
      }),
    )
  })

  it('回退成功:共享刷新 + 按 navigation 原子导航(URL 含稳定参数)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1', review_status: 'approved' })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    renderWithRefresh()
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    expect(screen.getByTestId('refresh-version').textContent).toBe('0')
    fireEvent.click(screen.getByTestId('evidence-rollback-rescore-r1'))
    fireEvent.change(screen.getByTestId('rollback-reason-input'), { target: { value: '重新评分' } })
    fireEvent.click(within(screen.getByTestId('rollback-rescore-dialog')).getByRole('button', { name: '回退并重新评分' }))
    await waitFor(() => expect(endpoints.rollbackReviewForRescore).toHaveBeenCalled())
    // 刷新版本递增 + 导航到任务工作区(URL 稳定参数齐全)
    await waitFor(() => expect(screen.getByTestId('refresh-version').textContent).toBe('1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=ta'))
    expect(window.location.hash).toContain('task_item_id=a1')
    expect(window.location.hash).toContain('target_type=connection')
    expect(window.location.hash).toContain('target_id=tgt-1')
  })

  it('promoted 警告:弹窗显示已晋升且当前有效', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({
        id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1',
        review_status: 'approved', promotion_status: 'promoted', effective_promotion_status: 'active',
      })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-rollback-rescore-r1'))
    await waitFor(() => expect(screen.getByText('已晋升为正式证据(当前有效)')).toBeTruthy())
    expect(screen.getByText(/回退后将撤销当前生效的正式证据/)).toBeTruthy()
  })

  it('409(已被他人回退)→ 关闭弹窗、共享刷新并提示', async () => {
    vi.mocked(endpoints.rollbackReviewForRescore).mockRejectedValueOnce(
      new ApiError(409, 'HTTP 409: {"code":"REVIEW_ALREADY_SUPERSEDED","message":"..."}'),
    )
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1', review_status: 'approved' })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    renderWithRefresh()
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-rollback-rescore-r1'))
    fireEvent.change(screen.getByTestId('rollback-reason-input'), { target: { value: 'x' } })
    fireEvent.click(within(screen.getByTestId('rollback-rescore-dialog')).getByRole('button', { name: '回退并重新评分' }))
    await waitFor(() => expect(screen.getByTestId('refresh-version').textContent).toBe('1'))
    expect(screen.queryByTestId('rollback-rescore-dialog')).toBeNull()
    expect(screen.getByText(/状态已变化/)).toBeTruthy()
  })

  it('403 与网络错误在弹窗内反馈', async () => {
    vi.mocked(endpoints.rollbackReviewForRescore).mockRejectedValueOnce(
      new ApiError(403, 'HTTP 403'),
    )
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1', review_status: 'approved' })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-rollback-rescore-r1'))
    fireEvent.change(screen.getByTestId('rollback-reason-input'), { target: { value: 'x' } })
    fireEvent.click(within(screen.getByTestId('rollback-rescore-dialog')).getByRole('button', { name: '回退并重新评分' }))
    await waitFor(() => expect(screen.getByTestId('rollback-submit-error').textContent).toContain('没有权限'))
  })

  it('曾晋升已撤销:显示「曾晋升，现已撤销」,superseded 版本无回退按钮并提示已回退', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({
        id: 'r1', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1',
        review_status: 'approved', promotion_status: 'promoted', effective_promotion_status: 'rolled_back',
        revision_no: 1, superseded_at: '2026-08-13T00:00:00Z', superseded_by: 'reviewer-1',
        rollback_reason: '重新评分', is_current: false, can_rollback_rescore: false,
        rollback_block_reason: 'ALREADY_SUPERSEDED',
      })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    expect(screen.getByTestId('evidence-processed-item-tgt-1-rolled-back').textContent).toContain('曾晋升，现已撤销')
    expect(screen.queryByTestId('evidence-rollback-rescore-r1')).toBeNull()
    expect(screen.getByTestId('evidence-processed-item-tgt-1-rollback-hint').textContent).toContain('已回退(历史版本)')
  })

  it('历史抽屉:点击查看审核历史 → 只读列表(当前/已回退/原因/曾晋升已撤销)', async () => {
    vi.mocked(endpoints.getReviewHistory).mockResolvedValue({
      source_review_id: 'r2',
      items: [
        {
          review_id: 'r1', revision_no: 1, review_status: 'approved', promotion_status: 'promoted',
          effective_promotion_status: 'rolled_back', reviewer_direction: 'supports', reviewer_confidence: 0.8,
          reviewed_at: null, approved_at: '2026-08-12T11:00:00Z', rejected_at: null,
          is_current: false, superseded_at: '2026-08-13T00:00:00Z', superseded_by: 'reviewer-1',
          rollback_reason: '结论有误',
        },
        {
          review_id: 'r2', revision_no: 2, review_status: 'approved', promotion_status: 'not_ready',
          effective_promotion_status: 'not_promoted', reviewer_direction: 'partial', reviewer_confidence: 0.6,
          reviewed_at: null, approved_at: '2026-08-13T10:00:00Z', rejected_at: null,
          is_current: true, superseded_at: null, superseded_by: null, rollback_reason: null,
        },
      ],
    })
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 'ta', target_id: 'tgt-1', item_id: 'a1' })], total: 1,
    })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r2', target_id: 'tgt-1', task_id: 'ta', task_item_id: 'a1', review_status: 'approved', revision_no: 2 })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('右丘脑本体 → 右壳核')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-review-history-r2'))
    await waitFor(() => expect(screen.getByTestId('review-history-drawer')).toBeTruthy())
    expect(endpoints.getReviewHistory).toHaveBeenCalledWith('r2')
    const drawer = within(screen.getByTestId('review-history-drawer'))
    expect(drawer.getByText('第 1 次评分')).toBeTruthy()
    expect(drawer.getByText('第 2 次评分')).toBeTruthy()
    expect(drawer.getByText('当前版本')).toBeTruthy()
    expect(drawer.getByText(/回退原因:结论有误/)).toBeTruthy()
    expect(drawer.getByText('曾晋升，现已撤销')).toBeTruthy()
  })

  it('standalone 回退:成功后导航到新任务(响应 navigation 的新 task_id)', async () => {
    vi.mocked(endpoints.rollbackReviewForRescore).mockResolvedValue({
      source_review_id: 'r1', new_review_id: null, task_id: 'new-task-1', task_item_id: 'new-item-1',
      target_type: 'connection', target_id: 'tgt-1', revision_no: 2,
      promotion_rollback: 'not_needed',
      navigation: { module: 'tasks', task_id: 'new-task-1', task_item_id: 'new-item-1', target_type: 'connection', target_id: 'tgt-1' },
    })
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({
      items: [makeReview({ id: 'r1', target_id: 'tgt-1', task_id: null, task_item_id: null, review_status: 'approved' })],
      total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterProvider><TaskProcessedPanel /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-standalone-review-r1')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-rollback-rescore-r1'))
    fireEvent.change(screen.getByTestId('rollback-reason-input'), { target: { value: '重评' } })
    fireEvent.click(within(screen.getByTestId('rollback-rescore-dialog')).getByRole('button', { name: '回退并重新评分' }))
    await waitFor(() => expect(window.location.hash).toContain('task_id=new-task-1'))
    expect(window.location.hash).toContain('task_item_id=new-item-1')
    expect(window.location.hash).toContain('target_id=tgt-1')
  })
})
