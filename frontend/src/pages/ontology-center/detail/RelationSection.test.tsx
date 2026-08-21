import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { RelationSection } from './RelationSection'
import type { RelationGroup } from './types'

describe('RelationSection', () => {
  it('renders group label, count and items with meta', () => {
    const group: RelationGroup = {
      key: 'connections',
      label: 'Related Connections',
      items: [
        {
          ref: { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' },
          meta: [
            { label: '方向', value: '出向' },
            { label: '置信度', value: '80%' },
          ],
        },
      ],
    }
    render(<RelationSection group={group} />)

    expect(screen.getByText('Related Connections')).toBeTruthy()
    expect(screen.getByText('1')).toBeTruthy() // count
    expect(screen.getByText('Cerebrum')).toBeTruthy()
    expect(screen.getByText('ng:br:cerebrum')).toBeTruthy()
    expect(screen.getByText('出向')).toBeTruthy()
    expect(screen.getByText('80%')).toBeTruthy()
  })

  it('renders empty state with reason for unavailable groups without fake data', () => {
    const group: RelationGroup = { key: 'circuits', label: 'Related Circuits', unavailable: true, items: [] }
    render(<RelationSection group={group} />)

    expect(screen.getByText('No canonical relation available')).toBeTruthy()
    expect(screen.getByText('后端 API 待接入（不展示假数据）')).toBeTruthy()
  })

  it('renders empty state with reason for empty available groups', () => {
    const group: RelationGroup = { key: 'connections', label: 'Related Connections', items: [] }
    render(<RelationSection group={group} />)

    expect(screen.getByText('No canonical relation available')).toBeTruthy()
    expect(screen.getByText('该实体暂无此关系记录')).toBeTruthy()
  })

  it('renders non-navigable items as static rows', () => {
    const group: RelationGroup = {
      key: 'candidates',
      label: 'Evidence · 对齐候选',
      navigable: false,
      items: [
        {
          ref: { id: 'cand-1', code: null, name: 'Brain', entityType: 'region' },
          meta: [{ label: '图谱', value: 'AAL3' }],
        },
      ],
    }
    const { container } = render(<RelationSection group={group} />)

    expect(screen.getByText('Brain')).toBeTruthy()
    expect(container.querySelector('.oc-relation-card-static')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('calls onNavigate with the ref entity when an item is clicked', () => {
    const onNavigate = vi.fn()
    const group: RelationGroup = {
      key: 'children',
      label: '子节点',
      items: [
        {
          ref: { id: 'r-hippo', code: null, name: 'Hippocampus', entityType: 'region', status: 'active' },
          meta: [],
        },
      ],
    }
    render(<RelationSection group={group} onNavigate={onNavigate} />)

    fireEvent.click(screen.getByRole('button'))
    expect(onNavigate).toHaveBeenCalledWith('region', 'r-hippo')
  })
})
