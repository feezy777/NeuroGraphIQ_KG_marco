import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { MacroCandidatesProvider, useMacroViewForEvidence } from './useMacroCandidates'
import { MacroCandidateSection, MacroDetailExpanded, MacroReviewContext, MacroPromotionGate } from './MacroGovernanceIntegration'
import {
  deriveWorkflowStatus,
  latestRollback,
  pairKey,
  runRuleChecks,
  saveWorkflowRollback,
  summarizeRuleChecks,
  WORKFLOW_LABEL,
  type WorkflowDeriveInput,
} from './macroWorkflow'
import type { MacroCandidateRankingItem } from '../../../api/endpoints'

vi.mock('../../../api/endpoints', () => ({
  listMacroCandidateRankings: vi.fn(),
  getMacroCandidateRankingDetail: vi.fn(),
  listMacroCandidateReviews: vi.fn(),
  listEvidenceReviews: vi.fn(),
  listMacroCandidateRuleValidations: vi.fn(),
}))

const RANKING: MacroCandidateRankingItem = {
  id: 'rk1',
  source_region_id: 's-amygdala',
  target_region_id: 't-hippo',
  source_name: 'Amygdala',
  target_name: 'Hippocampus',
  paper_count: 93,
  evidence_count: 93,
  score: 48,
  priority_level: 'A',
  created_at: '2026-08-25T09:00:00Z',
}

const RANKING_REVERSE = {
  ...RANKING, id: 'rk2',
  source_region_id: 't-hippo',
  target_region_id: 's-amygdala',
  source_name: 'Hippocampus',
  target_name: 'Amygdala',
}

const REVIEW = {
  ranking_id: 'rk1',
  source_region_id: 's-amygdala',
  target_region_id: 't-hippo',
  source_name: 'Amygdala',
  target_name: 'Hippocampus',
  decision: 'supported' as const,
  connection_type: 'projection' as const,
  direction: 'A_to_B' as const,
  confidence: 0.9,
  evidence_strength: 'high' as const,
  reasoning: 'dense projection',
  model_name: 'deepseek-chat',
  raw_response_json: { parsed: { decision: 'supported' } },
  created_at: '2026-08-25T09:30:00Z',
  paper_count: 93,
  evidence_count: 93,
  score: 48,
}

function setupDefaultMocks() {
  vi.mocked(endpoints.listMacroCandidateRankings).mockResolvedValue({
    total: 2, limit: 1000, offset: 0,
    items: [RANKING, RANKING_REVERSE],
  })
  vi.mocked(endpoints.listMacroCandidateReviews).mockResolvedValue({
    total: 1, limit: 1000, offset: 0, items: [REVIEW],
  })
  vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(endpoints.listMacroCandidateRuleValidations).mockResolvedValue({
    total: 0, limit: 2000, offset: 0, items: [],
  })
  vi.mocked(endpoints.getMacroCandidateRankingDetail).mockResolvedValue({
    ...RANKING,
    candidate_pair_ids: ['cp1'],
    ranking_reason: {},
    provenance_json: {},
    source_parent_name: null,
    target_parent_name: null,
  } as never)
  sessionStorage.clear()
}

async function renderWithProvider(ui: React.ReactElement) {
  render(
    <MacroCandidatesProvider>
      {ui}
    </MacroCandidatesProvider>,
  )
  await waitFor(() => expect(vi.mocked(endpoints.listMacroCandidateRankings)).toHaveBeenCalled())
  return new Promise<void>(resolve => resolve())
}

