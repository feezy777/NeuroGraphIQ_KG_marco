import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  buildReview: vi.fn(),
  completePaperEvidenceTaskItem: vi.fn(),
  listEvidenceReviews: vi.fn(),
  listPaperEvidence: vi.fn(),
  promoteReview: vi.fn(),
  returnReview: vi.fn(),
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

/** Phase 2:后端 EvidenceReviewItem 模拟 */
const BACKEND_REVIEW = {
  id: 'rev-r1-r2',
  target_type: 'connection',
  target_id: 'r1-r2',
  paper_id: 'paper-1',
  task_id: 't1',
  task_item_id: 'item-1',
  reviewer_id: null,
  review_status: 'approved',
  promotion_status: 'awaiting_promotion',
  claim_version: 'v1',
  claim_text_snapshot: 'R1 投射到 R2 且影响功能',
  claim_components_snapshot: [
    { component_type: 'relation', statement: '存在投射关系', required: true, metadata: {} },
    { component_type: 'source_region', statement: '源脑区为 R1', required: true, metadata: {} },
  ],
  model_direction: 'supports',
  model_assessment: '支持连接存在',
  reviewer_direction: 'supports',
  reviewer_evidence_level: 'direct',
  reviewer_confidence: 0.8,
  reviewer_note: '人工核对通过，允许晋升',
  coverage_summary_snapshot: null,
  coverage_formula_version: 'v2',
  draft_revision: 0,
  reviewed_at: '2026-08-10T08:00:00Z',
  approved_at: '2026-08-10T08:00:00Z',
  rejected_at: null,
  promoted_at: null,
  promoted_by: null,
  returned_at: null,
  returned_by: null,
  return_reason: null,
  evidence_id: null,
  created_at: '2026-08-10T08:00:00Z',
  updated_at: '2026-08-10T08:00:00Z',
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
  // promotionImpact 由异步 effect 推送 → 先等待右栏按钮出现(稳定性)
  await waitFor(() => expect(screen.getByTestId('pi-promote-btn')).toBeTruthy())
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
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [BACKEND_REVIEW] })
    vi.mocked(endpoints.promoteReview).mockResolvedValue({
      ...BACKEND_REVIEW,
      promotion_status: 'promoted',
      promoted_at: '2026-08-11T00:00:00Z',
      evidence_id: 'ev-new',
    })
    vi.mocked(endpoints.returnReview).mockResolvedValue({ review_id: 'rev-r1-r2', status: 'returned' })
    vi.mocked(endpoints.listPaperEvidence).mockResolvedValue({ items: [EVIDENCE_ACTIVE, EVIDENCE_INVALIDATED] })
    vi.mocked(endpoints.rollbackPaperEvidence).mockResolvedValue({
      evidence_id: 'ev-1',
      status: 'invalidated',
      changed: true,
      confidence: 0.7,
    })
  })

  // ─── V2-S4:待晋升来自后端 listEvidenceReviews(新 UI:自动选中第一条,中栏直接渲染详情) ───

  it('待晋升列表来自后端 listEvidenceReviews:自动选中并渲染审核详情', async () => {
    renderModule()
    // listEvidenceReviews 被调用
    await waitFor(() => expect(endpoints.listEvidenceReviews).toHaveBeenCalledWith(
      expect.objectContaining({ review_status: 'approved', promotion_status: 'awaiting_promotion' }),
    ))
    // 自动选中第一条 → 确认入库按钮 + 审核决策区(备注/方向/等级/置信度)渲染
    await waitFor(() => expect(screen.getByTestId('promotion-confirm-btn')).toBeTruthy())
    expect(screen.getAllByText(/支持/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/直接证据/).length).toBeGreaterThan(0)
  })

  it('待晋升列表:后端失败时降级为 sessionStorage(自动选中渲染详情)', async () => {
    vi.mocked(endpoints.listEvidenceReviews).mockRejectedValueOnce(new Error('后端不可用'))
    // 保留 sessionStorage 中的审核通过记录
    sessionStorage.setItem(REVIEW_KEY, JSON.stringify(REVIEW_RECORD))
    renderModule()
    await waitFor(() => expect(screen.getByTestId('promotion-confirm-btn')).toBeTruthy())
    expect(screen.getAllByText(/支持/).length).toBeGreaterThan(0)
  })

  it('选中待晋升项:中栏完整审核结果(论文/Coverage/Reviewer 决策/Confidence 预览)', async () => {
    renderModule()
    // 论文(草稿恢复)
    await waitFor(() => expect(screen.getAllByText('A Study of R1 to R2 Projection').length).toBeGreaterThan(0))
    // Coverage(复用 CoveragePanel)
    expect(screen.getByTestId('ew-coverage-panel')).toBeTruthy()
    expect(screen.getByText('1 / 2 已覆盖')).toBeTruthy()
    // Reviewer 决策(人工方向/等级/置信度/备注)
    expect(screen.getAllByText(/支持/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/直接证据/).length).toBeGreaterThan(0)
    // Confidence 预览(attachPaperEvidencePreview)
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
    // 预览区显示当前/建议/入库后预计
    await waitFor(() => expect(screen.getByTestId('promotion-confidence-preview')).toBeTruthy())
    const previewPanel = screen.getByTestId('promotion-confidence-preview')
    expect(within(previewPanel).getByText('当前')).toBeTruthy()
    expect(within(previewPanel).getByText('审核人建议')).toBeTruthy()
    await waitFor(() => expect(within(previewPanel).getByText('0.85')).toBeTruthy())
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

  it('右栏 PromotionImpact 字段齐全:当前/Reviewer/晋升后/新增 Evidence/新增 Passage/最终状态 + sticky Primary 仅确认晋升', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByTestId('evidence-promotion-impact')).toBeTruthy())
    const panel = screen.getByTestId('evidence-promotion-impact')
    // 6 字段标签与值(与视觉稿 §16 逐项核对)
    expect(within(panel).getByText('当前置信度')).toBeTruthy()
    expect(panel.querySelector('[data-testid="pi-current"]')?.textContent).toBe('0.70')
    expect(within(panel).getByText('Reviewer 置信度')).toBeTruthy()
    expect(panel.querySelector('[data-testid="pi-reviewer"]')?.textContent).toBe('0.80')
    expect(within(panel).getByText('晋升后置信度')).toBeTruthy()
    await waitFor(() => expect(panel.querySelector('[data-testid="pi-final"]')?.textContent).toBe('0.85'))
    expect(within(panel).getByText('新增 Evidence 数量')).toBeTruthy()
    expect(panel.querySelector('[data-testid="pi-evidence-new"]')?.textContent).toBe('+1')
    expect(within(panel).getByText('新增 Passage 数量')).toBeTruthy()
    expect(panel.querySelector('[data-testid="pi-passages-new"]')?.textContent).toBe('+1')
    expect(within(panel).getByText('最终状态')).toBeTruthy()
    expect(panel.querySelector('[data-testid="pi-status"]')?.textContent).toContain('human_verified')
    // sticky 操作区存在;Primary 仅「确认晋升」一个
    expect(panel.querySelector('.ew-sticky-actions')).toBeTruthy()
    const primaryBtns = panel.querySelectorAll('.btn-primary')
    expect(primaryBtns.length).toBe(1)
    expect((primaryBtns[0] as HTMLElement).textContent).toContain('确认晋升')
    expect((panel.querySelector('[data-testid="pi-return-btn"]') as HTMLElement).className).not.toContain('btn-primary')
  })

  it('多待晋升项:待晋升列表渲染两条,点击行切换选中项(中栏与右栏跟随切换)', async () => {
    // Mock 两个后端 Review
    const secondReview = {
      ...BACKEND_REVIEW,
      id: 'rev-x1-y1',
      target_id: 'x1-y1',
      reviewer_confidence: 0.75,
      reviewer_note: '第二篇也通过',
      approved_at: '2026-08-10T09:00:00Z',
    }
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [BACKEND_REVIEW, secondReview] })
    // 第二个对象的 sessionStorage 草稿(用于显示 paperTitle 等)
    sessionStorage.setItem('evidence-center.review-draft.x1-y1', JSON.stringify({
      ...DRAFT,
      paperTitle: 'Second Projection Paper',
      pmid: '99998888',
      reviewerConfidence: '0.75',
      note: '第二篇也通过',
    }))
    renderModule()
    // 待晋升列表两条 + 自动选中第一条
    await waitFor(() => expect(screen.getAllByTestId('promotion-pending-row')).toHaveLength(2))
    await waitFor(() => expect(screen.getAllByText('A Study of R1 to R2 Projection').length).toBeGreaterThan(0))
    // 点击第二行切换:中栏论文与备注切换
    fireEvent.click(screen.getAllByTestId('promotion-pending-row')[1])
    await waitFor(() => expect(screen.getAllByText(/Second Projection Paper/).length).toBeGreaterThan(0))
    // 右栏预览针对切换后的目标
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenLastCalledWith(
      expect.objectContaining({ target_id: 'x1-y1', pmid: '99998888' }),
      expect.anything(),
    ))
  })

  // ─── 确认晋升(唯一 attach 入口) ───

  it('「确认晋升」(右栏)→ PromotionDialog → promoteReview(后端)替换 attachPaperEvidence', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    const confirmBtn = await openConfirmDialog()
    expect(screen.getByTestId('ew-attach-dialog')).toBeTruthy()
    expect(confirmBtn.textContent).toContain('确认入库')
    expect(confirmBtn.textContent).not.toContain('确认晋升')
    fireEvent.click(confirmBtn)
    // Phase 2:调 promoteReview(reviewId) 而非 attachPaperEvidence
    await waitFor(() => expect(endpoints.promoteReview).toHaveBeenCalledWith('rev-r1-r2'))
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
  })

  it('晋升成功:promoteReview 调后端 → 清 status + 清 draft + 刷新列表', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    // 晋升后后端不再返回该 pending(因为 promotion_status 变为 promoted)
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [] })
    const confirmBtn = await openConfirmDialog()
    fireEvent.click(confirmBtn)
    await waitFor(() => expect(endpoints.promoteReview).toHaveBeenCalledWith('rev-r1-r2'))
    await waitFor(() => expect(endpoints.listPaperEvidence).toHaveBeenCalledTimes(2))
    // 刷新后重新调 listEvidenceReviews
    await waitFor(() => expect(endpoints.listEvidenceReviews).toHaveBeenCalledTimes(2))
    expect(sessionStorage.getItem(REVIEW_KEY)).toBeNull()
    expect(sessionStorage.getItem(DRAFT_KEY)).toBeNull()
    // 待晋升清空 → 空态
    await waitFor(() => expect(screen.getByText('暂无待晋升的审核通过证据')).toBeTruthy())
  })

  it('晋升成功:有 taskId 时调用 completePaperEvidenceTaskItem 标记后端完成', async () => {
    // 标记接口失败不阻断主流程:先 mock reject,再断言列表仍刷新、状态清理完成
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
    await waitFor(() => expect(endpoints.promoteReview).toHaveBeenCalledWith('rev-r1-r2'))
    await waitFor(() =>
      expect(endpoints.completePaperEvidenceTaskItem).toHaveBeenCalledWith('t1', 'item-1', 'ev-new'),
    )
    // 尽管标记接口 reject,主流程仍完成:列表刷新 + 状态清理
    await waitFor(() => expect(endpoints.listPaperEvidence).toHaveBeenCalledTimes(2))
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
    await waitFor(() => expect(endpoints.promoteReview).toHaveBeenCalledWith('rev-r1-r2'))
    expect(endpoints.completePaperEvidenceTaskItem).not.toHaveBeenCalled()
  })

  it('唯一 promote 入口:打开弹窗不调 API;仅弹窗确认按钮触发 promoteReview', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByTestId('pi-promote-btn')).toBeTruthy())
    // 全页仅右栏一个「确认晋升」触发按钮
    expect(screen.getAllByRole('button', { name: '确认晋升' })).toHaveLength(1)
    const confirmBtn = await openConfirmDialog()
    // 打开弹窗本身不触发 API
    expect(endpoints.promoteReview).not.toHaveBeenCalled()
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
    fireEvent.click(confirmBtn)
    await waitFor(() => expect(endpoints.promoteReview).toHaveBeenCalledTimes(1))
  })

  // ─── 退回人工审核 ───

  it('退回人工审核:调 returnReview(后端) + 清 status + draft + 跳转 review', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByTestId('pi-return-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pi-return-btn'))
    await waitFor(() => expect(endpoints.returnReview).toHaveBeenCalledWith('rev-r1-r2', '退回人工审核'))
    await waitFor(() => expect(window.location.hash).toContain('module=review'))
    expect(window.location.hash).toContain('target_id=r1-r2')
    expect(sessionStorage.getItem(REVIEW_KEY)).toBeNull()
    expect(sessionStorage.getItem(DRAFT_KEY)).toBeNull()
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
  })

  // ─── 已晋升 / 已失效(保持 listPaperEvidence) ───

  it('已晋升:点击记录打开 EvidenceDetailDrawer;「回滚」→ ConfirmDialog 输入原因 → rollbackPaperEvidence', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('已晋升证据')).toBeTruthy())
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

  it('禁止项:无搜索控件 / 无 Europe PMC(新 UI 确认按钮即「确认入库」)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByTestId('promotion-confirm-btn')).toBeTruthy())
    expect(screen.queryByPlaceholderText(/检索/)).toBeNull()
    expect(screen.queryByPlaceholderText(/关键词/)).toBeNull()
    expect(screen.queryByText(/Europe PMC/)).toBeNull()
  })
})
