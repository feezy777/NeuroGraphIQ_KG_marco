import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { TaskItemsRefreshProvider } from './taskItemsRefreshContext'
import { MacroCandidateTaskCards } from './MacroCandidateTaskCards'

vi.mock('../../../api/endpoints', () => ({
  listMacroCandidateReviewQueue: vi.fn(),
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  listEvidenceReviews: vi.fn(),
  listEvidencePapers: vi.fn(),
  getEvidenceTarget: vi.fn(),
}))

const ENH_ITEM = {
  target_type: 'existing_connection_evidence',
  target_id: 'rk-e2c5',
  label: 'Precentral → Thalamus proper',
  confidence: 0.95, status: 'awaiting_review', evidenceCount: 36,
  ranking_score: 48, priority_level: 'A',
  ai_decision: 'supported', ai_connection_type: 'structural_connection', rule_status: 'BLOCKED',
}
const NOVEL_ITEM = {
  ...ENH_ITEM,
  target_type: 'macro_connection_candidate',
  target_id: 'rk-novel1',
  label: 'Caudate → Insula',
  rule_status: 'PASS',
}

describe('MacroCandidateTaskCards(佐证任务页 Macro 来源)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.location.hash = ''
  })
  afterEach(() => { cleanup(); window.location.hash = '' })

  function renderCards() {
    return render(
      <EvidenceCenterProvider>
        <TaskItemsRefreshProvider>
          <MacroCandidateTaskCards />
        </TaskItemsRefreshProvider>
      </EvidenceCenterProvider>,
    )
  }

  it('渲染 Macro 候选任务卡:6 字段(来源/类型/评分/论文/AI/规则)', async () => {
    vi.mocked(endpoints.listMacroCandidateReviewQueue).mockImplementation(
      kind => Promise.resolve(kind === 'enhancement'
        ? { kind, total: 1, limit: 300, items: [ENH_ITEM] }
        : { kind, total: 1, limit: 300, items: [NOVEL_ITEM] }) as never,
    )
    renderCards()
    const card = await screen.findByTestId('macro-task-card-rk-e2c5')
    expect(card.textContent).toContain('Precentral → Thalamus proper')
    expect(card.textContent).toContain('structural_connection')
    expect(card.textContent).toContain('48.0')
    expect(card.textContent).toContain('36')
    expect(card.textContent).toContain('SUPPORTED')
    expect(card.textContent).toContain('BLOCKED')
    expect(screen.getByTestId('macro-task-card-rk-novel')).toBeTruthy()
  })

  it('继续验证 → openTarget(target_type, ranking_id)(唯一 target_id,非名称)', async () => {
    vi.mocked(endpoints.listMacroCandidateReviewQueue).mockImplementation(
      kind => Promise.resolve({
        kind, total: 1, limit: 300,
        items: kind === 'enhancement' ? [ENH_ITEM] : [],
      }) as never,
    )
    renderCards()
    fireEvent.click(await screen.findByTestId('macro-task-continue-rk-e2c5'))
    await waitFor(() => expect(window.location.hash).toContain('target_type=existing_connection_evidence'))
    expect(window.location.hash).toContain('target_id=rk-e2c5')
    expect(window.location.hash).toContain('module=candidates')
  })

  it('队列为空 → 不渲染分组(任务页无干扰)', async () => {
    vi.mocked(endpoints.listMacroCandidateReviewQueue).mockResolvedValue({
      kind: 'enhancement', total: 0, limit: 300, items: [],
    } as never)
    renderCards()
    await waitFor(() =>
      expect(vi.mocked(endpoints.listMacroCandidateReviewQueue)).toHaveBeenCalled())
    expect(screen.queryByTestId('macro-task-cards')).toBeNull()
  })
})
