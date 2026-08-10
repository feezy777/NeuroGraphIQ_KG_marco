import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { EvidenceReviewModal } from './EvidenceReviewModal'
import * as endpoints from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  searchPaperEvidence: vi.fn(),
  extractPaperPassage: vi.fn(),
  attachPaperEvidencePreview: vi.fn(),
  attachPaperEvidence: vi.fn(),
  listPaperEvidence: vi.fn(),
  translateEvidenceText: vi.fn(),
  getEvidenceQueue: vi.fn(),
  completePaperEvidenceTaskItem: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  writeEvidenceAudit: vi.fn(),
  getEvidenceTarget: vi.fn(),
  extractSelectedPaperEvidence: vi.fn(),
}))

const ITEM_A = {
  target_type: 'connection',
  target_id: '11111111-1111-1111-1111-111111111111',
  label: '连接 A',
  confidence: 0.42,
}
const ITEM_B = {
  target_type: 'connection',
  target_id: '22222222-2222-2222-2222-222222222222',
  label: '连接 B',
  confidence: 0.55,
}

const PAPER = {
  pmid: '12345',
  doi: '10.1000/xyz',
  title: 'Paper A',
  journal: 'J Neuro',
  year: '2024',
  authors: 'Alice, Bob',
  abstract: 'A real abstract sentence about connectivity and function.',
  source: 'europepmc',
  is_open_access: true,
}

const SEARCH_OK = {
  target_info: {
    target_type: 'connection',
    target_id: ITEM_A.target_id,
    function_term: 'connectivity',
    mode: 'function',
    query: 'connectivity AND function',
    info: {},
  },
  papers: [PAPER],
}

const EXTRACT_OK = {
  overall_direction: 'supports' as const,
  paper_relevance: 0.9,
  assessment: 'relevant',
  source_type: 'abstract' as const,
  passages: [
    {
      source_scope: 'abstract' as const,
      section_title: null,
      paragraph_index: 0,
      paragraph_id: 'abstract_p001',
      passage: 'A real abstract sentence about connectivity and function.',
      translation_zh: null,
      direction: 'supports' as const,
      evidence_level: 'direct' as const,
      reason: 'explicitly mentions the function',
      confidence: 0.8,
      semantic_confidence: 0.8,
      source_locator: 'abstract:0',
      source_verified: true,
      source_verification_method: 'exact',
      supported_components: ['source_region', 'target_region', 'relation', 'direction'],
    },
    {
      source_scope: 'abstract' as const,
      section_title: null,
      paragraph_index: 9,
      paragraph_id: 'abstract_p002',
      passage: 'A fabricated sentence that never appeared.',
      translation_zh: null,
      direction: 'supports' as const,
      evidence_level: 'background' as const,
      reason: 'hallucinated',
      confidence: 0.15,
      semantic_confidence: 0.15,
      source_locator: null,
      source_verified: false,
      source_verification_method: null,
      supported_components: [],
    },
  ],
  parse_status: 'ok',
  retry_count: 0,
  links: { pubmed: 'https://pubmed.ncbi.nlm.nih.gov/12345/' },
}

const PREVIEW_OK = {
  target_type: 'connection',
  target_id: ITEM_A.target_id,
  current_confidence: 0.42,
  direction: 'supports',
  reviewer_confidence: 0.8,
  final_confidence: 0.8,
  cap: 0.85,
  selected_passage_count: 1,
  duplicate_passage_count: 0,
  evidence_text_preview: '[论文证据:e1] Paper A | 12345 | 10.1000/xyz | supports | A real abstract sentence…',
  allow: true,
  block_reasons: [],
}

const ATTACH_OK = {
  evidence_id: 'e1',
  target_type: 'connection',
  target_id: ITEM_A.target_id,
  confidence: 0.8,
  final_confidence: 0.8,
  verification_status: 'human_verified',
  confidence_adjustment_status: 'applied',
  passage_count: 1,
  paper: {
    links: {
      pubmed: 'https://pubmed.ncbi.nlm.nih.gov/12345/',
      doi: 'https://doi.org/10.1000/xyz',
    },
  },
}

