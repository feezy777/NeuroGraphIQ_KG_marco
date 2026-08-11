import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PaperSearchPanel } from './PaperSearchPanel'

function renderPanel(overrides: Partial<Parameters<typeof PaperSearchPanel>[0]> = {}) {
  const props = {
    collapsed: false,
    busy: false,
    query: '',
    onQueryChange: vi.fn(),
    onSearch: vi.fn(),
    onRestoreRecommended: vi.fn(),
    queryTerms: ['R1', 'R2'],
    onClearTerm: vi.fn(),
    querySummary: 'R1 · R2',
    onExpand: vi.fn(),
    selectedCount: 0,
    onExtractSelected: vi.fn(),
    filters: <div data-testid="filters-slot">filters</div>,
    batchActions: <div data-testid="batch-slot">batch</div>,
    ...overrides,
  }
  return render(<PaperSearchPanel {...props} />)
}

describe('PaperSearchPanel(展开态)', () => {
  it('渲染标题「查找相关论文」+ 大搜索框(推荐 placeholder)+ 重新搜索/恢复系统推荐', () => {
    renderPanel()
    expect(screen.getByText('查找相关论文')).toBeTruthy()
    const input = screen.getByTestId('evidence-search-query') as HTMLInputElement
    expect(input.placeholder).toContain('检索式 / 关键词')
    expect(screen.getByRole('button', { name: '重新搜索' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '恢复系统推荐' })).toBeTruthy()
  })

  it('Query Chips 渲染关键词并带 × 清空按钮;点击触发 onClearTerm', () => {
    const onClearTerm = vi.fn()
    renderPanel({ onClearTerm })
    const chips = screen.getAllByTestId('evidence-query-term')
    expect(chips.map(c => c.textContent)).toEqual(expect.arrayContaining(['R1×', 'R2×']))
    fireEvent.click(screen.getByRole('button', { name: '清空关键词 R1' }))
    expect(onClearTerm).toHaveBeenCalledWith('R1')
  })

  it('无推荐词时隐藏 chips 行', () => {
    renderPanel({ queryTerms: [] })
    expect(screen.queryByTestId('evidence-search-terms')).toBeNull()
  })

  it('输入框受控;点击重新搜索/恢复系统推荐触发回调;busy 时禁用', () => {
    const onSearch = vi.fn()
    const onRestoreRecommended = vi.fn()
    const onQueryChange = vi.fn()
    renderPanel({ onSearch, onRestoreRecommended, onQueryChange, busy: true })
    fireEvent.change(screen.getByTestId('evidence-search-query'), { target: { value: 'abc' } })
    expect(onQueryChange).toHaveBeenCalledWith('abc')
    expect((screen.getByRole('button', { name: '检索中…' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '恢复系统推荐' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '检索中…' }))
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('展开态渲染 filters / batchActions 插槽', () => {
    renderPanel()
    expect(screen.getByTestId('filters-slot')).toBeTruthy()
    expect(screen.getByTestId('batch-slot')).toBeTruthy()
  })
})

describe('PaperSearchPanel(折叠条)', () => {
  it('折叠态:Query 摘要 + 重新搜索 + 展开检索 + 提取所选论文(N);不渲染三层插槽', () => {
    renderPanel({ collapsed: true, selectedCount: 3 })
    expect(screen.getByTestId('evidence-search-collapsed')).toBeTruthy()
    expect(screen.getByTestId('evidence-search-collapsed-query').textContent).toContain('R1 · R2')
    expect(screen.getByRole('button', { name: '重新搜索' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '展开检索' })).toBeTruthy()
    expect(screen.getByTestId('evidence-collapsed-extract').textContent).toContain('提取所选论文（3）')
    expect(screen.queryByTestId('filters-slot')).toBeNull()
    expect(screen.queryByTestId('batch-slot')).toBeNull()
    expect(screen.queryByText('查找相关论文')).toBeNull()
  })

  it('折叠条 [展开检索] / [重新搜索] / [提取所选论文] 触发对应回调', () => {
    const onExpand = vi.fn()
    const onSearch = vi.fn()
    const onExtractSelected = vi.fn()
    renderPanel({ collapsed: true, onExpand, onSearch, onExtractSelected, selectedCount: 2 })
    fireEvent.click(screen.getByRole('button', { name: '展开检索' }))
    expect(onExpand).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: '重新搜索' }))
    expect(onSearch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByTestId('evidence-collapsed-extract'))
    expect(onExtractSelected).toHaveBeenCalledTimes(1)
  })

  it('折叠条 [提取所选论文] 零选中或 busy 时禁用', () => {
    renderPanel({ collapsed: true, selectedCount: 0 })
    expect((screen.getByTestId('evidence-collapsed-extract') as HTMLButtonElement).disabled).toBe(true)
  })
})
