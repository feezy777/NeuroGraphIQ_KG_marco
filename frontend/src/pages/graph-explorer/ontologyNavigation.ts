/**
 * Phase 8 双向跳转的 URL 组装与导航决策（纯函数，便于测试）：
 *
 * 方向 1（Ontology Center → Graph Explorer）：
 *   EntityDetailPanel「Open in Graph」→ #/graph-explorer?view=canonical&entity={canonicalRegionId}
 *   图侧用 listRegionCandidates 解析出第一个 candidate_id，以 region 为中心加载。
 *
 * 方向 2（Graph Explorer → Ontology Center）：
 *   - brain_region 节点：先 resolve-candidate 解析 canonical_region_id，成功 → 直达实体详情；
 *     失败 → 退化为按名称搜索（诚实降级，不猜测映射）。
 *   - circuit / function / connection 节点：按节点名称搜索（无 canonical id 映射端点）。
 *   - circuit_step / evidence：无本体对应实体 → 不提供跳转。
 */
import { buildHashUrl } from '../../utils/pipelineNavigation'
import type { CandidateCanonicalResolution } from '../../api/endpoints'
import type { OntologyEntityType } from '../ontology-center/browser/tree/OntologyTreeNode'
import type { CanonicalNode } from './adapters/finalKgAdapter'

/** 本体中心实体详情直达 URL（tab=browser + entity_type + entity） */
export function ontologyCenterEntityUrl(entityType: OntologyEntityType, entityId: string): string {
  return buildHashUrl('/ontology-center', { tab: 'browser', entity_type: entityType, entity: entityId })
}

/** 本体中心按名称搜索 URL（tab=browser + search） */
export function ontologyCenterSearchUrl(query: string): string {
  return buildHashUrl('/ontology-center', { tab: 'browser', search: query })
}

/** 图谱探索 Canonical KG 实体定位 URL（view=canonical + entity） */
export function graphExplorerEntityUrl(entityId: string): string {
  return buildHashUrl('/graph-explorer', { view: 'canonical', entity: entityId })
}

/**
 * 图节点 → 本体中心跳转 URL。
 * @param resolution brain_region 节点的 candidate → canonical 解析结果（其他类型传 null）
 * @returns 可导航的 hash URL；无合理跳转目标时返回 null（不渲染按钮）
 */
export function ontologyNavigationUrlFor(
  node: CanonicalNode,
  resolution: CandidateCanonicalResolution | null,
): string | null {
  if (node.type === 'brain_region' && resolution?.resolved && resolution.canonical_region_id) {
    return ontologyCenterEntityUrl('region', resolution.canonical_region_id)
  }
  // circuit_step / evidence 无本体实体对应 → 不提供跳转
  if (node.type === 'circuit_step' || node.type === 'evidence') return null
  const query = node.label.trim()
  if (!query) return null
  // connection/circuit/function 无 id 映射端点 → 按名称搜索降级
  return ontologyCenterSearchUrl(query)
}
