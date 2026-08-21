import { describe, expect, it } from 'vitest'
import type { CanonicalGraph, CanonicalNode } from './finalKgAdapter'
import { mergeCanonicalGraphs } from './finalKgAdapter'

function makeNode(id: string, type: CanonicalNode['type'], label: string): CanonicalNode {
  return {
    id,
    type,
    label,
    entityId: id.split(':')[1] ?? id,
    metadata: { canonical_id: null, source_id: null, provenance: {}, granularity: null, confidence: null, raw: {} },
  }
}

function graph(nodes: CanonicalNode[], edges: { id: string; type: string; source: string; target: string }[], centerNodeId: string | null = null, warnings: string[] = []): CanonicalGraph {
  return {
    nodes,
    edges: edges.map(e => ({ ...e, label: null, metadata: { predicate: e.type, source: null, confidence: null, raw: {} } })),
    centerNodeId,
    warnings,
  }
}

describe('mergeCanonicalGraphs（Phase 6 增量展开合并）', () => {
  it('合并新增节点与边：Hippocampus 先 Region+Connection，再展开补 Circuit+Function', () => {
    const base = graph(
      [
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('projection:p1', 'connection', 'associative'),
      ],
      [{ id: 'e1', type: 'projection_source', source: 'region:r1', target: 'projection:p1' }],
      'region:r1',
    )
    const incoming = graph(
      [
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('circuit:c1', 'circuit', 'Papez'),
        makeNode('region_function:f1', 'function', 'Memory'),
      ],
      [
        { id: 'e1', type: 'projection_source', source: 'region:r1', target: 'projection:p1' },
        { id: 'e2', type: 'participates_in', source: 'region:r1', target: 'circuit:c1' },
        { id: 'e3', type: 'has_function', source: 'region:r1', target: 'region_function:f1' },
      ],
      'region:r1',
    )
    const merged = mergeCanonicalGraphs(base, incoming)
    expect(merged.nodes.map(n => n.id).sort()).toEqual(['circuit:c1', 'projection:p1', 'region:r1', 'region_function:f1'])
    expect(merged.edges.map(e => e.id).sort()).toEqual(['e1', 'e2', 'e3'])
  })

  it('已存在节点保留原数据（不被 incoming 覆盖）', () => {
    const base = graph([makeNode('region:r1', 'brain_region', 'Original name')], [])
    const incoming = graph([makeNode('region:r1', 'brain_region', 'Renamed')], [])
    const merged = mergeCanonicalGraphs(base, incoming)
    expect(merged.nodes).toHaveLength(1)
    expect(merged.nodes[0].label).toBe('Original name')
  })

  it('centerNodeId 保留 base 中心（布局锚点不变）', () => {
    const base = graph([makeNode('region:r1', 'brain_region', 'H')], [], 'region:r1')
    const incoming = graph([makeNode('circuit:c1', 'circuit', 'Papez')], [], 'circuit:c1')
    expect(mergeCanonicalGraphs(base, incoming).centerNodeId).toBe('region:r1')
  })

  it('warnings 合并去重', () => {
    const base = graph([], [], null, ['w1'])
    const incoming = graph([], [], null, ['w1', 'w2'])
    expect(mergeCanonicalGraphs(base, incoming).warnings).toEqual(['w1', 'w2'])
  })

  it('纯函数：不修改输入图', () => {
    const base = graph([makeNode('region:r1', 'brain_region', 'H')], [])
    const incoming = graph([makeNode('circuit:c1', 'circuit', 'Papez')], [])
    mergeCanonicalGraphs(base, incoming)
    expect(base.nodes).toHaveLength(1)
    expect(incoming.nodes).toHaveLength(1)
  })

  it('空图合并 incoming 时保留 incoming 数据、中心为 base 中心', () => {
    const base = graph([], [])
    const incoming = graph([makeNode('region:r1', 'brain_region', 'H')], [], 'region:r1')
    const merged = mergeCanonicalGraphs(base, incoming)
    expect(merged.nodes).toHaveLength(1)
    expect(merged.centerNodeId).toBeNull()
  })
})
