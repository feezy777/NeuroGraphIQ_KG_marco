import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PaperCandidateCard, type CandidatePaperData } from './PaperCandidateCard'

const SEARCH_PAPER: CandidatePaperData = {
  paperId: null,
  pmid: '99999999',
  doi: '10.9999/abc',
  pmcid: null,
  title: 'A Newly Found Paper',
  journal: 'Nature',
  year: '2025',
  authors: 'Doe J',
  isOa: true,
  abstractAvailable: true,
  fulltextAvailable: true,
  matchReason: '标题与 R1/R2 高度匹配',
  matchScore: 93,
  extracted: false,
  modelDirection: null,
  modelAssessment: null,
  coverageSummary: null,
  passageCount: 0,
  verifiedCount: 0,
}

const EXTRACTED_PAPER: CandidatePaperData = {
  ...SEARCH_PAPER,
  paperId: 'paper-1',
  authors: null,
  extracted: true,
  modelDirection: 'supports',
  modelAssessment: '支持连接存在',
  coverageSummary: {
    coverage_ratio: 0.5,
    required_components: ['source_region', 'target_region', 'relation'],
    supported_components: ['relation'],
    contradicted_components: [],
    uncovered_components: ['source_region', 'target_region'],
  },
  passageCount: 2,
  verifiedCount: 1,
}

function renderCard(paper: CandidatePaperData, overrides: Record<string, unknown> = {}) {
  const props = {
    paper,
    selected: false,
    onToggleSelected: vi.fn(),
    onOpenDetail: vi.fn(),
    onExclude: vi.fn(),
    onReExtract: vi.fn(),
    onViewEvidence: vi.fn(),
    reExtracting: false,
    ...overrides,
  }
  return render(<PaperCandidateCard {...props} />)
}

describe('PaperCandidateCard(未提取搜索卡)', () => {
  it('四行层级:标题 / 作者·期刊·年份 / 匹配度·理由 / PMID·DOI·摘要·OA 徽章', () => {
    renderCard(SEARCH_PAPER)
    expect(screen.getByText('A Newly Found Paper')).toBeTruthy()
    expect(screen.getByText('Doe J · Nature · 2025')).toBeTruthy()
    const match = screen.getByTestId('paper-card-match')
    expect(match.textContent).toContain('匹配 93%')
    expect(match.textContent).toContain('标题与 R1/R2 高度匹配')
    expect(screen.getByText('PMID 99999999')).toBeTruthy()
    // 新卡片:PMID/DOI 为链接徽章(值在 href 中),DOI 徽章文本为「DOI」
    expect(screen.getByRole('link', { name: 'PMID 99999999' })).toHaveProperty(
      'href',
      'https://pubmed.ncbi.nlm.nih.gov/99999999/',
    )
    const doiLink = screen.getByRole('link', { name: 'DOI' }) as HTMLAnchorElement
    expect(doiLink.href).toBe('https://doi.org/10.9999/abc')
    expect(screen.getByText('摘要')).toBeTruthy()
    expect(screen.getByText('OA 全文')).toBeTruthy()
  })

  it('底部操作行:☐加入提取 / 排除此候选;无提取结果区与 [查看证据候选]', () => {
    renderCard(SEARCH_PAPER)
    expect(screen.getByTestId('paper-card-select')).toBeTruthy()
    expect(screen.getByRole('button', { name: '排除此候选' })).toBeTruthy()
    expect(screen.queryByTestId('paper-card-result')).toBeNull()
    expect(screen.queryByRole('button', { name: /查看证据候选/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /重新提取/ })).toBeNull()
  })

  it('勾选「加入提取」触发 onToggleSelected;无 paperId 时不显示 [查看详情]', () => {
    const onToggleSelected = vi.fn()
    renderCard(SEARCH_PAPER, { onToggleSelected })
    fireEvent.click(screen.getByTestId('paper-card-select'))
    expect(onToggleSelected).toHaveBeenCalledWith(true)
    expect(screen.queryByRole('button', { name: '查看详情' })).toBeNull()
  })
})

describe('PaperCandidateCard(已提取卡)', () => {
  it('提取结果区:AI判断：支持 / Coverage N/M / 已核验片段 N;不挤同一行(独立行)', () => {
    renderCard(EXTRACTED_PAPER)
    const result = screen.getByTestId('paper-card-result')
    expect(result.textContent).toContain('AI判断：支持')
    expect(result.textContent).toContain('AI 初始覆盖 1/3')
    expect(result.textContent).toContain('已核验片段 1')
    // 独立行,不与操作行混排
    expect(screen.getByTestId('paper-card-actions-row')?.textContent).not.toContain('AI判断')
  })

  it('已提取后:[查看详情] / [排除此候选] / [查看证据候选] / [重新提取];无「加入提取」', () => {
    const onOpenDetail = vi.fn()
    const onViewEvidence = vi.fn()
    const onReExtract = vi.fn()
    renderCard(EXTRACTED_PAPER, { onOpenDetail, onViewEvidence, onReExtract })
    fireEvent.click(screen.getByRole('button', { name: '查看详情' }))
    expect(onOpenDetail).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: '查看证据候选' }))
    expect(onViewEvidence).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: '重新提取' }))
    expect(onReExtract).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('paper-card-select')).toBeNull()
  })

  it('coverage_summary 为空时不渲染 Coverage 徽章', () => {
    renderCard({ ...EXTRACTED_PAPER, coverageSummary: null })
    const result = screen.getByTestId('paper-card-result')
    expect(result.textContent).not.toContain('AI 初始覆盖')
  })

  it('required_components 为空数组但 coverage_ratio 存在时回退显示百分比', () => {
    renderCard({
      ...EXTRACTED_PAPER,
      coverageSummary: { coverage_ratio: 0.5, required_components: [], supported_components: [] },
    })
    expect(screen.getByTestId('paper-card-result').textContent).toContain('AI 初始覆盖 50%')
  })

  it('required_components 缺失但 coverage_ratio 存在时回退显示百分比', () => {
    renderCard({
      ...EXTRACTED_PAPER,
      coverageSummary: { coverage_ratio: 0.5 },
    })
    expect(screen.getByTestId('paper-card-result').textContent).toContain('AI 初始覆盖 50%')
  })

  it('重新提取中禁用按钮显示进度文案', () => {
    renderCard(EXTRACTED_PAPER, { reExtracting: true })
    expect((screen.getByRole('button', { name: '重新提取中…' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
