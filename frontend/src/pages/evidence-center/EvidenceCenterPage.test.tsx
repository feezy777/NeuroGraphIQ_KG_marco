import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { EvidenceCenterPage } from './EvidenceCenterPage'
import {
  attachPaperEvidence,
  attachPaperEvidencePreview,
  extractSelectedPaperEvidence,
  getEvidenceTarget,
  listEvidencePapers,
  listEvidenceReviews,
  listPaperEvidence,
  listPaperEvidenceTaskItems,
  listPaperEvidenceTasks,
  resolvePaperEvidenceTaskItem,
  rollbackPaperEvidence,
  saveTaskItemDraft,
  searchPaperEvidence,
  translateEvidenceText,
  validatePassageSelection,
} from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  listEvidencePapers: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  listEvidenceReviews: vi.fn(),
  getEvidenceTarget: vi.fn(),
  searchPaperEvidence: vi.fn(),
  extractSelectedPaperEvidence: vi.fn(),
  listPaperEvidence: vi.fn(),
  attachPaperEvidencePreview: vi.fn(),
  attachPaperEvidence: vi.fn(),
  rollbackPaperEvidence: vi.fn(),
  translateEvidenceText: vi.fn(),
  saveTaskItemDraft: vi.fn(),
  validatePassageSelection: vi.fn(),
  resolvePaperEvidenceTaskItem: vi.fn(),
}))

/** 默认 mock 实现(与 beforeEach 重置一致;避免测试间 mock 实现污染造成顺序依赖) */
function setupDefaultMocks() {
  vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(listEvidencePapers).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
  vi.mocked(listEvidenceReviews).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(getEvidenceTarget).mockResolvedValue(null)
  vi.mocked(searchPaperEvidence).mockResolvedValue({ target_info: {}, papers: [] })
  vi.mocked(extractSelectedPaperEvidence).mockResolvedValue({ results: [] })
  vi.mocked(listPaperEvidence).mockResolvedValue({ items: [] })
  vi.mocked(attachPaperEvidencePreview).mockResolvedValue({})
  vi.mocked(attachPaperEvidence).mockResolvedValue({})
  vi.mocked(rollbackPaperEvidence).mockResolvedValue({})
  vi.mocked(translateEvidenceText).mockResolvedValue({ translated: '' })
  vi.mocked(saveTaskItemDraft).mockResolvedValue({ server_revision: 0 })
  vi.mocked(validatePassageSelection).mockResolvedValue({ source_verified: true })
  vi.mocked(resolvePaperEvidenceTaskItem).mockResolvedValue({
    task_id: 't1', task_item_id: 'it', target_type: 'connection',
    target_id: 'r1-r2', status: 'awaiting_review', matched: 'task_target',
    rescore_source_review_id: null, rescore_revision_no: null,
  })
}

function makeItem(overrides: Record<string, unknown>) {
  return {
    id: 'it',
    target_type: 'connection',
    target_id: 'r1-r2',
    status: 'awaiting_review',
    pmid: null,
    title: null,
    passage: null,
    direction: null,
    confidence: null,
    evidence_id: null,
    error_message: null,
    updated_at: null,
    label: 'R1→R2',
    current_confidence: 0.85,
    attempt_count: 0,
    last_error_code: null,
    last_error_message: null,
    preprocess_outcome: null,
    paper_id: null,
    model_direction: null,
    candidate_papers: [],
    review_draft: null,
    claim_text_snapshot: null,
    claim_components_snapshot: null,
    passages_json: null,
    last_error: null,
    retry_count: 0,
    ...overrides,
  }
}

