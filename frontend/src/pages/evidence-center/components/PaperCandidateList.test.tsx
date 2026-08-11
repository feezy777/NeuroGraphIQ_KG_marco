import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PaperCandidateList } from './PaperCandidateList'

function renderList(overrides: Partial<Parameters<typeof PaperCandidateList>[0]> = {}) {
  const props = {
    total: 0,
    searchable: true,
    onAdjustSearch: vi.fn(),
    children: <div data-testid="candidate-cards">cards</div>,
    ...overrides,
  }
  return render(<PaperCandidateList {...props} />)
}

describe('PaperCandidateList(空态)', () => {
  it('标题「候选论文(N)」+ 暂无候选论文 + 说明 + [调整检索条件] + 底部轻提示', () => {
    renderList()
    expect(screen.getByText('候选论文（0）')).toBeTruthy()
    expect(screen.getByText('暂无候选论文')).toBeTruthy()
    expect(screen.getByText('当前还没有找到相关论文，可尝试调整检索条件后重新搜索。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '调整检索条件' })).toBeTruthy()
    expect(screen.getByTestId('evidence-candidates-hint').textContent).toContain('勾选论文后可批量操作')
    expect(screen.getByTestId('evidence-candidates-hint').textContent).toContain('已隐藏')
    expect(screen.queryByTestId('candidate-cards')).toBeNull()
  })

  it('[调整检索条件] 触发 onAdjustSearch(展开检索面板)', () => {
    const onAdjustSearch = vi.fn()
    renderList({ onAdjustSearch })
    fireEvent.click(screen.getByRole('button', { name: '调整检索条件' }))
    expect(onAdjustSearch).toHaveBeenCalledTimes(1)
  })

  it('不可手动检索时(任务候选):暂无候选证据 文案,无 [调整检索条件] 按钮', () => {
    renderList({ searchable: false })
    expect(screen.getByText('暂无候选证据')).toBeTruthy()
    expect(screen.getByText('当前对象暂无候选证据，可尝试重新提取或切换其他对象。')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '调整检索条件' })).toBeNull()
  })

})

describe('PaperCandidateList(有结果)', () => {
  it('渲染子卡片列表,不渲染空态与轻提示', () => {
    renderList({ total: 2 })
    expect(screen.getByText('候选论文（2）')).toBeTruthy()
    expect(screen.getByTestId('candidate-cards')).toBeTruthy()
    expect(screen.queryByTestId('evidence-empty')).toBeNull()
    expect(screen.queryByTestId('evidence-candidates-hint')).toBeNull()
  })
})
