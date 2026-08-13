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

describe('EvidenceTasksModule(任务列表视图)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('渲染任务卡片:名称/类型/状态徽章/进度/待审核/创建时间', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ name: '连接佐证A', failed_items: 2 })], total: 1,
    })
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('连接佐证A')).toBeTruthy())
    expect(screen.getByText('connection')).toBeTruthy()
    expect(screen.getByText('待预处理')).toBeTruthy()
    expect(screen.getByText(/已处理/).textContent).toContain('2')
    expect(screen.getByText(/待审核/).textContent).toContain('1')
    expect(screen.getByText(/失败/).textContent).toContain('2')
    expect(container.querySelector('.evidence-task-card-grid')).toBeTruthy()
  })

  it('排序:进行中 → 有等待审核 → 其他,同组内创建时间倒序', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [
        makeTask({ id: 't-old-running', name: '旧进行中', status: 'running', created_at: '2026-08-09T00:00:00Z' }),
        makeTask({ id: 't-done', name: '已完成', status: 'completed', awaiting_review_items: 0, created_at: '2026-08-12T00:00:00Z' }),
        makeTask({ id: 't-await', name: '待审核', status: 'completed', awaiting_review_items: 3, created_at: '2026-08-11T00:00:00Z' }),
        makeTask({ id: 't-new-running', name: '新进行中', status: 'running', created_at: '2026-08-13T00:00:00Z' }),
      ], total: 4,
    })
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('已完成')).toBeTruthy())
    expect(cardOrder(container)).toEqual([
      'evidence-task-card-t-new-running', 'evidence-task-card-t-old-running',
      'evidence-task-card-t-await', 'evidence-task-card-t-done',
    ])
  })

  it('空任务列表:空态 + 创建 CTA', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
    // 工具栏 + 空态操作按钮各一个
    expect(screen.getAllByRole('button', { name: '创建批量预处理' }).length).toBeGreaterThanOrEqual(1)
  })

  it('点击任务卡片 → openTask 进入 tasks 详情(URL 带 task_id、无残留 target,渲染详情视图)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-t1'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=t1'))
    // module=tasks 是 URL 默认值(buildEvidenceUrl 省略默认 module),以详情视图渲染佐证
    expect(window.location.hash).not.toContain('target_id=')
    await waitFor(() => expect(screen.getByTestId('evidence-task-detail-bar')).toBeTruthy())
  })

  it('任务列表加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('boom'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/任务列表加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByText('暂无佐证任务')).toBeTruthy())
  })
})

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

describe('EvidenceTasksModule(任务详情视图)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('进入详情:拉取 items + 自动选中置信度最低(null 最前)的对象', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-high', label: 'High', current_confidence: 0.9 }),
        makeItem({ id: 'i2', target_id: 'c-low', label: 'Low', current_confidence: 0.2 }),
        makeItem({ id: 'i3', target_id: 'c-null', label: 'NoConf', current_confidence: null }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalledWith('t1', { limit: 200 }))
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-null'))
    expect(screen.getByTestId('evidence-task-detail-bar')).toBeTruthy()
  })

  it('URL 已带本任务未完成 target 时不覆盖', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-a', label: 'A', current_confidence: 0.9 }),
        makeItem({ id: 'i2', target_id: 'c-b', label: 'B', current_confidence: null }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1&target_type=connection&target_id=c-a'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalled())
    await waitFor(() => expect(window.location.hash).toContain('target_id=c-a'))
    expect(window.location.hash).not.toContain('target_id=c-b')
  })

  it('全部完成时不嵌入候选组件:主区显示全部处理完成空态,URL 不带 target', async () => {
    // 全部完成时主区不挂载候选组件(其 URL 同步副作用会切走 module),展示空态;
    // 回退重审入口在右栏已完成区(Task 5/6 接入)
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c-a', status: 'completed', current_confidence: 0.9 }),
        makeItem({ id: 'i2', target_id: 'c-b', status: 'completed', current_confidence: 0.2 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByTestId('evidence-tasks-all-done')).toBeTruthy())
    expect(screen.getByText('全部处理完成')).toBeTruthy()
    await new Promise(r => setTimeout(r, 0))
    expect(window.location.hash).not.toContain('target_id=')
  })
})
