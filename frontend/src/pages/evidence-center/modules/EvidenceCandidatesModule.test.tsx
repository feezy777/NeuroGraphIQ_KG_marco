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
  function_context: '',
  current_confidence: 0.7,
  existing_evidence: 0,
  structured_claim: {},
  claim_text: 'R1 投射到 R2 且影响功能',
  claim_components: [
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

  it('渲染左侧候选队列(label + 状态)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('R1 → R2 连接')).toBeTruthy())
    expect(screen.getByText('待人工审核')).toBeTruthy()
    expect(screen.getByText('connection')).toBeTruthy()
    expect(endpoints.listPaperEvidenceTaskItems).toHaveBeenCalledWith('t1', { limit: 100 })
  })

  it('主区渲染 ClaimPanel(claim_text + components)', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('R1 投射到 R2 且影响功能')).toBeTruthy())
    expect(screen.getByTestId('ew-claim-panel')).toBeTruthy()
    expect(screen.getByText('connection · macro_clinical')).toBeTruthy()
    expect(screen.getByText('存在投射关系')).toBeTruthy()
  })

  it('Candidate Paper 卡渲染 title/model_direction/覆盖度/片段数与已核验数', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    expect(screen.getByText('Brain Journal · 2024 · PMID 12345678')).toBeTruthy()
    expect(screen.getByText('模型判断 支持')).toBeTruthy()
    expect(screen.getByText('覆盖度 50%')).toBeTruthy()
    expect(screen.getByText('片段 2')).toBeTruthy()
    expect(screen.getByText('已核验 1')).toBeTruthy()
  })

  it('查看候选证据展开片段列表,展示已核验标记', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    expect(screen.queryByTestId('cand-passages')).toBeNull()
    fireEvent.click(screen.getByText('查看候选证据'))
    expect(screen.getByTestId('cand-passages')).toBeTruthy()
    expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy()
    expect(screen.getByText('已核验')).toBeTruthy()
  })

  it('加入人工审核:勾选片段后写入 sessionStorage draft 并跳转 module=review', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    fireEvent.click(screen.getByText('查看候选证据'))
    const boxes = screen.getAllByTestId('cand-passage-checkbox')
    expect(boxes.length).toBe(2)
    fireEvent.click(boxes[0])
    fireEvent.click(screen.getByRole('button', { name: /加入人工审核/ }))
    await waitFor(() => expect(window.location.hash).toContain('module=review'))
    expect(window.location.hash).toContain('target_id=r1-r2')
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

  it('排除从列表移除候选论文卡', async () => {
    renderModule()
    await waitFor(() => expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy())
    fireEvent.click(screen.getByText('排除'))
    expect(screen.queryByText('A Study of R1 to R2 Projection')).toBeNull()
    expect(screen.getByText(/当前对象没有候选论文/)).toBeTruthy()
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
    fireEvent.click(screen.getByText('重新提取'))
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

  it('队列为空时显示手动检索/提取入口(不渲染候选卡)', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=candidates&task_id=t1&target_type=connection&target_id=r1-r2'
    render(
      <EvidenceCenterProvider>
        <EvidenceCandidatesModule />
      </EvidenceCenterProvider>,
    )
    await waitFor(() => expect(screen.getByText(/手动检索与提取/)).toBeTruthy())
    fireEvent.click(screen.getByText('检索'))
    await waitFor(() => expect(endpoints.searchPaperEvidence).toHaveBeenCalled())
    expect(screen.queryByText('A Study of R1 to R2 Projection')).toBeNull()
  })
})
