import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { TaskItemsRefreshProvider } from '../components/taskItemsRefreshContext'
import { PaperLibraryModule } from './PaperLibraryModule'

vi.mock('../../../api/endpoints', () => ({
  listEvidencePapers: vi.fn(),
  getEvidencePaperDetail: vi.fn(),
  addPaperToLibrary: vi.fn(),
  deletePaperSoft: vi.fn(),
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  listEvidenceReviews: vi.fn(),
  listEvidencePapersDetail: vi.fn(),
}))

const PAPER: Partial<endpoints.EvidencePaperItem> = {
  id: 'p-1111', pmid: '12345678', pmcid: null, doi: '10.1000/xyz',
  title: 'Thalamic projections to motor cortex: a long title that wraps over two lines properly',
  journal: 'Nature Neuroscience', publication_year: 2024, is_oa: false,
  abstract_available: true, fulltext_available: true, paragraph_count: 12, evidence_count: 12,
}

const DETAIL: endpoints.EvidencePaperDetail = {
  paper: {
    id: 'p-1111', pmid: '12345678', pmcid: null, doi: '10.1000/xyz',
    title: 'Thalamic projections to motor cortex', journal: 'Nature Neuroscience',
    publication_year: 2024, is_oa: false, abstract_available: true, fulltext_available: true,
    paragraph_count: 12, evidence_count: 12, authors: 'A. Author, B. Author',
    abstract: 'We studied thalamic projections to motor cortex using tract tracing.',
    review_count: 3,
  },
  paragraphs: [
    { paragraph_id: 'pa-1', section_title: 'Abstract', paragraph_index: 1, passage_text: 'We studied thalamic projections.', source_scope: 'abstract' },
    { paragraph_id: 'pa-2', section_title: 'Methods', paragraph_index: 2, passage_text: 'Subjects were traced.', source_scope: 'fulltext' },
    { paragraph_id: 'pa-3', section_title: 'Results', paragraph_index: 3, passage_text: 'Dense projections were found.', source_scope: 'fulltext' },
  ],
  evidence_count: 12,
  targets: [
    { target_type: 'connection', target_id: 'conn-1' },
    { target_type: 'circuit', target_id: 'circ-1' },
  ],
}

function renderModule() {
  return render(
    <EvidenceCenterProvider>
      <TaskItemsRefreshProvider>
        <PaperLibraryModule />
      </TaskItemsRefreshProvider>
    </EvidenceCenterProvider>,
  )
}

