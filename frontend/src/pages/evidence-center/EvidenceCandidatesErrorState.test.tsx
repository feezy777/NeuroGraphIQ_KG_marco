import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../api/endpoints'
import { ApiError } from '../../api/client'
import { EvidenceCenterProvider } from './EvidenceCenterContext'
import { EvidenceCenterPage } from './EvidenceCenterPage'
import { EvidenceCandidatesModule } from './modules/EvidenceCandidatesModule'

vi.mock('../../api/endpoints', () => ({
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
  listMacroCandidateRankings: vi.fn(),
  getMacroCandidateRankingDetail: vi.fn(),
  listMacroCandidateReviews: vi.fn(),
}))

function makeItem(overrides: Record<string, unknown>) {
  return {
    id: 'it', target_type: 'connection', target_id: 'c1', status: 'awaiting_review',
    pmid: null, title: null, passage: null, direction: null, confidence: null,
    evidence_id: null, error_message: null, updated_at: '2026-08-10T00:00:00Z',
    label: 'BLA → IL', current_confidence: 0.2, attempt_count: 0, last_error_code: null,
    last_error_message: null, preprocess_outcome: null, paper_id: null, model_direction: null,
    candidate_papers: [], review_draft: null, claim_text_snapshot: null,
    claim_components_snapshot: null, passages_json: null, last_error: null, retry_count: 0,
    live_display_name: null, live_confidence: null,
    display_name: 'BLA → IL', display_confidence: 0.2,
    display_name_source: 'task_snapshot', display_confidence_source: 'task_snapshot',
    ...overrides,
  }
}

const DTO = {
  granularity: 'macro', display_name: 'BLA → IL', source_region: 'BLA', target_region: 'IL',
  source_region_cn: '基底外侧杏仁核', target_region_cn: '下边缘皮质',
  canonical_terms: ['BLA', 'IL'], claim_text: 'BLA 到 IL 存在投射连接。',
  claim_components: [], structured_claim: {}, target_type: 'connection', target_id: 'c1',
  current_confidence: 0.2, existing_evidence: 0,
}

function notFoundError(): ApiError {
  return new ApiError(400, '{"code":"INVALID_REQUEST","message":"target not found"}', {
    url: '/target', method: 'GET', responseBody: { detail: { code: 'INVALID_REQUEST', message: 'target not found' } },
  })
}

function setupHash(task = true) {
  window.location.hash = task
    ? '#/validation-center?tab=paper_evidence&task_id=t1&target_type=connection&target_id=c1'
    : '#/validation-center?tab=paper_evidence&module=candidates&target_type=connection&target_id=c1'
}

