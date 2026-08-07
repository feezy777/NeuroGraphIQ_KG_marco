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
      passage: 'A real abstract sentence about connectivity and function.',
      direction: 'supports' as const,
      reason: 'explicitly mentions the function',
      confidence: 0.8,
      source_locator: 'abstract:0',
      source_verified: true,
    },
    {
      source_scope: 'abstract' as const,
      section_title: null,
      paragraph_index: 9,
      passage: 'A fabricated sentence that never appeared.',
      direction: 'supports' as const,
      reason: 'hallucinated',
      confidence: 0.15,
      source_locator: null,
      source_verified: false,
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
    fireEvent.click(screen.getByText('重新检索'))
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
    expect(screen.getByText('1/2 个片段通过原文校验')).toBeTruthy()
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
    await waitFor(() => expect(screen.getByText('确认')).toBeTruthy())
    await waitFor(
      () => expect((screen.getByTestId('ew-confirm-attach') as HTMLButtonElement).disabled).toBe(false),
      { timeout: 4000 },
    )
    fireEvent.click(screen.getByTestId('ew-confirm-attach'))
    await waitFor(() => expect(screen.getByText(/入库成功/)).toBeTruthy())
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
    await waitFor(() => expect(screen.getByText('没有可用论文，请调整关键词后重新检索')).toBeTruthy())
    expect(screen.getByPlaceholderText('Europe PMC 检索式（可编辑）')).toBeTruthy()
  })

  it('OA Only 筛选与排除候选生效', async () => {
    renderWorkbench([ITEM_A])
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    fireEvent.click(screen.getByText('排除候选'))
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
    await waitFor(() => expect(screen.getByText('确认')).toBeTruthy())
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
      passages_json: {
        papers: [PAPER],
        passages: [
          {
            source_scope: 'abstract',
            section_title: null,
            paragraph_index: 0,
            passage: 'A real abstract sentence about connectivity and function.',
            direction: 'supports',
            reason: 'explicit',
            confidence: 0.82,
            source_locator: 'abstract:0',
            source_verified: true,
          },
        ],
      },
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
    await waitFor(() => expect(screen.getByText(/入库成功/)).toBeTruthy())
    expect(vi.mocked(endpoints.completePaperEvidenceTaskItem)).toHaveBeenCalledWith('task-1', 'item-1')
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
})