function renderWorkbench(initialItems?: typeof ITEM_A[], initialTaskId?: string) {
  return render(
    <EvidenceReviewModal
      open
      initialItems={initialItems}
      initialTaskId={initialTaskId}
      onClose={vi.fn()}
    />,
  )
}

async function runToExtracted() {
  renderWorkbench([ITEM_A, ITEM_B])
  await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
  fireEvent.click(screen.getByText('Paper A'))
  fireEvent.click(screen.getByText('AI 提取原文'))
  await waitFor(() => expect(screen.getAllByTestId('ew-passage')).toHaveLength(2))
}

describe('EvidenceReviewModal 论文佐证工作台', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(endpoints.listPaperEvidence).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue(SEARCH_OK)
    vi.mocked(endpoints.extractPaperPassage).mockResolvedValue(EXTRACT_OK)
    vi.mocked(endpoints.attachPaperEvidencePreview).mockResolvedValue(PREVIEW_OK)
    vi.mocked(endpoints.attachPaperEvidence).mockResolvedValue(ATTACH_OK)
    vi.mocked(endpoints.translateEvidenceText).mockResolvedValue({ translated: '中文翻译' })
    vi.mocked(endpoints.getEvidenceQueue).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.writeEvidenceAudit).mockResolvedValue({ ok: true, action_type: 'x' })
    vi.mocked(endpoints.completePaperEvidenceTaskItem).mockResolvedValue({ task_id: 't', item_id: 'i', status: 'completed' })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue({
      target_type: 'connection',
      target_id: ITEM_A.target_id,
      granularity: 'macro',
      display_name: '连接 A',
      source_region: 'BLA',
      target_region: 'infralimbic cortex',
      canonical_terms: ['fear extinction'],
      relation: 'projection',
      directionality: 'BLA -> IL',
      circuit_context: '',
      function_context: '',
      current_confidence: 0.42,
      existing_evidence: 0,
      structured_claim: {},
      claim_text: 'BLA 到 infralimbic cortex 存在投射，并参与 fear extinction。',
      claim_components: [
        { component_type: 'source_region', statement: '源脑区为 BLA', required: true, metadata: {} },
        { component_type: 'target_region', statement: '靶脑区为 infralimbic cortex', required: true, metadata: {} },
        { component_type: 'relation', statement: 'BLA -> IL 投射', required: true, metadata: {} },
        { component_type: 'direction', statement: 'BLA -> IL', required: true, metadata: {} },
        { component_type: 'function', statement: 'participates in fear extinction', required: true, metadata: {} },
      ],
      claim_version: 'claim_v1',
    })
    vi.mocked(endpoints.extractSelectedPaperEvidence).mockResolvedValue({
      claim: 'c',
      claim_components: [],
      llm_model: 'test',
      results: [
        {
          paper_id: 'p-1',
          pmid: '12345',
          doi: '10.1000/xyz',
          pmcid: '',
          title: 'Paper A',
          journal: 'J Neuro',
          year: '2026',
          is_oa: true,
          paper_match_score: 12,
          model_direction: 'supports',
          model_assessment: 'a',
          coverage_summary: {
            required_components: ['source_region', 'target_region', 'relation'],
            supported_components: ['source_region', 'target_region', 'relation'],
            contradicted_components: [],
            uncovered_components: [],
            coverage_ratio: 1,
            has_conflict: false,
            full_claim_supported: true,
            overall_direction: 'supports',
          },
          passages: [
            {
              source_scope: 'abstract',
              paragraph_id: 'abstract_p001',
              paper_passage_id: 'pp-1',
              passage: 'A real abstract sentence about connectivity and function.',
              direction: 'supports',
              evidence_level: 'direct',
              reason: 'r',
              confidence: 0.8,
              semantic_confidence: 0.8,
              source_verified: true,
              source_verification_method: 'exact',
              supported_components: ['source_region', 'target_region', 'relation'],
            },
          ],
        },
        {
          paper_id: 'p-2',
          pmid: '99999',
          doi: '',
          pmcid: '',
          title: 'Broken Paper',
          journal: 'J',
          year: '2025',
          is_oa: false,
          paper_match_score: 5,
          error_code: 'PAPER_FETCH_FAILED',
          error_message: 'paper not found',
          passages: [],
        },
      ],
    })
  })

  it('渲染单条/多条对象队列与 Stepper，并自动开始第一条检索', async () => {
    renderWorkbench([ITEM_A, ITEM_B])
    await waitFor(() => expect(screen.getAllByTestId('ew-queue-item')).toHaveLength(2))
    expect(screen.getByTestId('ew-stepper').children).toHaveLength(5)
    expect(screen.getAllByText('确认对象').length).toBeGreaterThan(0)
    expect(screen.getAllByText('连接 A').length).toBeGreaterThan(0)
    await waitFor(() => expect(screen.getByTestId('ew-step-label').textContent).toContain('步骤 2/5'))
    expect(vi.mocked(endpoints.searchPaperEvidence)).toHaveBeenCalledWith(
      expect.objectContaining({
        target_type: ITEM_A.target_type,
        target_id: ITEM_A.target_id,
        limit: 10,
        query_override: undefined,
      }),
      expect.any(AbortSignal),
    )
  })

  it('支持编辑检索式并通过 query_override 重新检索', async () => {
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    fireEvent.change(screen.getByPlaceholderText('Europe PMC 检索式（可编辑）'), {
      target: { value: 'custom AND term' },
    })
    fireEvent.click(screen.getByText('重新搜索'))
    await waitFor(() => expect(vi.mocked(endpoints.searchPaperEvidence)).toHaveBeenCalledTimes(2))
    expect(vi.mocked(endpoints.searchPaperEvidence).mock.calls[1][0].query_override).toBe('custom AND term')
    expect(vi.mocked(endpoints.writeEvidenceAudit)).toHaveBeenCalledWith(
      expect.objectContaining({ action_type: 'EVIDENCE_QUERY_EDIT' }),
    )
  })

  it('多片段提取：通过校验的自动选中，未校验片段禁选', async () => {
    await runToExtracted()
    const boxes = screen.getAllByTestId('ew-passage')
      .map(el => el.querySelector('input[type="checkbox"]') as HTMLInputElement)
    expect(boxes[0].checked).toBe(true)
    expect(boxes[1].disabled).toBe(true)
    expect(screen.getByText(/1 个已通过原文核验，1 个未通过核验/)).toBeTruthy()
    expect((screen.getByTestId('ew-attach') as HTMLButtonElement).disabled).toBe(false)
  })

  it('方向为未找到时禁用入库', async () => {
    await runToExtracted()
    fireEvent.click(screen.getByLabelText('未找到'))
    expect((screen.getByTestId('ew-attach') as HTMLButtonElement).disabled).toBe(true)
  })

  it('入库成功后自动进入下一条未处理对象', async () => {
    await runToExtracted()
    fireEvent.click(screen.getByTestId('ew-attach'))
    await waitFor(() => expect(screen.getByTestId('ew-confirm-attach')).toBeTruthy())
    await waitFor(
      () => expect((screen.getByTestId('ew-confirm-attach') as HTMLButtonElement).disabled).toBe(false),
      { timeout: 4000 },
    )
    fireEvent.click(screen.getByTestId('ew-confirm-attach'))
    await waitFor(() => expect(screen.getByText(/已添加 1 篇论文证据/)).toBeTruthy())
    expect(vi.mocked(endpoints.attachPaperEvidence)).toHaveBeenCalledWith(
      expect.objectContaining({
        target_id: ITEM_A.target_id,
        direction: 'supports',
        reviewer_confidence: 0.8,
      }),
    )
    await waitFor(() => expect(screen.getAllByText('连接 B').length).toBeGreaterThan(0))
    await waitFor(() => expect(screen.getByTestId('ew-step-label').textContent).toContain('步骤 2/5'))
  })

  it('入库失败保留草稿与已选片段', async () => {
    vi.mocked(endpoints.attachPaperEvidence).mockRejectedValueOnce(new Error('500 backend boom'))
    await runToExtracted()
    fireEvent.click(screen.getByTestId('ew-attach'))
    await waitFor(
      () => expect((screen.getByTestId('ew-confirm-attach') as HTMLButtonElement).disabled).toBe(false),
      { timeout: 4000 },
    )
    fireEvent.click(screen.getByTestId('ew-confirm-attach'))
    await waitFor(() => expect(screen.getByText(/入库失败：500 backend boom（草稿已保留）/)).toBeTruthy())
    const firstBox = screen.getAllByTestId('ew-passage')[0].querySelector('input') as HTMLInputElement
    expect(firstBox.checked).toBe(true)
  })

  it('关闭后重新打开可从 localStorage 恢复队列', async () => {
    localStorage.setItem(
      'neurographiq.evidenceWorkbench.queue.v1',
      JSON.stringify({
        queue: [{ ...ITEM_B, status: 'pending', evidenceCount: 0 }],
        idx: 0,
        savedAt: new Date().toISOString(),
      }),
    )
    renderWorkbench(undefined)
    await waitFor(() => expect(screen.getByText('已恢复上次处理进度')).toBeTruthy())
    await waitFor(() => expect(screen.getAllByTestId('ew-queue-item')).toHaveLength(1))
    expect(screen.getAllByText('连接 B').length).toBeGreaterThan(0)
  })

  it('检索权限不足时标记失败并提供重试', async () => {
    vi.mocked(endpoints.searchPaperEvidence).mockRejectedValueOnce(new Error('403 Forbidden'))
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByText(/检索失败：403 Forbidden/)).toBeTruthy())
    await waitFor(() => expect(screen.getByText('重试')).toBeTruthy())
  })

  it('候选为空时展示具体原因并可修改关键词', async () => {
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({ ...SEARCH_OK, papers: [] })
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByText(/没有找到符合当前检索式的论文/)).toBeTruthy())
    expect(screen.getByPlaceholderText('Europe PMC 检索式（可编辑）')).toBeTruthy()
  })

  it('OA Only 筛选与排除候选生效', async () => {
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    fireEvent.click(screen.getByText('排除此候选'))
    await waitFor(() => expect(screen.getByText('当前筛选/排除后无论文，请调整筛选条件')).toBeTruthy())
    fireEvent.click(screen.getByText('恢复排除'))
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
  })

  it('全程不使用 window.prompt / window.confirm / alert', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockImplementation(() => null)
    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => false)
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined)
    await runToExtracted()
    fireEvent.click(screen.getByTestId('ew-attach'))
    await waitFor(() => expect(screen.getByTestId('ew-confirm-attach')).toBeTruthy())
    expect(promptSpy).not.toHaveBeenCalled()
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(alertSpy).not.toHaveBeenCalled()
  })

  it('从批量任务恢复草稿队列：加载片段、审核入库并标记任务项完成', async () => {
    const item = {
      id: 'item-1',
      target_type: 'connection',
      target_id: ITEM_A.target_id,
      status: 'awaiting_review',
      pmid: '12345',
      title: 'Paper A',
      passage: null,
      direction: 'supports',
      confidence: 0.82,
      evidence_id: null,
      error_message: null,
      updated_at: '2026-08-07T00:00:00Z',
      label: '连接 A',
      current_confidence: 0.42,
      attempt_count: 1,
      last_error_code: null,
      last_error_message: null,
      preprocess_outcome: 'evidence_found',
      paper_id: 'p-1',
      model_direction: 'supports',
      candidate_papers: [
        {
          paper_id: 'p-1',
          pmid: '12345',
          title: 'Paper A',
          journal: 'J Neuro',
          year: '2026',
          is_oa: true,
          model_direction: 'supports',
          model_assessment: 'relevant',
          coverage_summary: { full_claim_supported: true },
          passages: [
            {
              source_scope: 'abstract',
              section_title: null,
              paragraph_index: 0,
              paragraph_id: 'abstract_p001',
              paper_passage_id: 'pp-1',
              passage: 'A real abstract sentence about connectivity and function.',
              direction: 'supports',
              evidence_level: 'direct',
              reason: 'explicit',
              confidence: 0.82,
              semantic_confidence: 0.82,
              source_locator: 'abstract:0',
              source_verified: true,
              source_verification_method: 'exact',
              supported_components: ['source_region', 'target_region', 'relation'],
            },
          ],
        },
      ],
      review_draft: null,
      claim_text_snapshot: null,
      claim_components_snapshot: null,
      passages_json: null,
      last_error: null,
      retry_count: 0,
    }
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [item] })
    renderWorkbench(undefined, 'task-1')
    await waitFor(() => expect(screen.getByText('已恢复批量任务，共 1 条待审核草稿')).toBeTruthy())
    await waitFor(() => expect(screen.getAllByTestId('ew-passage')).toHaveLength(1))
    expect(screen.getByTestId('ew-step-label').textContent).toContain('步骤 3/5')
    fireEvent.click(screen.getByTestId('ew-attach'))
    await waitFor(
      () => expect((screen.getByTestId('ew-confirm-attach') as HTMLButtonElement).disabled).toBe(false),
      { timeout: 4000 },
    )
    fireEvent.click(screen.getByTestId('ew-confirm-attach'))
    await waitFor(() => expect(screen.getByText(/已添加 1 篇论文证据/)).toBeTruthy())
    expect(vi.mocked(endpoints.completePaperEvidenceTaskItem)).toHaveBeenCalledWith('task-1', 'item-1', 'e1')
  })

  it('提取中显示当前论文名称与进度条', async () => {
    let resolveExtract!: (v: unknown) => void
    vi.mocked(endpoints.extractPaperPassage).mockReturnValue(new Promise(res => { resolveExtract = res }))
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    fireEvent.click(screen.getByText('Paper A'))
    fireEvent.click(screen.getByText('AI 提取原文'))
    await waitFor(() => expect(screen.getAllByText(/DeepSeek 正在提取「Paper A」/).length).toBeGreaterThan(0))
    expect(screen.getByText(/当前论文：/)).toBeTruthy()
    expect(document.querySelector('.ew-progress-track')).toBeTruthy()
    resolveExtract(EXTRACT_OK)
  })

  it('parse_error 时显示友好消息并保留论文名', async () => {
    vi.mocked(endpoints.extractPaperPassage).mockRejectedValueOnce(
      new Error('HTTP 400: {"code":"INVALID_REQUEST","message":"passage extraction failed: parse_error after 3 attempt(s)"}'),
    )
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    fireEvent.click(screen.getByText('Paper A'))
    fireEvent.click(screen.getByText('AI 提取原文'))
    await waitFor(() => expect(screen.getByText(/「Paper A」提取解析失败/)).toBeTruthy())
  })

  it('展示 Claim 与 Claim Components', async () => {
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByTestId('ew-claim-panel')).toBeTruthy())
    expect(screen.getByText('BLA 到 infralimbic cortex 存在投射，并参与 fear extinction。')).toBeTruthy()
    expect(screen.getByText('源脑区')).toBeTruthy()
    expect(screen.getByText('功能')).toBeTruthy()
  })

  it('Passage 展示本段佐证并支持人工调整 supported_components，coverage 联动', async () => {
    await runToExtracted()
    // default: function is not covered by passage 1
    expect(screen.getAllByTestId('ew-passage')[0].textContent).toContain('本段佐证')
    // coverage panel appears with 4/5 (function missing)
    await waitFor(() => expect(screen.getByTestId('ew-coverage-panel')).toBeTruthy())
    expect(screen.getByText(/4 \/ 5 已覆盖/)).toBeTruthy()
    // manually enable function on passage 1 -> coverage 5/5
    const passage1 = screen.getAllByTestId('ew-passage')[0]
    fireEvent.click(passage1.querySelectorAll('.ew-comp-check input')[4])
    await waitFor(() => expect(screen.getByText(/5 \/ 5 已覆盖/)).toBeTruthy())
  })

  it('人工修改 evidence_level 与 reviewer direction（含混合）', async () => {
    await runToExtracted()
    const passage1 = screen.getAllByTestId('ew-passage')[0]
    fireEvent.change(passage1.querySelector('select')!, { target: { value: 'interpretive' } })
    expect((passage1.querySelector('select') as HTMLSelectElement).value).toBe('interpretive')
    fireEvent.click(screen.getByLabelText('混合证据'))
    expect((screen.getByLabelText('混合证据') as HTMLInputElement).checked).toBe(true)
    expect((screen.getByTestId('ew-attach') as HTMLButtonElement).disabled).toBe(false)
  })

  it('关闭时有未保存审核内容则弹出保存草稿 Dialog', async () => {
    await runToExtracted()
    fireEvent.change(screen.getByPlaceholderText('中文翻译（可编辑）'), { target: { value: '人工翻译' } })
    fireEvent.click(screen.getByText('关闭'))
    await waitFor(() => expect(screen.getByText('未保存的审核内容')).toBeTruthy())
    fireEvent.click(screen.getByText('保存并关闭'))
  })

  it('API race：切换对象后旧 extract 响应不会覆盖新对象', async () => {
    let resolveOld!: (v: unknown) => void
    vi.mocked(endpoints.extractPaperPassage).mockReturnValueOnce(new Promise(res => { resolveOld = res }))
    renderWorkbench([ITEM_A, ITEM_B])
    await waitFor(() => expect(screen.getAllByTestId('ew-queue-item')).toHaveLength(2))
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    fireEvent.click(screen.getByText('Paper A'))
    fireEvent.click(screen.getByText('AI 提取原文'))
    // switch to item B before old extract resolves
    fireEvent.click(screen.getAllByTestId('ew-queue-item')[1])
    await waitFor(() => expect(screen.getAllByText('连接 B').length).toBeGreaterThan(0))
    resolveOld(EXTRACT_OK)
    await new Promise(r => setTimeout(r, 100))
    // new object must NOT show old passages
    expect(screen.queryAllByTestId('ew-passage')).toHaveLength(0)
  })

  it('多选论文批量提取：结果按论文分组展示，失败论文隔离，可载入成功论文片段', async () => {
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    // select the paper via checkbox
    const checkbox = screen.getByTestId('ew-paper').querySelector('input[type="checkbox"]') as HTMLInputElement
    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(true)
    fireEvent.click(screen.getByTestId('ew-extract-selected'))
    await waitFor(() => expect(screen.getByTestId('ew-extract-all-results')).toBeTruthy())
    expect(screen.getByText(/批量提取结果（2 篇）/)).toBeTruthy()
    expect(screen.getByText(/PAPER_FETCH_FAILED/)).toBeTruthy()
    fireEvent.click(screen.getByText('选择此论文并载入片段'))
    await waitFor(() => expect(screen.getAllByTestId('ew-passage')).toHaveLength(1))
    expect(screen.getByTestId('ew-step-label').textContent).toContain('步骤 4/5')
    expect(vi.mocked(endpoints.extractSelectedPaperEvidence)).toHaveBeenCalledWith(
      expect.objectContaining({
        target_id: ITEM_A.target_id,
        papers: [expect.objectContaining({ pmid: '12345' })],
      }),
    )
  })

  it('缺少 PMID/DOI 的论文：单篇提取禁用，批量提取自动跳过并提示', async () => {
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      ...SEARCH_OK,
      papers: [
        PAPER,
        { ...PAPER, pmid: '', doi: '', title: 'No Identifier Paper' },
      ],
    })
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getAllByText('No Identifier Paper').length).toBeGreaterThan(0))
    // single extract disabled for identifier-less paper
    fireEvent.click(screen.getAllByText('No Identifier Paper')[0])
    expect((screen.getByText('AI 提取原文') as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/该论文缺少 PMID\/DOI，无法提取/)).toBeTruthy()
    // select all -> identifier-less paper skipped automatically
    fireEvent.click(screen.getByText('全选'))
    fireEvent.click(screen.getByTestId('ew-extract-selected'))
    await waitFor(() => expect(screen.getByText(/已处理 2 篇论文：1 篇找到有效片段/)).toBeTruthy())
    expect(vi.mocked(endpoints.extractSelectedPaperEvidence)).toHaveBeenCalledWith(
      expect.objectContaining({
        papers: [expect.objectContaining({ pmid: '12345' })], // identifier-less paper excluded
      }),
    )
  })
})
