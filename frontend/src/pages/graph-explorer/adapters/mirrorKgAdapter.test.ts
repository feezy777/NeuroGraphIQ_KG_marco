import { describe, expect, it } from 'vitest'
import type {
  CandidateBrainRegion,
  MirrorRegionCircuit,
  MirrorRegionConnection,
  MirrorRegionFunction,
} from '../../../api/endpoints'
import {
  adaptMirrorGraphResponse,
  canExpandMirrorNode,
  expandRequestForMirrorNode,
  type MirrorGraphSourceData,
} from './mirrorKgAdapter'
import type { CanonicalNode } from './finalKgAdapter'

// ─── fixtures ─────────────────────────────────────────────────────────────────

function makeCandidate(overrides: Partial<CandidateBrainRegion> = {}): CandidateBrainRegion {
  return {
    id: 'cand-1',
    generation_run_id: 'gen-1',
    batch_id: 'batch-1',
    resource_id: 'res-1',
    parse_run_id: 'parse-1',
    raw_name: 'Hippocampus_L',
    std_name: 'Hippocampus',
    en_name: 'Hippocampus',
    cn_name: '海马',
    laterality: 'left',
    granularity_level: 'macro',
    granularity_family: 'macro_clinical',
    source_atlas: 'AAL3',
    source_version: 'v1',
    candidate_status: 'candidate_created',
    created_at: '2026-08-21T00:00:00Z',
    updated_at: '2026-08-21T00:00:00Z',
    ...overrides,
  }
}

function makeConnection(overrides: Partial<MirrorRegionConnection> = {}): MirrorRegionConnection {
  return {
    id: 'conn-1',
    canonical_id: 'ng:conn:1',
    source_region_candidate_id: 'cand-1',
    target_region_candidate_id: 'cand-2',
    source_region_final_id: null,
    target_region_final_id: null,
    source_region_name_cn: '海马',
    source_region_name_en: 'Hippocampus',
    target_region_name_cn: '内嗅皮层',
    target_region_name_en: 'Entorhinal',
    resource_id: 'res-1',
    batch_id: 'batch-1',
    llm_run_id: null,
    llm_item_id: null,
    granularity_level: 'macro',
    granularity_family: 'macro_clinical',
    source_atlas: 'AAL3',
    source_version: 'v1',
    connection_type: 'structural_connection',
    directionality: 'directed',
    strength: null,
    modality: null,
    confidence: 0.7,
    evidence_text: null,
    uncertainty_reason: null,
    mirror_status: 'llm_suggested',
    review_status: 'pending',
    promotion_status: 'not_promoted',
    raw_payload_json: {},
    normalized_payload_json: {},
    created_by: null,
    updated_by: null,
    created_at: '2026-08-21T00:00:00Z',
    updated_at: '2026-08-21T00:00:00Z',
    ...overrides,
  }
}

function makeFunction(overrides: Partial<MirrorRegionFunction> = {}): MirrorRegionFunction {
  return {
    id: 'fn-1',
    canonical_id: 'ng:fn:1',
    region_candidate_id: 'cand-1',
    region_final_id: null,
    region_name_cn: '海马',
    region_name_en: 'Hippocampus',
    resource_id: 'res-1',
    batch_id: 'batch-1',
    llm_run_id: null,
    llm_item_id: null,
    granularity_level: 'macro',
    granularity_family: 'macro_clinical',
    source_atlas: 'AAL3',
    source_version: 'v1',
    function_term: 'memory encoding',
    function_category: 'memory',
    relation_type: 'has_function',
    confidence: 0.85,
    evidence_text: null,
    uncertainty_reason: null,
    mirror_status: 'llm_suggested',
    review_status: 'pending',
    promotion_status: 'not_promoted',
    created_at: '2026-08-21T00:00:00Z',
    updated_at: '2026-08-21T00:00:00Z',
    ...overrides,
  }
}

