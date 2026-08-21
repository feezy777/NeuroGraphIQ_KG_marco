import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { RelationExplorer } from './RelationExplorer'
import type { RelationGroup } from './types'

const GROUPS: RelationGroup[] = [
  {
    key: 'children',
    label: '子节点',
    items: [
      {
        ref: { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' },
        meta: [],
      },
    ],
  },
  { key: 'connections', label: 'Related Connections', items: [] },
  { key: 'circuits', label: 'Related Circuits', unavailable: true, items: [] },
]

describe('RelationExplorer', () => {
  it('shows skeleton while groups are loading', () => {
    render(<RelationExplorer groups={null} hasError={false} />)
    expect(screen.getByLabelText('加载中')).toBeTruthy()
  })

  it('shows error state with retry', () => {
    const onRetry = vi.fn()
    render(<RelationExplorer groups={null} hasError onRetry={onRetry} />)

    expect(screen.getByText('Relations failed to load')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it('renders tabs with count badges and default All view', () => {
    render(<RelationExplorer groups={GROUPS} hasError={false} />)

    const tablist = screen.getByRole('tablist')
    expect(within(tablist).getByRole('tab', { name: /All/ })).toBeTruthy()
    expect(within(tablist).getByRole('tab', { name: /Connections/ })).toBeTruthy()
    expect(within(tablist).getByRole('tab', { name: /Circuits/ })).toBeTruthy()
    // 无 functions 分组 → 不渲染 Functions tab
    expect(within(tablist).queryByRole('tab', { name: /Functions/ })).toBeNull()
    // All 计数 = 可用分组 items 总和（unavailable 不计入）
    expect(within(within(tablist).getByRole('tab', { name: /All/ })).getByText('1')).toBeTruthy()

    expect(screen.getByText('Cerebrum')).toBeTruthy()
  })

  it('filters groups to the selected tab', () => {
    render(<RelationExplorer groups={GROUPS} hasError={false} />)

    fireEvent.click(screen.getByRole('tab', { name: /Connections/ }))
    expect(screen.queryByText('Cerebrum')).toBeNull()
    expect(screen.getByText('该实体暂无此关系记录')).toBeTruthy()
  })

  it('clicking a relation navigates', () => {
    const onNavigate = vi.fn()
    render(<RelationExplorer groups={GROUPS} hasError={false} onNavigate={onNavigate} />)

    fireEvent.click(screen.getByText('Cerebrum'))
    expect(onNavigate).toHaveBeenCalledWith('region', 'r-cerebrum')
  })
})
