import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import * as endpoints from '../../../api/endpoints'
import { ApiError } from '../../../api/client'
import { EvidenceCenterProvider, useEvidenceCenter } from '../EvidenceCenterContext'
import { RightPanel } from '../components/RightPanel'
import { TaskItemsRefreshProvider, useTaskItemsRefresh } from '../components/taskItemsRefreshContext'
import type { EvidenceLevel, QueueStatus, WorkbenchPassage } from '../components/types'
import { EvidenceReviewModule } from './EvidenceReviewModule'

vi.mock('../../../api/endpoints', () => ({
  approveReview: vi.fn(),
  getEvidenceTarget: vi.fn(),
  attachPaperEvidencePreview: vi.fn(),
  attachPaperEvidence: vi.fn(),
  buildReview: vi.fn(),
  rejectReview: vi.fn(),
  reopenPaperEvidenceTaskItem: vi.fn(),
  translateEvidenceText: vi.fn(),
  validatePassageSelection: vi.fn(),
  saveTaskItemDraft: vi.fn(),
  resolvePaperEvidenceTaskItem: vi.fn(),
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
}))

const DRAFT_KEY = 'evidence-center.review-draft.r1-r2'
const REVIEW_STATUS_KEY = 'evidence-center.review-approved.r1-r2'

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

const PASSAGE_UNVERIFIED: WorkbenchPassage = {
  ...PASSAGE_VERIFIED,
  hash: 'h2',
  paper_passage_id: 'pp2',
  passage: 'A secondary passage without verification.',
  source_verified: false,
  source_verification_method: null,
  supported_components: [],
}

