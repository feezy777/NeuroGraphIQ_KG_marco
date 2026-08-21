import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { TreeNodeRow } from './TreeNodeRow'
import type { OntologyTreeNode } from './OntologyTreeNode'

const NODE: OntologyTreeNode = {
  id: 'r-brain',
  code: 'ng:br:brain',
  name: 'Brain',
  entityType: 'region',
  granularityLevel: 'whole_brain',
  status: 'active',
}

function renderRow(overrides: Partial<Parameters<typeof TreeNodeRow>[0]> = {}) {
  const onToggle = vi.fn()
  const onSelect = vi.fn()
  const props = {
    node: NODE,
    depth: 2,
    isExpanded: false,
    isSelected: false,
    isLoading: false,
    hasError: false,
    showChevron: true,
    onToggle,
    onSelect,
    ...overrides,
  }
  render(<TreeNodeRow {...props} />)
  return { onToggle, onSelect }
}

describe('TreeNodeRow', () => {
  it('renders name, code tooltip and [Whole-brain] 粒度徽章（不显示 L 编号）', () => {
    renderRow()
    expect(screen.getByText('Brain')).toBeTruthy()
    expect(screen.queryByText('ng:br:brain')).toBeNull() // code 不进文本，隐藏在行 tooltip
    expect(screen.getByTitle('ng:br:brain')).toBeTruthy()
    expect(screen.getByText('[Whole-brain]')).toBeTruthy()
    // 医生视角：不出现 L0-L9 编号徽章
    expect(screen.queryByText('[L0]')).toBeNull()
    // 长名称省略：名称自身携带 tooltip
    expect(screen.getByTitle('Brain')).toBeTruthy()
  })

  it('shows 收起 when expanded and 展开 when collapsed', () => {
    const { rerender } = render(<TreeNodeRow node={NODE} depth={0} isExpanded={false} isSelected={false} isLoading={false} hasError={false} showChevron onToggle={() => {}} onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: '展开' })).toBeTruthy()
    rerender(<TreeNodeRow node={NODE} depth={0} isExpanded isSelected={false} isLoading={false} hasError={false} showChevron onToggle={() => {}} onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: '收起' })).toBeTruthy()
  })

  it('chevron click calls onToggle but not onSelect', () => {
    const { onToggle, onSelect } = renderRow()
    fireEvent.click(screen.getByRole('button', { name: '展开' }))
    expect(onToggle).toHaveBeenCalledWith(NODE)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('row click calls onSelect', () => {
    const { onSelect } = renderRow()
    fireEvent.click(screen.getByText('Brain'))
    expect(onSelect).toHaveBeenCalledWith(NODE)
  })

  it('shows spinner while loading and error badge on failure', () => {
    renderRow({ isLoading: true })
    expect(screen.getByLabelText('加载中')).toBeTruthy()
  })

  it('renders status chip with the node status class', () => {
    const { container } = render(
      <TreeNodeRow node={NODE} depth={0} isExpanded={false} isSelected={false} isLoading={false} hasError showChevron onToggle={() => {}} onSelect={() => {}} />,
    )
    expect(screen.getByText('加载失败')).toBeTruthy()
    expect(container.querySelector('.oc-status-chip-green')).toBeTruthy()
  })

  it('uses a spacer instead of chevron for leaves', () => {
    const { container } = render(
      <TreeNodeRow node={NODE} depth={0} isExpanded={false} isSelected={false} isLoading={false} hasError={false} showChevron={false} onToggle={() => {}} onSelect={() => {}} />,
    )
    expect(screen.queryByRole('button', { name: '展开' })).toBeNull()
    expect(container.querySelector('.oc-tree-chevron-spacer')).toBeTruthy()
  })

  it('renders bold class for entity roots', () => {
    const rootNode: OntologyTreeNode = {
      id: 'root:region',
      code: null,
      name: 'Brain Region',
      entityType: 'region',
      isEntityRoot: true,
    }
    const { container } = render(
      <TreeNodeRow node={rootNode} depth={0} isExpanded={false} isSelected={false} isLoading={false} hasError={false} showChevron onToggle={() => {}} onSelect={() => {}} />,
    )
    expect(container.querySelector('.oc-tree-entity-root')).toBeTruthy()
  })

  it('renders group rows with count badge and no status/level chips', () => {
    const groupNode: OntologyTreeNode = {
      id: 'group:connection:structural',
      code: null,
      name: 'Structural',
      entityType: 'connection',
      isGroup: true,
      hasChildren: true,
      children: [
        { id: 'c-1', code: 'ng:cn:a_to_b', name: 'a → b', entityType: 'connection', hasChildren: false },
        { id: 'c-2', code: 'ng:cn:c_to_d', name: 'c → d', entityType: 'connection', hasChildren: false },
      ],
    }
    const { container } = render(
      <TreeNodeRow node={groupNode} depth={1} isExpanded={false} isSelected={false} isLoading={false} hasError={false} showChevron onToggle={() => {}} onSelect={() => {}} />,
    )

    expect(container.querySelector('.oc-tree-row-group')).toBeTruthy()
    expect(container.querySelector('.oc-tree-group-count')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy()
    expect(container.querySelector('.oc-status-chip')).toBeNull()
    expect(container.querySelector('.oc-badge-level')).toBeNull()
  })
})
