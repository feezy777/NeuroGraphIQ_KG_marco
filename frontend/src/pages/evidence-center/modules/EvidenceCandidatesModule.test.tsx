import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { EvidenceCandidatesModule } from './EvidenceCandidatesModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTaskItems: vi.fn(),
  getEvidenceTarget: vi.fn(),
  searchPaperEvidence: vi.fn(),
  extractSelectedPaperEvidence: vi.fn(),
}))

const CANDIDATE = {
  paper_id: 'paper-1',
  pmid: '12345678',
  doi: '10.1234/test',
  pmcid: 'PMC123',
  title: 'A Study of R1 to R2 Projection',
  journal: 'Brain Journal',
  year: '2024',
  is_oa: true,
  fulltext_fetched: true,
  model_direction: 'supports',
  model_assessment: '支持连接存在',
  coverage_summary: {
    coverage_ratio: 0.5,
    required_components: ['source_region', 'target_region', 'relation'],
    supported_components: ['relation'],
    contradicted_components: [],
    uncovered_components: ['source_region', 'target_region'],
  },
  passages: [
    {
      passage: 'We observed that R1 projects to R2 in the macaque.',
      source_scope: 'abstract',
      section_title: null,
      direction: 'supports',
      evidence_level: 'direct',
      source_verified: true,
      supported_components: ['relation'],
    },
    {
      passage: 'A secondary passage without verification.',
      source_scope: 'fulltext',
      section_title: 'Results',
      direction: 'supports',
      evidence_level: 'indirect',
      source_verified: false,
      supported_components: [],
    },
  ],
}

const ITEM = {
  id: 'item-1',
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
  label: 'R1 → R2 连接',
  current_confidence: 0.7,
  attempt_count: 0,
  last_error_code: null,
  last_error_message: null,
  preprocess_outcome: null,
  paper_id: null,
  model_direction: 'supports',
  candidate_papers: [CANDIDATE],
  review_draft: null,
  claim_text_snapshot: null,
  claim_components_snapshot: null,
  passages_json: null,
  last_error: null,
  retry_count: 0,
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
  function_context: '影响功能',
  current_confidence: 0.7,
  existing_evidence: 0,
  structured_claim: {},
  claim_text: 'R1 投射到 R2 且影响功能',
  claim_components: [
    { component_type: 'source_region', statement: 'R1', required: true, metadata: {} },
    { component_type: 'relation', statement: '存在投射关系', required: true, metadata: {} },
  ],
  claim_version: 'v1',
}

function renderModule() {
  window.location.hash = '#/evidence-center?module=candidates&task_id=t1'
  return render(
    <EvidenceCenterProvider>
      <EvidenceCandidatesModule />
    </EvidenceCenterProvider>,
  )
}

