import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import * as endpoints from '../../../api/endpoints'
import type { PaperEvidenceItem } from '../../../api/endpoints'
import { EvidenceCenterProvider, useEvidenceCenter } from '../EvidenceCenterContext'
import { RightPanel } from '../components/RightPanel'
import type { EvidenceLevel, QueueStatus, WorkbenchPassage } from '../components/types'
import { EvidencePromotionModule } from './EvidencePromotionModule'

vi.mock('../../../api/endpoints', () => ({
  getEvidenceTarget: vi.fn(),
  attachPaperEvidencePreview: vi.fn(),
  attachPaperEvidence: vi.fn(),
  completePaperEvidenceTaskItem: vi.fn(),
  listPaperEvidence: vi.fn(),
  rollbackPaperEvidence: vi.fn(),
}))

const DRAFT_KEY = 'evidence-center.review-draft.r1-r2'
const REVIEW_KEY = 'evidence-center.review-approved.r1-r2'
const HASH = '#/evidence-center?module=promotion&task_id=t1&target_type=connection&target_id=r1-r2'
const HASH_NO_TASK = '#/evidence-center?module=promotion&target_type=connection&target_id=r1-r2'

const PASSAGE_VERIFIED: WorkbenchPassage = {
  hash: 'h1',
  paper_id: 'paper-1',
  paper_passage_id: 'pp1',
  source_scope: 'abstract',
  section_title: null,
  paragraph_index: 0,
  paragraph_id: null,
  passage: 'We observed that R1 projects to R2 in the macaque.',
  translation_zh: null,
  direction: 'supports',
  evidence_level: 'direct',
  reason: '直接支持',
  confidence: 0.9,
  semantic_confidence: 0.82,
  source_locator: 'pmc:123:sec1',
  source_verified: true,
  source_verification_method: 'exact',
  supported_components: ['relation'],
}

/** T8 人工审核写回的完整草稿(含人工决策值) */
const DRAFT = {
  passages: [PASSAGE_VERIFIED],
  modelDirection: 'supports',
  modelAssessment: '支持连接存在',
  paperTitle: 'A Study of R1 to R2 Projection',
  pmid: '12345678',
  reviewerDirection: 'supports' as const,
  reviewerEvidenceLevel: 'direct' as EvidenceLevel,
  reviewerConfidence: '0.8',
  note: '人工核对通过，允许晋升',
}

/** S3 审核通过时 ReviewStatusStore 写入的审核状态记录 */
const REVIEW_RECORD = {
  targetId: 'r1-r2',
  targetType: 'connection',
  status: 'review_approved',
  meta: {
    direction: 'supports' as const,
    evidenceLevel: 'direct' as EvidenceLevel,
    confidence: '0.8',
    note: '人工核对通过，允许晋升',
    at: '2026-08-10T08:00:00.000Z',
  },
}

const DTO = {
  target_type: 'connection',
  target_id: 'r1-r2',
  granularity: 'macro_clinical',
  display_name: 'R1 → R2',
  source_region: 'R1',
  target_region: 'R2',
  canonical_terms: [],
  relation: 'projects_to',
  directionality: '',
  circuit_context: '',
  function_context: '',
  current_confidence: 0.7,
  existing_evidence: 2,
  structured_claim: {},
  claim_text: 'R1 投射到 R2 且影响功能',
  claim_components: [
    { component_type: 'relation', statement: '存在投射关系', required: true, metadata: {} },
    { component_type: 'source_region', statement: '源脑区为 R1', required: true, metadata: {} },
  ],
  claim_version: 'v1',
}

const PREVIEW = {
  target_type: 'connection',
  target_id: 'r1-r2',
  current_confidence: 0.7,
  direction: 'supports',
  reviewer_confidence: 0.8,
  final_confidence: 0.85,
  cap: 0.85,
  selected_passage_count: 1,
  duplicate_passage_count: 0,
  evidence_text_preview: '...',
  allow: true,
  block_reasons: [] as string[],
}

