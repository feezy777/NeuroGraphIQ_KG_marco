import { describe, expect, it } from 'vitest'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode } from './adapters/finalKgAdapter'
import { connectionLabelsOf, toXyflowNodes } from './graphToXyflow'

function makeNode(id: string, type: CanonicalNode['type'], label: string): CanonicalNode {
  return {
    id,
    type,
    label,
    entityId: id.split(':')[1] ?? id,
    metadata: { canonical_id: null, source_id: null, provenance: {}, granularity: null, confidence: null, raw: {} },
  }
}

function makeEdge(id: string, type: string, source: string, target: string): CanonicalEdge {
  return {
    id,
    source,
    target,
    type,
    label: null,
    metadata: { predicate: type, source: null, confidence: null, raw: {} },
  }
}

function makeGraph(nodes: CanonicalNode[], edges: CanonicalEdge[]): CanonicalGraph {
  return { nodes, edges, centerNodeId: null, warnings: [] }
}

describe('connectionLabelsOf（Phase 4 连接卡片标签派生）', () => {
  it('由 projection_source / projection_target 邻接脑区名组成 "source → target"', () => {
    const graph = makeGraph(
      [
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('region:r2', 'brain_region', 'Amygdala'),
        makeNode('projection:p1', 'connection', 'unknown_type'),
      ],
      [
        makeEdge('e1', 'projection_source', 'region:r1', 'projection:p1'),
        makeEdge('e2', 'projection_target', 'projection:p1', 'region:r2'),
      ],
    )
    expect(connectionLabelsOf(graph).get('projection:p1')).toBe('Hippocampus → Amygdala')
  })

  it('缺一侧时用 "?" 占位', () => {
    const graph = makeGraph(
      [makeNode('region:r1', 'brain_region', 'Hippocampus'), makeNode('projection:p1', 'connection', 't')],
      [makeEdge('e1', 'projection_source', 'region:r1', 'projection:p1')],
    )
    expect(connectionLabelsOf(graph).get('projection:p1')).toBe('Hippocampus → ?')
  })

  it('两侧都缺时不产生条目（视图回退到节点 label）', () => {
    const graph = makeGraph([makeNode('projection:p1', 'connection', 't')], [])
    expect(connectionLabelsOf(graph).has('projection:p1')).toBe(false)
  })

  it('非连接节点不产生条目', () => {
    const graph = makeGraph([makeNode('region:r1', 'brain_region', 'Hippocampus')], [])
    expect(connectionLabelsOf(graph).size).toBe(0)
  })

  it('toXyflowNodes 将派生标签写入 data.connectionLabel', () => {
    const graph = makeGraph(
      [
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('region:r2', 'brain_region', 'Amygdala'),
        makeNode('projection:p1', 'connection', 't'),
      ],
      [
        makeEdge('e1', 'projection_source', 'region:r1', 'projection:p1'),
        makeEdge('e2', 'projection_target', 'projection:p1', 'region:r2'),
      ],
    )
    const nodes = toXyflowNodes(graph, new Map())
    const connection = nodes.find(n => n.id === 'projection:p1')
    expect((connection?.data as Record<string, unknown>).connectionLabel).toBe('Hippocampus → Amygdala')
  })
})
