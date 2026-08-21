import { describe, expect, it } from 'vitest'
import type { FinalGraphResponse } from '../../../api/endpoints'
import {
  adaptFinalGraphResponse,
  canExpandNode,
  expandRequestForNode,
  nodeBackendType,
  parseNodeId,
  relationGroupOf,
} from './finalKgAdapter'

// ─── fixtures：覆盖后端全部节点/边类型 ──────────────────────────────────────

function makeResponse(): FinalGraphResponse {
  return {
    nodes: [
      {
        id: 'region:r-1',
        type: 'region',
        label: 'Hippocampus',
        final_id: 'fin-reg-1',
        source_mirror_id: 'mir-1',
        metadata: {
          source_atlas: 'AAL3',
          granularity_level: 'macro',
          granularity_family: 'macro_clinical',
          confidence: 0.9,
        },
      },
      {
        id: 'region_function:rf-1',
        type: 'region_function',
        label: 'Memory encoding',
        final_id: 'fin-rf-1',
        source_mirror_id: null,
        metadata: { confidence: '0.85' },
      },
      {
        id: 'circuit:ci-1',
        type: 'circuit',
        label: 'Papez circuit',
        final_id: 'fin-ci-1',
        source_mirror_id: 'mir-ci-1',
        metadata: {},
      },
      {
        id: 'circuit_step:cs-1',
        type: 'circuit_step',
        label: 'Step 1',
        final_id: null,
        source_mirror_id: null,
        metadata: {},
      },
      {
        id: 'projection:pj-1',
        type: 'projection',
        label: 'Hippocampus → Entorhinal',
        final_id: 'fin-pj-1',
        source_mirror_id: 'mir-pj-1',
        metadata: { confidence: 0.7 },
      },
      {
        id: 'projection_function:pf-1',
        type: 'projection_function',
        label: 'Spatial navigation',
        final_id: null,
        source_mirror_id: null,
        metadata: {},
      },
      {
        id: 'circuit_function:cf-1',
        type: 'circuit_function',
        label: 'Emotion regulation',
        final_id: null,
        source_mirror_id: null,
        metadata: {},
      },
      {
        id: 'evidence:ev-1',
        type: 'evidence',
        label: 'Evidence #1',
        final_id: null,
        source_mirror_id: null,
        metadata: {},
      },
    ],
    edges: [
      {
        id: 'edge:e1',
        type: 'has_function',
        source: 'region:r-1',
        target: 'region_function:rf-1',
        predicate: 'has_function',
        final_id: 'fin-edge-1',
        metadata: { confidence: 0.72 },
      },
      { id: 'edge:e2', type: 'participates_in', source: 'region:r-1', target: 'circuit:ci-1' },
      { id: 'edge:e3', type: 'contains_step', source: 'circuit:ci-1', target: 'circuit_step:cs-1' },
      { id: 'edge:e4', type: 'step_region', source: 'circuit_step:cs-1', target: 'region:r-1' },
      { id: 'edge:e5', type: 'projection_source', source: 'region:r-1', target: 'projection:pj-1' },
      { id: 'edge:e6', type: 'projection_target', source: 'projection:pj-1', target: 'region:r-1' },
      { id: 'edge:e7', type: 'circuit_contains_projection', source: 'circuit:ci-1', target: 'projection:pj-1' },
      { id: 'edge:e8', type: 'has_evidence', source: 'projection:pj-1', target: 'evidence:ev-1', predicate: 'has_evidence' },
      { id: 'edge:e9', type: 'has_function', source: 'projection:pj-1', target: 'projection_function:pf-1' },
      { id: 'edge:e10', type: 'has_function', source: 'circuit:ci-1', target: 'circuit_function:cf-1' },
      // 悬空边（节点不存在）应被丢弃
      { id: 'edge:e11', type: 'contains_projection', source: 'circuit:ci-1', target: 'projection:ghost' },
    ],
    center_node_id: 'region:r-1',
    warnings: ['demo warning'],
  }
}

// ─── 类型映射 ─────────────────────────────────────────────────────────────