describe('EvidenceCandidatesModule', () => {
  afterEach(() => {
    cleanup()
    window.location.hash = ''
    sessionStorage.clear()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [ITEM] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(DTO)
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: 'R1 AND R2', info: {} },
      papers: [],
    })
    vi.mocked(endpoints.extractSelectedPaperEvidence).mockResolvedValue({
      claim: '',
      claim_components: [],
      results: [],
      llm_model: null,
    })
  })

  it('不再自渲染左队列(队列由页面级 ObjectQueue 渲染)', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.listPaperEvidenceTaskItems).toHaveBeenCalledWith('t1', { limit: 100 }))
    expect(screen.queryByTestId('candidates-queue')).toBeNull()
    expect(screen.queryByTestId('candidates-queue-item')).toBeNull()
  })

  it('Claim 区重排:当前需要验证的事实 + Claim 单行 + Component Chips(标签 + 值)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('R1 投射到 R2 且影响功能')).toBeTruthy())
    expect(screen.getByText('当前需要验证的事实')).toBeTruthy()
    const chips = screen.getAllByTestId('evidence-claim-chip')
    expect(chips).toHaveLength(2)
    expect(chips[0].textContent).toContain('源脑区')
    expect(chips[0].textContent).toContain('R1')
    expect(chips[1].textContent).toContain('连接关系')
    expect(chips[1].textContent).toContain('存在投射关系')
  })

  it('PaperCard 分层:标题粗体 / 作者·期刊·年份 / 标签(PMID/DOI/摘要/OA 全文) / 提取结果行', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    // 引用行
    expect(screen.getByText(/Brain Journal · 2024/)).toBeTruthy()
    // 标签行
    expect(screen.getByText('PMID 12345678')).toBeTruthy()
    expect(screen.getByText('DOI 10.1234/test')).toBeTruthy()
    expect(screen.getByText('摘要')).toBeTruthy()
    expect(screen.getByText('OA 全文')).toBeTruthy()
    // 提取结果:AI 判断 + 覆盖度 + 片段数 + 已核验数 + [查看证据候选]
    expect(screen.getByText(/AI 判断 支持/)).toBeTruthy()
    expect(screen.getByText('覆盖度 50%')).toBeTruthy()
    expect(screen.getByText('片段 2')).toBeTruthy()
    expect(screen.getByText('已核验 1')).toBeTruthy()
    expect(screen.getByRole('button', { name: /查看证据候选/ })).toBeTruthy()
  })

  it('查看证据候选 → 中栏切换 PaperEvidenceView,← 返回论文列表恢复列表', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /查看证据候选/ }))
    // 论文列表隐藏,证据视图出现
    expect(screen.queryByRole('button', { name: /查看证据候选/ })).toBeNull()
    expect(screen.getByTestId('evidence-paper-view')).toBeTruthy()
    expect(screen.getByText('Claim Coverage')).toBeTruthy()
    expect(screen.getByText('候选佐证原文')).toBeTruthy()
    expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy()
    // 返回
    fireEvent.click(screen.getByTestId('evidence-paper-back'))
    expect(screen.queryByTestId('evidence-paper-view')).toBeNull()
    expect(screen.getByRole('button', { name: /查看证据候选/ })).toBeTruthy()
  })

  it('勾选已核验片段 → 自动写入 sessionStorage 审核草稿', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /查看证据候选/ }))
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes).toHaveLength(2)
    fireEvent.click(boxes[0])
    await waitFor(() => {
      const raw = sessionStorage.getItem('evidence-center.review-draft.r1-r2')
      expect(raw).toBeTruthy()
      const draft = JSON.parse(raw!) as {
        passages: Array<{ hash: string; source_verified: boolean }>
        modelDirection: string | null
        modelAssessment: string | null
        paperTitle: string
        pmid: string
      }
      expect(draft.passages.length).toBe(1)
      expect(draft.passages[0].source_verified).toBe(true)
      expect(draft.modelDirection).toBe('supports')
      expect(draft.modelAssessment).toBe('支持连接存在')
      expect(draft.paperTitle).toBe('A Study of R1 to R2 Projection')
      expect(draft.pmid).toBe('12345678')
    })
  })

  it('往返:建立审核草稿后模块重挂载,重新打开证据视图不误删草稿', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    // 勾选片段 → 写入审核草稿
    fireEvent.click(screen.getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    await waitFor(() => expect(sessionStorage.getItem('evidence-center.review-draft.r1-r2')).toBeTruthy())
    // 模拟「进入审核 → 返回候选」:模块重挂载,选中状态清空
    cleanup()
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    // 打开任意论文证据视图(零选中)→ 已存草稿必须保留
    fireEvent.click(screen.getByRole('button', { name: /查看证据候选/ }))
    expect(sessionStorage.getItem('evidence-center.review-draft.r1-r2')).toBeTruthy()
  })

  it('排除此候选从列表移除论文卡', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /排除此候选/ }))
    expect(screen.queryByText('A Study of R1 to R2 Projection')).toBeNull()
    expect(screen.getByText(/当前对象暂无候选证据/)).toBeTruthy()
  })

  it('重新提取触发 extractSelectedPaperEvidence 并更新片段数', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    const fresh = {
      ...CANDIDATE,
      passages: [
        ...CANDIDATE.passages,
        { passage: 'A newly extracted passage.', source_scope: 'fulltext', direction: 'supports', source_verified: true, supported_components: ['relation'] },
      ],
    }
    vi.mocked(endpoints.extractSelectedPaperEvidence).mockResolvedValueOnce({
      claim: '',
      claim_components: [],
      results: [fresh],
      llm_model: null,
    })
    fireEvent.click(screen.getByRole('button', { name: /重新提取/ }))
    await waitFor(() =>
      expect(endpoints.extractSelectedPaperEvidence).toHaveBeenCalledWith(expect.objectContaining({
        target_type: 'connection',
        target_id: 'r1-r2',
        papers: [expect.objectContaining({ pmid: '12345678' })],
      })),
    )
    await waitFor(() => expect(screen.getByText('片段 3')).toBeTruthy())
    expect(screen.getByText('已核验 2')).toBeTruthy()
  })

  it('禁止项:无正式 attach / confirm 文案与控件', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    expect(screen.queryByText('确认论文证据')).toBeNull()
    expect(screen.queryByText('确认入库')).toBeNull()
    expect(screen.queryByText('保存草稿')).toBeNull()
    expect(screen.queryByTestId('ew-attach')).toBeNull()
  })

  it('队列为空时显示搜索区三层(查找相关论文/检索过滤/批量操作)与 Query Terms Chips', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    // 三层标题
    expect(screen.getByText('查找相关论文')).toBeTruthy()
    expect(screen.getByText('检索过滤')).toBeTruthy()
    expect(screen.getByText('批量操作')).toBeTruthy()
    // Query Terms Chips 来自 DTO(源脑区/目标脑区/连接关系/功能)
    const terms = screen.getAllByTestId('evidence-query-term')
    expect(terms.map(t => t.textContent)).toEqual(expect.arrayContaining(['R1', 'R2', 'projects_to', '影响功能']))
    // 过滤控件
    expect(screen.getByLabelText('仅 OA')).toBeTruthy()
    expect(screen.getByLabelText('佐证模式')).toBeTruthy()
    expect(screen.getByPlaceholderText(/年份/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /恢复排除/ })).toBeTruthy()
  })

  it('手动检索:重新搜索携带 query_override;搜索结果显示为候选卡可勾选「加入提取」', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: 'R1 AND R2', info: {} },
      papers: [{
        pmid: '99999999',
        doi: '10.9999/abc',
        title: 'A Newly Found Paper',
        journal: 'Nature',
        year: '2025',
        authors: 'Doe J',
        abstract: 'Abstract text.',
        source: 'europepmc',
        is_open_access: true,
        fulltext_available: true,
        paper_match_score: 0.93,
        match_reason: '标题与 R1/R2 高度匹配',
      }],
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    fireEvent.change(screen.getByTestId('evidence-search-query'), { target: { value: 'R1 projection' } })
    fireEvent.click(screen.getByRole('button', { name: /重新搜索/ }))
    await waitFor(() =>
      expect(endpoints.searchPaperEvidence).toHaveBeenCalledWith(expect.objectContaining({
        target_type: 'connection',
        target_id: 'r1-r2',
        query_override: 'R1 projection',
      })),
    )
    // 搜索结果卡:标题 + 匹配信息 + 加入提取 checkbox
    expect(screen.getByText('A Newly Found Paper')).toBeTruthy()
    expect(screen.getByText(/Doe J · Nature · 2025/)).toBeTruthy()
    expect(screen.getByTestId('paper-card-match').textContent).toContain('匹配 93%')
    expect(screen.getByTestId('paper-card-match').textContent).toContain('标题与 R1/R2 高度匹配')
    expect(screen.getAllByTestId('paper-card-select')).toHaveLength(1)
  })

  it('恢复系统推荐:清空 Query 并以无 query_override 重新检索', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    fireEvent.change(screen.getByTestId('evidence-search-query'), { target: { value: 'my query' } })
    fireEvent.click(screen.getByRole('button', { name: /恢复系统推荐/ }))
    await waitFor(() =>
      expect(endpoints.searchPaperEvidence).toHaveBeenCalledWith(expect.objectContaining({ query_override: undefined })),
    )
    expect((screen.getByTestId('evidence-search-query') as HTMLInputElement).value).toBe('')
  })

  it('批量操作:全选 + 提取所选论文(N)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: '', info: {} },
      papers: [
        { pmid: '111', doi: '10.1/a', title: 'Paper A', journal: 'J', year: '2024', authors: '', abstract: '', source: 'europepmc' },
        { pmid: '222', doi: '10.2/b', title: 'Paper B', journal: 'J', year: '2023', authors: '', abstract: '', source: 'europepmc' },
      ],
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /重新搜索/ }))
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /全选/ }))
    fireEvent.click(screen.getByRole('button', { name: /提取所选论文（2）/ }))
    await waitFor(() =>
      expect(endpoints.extractSelectedPaperEvidence).toHaveBeenCalledWith(expect.objectContaining({
        papers: expect.arrayContaining([
          expect.objectContaining({ pmid: '111' }),
          expect.objectContaining({ pmid: '222' }),
        ]),
      })),
    )
  })

  it('手动批量提取后:提取结果卡片渲染且出现「查看证据候选」', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: '', info: {} },
      papers: [{
        pmid: '99999999',
        doi: '10.9999/abc',
        title: 'A Newly Found Paper',
        journal: 'Nature',
        year: '2025',
        authors: '',
        abstract: '',
        source: 'europepmc',
        is_open_access: true,
      }],
    })
    vi.mocked(endpoints.extractSelectedPaperEvidence).mockResolvedValueOnce({
      claim: '',
      claim_components: [],
      results: [{
        paper_id: 'paper-2',
        pmid: '99999999',
        doi: '10.9999/abc',
        pmcid: null,
        title: 'A Newly Found Paper',
        journal: 'Nature',
        year: '2025',
        is_oa: true,
        fulltext_fetched: true,
        model_direction: 'supports',
        model_assessment: '支持连接存在',
        coverage_summary: null,
        passages: [{
          passage: 'Evidence from the newly extracted paper.',
          source_scope: 'abstract',
          section_title: null,
          direction: 'supports',
          evidence_level: 'direct',
          source_verified: true,
          supported_components: ['relation'],
        }],
      }],
      llm_model: null,
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /重新搜索/ }))
    await waitFor(() => expect(screen.getByText('A Newly Found Paper')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /全选/ }))
    fireEvent.click(screen.getByRole('button', { name: /提取所选论文（1）/ }))
    // 提取结果卡:AI 判断 / 片段 / 已核验 + [查看证据候选];检索卡保留(标题出现两处)
    await waitFor(() => expect(screen.getByRole('button', { name: /查看证据候选/ })).toBeTruthy())
    expect(screen.getByText(/AI 判断 支持/)).toBeTruthy()
    expect(screen.getByText('片段 1')).toBeTruthy()
    expect(screen.getByText('已核验 1')).toBeTruthy()
    expect(screen.getByText(/候选论文（2）/)).toBeTruthy()
    expect(screen.getAllByText('A Newly Found Paper')).toHaveLength(2)
  })

  it('OA Only / 年份过滤在客户端过滤搜索结果', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: '', info: {} },
      papers: [
        { pmid: '111', doi: '10.1/a', title: 'OA Paper', journal: 'J', year: '2024', authors: '', abstract: '', source: 'europepmc', is_open_access: true },
        { pmid: '222', doi: '10.2/b', title: 'Closed Paper', journal: 'J', year: '2020', authors: '', abstract: '', source: 'europepmc', is_open_access: false },
      ],
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /重新搜索/ }))
    await waitFor(() => expect(screen.getByText('OA Paper')).toBeTruthy())
    expect(screen.getByText('Closed Paper')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('仅 OA'))
    expect(screen.queryByText('Closed Paper')).toBeNull()
    expect(screen.getByText('OA Paper')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('仅 OA'))
    fireEvent.change(screen.getByPlaceholderText(/年份/), { target: { value: '2023' } })
    expect(screen.queryByText('Closed Paper')).toBeNull()
    expect(screen.getByText('OA Paper')).toBeTruthy()
  })

  it('无任务时从 sessionStorage initial-queue 一次性恢复队列(数据中心入口交接)', async () => {
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
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText(/已从数据中心恢复 2 个待处理对象/)).toBeTruthy())
    expect(sessionStorage.getItem('evidence-center.initial-queue')).toBeNull()
  })
})
