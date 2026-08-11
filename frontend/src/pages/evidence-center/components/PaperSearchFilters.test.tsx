import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PaperSearchFilters } from './PaperSearchFilters'

function renderFilters(overrides: Partial<Parameters<typeof PaperSearchFilters>[0]> = {}) {
  const props = {
    oaOnly: false,
    onOaOnlyChange: vi.fn(),
    mode: 'auto' as const,
    onModeChange: vi.fn(),
    year: '',
    onYearChange: vi.fn(),
    onRestoreDefaults: vi.fn(),
    excludedCount: 0,
    onRestoreExcluded: vi.fn(),
    ...overrides,
  }
  return render(<PaperSearchFilters {...props} />)
}

describe('PaperSearchFilters', () => {
  it('渲染标题「检索过滤」+ ☐仅OA / 证据模式 / 年份 / 恢复默认 / 恢复排除', () => {
    renderFilters()
    expect(screen.getByText('检索过滤')).toBeTruthy()
    expect(screen.getByLabelText('仅 OA')).toBeTruthy()
    expect(screen.getByLabelText('证据模式')).toBeTruthy()
    expect(screen.getByLabelText('年份')).toBeTruthy()
    expect(screen.getByRole('button', { name: '恢复默认' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '恢复排除' })).toBeTruthy()
  })

  it('☐仅OA 切换触发回调', () => {
    const onOaOnlyChange = vi.fn()
    renderFilters({ onOaOnlyChange })
    fireEvent.click(screen.getByLabelText('仅 OA'))
    expect(onOaOnlyChange).toHaveBeenCalledWith(true)
  })

  it('证据模式 select 切换触发回调(自动/存在性/功能性)', () => {
    const onModeChange = vi.fn()
    renderFilters({ onModeChange })
    const select = screen.getByLabelText('证据模式') as HTMLSelectElement
    expect(select.value).toBe('auto')
    fireEvent.change(select, { target: { value: 'existence' } })
    expect(onModeChange).toHaveBeenCalledWith('existence')
  })

  it('年份 select 默认不限,选择具体年份触发回调', () => {
    const onYearChange = vi.fn()
    renderFilters({ onYearChange })
    const select = screen.getByLabelText('年份') as HTMLSelectElement
    expect(select.value).toBe('')
    fireEvent.change(select, { target: { value: '2020' } })
    expect(onYearChange).toHaveBeenCalledWith('2020')
  })

  it('[恢复默认] 触发回调(重置仅OA/模式/年份)', () => {
    const onRestoreDefaults = vi.fn()
    renderFilters({ onRestoreDefaults })
    fireEvent.click(screen.getByRole('button', { name: '恢复默认' }))
    expect(onRestoreDefaults).toHaveBeenCalledTimes(1)
  })

  it('[恢复排除] 无排除时禁用,有排除时可点击找回', () => {
    const onRestoreExcluded = vi.fn()
    const { rerender } = renderFilters({ onRestoreExcluded })
    expect((screen.getByRole('button', { name: '恢复排除' }) as HTMLButtonElement).disabled).toBe(true)
    rerender(
      <PaperSearchFilters
        oaOnly={false}
        onOaOnlyChange={vi.fn()}
        mode="auto"
        onModeChange={vi.fn()}
        year=""
        onYearChange={vi.fn()}
        onRestoreDefaults={vi.fn()}
        excludedCount={2}
        onRestoreExcluded={onRestoreExcluded}
      />,
    )
    expect((screen.getByRole('button', { name: '恢复排除' }) as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: '恢复排除' }))
    expect(onRestoreExcluded).toHaveBeenCalledTimes(1)
  })
})
