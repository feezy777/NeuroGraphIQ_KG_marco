import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { OntologyTree } from './OntologyTree'
import type { OntologyTreeNode } from './OntologyTreeNode'

const ROOT: OntologyTreeNode = {
  id: 'root:region',
  code: null,
  name: 'Brain Region',
  entityType: 'region',
  isEntityRoot: true,
}
const BRAIN: OntologyTreeNode = {
  id: 'r-brain',
  code: 'ng:br:brain',
  name: 'Brain',
  entityType: 'region',
  granularityLevel: 'whole_brain',
}
const CEREBRUM: OntologyTreeNode = {
  id: 'r-cerebrum',
  code: 'ng:br:cerebrum',
  name: 'Cerebrum',
  entityType: 'region',
  granularityLevel: 'macro',
}

function setupTree({
  roots = [ROOT],
  children = [BRAIN],
  selectedId = null,
}: {
  roots?: OntologyTreeNode[]
  children?: OntologyTreeNode[]
  selectedId?: string | null
} = {}) {
  const getChildren = vi.fn().mockResolvedValue(children)
  const onSelect = vi.fn()
  const { container } = render(
    <OntologyTree roots={roots} getChildren={getChildren} onSelect={onSelect} selectedId={selectedId} />,
  )
  return { getChildren, onSelect, container }
}

