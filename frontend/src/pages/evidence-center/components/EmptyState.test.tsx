import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('渲染图标 + 标题 + 说明 + 操作按钮', () => {
    render(
      <EmptyState
        icon={<span data-testid="empty-icon">📄</span>}
        title="暂无候选论文"
        description="当前还没有找到相关论文，可尝试调整检索条件后重新搜索。"
        actionLabel="调整检索条件"
        onAction={vi.fn()}
      />,
    )
    expect(screen.getByTestId('evidence-empty')).toBeTruthy()
    expect(screen.getByTestId('empty-icon')).toBeTruthy()
    expect(screen.getByText('暂无候选论文')).toBeTruthy()
    expect(screen.getByText('当前还没有找到相关论文，可尝试调整检索条件后重新搜索。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '调整检索条件' })).toBeTruthy()
  })

  it('无 icon / 说明 / 按钮时不渲染对应区域', () => {
    render(<EmptyState title="空" />)
    expect(screen.getByText('空')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('点击操作按钮触发 onAction', () => {
    const onAction = vi.fn()
    render(<EmptyState title="空" actionLabel="重试" onAction={onAction} />)
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })
})