const DRAFT = {
  passages: [PASSAGE_VERIFIED, PASSAGE_UNVERIFIED],
  modelDirection: 'supports',
  modelAssessment: '支持连接存在',
  paperTitle: 'A Study of R1 to R2 Projection',
  pmid: '12345678',
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

const REVIEW_HASH = '#/evidence-center?module=review&task_id=t1&target_type=connection&target_id=r1-r2'

function renderModule(hash = REVIEW_HASH) {
  window.location.hash = hash
  return render(
    <EvidenceCenterProvider>
      <EvidenceReviewModule />
      <RightPanel module="review" />
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

describe('EvidenceReviewModule', () => {
  afterEach(() => {
    cleanup()
    window.location.hash = ''
    sessionStorage.clear()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(DRAFT))
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(DTO)
    vi.mocked(endpoints.attachPaperEvidencePreview).mockResolvedValue(PREVIEW)
    vi.mocked(endpoints.translateEvidenceText).mockResolvedValue({ translated: '译文内容：R1 投射到 R2。' })
    vi.mocked(endpoints.validatePassageSelection).mockResolvedValue({
      source_verified: true,
      verification_method: 'exact',
      normalized_selection: 'R1 projects to R2.',
      char_start: 0,
      char_end: 20,
    })
    vi.mocked(endpoints.saveTaskItemDraft).mockResolvedValue({ item_id: 'item-1', saved: true, server_revision: 1 })
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.buildReview).mockResolvedValue({ review_id: 'rev-1', status: 'approved' })
    vi.mocked(endpoints.rejectReview).mockResolvedValue({ review_id: 'rev-1', status: 'rejected' })
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockResolvedValue({ task_id: 't1', item_id: 'item-1', status: 'awaiting_review' })
    // S6:任务模式默认唯一匹配解析到 item-1
    vi.mocked(endpoints.resolvePaperEvidenceTaskItem).mockResolvedValue({
      task_id: 't1',
      task_item_id: 'item-1',
      target_type: 'connection',
      target_id: 'r1-r2',
      status: 'awaiting_review',
      matched: 'task_target',
      rescore_source_review_id: null,
      rescore_revision_no: null,
    })
  })

  it('从 sessionStorage draft 恢复 passages 并渲染 PassageEvidenceCard + AI 初判', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    // 片段导航:默认展示第一条,第二条通过「下一个」切换
    expect(screen.queryByText('A secondary passage without verification.')).toBeNull()
    expect(screen.getByTestId('evidence-review-passage-nav-idx').textContent).toContain('1 / 2')
    await waitFor(() => expect(screen.getByTestId('ew-ai-direction').textContent).toBe('支持'))
    // 第一条(已核验)可勾选
    const card = screen.getAllByTestId('ew-passage')[0]
    const checkbox = card.querySelector('input[type="checkbox"]') as HTMLInputElement
    expect(checkbox.disabled).toBe(false)
    // 切到第二条(未核验)不可勾选
    fireEvent.click(screen.getByText('下一个 →'))
    const card2 = screen.getAllByTestId('ew-passage')[0]
    const checkbox2 = card2.querySelector('input[type="checkbox"]') as HTMLInputElement
    expect(checkbox2.disabled).toBe(true)
    expect(screen.getByText('未通过原文校验，请人工核对或重新截取')).toBeTruthy()
  })

  it('方向修改触发 attach-preview(debounce 350ms)', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    fireEvent.click(screen.getByLabelText('矛盾'))
    await waitFor(() =>
      expect(endpoints.attachPaperEvidencePreview).toHaveBeenLastCalledWith(expect.objectContaining({
        target_type: 'connection',
        target_id: 'r1-r2',
        pmid: '12345678',
        direction: 'contradicts',
        reviewer_confidence: 0.8,
      }), expect.anything()),
    )
    expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalledWith(expect.objectContaining({
      passages: expect.arrayContaining([expect.objectContaining({ source_verified: true, passage: PASSAGE_VERIFIED.passage })]),
    }), expect.anything())
  })

  it('翻译按钮调用 translateEvidenceText 并显示译文', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '翻译' }))
    await waitFor(() => expect(endpoints.translateEvidenceText).toHaveBeenCalledWith({ text: PASSAGE_VERIFIED.passage }))
    const ta = screen.getByPlaceholderText('中文翻译（可编辑）') as HTMLTextAreaElement
    await waitFor(() => expect(ta.value).toBe('译文内容：R1 投射到 R2。'))
  })

  it('「返回证据候选」→ module=candidates 且 draft 保留,重新进入 review 恢复', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '返回证据候选' }))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('target_id=r1-r2')
    const raw = sessionStorage.getItem(DRAFT_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).passages.length).toBe(2)
    // 重新进入 review 模块 → 从 draft 恢复
    cleanup()
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect(screen.getByTestId('ew-ai-direction').textContent).toBe('支持'))
  })

  it('「返回证据候选」在 debounce(500ms)窗口内同步落盘最后编辑(草稿不丢失)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    // 修改备注(触发 debounce 重排 500ms 定时器)
    const note = screen.getByPlaceholderText('为什么接受/调整方向/修改组件等（可选）') as HTMLTextAreaElement
    fireEvent.change(note, { target: { value: '最新人工备注' } })
    // 立即返回(不等待 debounce 触发)—— handleBack 必须同步落盘
    fireEvent.click(screen.getByRole('button', { name: '返回证据候选' }))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    const raw = sessionStorage.getItem(DRAFT_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).note).toBe('最新人工备注')
  })

  it('AI 初判区:modelDirection 灰字展示 + 人工方向 radio 独立高亮 + 分隔线「人工最终判断」', async () => {
    const { container } = renderModule()
    await waitFor(() => expect(screen.getByTestId('ew-ai-direction').textContent).toBe('支持'))
    expect(screen.getByText('AI 初判')).toBeTruthy()
    expect(container.querySelector('.ew-ai-recommend')).toBeTruthy()
    expect(screen.getByText('人工最终判断')).toBeTruthy()
    // 人工方向 radio 独立于 AI 初判存在,当前选择高亮
    const radios = container.querySelectorAll('input[name="dir"]')
    expect(radios.length).toBe(5)
    const checked = [...radios].find(r => (r as HTMLInputElement).checked) as HTMLInputElement
    expect(checked.value).toBe('supports')
    const chips = container.querySelectorAll('.ew-dir-chip')
    const supportsChip = [...chips].find(c => c.textContent?.trim() === '支持') as HTMLElement
    expect(supportsChip.className).toContain('ew-dir-chip-active')
    const contradictsChip = [...chips].find(c => c.textContent?.trim() === '矛盾') as HTMLElement
    expect(contradictsChip.className).not.toContain('ew-dir-chip-active')
  })

  it('AI 初判区展示 Coverage(已核验片段支撑的组件数/必需组件数)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByTestId('ew-ai-coverage').textContent).toBe('1/2'))
    expect(screen.getByText('Coverage')).toBeTruthy()
  })

  it('禁止项:无 Europe PMC 搜索控件 / 无 attach / 无正式确认文案', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    expect(screen.queryByPlaceholderText(/检索/)).toBeNull()
    expect(screen.queryByText(/Europe PMC/)).toBeNull()
    expect(screen.queryByText('确认论文证据')).toBeNull()
    expect(screen.queryByText('确认入库')).toBeNull()
    expect(screen.queryByTestId('ew-attach')).toBeNull()
    expect(screen.queryByText('检索')).toBeNull()
  })

  it('保存草稿:写 sessionStorage + 有 taskItemId 时调 saveTaskItemDraft', async () => {
    window.location.hash = REVIEW_HASH
    render(
      <EvidenceCenterProvider>
        <QueueSeeder />
        <EvidenceReviewModule />
        <RightPanel module="review" />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))
    await waitFor(() =>
      expect(endpoints.saveTaskItemDraft).toHaveBeenCalledWith('item-1', expect.objectContaining({
        passages: expect.any(Array),
        reviewerDirection: 'supports',
        modelDirection: 'supports',
        pmid: '12345678',
      }), 0),
    )
    const raw = sessionStorage.getItem(DRAFT_KEY)
    const draft = JSON.parse(raw!) as { reviewerDirection: string; reviewerEvidenceLevel: EvidenceLevel; note: string }
    expect(draft.reviewerDirection).toBe('supports')
    expect(draft.reviewerEvidenceLevel).toBe('indirect')
    expect(typeof draft.note).toBe('string')
  })

  it('重新截取调用 validatePassageSelection 并通过校验后替换原文', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '重新截取' }))
    const input = screen.getByPlaceholderText('输入更短的真实原文范围（后端校验）') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'R1 projects to R2.' } })
    fireEvent.click(screen.getByRole('button', { name: '校验并替换' }))
    await waitFor(() =>
      expect(endpoints.validatePassageSelection).toHaveBeenCalledWith({
        paper_passage_id: 'pp1',
        selected_text: 'R1 projects to R2.',
      }),
    )
    await waitFor(() => expect(screen.getByText('R1 projects to R2.')).toBeTruthy())
  })

  // ─── V2-S3:审核 ≠ 晋升 ───

  it('审核通过:写 sessionStorage + 调 buildReview(后端) + 提示进入晋升 + 不调 attach', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    // S6:任务项解析完成后按钮才可用
    await waitFor(() => expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: '审核通过' }))
    // sessionStorage 兼容写入 + 后端 buildReview 调用
    await waitFor(() => expect(sessionStorage.getItem(REVIEW_STATUS_KEY)).toBeTruthy())
    await waitFor(() => expect(endpoints.buildReview).toHaveBeenCalled())
    const record = JSON.parse(sessionStorage.getItem(REVIEW_STATUS_KEY)!)
    expect(record.status).toBe('review_approved')
    expect(record.targetId).toBe('r1-r2')
    expect(record.meta.direction).toBe('supports')
    expect(record.meta.evidenceLevel).toBe('indirect')
    expect(record.meta.confidence).toBe('0.8')
    expect(typeof record.meta.at).toBe('string')
    expect(screen.getAllByText(/已审核通过/).length).toBeGreaterThan(0)
    // 审核不调旧 attach
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
    // buildReview body 断言(S6:任务模式 payload 必须携带权威 task_id + task_item_id)
    expect(endpoints.buildReview).toHaveBeenCalledWith(expect.objectContaining({
      target_type: 'connection',
      target_id: 'r1-r2',
      task_id: 't1',
      task_item_id: 'item-1',
      reviewer_direction: 'supports',
      reviewer_evidence_level: 'indirect',
      reviewer_confidence: 0.8,
    }))
  })

  it('驳回证据:写 rejected + 调 buildReview(直接建 rejected 终态,不再调 rejectReview)+ 提示 + 不调 attach', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '驳回证据' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: '驳回证据' }))
    await waitFor(() => expect(sessionStorage.getItem(REVIEW_STATUS_KEY)).toBeTruthy())
    await waitFor(() => expect(endpoints.buildReview).toHaveBeenCalled())
    expect(endpoints.rejectReview).not.toHaveBeenCalled()
    const record = JSON.parse(sessionStorage.getItem(REVIEW_STATUS_KEY)!)
    expect(record.status).toBe('rejected')
    expect(record.meta.direction).toBe('supports')
    expect(screen.getAllByText(/已驳回/).length).toBeGreaterThan(0)
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
  })

  it('审核通过:buildReview 失败时提示错误,保留草稿', async () => {
    vi.mocked(endpoints.buildReview).mockRejectedValueOnce(new Error('后端不可用'))
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: '审核通过' }))
    await waitFor(() => expect(screen.getByText(/审核失败/)).toBeTruthy())
    // sessionStorage 仍已写入（先写 sessionStorage 再调后端）
    expect(sessionStorage.getItem(REVIEW_STATUS_KEY)).toBeTruthy()
  })

  it('审核通过后重新进入:右栏面板显示已审核通过状态标记', async () => {
    sessionStorage.setItem(REVIEW_STATUS_KEY, JSON.stringify({
      targetId: 'r1-r2',
      status: 'review_approved',
      meta: { direction: 'supports', evidenceLevel: 'direct', confidence: '0.8', note: '', at: '2026-08-10T00:00:00.000Z' },
    }))
    renderModule()
    await waitFor(() => expect(screen.getByTestId('ew-review-status')).toBeTruthy())
    expect(screen.getByTestId('ew-review-status').textContent).toContain('已审核通过')
  })

  it('置信度影响区:preview 可用时展示 preview 的 Current/Reviewer/Rule/Final', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    expect(screen.getByText('置信度影响')).toBeTruthy()
    expect(screen.getByTestId('ew-impact-current').textContent).toContain('0.7')
    expect(screen.getByTestId('ew-impact-reviewer').textContent).toContain('0.8')
    expect(screen.getByTestId('ew-impact-rule').textContent).toContain('0.85')
    expect(screen.getByTestId('ew-impact-final').textContent).toContain('0.85')
  })

  it('无 preview 时置信度影响本地计算:partial 方向 Rule cap 0.75 / Final 0.75', async () => {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ ...DRAFT, passages: [], modelDirection: 'partial' }))
    renderModule()
    await waitFor(() => expect(screen.getByText('人工最终判断')).toBeTruthy())
    fireEvent.click(screen.getByLabelText('部分支持'))
    expect(screen.getByTestId('ew-impact-rule').textContent).toContain('0.75')
    expect(screen.getByTestId('ew-impact-final').textContent).toContain('0.75')
  })

  it('sticky 底部按钮:驳回证据(次要) + 审核通过(primary)', async () => {
    const { container } = renderModule()
    await waitFor(() => expect(screen.getByTestId('ew-approve-btn')).toBeTruthy())
    const actions = container.querySelector('.ew-sticky-actions')
    expect(actions).toBeTruthy()
    const reject = screen.getByRole('button', { name: '驳回证据' })
    const approve = screen.getByRole('button', { name: '审核通过' })
    expect(reject.className).not.toContain('btn-primary')
    expect(approve.className).toContain('btn-primary')
  })

  // ─── U4:中栏标题体系 + 右栏置信度影响 5 格 ───

  it('中栏标题体系:模块标题「人工审核」+ Claim/Paper/Passage/Coverage 四分区标题齐全', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    // 模块标题(与佐证任务「任务列表」同语言;右栏面板标题同名,取中栏 h3)
    expect(screen.getAllByText('人工审核').length).toBeGreaterThan(0)
    // 中栏不再渲染 ClaimPanel(Claim 在左栏 ClaimSummaryPanel 展示)
    expect(screen.queryByText('当前需要验证的事实')).toBeNull()
    // 分区一:Paper
    expect(screen.getByText('当前论文')).toBeTruthy()
    // 分区二:PassageEvidenceCard(已选佐证原文 + 数量徽标)
    expect(screen.getByText('已选佐证原文')).toBeTruthy()
    expect(screen.getByTestId('evidence-review-passages-count').textContent).toBe('2')
    // 分区三:CoveragePanel
    expect(screen.getByText('Claim 覆盖情况')).toBeTruthy()
  })

  it('置信度影响 5 格:Current/Reviewer/Rule/Maximum/Final(preview 可用时 Maximum = max(current, reviewer))', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.attachPaperEvidencePreview).toHaveBeenCalled())
    expect(screen.getByTestId('ew-impact-current').textContent).toContain('0.7')
    expect(screen.getByTestId('ew-impact-reviewer').textContent).toContain('0.8')
    expect(screen.getByTestId('ew-impact-rule').textContent).toContain('0.85')
    // max(0.7, 0.8) = 0.80
    expect(screen.getByTestId('ew-impact-maximum').textContent).toContain('0.80')
    expect(screen.getByTestId('ew-impact-final').textContent).toContain('0.85')
  })

  it('无 preview 时本地计算 Maximum(partial 方向:reviewer 0.8 高于 current 0.7)', async () => {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ ...DRAFT, passages: [] }))
    renderModule()
    await waitFor(() => expect(screen.getByText('人工最终判断')).toBeTruthy())
    expect(screen.getByTestId('ew-impact-maximum').textContent).toContain('0.80')
  })

  // ─── S6:任务关联禁止静默丢失 ───

  it('任务模式:多匹配(409)→ 显示「无法唯一确定任务项」并禁用审核按钮,不提交 review', async () => {
    vi.mocked(endpoints.resolvePaperEvidenceTaskItem).mockRejectedValueOnce(
      new ApiError(409, 'HTTP 409: {"code":"REVIEW_CONFLICT","message":"ambiguous task item"}'),
    )
    renderModule()
    await waitFor(() => expect(screen.getByTestId('ew-task-link-error').textContent).toContain('无法唯一确定任务项'))
    const approve = screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement
    const reject = screen.getByRole('button', { name: '驳回证据' }) as HTMLButtonElement
    expect(approve.disabled).toBe(true)
    expect(reject.disabled).toBe(true)
    expect(endpoints.buildReview).not.toHaveBeenCalled()
    expect(endpoints.rejectReview).not.toHaveBeenCalled()
  })

  it('任务模式:0 匹配(404)→ 显示明确错误并禁用审核按钮', async () => {
    vi.mocked(endpoints.resolvePaperEvidenceTaskItem).mockRejectedValueOnce(
      new ApiError(404, 'HTTP 404: {"code":"REVIEW_NOT_FOUND","message":"no matching task item"}'),
    )
    renderModule()
    await waitFor(() => expect(screen.getByTestId('ew-task-link-error').textContent).toContain('当前任务中没有匹配该对象的任务项'))
    expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('任务模式:解析未完成时按钮禁用,完成后可用(不降级为 standalone)', async () => {
    let resolveFn: (v: unknown) => void = () => {}
    vi.mocked(endpoints.resolvePaperEvidenceTaskItem).mockImplementation(
      () => new Promise(resolve => { resolveFn = resolve }),
    )
    renderModule()
    await waitFor(() => expect(screen.getByTestId('ew-task-link-resolving')).toBeTruthy())
    expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(true)
    resolveFn({
      task_id: 't1', task_item_id: 'item-1', target_type: 'connection',
      target_id: 'r1-r2', status: 'awaiting_review', matched: 'task_target',
      rescore_source_review_id: null, rescore_revision_no: null,
    })
    await waitFor(() => expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(false))
  })

  it('standalone:无 task_id → payload 两个 ID 均为 null,可正常创建审核(独立审核)', async () => {
    window.location.hash = '#/evidence-center?module=review&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceReviewModule />
        <RightPanel module="review" />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(false))
    expect(endpoints.resolvePaperEvidenceTaskItem).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '审核通过' }))
    await waitFor(() => expect(endpoints.buildReview).toHaveBeenCalled())
    expect(endpoints.buildReview).toHaveBeenCalledWith(expect.objectContaining({
      task_id: null,
      task_item_id: null,
      target_id: 'r1-r2',
    }))
  })

  it('旧 deep link 唯一匹配后以 replace 语义补齐 task_item_id(不产生新历史)', async () => {
    window.location.hash = '#/evidence-center?module=review&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceReviewModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(window.location.hash).toContain('task_item_id=item-1'))
    expect(window.location.hash).toContain('task_id=t1')
    expect(window.location.hash).toContain('target_id=r1-r2')
  })

  it('S7B:重评上下文 → 工作区显示「正在进行第 N 次评分 · 由第 N-1 次审核回退」', async () => {
    vi.mocked(endpoints.resolvePaperEvidenceTaskItem).mockResolvedValue({
      task_id: 't1', task_item_id: 'item-1', target_type: 'connection',
      target_id: 'r1-r2', status: 'awaiting_review', matched: 'task_target',
      rescore_source_review_id: 'old-rev', rescore_revision_no: 2,
    })
    renderModule()
    await waitFor(() =>
      expect(screen.getByTestId('evidence-rescore-banner').textContent).toContain('正在进行第 2 次评分'),
    )
    expect(screen.getByTestId('evidence-rescore-banner').textContent).toContain('由第 1 次审核回退')
  })

  it('approve/reject 成功后触发第五步共享刷新', async () => {
    function RefreshProbe() {
      const { version } = useTaskItemsRefresh()
      return <span data-testid="refresh-version">{version}</span>
    }
    window.location.hash = '#/evidence-center?module=review&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <TaskItemsRefreshProvider>
        <EvidenceCenterProvider>
          <EvidenceReviewModule />
          <RightPanel module="review" />
          <RefreshProbe />
        </EvidenceCenterProvider>
      </TaskItemsRefreshProvider>,
    )
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(false))
    expect(screen.getByTestId('refresh-version').textContent).toBe('0')
    fireEvent.click(screen.getByRole('button', { name: '审核通过' }))
    await waitFor(() => expect(screen.getByTestId('refresh-version').textContent).toBe('1'))
  })

  it('审核通过自动跳转下一条待处理对象;「← 返回上一条」回到上一条', async () => {
    function TwoQueueSeeder() {
      const { setQueue } = useEvidenceCenter()
      useEffect(() => {
        setQueue([
          { target_type: 'connection', target_id: 'r1-r2', label: 'R1 → R2', confidence: 0.7, status: 'awaiting_review' as QueueStatus, evidenceCount: 1, taskItemId: 'item-1' },
          { target_type: 'connection', target_id: 'r3-r4', label: 'R3 → R4', confidence: 0.6, status: 'awaiting_review' as QueueStatus, evidenceCount: 1, taskItemId: 'item-2' },
        ])
      }, [setQueue])
      return null
    }
    window.location.hash = REVIEW_HASH
    render(
      <EvidenceCenterProvider>
        <TwoQueueSeeder />
        <EvidenceReviewModule />
        <RightPanel module="review" />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(false))
    // 初始无返回上一条按钮
    expect(screen.queryByTestId('review-prev-target')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '审核通过' }))
    // 自动跳转下一条 r3-r4
    await waitFor(() => expect(window.location.hash).toContain('target_id=r3-r4'))
    // 返回上一条按钮出现,点击回到 r1-r2
    const backBtn = screen.getByTestId('review-prev-target')
    fireEvent.click(backBtn)
    await waitFor(() => expect(window.location.hash).toContain('target_id=r1-r2'))
  })

  it('已审核对象重复驳回:REVIEW_LINK_INVALID 400 → 提示已完成审核并刷新', async () => {
    vi.mocked(endpoints.buildReview).mockRejectedValueOnce(
      new ApiError(400, 'HTTP 400: {"code":"REVIEW_LINK_INVALID","message":"task item status \'completed\' does not allow review"}'),
    )
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '驳回证据' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: '驳回证据' }))
    await waitFor(() => expect(screen.getByText('该对象已完成审核,不能重复审核')).toBeTruthy())
  })

  it('已驳回对象重新审核:先 reopen 任务项复位,再正常提交(改判支持)', async () => {
    // 模拟已驳回的本地审核记录(「← 返回上一条」场景)
    sessionStorage.setItem(REVIEW_STATUS_KEY, JSON.stringify({
      status: 'rejected',
      targetId: 'r1-r2',
      meta: { direction: 'supports', evidenceLevel: 'indirect', confidence: '0.8', at: '2026-08-18T00:00:00Z' },
    }))
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '驳回证据' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: '驳回证据' }))
    // 已审核 → 先 reopen 复位 item,再走正常 buildReview(驳回直接建 rejected 终态,不调 rejectReview)
    await waitFor(() => expect(endpoints.reopenPaperEvidenceTaskItem).toHaveBeenCalledWith('t1', 'item-1'))
    await waitFor(() => expect(endpoints.buildReview).toHaveBeenCalled())
    expect(endpoints.rejectReview).not.toHaveBeenCalled()
  })

  it('已驳回对象(awaiting_review)重新审核:reopen 报 "item is not completed" → 放行直接提交', async () => {
    sessionStorage.setItem(REVIEW_STATUS_KEY, JSON.stringify({
      status: 'rejected',
      targetId: 'r1-r2',
      meta: { direction: 'supports', evidenceLevel: 'indirect', confidence: '0.8', at: '2026-08-18T00:00:00Z' },
    }))
    // 驳回后 item 保持 awaiting_review → reopen 400 → 应放行继续审核
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockRejectedValueOnce(
      new ApiError(400, 'HTTP 400: {"code":"INVALID_REQUEST","message":"item is not completed"}'),
    )
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '驳回证据' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: '驳回证据' }))
    // reopen 失败被容错 → 正常走 buildReview(驳回直接建 rejected 终态,不调 rejectReview)
    await waitFor(() => expect(endpoints.buildReview).toHaveBeenCalled())
    expect(endpoints.rejectReview).not.toHaveBeenCalled()
    expect(screen.queryByText(/重新打开任务项失败/)).toBeNull()
  })

  it('审核通过后切换到证据列表(队列)的下一条对象:同队列多对象时自动切下一条', async () => {
    function ThreeQueueSeeder() {
      const { setQueue } = useEvidenceCenter()
      useEffect(() => {
        setQueue([
          { target_type: 'connection', target_id: 'r1-r2', label: 'R1 → R2', confidence: 0.7, status: 'awaiting_review' as QueueStatus, evidenceCount: 1, taskItemId: 'item-1' },
          { target_type: 'connection', target_id: 'r3-r4', label: 'R3 → R4', confidence: 0.6, status: 'awaiting_review' as QueueStatus, evidenceCount: 1, taskItemId: 'item-2' },
        ])
      }, [setQueue])
      return null
    }
    window.location.hash = REVIEW_HASH
    render(
      <EvidenceCenterProvider>
        <ThreeQueueSeeder />
        <EvidenceReviewModule />
        <RightPanel module="review" />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    await waitFor(() => expect((screen.getByRole('button', { name: '审核通过' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: '审核通过' }))
    // 切到证据列表下一条:同任务(无 task_id 变化)下一条对象 r3-r4,仍在 review 模块
    await waitFor(() => expect(window.location.hash).toContain('target_id=r3-r4'))
    expect(window.location.hash).toContain('module=review')
    expect(window.location.hash).not.toContain('task_id=t2')
  })
})