const TASK_ITEMS = [
  makeItem({
    candidate_papers: [{
      paper_id: 'p1',
      pmid: '12345678',
      doi: null,
      pmcid: null,
      title: 'Paper One',
      journal: 'Brain Journal',
      year: '2024',
      is_oa: true,
      fulltext_fetched: true,
      model_direction: null,
      model_assessment: null,
      coverage_summary: null,
      passages: [{
        passage: 'R1 projects to R2 in the macaque.',
        source_scope: 'abstract',
        section_title: null,
        direction: 'supports',
        evidence_level: 'direct',
        source_verified: true,
        supported_components: ['relation'],
      }],
    }],
  }),
  makeItem({
    id: 'it2',
    target_type: 'region',
    target_id: 'r3',
    label: 'R3',
    status: 'completed',
    current_confidence: 0.9,
    candidate_papers: [{ paper_id: 'p1' }],
  }),
]

const TASK_FIXTURE = {
  id: 'ta', target_type: 'connection', name: '任务A', status: 'pending',
  target_id: 'r1-r2', display_name_cn: 'R1→R2', display_name_en: 'R1→R2',
  display_confidence: 0.2, display_name_source: 'mirror_live', display_confidence_source: 'mirror_live',
  work_status: 'awaiting_review',
  item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 },
  capabilities: { can_continue_review: true, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false },
  total_items: 2, processed_items: 0, awaiting_review_items: 2, failed_items: 0,
  review_status: 'not_started', granularity_level: 'macro',
  estimated_target_count: 2, materialized_target_count: 2,
  scope: 'filter', mode: 'existence', max_papers_per_object: 3,
  created_at: '2026-08-10T00:00:00Z', created_by: null,
  started_at: null, finished_at: null, error_message: null, materialization_status: 'completed',
  materialization_cursor: null, materialization_error: null, confidence_lt: null,
  only_oa: false, stop_after_strong_support: false, summary: null,
  scope_type: 'filter', filter_snapshot: null, versions: null,
}

