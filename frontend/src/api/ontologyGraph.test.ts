import { describe, expect, it } from 'vitest'
import { buildGraph, toGraphNode } from './ontologyGraph'
import type { EntityDetailData, RelationGroup } from '../pages/ontology-center/detail/types'

const CENTER: EntityDetailData = {
  entityType: 'region',
  id: 'r-brain',
  name: 'Brain',
  code: 'ng:br:brain',
  status: 'active',
  granularityLevel: 'whole_brain',
  confidence: 0.95,
  description: null,
  basic: [],
  path: [{ id: 'r-brain', code: 'ng:br:brain', name: 'Brain', entityType: 'region' }],
  parent: null,
  children: [],
  provenance: [],
}

describe('toGraphNode', () => {
  it('maps an EntityRef to a GraphNode', () => {
    expect(
      toGraphNode({ id: 'r-brain', code: 'ng:br:brain', name: 'Brain', entityType: 'region' }),
    ).toEqual({ id: 'r-brain', type: 'region', label: 'Brain', code: 'ng:br:brain' })
  })
})

describe('buildGraph', () => {
  it('builds deduplicated nodes and edges from center + relations', () => {
    const relations: RelationGroup[] = [
      {
        key: 'children',
        label: '子节点',
        items: [
          { ref: { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' }, meta: [] },
        ],
      },
      {
        key: 'connections',
        label: 'Related Connections',
        items: [
          { ref: { id: 'r-thalamus', code: null, name: 'Thalamus', entityType: 'region' }, meta: [] },
        ],
      },
    ]

    const { nodes, edges } = buildGraph(CENTER, relations)

    expect(nodes).toHaveLength(3)
    expect(nodes.map(n => n.id).sort()).toEqual(['r-brain', 'r-cerebrum', 'r-thalamus'])
    expect(edges).toEqual([
      { id: 'r-brain->r-cerebrum:children', source: 'r-brain', target: 'r-cerebrum', relationType: '子节点' },
      { id: 'r-brain->r-thalamus:connections', source: 'r-brain', target: 'r-thalamus', relationType: 'Related Connections' },
    ])
  })

  it('deduplicates a node referenced by multiple groups', () => {
    const relations: RelationGroup[] = [
      {
        key: 'children',
        label: '子节点',
        items: [
          { ref: { id: 'r-cerebrum', code: null, name: 'Cerebrum', entityType: 'region' }, meta: [] },
        ],
      },
      {
        key: 'circuits',
        label: 'Related Circuits',
        items: [
          { ref: { id: 'r-cerebrum', code: null, name: 'Cerebrum', entityType: 'region' }, meta: [] },
        ],
      },
    ]

    const { nodes, edges } = buildGraph(CENTER, relations)

    expect(nodes).toHaveLength(2)
    expect(edges).toHaveLength(2)
  })

  it('excludes unavailable groups (no fake relations in the graph)', () => {
    const relations: RelationGroup[] = [
      { key: 'circuits', label: 'Related Circuits', unavailable: true, items: [] },
    ]

    const { nodes, edges } = buildGraph(CENTER, relations)

    expect(nodes).toHaveLength(1)
    expect(edges).toEqual([])
  })

  it('keeps center node even when all relation groups are empty', () => {
    const { nodes, edges } = buildGraph(CENTER, [])

    expect(nodes).toEqual([
      { id: 'r-brain', type: 'region', label: 'Brain', code: 'ng:br:brain' },
    ])
    expect(edges).toEqual([])
  })
})
