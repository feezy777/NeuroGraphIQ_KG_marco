import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { PaperLibraryModule } from './PaperLibraryModule'

vi.mock('../../../api/endpoints', () => ({
  listEvidencePapers: vi.fn(),
  getEvidencePaperDetail: vi.fn(),
}))

const PAPER_A = {
  id: 'p1',
  pmid: '12345678',
  pmcid: 'PMC1234567',
  doi: '10.1000/xyz123',
  title: 'Neural circuits of the prefrontal cortex',
  journal: 'Nature Neuroscience',
  publication_year: 2023,
  is_oa: true,
  abstract_available: true,
  fulltext_available: true,
  paragraph_count: 12,
  evidence_count: 3,
}

const PAPER_B = {
  id: 'p2',
  pmid: null,
  pmcid: null,
  doi: '10.1000/abc456',
  title: 'Thalamocortical loops in working memory',
  journal: 'Brain Research',
  publication_year: 2021,
  is_oa: false,
  abstract_available: false,
  fulltext_available: false,
  paragraph_count: 0,
  evidence_count: 0,
}

const DETAIL = {
  paper: PAPER_A,
  paragraphs: [
    { paragraph_id: 'pa1', section_title: 'Abstract', paragraph_index: 0, passage_text: 'The prefrontal cortex integrates sensory input with mnemonic content.', source_scope: 'abstract' },
    { paragraph_id: 'pa2', section_title: 'Abstract', paragraph_index: 1, passage_text: 'Here we show that recurrent dynamics support working memory.', source_scope: 'abstract' },
    { paragraph_id: 'pf1', section_title: 'Results', paragraph_index: 2, passage_text: 'We found elevated gamma power in layer 5.', source_scope: 'fulltext' },
    { paragraph_id: 'pf2', section_title: 'Discussion', paragraph_index: 3, passage_text: 'These findings suggest a distributed mnemonic network.', source_scope: 'fulltext' },
  ],
  evidence_count: 3,
  targets: [{ target_type: 'connection', target_id: 'conn-1' }],
}

const renderModule = () =>
  render(<EvidenceCenterProvider><PaperLibraryModule /></EvidenceCenterProvider>)

