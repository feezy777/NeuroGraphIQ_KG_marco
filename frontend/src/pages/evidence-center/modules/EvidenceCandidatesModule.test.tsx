import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import type { PaperEvidenceTaskItem } from '../../../api/endpoints'
import { EvidenceCenterProvider, useEvidenceCenter } from '../EvidenceCenterContext'
import { StepPills } from '../components/StepPills'
import { EvidenceCandidatesModule } from './EvidenceCandidatesModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTaskItems: vi.fn(),
  getEvidenceTarget: vi.fn(),
  searchPaperEvidence: vi.fn(),
  extractSelectedPaperEvidence: vi.fn(),
  createPaperEvidenceExtractionRun: vi.fn(),
  getPaperEvidenceExtractionRun: vi.fn(),
  cancelPaperEvidenceExtractionRun: vi.fn(),
  retryFailedPaperEvidenceExtractionRun: vi.fn(),
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

/** 第二篇论文:用于「多论文多片段混合审核」草稿累计测试 */
const PAPER_B = {
  paper_id: 'paper-2',
  pmid: '87654321',
  doi: null,
  pmcid: null,
  title: 'Another Study on R1 to R2',
  journal: 'Neuro Letters',
  year: '2023',
  is_oa: false,
  model_direction: 'supports',
  model_assessment: 'B 支持连接存在',
  coverage_summary: null,
  passages: [
    {
      passage: 'R1 also projects to R2 according to this study.',
      source_scope: 'abstract',
      section_title: null,
      direction: 'supports',
      evidence_level: 'direct',
      source_verified: true,
      supported_components: ['relation'],
    },
  ],
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

/** StepPills 进度探针:页面级 StepPills 由 module + progress 推导,这里直接渲染以断言当前高亮步骤 */
function StepPillsProbe() {
  const { state, progress } = useEvidenceCenter()
  return <StepPills module={state.module} progress={progress} />
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
    vi.mocked(endpoints.createPaperEvidenceExtractionRun).mockResolvedValue({
      run_id: 'run-1',
      status: 'queued',
      total_items: 1,
      requested_concurrency: 4,
      created_at: '2026-08-12T00:00:00Z',
    })
    vi.mocked(endpoints.getPaperEvidenceExtractionRun).mockResolvedValue({
      id: 'run-1',
      target_type: 'connection',
      target_id: 'r1-r2',
      mode: 'function',
      status: 'completed',
      total_items: 1,
      completed_items: 1,
      evidence_hit_items: 1,
      no_evidence_items: 0,
      failed_items: 0,
      requested_concurrency: 4,
      active_concurrency: 0,
      cancel_requested: false,
      created_at: '2026-08-12T00:00:00Z',
      updated_at: '2026-08-12T00:00:00Z',
      progress_percent: 100,
      items: [],
    })
  })

  it('不再自渲染左队列(队列由页面级 ObjectQueue 渲染)', async () => {
    renderModule()
    await waitFor(() => expect(endpoints.listPaperEvidenceTaskItems).toHaveBeenCalledWith('t1', { limit: 100 }))
    expect(screen.queryByTestId('candidates-queue')).toBeNull()
    expect(screen.queryByTestId('candidates-queue-item')).toBeNull()
  })

  it('不再自渲染 ClaimView(已移至页面左栏;模块中栏仅保留检索/统计条/候选列表)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    expect(screen.queryByTestId('evidence-claim')).toBeNull()
    expect(screen.queryByText('当前需要验证的事实')).toBeNull()
  })

  it('中栏统计条:找到论文 / AI 提取论文 / 已核验片段 / Coverage(N/M) / 模型判断', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByTestId('evidence-stats-bar')).toBeTruthy())
    const bar = screen.getByTestId('evidence-stats-bar')
    // ITEM 固定装置:1 篇已提取论文(2 片段,1 已核验);DTO 必需组件 2(源脑区/连接关系),已覆盖 1(连接关系)
    expect(within(bar).getByTestId('evidence-stats-found').textContent).toBe('1')
    expect(within(bar).getByTestId('evidence-stats-extracted').textContent).toBe('1')
    expect(within(bar).getByTestId('evidence-stats-verified').textContent).toBe('1')
    expect(within(bar).getByTestId('evidence-stats-coverage').textContent).toBe('1/2')
    expect(within(bar).getByTestId('evidence-stats-direction').textContent).toBe('部分支持')
    expect(within(bar).getByText('支持连接存在')).toBeTruthy()
  })

  it('PaperCard 分层:标题粗体 / 作者·期刊·年份 / 标签(PMID/DOI/摘要/OA 全文) / 提取结果行', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    // 引用行
    expect(screen.getByText(/Brain Journal · 2024/)).toBeTruthy()
    // 标签行
    expect(screen.getByText('PMID 12345678')).toBeTruthy()
    expect(screen.getByText('DOI')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'DOI' }).getAttribute('href')).toContain('10.1234/test')
    expect(screen.getByText('摘要')).toBeTruthy()
    expect(screen.getByText('OA 全文')).toBeTruthy()
    // 提取结果:AI判断 + Coverage(N/M) + 已核验片段数 + [查看证据候选]
    expect(screen.getByText(/AI判断：支持/)).toBeTruthy()
    expect(screen.getByText('AI 初始覆盖 1/3')).toBeTruthy()
    expect(screen.getByText('已核验片段 1')).toBeTruthy()
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

  it('进入人工审核只携带用户勾选的片段，不自动加入其他已核验片段', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [{ ...ITEM, candidate_papers: [CANDIDATE, PAPER_B] }],
    })
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    const cardA = screen.getAllByTestId('paper-card-candidate')
      .find(card => card.textContent?.includes('A Study of R1 to R2 Projection'))!
    fireEvent.click(within(cardA).getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    fireEvent.click(screen.getByRole('button', { name: /进入人工审核（1）/ }))

    const draft = JSON.parse(sessionStorage.getItem('evidence-center.review-draft.r1-r2')!) as {
      passages: Array<{ hash: string }>
    }
    expect(draft.passages).toHaveLength(1)
    expect(draft.passages[0].hash).toContain('paper-1')
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

  it('多论文混合审核:论文 A 与论文 B 勾选的片段累计写入同一份审核草稿(修复:不被后看论文覆盖)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [{ ...ITEM, candidate_papers: [CANDIDATE, PAPER_B] }],
    })
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())

    // 论文 A:查看证据候选 → 勾选已核验片段 → 草稿仅含 A
    const cardA = screen.getAllByTestId('paper-card-candidate')
      .find(c => c.textContent?.includes('A Study of R1 to R2 Projection'))!
    fireEvent.click(within(cardA).getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    await waitFor(() => {
      const draft = JSON.parse(sessionStorage.getItem('evidence-center.review-draft.r1-r2')!) as {
        passages: Array<{ hash: string }>
      }
      expect(draft.passages).toHaveLength(1)
      expect(draft.passages[0].hash).toBe('paper-1-0-We_observed_that_R1_projects_t')
    })

    // 返回列表 → 论文 B:查看证据候选 → 勾选 → 草稿累计两篇(A 不被 B 覆盖)
    fireEvent.click(screen.getByTestId('evidence-paper-back'))
    const cardB = screen.getAllByTestId('paper-card-candidate')
      .find(c => c.textContent?.includes('Another Study on R1 to R2'))!
    fireEvent.click(within(cardB).getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    await waitFor(() => {
      const draft = JSON.parse(sessionStorage.getItem('evidence-center.review-draft.r1-r2')!) as {
        passages: Array<{ hash: string }>
      }
      expect(draft.passages).toHaveLength(2)
      expect(new Set(draft.passages.map(p => p.hash))).toEqual(new Set([
        'paper-1-0-We_observed_that_R1_projects_t',
        'paper-2-0-R1_also_projects_to_R2_accordi',
      ]))
    })
  })

  it('多论文草稿:取消一篇勾选时保留另一篇;全部清空时删除草稿(删除保护不破坏)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [{ ...ITEM, candidate_papers: [CANDIDATE, PAPER_B] }],
    })
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())

    // 两篇论文各勾选一个片段
    const cardA = screen.getAllByTestId('paper-card-candidate')
      .find(c => c.textContent?.includes('A Study of R1 to R2 Projection'))!
    fireEvent.click(within(cardA).getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    fireEvent.click(screen.getByTestId('evidence-paper-back'))
    const cardB = screen.getAllByTestId('paper-card-candidate')
      .find(c => c.textContent?.includes('Another Study on R1 to R2'))!
    fireEvent.click(within(cardB).getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    await waitFor(() => {
      const draft = JSON.parse(sessionStorage.getItem('evidence-center.review-draft.r1-r2')!) as {
        passages: Array<{ hash: string }>
      }
      expect(draft.passages).toHaveLength(2)
    })

    // 论文 A 取消勾选 → 草稿保留论文 B 的片段(不被误删)
    fireEvent.click(screen.getByTestId('evidence-paper-back'))
    const cardA2 = screen.getAllByTestId('paper-card-candidate')
      .find(c => c.textContent?.includes('A Study of R1 to R2 Projection'))!
    fireEvent.click(within(cardA2).getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    await waitFor(() => {
      const draft = JSON.parse(sessionStorage.getItem('evidence-center.review-draft.r1-r2')!) as {
        passages: Array<{ hash: string }>
      }
      expect(draft.passages).toHaveLength(1)
      expect(draft.passages[0].hash).toBe('paper-2-0-R1_also_projects_to_R2_accordi')
    })

    // 论文 B 取消勾选 → 全部清空 → 草稿删除
    fireEvent.click(screen.getByTestId('evidence-paper-back'))
    const cardB2 = screen.getAllByTestId('paper-card-candidate')
      .find(c => c.textContent?.includes('Another Study on R1 to R2'))!
    fireEvent.click(within(cardB2).getByRole('button', { name: /查看证据候选/ }))
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    await waitFor(() => expect(sessionStorage.getItem('evidence-center.review-draft.r1-r2')).toBeNull())
  })

  it('排除此候选从列表移除论文卡;空态提示被排除论文已隐藏(列表头无恢复入口,恢复由检索过滤层提供)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /排除此候选/ }))
    expect(screen.queryByText('A Study of R1 to R2 Projection')).toBeNull()
    expect(screen.getByText(/当前对象暂无候选证据/)).toBeTruthy()
    // 空态提示不再提及「恢复排除」,改为「已隐藏」
    expect(screen.getByTestId('evidence-candidates-hint').textContent).toContain('已隐藏')
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
    await waitFor(() => expect(screen.getByText('已核验片段 2')).toBeTruthy())
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
    expect(terms.map(t => t.textContent)).toEqual(expect.arrayContaining(['R1×', 'R2×', 'projects_to×', '影响功能×']))
    // 过滤控件:☐仅OA / 证据模式 / 年份(下拉) / [恢复默认] + [恢复排除]
    expect(screen.getByLabelText('仅 OA')).toBeTruthy()
    expect(screen.getByLabelText('证据模式')).toBeTruthy()
    expect(screen.getByLabelText(/年份/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /恢复默认/ })).toBeTruthy()
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
        paper_match_score: 93,
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
    // 自动检索可能先折叠；改 query 前确保展开
    if (!screen.queryByTestId('evidence-search-query')) {
      fireEvent.click(screen.getByRole('button', { name: /展开检索/ }))
    }
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

  it('检索成功后检索区自动折叠为一条:折叠条可见、filters 不可见;展开可恢复;折叠条 [重新搜索] 直接执行', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: 'R1 AND R2', info: {} },
      papers: [{
        pmid: '99999999',
        doi: null,
        title: 'Found Paper',
        journal: 'Nature',
        year: '2025',
        authors: '',
        abstract: '',
        source: 'europepmc',
        is_open_access: true,
      }],
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /重新搜索/ }))
    // 检索成功 → 自动收起:折叠条可见,三层检索控件不可见
    await waitFor(() => expect(screen.getByTestId('evidence-search-collapsed')).toBeTruthy())
    expect(screen.queryByText('查找相关论文')).toBeNull()
    expect(screen.queryByText('检索过滤')).toBeNull()
    expect(screen.queryByText('批量操作')).toBeNull()
    expect(screen.queryByLabelText('仅 OA')).toBeNull()
    expect(screen.queryByTestId('evidence-search-query')).toBeNull()
    // 折叠条显示 Query 摘要(DTO 推荐词)
    expect(screen.getByTestId('evidence-search-collapsed-query').textContent).toContain('projects_to')
    // 展开可恢复:三层控件可见;展开态可 [收起检索] 回到折叠条
    fireEvent.click(screen.getByRole('button', { name: /展开检索/ }))
    expect(screen.getByText('查找相关论文')).toBeTruthy()
    expect(screen.getByText('检索过滤')).toBeTruthy()
    expect(screen.getByText('批量操作')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /收起检索/ }))
    expect(screen.getByTestId('evidence-search-collapsed')).toBeTruthy()
    // 折叠条 [重新搜索] 直接执行(无需展开)
    fireEvent.click(within(screen.getByTestId('evidence-search-collapsed')).getByRole('button', { name: /重新搜索/ }))
    await waitFor(() => expect(endpoints.searchPaperEvidence.mock.calls.length).toBeGreaterThanOrEqual(2))
    // 结果卡仍在候选列表区
    expect(screen.getByText('Found Paper')).toBeTruthy()
  })

  it('折叠条 [提取所选论文(N)]:检索折叠后从候选列表勾选论文可直接批量提取(零选中禁用)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: '', info: {} },
      papers: [{
        pmid: '99999999',
        doi: '10.9999/abc',
        title: 'Found Paper',
        journal: 'Nature',
        year: '2025',
        authors: '',
        abstract: '',
        source: 'europepmc',
        is_open_access: true,
      }],
    })
    vi.mocked(endpoints.createPaperEvidenceExtractionRun).mockResolvedValueOnce({
      run_id: 'run-collapsed',
      status: 'queued',
      total_items: 1,
      requested_concurrency: 4,
      created_at: '2026-08-12T00:00:00Z',
    })
    vi.mocked(endpoints.getPaperEvidenceExtractionRun).mockResolvedValue({
      id: 'run-collapsed',
      target_type: 'connection',
      target_id: 'r1-r2',
      mode: 'existence',
      status: 'completed',
      total_items: 1,
      completed_items: 1,
      evidence_hit_items: 1,
      no_evidence_items: 0,
      failed_items: 0,
      requested_concurrency: 4,
      active_concurrency: 0,
      cancel_requested: false,
      created_at: '2026-08-12T00:00:00Z',
      updated_at: '2026-08-12T00:00:00Z',
      progress_percent: 100,
      items: [{
        id: 'item-1',
        run_id: 'run-collapsed',
        item_index: 0,
        pmid: '99999999',
        title: 'Found Paper',
        paper_json: { pmid: '99999999' },
        status: 'completed',
        progress_percent: 100,
        attempt_count: 1,
        result_json: {
          paper_id: 'paper-2',
          pmid: '99999999',
          doi: '10.9999/abc',
          title: 'Found Paper',
          journal: 'Nature',
          year: '2025',
          is_oa: true,
          fulltext_fetched: true,
          model_direction: 'supports',
          model_assessment: '支持连接存在',
          coverage_summary: null,
          passages: [{
            passage: 'Evidence from the collapsed-bar extraction.',
            source_scope: 'abstract',
            section_title: null,
            direction: 'supports',
            evidence_level: 'direct',
            source_verified: true,
            supported_components: ['relation'],
          }],
        },
        stage_timings_json: {},
        updated_at: '2026-08-12T00:00:00Z',
      }],
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /重新搜索/ }))
    // 检索成功 → 折叠条出现;未勾选论文时 [提取所选论文] 禁用
    await waitFor(() => expect(screen.getByTestId('evidence-search-collapsed')).toBeTruthy())
    expect((screen.getByTestId('evidence-collapsed-extract') as HTMLButtonElement).disabled).toBe(true)
    // 从候选列表勾选检索结果卡(无需展开检索)→ 按钮可用且计数更新
    fireEvent.click(screen.getByTestId('paper-card-select'))
    await waitFor(() =>
      expect((screen.getByTestId('evidence-collapsed-extract') as HTMLButtonElement).disabled).toBe(false),
    )
    expect(screen.getByTestId('evidence-collapsed-extract').textContent).toContain('提取所选论文（1）')
    // 点击 → 批量提取
    fireEvent.click(screen.getByTestId('evidence-collapsed-extract'))
    await waitFor(() =>
      expect(endpoints.createPaperEvidenceExtractionRun).toHaveBeenCalledWith(expect.objectContaining({
        target_type: 'connection',
        target_id: 'r1-r2',
        papers: [expect.objectContaining({ pmid: '99999999' })],
      })),
    )
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
    // 检索成功 → 检索区自动折叠,批量操作需先展开
    fireEvent.click(screen.getByRole('button', { name: /展开检索/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /全选/ }))
    fireEvent.click(screen.getByRole('button', { name: /提取所选论文（2）/ }))
    await waitFor(() =>
      expect(endpoints.createPaperEvidenceExtractionRun).toHaveBeenCalledWith(expect.objectContaining({
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
    vi.mocked(endpoints.createPaperEvidenceExtractionRun).mockResolvedValueOnce({
      run_id: 'run-manual',
      status: 'queued',
      total_items: 1,
      requested_concurrency: 4,
      created_at: '2026-08-12T00:00:00Z',
    })
    vi.mocked(endpoints.getPaperEvidenceExtractionRun).mockResolvedValue({
      id: 'run-manual',
      target_type: 'connection',
      target_id: 'r1-r2',
      mode: 'existence',
      status: 'completed',
      total_items: 1,
      completed_items: 1,
      evidence_hit_items: 1,
      no_evidence_items: 0,
      failed_items: 0,
      requested_concurrency: 4,
      active_concurrency: 0,
      cancel_requested: false,
      created_at: '2026-08-12T00:00:00Z',
      updated_at: '2026-08-12T00:00:00Z',
      progress_percent: 100,
      items: [{
        id: 'item-manual',
        run_id: 'run-manual',
        item_index: 0,
        pmid: '99999999',
        title: 'A Newly Found Paper',
        paper_json: { pmid: '99999999' },
        status: 'completed',
        progress_percent: 100,
        attempt_count: 1,
        result_json: {
          paper_id: 'paper-2',
          pmid: '99999999',
          doi: '10.9999/abc',
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
        },
        stage_timings_json: {},
        updated_at: '2026-08-12T00:00:00Z',
      }],
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
    // 检索成功 → 检索区自动折叠,批量操作需先展开
    fireEvent.click(screen.getByRole('button', { name: /展开检索/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /全选/ }))
    fireEvent.click(screen.getByRole('button', { name: /提取所选论文（1）/ }))
    // 提取结果卡替换同一篇检索卡，避免候选数重复累计
    await waitFor(() => expect(screen.getByRole('button', { name: /查看证据候选/ })).toBeTruthy())
    expect(screen.getByText(/AI判断：支持/)).toBeTruthy()
    expect(screen.getByText('已核验片段 1')).toBeTruthy()
    expect(screen.getByText(/候选论文（1）/)).toBeTruthy()
    expect(screen.getByTestId('evidence-extraction-progress')).toBeTruthy()
    expect(screen.getAllByText('A Newly Found Paper').length).toBeGreaterThanOrEqual(1)
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
    // 检索成功 → 检索区自动折叠,过滤控件需先展开
    fireEvent.click(screen.getByRole('button', { name: /展开检索/ }))
    fireEvent.click(screen.getByLabelText('仅 OA'))
    expect(screen.queryByText('Closed Paper')).toBeNull()
    expect(screen.getByText('OA Paper')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('仅 OA'))
    fireEvent.change(screen.getByLabelText(/年份/), { target: { value: '2023' } })
    expect(screen.queryByText('Closed Paper')).toBeNull()
    expect(screen.getByText('OA Paper')).toBeTruthy()
  })

  it('筛选后仅按当前可见论文计数并提交，避免显示数量大于请求数量', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: '', info: {} },
      papers: [
        { pmid: '111', doi: '10.1/a', title: 'OA Paper', journal: 'J', year: '2024', authors: '', abstract: '', source: 'europepmc', is_open_access: true },
        { pmid: '222', doi: '10.2/b', title: 'Closed Paper', journal: 'J', year: '2023', authors: '', abstract: '', source: 'europepmc', is_open_access: false },
      ],
    })
    vi.mocked(endpoints.createPaperEvidenceExtractionRun).mockResolvedValue({
      run_id: 'run-filter',
      status: 'queued',
      total_items: 1,
      requested_concurrency: 4,
      created_at: '2026-08-12T00:00:00Z',
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )

    await waitFor(() => expect(screen.getByText('OA Paper')).toBeTruthy())
    for (const checkbox of screen.getAllByTestId('paper-card-select')) {
      fireEvent.click(checkbox)
    }
    expect(screen.getByTestId('evidence-collapsed-extract').textContent).toContain('提取所选论文（2）')

    fireEvent.click(screen.getByRole('button', { name: /展开检索/ }))
    fireEvent.click(screen.getByLabelText('仅 OA'))
    expect(screen.getByRole('button', { name: '提取所选论文（1）' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '提取所选论文（1）' }))

    await waitFor(() =>
      expect(endpoints.createPaperEvidenceExtractionRun).toHaveBeenCalledWith(expect.objectContaining({
        papers: [expect.objectContaining({ pmid: '111' })],
      })),
    )
  })

  it('DOI-only 论文使用 DOI 作为独立选择键，选中数与请求数一致', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: '', info: {} },
      papers: [
        { pmid: '', doi: '10.1/doi-a', title: 'DOI Paper A', journal: 'J', year: '2024', authors: '', abstract: '', source: 'openalex' },
        { pmid: '', doi: '10.1/doi-b', title: 'DOI Paper B', journal: 'J', year: '2023', authors: '', abstract: '', source: 'openalex' },
      ],
    })
    vi.mocked(endpoints.createPaperEvidenceExtractionRun).mockResolvedValue({
      run_id: 'run-doi',
      status: 'queued',
      total_items: 2,
      requested_concurrency: 4,
      created_at: '2026-08-12T00:00:00Z',
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )

    await waitFor(() => expect(screen.getByText('DOI Paper A')).toBeTruthy())
    const checkboxes = screen.getAllByTestId('paper-card-select')
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])
    expect(screen.getByTestId('evidence-collapsed-extract').textContent).toContain('提取所选论文（2）')
    fireEvent.click(screen.getByTestId('evidence-collapsed-extract'))

    await waitFor(() =>
      expect(endpoints.createPaperEvidenceExtractionRun).toHaveBeenCalledWith(expect.objectContaining({
        papers: [
          expect.objectContaining({ doi: '10.1/doi-a' }),
          expect.objectContaining({ doi: '10.1/doi-b' }),
        ],
      })),
    )
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

  it('直达 URL 进入(target 在 URL):items 异步加载后 derive effect 重跑,StepPills 高亮步骤 3「找到原文」', async () => {
    // 模拟刷新/深链:URL 直接带 target,items 延迟到达(加载期间 fallback current 的 candidate_papers 为空)
    let resolveItems!: (v: { items: PaperEvidenceTaskItem[] }) => void
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockReturnValueOnce(
      new Promise(res => { resolveItems = res }),
    )
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
        <StepPillsProbe />
      </EvidenceCenterProvider>,
    )
    // items 未到达:fallback current 无候选 → 进度停留在步骤 1「确认对象」
    const pills = screen.getByTestId('evidence-step-pills')
    expect(pills.querySelector('.evidence-step-pill.active')?.textContent).toContain('确认对象')
    // items 到达(候选含已提取片段)→ candidate_papers 变化触发 derive effect 重跑 → 步骤 3「找到原文」
    await act(async () => { resolveItems({ items: [ITEM] }) })
    await waitFor(() =>
      expect(screen.getByTestId('evidence-step-pills').querySelector('.evidence-step-pill.active')?.textContent)
        .toContain('找到原文'),
    )
  })

  it.skip('切换对象后手动检索状态清空:A 的检索结果 / query 摘要不泄漏到 B(折叠条消失、query 输入为空)', async () => {
    // Skipped: HashChangeEvent in jsdom does not reliably update EvidenceCenterContext target.
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: '', info: {} },
      papers: [{
        pmid: '99999999',
        doi: null,
        title: 'Found Paper',
        journal: 'Nature',
        year: '2025',
        authors: '',
        abstract: '',
        source: 'europepmc',
        is_open_access: true,
      }],
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    // 对象 A(r1-r2):带 query 检索成功 → 检索区折叠,折叠条显示 A 的 query 摘要
    if (!screen.queryByTestId('evidence-search-query')) {
      fireEvent.click(screen.getByRole('button', { name: /展开检索/ }))
    }
    fireEvent.change(screen.getByTestId('evidence-search-query'), { target: { value: 'A query' } })
    fireEvent.click(screen.getByRole('button', { name: /重新搜索/ }))
    await waitFor(() => expect(screen.getByTestId('evidence-search-collapsed')).toBeTruthy())
    expect(screen.getByTestId('evidence-search-collapsed-query').textContent).toContain('A query')
    expect(screen.getByText('Found Paper')).toBeTruthy()
    // 切换到对象 B:manualResult / manualQuery / manualResults / manualSelected 全部重置
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r3-r4'
    fireEvent(window, new HashChangeEvent('hashchange'))
    // A 的折叠条消失(不显示旧 query 摘要),检索区回到展开态且 query 输入为空,旧结果卡移除
    await waitFor(() => expect(screen.queryByTestId('evidence-search-collapsed')).toBeNull())
    await waitFor(() => {
      const expanded = screen.queryByText('查找相关论文')
      const query = screen.queryByTestId('evidence-search-query') as HTMLInputElement | null
      expect(expanded || query).toBeTruthy()
      if (query) expect(query.value).toBe('')
    })
    await waitFor(() => expect(screen.queryByText('Found Paper')).toBeNull())
  })

  it('Query Chip ×清空:移除该关键词;恢复系统推荐恢复全部推荐词', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    const terms = () => screen.getAllByTestId('evidence-query-term').map(t => t.textContent)
    expect(terms()).toEqual(expect.arrayContaining(['R1×', 'R2×', 'projects_to×', '影响功能×']))
    fireEvent.click(screen.getByRole('button', { name: '清空关键词 R1' }))
    expect(terms()).not.toContain('R1×')
    expect(terms()).toEqual(expect.arrayContaining(['R2×', 'projects_to×', '影响功能×']))
    // 恢复系统推荐:清空 Query + 恢复全部推荐词并重新检索
    fireEvent.click(screen.getByRole('button', { name: /恢复系统推荐/ }))
    await waitFor(() => expect(endpoints.searchPaperEvidence).toHaveBeenCalled())
    expect(terms()).toEqual(expect.arrayContaining(['R1×', 'R2×', 'projects_to×', '影响功能×']))
  })

  it('检索过滤 [恢复默认]:重置 仅OA / 年份 过滤条件', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: /展开检索/ }))
    // 仅OA + 年份 2024 → 只剩 OA Paper
    fireEvent.click(screen.getByLabelText('仅 OA'))
    fireEvent.change(screen.getByLabelText(/年份/), { target: { value: '2024' } })
    expect(screen.queryByText('Closed Paper')).toBeNull()
    // [恢复默认] → 全部过滤重置 → 两篇论文均恢复
    fireEvent.click(screen.getByRole('button', { name: /恢复默认/ }))
    expect((screen.getByLabelText('仅 OA') as HTMLInputElement).checked).toBe(false)
    expect((screen.getByLabelText(/年份/) as HTMLSelectElement).value).toBe('')
    expect(screen.getByText('Closed Paper')).toBeTruthy()
    expect(screen.getByText('OA Paper')).toBeTruthy()
  })

  it('空态(手动检索场景):暂无候选论文 + 调整检索条件 + 轻提示;排除后可恢复', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: '', info: {} },
      papers: [{
        pmid: '99999999',
        doi: '10.9999/abc',
        title: 'Only Paper',
        journal: 'Nature',
        year: '2025',
        authors: '',
        abstract: '',
        source: 'europepmc',
        is_open_access: true,
      }],
    })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText('查找相关论文')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /重新搜索/ }))
    await waitFor(() => expect(screen.getByText('Only Paper')).toBeTruthy())
    // 排除唯一论文 → 空态:标题/说明/调整检索条件/轻提示(已隐藏)
    fireEvent.click(screen.getByRole('button', { name: /排除此候选/ }))
    expect(screen.getByText('候选论文（0）')).toBeTruthy()
    expect(screen.getByText('暂无候选论文')).toBeTruthy()
    expect(screen.getByText('当前还没有找到相关论文，可尝试调整检索条件后重新搜索。')).toBeTruthy()
    expect(screen.getByTestId('evidence-candidates-hint').textContent).toContain('勾选论文后可批量操作')
    expect(screen.getByTestId('evidence-candidates-hint').textContent).toContain('已隐藏')
    // [调整检索条件] → 展开完整检索区,过滤行露出 [恢复排除]
    fireEvent.click(screen.getByRole('button', { name: /调整检索条件/ }))
    expect(screen.getByTestId('evidence-search-query')).toBeTruthy()
    expect(screen.getByText('检索过滤')).toBeTruthy()
  })

  it('任务模式:item 无候选论文时进入自动搜索(与数据中心入口一致,回退重评同路径)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [{ ...ITEM, candidate_papers: [] }],
    })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: { target_type: 'connection', target_id: 'r1-r2', function_term: '', mode: 'existence', query: 'R1 AND R2', info: {} },
      papers: [{
        pmid: '777', doi: '10.7/x', title: 'Auto Found Paper', journal: 'J', year: '2025',
        authors: '', abstract: '', source: 'europepmc', is_open_access: true,
      }],
    })
    renderModule()
    // 无候选论文 → 用系统推荐词自动触发一次搜索(非手动点击)
    await waitFor(() => expect(endpoints.searchPaperEvidence).toHaveBeenCalledWith(expect.objectContaining({ query_override: undefined })))
    await waitFor(() => expect(screen.getByText('Auto Found Paper')).toBeTruthy())
  })
})
