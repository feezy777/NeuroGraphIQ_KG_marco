import { describe, expect, it } from 'vitest'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode, CanonicalNodeType } from './adapters/finalKgAdapter'
import { emptyDisplayFilters, filterCanonicalGraph, toggleSetValue, type DisplayFilters } from './graphFilter'

function makeNode(id: string, type: CanonicalNode['type'], granularity: string | null = null): CanonicalNode {
  return {
    id,
    type,
    label: id,
    entityId: id.split(':')[1] ?? id,
    metadata: {
      canonical_id: null,
      source_id: null,
      provenance: {},
      granularity,
      confidence: null,
      raw: {},
    },
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

function makeGraph(): CanonicalGraph {
  return {
    nodes: [
      makeNode('region:r1', 'brain_region', 'macro'),
      makeNode('region:r2', 'brain_region', null),
      makeNode('projection:p1', 'connection'),
      makeNode('circuit:c1', 'circuit'),
      makeNode('region_function:f1', 'function'),
      makeNode('evidence:v1', 'evidence'),
    ],
    edges: [
      makeEdge('e1', 'projection_source', 'region:r1', 'projection:p1'),
      makeEdge('e2', 'participates_in', 'region:r1', 'circuit:c1'),
      makeEdge('e3', 'has_function', 'region:r1', 'region_function:f1'),
      makeEdge('e4', 'has_evidence', 'region:r2', 'evidence:v1'),
    ],
    centerNodeId: 'region:r1',
    warnings: ['w1'],
  }
}

function withFilters(patch: Partial<DisplayFilters>): DisplayFilters {
  return { ...emptyDisplayFilters(), ...patch }
}

describe('filterCanonicalGraph（Phase 7 前端展示过滤）', () => {
  it('空过滤条件 → 全量透传', () => {
    const graph = makeGraph()
    const out = filterCanonicalGraph(graph, emptyDisplayFilters())
    expect(out.nodes).toHaveLength(6)
    expect(out.edges).toHaveLength(4)
    expect(out.centerNodeId).toBe('region:r1')
  })

  it('实体类型过滤：只保留选中类型节点及其边', () => {
    const graph = makeGraph()
    // connection 单独过滤时所有边都连着被隐藏的 region，此处用双类型验证"两端可见的边保留"
    const out = filterCanonicalGraph(
      graph,
      withFilters({ entityTypes: new Set<CanonicalNodeType>(['brain_region', 'connection']) }),
    )
    expect(out.nodes.map(n => n.id)).toEqual(['region:r1', 'region:r2', 'projection:p1'])
    expect(out.edges.map(e => e.id)).toEqual(['e1'])
  })

  it('实体过滤后悬空边被移除（边端点不可见）', () => {
    const graph = makeGraph()
    const out = filterCanonicalGraph(graph, withFilters({ entityTypes: new Set<CanonicalNodeType>(['brain_region']) }))
    expect(out.nodes.map(n => n.id)).toEqual(['region:r1', 'region:r2'])
    expect(out.edges).toHaveLength(0)
  })

  it('粒度过滤：匹配的保留，不匹配的隐藏，未知粒度保留（不假装知道）', () => {
    const graph = makeGraph()
    const out = filterCanonicalGraph(graph, withFilters({ granularity: 'macro' }))
    // r1 匹配；r2 未知粒度保留；其余节点无粒度 → 全部保留
    expect(out.nodes.map(n => n.id)).toEqual([
      'region:r1',
      'region:r2',
      'projection:p1',
      'circuit:c1',
      'region_function:f1',
      'evidence:v1',
    ])
    const outMeso = filterCanonicalGraph(graph, withFilters({ granularity: 'meso' }))
    expect(outMeso.nodes.map(n => n.id).includes('region:r1')).toBe(false)
    expect(outMeso.nodes.map(n => n.id).includes('region:r2')).toBe(true)
  })

  it('关系分组过滤：按 relationGroupOf 隐藏边，节点保留', () => {
    const graph = makeGraph()
    const out = filterCanonicalGraph(graph, withFilters({ relationGroups: new Set(['has_function']) }))
    expect(out.nodes).toHaveLength(6)
    expect(out.edges.map(e => e.id)).toEqual(['e3'])
  })

  it('组合过滤：实体 + 关系同时生效', () => {
    const graph = makeGraph()
    const out = filterCanonicalGraph(
      graph,
      withFilters({
        entityTypes: new Set<CanonicalNodeType>(['brain_region', 'connection']),
        relationGroups: new Set(['structural']),
      }),
    )
    expect(out.nodes.map(n => n.id).sort()).toEqual(['projection:p1', 'region:r1', 'region:r2'])
    expect(out.edges.map(e => e.id)).toEqual(['e1'])
  })

  it('toggleSetValue 不可变：原 Set 不变，返回新 Set', () => {
    const original = new Set(['a'])
    const toggled = toggleSetValue(original, 'b')
    expect(original.has('b')).toBe(false)
    expect(toggled.has('b')).toBe(true)
    expect(toggleSetValue(toggled, 'a').has('a')).toBe(false)
  })
})
