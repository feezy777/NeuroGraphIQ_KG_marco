import type { OntologyEntityType } from '../pages/ontology-center/browser/tree/OntologyTreeNode'
import type {
  EntityDetailData,
  EntityRef,
  RelationGroup,
} from '../pages/ontology-center/detail/types'

/**
 * Phase 5：Graph Explorer 预留模型。
 * Tree Explorer 与 Graph Explorer 共享数据源（ontologyApi 的 EntityRef / RelationGroup），
 * 未来接 xyflow / react-flow 时直接把 buildGraph() 的输出映射为 nodes/edges 即可。
 */

export interface GraphNode {
  id: string
  /** entityType（region/connection/circuit/function）→ 图里按类型着色/图标 */
  type: OntologyEntityType
  label: string
  code?: string | null
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relationType: string
}

/** EntityRef → GraphNode（树节点 / 关系行 / 详情引用共用同一转换） */
export function toGraphNode(ref: EntityRef): GraphNode {
  return { id: ref.id, type: ref.entityType, label: ref.name, code: ref.code }
}

/**
 * 以中心实体为锚点，把详情 + 关系展开为一组 nodes/edges。
 * - 节点：中心实体 + 关系组中所有 EntityRef（去重）
 * - 边：中心 → 各关系目标，relationType = RelationGroup.label
 * 不自动生成关系：edges 只来自后端返回的真实关系数据。
 */
export function buildGraph(
  center: EntityDetailData,
  relations: RelationGroup[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes = new Map<string, GraphNode>()
  nodes.set(center.id, { id: center.id, type: center.entityType, label: center.name, code: center.code })

  const edges: GraphEdge[] = []
  for (const group of relations) {
    if (group.unavailable) continue // 后端无 API 的关系不进入图
    for (const item of group.items) {
      const ref = item.ref
      if (!nodes.has(ref.id)) {
        nodes.set(ref.id, toGraphNode(ref))
      }
      edges.push({
        id: `${center.id}->${ref.id}:${group.key}`,
        source: center.id,
        target: ref.id,
        relationType: group.label,
      })
    }
  }
  return { nodes: [...nodes.values()], edges }
}
