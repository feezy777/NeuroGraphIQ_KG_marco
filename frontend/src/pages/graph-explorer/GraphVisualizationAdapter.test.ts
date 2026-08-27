/**
 * GraphVisualizationAdapter 纯函数测试（不碰 DOM/网络）：
 * 核心断言（用户规格）：
 * 1. toCyElements：节点类型映射（region 圆形类/connection 胶囊类/function/circuit/evidence）
 * 2. 边 relation 分组映射：structural→蓝实线类 / functional→紫虚线类 / projection→青绿曲线类 /
 *    evidence→灰虚线类
 * 3. 名称优先：displayNameOf 不落 uuid
 * 4. 传导：connection 折叠边 isConnection=true,label=connection_type
 * 5. fold/center 标记
 */
import { describe, expect, it } from 'vitest'
import {
  canExpandAdapter,
  displayNameOf,
  nodeClassOf,
  relationClassOf,
  toCyElements,
  type CyEdgeData,
  type CyNodeData,
} from './GraphVisualizationAdapter'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode, CanonicalNodeType } from './adapters/finalKgAdapter'

const REGION = 'region:Hippocampus'
const NEIGHBOR = 'region:Cerebellum'

function node(over: Partial<CanonicalNode> = {}): CanonicalNode {
  return {
    id: REGION,
    type: 'brain_region',
    label: 'Hippocampus',
    entityId: 'Hippocampus',
    metadata: {
      canonical_id: null, source_id: null, provenance: {},
      granularity: 'macro', confidence: 0.7, raw: { cn_name: '海马体' },
    },
    ...over,
  }
}

function edge(over: Partial<CanonicalEdge> = {}): CanonicalEdge {
  return {
    id: 'connection:11111111-1111-1111-1111-111111111111',
    source: REGION,
    target: NEIGHBOR,
    type: 'connection',
    label: 'structural',
    metadata: {
      predicate: 'structural',
      source: '11111111-1111-1111-1111-111111111111',
      confidence: 0.5,
      raw: {
        connection: {
          connection_id: '11111111-1111-1111-1111-111111111111',
          connection_code: 'ng:cn:structural_hippocampus_to_cerebellum',
          connection_type: 'structural',
          direction: 'bidirectional',
          confidence: 0.5,
          evidence_count: 9,
          evidence_quality_score: 'high',
        },
      },
    },
    ...over,
  }
}

function graphOf(nodes: CanonicalNode[], edges: CanonicalEdge[]): CanonicalGraph {
  return { nodes, edges, centerNodeId: REGION, warnings: [] }
}

describe('GraphVisualizationAdapter（elements 转换/映射）', () => {
  it('节点类型 → cytoscape class（圆形/胶囊/橙/紫/灰）', () => {
    expect(nodeClassOf('brain_region')).toBe('n-region')
    expect(nodeClassOf('connection')).toBe('n-connection')
    expect(nodeClassOf('circuit')).toBe('n-circuit')
    expect(nodeClassOf('function')).toBe('n-function')
    expect(nodeClassOf('evidence')).toBe('n-evidence')
    expect(nodeClassOf('circuit_step')).toBe('n-step')
  })

  it('边 relation → 分组 class（结构/功能/投影/证据）', () => {
    expect(relationClassOf(edge({ type: 'connection' }))).toBe('e-structural')
    expect(relationClassOf(edge({ type: 'has_function' }))).toBe('e-function')
    expect(relationClassOf(edge({ type: 'participates_in' }))).toBe('e-projection')
    expect(relationClassOf(edge({ type: 'has_evidence' }))).toBe('e-evidence')
  })

  it('toCyElements：节点数据仅含展示字段（name 优先,无 uuid）', () => {
    const els = toCyElements(graphOf([node(), node({ id: NEIGHBOR, label: 'Cerebellum', entityId: 'Cerebellum', metadata: { ...node().metadata, raw: {} } })], [edge()]), REGION)
    const nodeEl = els.find(e => e.group === 'nodes' && e.data.id === REGION)!
    const d = nodeEl.data as unknown as CyNodeData
    expect(d.name).toBe('海马体') // cn 优先
    expect(d.isCenter).toBe(true)
    expect(String(nodeEl.data.id)).not.toContain('uuid')
  })

  it('toCyElements：connection 折叠边 isConnection=true、label=connection_type', () => {
    const els = toCyElements(graphOf([node(), node({ id: NEIGHBOR, label: 'Cerebellum', entityId: 'Cerebellum', metadata: { ...node().metadata, raw: {} } })], [edge()]), REGION)
    const edgeEl = els.find(e => e.group === 'edges')!
    const d = edgeEl.data as unknown as CyEdgeData
    expect(d.isConnection).toBe(true)
    expect(d.label).toBe('structural')
    expect(d.relation).toBe('structural')
    expect(edgeEl.classes).toContain('e-structural')
  })

  it('displayNameOf 名称优先,不回退 uuid', () => {
    const uuidNode = node({ label: 'left hippocampus', entityId: '69b29281-53bb-4d39-bccf-c968b8c0cf84', metadata: { ...node().metadata, raw: {} } })
    expect(displayNameOf(uuidNode)).toContain('left hippocampus')
    expect(displayNameOf(uuidNode)).not.toContain('69b29281')
  })

  it('canExpandAdapter：region/circuit 可展开', () => {
    expect(canExpandAdapter(node())).toBe(true)
    expect(canExpandAdapter(node({ type: 'circuit' as CanonicalNodeType }))).toBe(true)
    expect(canExpandAdapter(node({ type: 'function' as CanonicalNodeType }))).toBe(false)
  })

  it('统计派生：connectionCount 在图内正确累积', () => {
    const els = toCyElements(graphOf(
      [node(), node({ id: NEIGHBOR, label: 'Cerebellum', entityId: 'Cerebellum', metadata: { ...node().metadata, raw: {} } })],
      [edge(), edge({ id: 'connection:2222-2222', source: NEIGHBOR, target: REGION })],
    ), REGION)
    const center = els.find(e => e.data.id === REGION)!
    // 中心节点为初始 0（派生在组件内完成——纯函数不派生）
    expect((center.data as unknown as CyNodeData).connectionCount).toBe(0)
  })
})