describe('adaptFinalGraphResponse', () => {
  it('maps all backend node types to unified types', () => {
    const graph = adaptFinalGraphResponse(makeResponse())
    const byType = new Map(graph.nodes.map(n => [n.id, n.type]))
    expect(byType.get('region:r-1')).toBe('brain_region')
    expect(byType.get('region_function:rf-1')).toBe('function')
    expect(byType.get('circuit_function:cf-1')).toBe('function')
    expect(byType.get('projection_function:pf-1')).toBe('function')
    expect(byType.get('circuit:ci-1')).toBe('circuit')
    expect(byType.get('circuit_step:cs-1')).toBe('circuit_step')
    expect(byType.get('projection:pj-1')).toBe('connection')
    expect(byType.get('evidence:ev-1')).toBe('evidence')
  })

  it('extracts entityId from backend id format', () => {
    const graph = adaptFinalGraphResponse(makeResponse())
    const region = graph.nodes.find(n => n.id === 'region:r-1')
    expect(region?.entityId).toBe('r-1')
  })

  it('fills Phase 9 node metadata (canonical_id / source_id / provenance / granularity / confidence)', () => {
    const graph = adaptFinalGraphResponse(makeResponse())
    const region = graph.nodes.find(n => n.id === 'region:r-1')
    expect(region?.metadata.canonical_id).toBe('fin-reg-1')
    expect(region?.metadata.source_id).toBe('mir-1')
    expect(region?.metadata.provenance).toEqual({
      source_mirror_id: 'mir-1',
      source_atlas: 'AAL3',
      granularity_family: 'macro_clinical',
    })
    expect(region?.metadata.granularity).toBe('macro')
    expect(region?.metadata.confidence).toBe(0.9)
  })

  it('omits null provenance keys instead of writing explicit nulls', () => {
    const graph = adaptFinalGraphResponse(makeResponse())
    const cs = graph.nodes.find(n => n.id === 'circuit_step:cs-1')
    expect(cs?.metadata.provenance).toEqual({})
    expect(cs?.metadata.granularity).toBeNull()
  })

  it('parses string confidence and tolerates missing values', () => {
    const graph = adaptFinalGraphResponse(makeResponse())
    const rf = graph.nodes.find(n => n.id === 'region_function:rf-1')
    const cs = graph.nodes.find(n => n.id === 'circuit_step:cs-1')
    expect(rf?.metadata.confidence).toBe(0.85)
    expect(cs?.metadata.confidence).toBeNull()
    expect(cs?.metadata.canonical_id).toBeNull()
  })

  it('fills Phase 9 edge metadata (predicate / source / confidence)', () => {
    const graph = adaptFinalGraphResponse(makeResponse())
    const e1 = graph.edges.find(e => e.id === 'edge:e1')
    expect(e1?.metadata.predicate).toBe('has_function')
    // 溯源：晋升后正式 id（final_id）
    expect(e1?.metadata.source).toBe('fin-edge-1')
    expect(e1?.metadata.confidence).toBe(0.72)
    const e5 = graph.edges.find(e => e.id === 'edge:e5')
    // 后端无 predicate 字段时回退到 type；无 final_id / confidence 时置 null
    expect(e5?.metadata.predicate).toBe('projection_source')
    expect(e5?.metadata.source).toBeNull()
    expect(e5?.metadata.confidence).toBeNull()
  })

  it('drops dangling edges whose endpoints are missing', () => {
    const graph = adaptFinalGraphResponse(makeResponse())
    expect(graph.edges).toHaveLength(10)
    expect(graph.edges.some(e => e.id === 'edge:e11')).toBe(false)
  })

  it('passes through center_node_id and warnings', () => {
    const graph = adaptFinalGraphResponse(makeResponse())
    expect(graph.centerNodeId).toBe('region:r-1')
    expect(graph.warnings).toEqual(['demo warning'])
  })

  it('tolerates empty responses', () => {
    const graph = adaptFinalGraphResponse({ nodes: [], edges: [], center_node_id: null, warnings: [] })
    expect(graph.nodes).toEqual([])
    expect(graph.edges).toEqual([])
    expect(graph.centerNodeId).toBeNull()
  })

  it('falls back to brain_region and id label for unknown backend types / empty labels', () => {
    const graph = adaptFinalGraphResponse({
      nodes: [{ id: 'future:fx-1', type: 'future_type', label: '', metadata: {} }],
      edges: [],
      center_node_id: null,
    })
    const node = graph.nodes[0]
    expect(node.type).toBe('brain_region')
    expect(node.label).toBe('future:fx-1')
    expect(node.metadata.canonical_id).toBeNull()
  })

  it('is a pure function that never mutates the input response', () => {
    const input = makeResponse()
    const deepFreeze = (value: unknown): unknown => {
      if (value && typeof value === 'object') {
        Object.freeze(value)
        Object.values(value as Record<string, unknown>).forEach(deepFreeze)
      }
      return value
    }
    deepFreeze(input)
    // 若实现内部写入输入对象，严格模式下会抛 TypeError
    expect(() => adaptFinalGraphResponse(input)).not.toThrow()
    expect(input.nodes).toHaveLength(8)
    expect(input.edges).toHaveLength(11)
  })
})