const EVIDENCE_ACTIVE: PaperEvidenceItem = {
  evidence_id: 'ev-1',
  evidence_text: 'R1 投射到 R2（直接支持）',
  direction: 'supports',
  evidence_level: 'direct',
  model_direction: 'supports',
  model_assessment: '支持连接存在',
  reviewer_note: '支持正式入库',
  claim_version: 'v1',
  claim_text_snapshot: 'R1 投射到 R2 且影响功能',
  claim_components_snapshot: [
    { component_type: 'relation', statement: '存在投射关系', required: true, metadata: {} },
  ],
  coverage_summary_snapshot: {
    required_components: ['relation'],
    supported_components: ['relation'],
    contradicted_components: [],
    uncovered_components: [],
    coverage_ratio: 1,
    has_conflict: false,
    full_claim_supported: true,
    overall_direction: 'supports',
  },
  coverage_formula_version: 'v2',
  verification_status: 'verified',
  pmid: '12345678',
  doi: null,
  title: 'A Study of R1 to R2 Projection',
  journal: 'Nature',
  year: 2024,
  created_at: '2026-08-01T00:00:00Z',
  invalidated_at: null,
  invalidation_reason: null,
  passage_count: 1,
  links: { pubmed: 'https://pubmed.ncbi.nlm.nih.gov/12345678/', doi: null },
  passages: [{
    id: 'p1',
    source_scope: 'abstract',
    section_title: null,
    paragraph_index: 0,
    passage: 'We observed that R1 projects to R2 in the macaque.',
    translation_zh: null,
    direction: 'supports',
    reason: '直接支持',
    confidence: 0.9,
    source_locator: 'pmc:123:sec1',
    source_verified: true,
    source_verification_method: 'exact',
    supported_components: ['relation'],
    is_selected: true,
  }],
}

const EVIDENCE_INVALIDATED: PaperEvidenceItem = {
  ...EVIDENCE_ACTIVE,
  evidence_id: 'ev-2',
  verification_status: 'invalidated',
  invalidated_at: '2026-08-02T00:00:00Z',
  invalidation_reason: '人工撤销',
}

/** 与 EvidenceCenterPage 相同的组合:模块 + 右栏(晋升影响由模块经 Context 推送) */
function renderModule(hash = HASH) {
  window.location.hash = hash
  return render(
    <EvidenceCenterProvider>
      <EvidencePromotionModule />
      <RightPanel module="promotion" />
    </EvidenceCenterProvider>,
  )
}

/** 模拟候选模块已把带 taskItemId 的队列同步到 context */
function QueueSeeder() {
  const { setQueue } = useEvidenceCenter()
  useEffect(() => {
    setQueue([{
      target_type: 'connection',
      target_id: 'r1-r2',
      label: 'R1 → R2 连接',
      confidence: 0.7,
      status: 'awaiting_review' as QueueStatus,
      evidenceCount: 1,
      taskItemId: 'item-1',
    }])
  }, [setQueue])
  return null
}

/** 点击右栏唯一 attach 入口(确认晋升)→ PromotionDialog → 返回弹窗确认按钮 */
async function openConfirmDialog() {
  fireEvent.click(screen.getByTestId('pi-promote-btn'))
  const confirmBtn = screen.getByTestId('ew-confirm-attach') as HTMLButtonElement
  await waitFor(() => expect(confirmBtn.disabled).toBe(false))
  return confirmBtn
}