describe('OntologyTree', () => {
  it('renders root nodes and auto-loads default-expanded children on mount', async () => {
    const { getChildren } = setupTree()
    expect(screen.getByText('Brain Region')).toBeTruthy()
    expect(await screen.findByText('Brain')).toBeTruthy()
    expect(getChildren).toHaveBeenCalledTimes(1)
  })

  it('collapses and re-expands from cache without a second fetch', async () => {
    const { getChildren } = setupTree()
    await screen.findByText('Brain')

    fireEvent.click(screen.getByRole('button', { name: '收起' }))
    expect(screen.queryByText('Brain')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '展开' }))
    expect(await screen.findByText('Brain')).toBeTruthy()
    expect(getChildren).toHaveBeenCalledTimes(1)
  })

  it('hides chevron when loaded children are empty (leaf)', async () => {
    setupTree({ children: [] })
    await screen.findByText('Brain Region')
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '展开' })).toBeNull(),
    )
  })

  it('never loads children for hasChildren=false leaves', async () => {
    const leaf: OntologyTreeNode = {
      id: 'cn-1',
      code: 'ng:cn:x',
      name: 'X',
      entityType: 'connection',
      hasChildren: false,
    }
    const getChildren = vi.fn()
    render(
      <OntologyTree roots={[leaf]} getChildren={getChildren} onSelect={vi.fn()} selectedId={null} />,
    )
    expect(screen.getByText('X')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '展开' })).toBeNull()
    expect(getChildren).not.toHaveBeenCalled()
  })

  it('highlights the controlled selected row', async () => {
    setupTree({ selectedId: 'r-brain' })
    const row = (await screen.findByText('Brain')).closest('.oc-tree-row')
    expect(row?.className).toContain('oc-tree-row-selected')
  })

  it('calls onSelect with the node when a selectable row is clicked', async () => {
    const onSelect = vi.fn()
    render(
      <OntologyTree
        roots={[BRAIN]}
        getChildren={vi.fn().mockResolvedValue([])}
        onSelect={onSelect}
        selectedId={null}
      />,
    )
    fireEvent.click(screen.getByText('Brain'))
    expect(onSelect).toHaveBeenCalledWith(BRAIN)
  })

  it('entity root click toggles instead of calling onSelect', async () => {
    const { onSelect } = setupTree()
    await screen.findByText('Brain')

    fireEvent.click(screen.getByText('Brain Region'))
    expect(onSelect).not.toHaveBeenCalled()
    expect(screen.queryByText('Brain')).toBeNull()

    fireEvent.click(screen.getByText('Brain Region'))
    expect(await screen.findByText('Brain')).toBeTruthy()
  })

  it('shows 加载失败 on fetch error and retries on re-expand', async () => {
    const getChildren = vi
      .fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce([BRAIN])
    const onSelect = vi.fn()
    render(
      <OntologyTree roots={[ROOT]} getChildren={getChildren} onSelect={onSelect} selectedId={null} />,
    )

    expect(await screen.findByText('加载失败')).toBeTruthy()

    // 收起 → 再展开 = 清错误 + 重试
    fireEvent.click(screen.getByRole('button', { name: '收起' }))
    fireEvent.click(screen.getByRole('button', { name: '展开' }))
    expect(await screen.findByText('Brain')).toBeTruthy()
    expect(screen.queryByText('加载失败')).toBeNull()
    expect(getChildren).toHaveBeenCalledTimes(2)
  })

  it('shows nested children indented below an expanded region', async () => {
    const getChildren = vi
      .fn()
      .mockResolvedValueOnce([BRAIN])
      .mockResolvedValueOnce([CEREBRUM])
    const onSelect = vi.fn()
    render(
      <OntologyTree roots={[ROOT]} getChildren={getChildren} onSelect={onSelect} selectedId={null} />,
    )

    await screen.findByText('Brain')
    fireEvent.click(screen.getByRole('button', { name: '展开' }))
    expect(await screen.findByText('Cerebrum')).toBeTruthy()
    expect(getChildren).toHaveBeenCalledTimes(2)
  })

  it('cascades auto-expand through autoExpandLevels and stops at the first level outside them', async () => {
    const HIPPOCAMPUS: OntologyTreeNode = {
      id: 'r-hippocampus',
      code: 'ng:br:hippocampus',
      name: 'Hippocampus',
      entityType: 'region',
      granularityLevel: 'clinical',
    }
    const FORMATION: OntologyTreeNode = {
      id: 'r-hippocampal-formation',
      code: 'ng:br:hippocampal_formation',
      name: 'Hippocampal formation',
      entityType: 'region',
      granularityLevel: 'meso',
    }
    const CA1: OntologyTreeNode = {
      id: 'r-ca1',
      code: 'ng:br:ca1',
      name: 'CA1',
      entityType: 'region',
      granularityLevel: 'fine',
    }
    const getChildren = vi.fn(async (node: OntologyTreeNode) => {
      if (node.id === 'root:region') return [BRAIN]
      if (node.id === 'r-brain') return [CEREBRUM]
      if (node.id === 'r-cerebrum') return [HIPPOCAMPUS]
      if (node.id === 'r-hippocampus') return [FORMATION]
      if (node.id === 'r-hippocampal-formation') return [CA1]
      return []
    })
    render(
      <OntologyTree
        roots={[ROOT]}
        getChildren={getChildren}
        onSelect={vi.fn()}
        selectedId={null}
        autoExpandLevels={['whole_brain', 'macro', 'clinical']}
      />,
    )

    // 级联自动展开到 clinical；meso 行可见（父已展开）但自身折叠
    expect(await screen.findByText('Hippocampus')).toBeTruthy()
    expect(screen.getByText('Hippocampal formation')).toBeTruthy()
    expect(getChildren).toHaveBeenCalledTimes(4) // root + brain + cerebrum + hippocampus
    expect(screen.queryByText('CA1')).toBeNull()

    // 手动展开 meso → 下一级 fine 加载
    const formationRow = screen.getByText('Hippocampal formation').closest('.oc-tree-row') as HTMLElement
    fireEvent.click(within(formationRow).getByRole('button', { name: '展开' }))
    expect(await screen.findByText('CA1')).toBeTruthy()
    expect(getChildren).toHaveBeenCalledTimes(5)
  })

  it('auto-expands meso branches in mesoAutoExpandIds using preloaded children without a fetch', async () => {
    const HIPPOCAMPUS: OntologyTreeNode = {
      id: 'r-hippocampus',
      code: 'ng:br:hippocampus',
      name: 'Hippocampus',
      entityType: 'region',
      granularityLevel: 'clinical',
    }
    const FORMATION: OntologyTreeNode = {
      id: 'r-hippocampal-formation',
      code: 'ng:br:hippocampal_formation',
      name: 'Hippocampal formation',
      entityType: 'region',
      granularityLevel: 'meso',
    }
    const CA1: OntologyTreeNode = {
      id: 'r-ca1',
      code: 'ng:br:ca1',
      name: 'CA1',
      entityType: 'region',
      granularityLevel: 'fine',
    }
    const getChildren = vi.fn(async (node: OntologyTreeNode) => {
      if (node.id === 'root:region') return [BRAIN]
      if (node.id === 'r-brain') return [CEREBRUM]
      if (node.id === 'r-cerebrum') return [HIPPOCAMPUS]
      if (node.id === 'r-hippocampus') return [FORMATION]
      return []
    })
    render(
      <OntologyTree
        roots={[ROOT]}
        getChildren={getChildren}
        onSelect={vi.fn()}
        selectedId={null}
        autoExpandLevels={['whole_brain', 'macro', 'clinical']}
        mesoAutoExpandIds={new Set(['r-hippocampal-formation'])}
        preloadedChildren={{ 'r-hippocampal-formation': [CA1] }}
        childCountById={{ 'r-hippocampal-formation': 1 }}
      />,
    )

    // meso 小分支自动展开直达 fine（无点击）；预加载命中 → 无 formation 请求
    expect(await screen.findByText('CA1')).toBeTruthy()
    expect(getChildren).toHaveBeenCalledTimes(4) // root + brain + cerebrum + hippocampus
  })

  it('shows the (n) child-count badge from childCountById on a collapsed node', async () => {
    const FORMATION: OntologyTreeNode = {
      id: 'r-hippocampal-formation',
      code: 'ng:br:hippocampal_formation',
      name: 'Hippocampal formation',
      entityType: 'region',
      granularityLevel: 'meso',
    }
    const getChildren = vi.fn().mockResolvedValue([FORMATION])
    render(
      <OntologyTree
        roots={[ROOT]}
        getChildren={getChildren}
        onSelect={vi.fn()}
        selectedId={null}
        childCountById={{ 'r-hippocampal-formation': 360 }}
      />,
    )

    const formationRow = (await screen.findByText('Hippocampal formation')).closest(
      '.oc-tree-row',
    ) as HTMLElement
    expect(within(formationRow).getByText('(360)')).toBeTruthy()
    expect(getChildren).toHaveBeenCalledTimes(1) // 折叠不加载
  })

  it('renders fine nodes as leaves: no chevron and never probed', async () => {
    const AREA4: OntologyTreeNode = {
      id: 'r-area4',
      code: 'ng:br:area4',
      name: 'Area 4',
      entityType: 'region',
      granularityLevel: 'fine',
    }
    const getChildren = vi.fn().mockResolvedValue([AREA4])
    render(
      <OntologyTree roots={[ROOT]} getChildren={getChildren} onSelect={vi.fn()} selectedId={null} />,
    )

    const areaRow = (await screen.findByText('Area 4')).closest('.oc-tree-row') as HTMLElement
    expect(within(areaRow).queryByRole('button', { name: '展开' })).toBeNull()
    expect(getChildren).toHaveBeenCalledTimes(1) // 仅根节点；fine 叶子从不探测
  })

  it('expands the full chain down to research level when 展开到研究层级 is clicked', async () => {
    const HIPPOCAMPUS: OntologyTreeNode = {
      id: 'r-hippocampus',
      code: 'ng:br:hippocampus',
      name: 'Hippocampus',
      entityType: 'region',
      granularityLevel: 'clinical',
    }
    const FORMATION: OntologyTreeNode = {
      id: 'r-hippocampal-formation',
      code: 'ng:br:hippocampal_formation',
      name: 'Hippocampal formation',
      entityType: 'region',
      granularityLevel: 'meso',
    }
    const CA1: OntologyTreeNode = {
      id: 'r-ca1',
      code: 'ng:br:ca1',
      name: 'CA1',
      entityType: 'region',
      granularityLevel: 'fine',
    }
    const getChildren = vi.fn(async (node: OntologyTreeNode) => {
      if (node.id === 'root:region') return [BRAIN]
      if (node.id === 'r-brain') return [CEREBRUM]
      if (node.id === 'r-cerebrum') return [HIPPOCAMPUS]
      if (node.id === 'r-hippocampus') return [FORMATION]
      if (node.id === 'r-hippocampal-formation') return [CA1]
      return []
    })
    render(
      <OntologyTree
        roots={[ROOT]}
        getChildren={getChildren}
        onSelect={vi.fn()}
        selectedId={null}
        autoExpandLevels={['whole_brain', 'macro']}
        researchExpandIds={['r-hippocampal-formation']}
        researchAncestorIds={['r-brain', 'r-cerebrum', 'r-hippocampus']}
      />,
    )

    // 级联止于 macro：clinical 折叠，meso 目标尚未进入节点索引
    expect(await screen.findByText('Hippocampus')).toBeTruthy()
    expect(screen.queryByText('Hippocampal formation')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '展开到研究层级' }))

    // 迭代扫描：clinical 祖先 → 研究目标 meso → fine 全部展开
    expect(await screen.findByText('CA1')).toBeTruthy()
    expect(getChildren).toHaveBeenCalledTimes(5) // root + brain + cerebrum + hippocampus + formation
  })
})