function makeCircuit(overrides: Partial<MirrorRegionCircuit> = {}): MirrorRegionCircuit {
  return {
    id: 'circuit-1',
    canonical_id: 'ng:circuit:1',
    resource_id: 'res-1',
    batch_id: 'batch-1',
    llm_run_id: null,
    llm_item_id: null,
    granularity_level: 'macro',
    granularity_family: 'macro_clinical',
    source_atlas: 'AAL3',
    source_version: 'v1',
    circuit_name: 'Papez circuit',
    name_cn: '帕佩兹回路',
    circuit_type: 'functional_circuit',
    function_association: null,
    description: null,
    confidence: 0.6,
    evidence_text: null,
    uncertainty_reason: null,
    mirror_status: 'llm_suggested',
    review_status: 'pending',
    promotion_status: 'not_promoted',
    created_at: '2026-08-21T00:00:00Z',
    updated_at: '2026-08-21T00:00:00Z',
    ...overrides,
  }
}

function makeSource(): MirrorGraphSourceData {
  return {
    center: makeCandidate(),
    connections: [makeConnection()],
    functions: [makeFunction()],
    circuits: [makeCircuit()],
  }
}

// ─── 适配主函数 ──────────────────────────────────────────────────────────────

describe('adaptMirrorGraphResponse', () => {
  it('中心脑区 + 远端脑区 + 连接/功能/回路节点全部进入图', () => {
    const graph = adaptMirrorGraphResponse(makeSource())
    expect(graph.nodes).toHaveLength(5) // cand-1 + cand-2 + conn + fn + circuit
    const byId = new Map(graph.nodes.map(n => [n.id, n]))
    expect(byId.get('region:cand-1')?.type).toBe('brain_region')
    expect(byId.get('region:cand-2')?.label).toBe('Entorhinal')
    expect(byId.get('projection:conn-1')?.type).toBe('connection')
    expect(byId.get('region_function:fn-1')?.type).toBe('function')
    expect(byId.get('circuit:circuit-1')?.label).toBe('帕佩兹回路') // name_cn 优先
  })

  it('边语义与 Final 图一致：projection_source/target + has_function + participates_in', () => {
    const graph = adaptMirrorGraphResponse(makeSource())
    const types = graph.edges.map(e => e.type).sort()
    expect(types).toEqual([
      'has_function',
      'participates_in',
      'projection_source',
      'projection_target',
    ])
    const ps = graph.edges.find(e => e.type === 'projection_source')
    expect(ps?.source).toBe('region:cand-1')
    expect(ps?.target).toBe('projection:conn-1')
    const pt = graph.edges.find(e => e.type === 'projection_target')
    expect(pt?.source).toBe('projection:conn-1')
    expect(pt?.target).toBe('region:cand-2')
    const hf = graph.edges.find(e => e.type === 'has_function')
    expect(hf?.source).toBe('region:cand-1')
    expect(hf?.target).toBe('region_function:fn-1')
    const pi = graph.edges.find(e => e.type === 'participates_in')
    expect(pi?.source).toBe('region:cand-1')
    expect(pi?.target).toBe('circuit:circuit-1')
  })

  it('connection 节点标注 "source → target" 可由 graphToXyflow 派生（两侧脑区名在位）', () => {
    const graph = adaptMirrorGraphResponse(makeSource())
    const labelById = new Map(graph.nodes.map(n => [n.id, n.label]))
    const src = graph.edges.find(e => e.type === 'projection_source')!
    const tgt = graph.edges.find(e => e.type === 'projection_target')!
    expect(labelById.get(src.source)).toBe('Hippocampus')
    expect(labelById.get(tgt.target)).toBe('Entorhinal')
  })

  it('镜像溯源 metadata：canonical_id / source_id / provenance.source=mirror / 状态字段', () => {
    const graph = adaptMirrorGraphResponse(makeSource())
    const conn = graph.nodes.find(n => n.id === 'projection:conn-1')!
    expect(conn.metadata.canonical_id).toBe('ng:conn:1')
    expect(conn.metadata.source_id).toBe('conn-1')
    expect(conn.metadata.provenance).toEqual({
      source: 'mirror',
      source_atlas: 'AAL3',
      mirror_status: 'llm_suggested',
      review_status: 'pending',
      granularity_family: 'macro_clinical',
    })
    expect(conn.metadata.granularity).toBe('macro')
    expect(conn.metadata.confidence).toBe(0.7)
    const center = graph.nodes.find(n => n.id === 'region:cand-1')!
    expect(center.metadata.provenance.source).toBe('mirror')
    expect(center.metadata.provenance.candidate_status).toBe('candidate_created')
    expect(center.metadata.canonical_id).toBeNull()
  })

  it('边 metadata.predicate 取语义谓词，source 取镜像对象 id，confidence 透传', () => {
    const graph = adaptMirrorGraphResponse(makeSource())
    const hf = graph.edges.find(e => e.type === 'has_function')!
    expect(hf.metadata.predicate).toBe('has_function')
    expect(hf.metadata.source).toBe('fn-1')
    expect(hf.metadata.confidence).toBe(0.85)
    const ps = graph.edges.find(e => e.type === 'projection_source')!
    expect(ps.metadata.source).toBe('conn-1')
    expect(ps.metadata.confidence).toBe(0.7)
  })

  it('中心脑区在无任何关系时依然存在', () => {
    const graph = adaptMirrorGraphResponse({ center: makeCandidate(), connections: [], functions: [], circuits: [] })
    expect(graph.nodes).toHaveLength(1)
    expect(graph.centerNodeId).toBe('region:cand-1')
    expect(graph.edges).toEqual([])
  })

  it('连接缺少源/目标候选 id 时跳过并记录 warning', () => {
    const graph = adaptMirrorGraphResponse({
      center: makeCandidate(),
      connections: [makeConnection({ id: 'conn-bad', target_region_candidate_id: null })],
      functions: [],
      circuits: [],
    })
    expect(graph.nodes).toHaveLength(1) // 仅中心
    expect(graph.warnings).toHaveLength(1)
    expect(graph.warnings[0]).toContain('conn-bad')
  })

  it('源=目标=中心的自连接不产生重复节点', () => {
    const graph = adaptMirrorGraphResponse({
      center: makeCandidate(),
      connections: [makeConnection({ target_region_candidate_id: 'cand-1', target_region_name_en: 'Hippocampus' })],
      functions: [],
      circuits: [],
    })
    const regionNodes = graph.nodes.filter(n => n.type === 'brain_region')
    expect(regionNodes).toHaveLength(1)
    expect(graph.edges).toHaveLength(2)
  })

  it('多连接共享远端脑区时节点按 id 去重', () => {
    const source = makeSource()
    source.connections = [
      makeConnection(),
      makeConnection({ id: 'conn-2', canonical_id: null, confidence: 0.5 }),
    ]
    const graph = adaptMirrorGraphResponse(source)
    const regionNodes = graph.nodes.filter(n => n.type === 'brain_region')
    expect(regionNodes).toHaveLength(2)
    expect(graph.nodes).toHaveLength(6)
    expect(graph.edges).toHaveLength(6) // 2 连接×2 边 + 功能 + 回路
  })

  it('是纯函数：不修改输入对象', () => {
    const source = makeSource()
    const frozen = JSON.parse(JSON.stringify(source))
    adaptMirrorGraphResponse(source)
    expect(source).toEqual(frozen)
  })
})

// ─── 镜像模式展开（仅 brain_region）──────────────────────────────────────────

describe('mirror expand gating', () => {
  const graph = adaptMirrorGraphResponse(makeSource())
  const node = (id: string): CanonicalNode => graph.nodes.find(n => n.id === id)!

  it('brain_region 可展开，请求携带 candidate_id', () => {
    expect(canExpandMirrorNode(node('region:cand-2'))).toBe(true)
    expect(expandRequestForMirrorNode(node('region:cand-2'))).toEqual({ candidate_id: 'cand-2' })
  })

  it('connection / circuit / function 在镜像模式不可展开', () => {
    expect(canExpandMirrorNode(node('projection:conn-1'))).toBe(false)
    expect(canExpandMirrorNode(node('circuit:circuit-1'))).toBe(false)
    expect(canExpandMirrorNode(node('region_function:fn-1'))).toBe(false)
    expect(expandRequestForMirrorNode(node('circuit:circuit-1'))).toBeNull()
  })
})
