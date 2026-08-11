import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { EvidenceCenterPage } from './EvidenceCenterPage'
import { listPaperEvidenceTaskItems, listPaperEvidenceTasks } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  listEvidencePapers: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  listPaperEvidenceTaskItems: vi.fn().mockResolvedValue({ items: [] }),
  getEvidenceTarget: vi.fn().mockResolvedValue(null),
  searchPaperEvidence: vi.fn().mockResolvedValue({ target_info: {}, papers: [] }),
  extractSelectedPaperEvidence: vi.fn().mockResolvedValue({ results: [] }),
  listPaperEvidence: vi.fn().mockResolvedValue({ items: [] }),
  attachPaperEvidencePreview: vi.fn().mockResolvedValue({}),
  attachPaperEvidence: vi.fn().mockResolvedValue({}),
  rollbackPaperEvidence: vi.fn().mockResolvedValue({}),
  translateEvidenceText: vi.fn().mockResolvedValue({ translated: '' }),
  saveTaskItemDraft: vi.fn().mockResolvedValue({ server_revision: 0 }),
  validatePassageSelection: vi.fn().mockResolvedValue({ source_verified: true }),
}))

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
    { module: 'promotion', selector: '.evidence-promotion', text: /请先从「佐证任务」或「证据候选」进入一个目标对象/ },
  ])('五模块接线:module=$module 渲染对应模块', async ({ module, selector, text }) => {
    window.location.hash = `#/evidence-center?module=${module}`
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(container.querySelector(selector)).toBeTruthy())
    expect(screen.getByText(text)).toBeTruthy()
  })

  // ─── V2 三栏骨架 ───

  it('渲染三栏骨架:左队列 / 主内容 / 右栏', () => {
    window.location.hash = '#/evidence-center?module=candidates'
    const { container } = render(<EvidenceCenterPage />)
    expect(container.querySelector('.evidence-center-layout')).toBeTruthy()
    expect(container.querySelector('.evidence-left')).toBeTruthy()
    expect(container.querySelector('.evidence-main')).toBeTruthy()
    expect(container.querySelector('.evidence-right')).toBeTruthy()
    expect(screen.getByTestId('evidence-queue')).toBeTruthy()
    expect(screen.getByTestId('evidence-right-panel')).toBeTruthy()
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

  it('右栏随 module 切换:占位标题(任务/审核)与候选摘要(candidates)', () => {
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    const title = () => container.querySelector('.evidence-right-panel h4')?.textContent ?? ''
    expect(title()).toContain('任务')
    fireEvent.click(screen.getByText('证据候选'))
    expect(title()).toContain('候选摘要')
    fireEvent.click(screen.getAllByText('人工审核')[0])
    expect(title()).toContain('审核')
  })

  it('candidates 右栏渲染 CandidateSummary,勾选片段后点击 [进入人工审核] 跳转 review', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-candidate-summary')).toBeTruthy())
    // 零选中时 [进入人工审核] 禁用
    expect((screen.getByRole('button', { name: /进入人工审核/ }) as HTMLButtonElement).disabled).toBe(true)
    // 勾选已核验片段后启用(左栏 ObjectQueue 也有 checkbox,需限定在证据视图内)
    fireEvent.click(screen.getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(within(screen.getByTestId('evidence-paper-view')).getByLabelText('选择片段'))
    await waitFor(() =>
      expect((screen.getByRole('button', { name: /进入人工审核/ }) as HTMLButtonElement).disabled).toBe(false),
    )
    fireEvent.click(screen.getByRole('button', { name: /进入人工审核/ }))
    await waitFor(() => expect(window.location.hash).toContain('module=review'))
    expect(window.location.hash).toContain('target_id=r1-r2')
  })

  it('候选摘要禁止项:无 Reviewer Confidence / Direction 控件', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-candidate-summary')).toBeTruthy())
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

  it('无任务时 initial-queue 恢复的条目渲染在页面级左栏 ObjectQueue', async () => {
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
    // 队列条目渲染在页面级左栏 ObjectQueue(上下文条中也出现 label,需在队列内断言)
    expect(within(screen.getByTestId('evidence-queue')).getByText('R1 → R2 连接')).toBeTruthy()
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

  it('ObjectQueue 渲染待处理对象列表且当前项高亮', async () => {
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: TASK_ITEMS })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByText('待处理对象')).toBeTruthy())
    const items = screen.getAllByTestId('evidence-queue-item')
    expect(items).toHaveLength(2)
    expect(items[0].textContent).toContain('R1→R2')
    expect(items[0].textContent).toContain('待审核')
    expect(items[0].className).toContain('evidence-queue-item-active')
    expect(items[1].className).not.toContain('evidence-queue-item-active')
  })

  it('切换任务后 URL 不再残留上一任务 target,候选加载后回写到新任务首个 item', async () => {
    const taskB = { ...TASK_FIXTURE, id: 'tb', name: '任务B' }
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE, taskB], total: 2 })
    vi.mocked(listPaperEvidenceTaskItems).mockImplementation(async (taskId: string) => ({
      items: taskId === 'tb'
        ? [makeItem({ id: 'it-b', target_type: 'region', target_id: 'rB', label: 'RB', current_confidence: 0.5 })]
        : [makeItem({ id: 'it-a', target_type: 'connection', target_id: 'rA', label: 'RA' })],
    }))
    // 模拟陈旧状态:URL 残留任务A的 target,但停留在 tasks 模块
    window.location.hash = '#/evidence-center?module=tasks&task_id=ta&target_type=connection&target_id=stale-target'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByText('任务B')).toBeTruthy())
    fireEvent.click(within(screen.getByTestId('evidence-task-row-tb')).getByText('打开任务'))
    // 打开任务B:task_id 更新且陈旧 target 被清除
    await waitFor(() => expect(window.location.hash).toContain('task_id=tb'))
    expect(window.location.hash).not.toContain('target_id=stale-target')
    // 候选加载后 URL 回写到新任务首个 item
    await waitFor(() => expect(window.location.hash).toContain('target_id=rB'))
    expect(window.location.hash).toContain('target_type=region')
    expect(window.location.hash).not.toContain('rA')
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
})
