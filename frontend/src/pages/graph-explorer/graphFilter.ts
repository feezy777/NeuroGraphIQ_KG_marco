/**
 * 前端展示过滤（Phase 7）：
 * 只过滤画布展示——不修改数据库、不发新请求、不改后端返回数据。
 * - 实体类型过滤：空集合 = 全部可见
 * - 粒度过滤：'' = 全部；指定时隐藏不匹配节点；
 *   粒度未知（null，图 API 未下发）的节点保留——无法判断时不隐藏（不假装知道）
 * - 关系分组过滤：空集合 = 全部可见；边被隐藏时节点保留
 */
import type { CanonicalGraph, CanonicalNodeType } from './adapters/finalKgAdapter'
import { relationGroupOf } from './adapters/finalKgAdapter'

export interface DisplayFilters {
  /** 可见实体类型（空 = 全部） */
  entityTypes: Set<CanonicalNodeType>
  /** 粒度值（'' = 全部） */
  granularity: string
  /** 可见关系分组（空 = 全部） */
  relationGroups: Set<string>
}

export function emptyDisplayFilters(): DisplayFilters {
  return { entityTypes: new Set(), granularity: '', relationGroups: new Set() }
}

export function filterCanonicalGraph(graph: CanonicalGraph, filters: DisplayFilters): CanonicalGraph {
  const nodes = graph.nodes.filter(n => {
    if (filters.entityTypes.size > 0 && !filters.entityTypes.has(n.type)) return false
    if (filters.granularity && n.metadata.granularity && n.metadata.granularity !== filters.granularity) {
      return false
    }
    return true
  })
  const visibleIds = new Set(nodes.map(n => n.id))
  const edges = graph.edges.filter(e => {
    if (!visibleIds.has(e.source) || !visibleIds.has(e.target)) return false
    if (filters.relationGroups.size > 0 && !filters.relationGroups.has(relationGroupOf(e))) return false
    return true
  })
  return { nodes, edges, centerNodeId: graph.centerNodeId, warnings: graph.warnings }
}

/** 切换 Set 成员（不可变：返回新 Set） */
export function toggleSetValue<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}