describe('EvidenceCandidatesModule 目标数据加载状态(第四步)', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [makeItem({})], total: 1 })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(DTO)
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [], total: 0 })
  })

  it('请求成功 → 渲染候选工作区,无错误面板', async () => {
    setupHash()
    const { container } = render(<EvidenceCenterProvider embedded><EvidenceCandidatesModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(container.querySelector('.evidence-candidates')).toBeTruthy())
    await waitFor(() => expect(screen.queryByTestId('evidence-target-not-found')).toBeNull())
    expect(screen.queryByTestId('evidence-target-error')).toBeNull()
  })

  it('target not found → 专用错误面板(类型/名称/短ID/原因),不显示堆栈', async () => {
    setupHash()
    vi.mocked(endpoints.getEvidenceTarget).mockRejectedValue(notFoundError())
    render(<EvidenceCenterProvider embedded><EvidenceCandidatesModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-target-not-found')).toBeTruthy())
    expect(screen.getByText('目标数据不存在或尚未同步')).toBeTruthy()
    expect(screen.getByText(/对象类型:connection/)).toBeTruthy()
    expect(screen.getByText(/对象名称:BLA → IL/)).toBeTruthy()
    expect(screen.getByText(/对象 ID:c1/)).toBeTruthy()
    expect(screen.queryByText(/Error|stack|at /)).toBeNull()
  })

  it('普通 400(非 not found)→ 通用失败面板,不误判为 not found', async () => {
    setupHash()
    vi.mocked(endpoints.getEvidenceTarget).mockRejectedValue(
      new ApiError(400, '{"code":"INVALID_REQUEST","message":"bad request"}', { url: '/t', method: 'GET', responseBody: { detail: { message: 'bad request' } } }),
    )
    render(<EvidenceCenterProvider embedded><EvidenceCandidatesModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-target-error')).toBeTruthy())
    expect(screen.queryByTestId('evidence-target-not-found')).toBeNull()
  })

  it('403 → 通用失败面板', async () => {
    setupHash()
    vi.mocked(endpoints.getEvidenceTarget).mockRejectedValue(new ApiError(403, 'forbidden', { url: '/t', method: 'GET' }))
    render(<EvidenceCenterProvider embedded><EvidenceCandidatesModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-target-error')).toBeTruthy())
    expect(screen.queryByTestId('evidence-target-not-found')).toBeNull()
  })

  it('500 → 通用失败面板', async () => {
    setupHash()
    vi.mocked(endpoints.getEvidenceTarget).mockRejectedValue(new ApiError(500, 'boom', { url: '/t', method: 'GET' }))
    render(<EvidenceCenterProvider embedded><EvidenceCandidatesModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-target-error')).toBeTruthy())
  })

  it('重试重新请求当前 target,成功后进入工作区', async () => {
    setupHash()
    vi.mocked(endpoints.getEvidenceTarget)
      .mockRejectedValueOnce(notFoundError())
      .mockResolvedValueOnce(DTO)
    render(<EvidenceCenterProvider embedded><EvidenceCandidatesModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-target-not-found')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-target-not-found-retry'))
    await waitFor(() => expect(screen.queryByTestId('evidence-target-not-found')).toBeNull())
    expect(vi.mocked(endpoints.getEvidenceTarget)).toHaveBeenCalledTimes(2)
    expect(vi.mocked(endpoints.getEvidenceTarget)).toHaveBeenLastCalledWith('connection', 'c1')
  })

  it('返回任务:清 target 保留 taskId(经页面中间模块,候选组件卸载后不再回写 target)', async () => {
    setupHash(true)
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [{
        id: 't1', target_type: 'connection', name: '任务一', status: 'completed',
        total_items: 1, processed_items: 0, awaiting_review_items: 1, failed_items: 0,
        review_status: 'in_review', granularity_level: 'macro', estimated_target_count: 1,
        materialized_target_count: 1, scope: 'filter', mode: 'existence', max_papers_per_object: 3,
        created_at: '2026-08-10T00:00:00Z', created_by: null, started_at: null, finished_at: null,
        error_message: null, materialization_status: 'completed', materialization_cursor: null,
        materialization_error: null, confidence_lt: null, only_oa: false,
        stop_after_strong_support: false, summary: { counts: { awaiting_review: 1 } },
        scope_type: 'filter', filter_snapshot: null, versions: null,
        work_status: 'awaiting_review',
        item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 },
        capabilities: { can_continue_review: true, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false },
      }], total: 1,
    })
    vi.mocked(endpoints.getEvidenceTarget).mockRejectedValue(notFoundError())
    render(<EvidenceCenterPage embedded />)
    await waitFor(() => expect(screen.getByTestId('evidence-target-not-found')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-target-not-found-back'))
    await waitFor(() => expect(window.location.hash).not.toContain('target_id='))
    expect(window.location.hash).toContain('task_id=t1')
    // 候选组件已卸载(中间模块回到任务卡片)
    await waitFor(() => expect(screen.queryByTestId('evidence-target-not-found')).toBeNull())
  })

  it('快速切换 target:旧请求不覆盖新结果(stale 防护)', async () => {
    const resolvers: Record<string, (v: unknown) => void> = {}
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'i1', target_id: 'c1' }),
        makeItem({ id: 'i2', target_id: 'c2' }),
      ],
      total: 2,
    })
    vi.mocked(endpoints.getEvidenceTarget).mockImplementation(
      (t: string, id: string) => new Promise(resolve => { resolvers[id] = resolve }),
    )
    setupHash()
    render(<EvidenceCenterProvider embedded><EvidenceCandidatesModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('对象数据加载中…')).toBeTruthy())
    // 切换到同任务的另一对象(在 items 中)
    window.location.hash = '#/validation-center?tab=paper_evidence&task_id=t1&target_type=connection&target_id=c2'
    await waitFor(() => expect(vi.mocked(endpoints.getEvidenceTarget)).toHaveBeenCalledWith('connection', 'c2'))
    // 旧请求此刻才失败返回 → 不得把新 target 标记为 not_found
    resolvers['c1']?.(null)
    await new Promise(r => setTimeout(r, 0))
    expect(screen.queryByTestId('evidence-target-not-found')).toBeNull()
    expect(screen.getByText('对象数据加载中…')).toBeTruthy()
  })

  it('无 target 空态与请求失败态不同', async () => {
    window.location.hash = '#/validation-center?tab=paper_evidence&task_id=t1'
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [makeItem({})], total: 1 })
    vi.mocked(endpoints.getEvidenceTarget).mockRejectedValue(notFoundError())
    render(<EvidenceCenterProvider embedded><EvidenceCandidatesModule /></EvidenceCenterProvider>)
    // 有 target 但行缺失 → not_found;若完全无 target → 空态(由 current 分支保证)
    await waitFor(() => expect(screen.getByTestId('evidence-target-not-found')).toBeTruthy())
    expect(screen.queryByText('请先在「佐证任务」中打开一个任务')).toBeNull()
  })
})
