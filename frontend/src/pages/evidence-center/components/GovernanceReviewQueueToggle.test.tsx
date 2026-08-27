import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { TaskItemsRefreshProvider } from './taskItemsRefreshContext'
import { GovernanceReviewQueueToggle } from './GovernanceReviewQueueToggle'

vi.mock('../../../api/endpoints', () => ({
  listMacroCandidateReviewQueue: vi.fn(),
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  listEvidenceReviews: vi.fn(),
  listEvidencePapers: vi.fn(),
  getEvidenceTarget: vi.fn(),
}))

function renderToggle() {
  return render(
    <EvidenceCenterProvider>
      <TaskItemsRefreshProvider>
        <GovernanceReviewQueueToggle />
      </TaskItemsRefreshProvider>
    </EvidenceCenterProvider>,
  )
}

describe('GovernanceReviewQueueToggle(Phase 4 双入口)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listEvidencePapers).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    window.location.hash = ''
  })
  afterEach(() => {
    cleanup()
    window.location.hash = ''
    sessionStorage.clear()
  })

  it('渲染三个入口: 全部 / 已有连接证据增强 / 新增连接候选', () => {
    renderToggle()
    const toggle = screen.getByTestId('gov-review-queue-toggle')
    expect(toggle.textContent).toContain('全部')
    expect(toggle.textContent).toContain('已有连接证据增强')
    expect(toggle.textContent).toContain('新增连接候选')
  })

  it('切到 enhancement → 拉取治理队列并打开首项(target_type=existing_connection_evidence)', async () => {
    vi.mocked(endpoints.listMacroCandidateReviewQueue).mockResolvedValue({
      kind: 'enhancement', total: 1, limit: 300,
      items: [{
        target_type: 'existing_connection_evidence',
        target_id: 'rk-1', label: 'Amygdala → Hippocampus',
        confidence: 0.9, status: 'awaiting_review', evidenceCount: 93,
        ranking_score: 48, priority_level: 'A',
        ai_decision: 'supported', ai_connection_type: 'projection', rule_status: 'BLOCKED',
      }],
    })
    renderToggle()
    fireEvent.click(screen.getByText('已有连接证据增强'))
    await waitFor(() => expect(vi.mocked(endpoints.listMacroCandidateReviewQueue))
      .toHaveBeenCalledWith('enhancement'))
    await waitFor(() => expect(window.location.hash).toContain('target_type=existing_connection_evidence'))
    expect(window.location.hash).toContain('target_id=rk-1')
  })

  it('切到 novel → 使用 macro_candidate_connection 目标类型', async () => {
    vi.mocked(endpoints.listMacroCandidateReviewQueue).mockResolvedValue({
      kind: 'novel', total: 0, limit: 300, items: [],
    })
    renderToggle()
    fireEvent.click(screen.getByText('新增连接候选'))
    await waitFor(() => expect(vi.mocked(endpoints.listMacroCandidateReviewQueue))
      .toHaveBeenCalledWith('novel'))
    // 空队列:不跳转目标
    expect(window.location.hash).not.toContain('target_id=')
  })

  it('切回「全部」清空治理队列(返回任务模式)', async () => {
    renderToggle()
    fireEvent.click(screen.getByText('已有连接证据增强'))
    fireEvent.click(screen.getByText('全部'))
    // 治理模式请求过;切回不触发新的任务刷新(useTaskItemsRefresh.refresh 由模块层提供,此处无任务)
    await waitFor(() =>
      expect(screen.getByTestId('gov-review-queue-toggle').textContent).toContain('全部'))
    // 会话无任务时任务刷新为空侧;切回后不再停留在治理模式(active 为「全部」)
    expect(screen.getByText('全部').className).toContain('active')
  })
})
