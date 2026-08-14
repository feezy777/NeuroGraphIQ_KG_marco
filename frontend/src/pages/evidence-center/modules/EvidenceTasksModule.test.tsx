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

describe('EvidenceTasksModule(中栏工作区)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
  })

  it('未选对象 → 中栏提示从左侧选择', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-tasks-no-target')).toBeTruthy())
    expect(screen.getByText(/点击左侧待处理对象/)).toBeTruthy()
  })

  it('选中对象(深链 target) → 中栏挂载证据候选工作区', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'i1', target_id: 'c-1', label: 'BLA -> IL', current_confidence: 0.5 })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1&target_type=connection&target_id=c-1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.queryByTestId('evidence-tasks-no-target')).toBeNull())
    // 候选组件挂载(其自身空态/内容由候选模块负责)
    expect(screen.queryByTestId('evidence-tasks-no-target')).toBeNull()
  })

  it('任务名缺失 → 工具栏用「连接任务 #短ID」兜底,不裸显示 connection', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: null })], total: 1,
    })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'i1', target_id: 'c-1', label: 'BLA -> IL', current_confidence: 0.5 })],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1&target_type=connection&target_id=c-1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/连接任务 #t1/)).toBeTruthy())
    expect(screen.queryByText('connection')).toBeNull()
  })

  it('「← 返回全局」→ 清 taskId(URL 无 task_id)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't1', name: '任务一' })], total: 1,
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-task-middle-back')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-middle-back'))
    await waitFor(() => expect(window.location.hash).not.toContain('task_id='))
  })

  it('对象列表加载失败 → 错误 + 重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('boom'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/对象列表加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByTestId('evidence-tasks-no-target')).toBeTruthy())
  })
})
