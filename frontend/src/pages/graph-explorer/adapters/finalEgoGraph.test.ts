/**
 * Graph Explorer Data Adapter V1 —— finalEgoGraph 纯函数测试（不碰网络/DB）。
 * 核心断言（用户验收维度）：
 * 1. 构造图中没有 connection 类型节点（连接折叠为 region--region 边）
 * 2. 每条 connection edge 携带 connection_id / connection_type / direction /
 *    confidence / evidence_count / evidence_quality_score metadata
 * 3. Ego 语义：中心 + 两端邻居节点；中心精确名节点始终存在
 * 4. 单端缺失连接不造边（诚信降级,warning）
 * 5. region 目录本地搜索确定性（大小写不敏感,子串）
 */
import { describe, expect, it } from 'vitest'
import {
  buildFinalEgoGraph,
  buildMirrorPanoramaGraph,
  searchCanonicalRegions,
  type CanonicalConnectionSummary,
} from './finalEgoGraph'
import type { CanonicalRegion } from '../../../api/endpoints'

const CENTER = 'Hippocampus'
const A = 'Entorhinal Cortex'
const B = 'Prefrontal Cortex'

function summary(overrides: Partial<CanonicalConnectionSummary> = {}): CanonicalConnectionSummary {
  return {
    canonical_connection_id: 'conn-1',
    connection_code: 'ng:cn:structural_hippocampus_to_entorhinal',
    source_region: CENTER,
    target_region: A,
    connection_type: 'structural',
    directionality_policy: 'directed',
    evidence_count: 12,
    confidence: { min: 0.5, max: 0.9, mean: 0.7 },
    evidence_quality_score: 'medium',
    ...overrides,
  }
}

describe('finalEgoGraph（连接折叠为边 + ego 查询）', () => {
  it('构造图中不含 connection 类型节点（连接折叠为 region--region 边）', () => {
    const graph = buildFinalEgoGraph({
      centerName: CENTER,
      connections: [summary(), summary({ canonical_connection_id: 'conn-2', target_region: B })],
    })
    expect(graph.nodes.every(n => n.type !== 'connection')).toBe(true)
    expect(graph.nodes.map(n => n.label).sort()).toEqual([CENTER, A, B].sort())
    expect(graph.edges).toHaveLength(2)
    expect(graph.centerNodeId).toBe(`region:${CENTER}`)
  })

  it('每条 connection edge 携带规定的 metadata 字段（evidence_count 真实来自后端）', () => {
    const graph = buildFinalEgoGraph({ centerName: CENTER, connections: [summary()] })
    const edge = graph.edges[0]
    const meta = edge.metadata.raw.connection as {
      connection_id: string
      connection_code: string
      connection_type: string
      direction: string
      confidence: number | null
      evidence_count: number
      evidence_quality_score: string | null
    }
    expect(meta.connection_id).toBe('conn-1')
    expect(meta.connection_code).toBe('ng:cn:structural_hippocampus_to_entorhinal')
    expect(meta.connection_type).toBe('structural')
    expect(meta.direction).toBe('directed')
    expect(meta.confidence).toBe(0.7)
    expect(meta.evidence_count).toBe(12)
    expect(meta.evidence_quality_score).toBe('medium')
    expect(edge.source).toBe(`region:${CENTER}`)
    expect(edge.target).toBe(`region:${A}`)
  })

  it('中心精确名节点始终存在（即使零连接）', () => {
    const graph = buildFinalEgoGraph({ centerName: CENTER, connections: [] })
    expect(graph.nodes).toHaveLength(1)
    expect(graph.nodes[0].label).toBe(CENTER)
    expect(graph.edges).toHaveLength(0)
  })

  it('单端缺失连接不造边（诚信降级）+ warning', () => {
    const graph = buildFinalEgoGraph({
      centerName: CENTER,
      connections: [summary({ target_region: null })],
    })
    expect(graph.nodes).toHaveLength(1) // 只有中心,无虚构邻居
    expect(graph.edges).toHaveLength(0)
    expect(graph.warnings.join()).toContain('单端缺失')
  })

  it('Ego 语义：与中心同名命中的非锚定连接仍保留在图（后端 ILIKE 子串命中）', () => {
    // 例如 center="Hippocampus" 时 ILIKE 命中 "Hippocampo-amygdalar transition area" 的投影
    const graph = buildFinalEgoGraph({
      centerName: CENTER,
      connections: [
        summary(),
        summary({
          canonical_connection_id: 'conn-x',
          source_region: 'Hippocampo-amygdalar transition area',
          target_region: B,
        }),
      ],
    })
    expect(graph.nodes.map(n => n.label)).toContain(B)
    expect(graph.edges).toHaveLength(2)
    // 非锚定边标记 center_anchored=false
    const x = graph.edges.find(e => e.id === 'connection:conn-x')
    expect(x?.metadata.raw.center_anchored).toBe(false)
  })

  it('region 目录本地搜索：大小写不敏感子串 + limit', () => {
    const directory: CanonicalRegion[] = [
      { canonical_name_en: 'Hippocampus', granularity_level: 'macro' },
      { canonical_name_en: 'Hippocampo-amygdalar transition area', granularity_level: 'sub_connectivity' },
      { canonical_name_en: 'Entorhinal Cortex', granularity_level: 'meso' },
    ] as CanonicalRegion[]
    const hits = searchCanonicalRegions(directory, 'hippocamP', 10)
    expect(hits.map(r => r.canonical_name_en)).toEqual([
      'Hippocampus',
      'Hippocampo-amygdalar transition area',
    ])
    expect(searchCanonicalRegions(directory, '   ', 10)).toHaveLength(0)
    expect(searchCanonicalRegions(directory, 'Hippocampus', 1)).toHaveLength(1)
  })
})

// ── Macro 全景（电路折叠为脑区+连接） ────────────────────────────────────────────
describe('buildMirrorPanoramaGraph（macro 全景:回路以脑区+连接呈现）', () => {
  const conn = (id: string, s: string, t: string) => ({
    id,
    granularity_level: 'macro',
    connection_type: 'structural',
    directionality: 'directed',
    confidence: 0.5,
    source_region_candidate_id: 'cand-s',
    source_region_name_en: s,
    target_region_candidate_id: 'cand-t',
    target_region_name_en: t,
  }) as never

  it('不产生 circuit 节点（回路以脑区+连接呈现）', () => {
    const g = buildMirrorPanoramaGraph({
      connections: [conn('c1', 'Hippocampus', 'Cerebellum')],
      circuits: [{ id: 'circuit-a', circuit_name: 'Memory Circuit' }],
      functions: [{ id: 'f1', function_term: 'Memory consolidation' }],
    })
    expect(g.nodes.every(n => n.type !== 'circuit')).toBe(true)
    expect(g.nodes.filter(n => n.type === 'function')).toHaveLength(1)
    expect(g.nodes.filter(n => n.type === 'brain_region')).toHaveLength(2)
    expect(g.edges).toHaveLength(1)
    expect(g.edges[0].type).toBe('connection')
    expect(g.warnings.join()).toContain('回路以脑区+连接呈现')
  })
})
