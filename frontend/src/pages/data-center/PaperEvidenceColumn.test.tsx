import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { PaperEvidenceColumn } from './PaperEvidenceColumn'
import * as endpoints from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  searchPaperEvidence: vi.fn(),
  extractPaperPassage: vi.fn(),
  attachPaperEvidence: vi.fn(),
  listPaperEvidence: vi.fn(),
  translateEvidenceText: vi.fn(),
  rollbackPaperEvidence: vi.fn(),
}))

const TARGET = {
  target_type: 'connection',
  target_id: '11111111-1111-1111-1111-111111111111',
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

const EXISTING = {
  evidence_id: 'e1',
  evidence_text: '[论文证据:e1] Paper A | 12345 | 10.1000/xyz | supports | A real abstract sentence…',
  direction: 'supports',
  verification_status: 'human_verified',
  pmid: '12345',
  doi: '10.1000/xyz',
  title: 'Paper A',
  journal: 'J Neuro',
  year: 2024,
  created_at: '2026-08-07T00:00:00Z',
  verification_by: 'reviewer-1',
  suggested_confidence: 0.8,
  confidence_adjustment_status: 'applied',
  passage_count: 1,
  links: { pubmed: 'https://pubmed.ncbi.nlm.nih.gov/12345/', doi: 'https://doi.org/10.1000/xyz' },
  passages: [
    {
      id: 'p1',
      source_scope: 'abstract' as const,
      section_title: null,
      paragraph_index: 0,
      passage: 'A real abstract sentence about connectivity and function.',
      translation_zh: '关于连接和功能的真实摘要句。',
      direction: 'supports',
      reason: 'explicitly mentions the function',
      confidence: 0.8,
      source_locator: 'abstract:0',
      source_verified: true,
      is_selected: true,
    },
  ],
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

describe('PaperEvidenceColumn 对象抽屉证据列', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidence).mockResolvedValue({ items: [EXISTING] })
    vi.mocked(endpoints.searchPaperEvidence).mockResolvedValue({
      target_info: {
        target_type: TARGET.target_type,
        target_id: TARGET.target_id,
        function_term: 'connectivity',
        mode: 'function',
        query: 'connectivity',
        info: {},
      },
      papers: [PAPER],
    })
    vi.mocked(endpoints.extractPaperPassage).mockResolvedValue(EXTRACT_OK)
    vi.mocked(endpoints.attachPaperEvidence).mockResolvedValue({
      evidence_id: 'e2',
      target_type: TARGET.target_type,
      target_id: TARGET.target_id,
      confidence: 0.8,
      final_confidence: 0.8,
      verification_status: 'human_verified',
      confidence_adjustment_status: 'applied',
      passage_count: 1,
      paper: { links: { pubmed: 'https://pubmed.ncbi.nlm.nih.gov/12345/', doi: null } },
    })
    vi.mocked(endpoints.rollbackPaperEvidence).mockResolvedValue({
      evidence_id: 'e1',
      status: 'invalidated',
      changed: true,
      confidence: 0.42,
    })
    vi.mocked(endpoints.translateEvidenceText).mockResolvedValue({ translated: '中文翻译' })
  })

  it('展示已有证据、段落数，并可在详情抽屉查看中英文对照', async () => {
    render(<PaperEvidenceColumn targetType={TARGET.target_type} targetId={TARGET.target_id} />)
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    expect(screen.getByText(/段落 1/)).toBeTruthy()
    fireEvent.click(screen.getByText('Paper A'))
    await waitFor(() => expect(screen.getByText('证据详情')).toBeTruthy())
    expect(screen.getByText('关于连接和功能的真实摘要句。')).toBeTruthy()
    expect(screen.getByText('A real abstract sentence about connectivity and function.')).toBeTruthy()
    expect(screen.getByText('reviewer-1')).toBeTruthy()
  })

  it('撤销证据使用确认对话框并调用回滚接口，随后刷新列表', async () => {
    render(<PaperEvidenceColumn targetType={TARGET.target_type} targetId={TARGET.target_id} />)
    await waitFor(() => expect(screen.getByText('Paper A')).toBeTruthy())
    fireEvent.click(screen.getByText('Paper A'))
    await waitFor(() => expect(screen.getByText('撤销证据')).toBeTruthy())
    fireEvent.click(screen.getByText('撤销证据'))
    expect(screen.getByText('确认撤销')).toBeTruthy()
    fireEvent.change(screen.getByPlaceholderText('撤销原因（必填）'), {
      target: { value: '文献与方法不匹配' },
    })
    fireEvent.click(screen.getByText('确认撤销'))
    await waitFor(() => expect(vi.mocked(endpoints.rollbackPaperEvidence)).toHaveBeenCalledWith('e1', '文献与方法不匹配'))
    await waitFor(() => expect(vi.mocked(endpoints.listPaperEvidence).mock.calls.length).toBeGreaterThanOrEqual(2))
  })

  it('多 passage 提取与挂接：未校验片段禁选，仅传已选片段', async () => {
    render(<PaperEvidenceColumn targetType={TARGET.target_type} targetId={TARGET.target_id} />)
    fireEvent.click(screen.getByText('检索论文'))
    await waitFor(() => expect(screen.getAllByTestId('pe-paper').length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByTestId('pe-paper')[0])
    fireEvent.click(screen.getByText('AI 提取原文片段'))
    await waitFor(() => expect(screen.getAllByTestId('ew-passage')).toHaveLength(2))
    const boxes = screen.getAllByTestId('ew-passage')
      .map(el => el.querySelector('input[type="checkbox"]') as HTMLInputElement)
    expect(boxes[0].checked).toBe(true)
    expect(boxes[1].disabled).toBe(true)
    fireEvent.click(screen.getByText('挂接并更新置信度'))
    await waitFor(() =>
      expect(vi.mocked(endpoints.attachPaperEvidence)).toHaveBeenCalledWith(
        expect.objectContaining({
          target_id: TARGET.target_id,
          pmid: '12345',
          direction: 'supports',
          reviewer_confidence: 0.8,
        }),
      ),
    )
    const body = vi.mocked(endpoints.attachPaperEvidence).mock.calls[0][0]
    expect(body.passages).toHaveLength(1)
    expect(body.passages[0].source_verified).toBe(true)
  })
})