// ─── id 解析与展开映射 ────────────────────────────────────────────────────

describe('parseNodeId', () => {
  it('splits backend type and entity id', () => {
    expect(parseNodeId('region:abc-123')).toEqual({ backendType: 'region', entityId: 'abc-123' })
  })

  it('returns null for ids without a colon', () => {
    expect(parseNodeId('regiononly')).toBeNull()
    expect(parseNodeId(':nokey')).toBeNull()
    expect(parseNodeId('key:')).toBeNull()
  })
})

describe('expand mapping', () => {
  const graph = adaptFinalGraphResponse(makeResponse())
  const node = (id: string) => graph.nodes.find(n => n.id === id)!

  it('maps expandable backend types to center_type', () => {
    expect(expandRequestForNode(node('region:r-1'))).toEqual({ center_type: 'region', center_id: 'r-1' })
    expect(expandRequestForNode(node('circuit:ci-1'))).toEqual({ center_type: 'circuit', center_id: 'ci-1' })
    expect(expandRequestForNode(node('projection:pj-1'))).toEqual({ center_type: 'projection', center_id: 'pj-1' })
    expect(expandRequestForNode(node('circuit_step:cs-1'))).toEqual({ center_type: 'circuit_step', center_id: 'cs-1' })
    expect(expandRequestForNode(node('projection_function:pf-1'))).toEqual({
      center_type: 'projection_function',
      center_id: 'pf-1',
    })
  })

  it('marks region_function / circuit_function / evidence as non-expandable', () => {
    expect(canExpandNode(node('region:r-1'))).toBe(true)
    expect(canExpandNode(node('region_function:rf-1'))).toBe(false)
    expect(canExpandNode(node('circuit_function:cf-1'))).toBe(false)
    expect(canExpandNode(node('evidence:ev-1'))).toBe(false)
    expect(expandRequestForNode(node('evidence:ev-1'))).toBeNull()
  })

  it('derives backend type from node id prefix', () => {
    expect(nodeBackendType(node('projection:pj-1'))).toBe('projection')
  })
})

// ─── 关系分组（Phase 7 过滤）──────────────────────────────────────────────

describe('relationGroupOf', () => {
  const graph = adaptFinalGraphResponse(makeResponse())
  const edge = (id: string) => graph.edges.find(e => e.id === id)!

  it('groups structural / has_function / participates_in / evidence', () => {
    expect(relationGroupOf(edge('edge:e5'))).toBe('structural')
    expect(relationGroupOf(edge('edge:e3'))).toBe('structural')
    expect(relationGroupOf(edge('edge:e1'))).toBe('has_function')
    expect(relationGroupOf(edge('edge:e2'))).toBe('participates_in')
    expect(relationGroupOf(edge('edge:e8'))).toBe('evidence')
  })
})