describe('EvidenceCenterPage', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.resetAllMocks()
    setupDefaultMocks()
  })

  afterEach(() => {
    cleanup()
    window.location.hash = ''
    sessionStorage.clear()
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
  })

  it('渲染五模块导航与默认说明句', () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterPage />)
    const nav = screen.getByTestId('evidence-module-nav')
    expect(within(nav).getByText('佐证任务')).toBeTruthy()
    expect(within(nav).getByText('论文库')).toBeTruthy()
    expect(within(nav).getByText('证据候选')).toBeTruthy()
    expect(within(nav).getByText('人工审核')).toBeTruthy()
    expect(within(nav).getByText('证据晋升')).toBeTruthy()
    // 导航选中态:默认模块 tasks 的胶囊为 active
    expect(within(nav).getByRole('button', { name: '佐证任务' }).className).toContain('evidence-module-btn active')
    expect(within(nav).getByRole('button', { name: '论文库' }).className).not.toContain('active')
  })

  it('模块导航切换更新 URL 与内容区', async () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterPage />)
    fireEvent.click(screen.getByText('论文库'))
    await waitFor(() => expect(window.location.hash).toContain('module=papers'))
    expect(screen.getByText('管理系统已经获取和解析的真实论文资源。')).toBeTruthy()
    fireEvent.click(screen.getByText('返回数据中心'))
    await waitFor(() => expect(window.location.hash).toContain('/data-center'))
  })

  it.each([
    { module: 'papers', selector: '.paper-module', text: /暂无论文/ },
    { module: 'candidates', selector: '.evidence-candidates', text: /请先在「佐证任务」中打开一个任务/ },
    { module: 'review', selector: '.evidence-review', text: /请先从「佐证任务」或「证据候选」进入一个目标对象/ },
    { module: 'promotion', selector: '.evidence-review', text: /请先从「佐证任务」进入一个目标对象/ },
  ])('五模块接线:module=$module 渲染对应模块', async ({ module, selector, text }) => {
    window.location.hash = `#/evidence-center?module=${module}`
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(container.querySelector(selector)).toBeTruthy())
    expect(screen.getByText(text)).toBeTruthy()
  })

  // ─── V2 三栏骨架 ───

  it('渲染三栏骨架:candidates 左栏 Claim / 主内容 / 右栏队列', () => {
    window.location.hash = '#/evidence-center?module=candidates'
    const { container } = render(<EvidenceCenterPage />)
    // 页面根:背景面板 + 三栏布局(背景类随 .evidence-center 生效)
    expect(container.querySelector('.evidence-center')).toBeTruthy()
    expect(container.querySelector('.evidence-center-layout')).toBeTruthy()
    expect(container.querySelector('.evidence-left')).toBeTruthy()
    expect(container.querySelector('.evidence-main')).toBeTruthy()
    expect(container.querySelector('.evidence-right')).toBeTruthy()
    // 候选模块:左栏 ClaimSummaryPanel,右栏 EvidenceQueuePanel(队列已从左侧移到右栏)
    const left = container.querySelector('.evidence-left') as HTMLElement
    expect(within(left).getByTestId('evidence-claim-summary')).toBeTruthy()
    expect(left.querySelector('.evidence-queue')).toBeNull()
    expect(screen.getByTestId('evidence-queue-panel')).toBeTruthy()
    expect(screen.getByTestId('evidence-right-panel')).toBeTruthy()
  })

  it('其他模块左栏仍渲染 ObjectQueue(review/promotion/tasks 布局不变)', () => {
    window.location.hash = '#/evidence-center?module=review'
    const { container } = render(<EvidenceCenterPage />)
    const left = container.querySelector('.evidence-left') as HTMLElement
    expect(within(left).getByTestId('evidence-queue')).toBeTruthy()
    expect(left.querySelector('.evidence-claim')).toBeNull()
  })

  it('papers 模块例外:全宽渲染并隐藏左右栏,论文库主区布局完整', async () => {
    window.location.hash = '#/evidence-center?module=papers'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(container.querySelector('.evidence-center-layout-full')).toBeTruthy())
    expect(container.querySelector('.evidence-left')).toBeNull()
    expect(container.querySelector('.evidence-right')).toBeNull()
    // 全宽下论文库完整渲染:搜索条 + 空态(不受 620px 主区限制影响)
    expect(container.querySelector('.paper-module')).toBeTruthy()
    expect(container.querySelector('.paper-search-bar')).toBeTruthy()
    await waitFor(() => expect(screen.getByText(/暂无论文/)).toBeTruthy())
  })

  it('tasks 布局:左栏任务筛选+预览空态,右栏已处理面板', async () => {
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-processed-panel')).toBeTruthy())
    expect(screen.getByTestId('task-filter-preview')).toBeTruthy()
    expect(screen.getByTestId('task-preview-hint').textContent).toContain('点击任务卡片查看验证事实')
    fireEvent.click(screen.getByText('证据候选'))
    await waitFor(() => expect(screen.getByTestId('evidence-queue-panel')).toBeTruthy())
    const title = () => container.querySelector('.evidence-right-panel h4')?.textContent ?? ''
    expect(title()).toContain('待处理对象')
  })

  it('tasks 三栏常显:左栏待处理队列,中栏工作区提示,右栏已处理面板', async () => {
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE], total: 1 })
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [makeItem({ id: 'it-x', target_id: 'r1-r2', label: 'R1→R2', status: 'awaiting_review', current_confidence: 0.2 })] })
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getAllByText('R1→R2').length).toBeGreaterThan(0))
    expect(container.querySelector('.evidence-left')).toBeTruthy()
    expect(container.querySelector('.evidence-right')).toBeTruthy()
    expect(container.querySelector('.evidence-center-layout-full')).toBeNull()
    expect(screen.getByTestId('evidence-task-card-grid')).toBeTruthy()
  })

  it('candidates 右栏渲染对象队列;中栏统计条 [进入人工审核] 勾选后可用并跳转 review', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    // 右栏 = 待处理对象队列(队列条目在右栏)
    await waitFor(() => expect(screen.getByTestId('evidence-queue-panel')).toBeTruthy())
    expect(screen.queryByTestId('evidence-candidate-summary')).toBeNull()
    // 中栏统计条零选中时 [进入人工审核] 禁用
    expect(screen.getByTestId('evidence-stats-bar')).toBeTruthy()
    expect((screen.getByRole('button', { name: /进入人工审核/ }) as HTMLButtonElement).disabled).toBe(true)
    // 勾选已核验片段后启用(限定在证据视图内)
    fireEvent.click(screen.getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(within(screen.getByTestId('evidence-paper-view')).getByLabelText('选择片段'))
    await waitFor(() =>
      expect((screen.getByRole('button', { name: /进入人工审核/ }) as HTMLButtonElement).disabled).toBe(false),
    )
    fireEvent.click(screen.getByRole('button', { name: /进入人工审核/ }))
    await waitFor(() => expect(window.location.hash).toContain('module=review'))
    expect(window.location.hash).toContain('target_id=r1-r2')
  })

  it('候选统计条禁止项:无 Reviewer Confidence / Direction 控件', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-stats-bar')).toBeTruthy())
    expect(screen.queryByText(/Reviewer Confidence/i)).toBeNull()
    expect(screen.queryByText(/Reviewer Direction/i)).toBeNull()
    expect(screen.queryByRole('slider')).toBeNull()
  })

  it('granularity 从候选模块 DTO 填充队列并显示在 ContextBar', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    const { getEvidenceTarget } = await import('../../api/endpoints')
    vi.mocked(getEvidenceTarget).mockResolvedValue({
      target_type: 'connection',
      target_id: 'r1-r2',
      granularity: 'macro_clinical',
      display_name: 'R1→R2',
      source_region: 'R1',
      target_region: 'R2',
      canonical_terms: [],
      relation: 'projects_to',
      directionality: '',
      circuit_context: '',
      function_context: '',
      current_confidence: 0.85,
      existing_evidence: 0,
      structured_claim: {},
      claim_text: 'R1 投射到 R2',
      claim_components: [],
      claim_version: 'v1',
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    const bar = await screen.findByTestId('evidence-context-bar')
    await waitFor(() => expect(within(bar).getByText(/粒度 macro_clinical/)).toBeTruthy())
  })

  it('ContextBar 渲染完整事实句(candidates DTO claim 组件拼装,含方向)', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    const { getEvidenceTarget } = await import('../../api/endpoints')
    vi.mocked(getEvidenceTarget).mockResolvedValue({
      target_type: 'connection',
      target_id: 'r1-r2',
      granularity: 'macro_clinical',
      display_name: 'R1→R2',
      source_region: 'R1',
      target_region: 'R2',
      canonical_terms: [],
      relation: 'projects_to',
      directionality: '',
      circuit_context: '',
      function_context: '',
      current_confidence: 0.85,
      existing_evidence: 0,
      structured_claim: {},
      claim_text: 'R1 投射到 R2',
      claim_components: [
        { component_type: 'source_region', statement: 'R1', required: true, metadata: {} },
        { component_type: 'target_region', statement: 'R2', required: true, metadata: {} },
        { component_type: 'relation', statement: '存在投射连接', required: true, metadata: {} },
        { component_type: 'direction', statement: 'directed', required: false, metadata: {} },
      ],
      claim_version: 'v1',
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    const bar = await screen.findByTestId('evidence-context-bar')
    await waitFor(() =>
      expect(within(bar).getByText('需要验证:R1 到 R2 存在投射连接(方向性:directed)')).toBeTruthy(),
    )
  })

  it('candidates 左栏渲染 ClaimSummaryPanel(页面级):DTO 加载后显示类型/源脑区/连接关系信息块;中栏不再渲染', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    const { getEvidenceTarget } = await import('../../api/endpoints')
    vi.mocked(getEvidenceTarget).mockResolvedValue({
      target_type: 'connection',
      target_id: 'r1-r2',
      granularity: 'macro_clinical',
      display_name: 'R1→R2',
      source_region: 'R1',
      target_region: 'R2',
      canonical_terms: [],
      relation: 'projects_to',
      directionality: '',
      circuit_context: '',
      function_context: '',
      current_confidence: 0.85,
      existing_evidence: 0,
      structured_claim: {},
      claim_text: 'R1 投射到 R2',
      claim_components: [
        { component_type: 'source_region', statement: 'R1', required: true, metadata: {} },
        { component_type: 'relation', statement: '存在投射关系', required: true, metadata: {} },
      ],
      claim_version: 'v1',
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => {
      const left = container.querySelector('.evidence-left') as HTMLElement
      expect(within(left).getByText('存在投射关系')).toBeTruthy()
    })
    // 左栏:独立信息块(类型 + 源脑区 + 连接关系)
    const left = container.querySelector('.evidence-left') as HTMLElement
    expect(within(left).getByTestId('evidence-claim-summary')).toBeTruthy()
    expect(within(left).getByText('当前需要验证的事实')).toBeTruthy()
    const blocks = within(left).getAllByTestId('evidence-claim-block')
    expect(blocks).toHaveLength(3)
    expect(blocks[0].textContent).toContain('类型')
    expect(blocks[0].textContent).toContain('connection')
    expect(blocks[1].textContent).toContain('源脑区')
    expect(blocks[1].textContent).toContain('R1')
    expect(blocks[2].textContent).toContain('连接关系')
    expect(blocks[2].textContent).toContain('存在投射关系')
    // 中栏不再渲染 ClaimSummaryPanel
    const main = container.querySelector('.evidence-main') as HTMLElement
    expect(main.querySelector('.evidence-claim-summary')).toBeNull()
  })

  it('无任务时 initial-queue 恢复的条目渲染在页面级右栏 ObjectQueue(candidates)', async () => {
    sessionStorage.setItem(
      'evidence-center.initial-queue',
      JSON.stringify({
        items: [
          { target_type: 'connection', target_id: 'r1-r2', label: 'R1 → R2 连接', confidence: 0.7 },
          { target_type: 'region_function', target_id: 'f-1', label: 'R1 功能', confidence: 0.5 },
        ],
        taskId: null,
      }),
    )
    window.location.hash = '#/evidence-center?module=candidates&target_type=connection&target_id=r1-r2'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByText('R1 功能')).toBeTruthy())
    // 队列条目渲染在页面级右栏 EvidenceQueuePanel(上下文条中也出现 label,需在队列内断言)
    expect(within(screen.getByTestId('evidence-queue-panel')).getByText('R1 → R2 连接')).toBeTruthy()
    expect(screen.getByText(/已从数据中心恢复 2 个待处理对象/)).toBeTruthy()
  })

  it('ContextBar 显示当前对象、类型、置信度、证据数与队列进度', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    const bar = await screen.findByTestId('evidence-context-bar')
    await waitFor(() => expect(within(bar).getByText('R1→R2')).toBeTruthy())
    expect(within(bar).getByText('connection')).toBeTruthy()
    expect(within(bar).getByText(/置信度 85%/)).toBeTruthy()
    expect(within(bar).getByText(/1 条证据/)).toBeTruthy()
    expect(within(bar).getByText(/1\/2/)).toBeTruthy()
    expect(within(bar).getByText('待审核')).toBeTruthy()
  })

  it('队列为空时 ContextBar 显示占位', async () => {
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterPage />)
    const bar = await screen.findByTestId('evidence-context-bar')
    expect(within(bar).getByText('未选择对象')).toBeTruthy()
    expect(within(bar).getByText(/等待处理对象/)).toBeTruthy()
  })

  it('candidates 右栏 EvidenceQueuePanel:默认待审核 Tab 只显示未处理项,切 Tab 显示已完成', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-queue-panel')).toBeTruthy())
    // Tabs 计数:待审核 1(连接A)/ 已完成 1(脑区R3)/ 失败 0
    expect(screen.getByRole('tab', { name: /待审核/ }).textContent).toContain('1')
    expect(screen.getByRole('tab', { name: /已完成/ }).textContent).toContain('1')
    expect(screen.getByRole('tab', { name: /失败/ }).textContent).toContain('0')
    // 默认待审核 Tab:仅 awaiting_review 的 R1→R2 可见且为当前项高亮
    const items = screen.getAllByTestId('evidence-queue-item')
    expect(items).toHaveLength(1)
    expect(items[0].textContent).toContain('R1→R2')
    expect(items[0].textContent).toContain('待审核')
    expect(items[0].className).toContain('evidence-queue-item-active')
    // 切换已完成 Tab:显示脑区 R3,当前项不高亮
    fireEvent.click(screen.getByRole('tab', { name: /已完成/ }))
    const doneItems = screen.getAllByTestId('evidence-queue-item')
    expect(doneItems).toHaveLength(1)
    expect(doneItems[0].textContent).toContain('R3')
    expect(doneItems[0].className).not.toContain('evidence-queue-item-active')
  })

  it('任务卡点击 → 仅选中(URL 不变)+ 左栏预览联动', async () => {
    const taskA = { ...TASK_FIXTURE, id: 'ta' }
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [taskA], total: 1 })
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-task-card-ta')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-ta'))
    // 不跳转
    expect(window.location.hash).not.toContain('module=candidates')
    expect(window.location.hash).not.toContain('task_id=')
    // 左栏预览出现该任务信息
    await waitFor(() => expect(screen.getByTestId('task-preview-card')).toBeTruthy())
    expect(screen.getByTestId('task-preview-card').textContent).toContain('R1→R2')
    expect(screen.getByTestId('task-preview-continue')).toBeTruthy()
  })

  it('StepPills 渲染五步并随 module 高亮当前步', async () => {
    window.location.hash = '#/evidence-center?module=candidates'
    render(<EvidenceCenterPage />)
    const pills = await screen.findByTestId('evidence-step-pills')
    for (const label of ['确认对象', '查找论文', '找到原文', '人工审核', '确认晋升']) {
      expect(within(pills).getByText(label)).toBeTruthy()
    }
    expect(pills.querySelector('.evidence-step-pill.active')?.textContent).toContain('确认对象')
    fireEvent.click(screen.getAllByText('人工审核')[0])
    await waitFor(() => expect(window.location.hash).toContain('module=review'))
    expect(screen.getByTestId('evidence-step-pills').querySelector('.evidence-step-pill.active')?.textContent)
      .toContain('人工审核')
  })

  it('tasks 深链带 target 参数 → 自动跳转 candidates(右栏点击兼容)', async () => {
    const taskA = { ...TASK_FIXTURE, id: 'ta' }
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [taskA], total: 1 })
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=tasks&task_id=ta&target_type=connection&target_id=r1-r2'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=ta')
    expect(window.location.hash).toContain('target_id=r1-r2')
  })

  it('佐证页选中对象后点「佐证任务」导航可回到列表(不回弹)', async () => {
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE], total: 1 })
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=candidates&task_id=ta&target_type=connection&target_id=r1-r2'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-module-nav')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '佐证任务' }))
    // 回到任务列表:URL 清空 target/模块参数(buildEvidenceUrl 省略默认 module=tasks,解析时回落 tasks)
    await screen.findByTestId('evidence-task-card-grid')
    expect(window.location.hash).not.toContain('target_id=')
    expect(window.location.hash).not.toContain('target_type=')
    expect(window.location.hash).not.toContain('module=candidates')
  })
})
