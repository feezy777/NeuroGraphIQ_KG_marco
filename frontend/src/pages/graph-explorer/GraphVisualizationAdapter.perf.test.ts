/**
 * Graph Visualization Adapter 性能基准（合成图,headless cytoscape）：
 * 规格第七阶段 —— 100 nodes/500 edges 与 1000 nodes/5000 edges 布局不卡死。
 * 计时宽松（CI 稳定性）：主链路 ≤15s;并输出精确数字供报告。
 */
import { describe, expect, it } from 'vitest'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import { layoutOptionsOf, toCyElements } from './GraphVisualizationAdapter'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode } from './adapters/finalKgAdapter'

cytoscape.use(fcose)

function synthGraph(nodes: number, edges: number): CanonicalGraph {
  const types: CanonicalNode['type'][] = ['brain_region', 'connection', 'circuit', 'circuit_step', 'function', 'evidence']
  const typeWeight = [0.62, 0.08, 0.12, 0.06, 0.08, 0.04]
  const ns: CanonicalNode[] = []
  for (let i = 0; i < nodes; i++) {
    let acc = 0
    let t: CanonicalNode['type'] = 'brain_region'
    const r = (i * 7919) % 1000 / 1000 // 确定性伪随机（无 Math.random）
    for (let k = 0; k < types.length; k++) {
      acc += typeWeight[k]
      if (r <= acc) { t = types[k]; break }
    }
    ns.push({
      id: t === 'brain_region' ? `region:region-${i}` : `${t}:elem-${i}`,
      type: t,
      label: `Region ${i}`,
      entityId: String(i),
      metadata: { canonical_id: null, source_id: null, provenance: {}, granularity: 'macro', confidence: 0.4 + (i % 50) / 100, raw: {} },
    })
  }
  const es: CanonicalEdge[] = []
  for (let i = 0; i < edges; i++) {
    const s = ns[((i * 31) % nodes)]
    const t = ns[((i * 47 + 13) % nodes)]
    if (s.id === t.id) continue
    es.push({
      id: `connection:edge-${i}`,
      source: s.id,
      target: t.id,
      type: 'connection',
      label: 'structural',
      metadata: {
        predicate: 'structural',
        source: `edge-${i}`,
        confidence: 0.5,
        raw: { connection: { connection_id: `edge-${i}`, connection_code: 'ng:cn:synthetic', connection_type: 'structural', direction: 'directed', confidence: 0.5, evidence_count: i % 9, evidence_quality_score: 'medium' } },
      },
    })
  }
  return { nodes: ns, edges: es, centerNodeId: ns[0]?.id ?? null, warnings: [] }
}

function bench(graph: CanonicalGraph): number {
  const t0 = performance.now()
  const els = toCyElements(graph, graph.centerNodeId)
  const t1 = performance.now()
  const cy = cytoscape({ headless: true, elements: els })
  const layout = cy.layout(layoutOptionsOf(graph))
  layout.run()
  const t2 = performance.now()
  // 校验边数（转换守恒）
  const edgeCount = cy.elements('edge').length
  const nodeCount = cy.elements('node').length
  if (edgeCount !== graph.edges.length || nodeCount !== graph.nodes.length) {
    throw new Error(`mismatch nodes=${nodeCount}/${graph.nodes.length} edges=${edgeCount}/${graph.edges.length}`)
  }
  cy.destroy()
  // eslint-disable-next-line no-console -- benchmark 输出
  console.log(`[perf] nodes=${graph.nodes.length} edges=${graph.edges.length} convert=${(t1 - t0).toFixed(1)}ms layout=${(t2 - t1).toFixed(1)}ms total=${(t2 - t0).toFixed(1)}ms`)
  return t2 - t0
}

describe('GraphVisualizationAdapter 性能（合成图）', () => {
  it('100 nodes / 500 edges：流畅（<2s）', () => {
    const total = bench(synthGraph(100, 500))
    expect(total).toBeLessThan(2000)
  }, 10000)

  it('1000 nodes / 5000 edges：可接受（<15s;draft 布局）', () => {
    const total = bench(synthGraph(1000, 5000))
    expect(total).toBeLessThan(15000)
  }, 30000)
})
