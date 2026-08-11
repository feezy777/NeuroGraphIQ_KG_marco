import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PaperBatchActions } from './PaperBatchActions'

function renderActions(overrides: Partial<Parameters<typeof PaperBatchActions>[0]> = {}) {
  const props = {
    allSelected: false,
    onToggleAll: vi.fn(),
    selectedCount: 0,
    busy: false,
    onExtractSelected: vi.fn(),
    canSelect: true,
    canCollapse: true,
    onCollapse: vi.fn(),
    ...overrides,
  }
  return render(<PaperBatchActions {...props} />)
}

describe('PaperBatchActions', () => {
  it('渲染「批量操作」+ ☐全选 + 提取所选论文(N)', () => {
    renderActions({ selectedCount: 2 })
    expect(screen.getByText('批量操作')).toBeTruthy()
    const selectAll = screen.getByRole('checkbox', { name: '全选' })
    expect(selectAll).toBeTruthy()
    expect(screen.getByRole('button', { name: '提取所选论文（2）' })).toBeTruthy()
  })

  it('N=0 时 [提取所选论文] 禁用', () => {
    renderActions({ selectedCount: 0 })
    expect((screen.getByRole('button', { name: '提取所选论文（0）' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('☐全选 勾选/取消触发 onToggleAll;全部勾选时呈选中态', () => {
    const onToggleAll = vi.fn()
    const { rerender } = renderActions({ onToggleAll })
    const box = screen.getByRole('checkbox', { name: '全选' }) as HTMLInputElement
    expect(box.checked).toBe(false)
    fireEvent.click(box)
    expect(onToggleAll).toHaveBeenCalledWith(true)
    rerender(
      <PaperBatchActions
        allSelected={true}
        onToggleAll={onToggleAll}
        selectedCount={2}
        busy={false}
        onExtractSelected={vi.fn()}
        canSelect={true}
        canCollapse={true}
        onCollapse={vi.fn()}
      />,
    )
    expect((screen.getByRole('checkbox', { name: '全选' }) as HTMLInputElement).checked).toBe(true)
    fireEvent.click(screen.getByRole('checkbox', { name: '全选' }))
    expect(onToggleAll).toHaveBeenCalledWith(false)
  })

  it('无可选论文时 ☐全选 禁用;busy 时提取与全选均禁用', () => {
    const { rerender } = renderActions({ canSelect: false })
    expect((screen.getByRole('checkbox', { name: '全选' }) as HTMLInputElement).disabled).toBe(true)
    rerender(
      <PaperBatchActions
        allSelected={false}
        onToggleAll={vi.fn()}
        selectedCount={1}
        busy={true}
        onExtractSelected={vi.fn()}
        canSelect={true}
        canCollapse={true}
        onCollapse={vi.fn()}
      />,
    )
    expect((screen.getByRole('checkbox', { name: '全选' }) as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '提取所选论文（1）' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('[收起检索] 有结果时显示并触发 onCollapse;无结果时隐藏', () => {
    const onCollapse = vi.fn()
    const first = renderActions({ onCollapse })
    fireEvent.click(screen.getByRole('button', { name: '收起检索' }))
    expect(onCollapse).toHaveBeenCalledTimes(1)
    first.unmount()
    renderActions({ canCollapse: false })
    expect(screen.queryByRole('button', { name: '收起检索' })).toBeNull()
  })
})