describe('PaperLibraryModule(论文资产中心三栏)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.location.hash = ''
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listEvidencePapers).mockResolvedValue({ items: [PAPER as never], total: 1 })
    vi.mocked(endpoints.getEvidencePaperDetail).mockResolvedValue(DETAIL as never)
  })
  afterEach(() => { cleanup(); window.location.hash = ''; sessionStorage.clear() })

  it('渲染三栏:列表卡(PMID/DOI/状态标签) + 详情 + 资产关系', async () => {
    renderModule()
    const card = await screen.findByTestId('paper-card-p-1111')
    expect(card.textContent).toContain('PMID: 12345678')
    expect(card.textContent).toContain('DOI: 10.1000/xyz')
    expect(card.textContent).toContain('全文可用')
    expect(card.textContent).toContain('已生成 12 条证据')
    // 点击 → 中栏详情
    fireEvent.click(card)
    await waitFor(() => expect(vi.mocked(endpoints.getEvidencePaperDetail)).toHaveBeenCalledWith('p-1111'))
    expect(await screen.findByText('Paper Information')).toBeTruthy()
    expect(screen.getByText('We studied thalamic projections to motor cortex using tract tracing.')).toBeTruthy()
    // 右栏统计
    const right = screen.getByTestId('paper-library-right')
    expect(within(right).getByText('Evidence')).toBeTruthy()
    expect(within(right).getByText('Reviews')).toBeTruthy()
  })

  it('FullText 分章节展示(Abstract 聚合;无全文显示等待文案)', async () => {
    renderModule()
    fireEvent.click(await screen.findByTestId('paper-card-p-1111'))
    await screen.findByText('Paper Information')
    expect(screen.getAllByText(/Methods/).length).toBeGreaterThan(0)
    expect(screen.getByText('Dense projections were found.')).toBeTruthy()
  })

  it('Evidence Preview: 点击「进入证据候选」→ openTarget(candidates)', async () => {
    renderModule()
    fireEvent.click(await screen.findByTestId('paper-card-p-1111'))
    await screen.findByText(/Evidence Candidates:/)
    fireEvent.click(screen.getByTestId('paper-target-open-0'))
    await waitFor(() => expect(window.location.hash).toContain('target_type=connection'))
    expect(window.location.hash).toContain('target_id=conn-1')
    expect(window.location.hash).toContain('module=candidates')
  })

  it('PMID 搜索提交:调用 listEvidencePapers(search=', async () => {
    renderModule()
    const input = await screen.findByTestId('paper-search-input')
    fireEvent.change(input, { target: { value: '12345678' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() =>
      expect(vi.mocked(endpoints.listEvidencePapers)).toHaveBeenCalledWith(
        expect.objectContaining({ search: '12345678' })))
  })

  it('添加论文:PMID 填写 → 提交(addPaperToLibrary);重复返回提示不重复创建', async () => {
    vi.mocked(endpoints.addPaperToLibrary).mockResolvedValue({
      paper_id: 'p-x', created: false, message: 'already_exists',
    })
    renderModule()
    fireEvent.click(await screen.findByTestId('paper-add-btn'))
    fireEvent.change(screen.getByLabelText('PMID'), { target: { value: '99999999' } })
    fireEvent.click(screen.getByTestId('paper-add-confirm'))
    await waitFor(() =>
      expect(vi.mocked(endpoints.addPaperToLibrary))
        .toHaveBeenCalledWith({ pmid: '99999999', doi: null, url: null }))
    const msg = await screen.findByTestId('paper-add-msg')
    expect(msg.textContent).toContain('已存在')
    expect(msg.textContent).toContain('未重复创建')
  })

  it('删除为软删除:确认 → deletePaperSoft 调用 + 列表刷新', async () => {
    vi.mocked(endpoints.deletePaperSoft).mockResolvedValue({
      paper_id: 'p-1111', deleted: true, deleted_at: '2026-09-28T00:00:00Z', deleted_by: 'reviewer',
    })
    renderModule()
    fireEvent.click(await screen.findByTestId('paper-delete-p-1111'))
    fireEvent.click(await screen.findByText('删除'))
    await waitFor(() => expect(vi.mocked(endpoints.deletePaperSoft)).toHaveBeenCalledWith('p-1111'))
    expect(await screen.findByText(/软删除/)).toBeTruthy()
  })

  it('无全文论文 → 显示「摘要可用 · 等待全文解析」', async () => {
    vi.mocked(endpoints.listEvidencePapers).mockResolvedValue({
      items: [{ ...PAPER, fulltext_available: false, abstract_available: true } as never], total: 1,
    })
    vi.mocked(endpoints.getEvidencePaperDetail).mockResolvedValue({
      ...DETAIL,
      paper: { ...DETAIL.paper, fulltext_available: false },
      paragraphs: [DETAIL.paragraphs[0]],
    } as never)
    renderModule()
    fireEvent.click(await screen.findByTestId('paper-card-p-1111'))
    const txt = await screen.findByTestId('paper-fulltext-empty')
    expect(txt.textContent).toContain('摘要可用')
    expect(txt.textContent).toContain('等待全文解析')
  })

  it('结构检查:container > body > (sidebar + detail-panel + relation-panel) 三栏层级,未选论文显示空态', async () => {
    const { container } = renderModule()
    const root = container.querySelector('.paper-library-container')
    const body = root?.querySelector('.paper-library-body')
    const sidebar = body?.querySelector('.paper-library-sidebar')
    const detail = body?.querySelector('.paper-detail-panel')
    const relation = body?.querySelector('.paper-relation-panel')
    expect(root).toBeTruthy()
    expect(body).toBeTruthy()
    // 三栏兄弟层级(container>body 内并列)
    expect(sidebar).toBeTruthy()
    expect(detail).toBeTruthy()
    expect(relation).toBeTruthy()
    expect(detail?.parentElement).toBe(body ?? null)
    expect(sidebar?.parentElement).toBe(body ?? null)
    expect(relation?.parentElement).toBe(body ?? null)
    // 未选论文:中栏空态文案(不留白)
    expect(screen.getByText('请选择论文查看详情')).toBeTruthy()
    // 三栏元素均在 DOM(宽度契约由 CSS 表达,测试保留 testid 断言)
    expect(screen.getByTestId('paper-library-center')).toBeTruthy()
    expect(screen.getByTestId('paper-library-right')).toBeTruthy()
  })
})