describe('PaperLibraryModule', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listEvidencePapers).mockResolvedValue({ items: [PAPER_A, PAPER_B], total: 2 })
    vi.mocked(endpoints.getEvidencePaperDetail).mockResolvedValue(DETAIL)
  })

  it('列表渲染 title/journal/年份/OA 徽章/段落数/证据数', async () => {
    renderModule()
    expect(await screen.findByText('Neural circuits of the prefrontal cortex')).toBeTruthy()
    expect(screen.getByText('Nature Neuroscience (2023)')).toBeTruthy()
    expect(screen.getByText('Brain Research (2021)')).toBeTruthy()
    // OA 徽章(仅 PAPER_A)
    expect(screen.getByText('OA')).toBeTruthy()
    // 摘要/全文可用徽章 + 段落数 + 证据数
    expect(screen.getByText('摘要可用')).toBeTruthy()
    expect(screen.getByText('全文可用')).toBeTruthy()
    expect(screen.getByText('12 段')).toBeTruthy()
    expect(screen.getByText('3 条证据')).toBeTruthy()
    expect(screen.getByText('0 段')).toBeTruthy()
    // 标识
    expect(screen.getByText('PMID 12345678')).toBeTruthy()
    expect(screen.getByText('DOI 10.1000/abc456')).toBeTruthy()
    // 论文库不渲染 Reviewer/Attach/Coverage 控件
    expect(screen.queryByText(/确认晋升|Reviewer|Coverage|Attach/i)).toBeNull()
  })

  it('搜索与过滤条件携带参数重新请求', async () => {
    renderModule()
    await screen.findByText('Neural circuits of the prefrontal cortex')
    fireEvent.change(screen.getByPlaceholderText(/搜索/), { target: { value: 'prefrontal' } })
    fireEvent.click(screen.getByLabelText('仅开放获取'))
    fireEvent.change(screen.getByLabelText('年份'), { target: { value: '2023' } })
    fireEvent.click(screen.getByLabelText('已解析全文'))
    fireEvent.click(screen.getByText('搜索'))
    await waitFor(() =>
      expect(endpoints.listEvidencePapers).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'prefrontal', oa: true, year: 2023, has_fulltext: true, page: 1 }),
      ),
    )
    // 再次搜索会重置页码
    fireEvent.change(screen.getByPlaceholderText(/搜索/), { target: { value: '' } })
    fireEvent.click(screen.getByText('搜索'))
    await waitFor(() =>
      expect(endpoints.listEvidencePapers).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: undefined, oa: true, year: 2023, has_fulltext: true, page: 1 }),
      ),
    )
  })

  it('点击论文卡片打开详情抽屉(metadata + abstract + section 结构)', async () => {
    renderModule()
    await screen.findByText('Neural circuits of the prefrontal cortex')
    fireEvent.click(screen.getByText('Neural circuits of the prefrontal cortex'))
    await waitFor(() => expect(endpoints.getEvidencePaperDetail).toHaveBeenCalledWith('p1'))
    // metadata 行
    expect(screen.getByText('期刊')).toBeTruthy()
    expect(screen.getByText('PMID')).toBeTruthy()
    expect(screen.getByText('DOI')).toBeTruthy()
    expect(screen.getAllByText('Nature Neuroscience (2023)').length).toBeGreaterThanOrEqual(2)
    // abstract 段落默认展开
    expect(screen.getByText('The prefrontal cortex integrates sensory input with mnemonic content.')).toBeTruthy()
    // section 分组默认折叠:标题可见,段落隐藏
    expect(screen.getByText('Results')).toBeTruthy()
    expect(screen.queryByText('We found elevated gamma power in layer 5.')).toBeNull()
    // 展开后显示段落
    fireEvent.click(screen.getByText('Results'))
    expect(screen.getByText('We found elevated gamma power in layer 5.')).toBeTruthy()
    // 关联证据数 + targets 列表
    expect(screen.getByText('关联证据')).toBeTruthy()
    expect(screen.getByText('3 条')).toBeTruthy()
    expect(screen.getByText('connection · conn-1')).toBeTruthy()
    // 抽屉内同样不渲染 Reviewer/Attach/Coverage
    expect(screen.queryByText(/确认晋升|Reviewer|Coverage|Attach/i)).toBeNull()
  })

  it('点击 target 跳转证据候选模块', async () => {
    renderModule()
    await screen.findByText('Neural circuits of the prefrontal cortex')
    fireEvent.click(screen.getByText('Neural circuits of the prefrontal cortex'))
    await waitFor(() => expect(screen.getByText('connection · conn-1')).toBeTruthy())
    fireEvent.click(screen.getByText('connection · conn-1'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('target_type=connection')
    expect(window.location.hash).toContain('target_id=conn-1')
  })

  it('分页切换重新请求(上一页/下一页)', async () => {
    vi.mocked(endpoints.listEvidencePapers).mockResolvedValue({ items: [PAPER_A], total: 25 })
    renderModule()
    await screen.findByText('Neural circuits of the prefrontal cortex')
    // 第 1 页:上一页禁用
    expect((screen.getByText('上一页') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByText('下一页'))
    await waitFor(() =>
      expect(endpoints.listEvidencePapers).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })),
    )
    // 第 2 页:下一页禁用,上一页可用
    await waitFor(() => expect((screen.getByText('下一页') as HTMLButtonElement).disabled).toBe(true))
    expect((screen.getByText('上一页') as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(screen.getByText('上一页'))
    await waitFor(() =>
      expect(endpoints.listEvidencePapers).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 })),
    )
  })

  it('加载失败显示错误并可重试', async () => {
    vi.mocked(endpoints.listEvidencePapers).mockRejectedValueOnce(new Error('503 backend down'))
    renderModule()
    await waitFor(() => expect(screen.getByText(/论文加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByText('重试'))
    await waitFor(() => expect(screen.getByText('Neural circuits of the prefrontal cortex')).toBeTruthy())
  })
})