describe('macroWorkflow 状态模型', () => {
  it('13 个状态全部有中文 label', () => {
    const statuses = ['candidate', 'rule_pending', 'rule_pass', 'rule_failed', 'ai_review_pending',
      'ai_supported', 'ai_uncertain', 'human_review', 'approved', 'rejected',
      'promotion_ready', 'promoted', 'rollback'] as const
    expect(statuses.length).toBe(13)
    for (const s of statuses) expect(WORKFLOW_LABEL[s]).toBeTruthy()
  })

  it('deriveWorkflowStatus 全链路: candidate → rule → ai → human → promotion', () => {
    const base: WorkflowDeriveInput = {
      ranking: RANKING, review: null, ruleResult: summarizeRuleChecks(runRuleChecks(RANKING, null, null, false)),
      humanDecision: null, rollbackAt: null, promotedAt: null,
    }
    // 无规则/无 AI → rule_pending(等待规则)
    expect(deriveWorkflowStatus({ ...base, ruleResult: null })).toBe('rule_pending')
    // 规则 pass,无 AI → rule_pass → ai_review_pending 语义(candidate stage: 用 rule_pass;ai pending 由无 review 表达)
    expect(deriveWorkflowStatus(base)).toBe('rule_pass')
    // AI supported
    expect(deriveWorkflowStatus({ ...base, review: REVIEW })).toBe('ai_supported')
    // AI uncertain
    expect(deriveWorkflowStatus({ ...base, review: { ...REVIEW, decision: 'uncertain' } })).toBe('ai_uncertain')
    // 人工 approved → promotion_ready
    expect(deriveWorkflowStatus({
      ...base, review: REVIEW,
      humanDecision: {
        targetId: 'x', status: 'review_approved',
        meta: { direction: 'supports', evidenceLevel: 'direct', confidence: '0.8', note: '', at: '2026-08-25T10:00:00Z' },
      },
    })).toBe('promotion_ready')
    // promoted
    expect(deriveWorkflowStatus({
      ...base, review: REVIEW,
      humanDecision: {
        targetId: 'x', status: 'review_approved',
        meta: { direction: 'supports', evidenceLevel: 'direct', confidence: '0.8', note: '', at: '2026-08-25T10:00:00Z' },
      },
      promotedAt: '2026-08-25T11:00:00Z',
    })).toBe('promoted')
    // rejected
    expect(deriveWorkflowStatus({
      ...base, review: REVIEW,
      humanDecision: {
        targetId: 'x', status: 'rejected',
        meta: { direction: 'supports', evidenceLevel: 'direct', confidence: '0.8', note: '', at: '2026-08-25T10:00:00Z' },
      },
    })).toBe('rejected')
  })

  it('promotion 后 rollback: 回退最新 → rollback;重审后恢复 promotion_ready', () => {
    const approved = {
      targetId: 'x', status: 'review_approved' as const,
      meta: { direction: 'supports' as const, evidenceLevel: 'direct' as const, confidence: '0.8', note: '', at: '2026-08-25T10:00:00Z' },
    }
    const base: WorkflowDeriveInput = { ranking: RANKING, review: REVIEW, ruleResult: null, humanDecision: approved, rollbackAt: null, promotedAt: '2026-08-25T11:00:00Z' }
    expect(deriveWorkflowStatus(base)).toBe('promoted')
    // 回退(晚于晋升)→ rollback
    expect(deriveWorkflowStatus({ ...base, rollbackAt: '2026-08-25T12:00:00Z', promotedAt: '2026-08-25T13:00:00Z' })).toBe('rollback')
    // 人工重审(晚于回退)→ promotion_ready
    const reapproved = { ...approved, meta: { ...approved.meta, at: '2026-08-25T14:00:00Z' } }
    expect(deriveWorkflowStatus({ ...base, rollbackAt: '2026-08-25T12:00:00Z', humanDecision: reapproved })).toBe('promotion_ready')
  })

  it('规则检查 6 项: 存在性/自连/type/direction/duplicate/hierarchy', () => {
    // 全正常 → PASS
    let checks = runRuleChecks(RANKING, REVIEW, { source_parent_name: null, target_parent_name: null }, false)
    expect(checks).toHaveLength(6)
    expect(summarizeRuleChecks(checks).passed).toBe(true)
    // 反向对存在 → R5 FAIL
    checks = runRuleChecks(RANKING, REVIEW, null, true)
    expect(checks.find(c => c.code === 'R5')?.passed).toBe(false)
    // hierarchy 冲突 → R6 FAIL
    checks = runRuleChecks(RANKING, REVIEW, { source_parent_name: 'Hippocampus', target_parent_name: null }, false)
    expect(checks.find(c => c.code === 'R6')?.passed).toBe(false)
    // 非法 type → R3 FAIL
    checks = runRuleChecks(RANKING, { ...REVIEW, connection_type: 'tract' as never }, null, false)
    expect(checks.find(c => c.code === 'R3')?.passed).toBe(false)
    // 非法 direction → R4 FAIL
    checks = runRuleChecks(RANKING, { ...REVIEW, direction: 'up' as never }, null, false)
    expect(checks.find(c => c.code === 'R4')?.passed).toBe(false)
  })

  it('rollback 记录存储:追加不覆盖 + latest 取最新', () => {
    saveWorkflowRollback({ targetId: 't1', reason: '第一次', actor: 'admin', at: '2026-08-25T10:00:00Z', from: 'approved' })
    saveWorkflowRollback({ targetId: 't1', reason: '第二次', actor: 'admin', at: '2026-08-25T11:00:00Z', from: 'promoted' })
    const latest = latestRollback('t1')
    expect(latest?.reason).toBe('第二次')
    expect(sessionStorage.getItem('evidence-center.workflow-rollback.t1')).toContain('第一次')
  })

  it('pairKey 无向排序', () => {
    expect(pairKey('b', 'a')).toBe(pairKey('a', 'b'))
    expect(pairKey('a', 'b')).toBe('a|b')
  })
})

