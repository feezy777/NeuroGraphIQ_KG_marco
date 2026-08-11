import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider, useEvidenceCenter } from '../EvidenceCenterContext'
import { RightPanel } from '../components/RightPanel'
import type { EvidenceLevel, QueueStatus, WorkbenchPassage } from '../components/types'
import { EvidenceReviewModule } from './EvidenceReviewModule'

vi.mock('../../../api/endpoints', () => ({
  approveReview: vi.fn(),
  getEvidenceTarget: vi.fn(),
  attachPaperEvidencePreview: vi.fn(),
  attachPaperEvidence: vi.fn(),
  buildReview: vi.fn(),
  rejectReview: vi.fn(),
  translateEvidenceText: vi.fn(),
  validatePassageSelection: vi.fn(),
  saveTaskItemDraft: vi.fn(),
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
    vi.mocked(endpoints.buildReview).mockResolvedValue({ review_id: 'rev-1', status: 'approved' })
    vi.mocked(endpoints.rejectReview).mockResolvedValue({ review_id: 'rev-1', status: 'rejected' })
  })

  it('从 sessionStorage draft 恢复 passages 并渲染 PassageEvidenceCard + AI 初判', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    expect(screen.getByText('A secondary passage without verification.')).toBeTruthy()
    expect(screen.getByText('未通过原文校验，请人工核对或重新截取')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('ew-ai-direction').textContent).toBe('支持'))
    // 未核验片段不可勾选
    const cards = screen.getAllByTestId('ew-passage')
    const checkboxes = cards.map(c => c.querySelector('input[type="checkbox"]')) as HTMLInputElement[]
    expect(checkboxes[0].disabled).toBe(false)
    expect(checkboxes[1].disabled).toBe(true)
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
    expect(screen.getByText('已审核通过，进入「证据晋升」模块待晋升')).toBeTruthy()
    // 审核不调旧 attach
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
    // buildReview body 断言
    expect(endpoints.buildReview).toHaveBeenCalledWith(expect.objectContaining({
      target_type: 'connection',
      target_id: 'r1-r2',
      reviewer_direction: 'supports',
      reviewer_evidence_level: 'indirect',
      reviewer_confidence: 0.8,
    }))
  })

  it('驳回证据:写 rejected + 调 buildReview + rejectReview + 提示 + 不调 attach', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '驳回证据' }))
    await waitFor(() => expect(sessionStorage.getItem(REVIEW_STATUS_KEY)).toBeTruthy())
    await waitFor(() => expect(endpoints.buildReview).toHaveBeenCalled())
    await waitFor(() => expect(endpoints.rejectReview).toHaveBeenCalledWith('rev-1'))
    const record = JSON.parse(sessionStorage.getItem(REVIEW_STATUS_KEY)!)
    expect(record.status).toBe('rejected')
    expect(record.meta.direction).toBe('supports')
    expect(screen.getByText(/不会进入晋升/)).toBeTruthy()
    expect(endpoints.attachPaperEvidence).not.toHaveBeenCalled()
  })

  it('审核通过:buildReview 失败时提示错误,保留草稿', async () => {
    vi.mocked(endpoints.buildReview).mockRejectedValueOnce(new Error('后端不可用'))
    renderModule()
    await waitFor(() => expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy())
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
    // 分区一:Claim(ClaimPanel)
    expect(screen.getByText('当前需要验证的事实')).toBeTruthy()
    // 分区二:Paper
    expect(screen.getByText('当前论文')).toBeTruthy()
    // 分区三:PassageEvidenceCard(已选佐证原文 + 数量徽标)
    expect(screen.getByText('已选佐证原文')).toBeTruthy()
    expect(screen.getByTestId('evidence-review-passages-count').textContent).toBe('2')
    // 分区四:CoveragePanel
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
})
