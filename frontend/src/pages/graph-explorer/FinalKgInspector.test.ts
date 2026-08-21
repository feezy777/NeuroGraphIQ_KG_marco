import { describe, expect, it } from 'vitest'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode } from './adapters/finalKgAdapter'
import { directionalityOf, relationSectionsOf } from './FinalKgInspector'

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

function sectionsOf(graph: CanonicalGraph, node: CanonicalNode) {
  return relationSectionsOf(graph, node).map(s => ({ key: s.key, items: s.items.map(i => i.ref.id) }))
}

describe('relationSectionsOf（Phase 5 Inspector 关系派生）', () => {
  it('Region：派生 Connections / Circuits / Functions 三组', () => {
    const graph = makeGraph(
      [
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('projection:p1', 'connection', 'associative'),
        makeNode('circuit:c1', 'circuit', 'Papez'),
        makeNode('region_function:f1', 'function', 'Memory'),
      ],
      [
        makeEdge('e1', 'projection_source', 'region:r1', 'projection:p1'),
        makeEdge('e2', 'participates_in', 'region:r1', 'circuit:c1'),
        makeEdge('e3', 'has_function', 'region:r1', 'region_function:f1'),
      ],
    )
    const sections = sectionsOf(graph, graph.nodes[0])
    expect(sections).toEqual([
      { key: 'connections', items: ['projection:p1'] },
      { key: 'circuits', items: ['circuit:c1'] },
      { key: 'functions', items: ['region_function:f1'] },
    ])
  })

  it('Region：同一条投影同时有 source/target 边时合并去重', () => {
    const graph = makeGraph(
      [
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('region:r2', 'brain_region', 'Amygdala'),
        makeNode('projection:p1', 'connection', 'associative'),
      ],
      [
        makeEdge('e1', 'projection_source', 'region:r1', 'projection:p1'),
        makeEdge('e2', 'projection_target', 'projection:p1', 'region:r2'),
        makeEdge('e3', 'projection_target', 'projection:p1', 'region:r1'),
      ],
    )
    const sections = sectionsOf(graph, graph.nodes[0])
    expect(sections[0].items).toEqual(['projection:p1'])
  })

  it('Connection：派生 Source / Target 区域与方向性', () => {
    const graph = makeGraph(
      [
        makeNode('projection:p1', 'connection', 'associative'),
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('region:r2', 'brain_region', 'Amygdala'),
      ],
      [
        makeEdge('e1', 'projection_source', 'region:r1', 'projection:p1'),
        makeEdge('e2', 'projection_target', 'projection:p1', 'region:r2'),
      ],
    )
    expect(directionalityOf(graph, graph.nodes[0])).toBe('Directed（source → target）')
    expect(sectionsOf(graph, graph.nodes[0])).toEqual([
      { key: 'source', items: ['region:r1'] },
      { key: 'target', items: ['region:r2'] },
    ])
  })

  it('Connection：缺 target 边 → Partial（仅 source）', () => {
    const graph = makeGraph(
      [makeNode('projection:p1', 'connection', 't'), makeNode('region:r1', 'brain_region', 'H')],
      [makeEdge('e1', 'projection_source', 'region:r1', 'projection:p1')],
    )
    expect(directionalityOf(graph, graph.nodes[0])).toBe('Partial（仅 source）')
  })

  it('Circuit：Regions 含 participates_in 与 step_region 两个来源，Connections/Functions 分组', () => {
    const graph = makeGraph(
      [
        makeNode('circuit:c1', 'circuit', 'Papez'),
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('circuit_step:s1', 'circuit_step', 'Step 1'),
        makeNode('region:r2', 'brain_region', 'Mammillary'),
        makeNode('projection:p1', 'connection', 'associative'),
        makeNode('circuit_function:f1', 'function', 'Memory'),
      ],
      [
        makeEdge('e1', 'participates_in', 'region:r1', 'circuit:c1'),
        makeEdge('e2', 'contains_step', 'circuit:c1', 'circuit_step:s1'),
        makeEdge('e3', 'step_region', 'circuit_step:s1', 'region:r2'),
        makeEdge('e4', 'circuit_contains_projection', 'circuit:c1', 'projection:p1'),
        makeEdge('e5', 'has_function', 'circuit:c1', 'circuit_function:f1'),
      ],
    )
    expect(sectionsOf(graph, graph.nodes[0])).toEqual([
      { key: 'regions', items: ['region:r1', 'region:r2'] },
      { key: 'connections', items: ['projection:p1'] },
      { key: 'functions', items: ['circuit_function:f1'] },
    ])
  })

  it('Function：Related Entities = has_function 边的源端（region/projection/circuit）', () => {
    const graph = makeGraph(
      [
        makeNode('region_function:f1', 'function', 'Memory'),
        makeNode('region:r1', 'brain_region', 'Hippocampus'),
        makeNode('projection:p1', 'connection', 'associative'),
      ],
      [
        makeEdge('e1', 'has_function', 'region:r1', 'region_function:f1'),
        makeEdge('e2', 'has_function', 'projection:p1', 'region_function:f1'),
      ],
    )
    expect(sectionsOf(graph, graph.nodes[0])).toEqual([
      { key: 'related', items: ['region:r1', 'projection:p1'] },
    ])
  })

  it('Circuit Step：At Region 来自 step_region 边', () => {
    const graph = makeGraph(
      [makeNode('circuit_step:s1', 'circuit_step', 'Step 1'), makeNode('region:r1', 'brain_region', 'H')],
      [makeEdge('e1', 'step_region', 'circuit_step:s1', 'region:r1')],
    )
    expect(sectionsOf(graph, graph.nodes[0])).toEqual([{ key: 'region', items: ['region:r1'] }])
  })

  it('Evidence / 无关联节点 → 无关系分组', () => {
    const graph = makeGraph([makeNode('evidence:v1', 'evidence', 'text')], [])
    expect(relationSectionsOf(graph, graph.nodes[0])).toEqual([])
  })
})