describe('Macro 治理组件(Provider + mock 数据)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupDefaultMocks()
  })
  afterEach(() => {
    cleanup()
    sessionStorage.clear()
  })

  it('证据候选 Strip: source→target/来源/Ranking/论文数/规则/AI/人工 全显', async () => {
    await renderWithProvider(
      <MacroCandidateSection targetId="t-hippo" sourceName="Amygdala" targetName="Hippocampus" sourceCanonicalId="s-amygdala" targetCanonicalId="t-hippo" />,
    )
    const strip = await screen.findByTestId('govw-strip')
    expect(strip.textContent).toContain('Amygdala')
    expect(strip.textContent).toContain('Hippocampus')
    expect(strip.textContent).toContain('Paper Discovery')
    expect(strip.textContent).toContain('48.0')
    expect(strip.textContent).toContain('93')
    // 规则列存在(mock 含镜像对 → R5 警示 FAIL;状态派生为 AI 支持)
    expect(strip.textContent).toContain('规则')
    expect(strip.textContent).toContain('SUPPORTED')
    expect(strip.textContent).toContain('AI 支持')
  })

  it('展开详情: 规则卡 6 规则 + AI 卡 + 时间线', async () => {
    await renderWithProvider(
      <MacroCandidateSection targetId="t-hippo" sourceName="Amygdala" targetName="Hippocampus" sourceCanonicalId="s-amygdala" targetCanonicalId="t-hippo" />,
    )
    fireEvent.click(await screen.findByTestId('govw-open-detail'))
    await waitFor(() => expect(screen.getByTestId('govw-detail')).toBeTruthy())
    expect(screen.getByTestId('govw-rule-card').textContent).toContain('PASS')
    expect(screen.getByTestId('govw-rule-card').textContent).toContain('duplicate')
    expect(screen.getByTestId('govw-ai-card').textContent).toContain('deepseek-chat')
    expect(screen.getByTestId('govw-ai-card').textContent).toContain('SUPPORTED')
    expect(screen.getByTestId('govw-ai-card').textContent).toContain('dense projection')
    expect(screen.getByTestId('govw-timeline').textContent).toContain('创建候选')
    expect(screen.getByTestId('govw-timeline').textContent).toContain('规则验证')
    expect(screen.getByTestId('govw-timeline').textContent).toContain('AI 科学审核')
    expect(screen.getByTestId('govw-timeline').textContent).toContain('人工审核')
  })

  it('raw response 入口可展开', async () => {
    await renderWithProvider(
      <MacroDetailExpanded view={{ ...demoView(), review: REVIEW }} onClose={() => {}} />,
    )
    expect(screen.queryByTestId('govw-raw-response')).toBeNull()
    fireEvent.click(screen.getByTestId('govw-raw-toggle'))
    expect(screen.getByTestId('govw-raw-response')).toBeTruthy()
  })

  it('后端 BLOCKED 规则结果 → rule_blocked 状态 + 卡片显示 BLOCKED', async () => {
    vi.mocked(endpoints.listMacroCandidateRuleValidations).mockResolvedValue({
      total: 1, limit: 2000, offset: 0,
      items: [{
        ranking_id: 'rk1',
        validation_status: 'BLOCKED',
        rule_results: [
          { code: 'R1', name: 'region 存在性', passed: true, detail: 'ok' },
          { code: 'R2', name: 'source != target', passed: true, detail: 'ok' },
          { code: 'R3', name: 'connection_type 合法', passed: true, detail: 'ok' },
          { code: 'R4', name: 'direction 合法', passed: true, detail: 'ok' },
          { code: 'R5', name: 'duplicate 检查', passed: false, severity: 'block', detail: 'duplicate_existing: final=1' },
          { code: 'R6', name: 'hierarchy 检查', passed: true, detail: 'ok' },
        ],
        duplicate_existing: { final: true, canonical: false, mirror: false, mirror_pairs: [] },
        failed_rules: [{ code: 'R5', name: 'duplicate 检查', detail: 'duplicate_existing: final=1' }],
        validator_version: 'macro_candidate_rule_validation_v1',
        validation_timestamp: '2026-08-25T10:00:00Z',
        source_name: 'Paracentral',
        target_name: 'Lateral ventricle',
        paper_count: 20,
        score: 35.2,
      }],
    })
    await renderWithProvider(
      <MacroCandidateSection
        targetId="t-hippo" sourceName="Amygdala" targetName="Hippocampus"
        sourceCanonicalId="s-amygdala" targetCanonicalId="t-hippo" />,
    )
    // 展开详情(走 provider 构建的 view → 后端规则结果优先)
    fireEvent.click(await screen.findByTestId('govw-open-detail'))
    const card = await screen.findByTestId('govw-rule-card')
    expect(card.textContent).toContain('BLOCKED')
    expect(card.textContent).toContain('FAIL(BLOCK)')
    expect(card.textContent).toContain('duplicate_existing: final=true')
    // 门禁:BLOCKED → 不可进入人工审核
    await waitFor(() => expect(screen.queryByTestId('govw-enter-review')).toBeNull())
  })

  it('进入人工审核门禁: Rule PASS + AI != NOT_SUPPORTED → 按钮显示;点击提示下一步', async () => {
    await renderWithProvider(
      <MacroDetailExpanded view={demoView()} onClose={() => {}} />,
    )
    const btn = await screen.findByTestId('govw-enter-review')
    fireEvent.click(btn)
    expect(screen.getByTestId('govw-review-hint')).toBeTruthy()
  })

  it('AI NOT_SUPPORTED → 禁止进入人工审核', async () => {
    const view = { ...demoView(), review: { ...REVIEW, decision: 'not_supported' as const } }
    await renderWithProvider(<MacroDetailExpanded view={view} onClose={() => {}} />)
    await waitFor(() => expect(screen.queryByTestId('govw-enter-review')).toBeNull())
    expect(screen.getByText(/NOT_SUPPORTED 禁止进入/)).toBeTruthy()
  })

  it('回退:填原因 → 追加 rollback 记录;记录不回退自身状态', async () => {
    const view = demoView()
    await renderWithProvider(<MacroDetailExpanded view={view} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('回退原因'), { target: { value: '证据不足,需要重评' } })
    fireEvent.click(screen.getByTestId('govw-rollback-btn'))
    await waitFor(() => expect(screen.getByTestId('govw-rolledback-hint')).toBeTruthy())
    const rec = JSON.parse(sessionStorage.getItem(`evidence-center.workflow-rollback.${view.ranking!.target_region_id}`) ?? '[]')
    expect(rec[0].reason).toBe('证据不足,需要重评')
    expect(rec[0].actor).toBe('admin')
  })

  it('人工审核上下文条: 规则结果 + AI 意见', async () => {
    await renderWithProvider(
      <MacroReviewContext targetId="t-hippo" sourceName="Amygdala" targetName="Hippocampus" sourceCanonicalId="s-amygdala" targetCanonicalId="t-hippo" />,
    )
    const ctx = await screen.findByTestId('govw-review-context')
    expect(ctx.textContent).toContain('规则验证')
    expect(ctx.textContent).toContain('supported 置信 90%')
    expect(ctx.textContent).toContain('dense projection')
  })

  it('晋升门禁: 条件满足显示 ✓,不满足显示 ✗', async () => {
    await renderWithProvider(
      <MacroPromotionGate targetId="t-hippo" sourceName="Amygdala" targetName="Hippocampus" sourceCanonicalId="s-amygdala" targetCanonicalId="t-hippo" evidenceCount={3} />,
    )
    const gate = await screen.findByTestId('govw-promotion-gate')
    expect(gate.textContent).toContain('Rule PASS')
    expect(gate.textContent).toContain('Human Approved')
    expect(gate.textContent).toContain('Evidence 存在')
    // mock 无人审 → Human Approved 未通过
    expect(gate.textContent).toContain('未通过')
    expect(gate.textContent).toContain('晋升条件未全部满足')
  })

  it('无匹配对象 → 组件不渲染(零影响)', async () => {
    await renderWithProvider(
      <MacroCandidateSection targetId="no-match" sourceName="None" targetName="None" sourceCanonicalId={null} targetCanonicalId={null} />,
    )
    expect(screen.queryByTestId('govw-section')).toBeNull()
    expect(screen.queryByTestId('govw-strip')).toBeNull()
  })
})

function demoView() {
  return {
    key: pairKey(RANKING.source_region_id, RANKING.target_region_id),
    ranking: RANKING,
    detail: null,
    review: REVIEW,
    ruleResult: summarizeRuleChecks(runRuleChecks(RANKING, REVIEW, null, false)),
    status: 'promotion_ready' as const,
    sourceName: 'Amygdala',
    targetName: 'Hippocampus',
    paperCount: 93,
    rankScore: 48,
    reversePairExists: false,
  }
}