describe('EvidencePromotionModule', () => {
  afterEach(() => {
    cleanup()
    window.location.hash = ''
    sessionStorage.clear()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.setItem(REVIEW_KEY, JSON.stringify(REVIEW_RECORD))
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(DRAFT))
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(DTO)
    vi.mocked(endpoints.attachPaperEvidencePreview).mockResolvedValue(PREVIEW)
    vi.mocked(endpoints.attachPaperEvidence).mockResolvedValue({
      evidence_id: 'ev-new',
      target_type: 'connection',
      target_id: 'r1-r2',
      confidence: 0.8,
      final_confidence: 0.85,
      verification_status: 'verified',
      confidence_adjustment_status: 'adjusted',
      passage_count: 1,
      paper: { links: { pubmed: null, doi: null } },
    })
    vi.mocked(endpoints.listPaperEvidence).mockResolvedValue({ items: [EVIDENCE_ACTIVE, EVIDENCE_INVALIDATED] })
    vi.mocked(endpoints.rollbackPaperEvidence).mockResolvedValue({
      evidence_id: 'ev-1',
      status: 'invalidated',
      changed: true,
      confidence: 0.7,
    })
  })

  // ─── V2-S4:待晋升来自 ReviewStatusStore(review_approved) ───

  it('待晋升列表来自 ReviewStatusStore:仅渲染 review_approved,排除 rejected', async () => {
    // rejected 记录不进入待晋升列表
    sessionStorage.setItem('evidence-center.review-approved.x1-y1', JSON.stringify({
      targetId: 'x1-y1',
      targetType: 'connection',
      status: 'rejected',
      meta: { direction: 'contradicts', evidenceLevel: 'indirect', confidence: '0.4', note: '矛盾', at: '2026-08-10T08:00:00.000Z' },
    }))
    renderModule()
    await waitFor(() => expect(screen.getAllByTestId('promotion-pending-row')).toHaveLength(1))
    expect(screen.queryByText('x1-y1')).toBeNull()
    // 待晋升行展示审核结果摘要(方向/等级/置信度/时间)
    expect(screen.getByText(/支持 · 直接证据 · 置信度 0\.8/)).toBeTruthy()
  })

  it('选中待晋升项:中栏完整审核结果(Claim/论文/Coverage/Reviewer 决策/Confidence 预览)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('待晋升')).toBeTruthy())
    // Claim
    expect(screen.getByText('R1 投射到 R2 且影响功能')).toBeTruthy()
    // 论文(待晋升卡片 + 已晋升列表行可能同名,取首个匹配即可)
    expect(screen.getAllByText('A Study of R1 to R2 Projection').length).toBeGreaterThan(0)
    // Coverage(复用 CoveragePanel)
    expect(screen.getByTestId('ew-coverage-panel')).toBeTruthy()
    expect(screen.getByText('1 / 2 已覆盖')).toBeTruthy()
    // Reviewer 决策(人工方向/等级/置信度/备注;行摘要与决策行都可能含「直接证据」)
    expect(screen.getByText('人工核对通过，允许晋升')).toBeTruthy()
    expect(screen.getAllByText(/直接证据/).length).toBeGreaterThan(0)
    // 当前 confidence(ClaimPanel 数据源 getEvidenceTarget)
    expect(screen.getByText(/当前置信度 0\.7/)).toBeTruthy()
    // 预计后 confidence(attachPaperEvidencePreview)
    expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalledWith(expect.objectContaining({
      target_type: 'connection',
      target_id: 'r1-r2',
      pmid: '12345678',
      direction: 'supports',
      reviewer_confidence: 0.8,
      passages: expect.arrayContaining([expect.objectContaining({
        source_verified: true,
        passage: PASSAGE_VERIFIED.passage,
      })]),
    }), expect.anything())
    await waitFor(() => expect(screen.getByText(/预计晋升后置信度 0\.85/)).toBeTruthy())
  })

  it('右栏 PromotionImpact:KG 当前/晋升后/Evidence 新增/Passages 新增/状态', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByTestId('evidence-promotion-impact')).toBeTruthy())
    expect(screen.getByTestId('pi-current').textContent).toBe('0.70')
    await waitFor(() => expect(screen.getByTestId('pi-final').textContent).toBe('0.85'))
    expect(screen.getByTestId('pi-evidence-new').textContent).toBe('+1')
    expect(screen.getByTestId('pi-passages-new').textContent).toBe('+1')
    expect(screen.getByTestId('pi-status').textContent).toContain('human_verified')
  })

  it('多待晋升项:列表来自 store,点击行切换选中项(中栏与右栏跟随切换)', async () => {
    sessionStorage.setItem('evidence-center.review-draft.x1-y1', JSON.stringify({
      ...DRAFT,
      paperTitle: 'Second Projection Paper',
      pmid: '99998888',
      reviewerConfidence: '0.75',
      note: '第二篇也通过',
    }))
    sessionStorage.setItem('evidence-center.review-approved.x1-y1', JSON.stringify({
      targetId: 'x1-y1',
      targetType: 'connection',
      status: 'review_approved',
      meta: { direction: 'supports', evidenceLevel: 'direct', confidence: '0.75', note: '第二篇也通过', at: '2026-08-10T09:00:00.000Z' },
    }))
    renderModule()
    await waitFor(() => expect(screen.getAllByTestId('promotion-pending-row')).toHaveLength(2))
    // 切换到第二篇:中栏论文与备注切换
    fireEvent.click(screen.getAllByTestId('promotion-pending-row')[1])
    await waitFor(() => expect(screen.getByText('Second Projection Paper')).toBeTruthy())
    expect(screen.getByText('第二篇也通过')).toBeTruthy()
    // 右栏预览针对切换后的目标
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenLastCalledWith(
      expect.objectContaining({ target_id: 'x1-y1', pmid: '99998888' }),
      expect.anything(),
    ))
  })

  // ─── 确认晋升(唯一 attach 入口) ───

  it('「确认晋升」(右栏)→ PromotionDialog(文案为 确认晋升)→ attachPaperEvidence body 断言', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    const confirmBtn = await openConfirmDialog()
    expect(screen.getByTestId('ew-attach-dialog')).toBeTruthy()
    expect(confirmBtn.textContent).toContain('确认晋升')
    expect(confirmBtn.textContent).not.toContain('确认入库')
    fireEvent.click(confirmBtn)
    await waitFor(() =>
      expect(endpoints.attachPaperEvidence).toHaveBeenCalledWith(expect.objectContaining({
        target_type: 'connection',
        target_id: 'r1-r2',
        pmid: '12345678',
        direction: 'supports',
        evidence_level: 'direct',
        model_direction: 'supports',
        model_assessment: '支持连接存在',
        reviewer_note: '人工核对通过，允许晋升',
        reviewer_confidence: 0.8,
        passages: expect.arrayContaining([expect.objectContaining({
          source_verified: true,
          passage: PASSAGE_VERIFIED.passage,
          supported_components: ['relation'],
        })]),
      })),
    )
  })

  it('晋升成功:清 review status + 清 draft + 刷新已晋升/已失效列表', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    const confirmBtn = await openConfirmDialog()
    fireEvent.click(confirmBtn)
    await waitFor(() => expect(endpoints.attachPaperEvidence).toHaveBeenCalled())
    await waitFor(() => expect(endpoints.listPaperEvidence).toHaveBeenCalledTimes(2))
    expect(sessionStorage.getItem(REVIEW_KEY)).toBeNull()
    expect(sessionStorage.getItem(DRAFT_KEY)).toBeNull()
    // 待晋升组消失(store 记录已清除)
    await waitFor(() => expect(screen.queryAllByTestId('promotion-pending-row')).toHaveLength(0))
  })

  it('晋升成功:有 taskId 且 queue 带 taskItemId 时调用 completePaperEvidenceTaskItem 标记后端完成', async () => {
    // 标记接口失败不阻断主流程:先 mock reject,再断言列表仍刷新、成功消息仍出现
    vi.mocked(endpoints.completePaperEvidenceTaskItem).mockRejectedValueOnce(new Error('boom'))
    window.location.hash = HASH
    render(
      <EvidenceCenterProvider>
        <QueueSeeder />
        <EvidencePromotionModule />
        <RightPanel module="promotion" />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    const confirmBtn = await openConfirmDialog()
    fireEvent.click(confirmBtn)
    await waitFor(() => expect(endpoints.attachPaperEvidence).toHaveBeenCalled())
    await waitFor(() =>
      expect(endpoints.completePaperEvidenceTaskItem).toHaveBeenCalledWith('t1', 'item-1', 'ev-new'),
    )
    // 尽管标记接口 reject,主流程仍完成:列表刷新 + 成功消息 + 状态清理
    await waitFor(() => expect(endpoints.listPaperEvidence).toHaveBeenCalledTimes(2))
    expect(screen.getByText('证据已晋升并应用到知识对象')).toBeTruthy()
    expect(sessionStorage.getItem(REVIEW_KEY)).toBeNull()
    expect(sessionStorage.getItem(DRAFT_KEY)).toBeNull()
  })

  it('晋升成功:URL 无 task_id 时不调用 completePaperEvidenceTaskItem', async () => {
    window.location.hash = HASH_NO_TASK
    render(
      <EvidenceCenterProvider>
        <QueueSeeder />
        <EvidencePromotionModule />
        <RightPanel module="promotion" />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    const confirmBtn = await openConfirmDialog()
    fireEvent.click(confirmBtn)
    await waitFor(() => expect(endpoints.attachPaperEvidence).toHaveBeenCalled())
    expect(endpoints.completePaperEvidenceTaskItem).not.toHaveBeenCalled()
  })

  it('唯一 attach 入口:打开弹窗不调 attach;仅弹窗确认按钮触发,且一次晋升只调一次', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByTestId('pi-promote-btn')).toBeTruthy())
    // 待晋升卡片内无其他 attach 按钮:全页仅右栏一个「确认晋升」触发按钮
    expect(screen.getAllByRole('button', { name: '确认晋升' })).toHaveLength(1)
    const confirmBtn = await openConfirmDialog()
    // 打开弹窗本身不触发 attach
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
    fireEvent.click(confirmBtn)
    await waitFor(() => expect(endpoints.attachPaperEvidence).toHaveBeenCalledTimes(1))
  })

  // ─── 退回人工审核 ───

  it('退回人工审核:清除 review status + draft,openTarget 到 module=review', async () => {
    renderModule()
    await waitFor(() => expect(screen.getAllByTestId('promotion-pending-row')).toHaveLength(1))
    fireEvent.click(screen.getByTestId('pi-return-btn'))
    await waitFor(() => expect(window.location.hash).toContain('module=review'))
    expect(window.location.hash).toContain('target_id=r1-r2')
    expect(sessionStorage.getItem(REVIEW_KEY)).toBeNull()
    expect(sessionStorage.getItem(DRAFT_KEY)).toBeNull()
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
  })

  // ─── 已晋升 / 已失效(保持 listPaperEvidence) ───

  it('已晋升:点击记录打开 EvidenceDetailDrawer;「回滚」→ ConfirmDialog 输入原因 → rollbackPaperEvidence', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('已晋升')).toBeTruthy())
    fireEvent.click(screen.getAllByTestId('promotion-evidence-row')[0])
    await waitFor(() => expect(screen.getByTestId('evidence-detail-drawer')).toBeTruthy())
    // drawer 展示 reviewer 决策/备注/claim snapshot
    expect(screen.getByText('支持正式入库')).toBeTruthy()
    expect(screen.getAllByText(/直接证据/).length).toBeGreaterThan(0)
    // 回滚流程:原因输入 + 确认
    fireEvent.click(screen.getByRole('button', { name: '回滚' }))
    const ta = screen.getByPlaceholderText(/回滚原因/) as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: '证据不充分' } })
    fireEvent.click(screen.getByRole('button', { name: '确认回滚' }))
    await waitFor(() =>
      expect(endpoints.rollbackPaperEvidence).toHaveBeenCalledWith('ev-1', '证据不充分'),
    )
  })

  it('已失效:渲染 invalidated 记录,详情抽屉只读(无回滚按钮)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('已失效')).toBeTruthy())
    // 行内失效原因与日期同文本节点,用正则匹配
    expect(screen.getAllByText(/人工撤销/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByTestId('promotion-invalidated-row')[0])
    await waitFor(() => expect(screen.getByTestId('evidence-detail-drawer')).toBeTruthy())
    expect(screen.queryByRole('button', { name: '回滚' })).toBeNull()
    // 抽屉 meta 区单独展示失效原因
    expect(screen.getAllByText(/人工撤销/).length).toBeGreaterThan(0)
  })

  it('禁止项:无搜索控件 / 无 Europe PMC', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('待晋升')).toBeTruthy())
    expect(screen.queryByPlaceholderText(/检索/)).toBeNull()
    expect(screen.queryByPlaceholderText(/关键词/)).toBeNull()
    expect(screen.queryByText(/Europe PMC/)).toBeNull()
    expect(screen.queryByText('确认入库')).toBeNull()
  })
})
