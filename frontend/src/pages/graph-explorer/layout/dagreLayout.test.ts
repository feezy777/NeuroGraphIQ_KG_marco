import { describe, expect, it } from 'vitest'
import type { CanonicalEdge, CanonicalNode } from '../adapters/finalKgAdapter'
import { DAGRE_MAX_NODES, layoutCanonicalGraph, measureNode } from './dagreLayout'

function makeNode(id: string, type: CanonicalNode['type'], label?: string): CanonicalNode {
  return {
    id,
    type,
    label: label ?? id,
    entityId: id,
    metadata: { canonical_id: null, source_id: null, provenance: {}, granularity: null, confidence: null, raw: {} },
  }
}

function makeEdge(id: string, source: string, target: string): CanonicalEdge {
  return {
    id,
    source,
    target,
    type: 'has_function',
    label: null,
    metadata: { predicate: 'has_function', source: null, confidence: null, raw: {} },
  }
}

/** 两两矩形不重叠 */
function assertNoOverlap(nodes: CanonicalNode[], positions: Map<string, { x: number; y: number }>): void {
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i]
      const b = nodes[j]
      const pa = positions.get(a.id)
      const pb = positions.get(b.id)
      if (!pa || !pb) continue
      const sa = measureNode(a)
      const sb = measureNode(b)
      const overlap =
        pa.x < pb.x + sb.width && pa.x + sa.width > pb.x && pa.y < pb.y + sb.height && pa.y + sa.height > pb.y
      expect(overlap, `nodes "${a.id}" and "${b.id}" must not overlap`).toBe(false)
    }
  }
}

describe('layoutCanonicalGraph（Phase 3 确定性布局）', () => {
  it('空图返回空位置表', () => {
    expect(layoutCanonicalGraph([], []).size).toBe(0)
  })

  it('单节点有有限位置', () => {
    const node = makeNode('r1', 'brain_region')
    const positions = layoutCanonicalGraph([node], [], 'r1')
    const p = positions.get('r1')
    expect(p).toBeDefined()
    expect(Number.isFinite(p!.x)).toBe(true)
    expect(Number.isFinite(p!.y)).toBe(true)
  })

  it('相同输入产生相同输出（确定性，无随机）', () => {
    const nodes = [makeNode('r1', 'brain_region'), makeNode('f1', 'function'), makeNode('c1', 'circuit')]
    const edges = [makeEdge('e1', 'r1', 'f1'), makeEdge('e2', 'r1', 'c1')]
    const first = layoutCanonicalGraph(nodes, edges, 'r1')
    const second = layoutCanonicalGraph(nodes, edges, 'r1')
    for (const id of ['r1', 'f1', 'c1']) {
      expect(second.get(id)).toEqual(first.get(id))
    }
  })

  it('Function 在中心上方，Circuit 在中心下方（三段带）', () => {
    const nodes = [
      makeNode('r1', 'brain_region', 'Region'),
      makeNode('f1', 'function', 'Function'),
      makeNode('c1', 'circuit', 'Circuit'),
    ]
    const edges = [makeEdge('e1', 'r1', 'f1'), makeEdge('e2', 'r1', 'c1')]
    const positions = layoutCanonicalGraph(nodes, edges, 'r1')
    const py = positions.get('r1')!.y
    expect(positions.get('f1')!.y).toBeLessThan(py)
    expect(positions.get('c1')!.y).toBeGreaterThan(py)
  })

  it('节点两两不重叠', () => {
    const nodes = [
      makeNode('r1', 'brain_region', 'Hippocampus'),
      makeNode('r2', 'brain_region', 'Amygdala'),
      makeNode('p1', 'connection', 'Hippocampus → Amygdala'),
      makeNode('f1', 'function', 'Memory Consolidation'),
      makeNode('c1', 'circuit', 'Papez Circuit'),
      makeNode('s1', 'circuit_step', 'Step 1'),
      makeNode('v1', 'evidence', 'Evidence A'),
    ]
    const edges = [
      makeEdge('e1', 'r1', 'p1'),
      makeEdge('e2', 'p1', 'r2'),
      makeEdge('e3', 'r1', 'f1'),
      makeEdge('e4', 'r1', 'c1'),
      makeEdge('e5', 'c1', 's1'),
      makeEdge('e6', 'r1', 'v1'),
    ]
    const positions = layoutCanonicalGraph(nodes, edges, 'r1')
    for (const n of nodes) expect(positions.get(n.id), `position of ${n.id}`).toBeDefined()
    assertNoOverlap(nodes, positions)
  })
})

describe('layoutCanonicalGraph（大图确定性网格回退，性能护栏）', () => {
  /** 351 个节点（1 中心 + 200 脑区 + 148 连接 + 1 功能 + 1 回路）> DAGRE_MAX_NODES */
  function makeLargeGraph(): { nodes: CanonicalNode[]; edges: CanonicalEdge[] } {
    const nodes: CanonicalNode[] = [makeNode('center', 'brain_region', 'Center Region')]
    for (let i = 0; i < 200; i++) nodes.push(makeNode(`r${i}`, 'brain_region', `Region ${i}`))
    for (let i = 0; i < 148; i++) nodes.push(makeNode(`c${i}`, 'connection', `Connection ${i}`))
    nodes.push(makeNode('f1', 'function', 'Function A'))
    nodes.push(makeNode('circ1', 'circuit', 'Circuit A'))
    const edges = [makeEdge('e-f', 'center', 'f1'), makeEdge('e-c', 'center', 'circ1')]
    return { nodes, edges }
  }

  it('超过 DAGRE_MAX_NODES 时所有节点有有限位置且两两不重叠', () => {
    const { nodes, edges } = makeLargeGraph()
    expect(nodes.length).toBeGreaterThan(DAGRE_MAX_NODES)
    const positions = layoutCanonicalGraph(nodes, edges, 'center')
    expect(positions.size).toBe(nodes.length)
    for (const n of nodes) {
      const p = positions.get(n.id)
      expect(p, `position of ${n.id}`).toBeDefined()
      expect(Number.isFinite(p!.x)).toBe(true)
      expect(Number.isFinite(p!.y)).toBe(true)
    }
    assertNoOverlap(nodes, positions)
  })

  it('大图网格布局确定性（两次结果一致）', () => {
    const { nodes, edges } = makeLargeGraph()
    const first = layoutCanonicalGraph(nodes, edges, 'center')
    const second = layoutCanonicalGraph(nodes, edges, 'center')
    for (const n of nodes) expect(second.get(n.id)).toEqual(first.get(n.id))
  })

  it('网格布局保持三段带：中心节点在原点，Function 在上方，Circuit 在下方', () => {
    const { nodes, edges } = makeLargeGraph()
    const positions = layoutCanonicalGraph(nodes, edges, 'center')
    expect(positions.get('center')).toEqual({ x: 0, y: 0 })
    expect(positions.get('f1')!.y).toBeLessThan(0)
    expect(positions.get('circ1')!.y).toBeGreaterThan(0)
  })

  it('网格布局列式排布：脑区同列、连接同列且连接列在脑区列右侧', () => {
    const { nodes, edges } = makeLargeGraph()
    const positions = layoutCanonicalGraph(nodes, edges, 'center')
    const regionXs = new Set(nodes.filter(n => n.type === 'brain_region').map(n => positions.get(n.id)!.x))
    const connXs = new Set(nodes.filter(n => n.type === 'connection').map(n => positions.get(n.id)!.x))
    expect(regionXs.size).toBe(1)
    expect(connXs.size).toBe(1)
    expect([...connXs][0]).toBeGreaterThan([...regionXs][0])
  })
})
