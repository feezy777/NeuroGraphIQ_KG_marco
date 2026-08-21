import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { RelationItem } from '../detail/types'
import { RelationCard } from './RelationCard'
import { SectionCard } from './SectionCard'
import { StatusChip } from './StatusChip'

describe('StatusChip', () => {
  it('maps statuses to tones and hides for missing status', () => {
    const { rerender, container } = render(<StatusChip status="active" />)
    expect(container.querySelector('.oc-status-chip-green')).toBeTruthy()

    rerender(<StatusChip status="proposed" />)
    expect(container.querySelector('.oc-status-chip-yellow')).toBeTruthy()

    rerender(<StatusChip status="deprecated" />)
    expect(container.querySelector('.oc-status-chip-gray')).toBeTruthy()

    rerender(<StatusChip status={null} />)
    expect(container.querySelector('.oc-status-chip')).toBeNull()
  })
})

describe('SectionCard', () => {
  it('collapses and expands via the header button', () => {
    render(
      <SectionCard title="Overview">
        <span>body</span>
      </SectionCard>,
    )

    expect(screen.getByText('body')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Overview/ }))
    expect(screen.queryByText('body')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Overview/ }))
    expect(screen.getByText('body')).toBeTruthy()
  })

  it('shows a count pill when provided', () => {
    const { container } = render(
      <SectionCard title="Hierarchy" count={3}>
        <span>x</span>
      </SectionCard>,
    )

    expect(container.querySelector('.oc-section-card-count')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
  })
})

describe('RelationCard', () => {
  const item: RelationItem = {
    ref: {
      id: 'r-cerebrum',
      code: 'ng:br:cerebrum',
      name: 'Cerebrum',
      entityType: 'region',
      status: 'active',
    },
    meta: [
      { label: '方向', value: '出向' },
      { label: '置信度', value: '80%' },
    ],
  }

  it('renders a navigable button card with meta rows', () => {
    const onNavigate = vi.fn()
    render(<RelationCard item={item} arrow="down" onNavigate={onNavigate} />)

    const card = screen.getByRole('button')
    expect(card.className).toContain('oc-relation-card')
    expect(screen.getByText('出向')).toBeTruthy()
    expect(screen.getByText('80%')).toBeTruthy()

    fireEvent.click(card)
    expect(onNavigate).toHaveBeenCalledWith('region', 'r-cerebrum')
  })

  it('renders static cards for non-navigable items', () => {
    const { container } = render(<RelationCard item={item} navigable={false} />)

    expect(container.querySelector('.oc-relation-card-static')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})
